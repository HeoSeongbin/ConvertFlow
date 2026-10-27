from celery import Celery
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()
celery_app = Celery(
    "convertflow", broker=settings.redis_url, include=["app.tasks.convert"]
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    task_soft_time_limit=120,
    task_time_limit=150,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={
        "visibility_timeout": 300,
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
    },
    task_serializer="json",
    accept_content=["json"],
)
