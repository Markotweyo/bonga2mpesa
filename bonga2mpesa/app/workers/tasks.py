import asyncio
from celery import Task
from celery.utils.log import get_task_logger

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.daraja_client import DarajaClient
from app.services.transaction_service import TransactionService

logger = get_task_logger(__name__)


def run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_transaction_task",
    max_retries=settings.MAX_RETRIES,
    default_retry_delay=settings.RETRY_BACKOFF_BASE,
    acks_late=True,
    queue="payouts",
)
def process_transaction_task(self, transaction_id: str):
    """
    Background task to process B2C payout for a validated transaction.
    Uses exponential backoff on retry.
    """
    logger.info(f"Processing transaction {transaction_id}, attempt {self.request.retries + 1}")

    async def _run():
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            async with AsyncSessionLocal() as db:
                daraja = DarajaClient(redis_client)
                service = TransactionService(db, redis_client, daraja)
                await service.process_payout(transaction_id)
                await db.commit()
        finally:
            await redis_client.aclose()

    try:
        run_async(_run())
    except Exception as exc:
        retry_delay = settings.RETRY_BACKOFF_BASE ** (self.request.retries + 1)
        logger.warning(
            f"Transaction {transaction_id} failed on attempt {self.request.retries + 1}. "
            f"Retrying in {retry_delay}s. Error: {exc}"
        )
        raise self.retry(exc=exc, countdown=retry_delay)


@celery_app.task(
    name="app.workers.tasks.retry_failed_transactions",
    queue="maintenance",
)
def retry_failed_transactions():
    """
    Periodic task to pick up VALIDATED transactions that were never processed.
    Useful for recovering from worker crashes.
    """
    from sqlalchemy import select
    from app.models import Transaction, TransactionStatus

    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Transaction).where(
                    Transaction.status == TransactionStatus.VALIDATED,
                    Transaction.retry_count < settings.MAX_RETRIES,
                )
            )
            stale = result.scalars().all()
            for txn in stale:
                logger.info(f"Re-queueing stale transaction {txn.id}")
                process_transaction_task.delay(str(txn.id))

    run_async(_run())
