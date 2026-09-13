-- Run lifecycle: stage evidence and a publication boundary
-- ========================================================
-- add_metric_states_to_universe.sql recorded this as a known gap:
--
--     "The stricter contract -- immutable again once the run is finalised --
--      needs a run-status concept, and this schema has none. ... if a run
--      lifecycle is added later, that is where rows_written should be locked
--      on completion."
--
-- This is that lifecycle. It weakens nothing: screener.compute_runs keeps its
-- immutability trigger, and create_run() still happens BEFORE the work, so
-- every prerequisite result attaches to the identity under which the work
-- actually occurred rather than to a label applied afterwards.
--
-- What it makes machine-enforced is the thing a log line could not:
--
--     a run cannot be published unless every required stage proved it
--     covered its own source population.
--
-- The first discovery rebuild is why. yearly_compute reported
-- "1626 stocks | 0 skipped | 0 errors" -- clean by every signal it emitted --
-- while leaving 2,954 rows with a live source untouched, because its selection
-- excluded 224 delisted codes that build_screener_universe nonetheless reads.
-- Loop counters describe only what the loop was admitted to see. The evidence
-- has to compare an independently derived expected population against the
-- population actually written.
--
-- Two failure classes, deliberately named apart, because they are not equally
-- serious:
--
--     missing source   the source row is gone. Legitimate unavailability may
--                      result, and the metric says so.
--     missed source    the source row is present and the run did not rewrite
--                      it. A prior value stays readable and looks current.
--                      This is a run-integrity failure.

BEGIN;

-- ── Stage evidence ───────────────────────────────────────────────────────────
-- Append-only, and terminal. A stage computes everything, then inserts exactly
-- one row saying success or failed. There is no mutable status to race with,
-- and no history to rewrite: a retry is a NEW run, not an edit to this one.
-- If retries within a run ever become operationally necessary, the key grows
-- an attempt_no and each attempt stays immutable -- but that complexity is not
-- introduced without evidence it is needed.
CREATE TABLE IF NOT EXISTS screener.compute_run_stages (
    run_id            BIGINT      NOT NULL
                          REFERENCES screener.compute_runs(id) ON DELETE RESTRICT,
    stage_name        TEXT        NOT NULL,
    status            TEXT        NOT NULL
                          CHECK (status IN ('success', 'failed')),

    -- The positive form. Not "missing_count = 0" but two populations that must
    -- be equal, derived independently of each other.
    expected_count    INTEGER     NOT NULL,
    written_count     INTEGER     NOT NULL,
    missing_count     INTEGER     NOT NULL,   -- expected - written
    extra_count       INTEGER     NOT NULL,   -- written - expected, also suspicious

    -- Deterministic hashes over the sorted key sets, so equality is provable
    -- after the fact without storing thousands of codes on every run.
    expected_set_hash TEXT        NOT NULL,
    written_set_hash  TEXT        NOT NULL,

    -- A bounded sample of missing/extra keys, plus whatever else the stage
    -- wants on the record. Bounded on purpose: the hashes carry the proof,
    -- the sample carries the diagnosis.
    details           JSONB       NOT NULL DEFAULT '{}'::jsonb,

    completed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (run_id, stage_name)
);

COMMENT ON TABLE screener.compute_run_stages IS
    'Append-only evidence that a prerequisite stage covered its own source '
    'population. status=success requires expected_set_hash = written_set_hash. '
    'One terminal row per (run_id, stage_name); a retry is a new run.';


