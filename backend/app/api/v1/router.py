"""
API v1 — Main Router
Registers all route modules under /api/v1
"""
from fastapi import APIRouter
from app.api.v1.routes import companies, screener, market, auth

api_router = APIRouter()

api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])
api_router.include_router(screener.router,  prefix="/screener",  tags=["Screener"])
api_router.include_router(market.router,    prefix="/market",    tags=["Market"])
api_router.include_router(auth.router,      prefix="/auth",      tags=["Auth"])

# Future routers (uncomment as built):
# from app.api.v1.routes import watchlist, portfolio, alerts
# api_router.include_router(watchlist.router, prefix="/watchlist", tags=["Watchlist"])
