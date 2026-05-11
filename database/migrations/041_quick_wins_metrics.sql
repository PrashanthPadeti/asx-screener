-- ============================================================
-- Migration 041: Quick-win derived metrics
-- ============================================================
-- Adds 6 metrics that are 100% computable from existing data:
--   1. ocf_to_net_profit    → market.yearly_metrics + screener.universe
--   2. fcf_payout_ratio     → market.yearly_metrics + screener.universe
--   3. shares_dilution_3y   → market.yearly_metrics + screener.universe
--   4. eps_volatility_5y    → market.yearly_metrics + screener.universe
--   5. fcf_positive_years   → market.yearly_metrics + screener.universe
--   6. above_vwap           → market.daily_metrics  + screener.universe
-- ============================================================

-- ── market.yearly_metrics ────────────────────────────────────────────────────

ALTER TABLE market.yearly_metrics
    ADD COLUMN IF NOT EXISTS ocf_to_net_profit  NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS fcf_payout_ratio   NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS shares_dilution_3y NUMERIC(10,6),
    ADD COLUMN IF NOT EXISTS eps_volatility_5y  NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS fcf_positive_years SMALLINT;

COMMENT ON COLUMN market.yearly_metrics.ocf_to_net_profit
    IS 'Operating cash flow / net profit — earnings quality (cash conversion). >1 = strong.';
COMMENT ON COLUMN market.yearly_metrics.fcf_payout_ratio
    IS 'Dividends paid / free cash flow — FCF-based payout sustainability. <0.75 = sustainable.';
COMMENT ON COLUMN market.yearly_metrics.shares_dilution_3y
    IS '3-year CAGR of shares outstanding — positive = dilution, negative = buyback.';
COMMENT ON COLUMN market.yearly_metrics.eps_volatility_5y
    IS 'Coefficient of variation of EPS over 5 years (std/|mean|). Lower = more stable earnings.';
COMMENT ON COLUMN market.yearly_metrics.fcf_positive_years
    IS 'Count of consecutive years (most recent first) with positive free cash flow.';


-- ── market.daily_metrics ─────────────────────────────────────────────────────

ALTER TABLE market.daily_metrics
    ADD COLUMN IF NOT EXISTS above_vwap SMALLINT;

COMMENT ON COLUMN market.daily_metrics.above_vwap
    IS '1 if close > 20-day rolling VWAP, else 0. Simple mean-reversion / momentum signal.';


-- ── screener.universe ─────────────────────────────────────────────────────────

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS ocf_to_net_profit  NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS fcf_payout_ratio   NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS shares_dilution_3y NUMERIC(10,6),
    ADD COLUMN IF NOT EXISTS eps_volatility_5y  NUMERIC(10,4),
    ADD COLUMN IF NOT EXISTS fcf_positive_years SMALLINT,
    ADD COLUMN IF NOT EXISTS above_vwap         SMALLINT;

COMMENT ON COLUMN screener.universe.ocf_to_net_profit
    IS 'OCF / net profit — cash conversion quality (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.fcf_payout_ratio
    IS 'Dividends paid / FCF — payout sustainability (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.shares_dilution_3y
    IS '3Y shares-outstanding CAGR — dilution/buyback signal (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.eps_volatility_5y
    IS 'EPS coefficient of variation over 5Y (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.fcf_positive_years
    IS 'Consecutive years of positive FCF (from yearly_metrics latest FY).';
COMMENT ON COLUMN screener.universe.above_vwap
    IS '1 if latest close > 20d rolling VWAP, else 0 (from daily_metrics latest date).';
