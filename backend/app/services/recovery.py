"""Recover expired execution ownership, never infer that a process is dead."""

from datetime import timedelta
from sqlalchemy import select, or_
from app.core.db import Session
from app.core.config import settings
from app.models.job import Job, Outbox
from app.services.leases import clock
from app.services.lifecycle import finish_failure
from app.services.errors import Failure
from app.services.events import record_event


def recover_once():
    with Session.begin() as db:
        instant = clock(db)
        jobs = db.scalars(
            select(Job)
            .where(
                Job.status.in_(["PROCESSING", "CANCEL_REQUESTED"]),
                or_(Job.lease_expires_at <= instant, Job.lease_expires_at.is_(None)),
            )
            .order_by(Job.job_id)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            record_event(
                db,
                job.job_id,
                "RECOVERY_REQUIRED",
                "실행 Lease가 만료되어 소유권을 회수합니다.",
                attempt_id=job.active_attempt_id,
                generation=job.run_generation,
            )
            finish_failure(
                db,
                job,
                Failure(
                    "WORKER_LEASE_EXPIRED", "Worker 실행 Lease가 만료되었습니다.", True
                ),
                "LeaseExpired",
            )
    # A broker restart may lose a previously accepted message. Republish only
    # still-QUEUED generations; atomic Claim tolerates duplicates.
    with Session.begin() as db:
        instant = clock(db)
        jobs = db.scalars(
            select(Job)
            .join(
                Outbox,
                (Outbox.job_id == Job.job_id)
                & (Outbox.generation == Job.run_generation),
            )
            .where(
                Job.status == "QUEUED",
                Outbox.published_at
                < instant - timedelta(seconds=settings.redispatch_seconds),
            )
            .order_by(Outbox.published_at)
            .limit(20)
            .with_for_update(of=Job, skip_locked=True)
        ).all()
        for job in jobs:
            outbox = db.scalar(
                select(Outbox).where(
                    Outbox.job_id == job.job_id, Outbox.generation == job.run_generation
                )
            )
            if outbox:
                outbox.published_at = None
                record_event(
                    db,
                    job.job_id,
                    "DISPATCH_RECOVERY",
                    "미획득 메시지를 다시 발행합니다.",
                    generation=job.run_generation,
                )
