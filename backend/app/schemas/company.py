"""
Pydantic schemas for market.companies and company detail sub-resources.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class CompanyBase(BaseModel):
    asx_code: str
    company_name: str
    gics_sector: Optional[str] = None
    gics_industry_group: Optional[str] = None
    is_reit: bool = False
    is_miner: bool = False
    status: str = "active"


class CompanyListItem(CompanyBase):
    """Lightweight schema for screener/search results."""
    is_asx200: bool = False
    listing_date: Optional[date] = None

    model_config = {"from_attributes": True}


class CompanyDetail(CompanyBase):
    """Full company detail for company page."""
    isin: Optional[str] = None
    short_name: Optional[str] = None
    gics_industry: Optional[str] = None
    gics_sub_industry: Optional[str] = None
    asx_sector: Optional[str] = None
    company_type: Optional[str] = None

    is_bank: bool = False
    is_insurer: bool = False
    is_asx20: bool = False
    is_asx50: bool = False
    is_asx100: bool = False
    is_asx200: bool = False
    is_asx300: bool = False
    is_all_ords: bool = False

    listing_date: Optional[date] = None
    ipo_price: Optional[float] = None
    financial_year_end: Optional[int] = None
    shares_outstanding: Optional[int] = None
    shares_float: Optional[int] = None

    website: Optional[str] = None
    abn: Optional[str] = None
    domicile: Optional[str] = None
    state: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    employee_count: Optional[int] = None

    primary_commodity: Optional[str] = None
    secondary_commodity: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CompanySearchResult(BaseModel):
    """Minimal schema for autocomplete search."""
    asx_code: str
    company_name: str
    gics_sector: Optional[str] = None
    is_reit: bool = False
    is_miner: bool = False

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    data: list[CompanyListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Company sub-resource schemas ──────────────────────────────────────────────

class CompanyOverview(BaseModel):
    """
    All screener.universe metrics for one company.
    Used by Overview and Technicals tabs on the company detail page.

    Decimal ratio fields (stored as 0.15 = 15%):
        dividend_yield, grossed_up_yield, payout_ratio, dividend_cagr_3y,
        gross_margin, ebitda_margin, net_margin, operating_margin,
        roe, roa, roce, avg_roe_3y, fcf_yield,
        revenue_growth_*, earnings_growth_*, eps_growth_*,
        return_*, drawdown_from_ath, volatility_*
    Already 0-100 fields:
        franking_pct, short_pct, percent_insiders, percent_institutions, rsi_14, adx_14
    """
    # ── Price ─────────────────────────────────────────────────────────────────
    price: Optional[float] = None
    price_date: Optional[date] = None
    market_cap: Optional[float] = None
    volume: Optional[float] = None
    avg_volume_20d: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None

    # ── Valuation ──────────────────────────────────────────────────────────────
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    price_to_fcf: Optional[float] = None
    ev: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    ev_to_ebit: Optional[float] = None
    ev_to_revenue: Optional[float] = None
    graham_number: Optional[float] = None
    fcf_yield: Optional[float] = None           # decimal ratio

    # ── Dividends ──────────────────────────────────────────────────────────────
    dividend_yield: Optional[float] = None      # decimal ratio
    grossed_up_yield: Optional[float] = None    # decimal ratio
    franking_pct: Optional[float] = None        # 0-100
    dps_ttm: Optional[float] = None
    dps_fy0: Optional[float] = None
    payout_ratio: Optional[float] = None        # decimal ratio
    ex_div_date: Optional[date] = None
    dividend_consecutive_yrs: Optional[int] = None
    dividend_cagr_3y: Optional[float] = None    # decimal ratio

    # ── Profitability (all decimal ratios) ─────────────────────────────────────
    gross_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None
    net_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    roce: Optional[float] = None
    avg_roe_3y: Optional[float] = None

    # ── Income Statement snapshot ──────────────────────────────────────────────
    revenue_ttm: Optional[float] = None         # AUD full dollars
    ebitda_ttm: Optional[float] = None
    net_profit_ttm: Optional[float] = None
    revenue_fy0: Optional[float] = None
    revenue_fy1: Optional[float] = None
    revenue_fy2: Optional[float] = None
    net_profit_fy0: Optional[float] = None
    net_profit_fy1: Optional[float] = None
    eps_fy0: Optional[float] = None
    eps_fy1: Optional[float] = None

    # ── Balance Sheet ──────────────────────────────────────────────────────────
    total_assets: Optional[float] = None
    total_equity: Optional[float] = None
    total_debt: Optional[float] = None
    net_debt: Optional[float] = None
    cash: Optional[float] = None
    book_value_per_share: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None

    # ── Cash Flow ──────────────────────────────────────────────────────────────
    cfo_fy0: Optional[float] = None
    capex_fy0: Optional[float] = None
    fcf_fy0: Optional[float] = None

    # ── Growth (all decimal ratios) ────────────────────────────────────────────
    revenue_growth_1y: Optional[float] = None
    revenue_growth_3y_cagr: Optional[float] = None
    revenue_cagr_5y: Optional[float] = None
    earnings_growth_1y: Optional[float] = None
    eps_growth_3y_cagr: Optional[float] = None
    revenue_growth_yoy_q: Optional[float] = None
    eps_growth_yoy_q: Optional[float] = None
    revenue_growth_hoh: Optional[float] = None
    net_income_growth_hoh: Optional[float] = None
    eps_growth_hoh: Optional[float] = None

    # ── Quality & Ownership ────────────────────────────────────────────────────
    piotroski_f_score: Optional[int] = None     # 0–9
    altman_z_score: Optional[float] = None
    short_pct: Optional[float] = None           # 0-100
    percent_insiders: Optional[float] = None    # 0-100
    percent_institutions: Optional[float] = None  # 0-100

    # ── Analyst ────────────────────────────────────────────────────────────────
    analyst_rating: Optional[str] = None
    analyst_target_price: Optional[float] = None
    analyst_upside: Optional[float] = None      # decimal ratio

    # ── Returns (all decimal ratios) ───────────────────────────────────────────
    return_1w: Optional[float] = None
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    return_1y: Optional[float] = None
    return_ytd: Optional[float] = None
    return_3y: Optional[float] = None
    return_5y: Optional[float] = None
    drawdown_from_ath: Optional[float] = None

    # ── Technicals ─────────────────────────────────────────────────────────────
    rsi_14: Optional[float] = None              # 0-100
    adx_14: Optional[float] = None              # 0-100
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_20: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    atr_14: Optional[float] = None
    obv: Optional[float] = None
    volatility_20d: Optional[float] = None      # decimal ratio
    volatility_60d: Optional[float] = None      # decimal ratio
    beta_1y: Optional[float] = None
    sharpe_1y: Optional[float] = None
    momentum_3m: Optional[float] = None
    momentum_6m: Optional[float] = None

    model_config = {"from_attributes": True}


class AnnualFinancialsRow(BaseModel):
    """One fiscal year of combined P&L + balance sheet + cashflow."""
    fiscal_year: int
    period_end_date: Optional[date] = None

    # P&L (AUD millions from financials.annual_pnl)
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    ebitda: Optional[float] = None
    ebit: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None
    dps: Optional[float] = None

    # Margins (decimal ratios — stored in annual_pnl)
    gpm: Optional[float] = None
    ebitda_margin: Optional[float] = None
    npm: Optional[float] = None

    # Balance Sheet (AUD millions from annual_balance_sheet)
    total_assets: Optional[float] = None
    total_equity: Optional[float] = None
    total_debt: Optional[float] = None
    net_debt: Optional[float] = None
    cash_equivalents: Optional[float] = None
    book_value_per_share: Optional[float] = None
    debt_to_equity: Optional[float] = None

    # Cash Flow (AUD millions from annual_cashflow)
    cfo: Optional[float] = None
    capex: Optional[float] = None
    fcf: Optional[float] = None

    model_config = {"from_attributes": True}


class FinancialsResponse(BaseModel):
    asx_code: str
    years: list[AnnualFinancialsRow]


class PricePoint(BaseModel):
    date: str                       # ISO date string "YYYY-MM-DD"
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[int] = None


class PricesResponse(BaseModel):
    asx_code: str
    period: str
    data: list[PricePoint]
