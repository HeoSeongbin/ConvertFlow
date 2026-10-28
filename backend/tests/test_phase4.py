from datetime import timedelta
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.core.db import Session
from app.main import app
from app.models.job import Job, Attempt, Event, Result, Outbox, now
from app.services.leases import renew
from app.services.lifecycle import guard, StaleExecution, fail_attempt
from app.services.errors import Failure
from app.services.recovery import recover_once
from app.tasks.convert import convert_job
from test_phase3 import upload, dispatch


def running(identifier, *, expired=True, status="PROCESSING", retries=0):
    with Session.begin() as db:
        job = db.get(Job, identifier)
        job.status = status
        job.attempt_count = 1
        job.active_attempt_id = "old-attempt"
        job.auto_retry_count = retries
        job.lease_expires_at = now() + timedelta(seconds=-60 if expired else 60)
        db.add(
            Attempt(
                attempt_id="old-attempt",
                job_id=identifier,
                attempt_number=1,
                generation=1,
                origin="INITIAL",
                worker_name="lost",
                status="PROCESSING",
            )
        )


def test_expiry_fences_renew_progress_and_failure_before_recovery():
    identifier = upload(TestClient(app))
    running(identifier)
    assert not renew(identifier, 1, "old-attempt")
    with Session.begin() as db, pytest.raises(StaleExecution):
        guard(db, identifier, 1, "old-attempt")
    fail_attempt(
        identifier, 1, "old-attempt", Failure("STORAGE_ERROR", "late", True), "late"
    )
    with Session() as db:
        assert db.get(Job, identifier).status == "PROCESSING"


def test_heartbeat_extends_only_current_unexpired_owner():
    identifier = upload(TestClient(app))
    running(identifier, expired=False)
    assert renew(identifier, 1, "old-attempt")
    assert not renew(identifier, 2, "old-attempt")
    assert not renew(identifier, 1, "other")
    recover_once()
    with Session() as db:
        assert db.get(Job, identifier).status == "PROCESSING"


def test_recovery_preserves_attempt_and_publishes_one_result():
    identifier = upload(TestClient(app))
    running(identifier)
    with patch("app.services.lifecycle.retry_delay", return_value=0):
        recover_once()
        recover_once()
    with Session() as db:
        job = db.get(Job, identifier)
        assert job.run_generation == 2 and job.status == "RETRY_WAIT"
        assert db.get(Attempt, "old-attempt").error_code == "WORKER_LEASE_EXPIRED"
    dispatch()
    convert_job.run(identifier, 1)
    convert_job.run(identifier, 2)
    convert_job.run(identifier, 2)
    with Session() as db:
        assert db.get(Job, identifier).status == "SUCCESS"
        assert db.scalar(select(func.count()).select_from(Result)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.event_type == "SUCCESS")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(Attempt)) == 2


@pytest.mark.parametrize(
    "status,retries,expected",
    [("CANCEL_REQUESTED", 0, "CANCELLED"), ("PROCESSING", 3, "FAILED")],
)
def test_expired_cancel_and_bounded_recovery(status, retries, expected):
    identifier = upload(TestClient(app))
    running(identifier, status=status, retries=retries)
    recover_once()
    with Session() as db:
        assert db.get(Job, identifier).status == expected
        assert db.get(Job, identifier).active_attempt_id is None
        assert db.get(Job, identifier).lease_expires_at is None


def test_accepted_but_unclaimed_message_is_republished():
    identifier = upload(TestClient(app))
    with Session.begin() as db:
        event = db.scalar(select(Outbox).where(Outbox.job_id == identifier))
        event.published_at = now() - timedelta(seconds=90)
    recover_once()
    assert len(dispatch()) == 1
    recover_once()
    assert len(dispatch()) == 0
