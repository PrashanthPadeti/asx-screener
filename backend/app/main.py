"""
ASX Screener — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # ── Start schedulers ──────────────────────────────────────
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from app.workers.alert_worker import check_alerts
    from app.workers.portfolio_worker import check_portfolio_thresholds, send_weekly_portfolio_summaries
    from app.workers.announcement_worker import fetch_announcements

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

    scheduler.start()
    logger.info("Schedulers started: alerts(15m), portfolio-threshold(30m), weekly-summary(Mon 8am), announcements(10m)")

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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://209.38.84.102:3000",
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
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/", tags=["System"])
async def root():
    return {"message": "ASX Screener API", "docs": "/docs"}


# ── Routers ───────────────────────────────────────────────────
from app.api.v1.router import api_router
app.include_router(api_router, prefix="/api/v1")
