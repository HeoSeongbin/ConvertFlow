import errno
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, func
from billiard.exceptions import SoftTimeLimitExceeded
from app.main import app
from app.core.db import Session
from app.models.job import Result, Event, Outbox, JobFile, now
from app.tasks.convert import convert_job
from app.converters.image_pdf import ImagePDFConverter
from app.services.dispatcher import dispatch_once
from app.services.errors import classify_error, retry_delay, Failure
from app.services.lifecycle import fail_attempt
from app.services.validation import InvalidInput
from app.storage.local import storage


def upload(client):
    stream = io.BytesIO()
    Image.new("RGB", (60, 40), "red").save(stream, "PNG")
    response = client.post(
        "/api/v1/jobs", files={"file": ("retry.png", stream.getvalue(), "image/png")}
    )
    assert response.status_code == 202, response.text
    return response.json()["jobId"]


def detail(client, identifier):
    return client.get(f"/api/v1/jobs/{identifier}").json()


def attempts(client, identifier):
    response = client.get(f"/api/v1/jobs/{identifier}/attempts")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def fail(identifier, generation=1, exc=None):
    with patch(
        "app.tasks.convert.ImagePDFConverter.convert",
        side_effect=exc or RuntimeError("encoder unavailable"),
    ):
        convert_job.run(identifier, generation)


def dispatch():
    with patch("app.services.dispatcher.celery_app.send_task") as send:
        dispatch_once()
        return send.call_args_list


def test_manual_retry_preserves_failure_and_ignores_old_messages():
    client = TestClient(app)
    identifier = upload(client)
    fail(identifier)
    first = attempts(client, identifier)[0]
    assert first["status"] == "FAILED" and first["origin"] == "INITIAL"
    assert detail(client, identifier)["canRetry"]
    response = client.post(
        f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 1}
    )
    assert response.status_code == 202
    assert response.json()["runGeneration"] == 2
    assert (
        client.post(
            f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 1}
        ).status_code
        == 409
    )
    convert_job.run(identifier, 1)
    assert detail(client, identifier)["status"] == "QUEUED"
    convert_job.run(identifier, 2)
    assert detail(client, identifier)["status"] == "SUCCESS"
    assert detail(client, identifier)["errorCode"] is None
    rows = attempts(client, identifier)
    assert rows[0]["origin"] == "MANUAL" and rows[0]["status"] == "SUCCESS"
    assert rows[1] == first
    fail_attempt(
        identifier,
        1,
        first["attemptId"],
        Failure("STORAGE_ERROR", "stale", True),
        "OSError",
    )
    assert detail(client, identifier)["status"] == "SUCCESS"
    with Session() as db:
        result = db.scalar(select(Result).where(Result.job_id == identifier))
        assert result.attempt_id == rows[0]["attemptId"]
        assert rows[0]["attemptId"] in result.output_path
        assert (
            db.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.job_id == identifier, Event.event_type == "SUCCESS")
            )
            == 1
        )


def test_automatic_retry_due_time_and_dispatch_generation():
    client = TestClient(app)
    identifier = upload(client)
    with patch("app.services.lifecycle.retry_delay", return_value=60):
        fail(identifier, exc=OSError(errno.ENOSPC, "full"))
    job = detail(client, identifier)
    assert job["status"] == "RETRY_WAIT" and job["runGeneration"] == 2
    assert job["autoRetryCount"] == 1 and job["nextRetryAt"]
    assert not dispatch()  # old generation suppressed; retry is not due
    with Session.begin() as db:
        event = db.scalar(
            select(Outbox).where(Outbox.job_id == identifier, Outbox.generation == 2)
        )
        event.available_at = now() - timedelta(seconds=1)
    calls = dispatch()
    assert len(calls) == 1 and calls[0].kwargs["args"] == [identifier, 2]
    assert detail(client, identifier)["status"] == "QUEUED"
    convert_job.run(
        identifier
    )  # legacy one-argument message must never claim generation 2
    assert len(attempts(client, identifier)) == 1
    convert_job.run(identifier, 2)
    assert detail(client, identifier)["status"] == "SUCCESS"
    rows = attempts(client, identifier)
    assert rows[0]["origin"] == "AUTO"
    assert rows[1]["errorCode"] == "STORAGE_ERROR" and rows[1]["retryable"]


