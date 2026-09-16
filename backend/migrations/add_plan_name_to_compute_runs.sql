-- Plan identity is immutable run metadata
-- =======================================
-- Plan-specific prerequisites replaced the single static REQUIRED_STAGES
-- tuple, and that left a gap between the layers.
--
-- composite_score requires the plan's stages at publication. The RESOLVER did
-- not: it validated every finalised run against the static tuple, which
-- includes yearly_compute -- a stage DAILY_CANONICAL deliberately never runs.
-- So a daily run would have published correctly and then been invisible to the
-- API, and the product would have quietly served an older snapshot while every
-- log line said the run succeeded.
--
-- The fix is not to teach the resolver to guess from which stage rows happen
-- to exist. It is to record which plan the run was opened under, once, and
-- have all three layers resolve requirements from that same identity:
--
--     driver       executes PLANS[run.plan_name].stages
--     publication  requires PLANS[run.plan_name].required
--     resolver     validates PLANS[run.plan_name].required
--
-- Existing runs
-- -------------
-- They are backfilled to LEGACY_CANONICAL, whose required set is the
-- historical tuple (yearly_compute, daily_compute, universe_build) those runs
-- were actually published under.
--
-- Not FULL_FUNDAMENTALS_CANONICAL: that plan now also requires
-- transform_prices, technical_compute, halfyearly_compute and
-- period_metrics_compute, and retroactively holding old runs to a contract
-- that did not exist when they published would unpublish every one of them --
-- taking the governed surface dark on deploy -- without any evidence that they
-- were wrong. LEGACY_CANONICAL records what they proved, which is the honest
-- claim. run_plans.py marks it non-executable, so it can never be chosen for
-- a new run.
--
-- The column is added WITH a default rather than backfilled by UPDATE: an
-- UPDATE would trip screener.compute_runs_are_immutable, and a migration that
-- has to disable an immutability trigger is a migration that has stopped
-- believing in it. PostgreSQL 11+ applies the default without rewriting.
-- The default is then dropped, so every future INSERT must state its plan.

BEGIN;

ALTER TABLE screener.compute_runs
    ADD COLUMN IF NOT EXISTS plan_name TEXT DEFAULT 'LEGACY_CANONICAL';

ALTER TABLE screener.compute_runs
    ALTER COLUMN plan_name DROP DEFAULT;

ALTER TABLE screener.compute_runs
    ALTER COLUMN plan_name SET NOT NULL;

COMMENT ON COLUMN screener.compute_runs.plan_name IS
    'The run plan this run was opened under. Immutable. Decides which stage '
    'evidence its publication requires and which the resolver validates. '
    'LEGACY_CANONICAL marks runs published before plans existed, under the '
    'historical three-stage contract.';

-- Plan identity joins the immutable set. A run whose plan could be edited
-- after the fact is a run whose publication contract could be lowered to match
-- whatever evidence it happened to produce -- which is the precise inversion
-- of what this evidence is for.
CREATE OR REPLACE FUNCTION screener.compute_runs_are_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.run_at               IS DISTINCT FROM OLD.run_at
    OR NEW.engine               IS DISTINCT FROM OLD.engine
    OR NEW.factor_model_version IS DISTINCT FROM OLD.factor_model_version
    OR NEW.plan_name            IS DISTINCT FROM OLD.plan_name
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

-- The resolver joins runs to their plan's requirements on every governed
-- query, so the lookup must not be a sequential scan of the run table.
CREATE INDEX IF NOT EXISTS idx_compute_runs_plan_name
    ON screener.compute_runs (plan_name);

COMMIT;
