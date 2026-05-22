"""
Pipeline Tracker — Async helpers for APScheduler workers
=========================================================
Provides two tools:

  1. track_scheduler_job()
     Async context manager that records every APScheduler job execution
     to market.scheduler_job_runs (start time, end time, status, duration,
     error message).  Optionally checks whether the daily pipeline completed
     successfully today before allowing the job to run.

  2. check_pipeline_ran_today()
     Returns True if market.pipeline_runs has a 'success' row for today.
     Used by dependent workers (market_snapshot, anomaly_detect) to skip
     their run when the upstream pipeline failed or is still running.

Usage in a worker:

    from app.workers.pipeline_tracker import track_scheduler_job

    async def run_market_snapshot() -> None:
        async with track_scheduler_job(
            "market_snapshot", "Market Snapshot",
            skip_if_pipeline_failed=True,       # ← gate on pipeline success
        ):
            from compute.engine.market_snapshot import run
            await run(snapshot_date=date.today())

Design notes:
  - All DB operations are best-effort; exceptions are caught and logged so
    monitoring never blocks the actual job.
  - skip_if_pipeline_failed=True is appropriate for jobs that read from
    tables written by the pipeline (period_metrics, screener.universe).
    Jobs that are independent (index prices, fund prices) should use False.
  - The context manager re-raises exceptions so the caller's except block
    still fires and the heartbeat table still gets updated.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

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


@asynccontextmanager
async def track_scheduler_job(
    job_id: str,
    job_name: str,
    *,
    skip_if_pipeline_failed: bool = False,
) -> AsyncGenerator[None, None]:
    """
    Async context manager for APScheduler workers.

    - If skip_if_pipeline_failed=True and today's pipeline has not succeeded,
      records a 'skipped' row and exits without running the job body.
    - Otherwise records a 'running' row, yields control to the job body,
      then updates the row to 'success' or 'failed' with duration.
    - Re-raises any exception from the job body after recording 'failed'.

    Example:
        async with track_scheduler_job("market_snapshot", "Market Snapshot",
                                        skip_if_pipeline_failed=True):
            await do_work()
    """
    start = time.monotonic()

    # ── Dependency gate ───────────────────────────────────────────────────────
    if skip_if_pipeline_failed:
        pipeline_ok = await check_pipeline_ran_today()
        if not pipeline_ok:
            reason = "Daily pipeline did not complete successfully today"
            log.warning(f"[{job_id}] Skipping — {reason}")
            await _insert_completed(job_id, job_name, "skipped",
                                    duration=0.0, skip_reason=reason)
            return   # exit context manager without running job body

    # ── Record start ──────────────────────────────────────────────────────────
    run_id = await _insert_running(job_id, job_name)

    try:
        yield   # ── job body runs here ────────────────────────────────────────

        # ── Success ───────────────────────────────────────────────────────────
        elapsed = time.monotonic() - start
        await _update_run(run_id, "success", elapsed)

    except Exception as exc:
        # ── Failure ───────────────────────────────────────────────────────────
        elapsed = time.monotonic() - start
        await _update_run(run_id, "failed", elapsed, error_msg=str(exc)[:500])
        raise   # re-raise so caller's except block still fires


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _insert_running(job_id: str, job_name: str) -> int | None:
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


async def _update_run(run_id: int | None, status: str, duration: float,
                      error_msg: str = None) -> None:
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


async def _insert_completed(job_id: str, job_name: str, status: str,
                             duration: float, skip_reason: str = None,
                             error_msg: str = None) -> None:
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
