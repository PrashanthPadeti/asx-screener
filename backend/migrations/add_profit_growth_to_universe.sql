-- Phase B: growth-rate columns on screener.universe.
-- Sales growth (prior year) + Pre-tax Profit (PBT) YoY / prior-year / 3-5-7-10y CAGR.
-- Stored as DECIMAL ratios (0.155 = 15.5%) to match existing *_growth_* columns.
-- DOUBLE PRECISION (ADD if missing, then force type) — YoY growth off a near-zero
-- base can be large, so never use a narrow NUMERIC here.

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS sales_growth_prev_y DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_growth_1y       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_growth_prev_y   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_cagr_3y         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_cagr_5y         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_cagr_7y         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pbt_cagr_10y        DOUBLE PRECISION;

ALTER TABLE screener.universe
    ALTER COLUMN sales_growth_prev_y TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_growth_1y       TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_growth_prev_y   TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_cagr_3y         TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_cagr_5y         TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_cagr_7y         TYPE DOUBLE PRECISION,
    ALTER COLUMN pbt_cagr_10y        TYPE DOUBLE PRECISION;
