-- Migration 018: Widen narrow NUMERIC columns in market.yearly_metrics
-- =======================================================================
-- NUMERIC(8,2) columns overflow for near-zero-revenue stocks (DYL, VHL etc.)
-- when DSO/DIO/DPO = 365 / near_zero_turnover → values > 999,999.
--
-- NUMERIC(8,4) columns overflow for near-zero EPS/price stocks when
-- yields or payout ratios exceed ±9,999.
--
-- Fix: widen all affected columns to NUMERIC(18,6) — consistent with the
-- project-wide standard for ratios established in migration 008.
-- =======================================================================

ALTER TABLE market.yearly_metrics
    -- NUMERIC(8,2) → NUMERIC(18,6)  [Working Capital Efficiency / CCC]
    ALTER COLUMN receivables_days       TYPE NUMERIC(18,6),
    ALTER COLUMN inventory_days         TYPE NUMERIC(18,6),
    ALTER COLUMN payables_days          TYPE NUMERIC(18,6),
    ALTER COLUMN cash_conversion_cycle  TYPE NUMERIC(18,6),

    -- NUMERIC(8,4) → NUMERIC(18,6)  [Yield & Payout columns]
    ALTER COLUMN earnings_yield         TYPE NUMERIC(18,6),
    ALTER COLUMN fcf_yield              TYPE NUMERIC(18,6),
    ALTER COLUMN dividend_yield         TYPE NUMERIC(18,6),
    ALTER COLUMN franked_yield          TYPE NUMERIC(18,6),
    ALTER COLUMN payout_ratio           TYPE NUMERIC(18,6),

    -- NUMERIC(8,4) → NUMERIC(18,6)  [median growth / long-run price CAGR]
    ALTER COLUMN revenue_growth_median_5y   TYPE NUMERIC(18,6),
    ALTER COLUMN revenue_growth_median_10y  TYPE NUMERIC(18,6),
    ALTER COLUMN price_cagr_7y              TYPE NUMERIC(18,6),
    ALTER COLUMN price_cagr_10y             TYPE NUMERIC(18,6),
    ALTER COLUMN avg_current_ratio_3y       TYPE NUMERIC(18,6);
