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

    # ── Start alert scheduler ──────────────────────────────────
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.workers.alert_worker import check_alerts

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_alerts,
        trigger="interval",
        minutes=15,
        id="alert_checker",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Alert scheduler started (every 15 min)")

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
