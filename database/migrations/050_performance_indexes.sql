-- Migration 050: Performance indexes
-- Adds missing indexes on commonly queried columns to speed up screener,
-- market data endpoints, and announcement feeds.
-- All indexes are created CONCURRENTLY so they don't lock production tables.
-- Run with: psql $DATABASE_URL -f 050_performance_indexes.sql

-- ─── screener.universe ────────────────────────────────────────────────────────
-- Primary screener filter columns
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_gics_sector
    ON screener.universe (gics_sector);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_gics_industry
    ON screener.universe (gics_industry);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_market_cap
    ON screener.universe (market_cap DESC NULLS LAST);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_pe_ratio
    ON screener.universe (pe_ratio);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_dividend_yield
    ON screener.universe (dividend_yield DESC NULLS LAST);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_return_1d
    ON screener.universe (return_1d DESC NULLS LAST);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_return_ytd
    ON screener.universe (return_ytd DESC NULLS LAST);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_is_asx200
    ON screener.universe (is_asx200)
    WHERE is_asx200 = TRUE;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_universe_is_asx300
    ON screener.universe (is_asx300)
    WHERE is_asx300 = TRUE;

-- ─── market.daily_prices ──────────────────────────────────────────────────────
-- Most queries: WHERE asx_code = ? ORDER BY price_date DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_prices_code_date
    ON market.daily_prices (asx_code, price_date DESC);

-- Range scans (e.g. price_date >= :start)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_daily_prices_date
    ON market.daily_prices (price_date DESC);

-- ─── market.computed_metrics ──────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_computed_metrics_code
    ON market.computed_metrics (asx_code);

-- ─── market.index_prices ──────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_index_prices_code_date
    ON market.index_prices (index_code, price_date DESC);

-- ─── market.fund_prices ───────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fund_prices_code_date
    ON market.fund_prices (asx_code, price_date DESC);

-- ─── market.global_index_prices ───────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_global_index_prices_code_date
    ON market.global_index_prices (index_code, price_date DESC);

-- ─── market.fx_rates ──────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fx_rates_pair_date
    ON market.fx_rates (fx_pair, rate_date DESC);

-- ─── market.commodity_prices ──────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_commodity_prices_code_date
    ON market.commodity_prices (commodity_code, price_date DESC);

-- ─── market.asx_announcements ─────────────────────────────────────────────────
-- Feed sorted by released_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_announcements_released_at
    ON market.asx_announcements (released_at DESC NULLS LAST);

-- Per-company lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_announcements_asx_code
    ON market.asx_announcements (asx_code, released_at DESC NULLS LAST);

-- Sensitive-only filter
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_announcements_sensitive
    ON market.asx_announcements (released_at DESC NULLS LAST)
    WHERE market_sensitive = TRUE OR price_sensitive = TRUE;

-- Full-text search on title (for the search= filter)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_announcements_title_trgm
    ON market.asx_announcements USING gin (title gin_trgm_ops);

-- ─── market.short_positions ───────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_short_positions_code_date
    ON market.short_positions (asx_code, position_date DESC);

-- ─── market.anomalies ─────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomalies_code_date
    ON market.anomalies (asx_code, detected_at DESC);

-- ─── users.alerts ─────────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_user_active
    ON users.alerts (user_id, is_active)
    WHERE is_active = TRUE;

-- Enable trigram extension if not already present (needed for title search index)
-- Run once per database: CREATE EXTENSION IF NOT EXISTS pg_trgm;

\echo 'Migration 050 complete — performance indexes created.'
