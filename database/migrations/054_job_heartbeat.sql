-- Migration 054: Job Heartbeat Table
-- =====================================
-- Lightweight execution tracker for APScheduler/interval jobs.
-- Each job upserts a single row after every run so the Pipeline Monitor
-- can show the true last-execution time, independent of whether the job
-- produced any output rows.

CREATE TABLE IF NOT EXISTS app.job_heartbeat (
    job_id       TEXT        PRIMARY KEY,
    last_run_at  TIMESTAMPTZ NOT NULL,
    run_count    BIGINT      NOT NULL DEFAULT 1
);

COMMENT ON TABLE app.job_heartbeat IS
    'One row per scheduled job — updated after every execution regardless of output.';
