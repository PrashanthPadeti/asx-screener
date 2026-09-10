-- Carry applicability across the persistence boundary.
--
-- A nullable numeric column cannot say *why* it is null, and the five reasons
-- have different downstream behaviour: SOURCE_UNHEALTHY forbids composite
-- reweighting and blocks a canonical AlphaFive refresh, DOMAIN permits both.
-- Collapsing them into NULL undoes the applicability work upstream.
--
-- Sparse sidecar rather than a status column per metric: screener.universe
-- already carries 225 columns, and shadowing each one is a tax rather than a
-- design. An entry exists only for a metric that is NOT applicable, so on a
-- typical row the payload is small or empty.
--
--   {"altman_z_score":   {"state":"not_meaningful","cause":"domain",
--                         "reason":"Altman's model excludes financial ..."},
--    "grossed_up_yield": {"state":"unavailable","cause":"source_unhealthy",
--                         "reason":"dividend feed incomplete — latest ..."}}
--
-- The rule that makes sparseness safe: a NULL numeric column must never be the
-- only signal. Absent from metric_states means applicable, so a NULL value
-- with no entry is a contract violation. compute.engine.metric_states
-- .violations() is the check; it belongs in CI over a sample of rows.
--
-- Applied as part of the P0-A rollout, before the recompute step — a row
-- written by the new engine needs somewhere to put its states, and a row
-- written by the old one simply has an empty payload and reads as it does
-- today.

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS metric_states JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN screener.universe.metric_states IS
    'Sparse applicability sidecar: metric -> {state, cause, reason} for every '
    'metric that is not applicable. Absent means applicable. A NULL numeric '
    'column with no entry here is a contract violation.';

-- Only rows that actually carry a suppressed metric are worth indexing, and
-- jsonb_path_ops is the smaller operator class for containment queries such as
-- "which companies have a source-unhealthy metric".
CREATE INDEX IF NOT EXISTS idx_universe_metric_states
    ON screener.universe USING gin (metric_states jsonb_path_ops)
    WHERE metric_states <> '{}'::jsonb;


-- Run-level source health. Recorded once per compute run rather than per
-- company: a dividend feed 38 days behind is a fact about the exchange, and
-- writing it onto 2,117 rows invites it to disagree with itself mid-run.
--
-- factor_model_version extends the convention multibagger_version already
-- established, so a derived result can be checked against the contract that
-- produced it instead of being trusted because it looks recent.

CREATE TABLE IF NOT EXISTS screener.compute_runs (
    id                   BIGSERIAL PRIMARY KEY,
    run_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    engine               TEXT        NOT NULL,
    factor_model_version VARCHAR(32),
    unhealthy_sources    TEXT[]      NOT NULL DEFAULT '{}',
    detail               JSONB       NOT NULL DEFAULT '{}'::jsonb,
    rows_written         INTEGER
);

CREATE INDEX IF NOT EXISTS idx_compute_runs_run_at
    ON screener.compute_runs (run_at DESC);

COMMENT ON TABLE screener.compute_runs IS
    'One row per compute run. unhealthy_sources names the feeds that were not '
    'usable, so a consumer can tell "this company pays no dividend" from "we '
    'could not compute a dividend" without inspecting every metric.';


-- Provenance. screener.universe is mutable and rewritten every run, so
-- without an explicit run identifier the chain
--
--     value + metric_state  ->  ?  ->  compute run  ->  source health
--
-- can only be closed by matching timestamps, which stops working the moment
-- two runs land close together or a later run partially overwrites an earlier
-- one. A row can then say SOURCE_UNHEALTHY while the feed observation that
-- justified it is two runs in the past and unrecoverable.
--
-- Nullable because rows written before this migration genuinely have no run
-- to point at. That is the honest state, and it is distinguishable from a
-- row that does — which a default of 0 or a backfilled guess would destroy.

ALTER TABLE screener.universe
    ADD COLUMN IF NOT EXISTS compute_run_id BIGINT
        REFERENCES screener.compute_runs (id);

CREATE INDEX IF NOT EXISTS idx_universe_compute_run
    ON screener.universe (compute_run_id);

COMMENT ON COLUMN screener.universe.compute_run_id IS
    'The run that produced this row. Joins to screener.compute_runs for the '
    'factor model version and the source-health evidence behind any '
    'SOURCE_UNHEALTHY state. NULL means the row predates run attribution — '
    'never backfill it with a guess.';


-- A run that rows point at must not change underneath them. If the recorded
-- feed watermark or model version can be edited in place, the lineage
-- guarantee is only as good as nobody having run an UPDATE — and a row
-- claiming SOURCE_UNHEALTHY could end up joined to evidence that no longer
-- says the feed was broken. Corrections happen by writing a new run and
-- repointing rows, which leaves both versions visible.
--
-- rows_written is deliberately excluded: it is a tally the run itself fills in
-- on completion, not evidence a row depends on. It is the SOLE post-insert
-- mutable field, and it may move from NULL to its final count exactly once,
-- while the run is executing.
--
-- The stricter contract — immutable again once the run is finalised — needs a
-- run-status concept, and this schema has none. Inventing a state machine for
-- one tally inside a correctness slice would be the wrong trade. Recorded here
-- so it is a known gap rather than an oversight: if a run lifecycle is added
-- later, that is where rows_written should be locked on completion.

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
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_compute_runs_immutable ON screener.compute_runs;
CREATE TRIGGER trg_compute_runs_immutable
    BEFORE UPDATE ON screener.compute_runs
    FOR EACH ROW EXECUTE FUNCTION screener.compute_runs_are_immutable();


-- The universe write is one statement. Numeric columns, metric_states and
-- compute_run_id move together or not at all:
--
--     UPDATE screener.universe SET
--         grossed_up_yield = %(grossed_up_yield)s, ...,
--         metric_states    = %(metric_states)s::jsonb,
--         compute_run_id   = %(compute_run_id)s
--      WHERE asx_code = %(asx_code)s
--
-- Application-level coherence (compute.engine.metric_states.persist_row) is
-- necessary and not sufficient: a crash between two statements leaves exactly
-- the contradictory state violations() exists to catch, on a row that was
-- correct a moment earlier.


-- Rollout gate. Applying this migration does NOT make the table healthy:
-- every legacy row with a nullable governed metric and no sidecar entry is
-- now, correctly, a contract violation. That is the point — it is the
-- evidence that the canonical writer has not yet been through.
--
--     migration
--       -> recompute through the canonical writer
--       -> compute.engine.metric_states.violations() == 0 for the governed set
--       -> enable consumers that rely on the new semantics
--
-- Do NOT backfill metric_states with '{}' to make the validator green. That
-- encodes "applicable" without evidence and destroys the sidecar's purpose.
