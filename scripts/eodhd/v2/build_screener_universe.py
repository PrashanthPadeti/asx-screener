"""
Build Screener Universe — Golden Record
========================================
Builds screener.universe from all transform-layer and compute-layer tables.

One denormalised row per stock, covering:
  - Identity & classification  (market.companies_current)
  - Price & market cap         (market.daily_prices latest close +
                                market.valuation_snapshot)
  - Valuation ratios           (market.valuation_snapshot)
  - Dividends                  (market.dividends latest + valuation_snapshot)
  - Profitability / margins    (market.computed_metrics preferred,
                                market.valuation_snapshot fallback)
  - Financials FY0/FY1         (financials.annual_pnl + balance_sheet + cashflow)
  - Returns / momentum         (market.monthly_metrics — latest month)
  - Technicals                 (market.monthly_metrics — latest month)
  - Multi-year metrics         (market.yearly_metrics  — latest FY)
  - Latest-quarter growth      (market.quarterly_metrics — latest quarter)
  - Analyst ratings            (market.analyst_ratings)
  - Shares / ownership         (staging.shares_stats)

COALESCE priority for overlapping fields:
  market.computed_metrics  (daily, freshest)
  market.yearly_metrics    (annual compute, thorough)
  market.valuation_snapshot (EODHD snapshot, weekly refresh)

Run after all compute engines complete.

Usage:
    python scripts/eodhd/v2/build_screener_universe.py
    python scripts/eodhd/v2/build_screener_universe.py --codes BHP CBA
"""

import logging
import os
import argparse
from datetime import date

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


