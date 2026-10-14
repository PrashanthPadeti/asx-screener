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

from sqlalchemy import Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY

from compute.engine.job_telemetry import FAILED, RUNNING, SUCCESS, bound_failure

#: Separate logger so an instrumentation fault is attributable, and never
#: mistaken for the job's own failure.
log = logging.getLogger("app.core.job_instrumentation")

_INSERT = text("""
    INSERT INTO ops.job_executions (job_id, started_at, status)
    VALUES (:job_id, :started_at, :status)
    RETURNING run_id
""")

#: `findings` is TEXT[]; the bind is typed explicitly rather than inferred,
#: because an untyped empty list has no element type for the driver to guess
#: from and binds as the wrong thing exactly when there is nothing to show.
_CLOSE = text("""
    UPDATE ops.job_executions
       SET finished_at     = :finished_at,
           duration_ms     = :duration_ms,
           status          = :status,
           failure_class   = :failure_class,
           failure_message = :failure_message,
           degraded        = :degraded,
           findings        = :findings
     WHERE run_id = :run_id
       AND status = 'running'
""").bindparams(bindparam("findings", type_=ARRAY(Text)))


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
                     failure: Optional[BaseException] = None,
                     degraded: bool = False,
                     findings: Optional[list[str]] = None) -> None:
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
                "degraded": degraded,
                "findings": findings or None,
            })
            await session.commit()
    except Exception as exc:                                    # noqa: BLE001
        log.error("telemetry: could not close run %s for status %s: %s: %s",
                  run_id, status, type(exc).__name__, exc)


def _degradation_of(job_id: str, result: Any) -> tuple[bool, Optional[list[str]]]:
    """Read a degraded verdict off whatever the job returned.

    Duck-typed on purpose. Most jobs return None and are unaffected; a
    producer returns its `ProducerTally`, which already knows whether some
    eligible entity failed to publish and can say which. Importing the
    producer contract here to isinstance-check it would make every scheduled
    job depend on the compute layer to be observed.

    Read defensively, and never let the reading change the outcome. A job that
    returns something unexpected -- or a property that raises -- must not be
    converted into a failure by the instrument watching it. That rule has its
    own module (`app/core/instrument.py`) and three incidents behind it.
    """
    try:
        if not bool(getattr(result, "degraded", False)):
            return False, None
        report = getattr(result, "report", None)
        lines = [str(x) for x in report()] if callable(report) else []
        if not lines:
            # The schema refuses a degraded row with no findings, and it is
            # right to. Say that the verdict arrived without its evidence
            # rather than dropping the verdict or inventing the evidence.
            lines = ["degraded, but the producer recorded no findings"]
        return True, lines
    except Exception as exc:                                    # noqa: BLE001
        log.error("telemetry: could not read degradation from %s: %s: %s",
                  job_id, type(exc).__name__, exc)
        return False, None


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
        degraded, findings = _degradation_of(job_id, result)
        if degraded:
            # Logged here as well as recorded, because the log is where an
            # operator is already looking when a run finishes "successfully"
            # with less than it should have published.
            log.warning("%s completed DEGRADED: %s", job_id, "; ".join(findings or []))
        await _close_run(run_id, status=SUCCESS,
                         duration_ms=round((time.monotonic() - started) * 1000),
                         degraded=degraded, findings=findings)
        return result

    _run.__wrapped_job_id__ = job_id        # type: ignore[attr-defined]
    return _run
