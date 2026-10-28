"""DB-clock leases. Expired owners cannot renew or publish, even before recovery."""

import logging
from datetime import datetime, timedelta
from threading import Event, Thread
from sqlalchemy import select, func, update
from app.core.config import settings
from app.core.db import Session
from app.models.job import Job

logger = logging.getLogger(__name__)


def clock(db):
    # clock_timestamp advances within PostgreSQL transactions unlike now().
    value = db.scalar(
        select(
            func.clock_timestamp()
            if db.bind.dialect.name == "postgresql"
            else func.strftime("%Y-%m-%d %H:%M:%f", "now")
        )
    )
    from app.services.jobs import utc

    return utc(datetime.fromisoformat(value) if isinstance(value, str) else value)


def alive(job, instant):
    from app.services.jobs import utc

    return job.lease_expires_at is not None and utc(job.lease_expires_at) > instant


def renew(job_id, generation, attempt_id):
    with Session.begin() as db:
        # Read DB time after obtaining the row lock, not before a lock wait.
        db.scalar(select(Job).where(Job.job_id == job_id).with_for_update())
        instant = clock(db)
        return bool(
            db.execute(
                update(Job)
                .where(
                    Job.job_id == job_id,
                    Job.run_generation == generation,
                    Job.active_attempt_id == attempt_id,
                    Job.status.in_(["PROCESSING", "CANCEL_REQUESTED"]),
                    Job.lease_expires_at > instant,
                )
                .values(
                    heartbeat_at=instant,
                    lease_expires_at=instant
                    + timedelta(seconds=settings.lease_seconds),
                )
            ).rowcount
        )


class Heartbeat:
    def __init__(self, job_id, generation, attempt_id):
        self.args = job_id, generation, attempt_id
        self.stop_event = Event()
        self.thread = Thread(target=self.run, daemon=True, name="lease-heartbeat")

    def start(self):
        self.thread.start()

    def run(self):
        while not self.stop_event.wait(settings.heartbeat_seconds):
            try:
                if not renew(*self.args):
                    return
            except Exception:
                # DB outage cannot authorize further progress. Guards fail closed.
                logger.exception("job=%s heartbeat_failed", self.args[0])

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=1)
