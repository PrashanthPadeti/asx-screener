"""
The shared execution boundary for scheduled jobs
================================================
One wrapper, used at every `scheduler.add_job` call site, so that what a job
*did* is recorded separately from when APScheduler intended it to run.

    instrumented("alert_checker", check_alerts)

── The property that matters most ──────────────────────────────────────────────
**Telemetry failure must never change the job's outcome.** If the database is
unreachable, the job still runs, still succeeds or fails on its own terms, and
still raises what it would have raised. Every persistence call here is wrapped
so that an instrument cannot convert a real failure into a success, or a real
success into a failure. The observer does not get a vote on what it observes —
`app/core/instrument.py` froze that rule after three incidents; this is the
same rule applied to a different boundary.

A failed telemetry write is logged under its own logger so it is visible as an
instrumentation fault rather than silently widening the blast radius.

── Why a crash leaves a RUNNING row ────────────────────────────────────────────
`running` is written at the real start, a terminal status at the real end. A
process killed between them writes neither, leaving an open row. That is a true
statement about what is known, and job_telemetry.classify() surfaces it as
`stale_running` past the job's ceiling. Closing such rows on startup, or
assuming success, would replace an honest unknown with a reassuring lie.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional

from sqlalchemy import text

from compute.engine.job_telemetry import FAILED, RUNNING, SUCCESS, bound_failure

#: Separate logger so an instrumentation fault is attributable, and never
#: mistaken for the job's own failure.
log = logging.getLogger("app.core.job_instrumentation")

_INSERT = text("""
    INSERT INTO ops.job_executions (job_id, started_at, status)
    VALUES (:job_id, :started_at, :status)
    RETURNING run_id
""")

_CLOSE = text("""
    UPDATE ops.job_executions
       SET finished_at     = :finished_at,
           duration_ms     = :duration_ms,
           status          = :status,
           failure_class   = :failure_class,
           failure_message = :failure_message
     WHERE run_id = :run_id
       AND status = 'running'
""")


async def _open_run(job_id: str) -> Optional[int]:
    """Record the start. Returns None when telemetry is unavailable, which the
    caller treats as "unobserved", never as "do not run"."""
    try:
        from app.db.session import AsyncSessionLocal              # noqa: PLC0415
        async with AsyncSessionLocal() as session:
            result = await session.execute(_INSERT, {
                "job_id": job_id,
                "started_at": datetime.now(timezone.utc),
                "status": RUNNING,
            })
            run_id = result.scalar_one()
            await session.commit()
            return int(run_id)
    except Exception as exc:                                    # noqa: BLE001
        log.error("telemetry: could not open run for %s: %s: %s",
                  job_id, type(exc).__name__, exc)
        return None


async def _close_run(run_id: Optional[int], *, status: str, duration_ms: int,
                     failure: Optional[BaseException] = None) -> None:
    """Record the terminal boundary. Never raises into the caller."""
    if run_id is None:
        return
    try:
        from app.db.session import AsyncSessionLocal              # noqa: PLC0415
        async with AsyncSessionLocal() as session:
            await session.execute(_CLOSE, {
                "run_id": run_id,
                "finished_at": datetime.now(timezone.utc),
                "duration_ms": duration_ms,
                "status": status,
                "failure_class": type(failure).__name__ if failure else None,
                "failure_message": bound_failure(str(failure)) if failure else None,
            })
            await session.commit()
    except Exception as exc:                                    # noqa: BLE001
        log.error("telemetry: could not close run %s for status %s: %s: %s",
                  run_id, status, type(exc).__name__, exc)


def instrumented(job_id: str, func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a scheduled coroutine so its execution is recorded.

    The wrapper is deliberately transparent: it returns what the job returns
    and raises what the job raises. APScheduler's own success/failure handling
    is unchanged.
    """

    @wraps(func)
    async def _run(*args: Any, **kwargs: Any) -> Any:
        run_id = await _open_run(job_id)
        started = time.monotonic()
        try:
            result = await func(*args, **kwargs)
        except BaseException as exc:                            # noqa: BLE001
            # Record the failure, then re-raise unchanged. The job's semantics
            # are the job's; telemetry only watches.
            await _close_run(run_id, status=FAILED,
                             duration_ms=round((time.monotonic() - started) * 1000),
                             failure=exc)
            raise
        await _close_run(run_id, status=SUCCESS,
                         duration_ms=round((time.monotonic() - started) * 1000))
        return result

    _run.__wrapped_job_id__ = job_id        # type: ignore[attr-defined]
    return _run
