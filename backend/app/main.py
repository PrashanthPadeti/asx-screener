"""
ASX Screener — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
import sys

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
# Nothing configured the root logger before this. With no handler on it,
# Python's last-resort handler emits WARNING and above to stderr and DISCARDS
# everything below -- so every log.info() this application writes went nowhere
# in production. Not some of them: all of them, across billing, compute and the
# schedulers.
#
# That was not a cosmetic gap. During the 15 Sep 2026 billing outage the
# webhook logged "Stripe event: {type}" on every single request and none of it
# reached the log file, so diagnosis rested entirely on the traceback uvicorn
# happened to print at ERROR. Hours of a customer-facing outage were invisible
# in the one place an operator looks.
#
# Read from the environment rather than Settings deliberately: Settings uses
# extra="forbid", and a new field there means a new .env key on every
# deployment that lacks it. This needs no key to work and accepts one if given.
#
# stdout, because asx-backend.service has StandardOutput=append: pointing at
# logs/backend.log. uvicorn's own loggers set propagate=False, so its access
# lines are not duplicated by this.
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

# Redact credentials before they reach the sink. httpx logs every request URL
# at INFO with the query string intact, so every EODHD call was writing
# api_token=<key> into logs/backend.log -- which is how the original key
# leaked, and how its first replacement leaked on its very first use.
# Attached to the HANDLER, not the logger: a logger filter never sees records
# that propagate from httpx. See app/core/log_redaction.py.
from app.core.log_redaction import install_secret_redaction   # noqa: E402

install_secret_redaction()

# Global rate limiter — keyed by client IP
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # ── Stripe env validation ──────────────────────────────────
    _stripe_keys = [
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRO_MONTHLY", "STRIPE_PRO_YEARLY",
        "STRIPE_PREMIUM_MONTHLY", "STRIPE_PREMIUM_YEARLY",
    ]
    _missing = [k for k in _stripe_keys if not getattr(settings, k, "")]
    if _missing:
        logger.warning("Stripe env vars not set (payments disabled): %s", ", ".join(_missing))

    # ── Ensure audit tables exist ─────────────────────────────
    # Each statement runs in its own session/transaction so a failing
    # CREATE INDEX never rolls back the CREATE TABLE.
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import text as _text

    async def _run_ddl(sql: str, label: str) -> bool:
        """Execute one DDL statement in its own transaction. Returns True on success."""
        try:
            async with AsyncSessionLocal() as _db:
                await _db.execute(_text(sql))
                await _db.commit()
            return True
        except Exception as _e:
            logger.warning(f"DDL skipped ({label}): {_e}")
            return False

    if await _run_ddl("""
        CREATE TABLE IF NOT EXISTS users.subscription_events (
            id              BIGSERIAL PRIMARY KEY,
            user_id         UUID        NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
            event_type      TEXT        NOT NULL,
            old_plan        TEXT,
            new_plan        TEXT,
            stripe_event_id TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """, "create subscription_events"):
        logger.info("subscription_events table ready")

    await _run_ddl(
        "CREATE INDEX IF NOT EXISTS idx_sub_events_user_id ON users.subscription_events (user_id)",
        "idx_sub_events_user_id"
    )
    await _run_ddl(
        "CREATE INDEX IF NOT EXISTS idx_sub_events_event_type ON users.subscription_events (event_type)",
        "idx_sub_events_event_type"
    )

    # NOTE: email_verification_token + email_verification_sent_at columns were
    # added manually via psql (ALTER TABLE requires superuser on this DB setup).
    # A paid capability that depends on an external credential must announce
    # its own absence. Without ANTHROPIC_API_KEY, NL Screener (Pro+) and AI
    # Portfolio Insights (Premium+) return 503 to every entitled subscriber,
    # and before v11.2.34 nothing said so anywhere: no startup line, no log
    # on the refusal, nothing on /health. A customer found it instead, and
    # only after paying.
    #
    # Logged at ERROR deliberately. This is not a note about optional
    # tooling; it means people are being charged for features that cannot
    # run. The key itself is never logged -- only whether one is present.
    if not settings.ANTHROPIC_API_KEY:
        logger.error(
            "ANTHROPIC_API_KEY is not set — NL Screener and AI Portfolio "
            "Insights will return 503 to every Pro and Premium subscriber. "
            "Paid features are unavailable until a key is installed.")
    else:
        logger.info("AI features configured (NL Screener, Portfolio Insights)")

    # Schema is confirmed correct — no DDL needed at startup.

    # ── Start schedulers ──────────────────────────────────────
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    # An instrument gets a scheduler that schedules nothing.
    #
    # Importing this module runs the lifespan, and the lifespan is where a
    # production execution authority comes into being. Twice now a diagnostic
    # has started nineteen real jobs on the production host purely by
    # importing the app: Gate B while claiming to be read-only, and
    # test_admin_scheduler_surface, which passed standalone and failed only
    # under pytest because it set an environment variable that Settings had
    # already read.
    #
    # The check is here, at the single point of creation, rather than at each
    # of the twenty add_job call sites — a protection distributed across the
    # places the mistake keeps being made is a protection that will be missed
    # in the same way.
    from app.core.instrument import NullScheduler, instrument_mode

    if instrument_mode():
        logger.warning(
            "INSTRUMENT MODE — no scheduler is started. This process is a "
            "diagnostic; jobs will be declared and none registered.")
        scheduler = NullScheduler()
    else:
        scheduler = AsyncIOScheduler(job_defaults={
            "misfire_grace_time": 3600,  # fire missed jobs if up to 1 hour late (survives restarts/deploys)
            "coalesce": True,            # if multiple firings missed, run only once (no catch-up storm)
            "max_instances": 1,          # never overlap with a still-running instance
        })

    # Every add_job call lives in app/scheduler_registry.py so the worker
    # process (v11.2.44) registers exactly the same jobs from the same
    # declaration. Two lists would drift, and the drift reads as a job
    # running twice or not at all.
    from app.scheduler_registry import register_jobs
    register_jobs(scheduler, settings, logger)

    # ── Rollout freeze ────────────────────────────────────────
    # A maintenance window needs the API serving and nothing computing. The
    # P0-A migration and canonical recompute rewrite screener.universe, and
    # most of the jobs above read or write it; a job landing mid-rollout would
    # observe a half-transitioned table or overwrite recomputed rows with
    # values from the previous contract.
    #
    # Jobs are removed rather than the scheduler paused. job_defaults carries
    # misfire_grace_time=3600 with coalesce=True, so a paused scheduler that
    # resumes fires everything missed in the preceding hour — including on the
    # restart that lifts the freeze, which is the worst possible moment.
    # Removing before start() means the scheduler begins with nothing to run,
    # and no await happens in between, so nothing can fire in the gap.
    #
    # Read through Settings, not os.getenv. The systemd unit has no
    # EnvironmentFile, so nothing in .env reaches the process environment —
    # os.getenv would have returned None and reported a freeze that had not
    # happened. Settings is also where the variable must be *declared*:
    # pydantic-settings forbids extras, so an undeclared key in .env fails
    # Settings() construction at import and the app cannot start at all.
    #
    # Default is on: forgetting to set this leaves production behaving exactly
    # as it does today, and the freeze is the deliberate act.
    # Instrument mode implies frozen. Nothing is scheduled, so reporting
    # "enabled" would describe a scheduler that does not exist — and the admin
    # surface would then read as twenty jobs missing rather than as a process
    # that never had any.
    frozen = not settings.SCHEDULERS_ENABLED or instrument_mode()
    if frozen:
        scheduler.remove_all_jobs()

    scheduler.start()

    if frozen:
        logger.warning(
            "SCHEDULERS FROZEN — SCHEDULERS_ENABLED is off, so no background "
            "jobs are registered. The API is serving normally and nothing is "
            "computing. Unset the variable and restart to resume.")
    else:
        logger.info("Schedulers started: alerts(15m), portfolio-threshold(30m), weekly-summary(Mon 8am), announcements(10m), watchlist-digest(7:30am), asx-companies(6am), capital-raises(7:30am), index-prices(5:30pm), fund-prices(5:35pm), global-markets(5:40pm), commodities(5:45pm), asx-indices(5:50pm), market-snapshot(7:50pm), short-positions(8:05pm), anomaly-detect(8:20pm), anomaly-alerts(8:35pm), top5-strategy(2nd of month 8pm), mining-reit-metrics(Sun 7am)")

    # Published on /health because the log is not a usable channel: uvicorn
    # configures its own loggers and none of this module's logger.info lines
    # reach logs/backend.log — a whole-file grep for "Schedulers started"
    # returns zero. A freeze verified by log line could never succeed.
    #
    # The job count rather than the flag, because the flag only says what was
    # asked for. len(get_jobs()) is what the running scheduler actually holds,
    # so a freeze that silently failed to remove them cannot report success.
    app.state.schedulers_frozen = frozen
    app.state.scheduler_jobs = len(scheduler.get_jobs())

    # The scheduler itself, so the admin surface can report which jobs are
    # registered rather than only how many. A count cannot be reconciled
    # against static intent: twenty registrations and twenty live jobs agree
    # numerically while naming different work. Read-only by convention —
    # nothing outside this module may add, remove or modify a job through it.
    app.state.scheduler = scheduler

    yield

    scheduler.shutdown(wait=False)
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="ASX Stock Screener API — Australian stocks with franking credits, mining & REIT depth, AI insights",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://asxscreener.com.au",
        "https://www.asxscreener.com.au",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ──────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    from app.core.cache import cache_ping
    redis_ok = await cache_ping()
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "redis": "connected" if redis_ok else "unavailable",
        # Observable scheduler state, for maintenance windows. "jobs" is what
        # this process currently holds, so 0 is proof the freeze took effect
        # in the running app rather than proof a config file says so.
        "schedulers": {
            "frozen": getattr(app.state, "schedulers_frozen", None),
            "jobs":   getattr(app.state, "scheduler_jobs", None),
            # Reported separately from "frozen" because it is controlled
            # separately. Thawing restores the schedulers and must not restore
            # this; surfacing it here is what lets an operator verify that
            # after a thaw rather than take it on trust.
            "anomaly_alerts": settings.ANOMALY_ALERTS_ENABLED,
        },
        # Paid features that depend on an external credential. A missing key
        # turns NL Screener (Pro+) and AI Portfolio Insights (Premium+) into a
        # 503 for every subscriber entitled to them, and until now nothing
        # said so: no startup warning, no log on the refusal, nothing here.
        # The only signal was a customer complaining, 16 days in.
        #
        # Boolean only -- never the key, never its length. Whether the
        # capability is available is operational state; the credential is not.
        "features": {
            "ai_configured": bool(settings.ANTHROPIC_API_KEY),
        },
    }


@app.get("/", tags=["System"])
async def root():
    return {"message": "ASX Screener API", "docs": "/docs"}


# ── Routers ───────────────────────────────────────────────────
from app.api.v1.router import api_router
app.include_router(api_router, prefix="/api/v1")
