import hashlib
from datetime import timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.db import Session
from app.models.job import Job, Attempt, MonitorSnapshot, WorkerObservation, now
from sqlalchemy import select
from app.services.observer import collect_once, job_ids
from app.tasks.convert import convert_job
from app.storage.checksums import checksum
from test_phase3 import upload
from test_phase4 import running


def observe(tasks=None, ready=7, stats=None):
    inspect = MagicMock()
    inspect.stats.return_value = (
        stats
        if stats is not None
        else {"worker@test": {"pool": {"max-concurrency": 2}}}
    )
    inspect.active.return_value = {"worker@test": tasks or []}
    connection = MagicMock()
    channel = (
        connection.__enter__.return_value.channel.return_value.__enter__.return_value
    )
    channel.queue_declare.return_value.message_count = ready
    with (
        patch("app.services.observer.celery_app.control.inspect", return_value=inspect),
        patch(
            "app.services.observer.celery_app.connection_for_read",
            return_value=connection,
        ),
        patch("app.services.observer.now", return_value=now() - timedelta(seconds=2)),
    ):
        collect_once()
    channel.queue_declare.assert_called_once_with(queue="celery", passive=False)


def test_dashboard_preserves_failed_attempt_after_manual_success_and_scope():
    client = TestClient(app)
    identifier = upload(client)
    with patch(
        "app.tasks.convert.ImagePDFConverter.convert",
        side_effect=RuntimeError("failed encoder"),
    ):
        convert_job.run(identifier)
    response = client.post(
        f"/api/v1/jobs/{identifier}/retry", json={"expectedGeneration": 1}
    )
    assert response.status_code == 202
    convert_job.run(identifier, 2)
    other = TestClient(app)
    convert_job.run(upload(other))
    with Session.begin() as db:
        job = db.get(Job, identifier)
        job.completed_at = now() - timedelta(seconds=10)
        job.started_at = job.completed_at - timedelta(seconds=4)
        job.created_at = job.completed_at - timedelta(seconds=9)
        for attempt in db.scalars(select(Attempt).where(Attempt.job_id == identifier)):
            attempt.finished_at = job.completed_at
    data = client.get("/api/v1/monitoring/dashboard").json()
    assert data["total"] == data["recentSuccess"] == data["processingSamples"] == 1
    assert data["counts"]["SUCCESS"] == 1
    assert abs(data["meanProcessingSeconds"] - 4) < 0.001
    assert abs(data["meanEndToEndSeconds"] - 9) < 0.001
    assert data["recentFailedAttempts"] == data["recentSuccessfulAttempts"] == 1
    assert data["errors"] == [{"code": "CONVERSION_FAILED", "count": 1}]


def test_empty_workspace_and_missing_times_are_not_fake_zero():
    client = TestClient(app)
    data = client.get("/api/v1/monitoring/dashboard").json()
    assert data["total"] == 0 and data["meanProcessingSeconds"] is None
    assert data["meanEndToEndSeconds"] is None and data["errors"] == []
    identifier = upload(client)
    with Session.begin() as db:
        job = db.get(Job, identifier)
        job.status = "SUCCESS"
        job.completed_at = now() - timedelta(seconds=2)
    data = client.get("/api/v1/monitoring/dashboard").json()
    assert data["recentSuccess"] == 1 and data["processingSamples"] == 0
    assert data["meanProcessingSeconds"] is None


def test_observer_redacts_other_workspaces_and_never_inspects_in_api():
    client = TestClient(app)
    own = upload(client)
    running(own, expired=False)
    with Session.begin() as db:
        db.get(Attempt, "old-attempt").worker_name = "worker@test"
    other = upload(TestClient(app))
    tasks = [
        {"name": "convertflow.convert", "args": [own, 1]},
        {"name": "convertflow.convert", "args": str((other, 1))},
    ]
    observe(tasks)
    with patch(
        "app.services.observer.celery_app.control.inspect",
        side_effect=AssertionError("API cannot inspect"),
    ):
        response = client.get("/api/v1/monitoring/workers")
    data = response.json()
    assert other not in response.text
    worker = data["items"][0]
    assert worker["status"] == "ONLINE" and worker["activeCount"] == 2
    assert worker["concurrency"] == 2
    assert [job["jobId"] for job in worker["jobs"]] == [own]
    assert (
        data["queue"]["readyMessages"] == 7
        and data["queue"]["scope"] == "infrastructure"
    )
    assert (
        TestClient(app).get("/api/v1/monitoring/workers").json()["items"][0]["jobs"]
        == []
    )


