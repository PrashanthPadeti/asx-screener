-- Migration 014: SCD Type 2 on market.companies
-- ================================================
-- Converts market.companies from a single-row-per-stock table to a full
-- Slowly Changing Dimension (Type 2) design.
--
-- Why SCD Type 2 here?
--   ASX companies frequently change sector classification, fiscal year end,
--   stock type (equity → REIT, stapling/unstapling), or status (active → delisted).
--   We need to know WHAT a company looked like AT A POINT IN TIME — for screener
--   accuracy, backtesting, and audit trail. SCD Type 2 gives us that without
--   losing current-state query simplicity.
--
-- Pattern:
--   - Surrogate PK: id BIGSERIAL (asx_code alone is no longer unique)
--   - valid_from DATE NOT NULL   — date this version became current
--   - valid_to   DATE            — date this version was superseded (NULL = still current)
--   - is_current BOOLEAN         — fast filter: WHERE is_current = TRUE
--   - Partial unique index:  UNIQUE (asx_code) WHERE is_current = TRUE
--     → only one current row per stock, enforced by the DB
--
-- Query patterns:
--   Current state:    SELECT * FROM market.companies WHERE asx_code = 'BHP' AND is_current = TRUE
--   Point-in-time:    SELECT * FROM market.companies WHERE asx_code = 'BHP'
--                       AND valid_from <= '2022-01-01' AND (valid_to IS NULL OR valid_to > '2022-01-01')
--   All history:      SELECT * FROM market.companies WHERE asx_code = 'BHP' ORDER BY valid_from
--
-- Transform script logic (transform_companies.py):
--   1. Load new values from staging.company_profile / staging.highlights / staging.shares_stats
--   2. Fetch current row WHERE asx_code = X AND is_current = TRUE
--   3. If no current row → INSERT new row (valid_from = today, valid_to = NULL, is_current = TRUE)
--   4. If current row exists AND SCD2-tracked fields unchanged → UPDATE non-tracked fields in place
--   5. If current row exists AND any SCD2-tracked field changed:
--        UPDATE SET valid_to = today - 1, is_current = FALSE WHERE id = old_id
--        INSERT new row (valid_from = today, valid_to = NULL, is_current = TRUE)
--
-- SCD2-tracked fields (trigger a new version):
--   gics_sector, gics_industry_group, gics_industry, gics_sub_industry,
--   stock_type, status, fiscal_year_end_month, is_reit, is_miner
--
-- Non-tracked fields (updated in-place on current row, no version created):
--   company_name, short_name, isin, website, employee_count, description,
--   is_asx20/50/100/200/300/all_ords (index membership changes too frequently for versioning)

-- ─── Step 1: Add surrogate PK and SCD2 columns ────────────────────────────────

-- Drop existing PK (asx_code) so we can reassign it
ALTER TABLE market.companies DROP CONSTRAINT IF EXISTS companies_pkey;

-- Add surrogate PK
ALTER TABLE market.companies ADD COLUMN IF NOT EXISTS id BIGSERIAL;

-- Add SCD2 columns
ALTER TABLE market.companies
    ADD COLUMN IF NOT EXISTS valid_from  DATE    NOT NULL DEFAULT CURRENT_DATE,
    ADD COLUMN IF NOT EXISTS valid_to    DATE    DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS is_current  BOOLEAN NOT NULL DEFAULT TRUE;

-- Make id the new primary key
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'market.companies'::regclass
          AND conname   = 'companies_pkey'
    ) THEN
        ALTER TABLE market.companies ADD PRIMARY KEY (id);
    END IF;
END $$;

-- ─── Step 2: Unique index — only one current row per stock ────────────────────

DROP INDEX IF EXISTS market.idx_companies_current_code;
CREATE UNIQUE INDEX idx_companies_current_code
    ON market.companies (asx_code)
    WHERE is_current = TRUE;

-- ─── Step 3: Supporting indexes ───────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_companies_asx_code
    ON market.companies (asx_code);

CREATE INDEX IF NOT EXISTS idx_companies_valid_range
    ON market.companies (asx_code, valid_from, valid_to);

-- ─── Step 4: Add data_as_of to financials tables ──────────────────────────────
-- Lightweight restatement tracking: records when we last loaded this row from EODHD.
-- Not a full SCD2 — financial periods (fiscal_year) are already the natural key.

ALTER TABLE financials.annual_pnl
    ADD COLUMN IF NOT EXISTS data_as_of TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE financials.annual_balance_sheet
    ADD COLUMN IF NOT EXISTS data_as_of TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE financials.annual_cashflow
    ADD COLUMN IF NOT EXISTS data_as_of TIMESTAMPTZ DEFAULT NOW();

-- ─── Step 5: Helper view for current companies (convenience) ──────────────────

CREATE OR REPLACE VIEW market.companies_current AS
    SELECT * FROM market.companies WHERE is_current = TRUE;

COMMENT ON VIEW market.companies_current IS
    'Current version of each company (is_current = TRUE). '
    'Use this view for all screener queries. '
    'Query market.companies directly for point-in-time or full history.';
