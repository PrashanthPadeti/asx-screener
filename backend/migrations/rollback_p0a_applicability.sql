-- Downgrade for the P0-A applicability migrations.
--
--     add_metric_states_to_universe.sql
--     add_benchmark_states_to_sector_benchmarks.sql
--
-- ============================================================================
-- READ THIS BEFORE RUNNING IT
-- ============================================================================
--
-- This is almost certainly NOT the right response to a problem after the
-- migration has committed. Both migrations are additive: new nullable columns,
-- a new table, indexes, a trigger. Nothing existing is altered or dropped, and
-- an application that does not know about the new columns behaves exactly as
-- it did before them.
--
-- So the safe rollback for a migration-only fault is to roll the APPLICATION
-- back and leave this schema in place, dormant. Dropping columns under
-- incident pressure converts a reversible situation into an irreversible one,
-- and it destroys the sidecar and run evidence that would explain what went
-- wrong.
--
-- Reach for this file only when the schema itself must be removed — a failed
-- rollout being abandoned outright, or a restore into a clean database. It
-- exists so that decision is a documented option rather than something
-- improvised at 2am.
--
-- What is destroyed and is not recoverable from the remaining tables:
--
--     screener.universe.metric_states          every applicability state,
--                                              including the forensic
--                                              observed values
--     screener.universe.compute_run_id         all row-to-run attribution
--     screener.compute_runs                    all source-health evidence,
--                                              which is immutable by design
--                                              precisely so it cannot be lost
--     market.sector_benchmarks.*               benchmark states and their
--                                              run attribution
--
-- Take the snapshot (scripts/p0a_snapshot.sh) before you run this, not after.
--
-- Run inside a transaction so a partial drop cannot happen:
--
--     BEGIN;
--     \i migrations/rollback_p0a_applicability.sql
--     -- inspect, then COMMIT or ROLLBACK
--
-- ============================================================================

-- ── market.sector_benchmarks ────────────────────────────────────────────────
-- First, because it references nothing the others depend on.

DROP INDEX IF EXISTS market.idx_sector_benchmarks_compute_run;

ALTER TABLE market.sector_benchmarks
    DROP COLUMN IF EXISTS compute_run_id;

ALTER TABLE market.sector_benchmarks
    DROP COLUMN IF EXISTS benchmark_states;


-- ── screener.universe ───────────────────────────────────────────────────────
-- compute_run_id carries the foreign key, so it must go before the table it
-- references. Dropping the column removes the constraint with it; CASCADE on
-- the table would work too but would hide what it took with it.

DROP INDEX IF EXISTS screener.idx_universe_compute_run;

ALTER TABLE screener.universe
    DROP COLUMN IF EXISTS compute_run_id;

DROP INDEX IF EXISTS screener.idx_universe_metric_states;

ALTER TABLE screener.universe
    DROP COLUMN IF EXISTS metric_states;


-- ── screener.compute_runs ───────────────────────────────────────────────────
-- The trigger and its function are dropped explicitly rather than relying on
-- the table drop, so that running this file against a database where the
-- table was already removed still leaves nothing behind.

DROP TRIGGER IF EXISTS trg_compute_runs_immutable ON screener.compute_runs;

DROP TABLE IF EXISTS screener.compute_runs;

DROP FUNCTION IF EXISTS screener.compute_runs_are_immutable();


-- ── Verification ────────────────────────────────────────────────────────────
-- Run after COMMIT. Every count must be zero.
--
--   SELECT count(*) FROM information_schema.columns
--    WHERE (table_schema, table_name, column_name) IN (
--          ('screener','universe','metric_states'),
--          ('screener','universe','compute_run_id'),
--          ('market','sector_benchmarks','benchmark_states'),
--          ('market','sector_benchmarks','compute_run_id'));
--
--   SELECT count(*) FROM information_schema.tables
--    WHERE table_schema='screener' AND table_name='compute_runs';
--
--   SELECT count(*) FROM information_schema.routines
--    WHERE routine_schema='screener'
--      AND routine_name='compute_runs_are_immutable';
--
-- The application must be on a revision that predates the P0-A projection
-- work before this runs, or every governed request will fail: the projector
-- reads metric_states, and resolve_snapshot queries screener.compute_runs.
-- It degrades to 503 rather than 500 for a missing table, but that is a
-- designed pre-rollout state, not a state to leave production in.
