import base64
import uuid
from typing import Optional

import httpx
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

REDIS_TOKEN_KEY = "daraja:access_token"


class DarajaClient:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def _get_cached_token(self) -> Optional[str]:
        token = await self.redis.get(REDIS_TOKEN_KEY)
        if token:
            return token.decode() if isinstance(token, bytes) else token
        return None

    async def _fetch_token(self) -> str:
        credentials = f"{settings.DARAJA_CONSUMER_KEY}:{settings.DARAJA_CONSUMER_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                settings.DARAJA_AUTH_URL,
                headers={"Authorization": f"Basic {encoded}"},
            )
            resp.raise_for_status()
            data = resp.json()

        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600)) - 60  # buffer

        await self.redis.setex(REDIS_TOKEN_KEY, expires_in, token)
        logger.info("daraja_token_refreshed", expires_in=expires_in)
        return token

    async def get_token(self) -> str:
        token = await self._get_cached_token()
        if not token:
            token = await self._fetch_token()
        return token

    async def b2c_payment(
        self,
        phone_number: str,
        amount: float,
        correlation_id: str,
        occasion: str = "Bonga Points Redemption",
    ) -> dict:
        token = await self.get_token()

        payload = {
            "InitiatorName": settings.DARAJA_INITIATOR_NAME,
            "SecurityCredential": settings.DARAJA_SECURITY_CREDENTIAL,
            "CommandID": "BusinessPayment",
            "Amount": int(amount),
            "PartyA": settings.DARAJA_SHORTCODE,
            "PartyB": phone_number,
            "Remarks": f"Bonga redemption {correlation_id}",
            "QueueTimeOutURL": f"{settings.CALLBACK_BASE_URL}/callbacks/b2c/timeout",
            "ResultURL": f"{settings.CALLBACK_BASE_URL}/callbacks/b2c/result",
            "Occasion": occasion,
            "OriginatorConversationID": correlation_id,
        }

        logger.info(
            "b2c_payment_request",
            phone=phone_number,
            amount=amount,
            correlation_id=correlation_id,
        )

        for attempt in range(settings.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        settings.DARAJA_B2C_URL,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                logger.info(
                    "b2c_payment_submitted",
                    conversation_id=data.get("ConversationID"),
                    originator_id=data.get("OriginatorConversationID"),
                )
                return data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401 and attempt < settings.MAX_RETRIES - 1:
                    # Token expired — force refresh
                    await self.redis.delete(REDIS_TOKEN_KEY)
                    token = await self._fetch_token()
                    continue
                logger.error(
                    "b2c_http_error",
                    status=e.response.status_code,
                    body=e.response.text,
                    attempt=attempt,
                )
                raise
            except httpx.RequestError as e:
                logger.warning("b2c_request_error", error=str(e), attempt=attempt)
                if attempt == settings.MAX_RETRIES - 1:
                    raise

        raise RuntimeError("B2C payment failed after all retries")
