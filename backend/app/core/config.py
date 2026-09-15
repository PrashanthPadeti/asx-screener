"""
ASX Screener — App Configuration
Reads from environment variables / .env file
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ASX Screener API"
    APP_VERSION: str = "10.0.0"
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
    FRONTEND_URL: str = "http://localhost:3000"

    # Stripe
    # ── Outbound anomaly alerts ───────────────────────────────────────────────
    # Independently controlled, and OFF unless deliberately opted in.
    #
    # p0a_freeze.sh thaw restores every scheduler at once. Its header claimed
    # the anomaly alert worker was "excluded from thaw deliberately"; its
    # implementation restored it and printed a reminder asking a human to stop
    # the job before the next 20:35 run. A comment is not an exclusion, and a
    # reminder is not a control.
    #
    # Until the detector's applicability repair and re-detection sequence are
    # complete, the active anomaly set is known to contain defect-derived
    # flags -- doubled grossed-up yields, off-domain Piotroski scores. Those
    # must not reach a customer's inbox because somebody restarted a service.
    #
    # Turning this on is a release decision with its own gate (P0-A-7), not a
    # side effect of thawing.
    ANOMALY_ALERTS_ENABLED: bool = False

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
    CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"  # update here when model changes

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
    SUPPORT_EMAIL: str = "asxscreener@gmail.com"
    ADMIN_EMAILS: str = "asxscreener@gmail.com"   # comma-separated list

    # SMS (Twilio)
    TWILIO_ACCOUNT_SID:  str = ""
    TWILIO_AUTH_TOKEN:   str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # EODHD (market data)
    EODHD_API_KEY: str = ""

    # Alpha Vantage (commodities — free tier: 25 req/day)
    ALPHA_VANTAGE_API_KEY: str = ""

    # Rate limiting (requests per minute by plan)
    RATE_LIMIT_FREE: int = 30
    RATE_LIMIT_PRO: int = 120
    RATE_LIMIT_PREMIUM: int = 300

    # Founding Members promotion
    # First N paying subscribers get extended access:
    #   Monthly plan → 6 months access  (instead of 1 month)
    #   Annual plan  → 3 years access   (instead of 1 year)
    # Set to 0 to disable the promotion entirely.
    FOUNDING_MEMBER_LIMIT: int = 100

    # Rollout freeze. False stops app/main.py registering any background job,
    # so a maintenance window can halt computation while the API keeps serving.
    #
    # It must be declared here, not merely set in .env. pydantic-settings
    # defaults to extra="forbid", so an undeclared key does not fall back to a
    # default — it raises ValidationError while Settings() is constructed, at
    # import time, and uvicorn cannot load the app at all. Setting this
    # variable without this field took the API down for eight minutes on
    # 11 Sep 2026: the failure was total and immediate, not a quiet fallback.
    #
    # Reading it through Settings rather than os.getenv also matters. The
    # systemd unit has no EnvironmentFile, so nothing in .env reaches the
    # process environment; os.getenv would have returned None and reported a
    # freeze that had not happened.
    SCHEDULERS_ENABLED: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
