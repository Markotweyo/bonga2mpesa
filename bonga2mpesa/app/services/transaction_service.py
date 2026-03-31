import uuid
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger, set_correlation_id
from app.models import Transaction, TransactionStatus, User, WebhookLog, WebhookEventType
from app.schemas import C2BDirectPayload, B2CResultPayload
from app.services.valuation_service import ValuationService
from app.services.ledger_service import LedgerService
from app.services.daraja_client import DarajaClient

logger = get_logger(__name__)

IDEMPOTENCY_TTL = 86400  # 24 hours


class TransactionService:
    def __init__(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        daraja: DarajaClient,
    ):
        self.db = db
        self.redis = redis
        self.daraja = daraja
        self.valuation = ValuationService()
        self.ledger = LedgerService(db)

    # ── Idempotency ──────────────────────────────────────────────────────────

    async def _check_idempotency(self, key: str) -> bool:
        """Returns True if already processed (duplicate)."""
        redis_key = f"idempotency:{key}"
        result = await self.redis.set(redis_key, "1", ex=IDEMPOTENCY_TTL, nx=True)
        return result is None  # None = key existed = duplicate

    async def _get_transaction_by_receipt(self, receipt: str) -> Optional[Transaction]:
        result = await self.db.execute(
            select(Transaction).where(Transaction.mpesa_receipt == receipt)
        )
        return result.scalar_one_or_none()

    async def _get_transaction_by_correlation(self, correlation_id: str) -> Optional[Transaction]:
        result = await self.db.execute(
            select(Transaction).where(Transaction.correlation_id == correlation_id)
        )
        return result.scalar_one_or_none()

    async def _get_transaction_by_conversation(self, conversation_id: str) -> Optional[Transaction]:
        result = await self.db.execute(
            select(Transaction).where(Transaction.b2c_conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    # ── User ─────────────────────────────────────────────────────────────────

    async def _get_or_create_user(self, phone_number: str) -> User:
        result = await self.db.execute(
            select(User).where(User.phone_number == phone_number)
        )
        user = result.scalar_one_or_none()
        if not user:
            user = User(id=uuid.uuid4(), phone_number=phone_number)
            self.db.add(user)
            await self.db.flush()
        return user

    # ── Webhook Logging ──────────────────────────────────────────────────────

    async def _log_webhook(
        self,
        event_type: WebhookEventType,
        payload: dict,
    ) -> WebhookLog:
        log = WebhookLog(
            id=uuid.uuid4(),
            event_type=event_type,
            payload=payload,
            processed=False,
        )
        self.db.add(log)
        await self.db.flush()
        return log

    # ── C2B Processing ───────────────────────────────────────────────────────

    async def handle_c2b_callback(self, payload: dict) -> dict:
        """Process incoming C2B payment from Safaricom."""
        webhook_log = await self._log_webhook(WebhookEventType.C2B, payload)

        try:
            c2b = C2BDirectPayload(**payload)
        except Exception as e:
            webhook_log.processing_error = str(e)
            await self.db.flush()
            raise ValueError(f"Invalid C2B payload: {e}")

        receipt = c2b.TransID
        phone = c2b.MSISDN
        amount = float(c2b.TransAmount)
        bill_ref = c2b.BillRefNumber  # phone or bonga points from USSD

        set_correlation_id(receipt)

        # Idempotency check
        is_duplicate = await self._check_idempotency(f"c2b:{receipt}")
        if is_duplicate:
            logger.warning("c2b_duplicate", receipt=receipt)
            webhook_log.processed = True
            await self.db.flush()
            return {"status": "duplicate", "receipt": receipt}

        existing = await self._get_transaction_by_receipt(receipt)
        if existing:
            logger.warning("c2b_already_exists", receipt=receipt, txn_id=str(existing.id))
            webhook_log.processed = True
            await self.db.flush()
            return {"status": "already_processed", "transaction_id": str(existing.id)}

        # Try to infer bonga points from amount (reverse calc)
        bonga_points = round(amount / settings.SAFARICOM_RATE)
        expected_payout = self.valuation.compute_expected_payout(bonga_points)

        user = await self._get_or_create_user(phone)
        correlation_id = receipt

        transaction = Transaction(
            id=uuid.uuid4(),
            user_id=user.id,
            phone_number=phone,
            bonga_points=bonga_points,
            expected_amount=expected_payout,
            safaricom_amount=amount,
            payout_amount=expected_payout,
            status=TransactionStatus.PENDING,
            mpesa_receipt=receipt,
            correlation_id=correlation_id,
        )
        self.db.add(transaction)
        await self.db.flush()

        # Validate amount
        if not self.valuation.is_profitable(amount, expected_payout):
            transaction.status = TransactionStatus.FAILED
            transaction.failure_reason = "Insufficient profit margin"
            await self.db.flush()
            logger.error(
                "transaction_unprofitable",
                receipt=receipt,
                safaricom_amount=amount,
                payout=expected_payout,
            )
            webhook_log.processed = True
            await self.db.flush()
            return {"status": "rejected", "reason": "unprofitable"}

        transaction.status = TransactionStatus.VALIDATED
        webhook_log.processed = True
        await self.db.flush()

        logger.info(
            "c2b_validated",
            receipt=receipt,
            phone=phone,
            amount=amount,
            payout=expected_payout,
            transaction_id=str(transaction.id),
        )

        return {
            "status": "queued",
            "transaction_id": str(transaction.id),
            "correlation_id": correlation_id,
        }

    # ── B2C Payout ───────────────────────────────────────────────────────────

    async def process_payout(self, transaction_id: str) -> None:
        """Called by background worker to trigger B2C payment."""
        result = await self.db.execute(
            select(Transaction).where(Transaction.id == uuid.UUID(transaction_id))
        )
        transaction = result.scalar_one_or_none()

        if not transaction:
            logger.error("transaction_not_found", transaction_id=transaction_id)
            return

        if transaction.status not in (TransactionStatus.VALIDATED,):
            logger.warning(
                "transaction_wrong_status",
                transaction_id=transaction_id,
                status=transaction.status,
            )
            return

        set_correlation_id(transaction.correlation_id)

        idempotency_key = f"b2c_payout:{transaction.id}"
        is_duplicate = await self._check_idempotency(idempotency_key)
        if is_duplicate:
            logger.warning("b2c_payout_duplicate", transaction_id=transaction_id)
            return

        try:
            response = await self.daraja.b2c_payment(
                phone_number=transaction.phone_number,
                amount=float(transaction.payout_amount),
                correlation_id=transaction.correlation_id,
            )

            transaction.b2c_conversation_id = response.get("ConversationID")
            transaction.status = TransactionStatus.PROCESSING
            await self.db.flush()

            logger.info(
                "b2c_payout_initiated",
                transaction_id=str(transaction.id),
                conversation_id=transaction.b2c_conversation_id,
            )

        except Exception as e:
            transaction.retry_count += 1
            if transaction.retry_count >= settings.MAX_RETRIES:
                transaction.status = TransactionStatus.FAILED
                transaction.failure_reason = f"Max retries exceeded: {e}"
                logger.error(
                    "b2c_payout_max_retries",
                    transaction_id=transaction_id,
                    error=str(e),
                )
            else:
                logger.warning(
                    "b2c_payout_retry",
                    transaction_id=transaction_id,
                    retry=transaction.retry_count,
                    error=str(e),
                )
            await self.db.flush()
            raise

    # ── B2C Result Handling ──────────────────────────────────────────────────

    async def handle_b2c_result(self, payload: dict) -> dict:
        """Process B2C result callback from Daraja."""
        webhook_log = await self._log_webhook(WebhookEventType.B2C_RESULT, payload)

        try:
            b2c = B2CResultPayload(**payload)
        except Exception as e:
            webhook_log.processing_error = str(e)
            await self.db.flush()
            raise ValueError(f"Invalid B2C result payload: {e}")

        result = b2c.Result
        conversation_id = result.ConversationID
        originator_id = result.OriginatorConversationID

        set_correlation_id(originator_id)

        transaction = await self._get_transaction_by_conversation(conversation_id)
        if not transaction:
            transaction = await self._get_transaction_by_correlation(originator_id)

        if not transaction:
            logger.error(
                "b2c_result_transaction_not_found",
                conversation_id=conversation_id,
                originator_id=originator_id,
            )
            webhook_log.processing_error = "Transaction not found"
            await self.db.flush()
            return {"status": "error", "message": "Transaction not found"}

        if result.ResultCode == 0:
            # Success
            mpesa_receipt = result.TransactionID
            transaction.status = TransactionStatus.SUCCESS
            transaction.mpesa_receipt = mpesa_receipt if not transaction.mpesa_receipt else transaction.mpesa_receipt
            await self.db.flush()

            await self.ledger.record_transaction_complete(transaction)

            webhook_log.processed = True
            await self.db.flush()

            logger.info(
                "b2c_success",
                transaction_id=str(transaction.id),
                receipt=mpesa_receipt,
                payout=float(transaction.payout_amount),
            )
            return {"status": "success", "transaction_id": str(transaction.id)}

        else:
            # Failure
            transaction.status = TransactionStatus.FAILED
            transaction.failure_reason = f"B2C failed [{result.ResultCode}]: {result.ResultDesc}"
            webhook_log.processed = True
            await self.db.flush()

            logger.error(
                "b2c_failed",
                transaction_id=str(transaction.id),
                result_code=result.ResultCode,
                result_desc=result.ResultDesc,
            )
            return {"status": "failed", "transaction_id": str(transaction.id)}

    async def handle_b2c_timeout(self, payload: dict) -> dict:
        """Handle B2C timeout callback."""
        await self._log_webhook(WebhookEventType.B2C_TIMEOUT, payload)
        originator_id = payload.get("Result", {}).get("OriginatorConversationID", "")
        if originator_id:
            transaction = await self._get_transaction_by_correlation(originator_id)
            if transaction and transaction.status == TransactionStatus.PROCESSING:
                transaction.failure_reason = "B2C timeout — will retry"
                await self.db.flush()
                logger.warning("b2c_timeout", originator_id=originator_id)
        return {"status": "timeout_received"}
