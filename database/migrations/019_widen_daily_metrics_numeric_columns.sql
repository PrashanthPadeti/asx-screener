-- Migration 019: Widen NUMERIC(8,4) columns in market.daily_metrics
-- ====================================================================
-- NUMERIC(8,4) overflows for penny stocks where ratios/returns/volatility
-- exceed ±9999.9999 (e.g. CHM: pct_from_52w_low, roc_20, hv_20d, returns).
--
-- Fix: widen all affected columns to NUMERIC(18,6) — consistent with the
-- project-wide standard for ratios established in migration 008.
-- ====================================================================

ALTER TABLE market.daily_metrics
    -- Price/SMA ratios (could be extreme when SMA near zero)
    ALTER COLUMN dma20_ratio             TYPE NUMERIC(18,6),
    ALTER COLUMN dma50_ratio             TYPE NUMERIC(18,6),
    ALTER COLUMN dma200_ratio            TYPE NUMERIC(18,6),

    -- Gap % (open vs prev close)
    ALTER COLUMN gap_pct                 TYPE NUMERIC(18,6),

    -- Bollinger band metrics
    ALTER COLUMN bb_pct                  TYPE NUMERIC(18,6),
    ALTER COLUMN bb_width                TYPE NUMERIC(18,6),

    -- Momentum (Rate of Change — extreme for penny stocks)
    ALTER COLUMN roc_10                  TYPE NUMERIC(18,6),
    ALTER COLUMN roc_20                  TYPE NUMERIC(18,6),

    -- Volatility (annualised — can exceed 9999% for near-zero price stocks)
    ALTER COLUMN atr_pct                 TYPE NUMERIC(18,6),
    ALTER COLUMN hv_20d                  TYPE NUMERIC(18,6),
    ALTER COLUMN hv_60d                  TYPE NUMERIC(18,6),

    -- Volume ratio
    ALTER COLUMN cmf_20                  TYPE NUMERIC(18,6),
    ALTER COLUMN relative_volume         TYPE NUMERIC(18,6),

    -- % from levels (pct_from_52w_low most prone: 0.001 → 10 = 9990x)
    ALTER COLUMN pct_from_52w_high       TYPE NUMERIC(18,6),
    ALTER COLUMN pct_from_52w_low        TYPE NUMERIC(18,6),
    ALTER COLUMN pct_from_ath            TYPE NUMERIC(18,6),

    -- Multi-period returns (penny stocks can have >100x returns)
    ALTER COLUMN return_1w               TYPE NUMERIC(18,6),
    ALTER COLUMN return_1m               TYPE NUMERIC(18,6),
    ALTER COLUMN return_3m               TYPE NUMERIC(18,6),
    ALTER COLUMN return_6m               TYPE NUMERIC(18,6),
    ALTER COLUMN return_ytd              TYPE NUMERIC(18,6),
    ALTER COLUMN return_1y               TYPE NUMERIC(18,6);
