"""
API v1 — Main Router
Registers all route modules under /api/v1
"""
from fastapi import APIRouter
from app.api.v1.routes import companies

api_router = APIRouter()

api_router.include_router(companies.router, prefix="/companies", tags=["Companies"])

# Future routers (uncomment as built):
# from app.api.v1.routes import screener, auth, watchlist, portfolio, alerts
# api_router.include_router(auth.router,      prefix="/auth",      tags=["Auth"])
# api_router.include_router(screener.router,  prefix="/screener",  tags=["Screener"])
# api_router.include_router(watchlist.router, prefix="/watchlist", tags=["Watchlist"])
