-- yfinance observations get their own staging table
-- ==================================================
-- `backfill_yfinance_prices` wrote directly into market.daily_prices — a
-- canonical OUTPUT, published by the plan stage transform_prices — from an
-- independent 09:00 UTC weekday cron, thirty minutes into the daily
-- pipeline's own window. Two writers, one table, no coordination.
--
-- Rule 5 of docs/canonical_orchestration.md: a canonical output table has one
-- publication authority. So the yfinance job stops publishing and starts
-- acquiring: it lands observations here, and transform_prices remains the
-- sole writer of market.daily_prices.
--
-- Why not staging_au.eod_prices
-- -----------------------------
-- Because its lifecycle would destroy them. load_to_staging_prices TRUNCATEs
-- that table on a full run and DELETEs by date on an incremental one, and it
-- runs at daily_pipeline step 3 while transform_prices runs at step 5. Rows
-- parked there at 09:00 would be gone before the transform ever saw them.
-- That is a lifecycle fact, not a preference.
--
-- Types match staging_au.eod_prices exactly — numeric(12,4) for OHLC, bigint
-- volume, varchar(10) code. Not a stylistic choice: transform_prices passes
-- these values straight through to market.daily_prices, and this codebase has
-- already lost a day to Decimal-versus-float rounding differences that only
-- appeared in a full-population read-back.
--
-- (asx_code, date) is the primary key rather than a surrogate id, because a
-- re-run of the same backfill window must update the same rows rather than
-- accumulate duplicates. Idempotence is a property of the key here.

BEGIN;

CREATE TABLE IF NOT EXISTS staging_au.yfinance_prices (
    asx_code        VARCHAR(10)   NOT NULL,
    date            DATE          NOT NULL,
    open            NUMERIC(12,4),
    high            NUMERIC(12,4),
    low             NUMERIC(12,4),
    close           NUMERIC(12,4),
    adjusted_close  NUMERIC(12,4),
    volume          BIGINT,
    fetched_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (asx_code, date)
);

COMMENT ON TABLE staging_au.yfinance_prices IS
    'Price observations acquired from Yahoo Finance, awaiting publication by '
    'transform_prices. PRE_INGESTION state: nothing downstream may read it '
    'except the transform, and nothing may publish from it except the '
    'transform. Separate from staging_au.eod_prices because that table is '
    'truncated and date-deleted by its loader, which would erase these rows '
    'before they were consumed.';

COMMENT ON COLUMN staging_au.yfinance_prices.fetched_at IS
    'When this observation was acquired. Diagnostic only — it is NOT a '
    'precedence input. Precedence between feeds is declared in '
    'transform_prices and must not depend on arrival time.';

-- transform_prices reads by code and date window, the same access pattern as
-- staging_au.eod_prices.
CREATE INDEX IF NOT EXISTS idx_stg_yfinance_prices_code_date
    ON staging_au.yfinance_prices (asx_code, date DESC);

COMMIT;
