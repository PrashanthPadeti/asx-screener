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
    return_1d: Optional[float] = None   # decimal ratio
    return_1w: Optional[float] = None   # decimal ratio
    return_1m: Optional[float] = None   # decimal ratio
    return_3m: Optional[float] = None   # decimal ratio
    market_cap: Optional[float] = None  # AUD millions
    period_high: Optional[float] = None # period high price
    period_low: Optional[float] = None  # period low price


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


class VolumePressureStock(DashboardStock):
    volume: Optional[int] = None
    avg_volume_20d: Optional[int] = None
    volume_ratio: Optional[float] = None   # volume / avg_volume_20d


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
    heavy_buying: list[VolumePressureStock]
    heavy_selling: list[VolumePressureStock]
    upcoming_exdiv: list[ExDivStock]
    period: str = "1w"
    universe_built_at: Optional[datetime] = None


class VolumeActivityResponse(BaseModel):
    most_active:   list[ActiveStock]
    heavy_buying:  list[VolumePressureStock]
    heavy_selling: list[VolumePressureStock]
    cap_tier:      Optional[str] = None   # echoed back, None = 'all'


# ── Performance Heatmap schemas ───────────────────────────────────────────────

class HeatmapRow(BaseModel):
    """One stock row in the rolling performance heatmap."""
    asx_code:     str
    company_name: str
    sector:       Optional[str]   = None
    industry:     Optional[str]   = None
    price:        Optional[float] = None   # current price AUD
    market_cap:   Optional[float] = None   # AUD (raw)
    p1:           Optional[float] = None   # most-recent period return (decimal)
    p2:           Optional[float] = None
    p3:           Optional[float] = None
    p4:           Optional[float] = None
    p5:           Optional[float] = None   # oldest of the 5 periods


class HeatmapResponse(BaseModel):
    rows:   list[HeatmapRow]
    labels: list[str]   # 5 human-readable period labels, newest first
    mode:   str         # "days" | "weeks"
    total:  int
