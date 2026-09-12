-- Reporting history as an observation
-- ===================================
-- Separate from add_metric_states_to_universe.sql deliberately. That migration
-- has been reviewed and staged against a specific freeze window; this one is a
-- later finding and arrives on its own rather than by amending a frozen file.
--
-- What it adds is not a metric. annual_periods is an observation in the same
-- class as total_equity — an input gate 2 reads, never a value served to a
-- customer, and so not a member of any GOVERNED_METRICS set and not a field on
-- ScreenerRow.
--
-- Why it is needed: an avg_*_ny metric claims the mean of exactly n annual
-- observations from a contiguous window. When that cannot be satisfied the
-- value is absent, and the absence has two causes that clear by different
-- means:
--
--     the required fiscal years do not exist   INSUFFICIENT_HISTORY
--     the years exist, an observation is NULL  SOURCE_MISSING
--
-- average_over() knows which case it hit and cannot say so: the numeric column
-- carries no state. Without this count every such absence reports as
-- SOURCE_MISSING — which for roic would blame our feed for 537 of 1,594
-- three-year windows that are genuinely short, and for a company listed two
-- years ago would blame the feed for the fact that it has not existed long
-- enough. Both of those send an operator to look in the wrong place.
--
-- NULL is a real state here and the column takes no default: a company with no
-- financials.annual_pnl row at all has no FY0 to anchor a run to, and its
-- count is unknown rather than zero. A DEFAULT 0 would assert of every legacy
-- row that we had checked and found no reporting history — the same error the
-- metric_states migration avoided by refusing DEFAULT '{}'.

BEGIN;

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS annual_periods SMALLINT;

COMMENT ON COLUMN screener.universe.annual_periods IS
    'Consecutive annual reporting periods ending at FY0, counted over '
    'financials.annual_pnl — the same row set the averaging series is drawn '
    'from. An observation for applicability gate 2, not a served metric. '
    'NULL means unknown (no FY0 anchor), never zero.';

COMMIT;

-- Rollback:
--   ALTER TABLE screener.universe DROP COLUMN IF EXISTS annual_periods;
--
-- Dropping it is safe in the sense that nothing reads it as a metric. It is
-- not safe in the sense that the cause distinction silently reverts: every
-- short window goes back to reporting SOURCE_MISSING. Drop it only together
-- with the code that supplies periods_available.
