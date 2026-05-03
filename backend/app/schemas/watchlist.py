"""
ASX Screener — Watchlist Pydantic Schemas
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class WatchlistCreate(BaseModel):
    name: str
    description: Optional[str] = None


class WatchlistUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class WatchlistAddStock(BaseModel):
    asx_code: str
    notes: Optional[str] = None
    target_price: Optional[float] = None


class WatchlistItemOut(BaseModel):
    asx_code:     str
    added_at:     Optional[datetime] = None
    notes:        Optional[str]      = None
    target_price: Optional[float]    = None
    sort_order:   int                = 0

    model_config = {"from_attributes": True}


class WatchlistSummary(BaseModel):
    id:          str
    name:        str
    description: Optional[str]      = None
    item_count:  int                 = 0
    created_at:  Optional[datetime]  = None

    model_config = {"from_attributes": True}


class WatchlistDetail(WatchlistSummary):
    """Watchlist with the list of ASX codes (live data fetched separately via /screener/batch)."""
    codes: list[str] = []


class WatchlistsResponse(BaseModel):
    watchlists: list[WatchlistSummary]
