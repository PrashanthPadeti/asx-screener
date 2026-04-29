-- Migration 017: Add raw financials + multi-year price returns
-- =============================================================
-- market.yearly_metrics gains denormalised raw financial values so
-- the API can power company-detail history tables from a single table
-- (instead of JOINing financials.annual_pnl + balance_sheet + cashflow).
--
-- Also adds 3Y/5Y/7Y/10Y/15Y price-return columns to both
-- market.yearly_metrics (historical, per FY) and screener.universe
-- (current-year, for screening).
--
-- All new NUMERIC columns use NUMERIC(18,6) for ratios/returns and
-- NUMERIC(18,2) for AUD-million absolute values — consistent with
-- the project-wide standard established in migration 008.
-- =============================================================


-- ── market.yearly_metrics — raw absolute financials ──────────────────────────
ALTER TABLE market.yearly_metrics
    -- Income statement raw values (AUD millions)
    ADD COLUMN IF NOT EXISTS revenue          NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS ebitda           NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS net_profit       NUMERIC(18,2),

    -- Cash flow raw values (AUD millions)
    ADD COLUMN IF NOT EXISTS cfo              NUMERIC(18,2),   -- operating cash flow
    ADD COLUMN IF NOT EXISTS capex            NUMERIC(18,2),   -- capital expenditure (negative)
    ADD COLUMN IF NOT EXISTS cfi              NUMERIC(18,2),   -- investing cash flow
    ADD COLUMN IF NOT EXISTS fcf              NUMERIC(18,2),   -- free cash flow

    -- Balance sheet raw values (AUD millions)
    ADD COLUMN IF NOT EXISTS total_debt       NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS working_capital  NUMERIC(18,2),   -- current_assets - current_liabilities
    ADD COLUMN IF NOT EXISTS cash             NUMERIC(18,2),   -- cash & equivalents
    ADD COLUMN IF NOT EXISTS total_equity     NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS inventory        NUMERIC(18,2),

    -- Multi-year price returns (from daily_prices, computed at FY end date)
    ADD COLUMN IF NOT EXISTS return_3y        NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS return_5y        NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS return_7y        NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS return_10y       NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS return_15y       NUMERIC(18,6);


-- ── screener.universe — multi-year price returns (current year) ───────────────
-- Drop dependent views first
DROP VIEW IF EXISTS screener.fundamentals;
DROP VIEW IF EXISTS screener.technicals;

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS return_3y        NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS return_5y        NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS return_7y        NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS return_10y       NUMERIC(18,6),
    ADD COLUMN IF NOT EXISTS return_15y       NUMERIC(18,6);


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
    return_1y, return_3y, return_5y, return_7y, return_10y, return_15y,
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
    return_3y, return_5y, return_10y,
    momentum_3m, momentum_6m, momentum_12m,
    volatility_20d, volatility_60d, sharpe_1y, drawdown_from_ath,
    beta_1y, short_pct
FROM screener.universe;

-- ── Permissions ──────────────────────────────────────────────────────────────
GRANT SELECT ON screener.fundamentals TO asx_user;
GRANT SELECT ON screener.technicals   TO asx_user;
