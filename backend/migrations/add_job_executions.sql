-- What a scheduled job actually did.
--
-- APScheduler records intent: a trigger, and the next time a job will fire. It
-- records nothing about execution. On 2 Oct 2026 the site was unavailable for
-- ~40 minutes while an in-process job made hundreds of serial outbound calls,
-- and the only reason its ~55-minute runtime is known is that it happened to
-- log every HTTP request during an outage someone was already investigating.
--
-- Immutable rows, one per execution, NOT one per job id. A status column keyed
-- by job id cannot represent a job overlapping itself, and overlap is exactly
-- the pathology worth seeing. History becomes a sequence of facts rather than
-- a field that gets overwritten.
--
-- A process killed mid-run writes no terminal row. That is intentional: the
-- surviving RUNNING row is a true statement about what is known, and
-- job_telemetry.classify() surfaces it as `stale_running` once it exceeds the
-- job's ceiling. The alternative — assuming success on restart — would convert
-- an unknown into a reassuring lie.

CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.job_executions (
    run_id          BIGSERIAL    PRIMARY KEY,
    job_id          TEXT         NOT NULL,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    duration_ms     INTEGER,
    status          TEXT         NOT NULL DEFAULT 'running',
    failure_class   TEXT,
    failure_message TEXT,

    CONSTRAINT job_executions_status_known
        CHECK (status IN ('running', 'success', 'failed')),

    -- A terminal row must carry its terminal facts, and a running row must not
    -- pretend to have them. This is what stops a half-written terminal state
    -- from reading as a completed run.
    CONSTRAINT job_executions_terminal_is_complete
        CHECK (
            (status = 'running' AND finished_at IS NULL AND duration_ms IS NULL)
            OR
            (status IN ('success', 'failed') AND finished_at IS NOT NULL)
        ),

    -- Failure metadata belongs only to a failure.
    CONSTRAINT job_executions_failure_only_when_failed
        CHECK (status = 'failed' OR (failure_class IS NULL AND failure_message IS NULL))
);

-- "What is running right now" is the hot query; keep it cheap and partial.
CREATE INDEX IF NOT EXISTS job_executions_running_idx
    ON ops.job_executions (started_at DESC)
    WHERE status = 'running';

-- "Most recent terminal execution per job" is the other hot query.
CREATE INDEX IF NOT EXISTS job_executions_terminal_idx
    ON ops.job_executions (job_id, finished_at DESC)
    WHERE status IN ('success', 'failed');

COMMENT ON TABLE ops.job_executions IS
    'Immutable execution records for scheduled jobs. One row per execution so '
    'overlapping runs are representable. A row left in `running` is a process '
    'that died without closing it, surfaced as stale_running rather than '
    'assumed successful.';
