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
    yield
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
        "http://localhost:3000",       # Next.js dev
        "https://asxscreener.com.au",  # Production
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


# ── Routers (added as built) ──────────────────────────────────
# from app.api.v1.routes import screener, companies, auth, watchlist
# app.include_router(auth.router,      prefix="/api/v1/auth",      tags=["Auth"])
# app.include_router(companies.router, prefix="/api/v1/companies", tags=["Companies"])
# app.include_router(screener.router,  prefix="/api/v1/screener",  tags=["Screener"])
# app.include_router(watchlist.router, prefix="/api/v1/watchlist", tags=["Watchlist"])
