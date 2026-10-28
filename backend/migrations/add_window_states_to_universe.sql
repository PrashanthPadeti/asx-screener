-- Where the reason a price window is empty waits to become contract state.
--
-- technical_compute records why each window is absent -- no close near the
-- window's start, too little history, an unreconciled corporate action
-- inside it, or a value past the column's ceiling -- into
-- market.daily_metrics.metric_states. The canonical writer needs that reason
-- to build the sidecar entry for a governed metric, and it reads
-- screener.universe, not daily_metrics.
--
-- The obvious route was for build_screener_universe to carry it straight
-- into screener.universe.metric_states. That is forbidden, and the
-- orchestration contract says so plainly:
--
--     the builder may DESTROY a canonical claim; it may never MAKE one
--
-- metric_states and compute_run_id are canonical state. The builder has
-- assessed nothing -- it copies provisional values from upstream tables --
-- so writing a sidecar there would be an attribution it did not compute, and
-- a row would look assessed while nothing had assessed it. The guard
-- test_the_universe_builder_revokes_canonical_state_and_never_claims_it
-- catches it, and caught it here.
--
-- So the reason arrives in its own column, with exactly the standing of the
-- return_1y value sitting beside it: produced upstream, carried here
-- unassessed, and read by the canonical writer, which turns it into a real
-- sidecar entry and writes metric_states itself, in one statement, as it
-- already does for every other governed metric.
--
--   market.daily_metrics.metric_states   produced, per row, by the engine
--   screener.universe.window_states      carried, provisional, unassessed
--   screener.universe.metric_states      canonical, written only by the
--                                        canonical writer
--
-- Same payload shape in all three, so no reader needs a second vocabulary:
--
--   {"return_1y": {"state":"insufficient_data",
--                  "cause":"insufficient_history",
--                  "reason":"no close within 7 days of 2025-10-27"}}
--
-- Nullable, no default, as with every sidecar on this project: NULL means
-- the row was never assessed, '{}' means assessed with nothing to record.
-- A default would assert that every existing row had been examined and found
-- clean, which is false -- they were never looked at.

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS window_states JSONB;

COMMENT ON COLUMN screener.universe.window_states IS
    'Provisional, per-metric reasons for absent price windows, carried from '
    'market.daily_metrics.metric_states by build_screener_universe. NOT '
    'canonical state: the builder assesses nothing and may never write '
    'metric_states, which belongs to the canonical writer. The writer reads '
    'this column, rebuilds each window Assessment from it, and emits the real '
    'sidecar. NULL means never assessed; ''{}'' means assessed and clean.';
