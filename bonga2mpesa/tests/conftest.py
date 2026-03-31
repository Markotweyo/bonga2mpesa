import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings


@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "YOUR_RATE", 0.133)
    monkeypatch.setattr(settings, "SAFARICOM_RATE", 0.2)
    monkeypatch.setattr(settings, "MAX_RETRIES", 3)


@pytest_asyncio.fixture
async def client(mock_redis):
    """
    Test client with Redis and DB mocked — no real infrastructure needed.
    Bypasses the lifespan so we inject state manually.
    """
    app.state.redis = mock_redis

    # Patch get_db so no real Postgres connection is attempted
    async def _fake_db():
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        yield db

    with patch("app.api.routes.callbacks.get_db", _fake_db):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_daraja():
    client = AsyncMock()
    client.b2c_payment = AsyncMock(return_value={
        "ConversationID": "AG_20240101_test123",
        "OriginatorConversationID": "test-correlation-id",
        "ResponseCode": "0",
        "ResponseDescription": "Accept the service request successfully.",
    })
    return client


@pytest.fixture
def sample_c2b_payload():
    return {
        "TransactionType": "Pay Bill",
        "TransID": "RCX12345ABC",
        "TransTime": "20240101120000",
        "TransAmount": "153.40",
        "BusinessShortCode": "123456",
        "BillRefNumber": "0712345678",
        "MSISDN": "254712345678",
        "FirstName": "John",
        "LastName": "Doe",
    }


@pytest.fixture
def sample_b2c_result_payload():
    return {
        "Result": {
            "ResultType": 0,
            "ResultCode": 0,
            "ResultDesc": "The service request is processed successfully.",
            "OriginatorConversationID": "RCX12345ABC",
            "ConversationID": "AG_20240101_test123",
            "TransactionID": "NLJ7RT61SV",
            "ResultParameters": {
                "ResultParameter": [
                    {"Key": "TransactionAmount", "Value": 102},
                    {"Key": "TransactionReceipt", "Value": "NLJ7RT61SV"},
                    {"Key": "ReceiverPartyPublicName", "Value": "254712345678 - John Doe"},
                    {"Key": "TransactionCompletedDateTime", "Value": "01.01.2024 12:00:00"},
                ]
            },
        }
    }
