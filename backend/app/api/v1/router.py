"""
API v1 — Main Router
Registers all route modules under /api/v1
"""
from fastapi import APIRouter
from app.api.v1.routes import (
    companies, screener, market, auth, watchlist, alerts,
    stripe_routes, ai, portfolio, indices_funds,
    notifications, announcements,
)

api_router = APIRouter()

api_router.include_router(companies.router,      prefix="/companies",      tags=["Companies"])
api_router.include_router(screener.router,       prefix="/screener",       tags=["Screener"])
api_router.include_router(market.router,         prefix="/market",         tags=["Market"])
api_router.include_router(auth.router,           prefix="/auth",           tags=["Auth"])
api_router.include_router(watchlist.router,      prefix="/watchlist",      tags=["Watchlist"])
api_router.include_router(alerts.router,         prefix="/alerts",         tags=["Alerts"])
api_router.include_router(stripe_routes.router,  prefix="/billing",        tags=["Billing"])
api_router.include_router(ai.router,             prefix="/ai",             tags=["AI"])
api_router.include_router(portfolio.router,      prefix="/portfolio",      tags=["Portfolio"])
api_router.include_router(indices_funds.router,  prefix="/market-data",    tags=["Indices & Funds"])
api_router.include_router(notifications.router,  prefix="/notifications",  tags=["Notifications"])
api_router.include_router(announcements.router,  prefix="/announcements",  tags=["Announcements"])
