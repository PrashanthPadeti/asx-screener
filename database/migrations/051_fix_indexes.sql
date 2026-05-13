-- Migration 051: Fix indexes that failed in 050
-- Two issues in 050:
--   1. screener.universe has no return_1d column (skip) and no gics_sector/gics_industry
--      columns (correct names are sector / industry). sector index already existed
--      from migration 015 (idx_su_sector), so only industry is missing.
--   2. market.daily_prices and market.computed_metrics are TimescaleDB hypertables
--      which do NOT support CONCURRENTLY index creation. daily_prices already has
--      idx_daily_prices_asx_time from migration 003. computed_metrics needs a new
--      regular (non-concurrent) index.
-- All other 050 indexes created successfully.

-- ── screener.universe: industry filter (missing from all prior migrations) ────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_industry
    ON screener.universe (industry);

-- ── market.computed_metrics: code lookup (hypertable — no CONCURRENTLY) ───────
CREATE INDEX IF NOT EXISTS idx_computed_metrics_code_time
    ON market.computed_metrics (asx_code, time DESC);

\echo 'Migration 051 complete — 2 fix indexes created.'
