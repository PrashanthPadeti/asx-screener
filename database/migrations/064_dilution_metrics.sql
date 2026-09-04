-- ─────────────────────────────────────────────────────────────
-- 064 — Dilution metrics
-- ─────────────────────────────────────────────────────────────
-- Derived from market.shares_history. Magnitude alone is not enough for a
-- compounding score: a company issuing 20 percent once to fund an acquisition
-- and one issuing 6-8 percent every year to fund operations produce a similar
-- three-year CAGR, yet the second is the far worse signal. Persistence is
-- therefore stored separately from magnitude.
--
-- Every metric is NULL unless the underlying window is trustworthy. Validation
-- of the raw history found share counts of 400, 1,800 and 2,500 for listed
-- companies, and jumps of six orders of magnitude — consistent with
-- consolidations that market.splits does not record (it covers 861 of ~2,100
-- stocks). A consolidation misread as a 99 percent buyback would score a
-- company 100 on dilution, the most damaging error available in this
-- component, so an implausible step voids the whole window rather than being
-- clamped into a plausible-looking number.

ALTER TABLE screener.universe
    -- Annualised change in share count across the window. Positive is dilution.
    ADD COLUMN IF NOT EXISTS shares_outstanding_cagr_3y NUMERIC(10,4),
    -- Most recent year-on-year change, to catch a raise the CAGR would smooth.
    ADD COLUMN IF NOT EXISTS shares_change_1y           NUMERIC(10,4),
    -- Count of materially dilutive years in the window: persistence, not size.
    ADD COLUMN IF NOT EXISTS dilution_years_3y          SMALLINT,
    -- Largest single-year issuance, to expose a one-off capital raising.
    ADD COLUMN IF NOT EXISTS max_annual_dilution_3y     NUMERIC(10,4),
    -- Observations backing the window, so sparse history cannot imply precision.
    ADD COLUMN IF NOT EXISTS shares_history_years       SMALLINT;

COMMENT ON COLUMN screener.universe.shares_outstanding_cagr_3y IS
    'Annualised share-count change over the window, as a ratio (0.05 = 5 percent '
    'per year of dilution). Negative means the count shrank. NULL when any '
    'year-on-year step in the window is implausible, which usually indicates an '
    'unrecorded consolidation rather than genuine issuance.';

COMMENT ON COLUMN screener.universe.dilution_years_3y IS
    'Number of years in the window where the share count grew more than 2 '
    'percent. Distinguishes a serial issuer from a single capital event.';

COMMENT ON COLUMN screener.universe.shares_history_years IS
    'Observations used. Fewer than 3 means no CAGR is published.';