def test_auto_retry_limit_and_manual_cycle_reset():
    client = TestClient(app)
    identifier = upload(client)
    with patch("app.services.lifecycle.retry_delay", return_value=0):
        for generation in range(1, 5):
            fail(identifier, generation, OSError(errno.EIO, "temporary"))
            job = detail(client, identifier)
            if generation < 4:
                assert job["status"] == "RETRY_WAIT"
                dispatch()
            else:
                assert job["status"] == "FAILED"
    assert len(attempts(client, identifier)) == 4
    assert job["autoRetryCount"] == 3 and job["runGeneration"] == 4
    assert (
        client.post(
            f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 4}
        ).status_code
        == 202
    )
    assert detail(client, identifier)["autoRetryCount"] == 0
    assert (
        client.post(
            f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 1}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "exception,code,auto",
    [
        (InvalidInput("DECODE_FAILED", "bad image"), "DECODE_FAILED", False),
        (InvalidInput("INVALID_OPTIONS", "bad option"), "INVALID_OPTIONS", False),
        (FileNotFoundError(), "SOURCE_MISSING", False),
        (PermissionError(errno.EACCES, "denied"), "STORAGE_ERROR", False),
        (OSError(errno.ENOSPC, "full"), "STORAGE_ERROR", True),
        (SoftTimeLimitExceeded(), "TIME_LIMIT_EXCEEDED", True),
        (MemoryError(), "RESOURCE_EXHAUSTED", True),
        (RuntimeError(), "CONVERSION_FAILED", False),
    ],
)
def test_failure_classification(exception, code, auto):
    failure = classify_error(exception)
    assert failure.code == code and failure.retryable == auto


def test_backoff_jitter_and_cap():
    for number, ceiling in [(1, 5), (2, 10), (3, 20), (20, 300)]:
        for _ in range(5):
            assert ceiling / 2 <= retry_delay(number) <= ceiling


def test_non_retryable_input_and_missing_source():
    client = TestClient(app)
    identifier = upload(client)
    fail(identifier, exc=InvalidInput("INVALID_OPTIONS", "bad margins"))
    assert not detail(client, identifier)["canRetry"]
    assert (
        client.post(
            f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 1}
        ).status_code
        == 409
    )
    identifier = upload(client)
    fail(identifier)
    with Session() as db:
        source = db.scalar(select(JobFile).where(JobFile.job_id == identifier))
        storage.path(source.storage_path).unlink()
    assert not detail(client, identifier)["sourceAvailable"]
    listing = client.get(
        "/api/v1/jobs", params={"search": identifier, "retryCenter": True}
    ).json()
    assert not listing["items"][0]["canRetry"]
    response = client.post(
        f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 1}
    )
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "SOURCE_UNAVAILABLE"
    )
    assert detail(client, identifier)["runGeneration"] == 1


def test_queued_cancel_and_repeat_are_idempotent():
    client = TestClient(app)
    identifier = upload(client)
    for _ in range(2):
        response = client.post(
            f"/api/v1/jobs/{identifier}/cancel", json={"expectedGeneration": 1}
        )
        assert response.status_code == 202 and response.json()["status"] == "CANCELLED"
    convert_job.run(identifier)
    assert detail(client, identifier)["attemptCount"] == 0
    assert not attempts(client, identifier)
    assert not dispatch()
    with Session() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.job_id == identifier, Event.event_type == "CANCELLED")
            )
            == 1
        )


@pytest.mark.parametrize("boundary", ["page", "publish", "error"])
def test_processing_cancellation_wins_before_publish(boundary):
    client = TestClient(app)
    identifier = upload(client)
    original = ImagePDFConverter.convert

    def conversion(sources, destination, options, on_page):
        if boundary == "publish":
            result = original(
                ImagePDFConverter(), sources, destination, options, on_page
            )
        response = client.post(
            f"/api/v1/jobs/{identifier}/cancel", json={"expectedGeneration": 1}
        )
        assert (
            response.status_code == 202
            and response.json()["status"] == "CANCEL_REQUESTED"
        )
        if boundary == "error":
            raise OSError("disk failed after cancel")
        if boundary == "page":
            destination.write_bytes(b"partial")
            on_page(0, 1, 1)
            raise AssertionError("must stop before this point")
        return result

    with patch("app.tasks.convert.ImagePDFConverter.convert", side_effect=conversion):
        convert_job.run(identifier)
    job = detail(client, identifier)
    assert job["status"] == "CANCELLED" and job["progress"] < 100
    assert not job["downloadAvailable"] and job["result"] is None
    assert attempts(client, identifier)[0]["status"] == "CANCELLED"
    assert client.get(f"/api/v1/jobs/{identifier}/download").status_code == 409
    with Session() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Outbox)
                .where(Outbox.job_id == identifier)
            )
            == 1
        )


