import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_c2b_callback_queued(client, sample_c2b_payload):
    mock_service = AsyncMock()
    mock_service.handle_c2b_callback = AsyncMock(return_value={
        "status": "queued",
        "transaction_id": "test-uuid-1234",
        "correlation_id": "RCX12345ABC",
    })

    with patch("app.api.routes.callbacks.TransactionService", return_value=mock_service), \
         patch("app.api.routes.callbacks.DarajaClient"), \
         patch("app.api.routes.callbacks.process_transaction_task") as mock_task:

        mock_task.delay = MagicMock()
        resp = await client.post("/callbacks/c2b", json=sample_c2b_payload)

    assert resp.status_code == 200
    assert resp.json()["ResultCode"] == "00000000"
    mock_task.delay.assert_called_once_with("test-uuid-1234")


@pytest.mark.asyncio
async def test_c2b_callback_duplicate(client, sample_c2b_payload):
    mock_service = AsyncMock()
    mock_service.handle_c2b_callback = AsyncMock(return_value={
        "status": "duplicate",
        "receipt": "RCX12345ABC",
    })

    with patch("app.api.routes.callbacks.TransactionService", return_value=mock_service), \
         patch("app.api.routes.callbacks.DarajaClient"), \
         patch("app.api.routes.callbacks.process_transaction_task") as mock_task:

        mock_task.delay = MagicMock()
        resp = await client.post("/callbacks/c2b", json=sample_c2b_payload)

    assert resp.status_code == 200
    mock_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_c2b_callback_invalid_json(client):
    resp = await client.post(
        "/callbacks/c2b",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_c2b_callback_validation_error(client, sample_c2b_payload):
    mock_service = AsyncMock()
    mock_service.handle_c2b_callback = AsyncMock(
        side_effect=ValueError("Invalid C2B payload")
    )

    with patch("app.api.routes.callbacks.TransactionService", return_value=mock_service), \
         patch("app.api.routes.callbacks.DarajaClient"):
        resp = await client.post("/callbacks/c2b", json=sample_c2b_payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_b2c_result_success(client, sample_b2c_result_payload):
    mock_service = AsyncMock()
    mock_service.handle_b2c_result = AsyncMock(return_value={
        "status": "success",
        "transaction_id": "test-uuid-1234",
    })

    with patch("app.api.routes.callbacks.TransactionService", return_value=mock_service), \
         patch("app.api.routes.callbacks.DarajaClient"):
        resp = await client.post("/callbacks/b2c/result", json=sample_b2c_result_payload)

    assert resp.status_code == 200
    assert resp.json()["ResultCode"] == "00000000"


@pytest.mark.asyncio
async def test_b2c_timeout(client):
    mock_service = AsyncMock()
    mock_service.handle_b2c_timeout = AsyncMock(return_value={"status": "timeout_received"})

    with patch("app.api.routes.callbacks.TransactionService", return_value=mock_service), \
         patch("app.api.routes.callbacks.DarajaClient"):
        resp = await client.post("/callbacks/b2c/timeout", json={"Result": {}})

    assert resp.status_code == 200
