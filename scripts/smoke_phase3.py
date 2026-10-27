"""Run via stdin inside the API container, with the regular dispatcher stopped.
Uses real PostgreSQL + Redis + an isolated Linux Celery solo test worker.
Fault injection is confined to this test process; no production fault flag exists.
"""

import errno
import io
import json
import threading
import time
from uuid import uuid4
from unittest.mock import patch
import httpx
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select, func
from celery.contrib.testing.worker import start_worker
from app.core.db import Session
from app.models.job import Job, Result
from app.services.dispatcher import dispatch_once
from app.tasks.celery_app import celery_app
from app.converters.image_pdf import ImagePDFConverter

with Session() as db:
    active = db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.status.in_(["QUEUED", "PROCESSING", "RETRY_WAIT", "CANCEL_REQUESTED"])
        )
    )
assert active == 0, (
    "Active jobs exist; finish them before running the isolated integration harness"
)
queue = "phase3_test_" + uuid4().hex
celery_app.conf.task_routes = {"convertflow.convert": {"queue": queue}}
celery_app.conf.task_default_queue = queue
stop = threading.Event()
allow_dispatch = threading.Event()
encoded = threading.Event()
release = threading.Event()
plans = {}
errors = []
original = ImagePDFConverter.convert


def convert(sources, destination, options, on_page):
    identifier = sources[0].parent.name
    plan = plans.get(identifier, {})
    if plan.get("fail", 0) > 0:
        plan["fail"] -= 1
        raise OSError(errno.ENOSPC, "controlled transient storage error")
    count = original(ImagePDFConverter(), sources, destination, options, on_page)
    if plan.get("hold"):
        encoded.set()
        assert release.wait(15), "cancellation test timed out"
    return count


def scheduler():
    while not stop.wait(0.05):
        if allow_dispatch.is_set():
            try:
                dispatch_once()
            except Exception as exc:
                errors.append(repr(exc))
                stop.set()


def wait_for(client, identifier, status, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert not errors, errors
        response = client.get(f"/api/v1/jobs/{identifier}")
        response.raise_for_status()
        job = response.json()
        if job["status"] == status:
            return job
        time.sleep(0.05)
    raise AssertionError((identifier, status, job))


def create(client, name):
    allow_dispatch.clear()
    stream = io.BytesIO()
    Image.new("RGB", (100, 60), "#278b73").save(stream, "PNG")
    response = client.post(
        "/api/v1/jobs", files={"file": (name, stream.getvalue(), "image/png")}
    )
    response.raise_for_status()
    return response.json()["jobId"]


def history(client, identifier):
    response = client.get(f"/api/v1/jobs/{identifier}/attempts")
    response.raise_for_status()
    return response.json()["items"]


def action(client, identifier, name, generation):
    response = client.post(
        f"/api/v1/jobs/{identifier}/{name}", json={"expectedGeneration": generation}
    )
    response.raise_for_status()
    return response.json()


thread = threading.Thread(target=scheduler, daemon=True)
try:
    with (
        patch("app.tasks.convert.ImagePDFConverter.convert", side_effect=convert),
        patch("app.services.lifecycle.retry_delay", return_value=0.25),
        start_worker(
            celery_app,
            pool="solo",
            perform_ping_check=False,
            queues=[queue],
            loglevel="ERROR",
            shutdown_timeout=10,
        ),
        httpx.Client(base_url="http://127.0.0.1:8000", timeout=20) as client,
    ):
        thread.start()
        auto = create(client, "phase3-auto.png")
        plans[auto] = {"fail": 1}
        allow_dispatch.set()
        auto_job = wait_for(client, auto, "SUCCESS")
        auto_rows = history(client, auto)
        assert auto_job["attemptCount"] == 2 and [
            row["origin"] for row in auto_rows
        ] == ["AUTO", "INITIAL"]
        assert auto_rows[1]["status"] == "FAILED" and auto_rows[1]["retryable"]
        pdf = client.get(f"/api/v1/jobs/{auto}/download")
        pdf.raise_for_status()
        assert len(PdfReader(io.BytesIO(pdf.content)).pages) == 1

        exhausted = create(client, "phase3-exhausted.png")
        plans[exhausted] = {"fail": 4}
        allow_dispatch.set()
        failed = wait_for(client, exhausted, "FAILED")
        assert (
            failed["attemptCount"] == 4
            and failed["autoRetryCount"] == 3
            and failed["canRetry"]
        )
        failed_rows = history(client, exhausted)
        assert len(failed_rows) == 4 and all(
            row["status"] == "FAILED" for row in failed_rows
        )
        allow_dispatch.clear()
        manual = action(client, exhausted, "retry", failed["runGeneration"])
        assert manual["runGeneration"] == 5
        # Redeliver an obsolete generation while the new generation is queued.
        celery_app.send_task("convertflow.convert", args=[exhausted, 1], queue=queue)
        time.sleep(0.25)
        assert len(history(client, exhausted)) == 4
        allow_dispatch.set()
        success = wait_for(client, exhausted, "SUCCESS")
        manual_rows = history(client, exhausted)
        assert success["attemptCount"] == 5 and manual_rows[0]["origin"] == "MANUAL"
        assert manual_rows[1:] == failed_rows

        waiting = create(client, "phase3-wait-cancel.png")
        plans[waiting] = {"fail": 1}
        with patch("app.services.lifecycle.retry_delay", return_value=5):
            allow_dispatch.set()
            waiting_job = wait_for(client, waiting, "RETRY_WAIT")
            assert (
                action(client, waiting, "cancel", waiting_job["runGeneration"])[
                    "status"
                ]
                == "CANCELLED"
            )
        assert (
            len(history(client, waiting)) == 1
            and history(client, waiting)[0]["status"] == "FAILED"
        )

        pending = create(client, "phase3-queued-cancel.png")
        assert action(client, pending, "cancel", 1)["status"] == "CANCELLED"
        allow_dispatch.set()
        time.sleep(0.2)
        assert not history(client, pending)

        running = create(client, "phase3-publish-cancel.png")
        plans[running] = {"hold": True}
        allow_dispatch.set()
        assert encoded.wait(15), "worker never produced test PDF"
        assert action(client, running, "cancel", 1)["status"] == "CANCEL_REQUESTED"
        release.set()
        cancelled = wait_for(client, running, "CANCELLED")
        assert not cancelled["downloadAvailable"] and cancelled["result"] is None
        assert history(client, running)[0]["status"] == "CANCELLED"
        assert client.get(f"/api/v1/jobs/{running}/download").status_code == 409
        with Session() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Result)
                    .where(Result.job_id == running)
                )
                == 0
            )
        assert not errors, errors
        print(
            "PASS Phase 3 real Redis/PostgreSQL:",
            json.dumps(
                {
                    "autoRetryJob": auto,
                    "manualRetryJob": exhausted,
                    "attemptsPreserved": 5,
                    "cancelRetryWait": waiting,
                    "cancelQueued": pending,
                    "cancelBeforePublish": running,
                    "staleMessageIgnored": True,
                }
            ),
        )
finally:
    release.set()
    allow_dispatch.clear()
    stop.set()
    if thread.is_alive():
        thread.join(timeout=10)
