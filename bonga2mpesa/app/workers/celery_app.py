import asyncio
from celery import Celery
from celery.utils.log import get_task_logger

from app.core.config import settings

logger = get_task_logger(__name__)

celery_app = Celery(
    "bonga2mpesa",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Nairobi",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.process_transaction_task": {"queue": "payouts"},
        "app.workers.tasks.retry_failed_transactions": {"queue": "maintenance"},
    },
    task_default_queue="default",
    # Dead-letter via rejected tasks
    task_reject_on_worker_lost=True,
    task_max_retries=settings.MAX_RETRIES,
    beat_schedule={
        "retry-stale-validated-transactions": {
            "task": "app.workers.tasks.retry_failed_transactions",
            "schedule": 300.0,  # every 5 minutes
        },
    },
)


def get_celery() -> Celery:
    return celery_app