-- ── Publication boundary ─────────────────────────────────────────────────────
-- The existence of a row here is what makes a run eligible to be served. It is
-- written last, by the canonical writer, only after the prerequisite stages
-- succeeded and the persisted rows validated.
CREATE TABLE IF NOT EXISTS screener.compute_run_finalizations (
    run_id                 BIGINT      PRIMARY KEY
                               REFERENCES screener.compute_runs(id) ON DELETE RESTRICT,
    validated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rows_written           INTEGER     NOT NULL,
    -- Recorded rather than assumed. A finalisation asserting zero is a claim
    -- that can be checked against the rows themselves later.
    persistence_violations INTEGER     NOT NULL,
    snapshot_id            TEXT,
    details                JSONB       NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE screener.compute_run_finalizations IS
    'One row per published run. Its presence is the publication boundary: a '
    'resolver requires this plus a success row for every required stage. '
    'Append-only -- an unpublishable run stays unfinalised rather than being '
    'downgraded.';


-- ── Both tables are evidence, so neither may be edited ───────────────────────
CREATE OR REPLACE FUNCTION screener.run_evidence_is_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        '%.% is append-only evidence: a stage or finalisation records what was '
        'true when it was written. Start a new compute run rather than '
        'changing history underneath an existing run identity.',
        TG_TABLE_SCHEMA, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_stages_append_only ON screener.compute_run_stages;
CREATE TRIGGER trg_stages_append_only
    BEFORE UPDATE OR DELETE ON screener.compute_run_stages
    FOR EACH ROW EXECUTE FUNCTION screener.run_evidence_is_append_only();

DROP TRIGGER IF EXISTS trg_finalizations_append_only ON screener.compute_run_finalizations;
CREATE TRIGGER trg_finalizations_append_only
    BEFORE UPDATE OR DELETE ON screener.compute_run_finalizations
    FOR EACH ROW EXECUTE FUNCTION screener.run_evidence_is_append_only();


-- ── Close the gap the earlier migration recorded ─────────────────────────────
-- rows_written was the sole mutable field, and could move from NULL to its
-- final count "while the run is executing" -- with nothing defining when
-- executing ends. Finalisation defines it. Once a finalisation row exists the
-- tally is locked like everything else on the run.
CREATE OR REPLACE FUNCTION screener.compute_runs_are_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.run_at               IS DISTINCT FROM OLD.run_at
    OR NEW.engine               IS DISTINCT FROM OLD.engine
    OR NEW.factor_model_version IS DISTINCT FROM OLD.factor_model_version
    OR NEW.unhealthy_sources    IS DISTINCT FROM OLD.unhealthy_sources
    OR NEW.detail               IS DISTINCT FROM OLD.detail THEN
        RAISE EXCEPTION
            'screener.compute_runs id=% is immutable evidence; write a new '
            'run and repoint rows rather than editing this one', OLD.id;
    END IF;

    IF NEW.rows_written IS DISTINCT FROM OLD.rows_written
       AND EXISTS (SELECT 1 FROM screener.compute_run_finalizations f
                    WHERE f.run_id = OLD.id) THEN
        RAISE EXCEPTION
            'screener.compute_runs id=% is finalised; rows_written is part of '
            'the published evidence and cannot be restated', OLD.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ── Ownership, derived rather than assumed ───────────────────────────────────
-- The same pattern the metric_states migration needed: objects created by
-- postgres are owned by postgres, and the application role then cannot read
-- them. That failure masqueraded as a 503 and let Gate A pass while the
-- contract table was unreadable.
DO $$
DECLARE
    target_owner TEXT;
BEGIN
    SELECT tableowner INTO target_owner
      FROM pg_tables WHERE schemaname = 'screener' AND tablename = 'universe';

    IF target_owner IS NULL THEN
        RAISE EXCEPTION 'screener.universe not found; cannot derive an owner';
    END IF;

    EXECUTE format('ALTER TABLE screener.compute_run_stages OWNER TO %I', target_owner);
    EXECUTE format('ALTER TABLE screener.compute_run_finalizations OWNER TO %I', target_owner);
    EXECUTE format('ALTER FUNCTION screener.run_evidence_is_append_only() OWNER TO %I', target_owner);
    EXECUTE format('ALTER FUNCTION screener.compute_runs_are_immutable() OWNER TO %I', target_owner);

    RAISE NOTICE 'run lifecycle objects owned by %', target_owner;
END $$;

COMMIT;

-- Rollback:
--   DROP TRIGGER IF EXISTS trg_finalizations_append_only ON screener.compute_run_finalizations;
--   DROP TRIGGER IF EXISTS trg_stages_append_only ON screener.compute_run_stages;
--   DROP TABLE IF EXISTS screener.compute_run_finalizations;
--   DROP TABLE IF EXISTS screener.compute_run_stages;
--   DROP FUNCTION IF EXISTS screener.run_evidence_is_append_only();
-- and restore the previous compute_runs_are_immutable() body, which omits the
-- finalisation check.
--
-- Dropping these removes the publication boundary. A resolver that required
-- them will then find no eligible run at all, which fails closed -- but the
-- rollback must be paired with reverting the resolver, or nothing is servable.
