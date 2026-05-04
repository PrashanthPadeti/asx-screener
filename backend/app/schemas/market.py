"""
Pydantic schemas for the Market summary API
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class MarketSummary(BaseModel):
    """Aggregate stats across screener.universe for the homepage."""
    total_stocks: int
    asx200_stocks: int
    stocks_with_dividends: int
    avg_dividend_yield: Optional[float] = None   # decimal ratio (0.04 = 4%)
    median_pe: Optional[float] = None
    total_market_cap_bn: Optional[float] = None  # AUD billions
    universe_built_at: Optional[datetime] = None


class MoverStock(BaseModel):
    asx_code: str
    company_name: str
    sector: Optional[str] = None
    price: Optional[float] = None
    return_1w: Optional[float] = None   # decimal ratio
    return_1m: Optional[float] = None   # decimal ratio
    market_cap: Optional[float] = None  # AUD millions


class MoversResponse(BaseModel):
    gainers: list[MoverStock]
    losers: list[MoverStock]
    period: str  # "1w"


class SectorStat(BaseModel):
    sector: str
    stock_count: int
    avg_pe: Optional[float] = None
    avg_dividend_yield: Optional[float] = None   # decimal ratio
    avg_return_1y: Optional[float] = None        # decimal ratio
    total_market_cap_bn: Optional[float] = None  # AUD billions


class SectorsResponse(BaseModel):
    sectors: list[SectorStat]


# ── Dashboard schemas ─────────────────────────────────────────────────────────

class IndexSnapshot(BaseModel):
    stock_count: int
    gainers: int
    losers: int
    unchanged: int
    avg_return_1w: Optional[float] = None
    total_market_cap_bn: Optional[float] = None


class DashboardStock(BaseModel):
    asx_code: str
    company_name: str
    sector: Optional[str] = None
    price: Optional[float] = None
    return_1w: Optional[float] = None
    market_cap: Optional[float] = None


class ActiveStock(DashboardStock):
    volume: Optional[int] = None
    avg_volume_20d: Optional[int] = None


class ShortedStock(DashboardStock):
    short_pct: Optional[float] = None


class SectorHeatmapItem(BaseModel):
    sector: str
    stock_count: int
    avg_return_1w: Optional[float] = None
    total_market_cap_bn: Optional[float] = None


class ExDivStock(BaseModel):
    asx_code: str
    company_name: str
    ex_div_date: Optional[str] = None
    pay_date: Optional[str] = None
    dps_ttm: Optional[float] = None
    dividend_yield: Optional[float] = None
    franking_pct: Optional[float] = None


class MarketDashboard(BaseModel):
    asx200: IndexSnapshot
    asx300: IndexSnapshot
    sector_heatmap: list[SectorHeatmapItem]
    top_gainers: list[DashboardStock]
    top_losers: list[DashboardStock]
    most_active: list[ActiveStock]
    most_shorted: list[ShortedStock]
    upcoming_exdiv: list[ExDivStock]
    period: str = "1w"
    universe_built_at: Optional[datetime] = None
