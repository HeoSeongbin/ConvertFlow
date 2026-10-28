"""Independent, bounded Celery/Kombu observations cached in PostgreSQL."""

import ast
import logging
import time
from uuid import UUID
from sqlalchemy import update
from app.core.db import Session
from app.core.config import settings
from app.models.job import MonitorSnapshot, WorkerObservation, now
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def executions(tasks):
    identifiers = set()
    for task in tasks:
        if task.get("name") != "convertflow.convert":
            continue
        args = task.get("args")
        if isinstance(args, str) and len(args) < 1000:
            try:
                args = ast.literal_eval(args)
            except (ValueError, SyntaxError):
                continue
        if isinstance(args, (tuple, list)) and args:
            try:
                generation = args[1] if len(args) > 1 else 1
                if type(generation) is int and generation >= 1:
                    identifiers.add((str(UUID(str(args[0]))), generation))
            except ValueError:
                continue
    return [
        {"jobId": identifier, "generation": generation}
        for identifier, generation in sorted(identifiers)
    ]


def job_ids(tasks):
    return sorted({item["jobId"] for item in executions(tasks)})


def collect_once():
    stats = active = {}
    workers_error = queue_error = None
    ready = None
    try:
        inspect = celery_app.control.inspect(timeout=2)
        stats = inspect.stats() or {}
        active = inspect.active() or {}
        if not stats:
            workers_error = "NO_WORKER_REPLY"
    except Exception:
        workers_error = "INSPECT_UNAVAILABLE"
        logger.exception("worker_observation_failed")
    workers_at = now()
    try:
        # Redis removes empty list keys, so passive=True reports 404 for a
        # healthy empty queue. Declaration's Redis _new_queue is a no-op;
        # the transport supplies its supported priority-aware message count.
        with celery_app.connection_for_read() as connection:
            with connection.channel() as channel:
                declaration = channel.queue_declare(
                    queue=celery_app.conf.task_default_queue, passive=False
                )
                ready = int(declaration.message_count)
    except Exception:
        queue_error = "BROKER_UNAVAILABLE"
        logger.exception("queue_observation_failed")
    queue_at = now()
    with Session.begin() as db:
        db.execute(
            update(WorkerObservation).values(responding=False, last_probe_at=workers_at)
        )
        for name, data in stats.items():
            if not isinstance(name, str) or len(name) > 255:
                continue
            observation = db.get(WorkerObservation, name)
            if observation is None:
                observation = WorkerObservation(worker_name=name)
                db.add(observation)
            observation.last_seen_at = observation.last_probe_at = workers_at
            observation.responding = True
            concurrency = data.get("pool", {}).get("max-concurrency")
            observation.concurrency = (
                concurrency if isinstance(concurrency, int) else None
            )
            observation.active_job_ids = (
                job_ids(active[name]) if name in active else None
            )
            observation.active_count = len(active[name]) if name in active else None
        snapshot = db.get(MonitorSnapshot, "celery")
        if snapshot is None:
            snapshot = MonitorSnapshot(key="celery")
            db.add(snapshot)
        snapshot.sampled_at = queue_at
        snapshot.data = {
            "activeExecutions": {
                name: executions(tasks) for name, tasks in active.items()
            },
            "workersAt": workers_at.isoformat(),
            "workersError": workers_error,
            "queueAt": queue_at.isoformat(),
            "queueError": queue_error,
            "readyMessages": ready,
            "queueName": celery_app.conf.task_default_queue,
        }


if __name__ == "__main__":
    while True:
        try:
            collect_once()
        except Exception:
            logger.exception("observer_cycle_failed")
        time.sleep(settings.monitor_interval_seconds)
