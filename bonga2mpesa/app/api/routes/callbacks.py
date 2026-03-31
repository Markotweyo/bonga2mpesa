from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.logging import get_logger
from app.core.security import validate_safaricom_ip
from app.db.session import get_db
from app.schemas import AcknowledgeResponse
from app.services.daraja_client import DarajaClient
from app.services.transaction_service import TransactionService
from app.workers.tasks import process_transaction_task

logger = get_logger(__name__)

router = APIRouter(prefix="/callbacks", tags=["callbacks"])


def get_redis(request: Request) -> aioredis.Redis:
    """Dependency: pull the shared Redis client from app state."""
    return request.app.state.redis


async def get_transaction_service(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TransactionService:
    daraja = DarajaClient(redis)
    return TransactionService(db, redis, daraja)


@router.post(
    "/c2b",
    response_model=AcknowledgeResponse,
    summary="Safaricom C2B payment callback",
)
async def c2b_callback(
    request: Request,
    service: TransactionService = Depends(get_transaction_service),
):
    await validate_safaricom_ip(request)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info("c2b_callback_received", payload_keys=list(payload.keys()))

    try:
        result = await service.handle_c2b_callback(payload)
    except ValueError as e:
        logger.error("c2b_validation_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.exception("c2b_processing_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )

    # Enqueue payout for validated transactions
    if result.get("status") == "queued":
        transaction_id = result["transaction_id"]
        process_transaction_task.delay(transaction_id)
        logger.info("payout_task_enqueued", transaction_id=transaction_id)

    return AcknowledgeResponse()


@router.post(
    "/b2c/result",
    response_model=AcknowledgeResponse,
    summary="Daraja B2C result callback",
)
async def b2c_result_callback(
    request: Request,
    service: TransactionService = Depends(get_transaction_service),
):
    await validate_safaricom_ip(request)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info("b2c_result_received", payload_keys=list(payload.keys()))

    try:
        await service.handle_b2c_result(payload)
    except ValueError as e:
        logger.error("b2c_result_validation_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.exception("b2c_result_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )

    return AcknowledgeResponse()


@router.post(
    "/b2c/timeout",
    response_model=AcknowledgeResponse,
    summary="Daraja B2C timeout callback",
)
async def b2c_timeout_callback(
    request: Request,
    service: TransactionService = Depends(get_transaction_service),
):
    await validate_safaricom_ip(request)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info("b2c_timeout_received")

    try:
        await service.handle_b2c_timeout(payload)
    except Exception as e:
        logger.exception("b2c_timeout_error", error=str(e))

    return AcknowledgeResponse()
