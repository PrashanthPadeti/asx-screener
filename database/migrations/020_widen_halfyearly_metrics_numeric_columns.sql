-- Migration 020: Widen NUMERIC(8,4) columns in market.halfyearly_metrics
-- ========================================================================
-- NUMERIC(8,4) overflows for near-zero-revenue stocks (BTE etc.) where
-- margins and growth rates exceed ±9999.9999.
--
-- Fix: widen all ratio/growth columns to NUMERIC(18,6) — consistent with
-- the project-wide standard established in migrations 018 and 019.
-- ========================================================================

ALTER TABLE market.halfyearly_metrics
    -- Margins
    ALTER COLUMN gross_margin            TYPE NUMERIC(18,6),
    ALTER COLUMN ebit_margin             TYPE NUMERIC(18,6),
    ALTER COLUMN net_margin              TYPE NUMERIC(18,6),

    -- Period-over-Period Growth
    ALTER COLUMN revenue_growth_hoh      TYPE NUMERIC(18,6),
    ALTER COLUMN revenue_growth_yoy      TYPE NUMERIC(18,6),
    ALTER COLUMN net_income_growth_hoh   TYPE NUMERIC(18,6),
    ALTER COLUMN net_income_growth_yoy   TYPE NUMERIC(18,6),
    ALTER COLUMN eps_growth_hoh          TYPE NUMERIC(18,6),
    ALTER COLUMN eps_growth_yoy          TYPE NUMERIC(18,6);
