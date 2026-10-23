-- Company profile fields, and the date they were obtained
-- =======================================================
-- Measured 23 Oct 2026 across 2,589 current companies:
--
--     employee_count       0 / 2589   EMPTY
--     listing_date         0 / 2589   EMPTY
--     shares_outstanding   0 / 2589   EMPTY
--     logo_url             0 / 2589   EMPTY
--     state, abn, acn      0 / 2589   EMPTY
--     description       1818 / 2589   70.2%
--     website           1799 / 2589   69.5%
--
-- The columns exist; nothing fills them. `asx_companies.py` writes only
-- company_name, company_type and status. The rest came from manual scripts
-- under scripts/eodhd/v2/ that are not scheduled, which is why updated_at
-- spans 23 June to 22 October with no pattern. That is why the live company
-- page reads "EMPLOYEES —" and "LISTED —" for every company.
--
-- This adds the fields the provider serves and we do not yet store, plus
-- the one that matters most:
--
--     profile_updated_at
--
-- Without it a profile cannot be dated, and an undated profile is one that
-- can go stale silently -- the defect this codebase has spent weeks
-- removing from price series. A page that says "1,175 employees" without
-- saying when, eventually says it for years.

ALTER TABLE market.companies
    ADD COLUMN IF NOT EXISTS officers            JSONB,
    ADD COLUMN IF NOT EXISTS head_office_address TEXT,
    ADD COLUMN IF NOT EXISTS phone               TEXT,
    ADD COLUMN IF NOT EXISTS ipo_date            DATE,
    ADD COLUMN IF NOT EXISTS lei                 TEXT,
    ADD COLUMN IF NOT EXISTS profile_updated_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS profile_source      TEXT;

-- The refresh selects the least recently refreshed companies first, so this
-- is the index that query lives on. NULLS FIRST because a company never
-- profiled is the most urgent, not the least.
CREATE INDEX IF NOT EXISTS companies_profile_staleness_idx
    ON market.companies (profile_updated_at NULLS FIRST)
    WHERE is_current;

-- A profile date without a source cannot be interpreted: "as of 23 October"
-- means something different depending on who said so. The pair is one fact.
ALTER TABLE market.companies
    DROP CONSTRAINT IF EXISTS companies_profile_dated_has_source;
ALTER TABLE market.companies
    ADD CONSTRAINT companies_profile_dated_has_source
    CHECK (profile_updated_at IS NULL OR profile_source IS NOT NULL);

COMMENT ON COLUMN market.companies.profile_updated_at IS
    'When this company profile was last obtained from its source. NULL means '
    'never obtained -- which is different from "obtained and the provider had '
    'nothing", and the two must not be rendered the same way.';

COMMENT ON COLUMN market.companies.officers IS
    'Officers as the provider holds them, stored verbatim. Currency is '
    'profile_updated_at; the provider does not date individual fields.';
