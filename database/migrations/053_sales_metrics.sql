-- Migration 053: Add sales-based signal columns to screener.universe
-- revenue_growth_accelerating: current year growth > previous year (acceleration signal)
-- revenue_growth_delta:        magnitude of acceleration in pp (decimal, e.g. 0.05 = +5pp)
-- revenue_growth_consistency:  count of positive YoY growth years in last 3 (0-3)

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS revenue_growth_accelerating BOOLEAN,
    ADD COLUMN IF NOT EXISTS revenue_growth_delta         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS revenue_growth_consistency   SMALLINT;
