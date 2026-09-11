"""
Pydantic schemas for the Screener API
"""
from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
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


class QueryScreenerRequest(BaseModel):
    """Request body for the SQL-like query mode endpoint."""
    query:     str  = Field(..., min_length=1, max_length=4000,
                            description="SQL-like WHERE expression, e.g. 'roe > 10 AND (roce > 10 OR roic > 10)'")
    sort_by:   str  = Field(default="market_cap", description="Column to sort results by")
    sort_dir:  Literal["asc", "desc"] = Field(default="desc", description="Sort direction")
    page:      int  = Field(default=1, ge=1)
    page_size: int  = Field(default=50, ge=1, le=200)

    model_config = {
        "json_schema_extra": {
            "example": {
                "query":     "roe > 15 AND roce > 15 AND (revenue_cagr_5y > 10 OR earnings_growth_1y > 10)",
                "sort_by":   "market_cap",
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
    roic:             Optional[float] = None   # decimal ratio
    avg_roe_3y:       Optional[float] = None   # decimal ratio
    asset_turnover:   Optional[float] = None   # ratio
    ocf_margin:       Optional[float] = None   # decimal ratio
    fcf_margin:       Optional[float] = None   # decimal ratio
    capex_intensity:  Optional[float] = None   # decimal ratio

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
    ebitda_growth_1y:        Optional[float] = None   # decimal ratio
    fcf_growth_1y:           Optional[float] = None   # decimal ratio
    eps_growth_1y:           Optional[float] = None   # decimal ratio
    revenue_cagr_7y:         Optional[float] = None   # decimal ratio
    revenue_cagr_10y:        Optional[float] = None   # decimal ratio
    net_income_cagr_5y:      Optional[float] = None   # decimal ratio
    eps_cagr_5y:             Optional[float] = None   # decimal ratio
    ebitda_cagr_3y:          Optional[float] = None   # decimal ratio
    ebitda_cagr_5y:          Optional[float] = None   # decimal ratio
    fcf_cagr_3y:             Optional[float] = None   # decimal ratio
    fcf_cagr_5y:             Optional[float] = None   # decimal ratio
    dividend_cagr_5y:        Optional[float] = None   # decimal ratio
    bvps_cagr_3y:            Optional[float] = None   # decimal ratio
    bvps_cagr_5y:            Optional[float] = None   # decimal ratio

    # ── Rolling Averages ─────────────────────────────────────────────────────
    avg_roe_5y:              Optional[float] = None   # decimal ratio
    avg_roa_3y:              Optional[float] = None   # decimal ratio
    avg_roa_5y:              Optional[float] = None   # decimal ratio
    avg_roce_3y:             Optional[float] = None   # decimal ratio
    avg_roce_5y:             Optional[float] = None   # decimal ratio
    avg_gross_margin_3y:     Optional[float] = None   # decimal ratio
    avg_gross_margin_5y:     Optional[float] = None   # decimal ratio
    avg_ebitda_margin_3y:    Optional[float] = None   # decimal ratio
    avg_ebitda_margin_5y:    Optional[float] = None   # decimal ratio
    avg_operating_margin_3y: Optional[float] = None   # decimal ratio
    avg_operating_margin_5y: Optional[float] = None   # decimal ratio
    avg_net_margin_3y:       Optional[float] = None   # decimal ratio
    avg_net_margin_5y:       Optional[float] = None   # decimal ratio
    avg_eps_growth_3y:       Optional[float] = None   # decimal ratio
    avg_eps_growth_5y:       Optional[float] = None   # decimal ratio

    # ── Tier 3: Inline calculations ──────────────────────────────────────────
    price_to_52w_high:   Optional[float] = None   # price / 52w high (1.0 = at high)
    price_to_52w_low:    Optional[float] = None   # price / 52w low  (1.0 = at low)
    fcf_per_share:       Optional[float] = None   # AUD per share
    ocf_per_share:       Optional[float] = None   # AUD per share
    revenue_per_share:   Optional[float] = None   # AUD per share
    working_capital:     Optional[float] = None   # AUD millions

    # ── Balance Sheet ────────────────────────────────────────────────────────
    debt_to_equity:      Optional[float] = None
    current_ratio:       Optional[float] = None
    debt_to_assets:      Optional[float] = None
    lt_debt_to_capital:  Optional[float] = None
    net_debt_to_ebitda:  Optional[float] = None   # ratio (x)
    interest_coverage:   Optional[float] = None   # ratio (x)
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
    rsi_21:       Optional[float] = None   # 0–100
    adx_14:       Optional[float] = None   # 0–100
    macd:         Optional[float] = None
    macd_signal:  Optional[float] = None
    sma_20:       Optional[float] = None
    sma_50:       Optional[float] = None
    sma_200:      Optional[float] = None
    ema_20:       Optional[float] = None
    bb_upper:     Optional[float] = None
    bb_lower:     Optional[float] = None
    bb_pct:       Optional[float] = None   # Bollinger %B (0=at lower, 1=at upper)
    atr_14:       Optional[float] = None
    obv:          Optional[float] = None
    stoch_k:      Optional[float] = None   # Stochastic %K
    stoch_d:      Optional[float] = None   # Stochastic %D
    dma50_ratio:  Optional[float] = None   # price / SMA50
    dma200_ratio: Optional[float] = None   # price / SMA200
    relative_volume: Optional[float] = None  # volume / avg_volume_20d
    volatility_20d: Optional[float] = None   # decimal ratio
    volatility_60d: Optional[float] = None   # decimal ratio
    beta_1y:      Optional[float] = None
    sharpe_1y:    Optional[float] = None

    # ── Technical signals (boolean) ───────────────────────────────────────────
    above_sma50:        Optional[bool] = None
    above_sma200:       Optional[bool] = None
    golden_cross:       Optional[bool] = None   # SMA50 crossed above SMA200
    death_cross:        Optional[bool] = None   # SMA50 crossed below SMA200
    new_52w_high:       Optional[bool] = None
    new_52w_low:        Optional[bool] = None
    rsi_overbought:     Optional[bool] = None   # RSI14 >= 70
    rsi_oversold:       Optional[bool] = None   # RSI14 <= 30
    macd_bullish_cross: Optional[bool] = None
    macd_bearish_cross: Optional[bool] = None

    # ── Returns ──────────────────────────────────────────────────────────────
    return_1w:         Optional[float] = None   # decimal ratio
    return_1m:         Optional[float] = None   # decimal ratio
    return_3m:         Optional[float] = None   # decimal ratio
    return_6m:         Optional[float] = None   # decimal ratio
    return_1y:         Optional[float] = None   # decimal ratio
    return_ytd:        Optional[float] = None   # decimal ratio
    return_2y:         Optional[float] = None   # decimal ratio
    return_3y:         Optional[float] = None   # decimal ratio
    return_4y:         Optional[float] = None   # decimal ratio
    return_5y:         Optional[float] = None   # decimal ratio
    return_6y:         Optional[float] = None   # decimal ratio
    return_7y:         Optional[float] = None   # decimal ratio
    return_8y:         Optional[float] = None   # decimal ratio
    return_9y:         Optional[float] = None   # decimal ratio
    return_10y:        Optional[float] = None   # decimal ratio
    drawdown_from_ath: Optional[float] = None   # decimal ratio (negative)

    # ── Selected by the query but previously absent here, so dropped in the
    #    response and rendered as "—" in the UI ────────────────────────────────
    avg_roic_3y:            Optional[float] = None   # decimal ratio
    avg_roic_5y:            Optional[float] = None   # decimal ratio
    earnings_growth_3y_cagr: Optional[float] = None  # decimal ratio
    eps_fy0:                Optional[float] = None   # AUD

    # ── Multibagger potential (MULTIBAGGER_POTENTIAL_V1) ─────────────────────
    # Strength of compounding CHARACTERISTICS, never a prediction of returns.
    # Nullable on purpose: roughly a quarter of the universe lacks the history
    # to earn a score, and a manufactured value would be worse than none.
    multibagger_potential_score: Optional[float] = None
    mb_valid_weight_pct:         Optional[float] = None   # data coverage, 0-100
    multibagger_version:         Optional[str]   = None   # e.g. MULTIBAGGER_POTENTIAL_V1

    # ── Factor Scores (percentile 0–100, NOT decimal ratios) ─────────────────
    composite_score:   Optional[float] = None
    value_score:       Optional[float] = None
    quality_score:     Optional[float] = None
    growth_score:      Optional[float] = None
    momentum_score:    Optional[float] = None
    income_score:      Optional[float] = None

    # ── Metadata ─────────────────────────────────────────────────────────────
    price_date:         Optional[date]     = None
    universe_built_at:  Optional[datetime] = None

    # ── Why a governed field is null ─────────────────────────────────────────
    # Sparse, and the absence is the signal: a metric with no entry here was
    # applicable, so the payload stays proportional to the problem rather than
    # to the column count.
    #
    # A null governed field is never evidence. Without an entry a client cannot
    # tell "this bank has no meaningful current ratio" from "the dividend feed
    # is stale" from "nobody has computed this yet", and all three would
    # otherwise render as the same dash — or, worse, as zero. Each entry
    # carries state, cause and reason so the client renders the right one.
    #
    # The forensic observed value is deliberately not here; it is stripped at
    # projection, because a frontend that finds a number will display it.
    metric_states: dict[str, dict] = {}

    model_config = {"from_attributes": True}


class OrderingExclusion(BaseModel):
    """Why a screen member is absent from this ordering.

    Returned as a count by default; identifiers and reasons only for a small
    result set or on request, because a page carrying thousands of exclusions
    is payload nobody reads.
    """

    metric:  str
    count:   int
    reasons: dict[str, int] = {}             # cause -> how many
    codes:   Optional[list[str]] = None      # populated only when small


class ScreenerResponse(BaseModel):
    data:            list[ScreenerRow]
    total:           int
    page:            int
    page_size:       int
    total_pages:     int
    filters_applied: int
    is_capped:       bool          = False   # True when free-tier 500-row limit applied
    free_limit:      Optional[int] = None    # 500 for free users, None otherwise

    # ── Three-valued result metadata ─────────────────────────────────────────
    # total is screen membership. ranked_total is the subset with a valid
    # observation for the requested ordering. They diverge only when the
    # ordering is governed and some members cannot participate — a company
    # with a source-unhealthy dividend yield belongs in the universe and
    # cannot be placed in a yield ranking, and collapsing those into one
    # number forces the client to guess which question it answered.
    ranked_total:           Optional[int] = None
    excluded_from_ordering: Optional[OrderingExclusion] = None

    # An opaque identifier for the logical contract this result was computed
    # under — model version plus source-health state, over whatever set of
    # physical runs happened to be coherent. Deliberately not one run id:
    # presenting an arbitrary shard's id as though it explained the whole
    # result set would be false the first time sharding appeared.
    #
    # It means exactly one thing:
    #
    #     Any governed values in this response were interpreted under this
    #     logical contract.
    #
    # It does NOT mean the snapshot determined universe membership, and a
    # present snapshot is not licence to add WHERE compute_run_id IN (...) to
    # the query. An ungoverned screen — sector = Financials ORDER BY
    # market_cap — selects every company satisfying that ordinary question,
    # including one newly listed and not yet through a factor-model run, and
    # then suppresses that row's governed fields with a stated cause. Scoping
    # membership to the compute run instead would silently delete the new
    # listing from results it belongs in, trading discovery completeness for
    # a correctness guarantee that projection already provides.
    #
    # So a non-null snapshot on an ungoverned response is expected after
    # migration, and explains the governed fields inside the rows rather than
    # which rows there are. Null means no validated contract was resolvable,
    # in which case every governed field in every row has failed closed.
    snapshot:     Optional[str] = None
    #: Diagnostic only. The physical runs behind the snapshot.
    run_ids:      Optional[list[int]] = None
