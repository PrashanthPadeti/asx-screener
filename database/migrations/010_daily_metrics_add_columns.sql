-- Migration 010: Add missing columns to market.daily_metrics
-- These columns were in compute_daily.py output but missing from the table.
-- Using ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+).

ALTER TABLE market.daily_metrics
    ADD COLUMN IF NOT EXISTS open            NUMERIC(12,4),
    ADD COLUMN IF NOT EXISTS high            NUMERIC(12,4),
    ADD COLUMN IF NOT EXISTS low             NUMERIC(12,4),
    ADD COLUMN IF NOT EXISTS aroon_up        NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS aroon_down      NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS pct_from_atl    NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS volume_avg_52w  BIGINT,
    ADD COLUMN IF NOT EXISTS return_1d       NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS return_5d       NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS return_20d      NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS return_60d      NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS sma_5_prev      NUMERIC(12,4),
    ADD COLUMN IF NOT EXISTS sma_20_prev     NUMERIC(12,4),
    ADD COLUMN IF NOT EXISTS rsi_overbought  BOOLEAN,
    ADD COLUMN IF NOT EXISTS rsi_oversold    BOOLEAN,
    ADD COLUMN IF NOT EXISTS macd_bullish_cross BOOLEAN,
    ADD COLUMN IF NOT EXISTS macd_bearish_cross BOOLEAN;
