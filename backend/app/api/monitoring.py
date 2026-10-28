from datetime import datetime, timedelta
from fastapi import APIRouter, Request
from sqlalchemy import select, func, false
from app.core.db import Session
from app.core.config import settings
from app.models.job import Job, Attempt, Outbox, MonitorSnapshot, WorkerObservation
from app.services.jobs import WORKSPACE_COOKIE, token_hash, iso, utc
from app.services.leases import clock, alive

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])
STATUSES = [
    "QUEUED",
    "PROCESSING",
    "RETRY_WAIT",
    "CANCEL_REQUESTED",
    "SUCCESS",
    "FAILED",
    "CANCELLED",
]


def scope(request):
    workspace = request.cookies.get(WORKSPACE_COOKIE)
    return Job.workspace_hash == token_hash(workspace) if workspace else false()


def seconds(db, end, start):
    if db.bind.dialect.name == "postgresql":
        return func.extract("epoch", end - start)
    return (func.julianday(end) - func.julianday(start)) * 86400


@router.get("/dashboard")
def dashboard(request: Request):
    with Session() as db:
        instant = clock(db)
        since = instant - timedelta(hours=1)
        owned = scope(request)
        counts = dict(
            db.execute(
                select(Job.status, func.count()).where(owned).group_by(Job.status)
            ).all()
        )
        recent = [
            owned,
            Job.status == "SUCCESS",
            Job.completed_at >= since,
            Job.completed_at <= instant,
        ]
        duration = seconds(db, Job.completed_at, Job.started_at)
        latency = seconds(db, Job.completed_at, Job.created_at)
        completed, mean, maximum, latency_mean, duration_samples = db.execute(
            select(
                func.count(),
                func.avg(duration),
                func.max(duration),
                func.avg(latency),
                func.count(duration),
            )
            .select_from(Job)
            .where(*recent)
        ).one()
        attempts = [owned, Attempt.finished_at >= since, Attempt.finished_at <= instant]
        errors = db.execute(
            select(Attempt.error_code, func.count())
            .join(Job, Job.job_id == Attempt.job_id)
            .where(*attempts, Attempt.status == "FAILED")
            .group_by(Attempt.error_code)
            .order_by(func.count().desc(), Attempt.error_code)
            .limit(10)
        ).all()
        attempt_counts = dict(
            db.execute(
                select(Attempt.status, func.count())
                .join(Job, Job.job_id == Attempt.job_id)
                .where(*attempts)
                .group_by(Attempt.status)
            ).all()
        )
        pending = db.scalar(
            select(func.count())
            .select_from(Outbox)
            .join(Job, Job.job_id == Outbox.job_id)
            .where(
                owned,
                Outbox.generation == Job.run_generation,
                Outbox.published_at.is_(None),
                Job.status.in_(["QUEUED", "RETRY_WAIT"]),
            )
        )
        return {
            "sampledAt": iso(instant),
            "scope": "workspace",
            "windowStart": iso(since),
            "windowMinutes": 60,
            "counts": {s: counts.get(s, 0) for s in STATUSES},
            "total": sum(counts.values()),
            "recentSuccess": completed,
            "processingSamples": duration_samples,
            "recentFailedAttempts": attempt_counts.get("FAILED", 0),
            "recentSuccessfulAttempts": attempt_counts.get("SUCCESS", 0),
            "throughputJobsPerMinute": completed / 60,
            "meanProcessingSeconds": mean,
            "maxProcessingSeconds": maximum,
            "meanEndToEndSeconds": latency_mean,
            "pendingDispatch": pending,
            "errors": [
                {"code": code or "UNKNOWN", "count": count} for code, count in errors
            ],
        }


