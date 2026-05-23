"""
ASX Screener — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings

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
    # Schema is confirmed correct — no DDL needed at startup.

    # ── Start schedulers ──────────────────────────────────────
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from app.workers.alert_worker import check_alerts
    from app.workers.portfolio_worker import check_portfolio_thresholds, send_weekly_portfolio_summaries
    from app.workers.announcement_worker import fetch_announcements
    from app.workers.watchlist_digest_worker import send_watchlist_digests
    from app.workers.index_prices_worker import compute_index_prices
    from app.workers.fund_prices_worker import compute_fund_prices
    from app.workers.global_markets_worker import compute_global_markets
    from app.workers.commodities_worker import compute_commodities
    from app.workers.market_snapshot_worker import run_market_snapshot
    from app.workers.asx_indices_worker import run_asx_indices
    from app.workers.short_positions_worker import run_short_positions
    from app.workers.anomaly_worker import run_anomaly_detect
    from app.workers.top5_strategy_worker import run_top5_strategy
    from app.workers.asx_companies_worker import sync_asx_companies
    from app.workers.anomaly_alert_worker import send_anomaly_alerts
    from app.workers.capital_raise_worker import scan_capital_raises
    from app.workers.cleanup_worker import purge_expired_sessions, run_data_deletion
    from app.workers.mining_reit_worker import sync_mining_reit_metrics

    scheduler = AsyncIOScheduler()

    # Price alerts — every 15 min
    scheduler.add_job(check_alerts, trigger="interval", minutes=15,
                      id="alert_checker", replace_existing=True)

    # Portfolio threshold alerts — every 30 min
    scheduler.add_job(check_portfolio_thresholds, trigger="interval", minutes=30,
                      id="portfolio_threshold_checker", replace_existing=True)

    # Weekly portfolio summary — Monday 8am AEST
    scheduler.add_job(send_weekly_portfolio_summaries,
                      CronTrigger(day_of_week="mon", hour=8, minute=0,
                                  timezone="Australia/Sydney"),
                      id="weekly_portfolio_summary", replace_existing=True)

    # ASX announcements fetch — every 10 min
    scheduler.add_job(fetch_announcements, trigger="interval", minutes=10,
                      id="announcement_fetcher", replace_existing=True)

    # Watchlist daily digest — 7:30am AEST
    scheduler.add_job(send_watchlist_digests,
                      CronTrigger(hour=7, minute=30, timezone="Australia/Sydney"),
                      id="watchlist_digest", replace_existing=True)

    # ASX index prices — daily at 5:30pm AEST (30 min after market close)
    scheduler.add_job(compute_index_prices,
                      CronTrigger(hour=17, minute=30, timezone="Australia/Sydney"),
                      id="index_prices", replace_existing=True)

    # ASX ETF/fund prices — daily at 5:35pm AEST
    scheduler.add_job(compute_fund_prices,
                      CronTrigger(hour=17, minute=35, timezone="Australia/Sydney"),
                      id="fund_prices", replace_existing=True)

    # Global market indices + AUD FX — daily at 5:40pm AEST
    scheduler.add_job(compute_global_markets,
                      CronTrigger(hour=17, minute=40, timezone="Australia/Sydney"),
                      id="global_markets", replace_existing=True)

    # Commodity prices — daily at 5:45pm AEST
    scheduler.add_job(compute_commodities,
                      CronTrigger(hour=17, minute=45, timezone="Australia/Sydney"),
                      id="commodities", replace_existing=True)

    # ASX index constituent flags (is_asx200/300) — daily at 5:50pm AEST
    scheduler.add_job(run_asx_indices,
                      CronTrigger(hour=17, minute=50, timezone="Australia/Sydney"),
                      id="asx_indices", replace_existing=True)

    # ASIC short positions — daily at 8:05pm AEST
    # Moved from 6:30pm: the daily_pipeline (cron 6:30pm) processes short positions in
    # steps 2/4/6; running APScheduler at the same time caused simultaneous writes to
    # staging_au.short_positions / market.short_positions.  8:05pm is well after the
    # pipeline finishes (~7:30-7:40pm) and still covers ASIC's ~6pm publication lag.
    scheduler.add_job(run_short_positions,
                      CronTrigger(hour=20, minute=5, timezone="Australia/Sydney"),
                      id="short_positions", replace_existing=True)

    # Market snapshot (ASX200/300, movers, shorted) — daily at 7:50pm AEST
    # Moved from 6:45pm: at 6:45pm the pipeline's compute engines (steps 7-10) and
    # universe build (step 13) had not yet finished, so the snapshot read stale
    # period_metrics and an incomplete screener.universe.  7:50pm gives a 10-15 min
    # buffer after the pipeline's own step 14 snapshot (~7:30-7:40pm) and acts as a
    # safety-net rerun with fully-settled data.
    scheduler.add_job(run_market_snapshot,
                      CronTrigger(hour=19, minute=50, timezone="Australia/Sydney"),
                      id="market_snapshot", replace_existing=True)

    # Anomaly detection — daily at 8:20pm AEST (after snapshot safety-net at 7:50pm)
    # Moved from 7:00pm: anomaly detection reads mover_snapshots; running at 7:00pm
    # meant the pipeline step 14 snapshot (~7:30pm) had not yet written fresh data.
    scheduler.add_job(run_anomaly_detect,
                      CronTrigger(hour=20, minute=20, timezone="Australia/Sydney"),
                      id="anomaly_detect", replace_existing=True)

    # Anomaly alert emails — daily at 8:35pm AEST (15 min after anomaly detection)
    scheduler.add_job(send_anomaly_alerts,
                      CronTrigger(hour=20, minute=35, timezone="Australia/Sydney"),
                      id="anomaly_alerts", replace_existing=True)

    # Capital raise scanner — daily at 7:30am AEST (after announcement fetch settles)
    scheduler.add_job(scan_capital_raises,
                      CronTrigger(hour=7, minute=30, timezone="Australia/Sydney"),
                      id="capital_raise_scan", replace_existing=True)

    # Mining & REIT metrics sync — weekly Sunday at 7:00am AEST
    scheduler.add_job(sync_mining_reit_metrics,
                      CronTrigger(day_of_week="sun", hour=7, minute=0, timezone="Australia/Sydney"),
                      id="mining_reit_metrics", replace_existing=True)

    # Top 5 monthly picks — 2nd of each month at 8pm AEST (after universe + composite scores settle)
    scheduler.add_job(run_top5_strategy,
                      CronTrigger(day=2, hour=20, minute=0, timezone="Australia/Sydney"),
                      id="top5_strategy", replace_existing=True)

    # Nightly cleanup — 2:00am AEST (low traffic window)
    scheduler.add_job(purge_expired_sessions,
                      CronTrigger(hour=2, minute=0, timezone="Australia/Sydney"),
                      id="session_cleanup", replace_existing=True)

    # Premium data deletion — 2:15am AEST (after session cleanup)
    # Removes portfolios/alerts for cancelled users whose 12-month window has passed
    scheduler.add_job(run_data_deletion,
                      CronTrigger(hour=2, minute=15, timezone="Australia/Sydney"),
                      id="data_deletion", replace_existing=True)

    # ASX companies list sync — daily at 6:00am AEST (before universe build)
    scheduler.add_job(sync_asx_companies,
                      CronTrigger(hour=6, minute=0, timezone="Australia/Sydney"),
                      id="asx_companies", replace_existing=True)

    scheduler.start()
    logger.info("Schedulers started: alerts(15m), portfolio-threshold(30m), weekly-summary(Mon 8am), announcements(10m), watchlist-digest(7:30am), asx-companies(6am), capital-raises(7:30am), index-prices(5:30pm), fund-prices(5:35pm), global-markets(5:40pm), commodities(5:45pm), asx-indices(5:50pm), market-snapshot(7:50pm), short-positions(8:05pm), anomaly-detect(8:20pm), anomaly-alerts(8:35pm), top5-strategy(2nd of month 8pm), mining-reit-metrics(Sun 7am)")

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
    }


@app.get("/", tags=["System"])
async def root():
    return {"message": "ASX Screener API", "docs": "/docs"}


# ── Routers ───────────────────────────────────────────────────
from app.api.v1.router import api_router
app.include_router(api_router, prefix="/api/v1")
