-- Partial success is neither green nor fatal
-- ==========================================
-- 14 Oct 2026, 06:37 UTC:
--
--     fund_prices: 53/55 obtained, 0 refused, 2 empty, 157 rows
--     Job "compute_fund_prices" executed successfully
--
-- Two eligible funds published nothing. 157 rows were written for the other
-- 53, so the run was not a failure -- `verify()` is right not to raise, and
-- discarding the 53 would be worse than anything it fixes. But `success` is
-- the only thing the record could say, and so the two that failed are absent
-- from it. Which two, and why, is exactly the question the per-entity
-- outcomes were built to answer.
--
-- Why a column and not a new status
-- ---------------------------------
-- `status` is read by filters written against its three literals:
--
--     job_executions_terminal_idx      WHERE status IN ('success','failed')
--     admin.py:362                     WHERE status IN ('success','failed')
--     admin.py:1004-1008               FILTER (WHERE status = 'success') ...
--     job_telemetry.TERMINAL           (SUCCESS, FAILED)
--
-- Adding a fourth literal makes a degraded run match none of them: it would
-- drop out of the terminal index, out of the Pipeline Monitor, and out of
-- `last_success` -- invisible rather than merely green. A state that every
-- existing filter excludes is worse than the state we have. See the standing
-- rule on scoped verdicts.
--
-- So `status` keeps its domain and its meaning (the job completed; prices
-- were written), and the degradation rides alongside it where nothing has to
-- be re-enumerated to keep working.
--
-- ORDERING: this migration must be applied BEFORE the code that writes these
-- columns is deployed. `_close_run` writes one UPDATE naming them; against an
-- un-migrated table that statement fails, and while the wrapper swallows the
-- error so no job outcome changes, the run would go unrecorded entirely.
-- Migration first, then deploy.

ALTER TABLE ops.job_executions
    ADD COLUMN IF NOT EXISTS degraded BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS findings TEXT[];

-- A degraded run must say what was degraded about it.
--
-- `degraded = true` with no findings is a worse record than `success`: it
-- asserts that something went wrong and then declines to say what, which
-- sends an operator to the logs with nothing to search for. The flag and its
-- evidence are one fact, so the table refuses to hold half of it.
ALTER TABLE ops.job_executions
    DROP CONSTRAINT IF EXISTS job_executions_degraded_has_findings;
ALTER TABLE ops.job_executions
    ADD CONSTRAINT job_executions_degraded_has_findings
    CHECK (
        degraded = false
        OR (findings IS NOT NULL AND cardinality(findings) > 0)
    );

-- Degradation is a terminal fact. A row still `running` has not finished
-- deciding what it obtained, so it cannot yet be partially successful.
ALTER TABLE ops.job_executions
    DROP CONSTRAINT IF EXISTS job_executions_degraded_is_terminal;
ALTER TABLE ops.job_executions
    ADD CONSTRAINT job_executions_degraded_is_terminal
    CHECK (status <> 'running' OR degraded = false);

-- "Which runs completed but did not publish everything they should have" is
-- the query this column exists to serve; keep it cheap and partial.
CREATE INDEX IF NOT EXISTS job_executions_degraded_idx
    ON ops.job_executions (job_id, finished_at DESC)
    WHERE degraded;

COMMENT ON COLUMN ops.job_executions.degraded IS
    'The run completed and wrote what it obtained, but at least one eligible '
    'entity did not publish. Distinct from failure: the successful entities '
    'ARE published. `status` remains success so existing terminal filters, '
    'indexes and success-rate queries continue to match.';

COMMENT ON COLUMN ops.job_executions.findings IS
    'Per-entity reasons for the degradation, one line per finding, as '
    'ProducerTally.report() produced them. Required whenever degraded.';