@router.get("/workers")
def workers(request: Request):
    with Session() as db:
        instant = clock(db)
        snapshot = db.get(MonitorSnapshot, "celery")
        payload = snapshot.data if snapshot else {}

        def fresh(value):
            return bool(
                value
                and timedelta(0)
                <= instant - utc(value)
                <= timedelta(seconds=settings.monitor_stale_seconds)
            )

        workers_at = (
            datetime.fromisoformat(payload["workersAt"])
            if payload.get("workersAt")
            else None
        )
        queue_at = (
            datetime.fromisoformat(payload["queueAt"])
            if payload.get("queueAt")
            else None
        )
        worker_fresh = fresh(workers_at)
        observations = db.scalars(
            select(WorkerObservation)
            .order_by(
                WorkerObservation.last_seen_at.desc(), WorkerObservation.worker_name
            )
            .limit(100)
        ).all()
        all_ids = [
            identifier
            for worker in observations
            for identifier in (worker.active_job_ids or [])
        ]
        jobs = (
            {
                job.job_id: job
                for job in db.scalars(
                    select(Job).where(
                        scope(request),
                        Job.job_id.in_(all_ids),
                        Job.status.in_(["PROCESSING", "CANCEL_REQUESTED"]),
                    )
                )
            }
            if all_ids
            else {}
        )
        owners = (
            {
                attempt.attempt_id: attempt.worker_name
                for attempt in db.scalars(
                    select(Attempt).where(
                        Attempt.attempt_id.in_(
                            [job.active_attempt_id for job in jobs.values()]
                        )
                    )
                )
            }
            if jobs
            else {}
        )
        recent = db.execute(
            select(Attempt.worker_name, Attempt.status, func.count())
            .join(Job, Job.job_id == Attempt.job_id)
            .where(
                scope(request),
                Attempt.finished_at >= instant - timedelta(hours=1),
                Attempt.finished_at <= instant,
            )
            .group_by(Attempt.worker_name, Attempt.status)
        ).all()
        outcomes = {(name, status): count for name, status, count in recent}
        items = []
        for worker in observations:
            online = worker_fresh and worker.responding and fresh(worker.last_seen_at)
            items.append(
                {
                    "name": worker.worker_name,
                    "status": "ONLINE" if online else "UNKNOWN",
                    "lastSeenAt": iso(worker.last_seen_at),
                    "lastProbeAt": iso(worker.last_probe_at),
                    "concurrency": worker.concurrency if online else None,
                    "activeCount": worker.active_count if online else None,
                    "jobs": [
                        {
                            "jobId": identifier,
                            "status": jobs[identifier].status,
                            "heartbeatAt": iso(jobs[identifier].heartbeat_at),
                            "leaseExpiresAt": iso(jobs[identifier].lease_expires_at),
                        }
                        for identifier in (worker.active_job_ids or [])
                        if online
                        and identifier in jobs
                        and alive(jobs[identifier], instant)
                        and owners.get(jobs[identifier].active_attempt_id)
                        == worker.worker_name
                        and {
                            "jobId": identifier,
                            "generation": jobs[identifier].run_generation,
                        }
                        in payload.get("activeExecutions", {}).get(
                            worker.worker_name, []
                        )
                    ],
                    "recentSuccess": outcomes.get((worker.worker_name, "SUCCESS"), 0),
                    "recentFailedAttempts": outcomes.get(
                        (worker.worker_name, "FAILED"), 0
                    ),
                }
            )
        queue_known = (
            fresh(queue_at)
            and not payload.get("queueError")
            and payload.get("readyMessages") is not None
        )
        return {
            "sampledAt": iso(instant),
            "workersSampledAt": iso(workers_at),
            "workersError": payload.get("workersError")
            or ("STALE_OBSERVATION" if not worker_fresh else None),
            "staleAfterSeconds": settings.monitor_stale_seconds,
            "items": items,
            "totalKnown": db.scalar(
                select(func.count()).select_from(WorkerObservation)
            ),
            "queue": {
                "name": payload.get("queueName", "celery"),
                "scope": "infrastructure",
                "status": "KNOWN" if queue_known else "UNKNOWN",
                "sampledAt": iso(queue_at),
                "readyMessages": payload.get("readyMessages") if queue_known else None,
                "error": payload.get("queueError")
                or (None if queue_known else "STALE_OBSERVATION"),
            },
        }
