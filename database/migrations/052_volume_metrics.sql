-- Migration 052: Add volume-based metric columns
-- Adds ADL, Up/Down Volume Ratio, OBV Rising, Volume Breakout to daily_metrics,
-- and exposes avg_volume_50d, cmf_20 + all new signals in screener.universe.

-- ── market.daily_metrics ──────────────────────────────────────────────────────
ALTER TABLE market.daily_metrics
    ADD COLUMN IF NOT EXISTS adl                   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS up_down_vol_ratio_20d DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS obv_rising            BOOLEAN,
    ADD COLUMN IF NOT EXISTS volume_breakout       BOOLEAN;

-- ── screener.universe ─────────────────────────────────────────────────────────
ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS avg_volume_50d        BIGINT,
    ADD COLUMN IF NOT EXISTS cmf_20                DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS adl                   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS up_down_vol_ratio_20d DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS obv_rising            BOOLEAN,
    ADD COLUMN IF NOT EXISTS volume_breakout       BOOLEAN;
