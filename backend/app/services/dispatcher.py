import logging
import time
from sqlalchemy import select
from app.core.db import Session
from app.models.job import Outbox, now
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def dispatch_once():
    with Session.begin() as db:
        events = db.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        ).all()
        for event in events:
            event.retry_count += 1
            try:
                celery_app.send_task(
                    "convertflow.convert", args=[event.job_id], retry=False
                )
                event.published_at = now()
            except Exception:
                logger.exception("job=%s dispatch_failed", event.job_id)


if __name__ == "__main__":
    while True:
        try:
            dispatch_once()
        except Exception:
            logger.exception("dispatcher_failed")
        time.sleep(3)
