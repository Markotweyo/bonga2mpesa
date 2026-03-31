from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/bonga2mpesa"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Daraja
    DARAJA_CONSUMER_KEY: str
    DARAJA_CONSUMER_SECRET: str
    DARAJA_SHORTCODE: str
    DARAJA_INITIATOR_NAME: str
    DARAJA_SECURITY_CREDENTIAL: str
    DARAJA_B2C_URL: str = "https://sandbox.safaricom.co.ke/mpesa/b2c/v3/paymentrequest"
    DARAJA_AUTH_URL: str = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

    # Callback URLs
    CALLBACK_BASE_URL: str = "https://yourdomain.com"

    # Business logic
    YOUR_RATE: float = 0.133
    SAFARICOM_RATE: float = 0.2
    MIN_PROFIT_MARGIN: float = 0.1

    # Worker
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_BASE: int = 2

    # Security
    SAFARICOM_IP_WHITELIST: str = "196.201.214.200,196.201.214.206"

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    LOG_LEVEL: str = "INFO"

    @property
    def allowed_ips(self) -> List[str]:
        return [ip.strip() for ip in self.SAFARICOM_IP_WHITELIST.split(",")]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def async_database_url(self) -> str:
        db_url = self.DATABASE_URL.strip()

        if db_url.startswith("postgresql+asyncpg:postgresql://"):
            db_url = db_url.replace("postgresql+asyncpg:postgresql://", "postgresql+asyncpg://", 1)

        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        if not db_url.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use postgresql+asyncpg:// for async SQLAlchemy engine"
            )

        return db_url


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
