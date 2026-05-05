"""
ASX Screener — App Configuration
Reads from environment variables / .env file
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ASX Screener API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str                        # Async: postgresql+asyncpg://...
    DATABASE_URL_SYNC: str                   # Sync:  postgresql://...

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Frontend base URL (used in Stripe redirect URLs)
    FRONTEND_URL: str = "http://209.38.84.102:3000"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Individual plans
    STRIPE_PRO_MONTHLY:     str = ""
    STRIPE_PRO_YEARLY:      str = ""
    STRIPE_PREMIUM_MONTHLY: str = ""
    STRIPE_PREMIUM_YEARLY:  str = ""

    # Enterprise Pro
    STRIPE_ENT_PRO_5_MONTHLY:   str = ""
    STRIPE_ENT_PRO_5_YEARLY:    str = ""
    STRIPE_ENT_PRO_10_MONTHLY:  str = ""
    STRIPE_ENT_PRO_10_YEARLY:   str = ""

    # Enterprise Premium
    STRIPE_ENT_PREM_5_MONTHLY:   str = ""
    STRIPE_ENT_PREM_5_YEARLY:    str = ""
    STRIPE_ENT_PREM_10_MONTHLY:  str = ""
    STRIPE_ENT_PREM_10_YEARLY:   str = ""

    # Legacy (keep for backwards compat)
    STRIPE_PRO_PRICE_ID: str = ""

    # Anthropic (Claude)
    ANTHROPIC_API_KEY: str = ""

    # OpenAI (embeddings)
    OPENAI_API_KEY: str = ""

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "asx-screener-docs"
    AWS_REGION: str = "ap-southeast-2"

    # Email (Resend)
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@asxscreener.com.au"

    # SMS (Twilio)
    TWILIO_ACCOUNT_SID:  str = ""
    TWILIO_AUTH_TOKEN:   str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # EODHD (market data)
    EODHD_API_KEY: str = ""

    # Rate limiting (requests per minute by plan)
    RATE_LIMIT_FREE: int = 30
    RATE_LIMIT_PRO: int = 120
    RATE_LIMIT_PREMIUM: int = 300

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