def test_stale_and_no_reply_workers_are_unknown_not_offline():
    client = TestClient(app)
    observe(ready=0)
    assert (
        client.get("/api/v1/monitoring/workers").json()["queue"]["readyMessages"] == 0
    )
    observe(stats={})
    data = client.get("/api/v1/monitoring/workers").json()
    assert data["items"][0]["status"] == "UNKNOWN"
    assert data["items"][0]["activeCount"] is None
    with Session.begin() as db:
        snapshot = db.get(MonitorSnapshot, "celery")
        old = (now() - timedelta(minutes=2)).isoformat()
        snapshot.data = {**snapshot.data, "queueAt": old, "workersAt": old}
    data = client.get("/api/v1/monitoring/workers").json()
    assert data["queue"]["readyMessages"] is None
    assert data["queue"]["status"] == "UNKNOWN"


def test_broker_failure_keeps_last_seen_but_hides_unconfirmed_values():
    observe()
    with Session() as db:
        previous = db.get(WorkerObservation, "worker@test").last_seen_at
    with (
        patch(
            "app.services.observer.celery_app.control.inspect",
            side_effect=OSError("offline"),
        ),
        patch(
            "app.services.observer.celery_app.connection_for_read",
            side_effect=OSError("offline"),
        ),
    ):
        collect_once()
    data = TestClient(app).get("/api/v1/monitoring/workers").json()
    assert data["workersError"] == "INSPECT_UNAVAILABLE"
    assert data["queue"]["error"] == "BROKER_UNAVAILABLE"
    assert data["queue"]["readyMessages"] is None
    assert data["items"][0]["status"] == "UNKNOWN"
    with Session() as db:
        assert db.get(WorkerObservation, "worker@test").last_seen_at == previous


def test_active_list_failure_does_not_fabricate_zero():
    inspect = MagicMock()
    inspect.stats.return_value = {"worker@test": {"pool": {"max-concurrency": 1}}}
    inspect.active.side_effect = OSError("active unavailable")
    with (
        patch("app.services.observer.celery_app.control.inspect", return_value=inspect),
        patch(
            "app.services.observer.celery_app.connection_for_read",
            side_effect=OSError("offline"),
        ),
        patch("app.services.observer.now", return_value=now() - timedelta(seconds=2)),
    ):
        collect_once()
    worker = TestClient(app).get("/api/v1/monitoring/workers").json()["items"][0]
    assert worker["status"] == "ONLINE" and worker["activeCount"] is None


def test_job_args_are_validated_and_not_executed():
    assert (
        job_ids(
            [
                {
                    "name": "convertflow.convert",
                    "args": "__import__('os').system('false')",
                },
                {"name": "convertflow.convert", "args": ["not-uuid"]},
            ]
        )
        == []
    )


def test_hash_uses_streaming_buffer(tmp_path):
    data = b"large fixture" * 100_000
    path = tmp_path / "large.bin"
    path.write_bytes(data)
    with patch(
        "pathlib.Path.read_bytes", side_effect=AssertionError("no whole-file reads")
    ):
        assert checksum(path) == hashlib.sha256(data).hexdigest()


def test_history_outside_window_is_not_recent():
    client = TestClient(app)
    identifier = upload(client)
    with Session.begin() as db:
        job = db.get(Job, identifier)
        job.status = "SUCCESS"
        job.started_at = now() - timedelta(hours=3)
        job.completed_at = now() - timedelta(hours=2)
    data = client.get("/api/v1/monitoring/dashboard").json()
    assert data["total"] == 1 and data["recentSuccess"] == 0
    assert data["meanProcessingSeconds"] is None


def test_old_generation_and_wrong_worker_do_not_claim_current_job():
    client = TestClient(app)
    identifier = upload(client)
    running(identifier, expired=False)
    with Session.begin() as db:
        db.get(Attempt, "old-attempt").worker_name = "worker@test"
        db.get(Job, identifier).run_generation = 2
        db.get(Attempt, "old-attempt").generation = 2
    observe([{"name": "convertflow.convert", "args": [identifier, 1]}])
    worker = client.get("/api/v1/monitoring/workers").json()["items"][0]
    assert worker["activeCount"] == 1 and worker["jobs"] == []
    observe([{"name": "convertflow.convert", "args": [identifier, 2]}])
    assert len(client.get("/api/v1/monitoring/workers").json()["items"][0]["jobs"]) == 1
    with Session.begin() as db:
        db.get(Attempt, "old-attempt").worker_name = "worker@replacement"
    assert client.get("/api/v1/monitoring/workers").json()["items"][0]["jobs"] == []
