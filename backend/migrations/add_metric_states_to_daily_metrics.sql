-- The reason a return is absent exists, and currently dies where it is known.
--
-- technical_compute knows exactly why each window is empty. It distinguishes
-- three cases already:
--
--   no close within the window's grace     the series skips the anchor date
--   series shorter than the window         not enough history to measure it
--   withheld over an unreconciled split    a corporate action sits in the
--                                          window and cannot be adjusted out
--
-- All three are logged ("MRD: 14102 metric value(s) withheld") and then
-- dropped. market.daily_metrics has fixed numeric columns, so an absent
-- window can only be written as NULL, and by the time build_screener_universe
-- reads the row the three cases are indistinguishable.
--
-- They are not the same fact and they do not have the same remediation. The
-- first two are properties of the company's trading; the third is a property
-- of our own data, and it is the one that should make somebody go and
-- reconcile a split.
--
-- Why the sidecar lives on this table rather than being derived downstream:
-- the alternative is build_screener_universe re-deriving the reason from the
-- price series, which means a second implementation of the anchor rule that
-- can disagree with the first. Evidence travels with the value it explains.
-- Same row, same write, so no reader can observe a number whose state has not
-- yet been updated.
--
-- Shape matches screener.universe.metric_states exactly -- metric -> {state,
-- cause, reason, observed} -- because a reader that can interpret one must
-- not need a second vocabulary for the other:
--
--   {"return_1y": {"state":"insufficient_data",
--                  "cause":"insufficient_history",
--                  "reason":"no close within 7 days of 2025-10-27"},
--    "return_6m": {"state":"unavailable",
--                  "cause":"source_missing",
--                  "reason":"unreconciled split 2024-12-16 in window"}}
--
-- Sparse, like the company sidecar and unlike the benchmark one: an entry
-- appears only where there is something to say beyond the number. An
-- APPLICABLE window is represented by its value and by the absence of an
-- entry, which is what keeps the payload proportional to the problem rather
-- than to 400 days times six windows.

-- Nullable, no default, following add_metric_states_to_universe.sql:
--   NULL  this row was written before the contract existed, or by a producer
--         that does not assess -- nothing was ever decided about it
--   '{}'  assessed, and every governed window on this row is applicable
--
-- A default of '{}' would erase that distinction across every historical row
-- in one statement, asserting that rows written months ago were assessed and
-- found clean. They were not; they were never looked at. On a hypertable this
-- also keeps the change metadata-only rather than a rewrite.

ALTER TABLE market.daily_metrics
    ADD COLUMN IF NOT EXISTS metric_states JSONB;

COMMENT ON COLUMN market.daily_metrics.metric_states IS
    'Per-metric state for the calendar price windows: metric -> {state, cause, '
    'reason, observed}. Sparse -- an entry exists only for a metric whose '
    'state is not APPLICABLE, so a populated numeric column must never sit '
    'beside an entry, and a NULL numeric column with no entry is a contract '
    'violation rather than a default. NULL (not ''{}'') means the row was '
    'never assessed: written before FACTOR_MODEL_V3 or by a producer that '
    'does not assess. Same vocabulary as screener.universe.metric_states.';
