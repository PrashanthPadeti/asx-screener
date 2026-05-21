-- Migration 052: Add period_high / period_low to market.mover_snapshots
--
-- Root-cause fix for the recurring "High/Low shows dashes" problem.
-- The snapshot table was designed without H/L columns, forcing the API
-- to do a fragile runtime JOIN against market.period_metrics using
-- CURRENT_DATE — which races against the nightly compute jobs.
--
-- This migration adds the columns so market_snapshot.py can write them
-- at snapshot time and the API can read them directly without any JOIN.

ALTER TABLE market.mover_snapshots
    ADD COLUMN IF NOT EXISTS period_high NUMERIC(12,4),
    ADD COLUMN IF NOT EXISTS period_low  NUMERIC(12,4);

COMMENT ON COLUMN market.mover_snapshots.period_high
    IS 'Period high price (e.g. 1W high for GAINER_1W rows). Written by market_snapshot.py from period_metrics.';
COMMENT ON COLUMN market.mover_snapshots.period_low
    IS 'Period low price (e.g. 1W low for GAINER_1W rows). Written by market_snapshot.py from period_metrics.';
