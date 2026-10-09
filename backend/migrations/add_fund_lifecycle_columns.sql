-- Fund lifecycle columns — ADDITIVE ONLY, no lifecycle decisions
-- ============================================================================
-- `market.funds.is_active` already existed, was written TRUE on every seed,
-- and was never updated: the seed's ON CONFLICT clause omits the column. The
-- flag existed; the transition did not. So a fund that stopped trading was
-- indistinguishable from a fund someone forgot to list, and eight ETFs served
-- June prices for four months while two dead tickers (DIV, delisted
-- 2020-05-21; PMC, ceased ~2026-02-02) were fetched every day.
--
-- This migration adds the vocabulary for a retirement. It records NO
-- retirement.
--
--   * every column is NULLABLE with no default
--   * no row is updated; existing is_active values are untouched
--   * no fund is retired, and no successor is linked
--
-- In particular PMC is NOT linked to GLS here. Their ISINs differ
-- (AU000000PMC2 vs AU0000440166), so continuity is unproven and history must
-- not be consolidated on vendor data. That decision waits on the ASX
-- announcement.
--
-- Idempotent: safe to re-run. IF NOT EXISTS on every statement, and because
-- nothing is written, a second run cannot overwrite a lifecycle decision
-- recorded between runs.
--
--   psql "$DATABASE_URL" -f migrations/add_fund_lifecycle_columns.sql

BEGIN;

-- When the security stopped trading. The LAST OBSERVED PRICE is not this
-- date -- it establishes the last trade seen, not the official delisting --
-- so this is populated from the ASX announcement, never inferred from
-- market.fund_prices.
ALTER TABLE market.funds
    ADD COLUMN IF NOT EXISTS retired_at DATE;

-- delisted | renamed | merged | superseded. Free text rather than an enum so
-- a corporate action nobody anticipated can be recorded accurately instead
-- of being forced into the nearest existing word.
ALTER TABLE market.funds
    ADD COLUMN IF NOT EXISTS retired_reason TEXT;

-- The security that continues this one, where a corporate action created
-- one. NOT a foreign key: a successor may not be in market.funds yet, and a
-- constraint that forces the successor to be seeded first would make the
-- correct ordering impossible to record.
ALTER TABLE market.funds
    ADD COLUMN IF NOT EXISTS successor_code TEXT;

-- A reason without a date, or a successor without a date, is a half-recorded
-- retirement -- which reads as "retired" to some queries and "active" to
-- others. Either the transition is recorded or it is not.
ALTER TABLE market.funds
    DROP CONSTRAINT IF EXISTS funds_retirement_is_complete;
ALTER TABLE market.funds
    ADD CONSTRAINT funds_retirement_is_complete
    CHECK (
        (retired_at IS NULL AND retired_reason IS NULL AND successor_code IS NULL)
        OR
        (retired_at IS NOT NULL AND retired_reason IS NOT NULL)
    );

-- Eligibility is read on every producer run: active and not retired.
CREATE INDEX IF NOT EXISTS funds_eligible_idx
    ON market.funds (asx_code)
    WHERE is_active = TRUE AND retired_at IS NULL;

COMMIT;

-- Verification (run separately; this file writes no rows):
--
--   SELECT count(*) FILTER (WHERE retired_at IS NOT NULL)     AS retired,
--          count(*) FILTER (WHERE is_active)                  AS active,
--          count(*)                                           AS total
--     FROM market.funds;
--
-- Expected immediately after this migration: retired 0, active 55, total 55
-- -- unchanged from before it, which is the point.
