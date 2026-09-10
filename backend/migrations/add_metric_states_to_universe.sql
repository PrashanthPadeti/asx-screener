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
