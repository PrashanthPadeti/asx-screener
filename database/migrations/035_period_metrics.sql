-- migration: 035_period_metrics.sql
-- Pre-computed period H/L/AvgVol for each instrument, updated daily.
-- Covers 1D, 1W, 1M, 3M, 6M, 1Y, 52W windows.
-- API reads from this table instead of running live CTEs each request.

CREATE TABLE IF NOT EXISTS market.period_metrics (
    asx_code        VARCHAR(10)  NOT NULL,
    computed_date   DATE         NOT NULL DEFAULT CURRENT_DATE,

    -- 1 Day (last 3 calendar days to catch weekends/holidays)
    high_1d         NUMERIC(14,4),
    low_1d          NUMERIC(14,4),
    avg_volume_1d   BIGINT,

    -- 1 Week (~7 calendar days)
    high_1w         NUMERIC(14,4),
    low_1w          NUMERIC(14,4),
    avg_volume_1w   BIGINT,

    -- 1 Month (~35 calendar days)
    high_1m         NUMERIC(14,4),
    low_1m          NUMERIC(14,4),
    avg_volume_1m   BIGINT,

    -- 3 Months (~100 calendar days)
    high_3m         NUMERIC(14,4),
    low_3m          NUMERIC(14,4),
    avg_volume_3m   BIGINT,

    -- 6 Months (~185 calendar days)
    high_6m         NUMERIC(14,4),
    low_6m          NUMERIC(14,4),
    avg_volume_6m   BIGINT,

    -- 1 Year (365 calendar days)
    high_1y         NUMERIC(14,4),
    low_1y          NUMERIC(14,4),
    avg_volume_1y   BIGINT,

    -- 52 Weeks (364 calendar days — exactly 52 × 7)
    high_52w        NUMERIC(14,4),
    low_52w         NUMERIC(14,4),
    avg_volume_52w  BIGINT,

    PRIMARY KEY (asx_code, computed_date)
);

-- Fast lookup: latest date for all stocks
CREATE INDEX IF NOT EXISTS idx_period_metrics_date
    ON market.period_metrics (computed_date DESC);

COMMENT ON TABLE market.period_metrics IS
    'Daily snapshot of period H/L/AvgVol per instrument. Computed by period_metrics_compute.py after market close.';
