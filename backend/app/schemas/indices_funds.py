"""
Pydantic schemas for Indices and ETF/Managed Funds APIs.
"""
from pydantic import BaseModel
from typing import Optional


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


# ── Index Detail ──────────────────────────────────────────────────────────────

class IndexConstituentRow(BaseModel):
    asx_code: str
    company_name: str
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    weight_pct: Optional[float] = None
    price: Optional[float] = None
    return_1d: Optional[float] = None
    return_1y: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    franking_pct: Optional[float] = None


class IndexSectorBreakdown(BaseModel):
    sector: str
    count: int
    weight_pct: float
    market_cap_bn: float


class IndexPrimaryETF(BaseModel):
    asx_code: Optional[str] = None
    name: Optional[str] = None
    mer_pct: Optional[float] = None


class IndexDetailResponse(BaseModel):
    index_code: str
    display_name: str
    description: Optional[str] = None
    eligibility: Optional[str] = None
    methodology: Optional[str] = None
    rebalance_freq: Optional[str] = None
    market_coverage: Optional[str] = None
    primary_etf: Optional[IndexPrimaryETF] = None
    price: Optional[IndexPrice] = None
    constituents: list[IndexConstituentRow] = []
    total_market_cap_bn: Optional[float] = None
    constituent_count: int = 0
    sector_breakdown: list[IndexSectorBreakdown] = []


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