def test_cancel_retry_wait_does_not_restart_failed_attempt():
    client = TestClient(app)
    identifier = upload(client)
    with patch("app.services.lifecycle.retry_delay", return_value=0):
        fail(identifier, exc=OSError("temporary"))
    assert (
        client.post(
            f"/api/v1/jobs/{identifier}/cancel", json={"expectedGeneration": 2}
        ).json()["status"]
        == "CANCELLED"
    )
    assert not dispatch()
    convert_job.run(identifier, 2)
    assert len(attempts(client, identifier)) == 1
    assert attempts(client, identifier)[0]["status"] == "FAILED"


def test_mutation_access_control_and_terminal_cancel_conflict():
    owner, outsider = TestClient(app), TestClient(app)
    identifier = upload(owner)
    for endpoint in ("retry", "cancel"):
        assert (
            outsider.post(
                f"/api/v1/jobs/{identifier}/{endpoint}", json={"expectedGeneration": 1}
            ).status_code
            == 404
        )
        assert (
            owner.post(f"/api/v1/jobs/{identifier}/{endpoint}", json={}).status_code
            == 422
        )
    assert (
        owner.post(
            f"/api/v1/jobs/{identifier}/retry",
            json={"expectedGeneration": 1, "options": {}},
        ).status_code
        == 422
    )
    assert outsider.get(f"/api/v1/jobs/{identifier}/attempts").status_code == 404
    convert_job.run(identifier)
    assert (
        owner.post(
            f"/api/v1/jobs/{identifier}/cancel", json={"expectedGeneration": 1}
        ).status_code
        == 409
    )
    assert (
        owner.post(
            f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 1}
        ).status_code
        == 409
    )


def test_retry_center_and_attempt_pagination():
    client = TestClient(app)
    identifier = upload(client)
    for generation in (1, 2, 3):
        fail(identifier, generation)
        if generation < 3:
            assert (
                client.post(
                    f"/api/v1/jobs/{identifier}/retry",
                    json={"expectedGeneration": generation},
                ).status_code
                == 202
            )
    listing = client.get("/api/v1/jobs?retryCenter=true").json()
    assert listing["total"] == 1 and listing["items"][0]["canRetry"]
    rows = client.get(f"/api/v1/jobs/{identifier}/attempts?page=2&pageSize=1").json()
    assert rows["total"] == 3 and rows["items"][0]["attemptNumber"] == 2
    assert client.get(f"/api/v1/jobs/{identifier}/attempts?page=0").status_code == 422
    assert (
        client.get(f"/api/v1/jobs/{identifier}/attempts?pageSize=101").status_code
        == 422
    )


def test_duplicate_manual_retry_only_advances_once():
    owner = TestClient(app)
    identifier = upload(owner)
    fail(identifier)
    cookies = dict(owner.cookies)

    def retry():
        with TestClient(app, cookies=cookies) as client:
            return client.post(
                f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 1}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: retry(), range(2)))
    assert sorted(codes) == [202, 409]
    assert detail(owner, identifier)["runGeneration"] == 2
    with Session() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Outbox)
                .where(Outbox.job_id == identifier, Outbox.generation == 2)
            )
            == 1
        )


def test_retry_queued_state_is_committed_before_broker_publication():
    client = TestClient(app)
    identifier = upload(client)
    with patch("app.services.lifecycle.retry_delay", return_value=0):
        fail(identifier, exc=OSError("temporary"))
    observed = []

    def publish(*args, **kwargs):
        # A different connection models what an immediately consuming Worker sees.
        with Session() as db:
            from app.models.job import Job

            row = db.get(Job, identifier)
            observed.append((row.status, row.run_generation))

    with patch("app.services.dispatcher.celery_app.send_task", side_effect=publish):
        dispatch_once()
    assert observed == [("QUEUED", 2)]
