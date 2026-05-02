-- Migration 022: ASIC Short Interest — staging + processed tables + screener column
-- ===================================================================================
-- Adds a proper 3-stage pipeline for ASIC short position data:
--   raw CSV → staging.short_positions → market.short_positions (with WoW change)
-- Also adds short_interest_chg_1w to screener.universe for the golden record.
-- ===================================================================================

-- ── 1. Staging table — raw CSV rows ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.short_positions (
    id              BIGSERIAL       PRIMARY KEY,
    loaded_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    source_file     TEXT,                                   -- filename of source CSV
    report_date     DATE            NOT NULL,
    asx_code        VARCHAR(10)     NOT NULL,
    short_shares    BIGINT,                                 -- gross short position
    total_issued    BIGINT,                                 -- total product in issue
    short_pct       NUMERIC(10, 6),                        -- % of total product
    UNIQUE (report_date, asx_code)
);

CREATE INDEX IF NOT EXISTS idx_staging_short_positions_date
    ON staging.short_positions (report_date DESC);
CREATE INDEX IF NOT EXISTS idx_staging_short_positions_code
    ON staging.short_positions (asx_code);

GRANT SELECT, INSERT, UPDATE ON staging.short_positions TO asx_user;
GRANT USAGE, SELECT ON SEQUENCE staging.short_positions_id_seq TO asx_user;

-- ── 2. Processed market table — with WoW change computed ─────────────────────────
CREATE TABLE IF NOT EXISTS market.short_positions (
    report_date         DATE            NOT NULL,
    asx_code            VARCHAR(10)     NOT NULL,
    short_pct           NUMERIC(10, 6),                    -- % of total product in issue
    short_shares        BIGINT,                            -- gross short position
    short_pct_chg_1w    NUMERIC(10, 6),                    -- WoW change (pp, can be NULL)
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (report_date, asx_code)
);

CREATE INDEX IF NOT EXISTS idx_market_short_positions_code_date
    ON market.short_positions (asx_code, report_date DESC);

GRANT SELECT, INSERT, UPDATE ON market.short_positions TO asx_user;

-- ── 3. Add short_interest_chg_1w to screener.universe ────────────────────────────
-- short_pct already exists (from market.short_interest).
-- short_interest_chg_1w is the new week-over-week change column.
ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS short_interest_chg_1w NUMERIC(8, 4);

COMMENT ON COLUMN screener.universe.short_interest_chg_1w IS
    'Week-over-week change in short interest % (percentage points, from market.short_positions)';
