"""
What a scheduled job actually did, as distinct from when it was meant to run
===========================================================================
APScheduler knows a job's *intent*: its trigger, and the next time it will
fire. It does not know whether the last run took four seconds or fifty-five
minutes, whether it is running right now, or whether it has failed twenty times
in a row.

On 2 Oct 2026 the site was unavailable for ~40 minutes while an in-process job
made hundreds of serial outbound calls. The only reason its ~55-minute runtime
is known is that it happened to log every HTTP request during an outage someone
was already investigating. Sixteen other jobs have no measured runtime at all,
and five of them fire within twenty minutes of each other.

So this module answers the two questions an operator actually has:

    Is something running right now?
    When did it last finish, how long did it take, and did it succeed?

Intent and execution are kept separate. `/system-health` may join the two
views; neither substitutes for the other.

── Why executions are immutable rows ────────────────────────────────────────
One row per job id cannot represent a job that overlaps itself, and overlap is
precisely the pathology worth seeing. Each execution gets its own identity, so
history is a sequence of facts rather than a mutable status field.

── Why a crashed process is not a success ───────────────────────────────────
RUNNING is written at the real execution boundary and a terminal status at the
real terminal boundary. A process killed mid-run writes neither — it leaves a
RUNNING row that never closes, which is a true statement about what is known.
`stale_running` is how that becomes visible instead of looking healthy forever.

Pure by construction: no database, no clock of its own, no network. `now` is
passed in. Two consumers — the admin surface and the tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Optional

RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"
TERMINAL = (SUCCESS, FAILED)

#: How long a job may be RUNNING before the row is treated as suspicious
#: rather than healthy. Deliberately generous: this detects a run that never
#: closed, not a run that is merely slow.
DEFAULT_CEILING_SECONDS = 30 * 60

#: Per-job ceilings, for jobs whose honest runtime exceeds the default.
#: `announcement_fetcher` is measured, not guessed: 09:10 -> 10:05 UTC on
#: 2 Oct 2026. It is listed here so that its known cost is explicit rather
#: than quietly normalised by a large default.
CEILING_SECONDS: dict[str, int] = {
    "announcement_fetcher": 90 * 60,
}

#: Registered scheduler identities that deliberately carry no execution
#: telemetry, each with the reason. An identity that is neither wrapped nor
#: listed here is UNKNOWN, which is a failing state — the whole point of the
#: coverage contract is that silence is not evidence of health.
UNOBSERVABLE: dict[str, str] = {}

#: Failure text is bounded before it reaches an admin response. An exception
#: payload can carry a connection string, a token, or a megabyte of SQL.
MAX_FAILURE_CHARS = 300


@dataclass(frozen=True)
class Execution:
    """One immutable execution record."""
    run_id: int
    job_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    status: str = RUNNING
    failure_class: Optional[str] = None
    failure_message: Optional[str] = None


def ceiling_for(job_id: str) -> int:
    return CEILING_SECONDS.get(job_id, DEFAULT_CEILING_SECONDS)


def bound_failure(text: Optional[str]) -> Optional[str]:
    """Truncate failure text so an admin response cannot become an exfiltration
    channel for whatever an exception happened to carry."""
    if not text:
        return None
    collapsed = " ".join(str(text).split())
    if len(collapsed) <= MAX_FAILURE_CHARS:
        return collapsed
    return collapsed[:MAX_FAILURE_CHARS - 1] + "…"


def classify(execution: Execution, now: datetime) -> str:
    """running | stale_running | success | failed.

    A RUNNING row older than its ceiling is `stale_running`: either the job is
    pathologically long or the process died without closing it. Both are
    conditions worth seeing, and neither is health.
    """
    if execution.status in TERMINAL:
        return execution.status
    age = (now - execution.started_at).total_seconds()
    return "stale_running" if age > ceiling_for(execution.job_id) else RUNNING


def _age_seconds(then: Optional[datetime], now: datetime) -> Optional[int]:
    return None if then is None else int((now - then).total_seconds())


def health_view(*,
                registered: Iterable[str],
                running: Iterable[Execution],
                latest_terminal: Mapping[str, Execution],
                now: datetime,
                scheduler_enabled: bool = True,
                ) -> dict[str, Any]:
    """The operator's two questions, answered together.

    `registered` is scheduling intent (APScheduler's job ids). `running` and
    `latest_terminal` are execution facts. Joining them here is what makes a
    job that is registered but has never been observed visible as UNKNOWN,
    rather than absent.
    """
    registered = sorted(set(registered))
    running = list(running)

    now_running = [
        {
            "run_id": e.run_id,
            "job_id": e.job_id,
            "started_at": e.started_at.isoformat(),
            "running_for_seconds": _age_seconds(e.started_at, now),
            "state": classify(e, now),
            "ceiling_seconds": ceiling_for(e.job_id),
        }
        for e in sorted(running, key=lambda e: e.started_at)
    ]

    jobs = []
    unknown = []
    for job_id in registered:
        if job_id in UNOBSERVABLE:
            jobs.append({"job_id": job_id, "coverage": "unobservable",
                         "reason": UNOBSERVABLE[job_id]})
            continue
        last = latest_terminal.get(job_id)
        if last is None:
            # Registered, observable, and never seen to finish. Not health.
            unknown.append(job_id)
            jobs.append({"job_id": job_id, "coverage": "instrumented",
                         "last_terminal": None, "state": "unknown"})
            continue
        jobs.append({
            "job_id": job_id,
            "coverage": "instrumented",
            "state": last.status,
            "last_terminal": {
                "run_id": last.run_id,
                "finished_at": last.finished_at.isoformat() if last.finished_at else None,
                "duration_ms": last.duration_ms,
                "status": last.status,
                "failure_class": last.failure_class,
                "failure_message": bound_failure(last.failure_message),
                "age_seconds": _age_seconds(last.finished_at, now),
            },
        })

    stale = [r for r in now_running if r["state"] == "stale_running"]
    failed = [j["job_id"] for j in jobs if j.get("state") == FAILED]

    # A frozen or disabled scheduler legitimately runs nothing. Zero running
    # jobs is only suspicious when the scheduler claims to be live, and even
    # then it is normal most of the time — so it is never a failure here.
    if stale:
        verdict = "suspect"
    elif unknown:
        verdict = "incomplete"
    elif failed:
        verdict = "failing"
    else:
        verdict = "ok"

    return {
        "scheduler_enabled": scheduler_enabled,
        "verdict": verdict,
        "running": now_running,
        "jobs": jobs,
        "stale_running": [r["job_id"] for r in stale],
        "failing": failed,
        "unknown": unknown,
        "registered_count": len(registered),
    }
