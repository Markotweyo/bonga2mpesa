import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.transaction_service import TransactionService
from app.models import TransactionStatus


def make_service(mock_db, mock_redis, mock_daraja):
    return TransactionService(mock_db, mock_redis, mock_daraja)


@pytest.mark.asyncio
async def test_c2b_duplicate_rejected(mock_db, mock_redis, mock_daraja, sample_c2b_payload):
    # Redis returns None on set → key already existed → duplicate
    mock_redis.set = AsyncMock(return_value=None)

    svc = make_service(mock_db, mock_redis, mock_daraja)

    # Patch _log_webhook so DB isn't actually called
    svc._log_webhook = AsyncMock(return_value=MagicMock(processed=False, processing_error=None))

    result = await svc.handle_c2b_callback(sample_c2b_payload)
    assert result["status"] == "duplicate"


@pytest.mark.asyncio
async def test_c2b_invalid_payload_raises(mock_db, mock_redis, mock_daraja):
    svc = make_service(mock_db, mock_redis, mock_daraja)
    svc._log_webhook = AsyncMock(return_value=MagicMock(processed=False, processing_error=None))
    mock_redis.set = AsyncMock(return_value=True)

    with pytest.raises(ValueError, match="Invalid C2B payload"):
        await svc.handle_c2b_callback({"bad": "data"})


@pytest.mark.asyncio
async def test_b2c_result_success_updates_transaction(mock_db, mock_redis, mock_daraja, sample_b2c_result_payload):
    svc = make_service(mock_db, mock_redis, mock_daraja)
    svc._log_webhook = AsyncMock(return_value=MagicMock(processed=False, processing_error=None))

    fake_txn = MagicMock()
    fake_txn.id = uuid.uuid4()
    fake_txn.safaricom_amount = 153.4
    fake_txn.payout_amount = 102.01
    fake_txn.mpesa_receipt = None
    fake_txn.status = TransactionStatus.PROCESSING

    svc._get_transaction_by_conversation = AsyncMock(return_value=fake_txn)
    svc._get_transaction_by_correlation = AsyncMock(return_value=None)
    svc.ledger.record_transaction_complete = AsyncMock()

    result = await svc.handle_b2c_result(sample_b2c_result_payload)

    assert result["status"] == "success"
    assert fake_txn.status == TransactionStatus.SUCCESS


@pytest.mark.asyncio
async def test_b2c_result_failure_marks_failed(mock_db, mock_redis, mock_daraja):
    svc = make_service(mock_db, mock_redis, mock_daraja)
    svc._log_webhook = AsyncMock(return_value=MagicMock(processed=False, processing_error=None))

    failed_payload = {
        "Result": {
            "ResultType": 0,
            "ResultCode": 2001,
            "ResultDesc": "Insufficient funds",
            "OriginatorConversationID": "orig-123",
            "ConversationID": "conv-456",
            "TransactionID": "TXN001",
        }
    }

    fake_txn = MagicMock()
    fake_txn.id = uuid.uuid4()
    fake_txn.status = TransactionStatus.PROCESSING

    svc._get_transaction_by_conversation = AsyncMock(return_value=fake_txn)

    result = await svc.handle_b2c_result(failed_payload)

    assert result["status"] == "failed"
    assert fake_txn.status == TransactionStatus.FAILED
    assert "2001" in fake_txn.failure_reason
