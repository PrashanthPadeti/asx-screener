-- ─────────────────────────────────────────────────────────────
-- 063 — Share count history
-- ─────────────────────────────────────────────────────────────
-- Dated observations of shares outstanding, parsed from the EODHD fundamentals
-- snapshots already on disk. No new API calls.
--
-- The observations are kept rather than reduced to a single CAGR on ingest,
-- because magnitude alone cannot separate the two cases that matter most to a
-- compounding score:
--   a company issuing 20 percent once to fund an acquisition, versus
--   a company issuing 6-8 percent every year to fund operations.
-- A three-year CAGR makes those look similar; economically the second is the
-- far worse signal. Persistence measures need the yearly points, so they are
-- stored now even though only the CAGR is consumed initially.
--
-- Deliberately NOT deriving anything here. The sequence is ingest, inspect the
-- distribution, inspect known splits and capital raisings, then calibrate.
-- Five separate unit and scale errors were found in the multibagger components
-- by following that order, and every one would have executed without raising.

CREATE TABLE IF NOT EXISTS market.shares_history (
    asx_code        VARCHAR(10)  NOT NULL,
    fiscal_date     DATE         NOT NULL,   -- period end the count refers to
    shares          BIGINT,                  -- raw count
    shares_mln      NUMERIC(18,4),           -- as reported, millions
    source          VARCHAR(40)  NOT NULL DEFAULT 'eodhd_fundamentals_annual',
    snapshot_date   DATE,                    -- fundamentals file this came from
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (asx_code, fiscal_date, source)
);

CREATE INDEX IF NOT EXISTS idx_shares_history_code
    ON market.shares_history (asx_code, fiscal_date DESC);

COMMENT ON TABLE market.shares_history IS
    'Dated shares-outstanding observations from EODHD fundamentals. Raw history, '
    'no derived metrics — dilution measures are computed downstream so the '
    'definition can change without re-ingesting.';

COMMENT ON COLUMN market.shares_history.fiscal_date IS
    'Period end the share count refers to, from outstandingShares.annual '
    'dateFormatted. NOT the date the snapshot was taken.';

COMMENT ON COLUMN market.shares_history.snapshot_date IS
    'Date of the fundamentals file supplying this row. Two snapshots can report '
    'different counts for the same fiscal_date after a restatement; the newest '
    'snapshot wins on upsert.';
