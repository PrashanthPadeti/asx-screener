"""
Pydantic schemas for the Screener API
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import date, datetime
from enum import Enum


class FilterOperator(str, Enum):
    gt  = "gt"    # greater than
    gte = "gte"   # greater than or equal
    lt  = "lt"    # less than
    lte = "lte"   # less than or equal
    eq  = "eq"    # equal
    neq = "neq"   # not equal
    in_ = "in"    # in list


class ScreenerFilter(BaseModel):
    field:    str
    operator: FilterOperator
    value:    Any   # number, string, bool, or list


class ScreenerRequest(BaseModel):
    filters:    list[ScreenerFilter] = Field(default=[], description="List of filter conditions")
    sort_by:    str                  = Field(default="market_cap", description="Column to sort by")
    sort_dir:   str                  = Field(default="desc", description="asc | desc")
    page:       int                  = Field(default=1, ge=1)
    page_size:  int                  = Field(default=50, ge=1, le=200)

    model_config = {
        "json_schema_extra": {
            "example": {
                "filters": [
                    {"field": "sector",          "operator": "eq",  "value": "Materials"},
                    {"field": "pe_ratio",        "operator": "lte", "value": 15},
                    {"field": "dividend_yield",  "operator": "gte", "value": 3},
                    {"field": "franking_pct",    "operator": "eq",  "value": 100},
                ],
                "sort_by":   "grossed_up_yield",
                "sort_dir":  "desc",
                "page":      1,
                "page_size": 50,
            }
        }
    }


class ScreenerRow(BaseModel):
    """
    One row in the screener results — sourced entirely from screener.universe.

    Percentage/ratio fields are stored as decimal ratios in the DB (0.15 = 15%).
    The frontend multiplies by 100 for display.
    Exceptions (already 0-100 scale): franking_pct, percent_insiders,
    percent_institutions, short_pct, rsi_14, adx_14.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    asx_code:     str
    company_name: str
    sector:       Optional[str]   = None
    industry:     Optional[str]   = None
    stock_type:   Optional[str]   = None
    status:       Optional[str]   = None
    is_reit:      bool            = False
    is_miner:     bool            = False
    is_asx200:    bool            = False
    is_asx300:    bool            = False

    # ── Price ────────────────────────────────────────────────────────────────
    price:          Optional[float] = None
    high_52w:       Optional[float] = None
    low_52w:        Optional[float] = None
    volume:         Optional[float] = None
    avg_volume_20d: Optional[float] = None
    market_cap:     Optional[float] = None   # AUD millions

    # ── Valuation ────────────────────────────────────────────────────────────
    pe_ratio:       Optional[float] = None
    forward_pe:     Optional[float] = None
    price_to_book:  Optional[float] = None
    price_to_sales: Optional[float] = None
    ev_to_ebitda:   Optional[float] = None
    peg_ratio:      Optional[float] = None
    price_to_fcf:   Optional[float] = None
    fcf_yield:      Optional[float] = None   # decimal ratio

    # ── Dividends ────────────────────────────────────────────────────────────
    dividend_yield:           Optional[float] = None   # decimal ratio
    grossed_up_yield:         Optional[float] = None   # decimal ratio
    franking_pct:             Optional[float] = None   # 0–100
    dps_ttm:                  Optional[float] = None   # AUD per share
    payout_ratio:             Optional[float] = None   # decimal ratio
    dividend_consecutive_yrs: Optional[int]   = None
    dividend_cagr_3y:         Optional[float] = None   # decimal ratio

    # ── Profitability ────────────────────────────────────────────────────────
    gross_margin:     Optional[float] = None   # decimal ratio
    ebitda_margin:    Optional[float] = None   # decimal ratio
    net_margin:       Optional[float] = None   # decimal ratio
    operating_margin: Optional[float] = None   # decimal ratio
    roe:              Optional[float] = None   # decimal ratio
    roa:              Optional[float] = None   # decimal ratio
    roce:             Optional[float] = None   # decimal ratio
    avg_roe_3y:       Optional[float] = None   # decimal ratio

    # ── Growth ───────────────────────────────────────────────────────────────
    revenue_growth_1y:       Optional[float] = None   # decimal ratio
    revenue_growth_3y_cagr:  Optional[float] = None   # decimal ratio
    revenue_cagr_5y:         Optional[float] = None   # decimal ratio
    earnings_growth_1y:      Optional[float] = None   # decimal ratio
    eps_growth_3y_cagr:      Optional[float] = None   # decimal ratio
    revenue_growth_yoy_q:    Optional[float] = None   # decimal ratio
    eps_growth_yoy_q:        Optional[float] = None   # decimal ratio
    revenue_growth_hoh:      Optional[float] = None   # decimal ratio ★ ASX unique
    net_income_growth_hoh:   Optional[float] = None   # decimal ratio ★ ASX unique
    eps_growth_hoh:          Optional[float] = None   # decimal ratio ★ ASX unique

    # ── Balance Sheet ────────────────────────────────────────────────────────
    debt_to_equity:      Optional[float] = None
    current_ratio:       Optional[float] = None
    net_debt:            Optional[float] = None   # AUD millions
    total_debt:          Optional[float] = None   # AUD millions
    book_value_per_share:Optional[float] = None   # AUD
    total_assets:        Optional[float] = None   # AUD millions
    total_equity:        Optional[float] = None   # AUD millions
    fcf_fy0:             Optional[float] = None   # AUD millions
    cfo_fy0:             Optional[float] = None   # AUD millions

    # ── Quality Scores ────────────────────────────────────────────────────────
    piotroski_f_score:    Optional[int]   = None   # 0–9
    altman_z_score:       Optional[float] = None
    percent_insiders:     Optional[float] = None   # 0–100
    percent_institutions: Optional[float] = None   # 0–100
    short_pct:            Optional[float] = None   # 0–100

    # ── Technicals ───────────────────────────────────────────────────────────
    rsi_14:       Optional[float] = None   # 0–100
    adx_14:       Optional[float] = None   # 0–100
    macd:         Optional[float] = None
    macd_signal:  Optional[float] = None
    sma_20:       Optional[float] = None
    sma_50:       Optional[float] = None
    sma_200:      Optional[float] = None
    ema_20:       Optional[float] = None
    bb_upper:     Optional[float] = None
    bb_lower:     Optional[float] = None
    atr_14:       Optional[float] = None
    obv:          Optional[float] = None
    volatility_20d: Optional[float] = None   # decimal ratio
    volatility_60d: Optional[float] = None   # decimal ratio
    beta_1y:      Optional[float] = None
    sharpe_1y:    Optional[float] = None

    # ── Returns ──────────────────────────────────────────────────────────────
    return_1w:         Optional[float] = None   # decimal ratio
    return_1m:         Optional[float] = None   # decimal ratio
    return_3m:         Optional[float] = None   # decimal ratio
    return_6m:         Optional[float] = None   # decimal ratio
    return_1y:         Optional[float] = None   # decimal ratio
    return_ytd:        Optional[float] = None   # decimal ratio
    return_3y:         Optional[float] = None   # decimal ratio
    return_5y:         Optional[float] = None   # decimal ratio
    drawdown_from_ath: Optional[float] = None   # decimal ratio (negative)

    # ── Metadata ─────────────────────────────────────────────────────────────
    price_date:         Optional[date]     = None
    universe_built_at:  Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScreenerResponse(BaseModel):
    data:            list[ScreenerRow]
    total:           int
    page:            int
    page_size:       int
    total_pages:     int
    filters_applied: int
