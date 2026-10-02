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


#: How long past a job's expected fire time before absent evidence becomes a
#: finding rather than a timing artefact.
MISSED_GRACE_SECONDS = 15 * 60


def first_run_state(next_run_time: Optional[datetime],
                    now: datetime) -> tuple[str, Optional[str]]:
    """A registered job with no execution evidence yet.

    "Never observed" is not one condition. Three of the twenty jobs are weekly
    or monthly; a monthly job deployed today legitimately has no terminal
    execution for weeks, and calling that `unknown` would make the surface
    permanently red for a healthy system — which is how an operator learns to
    ignore it.

    So absence is classified against the job's own schedule:

        pending_first_run  its next fire has not arrived yet. Healthy and
                           transitional; the expected time is published so the
                           claim can be checked rather than trusted.
        missed             its fire time passed by more than the grace and
                           nothing was recorded. The scheduler did not run it,
                           or ran it without telemetry.
        unknown            no next fire time at all — the registration exists
                           but APScheduler has no intent for it. Genuinely
                           inconsistent, which is what `unknown` is reserved
                           for.

    Limit, stated rather than hidden: this reasons from the NEXT fire time,
    which APScheduler advances after each run. A job that fired and whose
    telemetry write failed therefore reads as `pending_first_run` until its
    following fire. That case is not silent — job_instrumentation logs an
    instrumentation fault under its own logger — but it is not detected here,
    and detecting it would need the previous fire time to be persisted.
    """
    if next_run_time is None:
        return "unknown", "registered but APScheduler reports no next run time"
    overdue = (now - next_run_time).total_seconds()
    if overdue > MISSED_GRACE_SECONDS:
        return "missed", (f"expected at {next_run_time.isoformat()}, "
                          f"{int(overdue)}s ago, with no execution recorded")
    return "pending_first_run", None


def health_view(*,
                registered: Mapping[str, Optional[datetime]] | Iterable[str],
                running: Iterable[Execution],
                latest_terminal: Mapping[str, Execution],
                now: datetime,
                scheduler_enabled: bool = True,
                ) -> dict[str, Any]:
    """The operator's two questions, answered together.

    `registered` is scheduling INTENT: job id -> next fire time, as APScheduler
    reports it. A bare iterable of ids is accepted, and then every job's next
    run time is None — which is itself a legitimate statement of ignorance, and
    classifies as `unknown` rather than quietly passing.

    `running` and `latest_terminal` are execution FACT. The two are joined here
    and nowhere else. Neither substitutes for the other: intent cannot say what
    happened, and execution cannot say what was supposed to.
    """
    if not isinstance(registered, Mapping):
        registered = {job_id: None for job_id in registered}
    next_runs: Mapping[str, Optional[datetime]] = registered
    registered = sorted(next_runs)
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

    jobs: list[dict[str, Any]] = []
    unknown: list[str] = []
    missed: list[str] = []
    pending: list[str] = []

    # An execution recorded against an id the scheduler does not register is
    # genuinely unresolvable: runtime fact with no matching intent. It may be a
    # renamed job still writing under its old id, or a second process. Either
    # way it is `unknown` in the strict sense — not merely unobserved.
    unexpected = sorted({e.job_id for e in running} - set(registered))
    for job_id in registered:
        if job_id in UNOBSERVABLE:
            jobs.append({"job_id": job_id, "coverage": "unobservable",
                         "reason": UNOBSERVABLE[job_id]})
            continue
        last = latest_terminal.get(job_id)
        if last is None:
            # Registered, observable, nothing recorded yet. Which of the three
            # that is depends on the job's own schedule, not on our impatience.
            state, detail = first_run_state(next_runs.get(job_id), now)
            entry: dict[str, Any] = {
                "job_id": job_id, "coverage": "instrumented",
                "last_terminal": None, "state": state,
            }
            nxt = next_runs.get(job_id)
            if nxt is not None:
                entry["next_expected_at"] = nxt.isoformat()
            if detail:
                entry["detail"] = detail
            jobs.append(entry)
            if state == "unknown":
                unknown.append(job_id)
            elif state == "missed":
                missed.append(job_id)
            else:
                pending.append(job_id)
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
    #
    # `pending_first_run` is deliberately absent from this ladder: a weekly job
    # awaiting its first opportunity is healthy, and treating it otherwise
    # would make the surface red for weeks after any deployment.
    if unknown or unexpected:
        verdict = "unresolved"
    elif stale:
        verdict = "suspect"
    elif missed:
        verdict = "missed"
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
        "missed": missed,
        "pending_first_run": pending,
        "unknown": unknown,
        "unexpected_job_ids": unexpected,
        "registered_count": len(registered),
    }