UPSERT_SQL = """
INSERT INTO screener.universe (
    -- ── Identity ─────────────────────────────────────────────────────────────
    asx_code, company_name, sector, industry_group, industry, sub_industry,
    stock_type, status, fiscal_year_end_month,
    is_reit, is_miner,
    is_asx20, is_asx50, is_asx100, is_asx200, is_asx300, is_all_ords,
    isin, website, description,

    -- ── Price ────────────────────────────────────────────────────────────────
    price, price_date, open, volume, avg_volume_20d, market_cap,
    high_52w, low_52w,

    -- ── Valuation ratios (from valuation_snapshot) ───────────────────────────
    pe_ratio, forward_pe, peg_ratio, price_to_book, price_to_sales,
    ev, ev_to_ebitda, ev_to_revenue,

    -- ── Dividends ────────────────────────────────────────────────────────────
    dividend_yield, dps_ttm, ex_div_date, franking_pct,

    -- ── Profitability (computed_metrics → yearly_metrics → valuation_snapshot)
    revenue_ttm, gross_profit_ttm, ebitda_ttm,
    gross_margin, ebitda_margin, net_margin, operating_margin,
    roe, roa, roce,
    grossed_up_yield, fcf_yield,

    -- ── EPS ──────────────────────────────────────────────────────────────────
    eps_fy0, eps_fy1,

    -- ── Income Statement FY0 / FY1 ───────────────────────────────────────────
    revenue_fy0, revenue_fy1,
    ebitda_fy0, ebitda_fy1,
    net_profit_fy0, net_profit_fy1,

    -- ── Balance Sheet (latest FY) ─────────────────────────────────────────────
    total_assets, total_equity, total_debt, net_debt, cash,
    book_value_per_share, debt_to_equity, current_ratio,

    -- ── Cash Flow (latest FY) ────────────────────────────────────────────────
    cfo_fy0, capex_fy0, fcf_fy0,

    -- ── Growth rates (computed_metrics → yearly_metrics) ─────────────────────
    revenue_growth_1y, revenue_growth_3y_cagr,
    earnings_growth_1y, earnings_growth_3y_cagr,

    -- ── Returns (weekly + monthly) ───────────────────────────────────────────
    return_1w,
    return_1m, return_3m, return_6m, return_1y, return_ytd,
    momentum_3m, momentum_6m, momentum_12m,

    -- ── Volatility & risk ────────────────────────────────────────────────────
    volatility_20d, volatility_60d,
    sharpe_1y, drawdown_from_ath,
    beta_1y,

    -- ── Technicals (daily preferred; weekly/monthly fallback) ────────────────
    rsi_14, macd, macd_signal,
    sma_20, sma_50, sma_200, ema_20,
    bb_upper, bb_lower, atr_14, adx_14, obv,

    -- ── Multi-year quality & CAGR (from yearly_metrics — latest FY) ──────────
    piotroski_f_score, altman_z_score,
    revenue_cagr_5y, eps_growth_3y_cagr,
    avg_roe_3y,
    dividend_cagr_3y, dividend_consecutive_yrs,
    return_3y, return_5y, return_7y, return_10y, return_15y,

    -- ── Latest-quarter YoY growth (from quarterly_metrics) ───────────────────
    revenue_growth_yoy_q, eps_growth_yoy_q, net_income_growth_yoy_q,

    -- ── Half-yearly HoH growth (from halfyearly_metrics — latest half) ───────
    revenue_growth_hoh, net_income_growth_hoh, eps_growth_hoh,

    -- ── Analyst ──────────────────────────────────────────────────────────────
    analyst_rating, analyst_target_price,
    analyst_strong_buy, analyst_buy, analyst_hold, analyst_sell, analyst_strong_sell,

    -- ── Short interest (ASIC) ────────────────────────────────────────────────
    short_pct, short_position_shares,

    -- ── Shares ───────────────────────────────────────────────────────────────
    shares_outstanding,

    universe_built_at
)
SELECT
    -- ── Identity ─────────────────────────────────────────────────────────────
    c.asx_code,
    c.company_name,
    c.gics_sector,
    c.gics_industry_group,
    c.gics_industry,
    c.gics_sub_industry,
    c.company_type,
    c.status,
    c.fiscal_year_end_month,
    c.is_reit,
    c.is_miner,
    c.is_asx20,  c.is_asx50,  c.is_asx100,
    c.is_asx200, c.is_asx300, c.is_all_ords,
    c.isin,
    c.website,
    c.description,

    -- ── Price (latest close + 52w range) ─────────────────────────────────────
    dp.close          AS price,
    dp.price_date     AS price_date,
    dp.open           AS open,
    dp.volume         AS volume,
    dp.avg_volume_20d AS avg_volume_20d,
    vs.market_cap,
    dp.high_52w,
    dp.low_52w,

    -- ── Valuation ratios ─────────────────────────────────────────────────────
    vs.pe_ratio,
    vs.forward_pe,
    vs.peg_ratio,
    vs.price_to_book,
    vs.price_to_sales,
    vs.enterprise_value     AS ev,
    vs.ev_to_ebitda,
    vs.ev_to_revenue,

    -- ── Dividends ────────────────────────────────────────────────────────────
    vs.dividend_yield,
    vs.dividend_per_share   AS dps_ttm,
    div_latest.ex_date,
    div_latest.franking_pct,

    -- ── Profitability TTM ─────────────────────────────────────────────────────
    -- Priority: computed_metrics (daily) → valuation_snapshot (weekly)
    vs.revenue_ttm,
    vs.gross_profit_ttm,
    vs.ebitda_ttm,
    COALESCE(cm.gpm,           NULL)                         AS gross_margin,
    COALESCE(cm.ebitda_margin, NULL)                         AS ebitda_margin,
    COALESCE(cm.npm,           vs.profit_margin)             AS net_margin,
    COALESCE(cm.opm,           vs.operating_margin)          AS operating_margin,
    COALESCE(cm.roe,  ym.roe,  vs.roe_ttm)                  AS roe,
    COALESCE(cm.roa,  ym.roa,  vs.roa_ttm)                  AS roa,
    COALESCE(cm.roce, ym.roce)                               AS roce,
    COALESCE(cm.grossed_up_yield, ym.franked_yield)          AS grossed_up_yield,
    COALESCE(cm.fcf_yield,        ym.fcf_yield)              AS fcf_yield,

    -- ── EPS ──────────────────────────────────────────────────────────────────
    pnl0.eps        AS eps_fy0,
    pnl1.eps        AS eps_fy1,

    -- ── Income Statement FY0 / FY1 ───────────────────────────────────────────
    pnl0.revenue    AS revenue_fy0,
    pnl1.revenue    AS revenue_fy1,
    pnl0.ebitda     AS ebitda_fy0,
    pnl1.ebitda     AS ebitda_fy1,
    pnl0.net_profit AS net_profit_fy0,
    pnl1.net_profit AS net_profit_fy1,

    -- ── Balance Sheet ────────────────────────────────────────────────────────
    bs0.total_assets,
    bs0.total_equity,
    bs0.total_debt,
    bs0.net_debt,
    bs0.cash_equivalents    AS cash,
    bs0.book_value_per_share,
    CASE WHEN bs0.total_equity <> 0 AND bs0.total_equity IS NOT NULL
         THEN ROUND(bs0.total_debt / bs0.total_equity, 4) END AS debt_to_equity,
    CASE WHEN bs0.total_current_liab <> 0 AND bs0.total_current_liab IS NOT NULL
         THEN ROUND(bs0.total_current_assets / bs0.total_current_liab, 4) END AS current_ratio,

    -- ── Cash Flow ────────────────────────────────────────────────────────────
    cf0.cfo         AS cfo_fy0,
    cf0.capex       AS capex_fy0,
    cf0.fcf         AS fcf_fy0,

    -- ── Growth rates ─────────────────────────────────────────────────────────
    -- Priority: computed_metrics (uses latest price + last 5 annual rows)
    --           yearly_metrics  (more thorough historical CAGR)
    COALESCE(cm.revenue_growth_1y,  ym.revenue_growth_1y)        AS revenue_growth_1y,
    COALESCE(cm.revenue_growth_3y,  ym.revenue_cagr_3y)          AS revenue_growth_3y_cagr,
    COALESCE(cm.profit_growth_1y,   ym.net_income_growth_1y)     AS earnings_growth_1y,
    COALESCE(cm.profit_growth_3y,   ym.net_income_cagr_3y)       AS earnings_growth_3y_cagr,

    -- ── Returns (daily → weekly/monthly fallback) ─────────────────────────────
    COALESCE(dm.return_1w,  wm.weekly_return)  AS return_1w,
    COALESCE(dm.return_1m,  mm.monthly_return) AS return_1m,
    COALESCE(dm.return_3m,  mm.return_3m)      AS return_3m,
    COALESCE(dm.return_6m,  mm.return_6m)      AS return_6m,
    COALESCE(dm.return_1y,  mm.return_12m)     AS return_1y,
    COALESCE(dm.return_ytd, mm.return_ytd)     AS return_ytd,
    mm.momentum_3m      AS momentum_3m,
    mm.momentum_6m      AS momentum_6m,
    mm.momentum_12m     AS momentum_12m,

    -- ── Volatility & risk ────────────────────────────────────────────────────
    COALESCE(dm.hv_20d, mm.volatility_1m)      AS volatility_20d,
    COALESCE(dm.hv_60d, mm.volatility_3m)      AS volatility_60d,
    ym.sharpe_1y        AS sharpe_1y,
    COALESCE(dm.pct_from_ath, mm.drawdown_from_ath, ym.max_drawdown_1y) AS drawdown_from_ath,
    ym.beta_1y          AS beta_1y,

    -- ── Technicals: daily metrics preferred; weekly/monthly as fallback ───────
    COALESCE(dm.rsi_14,     mm.rsi_14)         AS rsi_14,
    COALESCE(dm.macd_line,  mm.macd_line)      AS macd,
    COALESCE(dm.macd_signal,mm.macd_signal)    AS macd_signal,
    -- SMAs: exact daily values preferred over weekly approximations
    COALESCE(dm.sma_20,  wm.sma_20w)           AS sma_20,
    COALESCE(dm.sma_50,  wm.sma_10w)           AS sma_50,
    COALESCE(dm.sma_200, wm.sma_40w)           AS sma_200,
    COALESCE(dm.ema_20,  wm.ema_13w)           AS ema_20,
    COALESCE(dm.bb_upper,wm.bb_upper)          AS bb_upper,
    COALESCE(dm.bb_lower,wm.bb_lower)          AS bb_lower,
    COALESCE(dm.atr_14,  wm.atr_14)            AS atr_14,
    dm.adx_14,
    COALESCE(dm.obv,     wm.obv)               AS obv,

    -- ── Multi-year quality & CAGR (from yearly_metrics — latest FY) ──────────
    ym.piotroski_f_score,
    ym.altman_z_score,
    ym.revenue_cagr_5y,
    ym.eps_cagr_3y          AS eps_growth_3y_cagr,
    ym.avg_roe_3y,
    ym.dividend_cagr_3y,
    ym.dividend_consecutive_yrs,
    ym.return_3y,
    ym.return_5y,
    ym.return_7y,
    ym.return_10y,
    ym.return_15y,

    -- ── Latest-quarter YoY growth (from quarterly_metrics) ───────────────────
    qm.revenue_growth_yoy    AS revenue_growth_yoy_q,
    qm.eps_growth_yoy        AS eps_growth_yoy_q,
    qm.net_income_growth_yoy AS net_income_growth_yoy_q,

    -- ── Half-yearly HoH growth (from halfyearly_metrics — latest half) ────────
    hym.revenue_growth_hoh,
    hym.net_income_growth_hoh,
    hym.eps_growth_hoh,

    -- ── Analyst ──────────────────────────────────────────────────────────────
    ar.rating           AS analyst_rating,
    ar.target_price     AS analyst_target_price,
    ar.strong_buy, ar.buy, ar.hold, ar.sell, ar.strong_sell,

    -- ── Short interest (ASIC — latest date per stock) ───────────────────────
    si.total_product_short_pct AS short_pct,
    si.gross_short_position    AS short_position_shares,

    -- ── Shares ───────────────────────────────────────────────────────────────
    ss.shares_outstanding,

    NOW()

FROM market.companies_current c

-- ── Latest close price + open/volume + 52w high/low + 20d avg volume ────────
LEFT JOIN LATERAL (
    SELECT
        close,
        open,
        volume,
        DATE(time AT TIME ZONE 'Australia/Sydney') AS price_date,
        MAX(high)   OVER (PARTITION BY asx_code ORDER BY time
            ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS high_52w,
        MIN(low)    OVER (PARTITION BY asx_code ORDER BY time
            ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS low_52w,
        AVG(volume) OVER (PARTITION BY asx_code ORDER BY time
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)  AS avg_volume_20d
    FROM market.daily_prices
    WHERE asx_code = c.asx_code
    ORDER BY time DESC
    LIMIT 1
) dp ON TRUE

-- ── Valuation snapshot (EODHD weekly refresh) ─────────────────────────────────
LEFT JOIN market.valuation_snapshot vs ON vs.asx_code = c.asx_code

-- ── Latest ex-dividend date ───────────────────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT ex_date, franking_pct FROM market.dividends
    WHERE asx_code = c.asx_code
    ORDER BY ex_date DESC
    LIMIT 1
) div_latest ON TRUE

-- ── Annual P&L FY0 (most recent) ─────────────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT fiscal_year, revenue, ebitda, net_profit, eps
    FROM financials.annual_pnl
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) pnl0 ON TRUE

-- ── Annual P&L FY1 (second most recent) ──────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT fiscal_year, revenue, ebitda, net_profit, eps
    FROM financials.annual_pnl
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1 OFFSET 1
) pnl1 ON TRUE

-- ── Balance Sheet (latest FY) ─────────────────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT total_assets, total_equity, total_debt, net_debt,
           cash_equivalents, book_value_per_share,
           total_current_assets, total_current_liab
    FROM financials.annual_balance_sheet
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) bs0 ON TRUE

-- ── Cash Flow (latest FY) ─────────────────────────────────────────────────────
LEFT JOIN LATERAL (
    SELECT cfo, capex, fcf
    FROM financials.annual_cashflow
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) cf0 ON TRUE

-- ── Computed metrics (daily compute — freshest ratios & margins) ──────────────
LEFT JOIN LATERAL (
    SELECT roe, roa, roce, opm, npm, gpm, ebitda_margin,
           grossed_up_yield, fcf_yield,
           revenue_growth_1y, revenue_growth_3y,
           profit_growth_1y,  profit_growth_3y
    FROM market.computed_metrics
    WHERE asx_code = c.asx_code
    ORDER BY time DESC
    LIMIT 1
) cm ON TRUE

-- ── Weekly metrics (latest week — return_1w, SMAs, BB, ATR, OBV) ─────────────
LEFT JOIN LATERAL (
    SELECT weekly_return,
           sma_10w, sma_20w, sma_40w, ema_13w,
           bb_upper, bb_lower, atr_14, obv,
           above_sma10w, above_sma40w, golden_cross, death_cross
    FROM market.weekly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY week_date DESC
    LIMIT 1
) wm ON TRUE

-- ── Monthly metrics (latest month — returns, momentum, volatility, technicals)
LEFT JOIN LATERAL (
    SELECT monthly_return, return_3m, return_6m, return_12m, return_ytd,
           momentum_3m, momentum_6m, momentum_12m,
           volatility_1m, volatility_3m,
           drawdown_from_ath,
           rsi_14, macd_line, macd_signal
    FROM market.monthly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY month_date DESC
    LIMIT 1
) mm ON TRUE

-- ── Daily metrics (latest date — exact technical indicators) ──────────────────
LEFT JOIN LATERAL (
    SELECT rsi_14, macd_line, macd_signal,
           sma_20, sma_50, sma_200, ema_20,
           bb_upper, bb_lower, atr_14, adx_14, obv,
           hv_20d, hv_60d, pct_from_ath,
           return_1w, return_1m, return_3m, return_6m, return_ytd, return_1y
    FROM market.daily_metrics
    WHERE asx_code = c.asx_code
    ORDER BY date DESC
    LIMIT 1
) dm ON TRUE

-- ── Yearly metrics (latest FY — CAGRs, quality scores, risk) ─────────────────
LEFT JOIN LATERAL (
    SELECT roe, roa, roce,
           fcf_yield, franked_yield,
           revenue_growth_1y, revenue_cagr_3y, revenue_cagr_5y,
           net_income_growth_1y, net_income_cagr_3y,
           eps_cagr_3y,
           avg_roe_3y,
           piotroski_f_score, altman_z_score,
           sharpe_1y, max_drawdown_1y,
           beta_1y,
           dividend_cagr_3y, dividend_consecutive_yrs,
           return_3y, return_5y, return_7y, return_10y, return_15y
    FROM market.yearly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC
    LIMIT 1
) ym ON TRUE

-- ── Quarterly metrics (latest quarter — QoQ and YoY growth) ──────────────────
LEFT JOIN LATERAL (
    SELECT revenue_growth_yoy, eps_growth_yoy, net_income_growth_yoy
    FROM market.quarterly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY fiscal_year DESC, quarter DESC
    LIMIT 1
) qm ON TRUE

-- ── Half-yearly metrics (latest half — HoH growth) ───────────────────────────
LEFT JOIN LATERAL (
    SELECT revenue_growth_hoh, net_income_growth_hoh, eps_growth_hoh
    FROM market.halfyearly_metrics
    WHERE asx_code = c.asx_code
    ORDER BY period_end_date DESC
    LIMIT 1
) hym ON TRUE

-- ── Analyst ratings ───────────────────────────────────────────────────────────
LEFT JOIN market.analyst_ratings ar ON ar.asx_code = c.asx_code

-- ── Shares outstanding (staging — most recently loaded) ───────────────────────
LEFT JOIN LATERAL (
    SELECT shares_outstanding::BIGINT
    FROM staging.shares_stats
    WHERE asx_code = c.asx_code
    LIMIT 1
) ss ON TRUE

-- ── ASIC short interest (latest report date per stock) ──────────────────────
LEFT JOIN LATERAL (
    SELECT
        total_product_short_pct,
        gross_short_position
    FROM market.short_interest
    WHERE asx_code = c.asx_code
    ORDER BY time DESC
    LIMIT 1
) si ON TRUE

{code_filter}

ON CONFLICT (asx_code) DO UPDATE SET
    -- Identity
    company_name            = EXCLUDED.company_name,
    sector                  = EXCLUDED.sector,
    industry_group          = EXCLUDED.industry_group,
    industry                = EXCLUDED.industry,
    sub_industry            = EXCLUDED.sub_industry,
    stock_type              = EXCLUDED.stock_type,
    status                  = EXCLUDED.status,
    fiscal_year_end_month   = EXCLUDED.fiscal_year_end_month,
    is_reit                 = EXCLUDED.is_reit,
    is_miner                = EXCLUDED.is_miner,
    is_asx20                = EXCLUDED.is_asx20,
    is_asx50                = EXCLUDED.is_asx50,
    is_asx100               = EXCLUDED.is_asx100,
    is_asx200               = EXCLUDED.is_asx200,
    is_asx300               = EXCLUDED.is_asx300,
    is_all_ords             = EXCLUDED.is_all_ords,
    isin                    = EXCLUDED.isin,
    website                 = EXCLUDED.website,
    description             = EXCLUDED.description,
    -- Price
    price                   = EXCLUDED.price,
    price_date              = EXCLUDED.price_date,
    open                    = EXCLUDED.open,
    volume                  = EXCLUDED.volume,
    avg_volume_20d          = EXCLUDED.avg_volume_20d,
    market_cap              = EXCLUDED.market_cap,
    high_52w                = EXCLUDED.high_52w,
    low_52w                 = EXCLUDED.low_52w,
    -- Valuation
    pe_ratio                = EXCLUDED.pe_ratio,
    forward_pe              = EXCLUDED.forward_pe,
    peg_ratio               = EXCLUDED.peg_ratio,
    price_to_book           = EXCLUDED.price_to_book,
    price_to_sales          = EXCLUDED.price_to_sales,
    ev                      = EXCLUDED.ev,
    ev_to_ebitda            = EXCLUDED.ev_to_ebitda,
    ev_to_revenue           = EXCLUDED.ev_to_revenue,
    -- Dividends
    dividend_yield          = EXCLUDED.dividend_yield,
    dps_ttm                 = EXCLUDED.dps_ttm,
    ex_div_date             = EXCLUDED.ex_div_date,
    franking_pct            = EXCLUDED.franking_pct,
    -- Profitability
    revenue_ttm             = EXCLUDED.revenue_ttm,
    gross_profit_ttm        = EXCLUDED.gross_profit_ttm,
    ebitda_ttm              = EXCLUDED.ebitda_ttm,
    gross_margin            = EXCLUDED.gross_margin,
    ebitda_margin           = EXCLUDED.ebitda_margin,
    net_margin              = EXCLUDED.net_margin,
    operating_margin        = EXCLUDED.operating_margin,
    roe                     = EXCLUDED.roe,
    roa                     = EXCLUDED.roa,
    roce                    = EXCLUDED.roce,
    grossed_up_yield        = EXCLUDED.grossed_up_yield,
    fcf_yield               = EXCLUDED.fcf_yield,
    -- EPS
    eps_fy0                 = EXCLUDED.eps_fy0,
    eps_fy1                 = EXCLUDED.eps_fy1,
    -- Income Statement
    revenue_fy0             = EXCLUDED.revenue_fy0,
    revenue_fy1             = EXCLUDED.revenue_fy1,
    ebitda_fy0              = EXCLUDED.ebitda_fy0,
    ebitda_fy1              = EXCLUDED.ebitda_fy1,
    net_profit_fy0          = EXCLUDED.net_profit_fy0,
    net_profit_fy1          = EXCLUDED.net_profit_fy1,
    -- Balance Sheet
    total_assets            = EXCLUDED.total_assets,
    total_equity            = EXCLUDED.total_equity,
    total_debt              = EXCLUDED.total_debt,
    net_debt                = EXCLUDED.net_debt,
    cash                    = EXCLUDED.cash,
    book_value_per_share    = EXCLUDED.book_value_per_share,
    debt_to_equity          = EXCLUDED.debt_to_equity,
    current_ratio           = EXCLUDED.current_ratio,
    -- Cash Flow
    cfo_fy0                 = EXCLUDED.cfo_fy0,
    capex_fy0               = EXCLUDED.capex_fy0,
    fcf_fy0                 = EXCLUDED.fcf_fy0,
    -- Growth rates
    revenue_growth_1y       = EXCLUDED.revenue_growth_1y,
    revenue_growth_3y_cagr  = EXCLUDED.revenue_growth_3y_cagr,
    earnings_growth_1y      = EXCLUDED.earnings_growth_1y,
    earnings_growth_3y_cagr = EXCLUDED.earnings_growth_3y_cagr,
    -- Returns & momentum
    return_1w               = EXCLUDED.return_1w,
    return_1m               = EXCLUDED.return_1m,
    return_3m               = EXCLUDED.return_3m,
    return_6m               = EXCLUDED.return_6m,
    return_1y               = EXCLUDED.return_1y,
    return_ytd              = EXCLUDED.return_ytd,
    momentum_3m             = EXCLUDED.momentum_3m,
    momentum_6m             = EXCLUDED.momentum_6m,
    momentum_12m            = EXCLUDED.momentum_12m,
    -- Volatility & risk
    volatility_20d          = EXCLUDED.volatility_20d,
    volatility_60d          = EXCLUDED.volatility_60d,
    sharpe_1y               = EXCLUDED.sharpe_1y,
    drawdown_from_ath       = EXCLUDED.drawdown_from_ath,
    beta_1y                 = EXCLUDED.beta_1y,
    -- Technicals
    rsi_14                  = EXCLUDED.rsi_14,
    macd                    = EXCLUDED.macd,
    macd_signal             = EXCLUDED.macd_signal,
    sma_20                  = EXCLUDED.sma_20,
    sma_50                  = EXCLUDED.sma_50,
    sma_200                 = EXCLUDED.sma_200,
    ema_20                  = EXCLUDED.ema_20,
    bb_upper                = EXCLUDED.bb_upper,
    bb_lower                = EXCLUDED.bb_lower,
    atr_14                  = EXCLUDED.atr_14,
    adx_14                  = EXCLUDED.adx_14,
    obv                     = EXCLUDED.obv,
    -- Multi-year quality & CAGR
    piotroski_f_score       = EXCLUDED.piotroski_f_score,
    altman_z_score          = EXCLUDED.altman_z_score,
    revenue_cagr_5y         = EXCLUDED.revenue_cagr_5y,
    eps_growth_3y_cagr      = EXCLUDED.eps_growth_3y_cagr,
    avg_roe_3y              = EXCLUDED.avg_roe_3y,
    dividend_cagr_3y        = EXCLUDED.dividend_cagr_3y,
    dividend_consecutive_yrs = EXCLUDED.dividend_consecutive_yrs,
    return_3y               = EXCLUDED.return_3y,
    return_5y               = EXCLUDED.return_5y,
    return_7y               = EXCLUDED.return_7y,
    return_10y              = EXCLUDED.return_10y,
    return_15y              = EXCLUDED.return_15y,
    -- Latest-quarter growth
    revenue_growth_yoy_q    = EXCLUDED.revenue_growth_yoy_q,
    eps_growth_yoy_q        = EXCLUDED.eps_growth_yoy_q,
    net_income_growth_yoy_q = EXCLUDED.net_income_growth_yoy_q,
    -- Half-yearly HoH growth
    revenue_growth_hoh      = EXCLUDED.revenue_growth_hoh,
    net_income_growth_hoh   = EXCLUDED.net_income_growth_hoh,
    eps_growth_hoh          = EXCLUDED.eps_growth_hoh,
    -- Analyst
    analyst_rating          = EXCLUDED.analyst_rating,
    analyst_target_price    = EXCLUDED.analyst_target_price,
    analyst_strong_buy      = EXCLUDED.analyst_strong_buy,
    analyst_buy             = EXCLUDED.analyst_buy,
    analyst_hold            = EXCLUDED.analyst_hold,
    analyst_sell            = EXCLUDED.analyst_sell,
    analyst_strong_sell     = EXCLUDED.analyst_strong_sell,
    -- Short interest (ASIC)
    short_pct               = EXCLUDED.short_pct,
    short_position_shares   = EXCLUDED.short_position_shares,
    -- Shares
    shares_outstanding      = EXCLUDED.shares_outstanding,
    universe_built_at       = NOW()
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        code_filter = f"WHERE c.asx_code IN ({placeholders})"
        params = [c.upper() for c in args.codes]
    else:
        code_filter = ""
        params = []

    sql = UPSERT_SQL.format(code_filter=code_filter)

    log.info(f"Building screener.universe {'for ' + str(args.codes) if args.codes else '(all stocks)'}…")
    cur.execute(sql, params)
    n = cur.rowcount
    conn.commit()

    cur.close()
    conn.close()
    log.info(f"DONE — {n:,} rows upserted into screener.universe")


if __name__ == "__main__":
    main()
