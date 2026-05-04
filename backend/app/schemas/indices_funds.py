"""
Pydantic schemas for Indices and ETF/Managed Funds APIs.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import date


# ── Indices ───────────────────────────────────────────────────────────────────

class IndexMeta(BaseModel):
    index_code: str
    display_name: str
    description: Optional[str] = None
    constituent_count: Optional[int] = None
    rebalance_freq: Optional[str] = None


class IndexPrice(BaseModel):
    index_code: str
    display_name: str
    price_date: Optional[str] = None
    close_price: Optional[float] = None
    return_1d: Optional[float] = None
    return_1w: Optional[float] = None
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    return_1y: Optional[float] = None
    return_ytd: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None


class IndicesResponse(BaseModel):
    indices: list[IndexPrice]
    as_of: Optional[str] = None


# ── ETF / Managed Funds ───────────────────────────────────────────────────────

class FundRow(BaseModel):
    asx_code: str
    fund_name: str
    fund_type: str          # 'ETF' | 'LIC' | 'MANAGED'
    asset_class: Optional[str] = None
    index_tracked: Optional[str] = None
    fund_manager: Optional[str] = None
    mer_pct: Optional[float] = None
    funds_under_mgmt_bn: Optional[float] = None
    distribution_freq: Optional[str] = None
    is_hedged: Optional[bool] = None
    # Latest price data
    close_price: Optional[float] = None
    return_1d: Optional[float] = None
    return_1w: Optional[float] = None
    return_1m: Optional[float] = None
    return_1y: Optional[float] = None
    return_ytd: Optional[float] = None
    distribution_yield: Optional[float] = None
    nav_discount_pct: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    price_date: Optional[str] = None


class FundsResponse(BaseModel):
    funds: list[FundRow]
    total: int
    as_of: Optional[str] = None
