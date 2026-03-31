from fastapi import Request, HTTPException, status
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def validate_safaricom_ip(request: Request) -> None:
    """Middleware to whitelist Safaricom callback IPs."""
    if not settings.is_production:
        return  # Skip in dev/test

    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else ""

    if client_ip not in settings.allowed_ips:
        logger.warning(
            "unauthorized_callback_ip",
            client_ip=client_ip,
            allowed=settings.allowed_ips,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: IP not whitelisted",
        )


def sanitize_phone(phone: str) -> str:
    """Normalize phone number to 2547XXXXXXXX format."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+254"):
        phone = phone[1:]
    elif phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7") or phone.startswith("1"):
        phone = "254" + phone
    return phone


def is_valid_kenyan_phone(phone: str) -> bool:
    """Validate Kenyan phone number."""
    sanitized = sanitize_phone(phone)
    return (
        sanitized.startswith("254")
        and len(sanitized) == 12
        and sanitized[3:4] in ("7", "1")
    )
