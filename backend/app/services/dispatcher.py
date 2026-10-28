import logging
import time
from sqlalchemy import select
from app.core.db import Session
from app.models.job import Outbox, Job, now
from app.services.lifecycle import lock_job
from app.services.events import record_event
from app.tasks.celery_app import celery_app
from app.services.recovery import recover_once

logger = logging.getLogger(__name__)


def dispatch_once():
    # PostgreSQL workers must see QUEUED before the broker message can arrive.
    # Publishing in the same transaction as RETRY_WAIT -> QUEUED loses messages.
    with Session.begin() as db:
        ready = db.scalars(
            select(Job)
            .join(
                Outbox,
                (Outbox.job_id == Job.job_id)
                & (Outbox.generation == Job.run_generation),
            )
            .where(
                Job.status == "RETRY_WAIT",
                Outbox.published_at.is_(None),
                Outbox.available_at <= now(),
            )
            .with_for_update(of=Job, skip_locked=True)
        ).all()
        for job in ready:
            job.status = job.stage = "QUEUED"
            job.progress = job.processed_files = job.processed_pages = 0
            job.started_at = job.completed_at = job.next_retry_at = None
            record_event(
                db,
                job.job_id,
                "QUEUED",
                "자동 재시도 실행 대기 중",
                generation=job.run_generation,
            )
    with Session.begin() as db:
        events = db.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None), Outbox.available_at <= now())
            .order_by(Outbox.available_at, Outbox.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for event in events:
            job = lock_job(db, event.job_id)
            if (
                not job
                or job.run_generation != event.generation
                or job.status not in {"QUEUED", "RETRY_WAIT"}
            ):
                event.published_at = now()
                continue
            if job.status == "RETRY_WAIT":
                # A retry may have become due after the preparation transaction.
                # Never publish a generation until QUEUED is durably visible.
                continue
            event.retry_count += 1
            try:
                celery_app.send_task(
                    "convertflow.convert",
                    args=[event.job_id, event.generation],
                    retry=False,
                )
                event.published_at = now()
            except Exception:
                logger.exception(
                    "job=%s generation=%s dispatch_failed",
                    event.job_id,
                    event.generation,
                )


if __name__ == "__main__":
    while True:
        try:
            recover_once()
            dispatch_once()
        except Exception:
            logger.exception("dispatcher_failed")
        time.sleep(3)
