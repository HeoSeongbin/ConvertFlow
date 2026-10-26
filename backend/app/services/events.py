from sqlalchemy import select, func
from app.models.job import Event


def record_event(db, job_id: str, event_type: str, message: str, **details):
    # Callers hold the job update/row lock; events are appended, never replaced.
    sequence = (
        db.scalar(select(func.max(Event.sequence)).where(Event.job_id == job_id)) or 0
    ) + 1
    db.add(
        Event(
            job_id=job_id,
            sequence=sequence,
            event_type=event_type,
            message=message,
            details=details,
        )
    )
