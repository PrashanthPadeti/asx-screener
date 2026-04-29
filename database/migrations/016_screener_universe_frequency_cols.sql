-- Migration 016: Add frequency-metric columns to screener.universe
-- =================================================================
-- Adds columns sourced from:
--   market.monthly_metrics  → returns, momentum, volatility, technicals
--   market.yearly_metrics   → CAGRs, quality scores, risk metrics
--   market.quarterly_metrics → latest-quarter YoY growth
--
-- These are populated by build_screener_universe.py via LATERAL JOINs.
-- The existing columns (return_1m, momentum_3m, rsi_14 etc.) were already
-- in the schema from migration 015 but not yet being populated.
-- New columns added here: piotroski_f_score, altman_z_score, revenue_cagr_5y,
-- eps_growth_3y_cagr, avg_roe_3y, beta_1y, dividend_cagr_3y,
-- dividend_consecutive_yrs, revenue_growth_yoy_q, eps_growth_yoy_q,
-- net_income_growth_yoy_q.

-- Drop dependent views first (required before any column changes)
DROP VIEW IF EXISTS screener.fundamentals;
DROP VIEW IF EXISTS screener.technicals;

-- ── New columns from yearly_metrics ───────────────────────────────────────────
ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS piotroski_f_score        SMALLINT,          -- 0–9 financial quality score
    ADD COLUMN IF NOT EXISTS altman_z_score           NUMERIC(8,4),      -- bankruptcy risk score
    ADD COLUMN IF NOT EXISTS revenue_cagr_5y          NUMERIC(8,4),      -- 5-year revenue CAGR
    ADD COLUMN IF NOT EXISTS eps_growth_3y_cagr       NUMERIC(8,4),      -- 3-year EPS CAGR
    ADD COLUMN IF NOT EXISTS avg_roe_3y               NUMERIC(8,4),      -- 3-year average ROE
    ADD COLUMN IF NOT EXISTS beta_1y                  NUMERIC(8,4),      -- 1-year beta vs XJO
    ADD COLUMN IF NOT EXISTS dividend_cagr_3y         NUMERIC(8,4),      -- 3-year dividend CAGR
    ADD COLUMN IF NOT EXISTS dividend_consecutive_yrs SMALLINT;          -- years of uninterrupted dividends

-- ── New columns from quarterly_metrics (latest quarter YoY growth) ────────────
ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS revenue_growth_yoy_q     NUMERIC(8,4),      -- latest quarter revenue YoY
    ADD COLUMN IF NOT EXISTS eps_growth_yoy_q         NUMERIC(8,4),      -- latest quarter EPS YoY
    ADD COLUMN IF NOT EXISTS net_income_growth_yoy_q  NUMERIC(8,4);      -- latest quarter NI YoY

-- ── Recreate screener.fundamentals view ──────────────────────────────────────
CREATE OR REPLACE VIEW screener.fundamentals AS
SELECT
    asx_code, company_name, sector, industry, stock_type, status,
    market_cap, pe_ratio, forward_pe, peg_ratio, price_to_book,
    price_to_sales, price_to_cash_flow, price_to_fcf,
    ev, ev_to_ebitda, ev_to_ebit, ev_to_revenue, graham_number,
    dps_ttm, dividend_yield, franking_pct, grossed_up_yield,
    payout_ratio,
    dividend_cagr_3y, dividend_consecutive_yrs,
    revenue_ttm, gross_profit_ttm, ebitda_ttm, net_profit_ttm,
    gross_margin, ebitda_margin, net_margin, operating_margin,
    roe, roa, roce, avg_roe_3y,
    revenue_fy0, revenue_fy1, revenue_fy2,
    ebitda_fy0, ebitda_fy1,
    net_profit_fy0, net_profit_fy1,
    eps_fy0, eps_fy1, dps_fy0, dps_fy1,
    total_assets, total_equity, total_debt, net_debt, cash,
    book_value_per_share, debt_to_equity, current_ratio,
    cfo_fy0, capex_fy0, fcf_fy0, fcf_yield,
    revenue_growth_1y, revenue_growth_3y_cagr, revenue_cagr_5y,
    earnings_growth_1y, earnings_growth_3y_cagr, eps_growth_3y_cagr,
    revenue_growth_yoy_q, eps_growth_yoy_q, net_income_growth_yoy_q,
    piotroski_f_score, altman_z_score,
    analyst_rating, analyst_target_price, analyst_upside,
    shares_outstanding, percent_insiders, percent_institutions
FROM screener.universe;

-- ── Recreate screener.technicals view ────────────────────────────────────────
CREATE OR REPLACE VIEW screener.technicals AS
SELECT
    asx_code, company_name, sector, market_cap,
    price, price_date, open, high_52w, low_52w, volume, avg_volume_20d,
    rsi_14, macd, macd_signal, sma_20, sma_50, sma_200, ema_20,
    bb_upper, bb_lower, atr_14, adx_14, obv,
    return_1w, return_1m, return_3m, return_6m, return_1y, return_ytd,
    momentum_3m, momentum_6m, momentum_12m,
    volatility_20d, volatility_60d, sharpe_1y, drawdown_from_ath,
    beta_1y, short_pct
FROM screener.universe;

-- ── Permissions ──────────────────────────────────────────────────────────────
GRANT SELECT ON screener.fundamentals TO asx_user;
GRANT SELECT ON screener.technicals   TO asx_user;
