"""
Pipeline Tracker — Async helpers for APScheduler workers
=========================================================
Provides two tools:

  1. track_scheduler_job
     Async context manager (class-based) that records every APScheduler job
     execution to market.scheduler_job_runs (start time, end time, status,
     duration, error message).  Optionally checks whether the daily pipeline
     completed successfully today before allowing the job to run.

     Usage:
         async with track_scheduler_job(
             "market_snapshot", "Market Snapshot",
             skip_if_pipeline_failed=True,
         ) as job:
             if job.skipped:
                 return          # pipeline gate triggered — exit body early
             await do_work()

     The `.skipped` property is True when the pipeline gate fired.
     Workers that use skip_if_pipeline_failed=True MUST check job.skipped
     at the top of their body and return early.  Other workers (False) can
     ignore the property.

  2. check_pipeline_ran_today()
     Returns True if market.pipeline_runs has a 'success' row for today.
     Used by dependent workers (market_snapshot, anomaly_detect) to skip
     their run when the upstream pipeline failed or is still running.

Design notes:
  - All DB operations are best-effort; exceptions are caught and logged so
    monitoring never blocks the actual job.
  - skip_if_pipeline_failed=True is appropriate for jobs that read from
    tables written by the pipeline (period_metrics, screener.universe).
    Jobs that are independent (index prices, fund prices) should use False.
  - When skipped, __aexit__ suppresses exceptions from the body so that
    callers can safely return early without triggering spurious error logs.
  - The context manager re-raises exceptions from job body after recording
    'failed' so the caller's except block still fires.

WHY CLASS-BASED (not asynccontextmanager):
  asynccontextmanager requires exactly one yield.  The previous implementation
  used `return` before `yield` to skip the body, which raises
  RuntimeError("generator didn't yield") — silently killing the caller
  before heartbeat writes or cleanup code could run.  The class-based
  approach avoids this entirely: __aenter__ always returns self, workers
  check job.skipped to exit the body, and __aexit__ runs normally.
"""

import logging
import time
from typing import Optional

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

log = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

async def check_pipeline_ran_today() -> bool:
    """
    Return True if the daily pipeline completed successfully today.
    Fails open (returns True) if the DB check itself errors, so a monitoring
    table outage can never block production jobs.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                SELECT 1
                  FROM market.pipeline_runs
                 WHERE run_date = CURRENT_DATE
                   AND status   = 'success'
                 LIMIT 1
            """))
            return result.fetchone() is not None
    except Exception as exc:
        log.warning(f"[pipeline_tracker] pipeline check failed: {exc} — failing open")
        return True   # fail-open: don't block jobs if monitoring DB is unavailable


class track_scheduler_job:
    """
    Async context manager for APScheduler workers.

    If skip_if_pipeline_failed=True and today's pipeline has not succeeded,
    records a 'skipped' row, sets self.skipped = True, and returns normally
    from __aenter__.  Workers MUST check `job.skipped` and exit the body
    early — __aexit__ will suppress any exceptions raised during a skipped
    body so cleanup code in the caller still runs.

    If skip_if_pipeline_failed=False (default) or the pipeline ran today,
    records a 'running' row, yields control to the job body, then updates
    the row to 'success' or 'failed' with duration.

    Re-raises job body exceptions (non-skip path) after recording 'failed'.

    Example:
        async with track_scheduler_job("market_snapshot", "Market Snapshot",
                                        skip_if_pipeline_failed=True) as job:
            if job.skipped:
                return
            await do_work()
    """

    def __init__(
        self,
        job_id: str,
        job_name: str,
        *,
        skip_if_pipeline_failed: bool = False,
    ) -> None:
        self.job_id = job_id
        self.job_name = job_name
        self.skip_if_pipeline_failed = skip_if_pipeline_failed
        self.skipped: bool = False
        self._run_id: Optional[int] = None
        self._start: float = 0.0

    async def __aenter__(self) -> "track_scheduler_job":
        self._start = time.monotonic()

        # ── Dependency gate ───────────────────────────────────────────────────
        if self.skip_if_pipeline_failed:
            pipeline_ok = await check_pipeline_ran_today()
            if not pipeline_ok:
                reason = "Daily pipeline did not complete successfully today"
                log.warning(f"[{self.job_id}] Skipping — {reason}")
                await _insert_completed(
                    self.job_id, self.job_name, "skipped",
                    duration=0.0, skip_reason=reason,
                )
                self.skipped = True
                return self   # caller checks job.skipped and returns early

        # ── Record start ──────────────────────────────────────────────────────
        self._run_id = await _insert_running(self.job_id, self.job_name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.skipped:
            # Body returned early (or raised) during a skip — suppress so that
            # code after `async with` (e.g. heartbeat writes) still executes.
            return True

        elapsed = time.monotonic() - self._start

        if exc_val is None:
            await _update_run(self._run_id, "success", elapsed)
        else:
            await _update_run(
                self._run_id, "failed", elapsed, error_msg=str(exc_val)[:500]
            )

        return False  # re-raise job body exceptions on non-skip path


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _insert_running(job_id: str, job_name: str) -> Optional[int]:
    """Insert a 'running' row and return its id."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                INSERT INTO market.scheduler_job_runs
                    (run_date, job_id, job_name, started_at, status)
                VALUES (CURRENT_DATE, :job_id, :job_name, NOW(), 'running')
                RETURNING id
            """), {"job_id": job_id, "job_name": job_name})
            await db.commit()
            row = result.fetchone()
            return row[0] if row else None
    except Exception as exc:
        log.debug(f"[pipeline_tracker] insert_running failed: {exc}")
        return None


async def _update_run(
    run_id: Optional[int],
    status: str,
    duration: float,
    error_msg: str = None,
) -> None:
    """Update an existing run row with final status and duration."""
    if run_id is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                UPDATE market.scheduler_job_runs
                   SET completed_at     = NOW(),
                       status           = :status,
                       duration_seconds = :duration,
                       error_message    = :error_msg
                 WHERE id = :run_id
            """), {
                "run_id":    run_id,
                "status":    status,
                "duration":  round(duration, 2),
                "error_msg": error_msg,
            })
            await db.commit()
    except Exception as exc:
        log.debug(f"[pipeline_tracker] update_run failed: {exc}")


async def _insert_completed(
    job_id: str,
    job_name: str,
    status: str,
    duration: float,
    skip_reason: str = None,
    error_msg: str = None,
) -> None:
    """Insert a single completed row (for skipped jobs)."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO market.scheduler_job_runs
                    (run_date, job_id, job_name, started_at, completed_at,
                     status, duration_seconds, skip_reason, error_message)
                VALUES (CURRENT_DATE, :job_id, :job_name, NOW(), NOW(),
                        :status, :duration, :skip_reason, :error_msg)
            """), {
                "job_id":      job_id,
                "job_name":    job_name,
                "status":      status,
                "duration":    round(duration, 2),
                "skip_reason": skip_reason,
                "error_msg":   error_msg,
            })
            await db.commit()
    except Exception as exc:
        log.debug(f"[pipeline_tracker] insert_completed failed: {exc}")
