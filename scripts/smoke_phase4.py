"""Run inside API container, normal dispatcher stopped. Real PG/Redis/Celery.

Copy this file to /tmp/smoke_phase4.py, then python /tmp/smoke_phase4.py.
Fault hooks exist only in disposable child test workers, never product settings.
"""

import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from unittest.mock import patch
import httpx
from PIL import Image
from sqlalchemy import select, func
from app.core.db import Session
from app.models.job import Job, Attempt, Result, Event
from app.services.recovery import recover_once
from app.services.dispatcher import dispatch_once
from app.tasks.celery_app import celery_app


def wait(check, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.2)
    raise AssertionError("timed out waiting for fault scenario")


def worker():
    from app.tasks import convert

    root = Path(os.environ["FAULT_ROOT"])
    original = convert.ImagePDFConverter.convert
    replace = convert.os.replace

    def gate():
        (root / "reached").touch()
        wait(lambda: (root / "release").exists(), 180)

    def encode(self, *args, **kwargs):
        if os.environ["FAULT_MODE"] == "encode":
            gate()
        return original(self, *args, **kwargs)

    def publish(source, target):
        replace(source, target)
        if os.environ["FAULT_MODE"] == "publish":
            gate()

    convert.ImagePDFConverter.convert = encode
    convert.os.replace = publish
    celery_app.worker_main(
        [
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=WARNING",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "-Q",
            os.environ["FAULT_QUEUE"],
            "-n",
            "phase4-" + str(os.getpid()) + "@%h",
        ]
    )


def main():
    queue = "phase4-" + uuid4().hex
    children = []
    logs = []
    report = {}
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=10)
    send = celery_app.send_task

    def dispatch():
        def routed(*args, **kwargs):
            return send(*args, **kwargs, queue=queue)

        with patch.object(celery_app, "send_task", side_effect=routed):
            dispatch_once()

    def spawn(mode="none"):
        root = Path(tempfile.mkdtemp(prefix="phase4-"))
        log = (root / "worker.log").open("w")
        logs.append(log)
        process = subprocess.Popen(
            [sys.executable, __file__, "--worker"],
            stdout=log,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "FAULT_ROOT": str(root),
                "FAULT_QUEUE": queue,
                "FAULT_MODE": mode,
                "LEASE_SECONDS": "6",
                "HEARTBEAT_SECONDS": "1",
            },
        )
        children.append(process)
        return process, root

    def upload():
        image = io.BytesIO()
        Image.new("RGB", (80, 40), "red").save(image, "PNG")
        response = client.post(
            "/api/v1/jobs",
            files={"file": ("recovery.png", image.getvalue(), "image/png")},
        )
        assert response.status_code == 202, response.text
        return response.json()["jobId"]

    def status(identifier):
        with Session() as db:
            return db.get(Job, identifier).status

    def complete(identifier):
        def tick():
            with ThreadPoolExecutor(max_workers=2) as schedulers:
                list(schedulers.map(lambda _: recover_once(), range(2)))
            dispatch()
            return status(identifier) == "SUCCESS"

        wait(tick)
        with Session() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Result)
                    .where(Result.job_id == identifier)
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Event)
                    .where(Event.job_id == identifier, Event.event_type == "SUCCESS")
                )
                == 1
            )
            attempts = db.scalars(
                select(Attempt)
                .where(Attempt.job_id == identifier)
                .order_by(Attempt.attempt_number)
            ).all()
            assert [a.status for a in attempts] == ["FAILED", "SUCCESS"]
            assert attempts[0].error_code == "WORKER_LEASE_EXPIRED"
        result = client.get(f"/api/v1/jobs/{identifier}/download")
        assert result.status_code == 200 and result.content.startswith(b"%PDF")

    try:
        with Session() as db:
            assert not db.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.status.in_(
                        ["PROCESSING", "CANCEL_REQUESTED", "QUEUED", "RETRY_WAIT"]
                    )
                )
            ), "finish active jobs before isolated test"
        # Entire Celery process SIGKILL, including its heartbeat thread.
        for mode in ["encode", "publish"]:
            process, root = spawn(mode)
            identifier = upload()
            dispatch()
            wait(lambda: (root / "reached").exists())
            assert client.get(f"/api/v1/jobs/{identifier}/download").status_code == 409
            if mode == "encode":
                # Long native work must keep ownership without page callbacks.
                time.sleep(8)
                recover_once()
                assert status(identifier) == "PROCESSING"
            process.kill()
            process.wait(timeout=10)
            replacement, _ = spawn()
            complete(identifier)
            replacement.terminate()
            replacement.wait(timeout=15)
            report[mode + "KillRecovered"] = identifier
        # Stopped process returns after replacement: fencing must reject it.
        old, root = spawn("encode")
        identifier = upload()
        dispatch()
        wait(lambda: (root / "reached").exists())
        os.kill(old.pid, signal.SIGSTOP)
        replacement, _ = spawn()
        complete(identifier)
        (root / "release").touch()
        os.kill(old.pid, signal.SIGCONT)
        time.sleep(2)
        assert status(identifier) == "SUCCESS"
        with Session() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Event)
                    .where(Event.job_id == identifier, Event.event_type == "SUCCESS")
                )
                == 1
            )
        old.terminate()
        old.wait(timeout=15)
        report["staleOwnerFenced"] = identifier
        # Duplicate real messages delivered to two independently running workers.
        second, _ = spawn()
        identifier = upload()
        for _ in range(12):
            send("convertflow.convert", args=[identifier, 1], queue=queue)
        wait(lambda: status(identifier) == "SUCCESS")
        time.sleep(2)
        with Session() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Attempt)
                    .where(Attempt.job_id == identifier)
                )
                == 1
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Result)
                    .where(Result.job_id == identifier)
                )
                == 1
            )
        report["twoWorkersDuplicateMessages"] = identifier
        # Cancellation of a dead owner must finish without running a new attempt.
        for child in [replacement, second]:
            child.terminate()
            child.wait(timeout=15)
        victim, root = spawn("encode")
        identifier = upload()
        dispatch()
        wait(lambda: (root / "reached").exists())
        response = client.post(
            f"/api/v1/jobs/{identifier}/cancel", json={"expectedGeneration": 1}
        )
        assert response.status_code == 202, response.text
        victim.kill()
        victim.wait(timeout=10)
        wait(lambda: (recover_once() or status(identifier) == "CANCELLED"))
        with Session() as db:
            assert db.get(Job, identifier).attempt_count == 1
            assert not db.scalar(select(Result).where(Result.job_id == identifier))
        report["lostOwnerCancellation"] = identifier
        print(json.dumps(report, indent=2), flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                os.kill(child.pid, signal.SIGCONT)
                child.kill()
                child.wait(timeout=10)
        for log in logs:
            log.close()
        client.close()


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker()
    else:
        main()
