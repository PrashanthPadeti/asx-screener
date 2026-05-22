-- ============================================================
-- Migration 055: Pipeline Monitoring Tables
-- ============================================================
-- Creates three tables for full observability:
--   market.pipeline_runs       — one row per daily pipeline execution
--   market.pipeline_step_runs  — per-step detail (14 steps per run)
--   market.scheduler_job_runs  — APScheduler job run history
-- ============================================================

-- ── 1. Pipeline Runs ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.pipeline_runs (
    id               SERIAL        PRIMARY KEY,
    run_date         DATE          NOT NULL,
    pipeline_name    VARCHAR(50)   NOT NULL DEFAULT 'daily',
    started_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ,
    status           VARCHAR(20)   NOT NULL DEFAULT 'running',
        -- running | success | failed | partial
    total_steps      INTEGER       NOT NULL DEFAULT 14,
    steps_completed  INTEGER       NOT NULL DEFAULT 0,
    failed_step      INTEGER,
    failed_step_name VARCHAR(100),
    error_message    TEXT,
    duration_seconds INTEGER,
    UNIQUE (run_date, pipeline_name)
);

COMMENT ON TABLE  market.pipeline_runs IS 'One row per daily pipeline execution — tracks overall status and timing';
COMMENT ON COLUMN market.pipeline_runs.status          IS 'running | success | failed | partial';
COMMENT ON COLUMN market.pipeline_runs.steps_completed IS 'Number of steps that completed successfully';
COMMENT ON COLUMN market.pipeline_runs.failed_step     IS 'Step number that caused the failure (NULL if success)';

-- ── 2. Pipeline Step Runs ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.pipeline_step_runs (
    id               SERIAL        PRIMARY KEY,
    run_id           INTEGER       NOT NULL REFERENCES market.pipeline_runs(id) ON DELETE CASCADE,
    run_date         DATE          NOT NULL,
    step_number      INTEGER       NOT NULL,
    step_name        VARCHAR(100)  NOT NULL,
    started_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ,
    status           VARCHAR(20)   NOT NULL DEFAULT 'running',
        -- running | success | failed | skipped
    duration_seconds NUMERIC(10,2),
    error_message    TEXT,
    UNIQUE (run_id, step_number)
);

COMMENT ON TABLE market.pipeline_step_runs IS 'Per-step detail for each pipeline run — 14 steps per daily run';

-- ── 3. Scheduler Job Runs ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market.scheduler_job_runs (
    id               SERIAL        PRIMARY KEY,
    run_date         DATE          NOT NULL,
    job_id           VARCHAR(50)   NOT NULL,
    job_name         VARCHAR(100)  NOT NULL,
    started_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    completed_at     TIMESTAMPTZ,
    status           VARCHAR(20)   NOT NULL DEFAULT 'running',
        -- running | success | failed | skipped
    duration_seconds NUMERIC(10,2),
    skip_reason      TEXT,
    error_message    TEXT
);

COMMENT ON TABLE  market.scheduler_job_runs IS 'APScheduler job run history — every worker execution recorded here';
COMMENT ON COLUMN market.scheduler_job_runs.skip_reason IS 'Reason job was skipped (e.g. pipeline did not complete today)';

-- ── Indexes ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_run_date
    ON market.pipeline_runs (run_date DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
    ON market.pipeline_runs (status, run_date DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_step_runs_run_id
    ON market.pipeline_step_runs (run_id);

CREATE INDEX IF NOT EXISTS idx_scheduler_job_runs_run_date
    ON market.scheduler_job_runs (run_date DESC, job_id);

CREATE INDEX IF NOT EXISTS idx_scheduler_job_runs_job_id
    ON market.scheduler_job_runs (job_id, run_date DESC);
