"""
One evaluator, two consumers
=============================
A job that takes the auxiliary lease and finds a canonical run in flight
returns without writing. Correct -- and indistinguishable from a quiet week,
because the process exits 0 either way.

This module holds the registry, the query and the DECISION. It holds no
connection and runs no I/O, so the cron gate and the admin surface cannot
disagree about what "stale" means: they execute the same SQL with their own
driver and hand the result to the same classifier.

The alternative -- having the endpoint read the cron job's log file -- would
make the surface a report of a report. A log that stopped being written looks
exactly like a log with nothing to say.

Three states, and the third is not a synonym for the first:

    current       the output advanced inside its limit
    stale         it did not, and that is a fault
    unobservable  the job writes no timestamp of its own; NAMED, with the
                  reason. Not equivalent to fresh, and never counted as such.

`broken` is a fourth, for an anchor whose column does not exist -- an
instrument defect, reported as itself rather than as a stale job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class Anchor:
    """A job, the output that proves it ran, and how stale is too stale."""

    job: str
    table: str
    column: str
    max_age_hours: int
    why: str


#: Jobs whose output IS independently observable.
#:
#: max_age is the cadence plus one full period, so a single deferral is
#: tolerated and a second consecutive one is not. A threshold tighter than the
#: cadence would fire on exactly the behaviour the lease exists to produce.
ANCHORS: tuple[Anchor, ...] = (
    Anchor("short_positions", "market.short_positions", "updated_at", 24 * 10,
           "ASIC publishes weekly with a few days' lag; the job upserts on "
           "every successful download, so updated_at advances even when the "
           "report date does not"),
    Anchor("top5_strategy", "strategy.monthly_picks", "computed_at", 24 * 15,
           "runs Sunday 22:00 UTC, inside the weekly canonical window, so it "
           "is the job most likely to defer; two missed Sundays is a fault"),
)

#: Jobs whose freshness CANNOT be observed from their own output, and why.
#:
#: Named rather than omitted. An unchecked job missing from a report reads as
#: a healthy one, which is the failure this file exists to remove.
UNOBSERVABLE: dict[str, str] = {
    "pros_cons":
        "writes only screener.universe (pros/cons columns), which the "
        "canonical run rebuilds wholesale -- no timestamp of its own. Its "
        "freshness is implied by the run that published those rows, which "
        "compute_run_finalizations already evidences.",
    "asx_indices":
        "writes index-membership flags into screener.universe and "
        "market.companies with no timestamp attributable to this job. "
        "Observing it needs a column it does not currently write.",
}


@dataclass(frozen=True)
class Finding:
    """What is known about one job, in a shape both consumers can render."""

    job: str
    state: str                      # current | stale | broken | unobservable
    table: Optional[str] = None
    column: Optional[str] = None
    observed_at: Optional[str] = None
    age_hours: Optional[float] = None
    limit_hours: Optional[int] = None
    reason: str = ""

    @property
    def ok(self) -> bool:
        """`unobservable` is NOT ok and NOT a fault.

        It is excluded from both tallies deliberately. Folding it into `ok`
        would let two unchecked jobs read as two healthy ones, which is the
        dishonesty this module exists to prevent; folding it into failures
        would make a known limitation page somebody every night.
        """
        return self.state == "current"

    @property
    def faulty(self) -> bool:
        return self.state in ("stale", "broken")

    def as_dict(self) -> dict:
        return {
            "job": self.job,
            "state": self.state,
            "table": self.table,
            "column": self.column,
            "observed_at": self.observed_at,
            "age_hours": (round(self.age_hours, 1)
                          if self.age_hours is not None else None),
            "limit_hours": self.limit_hours,
            "reason": self.reason,
        }


def existence_sql(anchor: Anchor) -> str:
    """Does the anchor's column exist? Asked before it is trusted.

    A missing column would otherwise raise, and an operator reading a
    traceback learns the check is broken, not whether the job ran.

    Parameterless on purpose. The two consumers use different drivers with
    different paramstyles -- psycopg2 wants %s, SQLAlchemy text() wants :name
    -- and carrying both spellings would be two SQL strings pretending to be
    one, which is exactly the divergence this module exists to prevent.

    The values are safe to embed because they are not inputs: every one comes
    from ANCHORS, a frozen tuple in this file. Nothing reaches here from a
    request, an environment variable or a caller.
    """
    schema, name = anchor.table.split(".", 1)
    for part in (schema, name, anchor.column):
        if not part.replace("_", "").isalnum():
            raise ValueError(f"refusing to build SQL from {part!r}")
    return (
        "SELECT count(*) = 1 FROM information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{name}' "
        f"AND column_name = '{anchor.column}'"
    )


def latest_sql(anchor: Anchor) -> str:
    """The newest value of the anchor column. No parameters: the identifiers
    come from this module's own frozen registry, never from a caller."""
    return f"SELECT max({anchor.column}) FROM {anchor.table}"


def classify(anchor: Anchor, column_exists: bool,
             latest: Optional[datetime],
             now: Optional[datetime] = None) -> Finding:
    """The decision, pure. Both consumers call exactly this."""
    if not column_exists:
        return Finding(anchor.job, "broken", anchor.table, anchor.column,
                       limit_hours=anchor.max_age_hours,
                       reason=f"{anchor.table}.{anchor.column} does not exist")
    if latest is None:
        return Finding(anchor.job, "broken", anchor.table, anchor.column,
                       limit_hours=anchor.max_age_hours,
                       reason=f"{anchor.table} has no rows at all")

    now = now or datetime.now(timezone.utc)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    age = (now - latest).total_seconds() / 3600.0
    state = "current" if age <= anchor.max_age_hours else "stale"
    return Finding(
        anchor.job, state, anchor.table, anchor.column,
        observed_at=latest.isoformat(), age_hours=age,
        limit_hours=anchor.max_age_hours,
        reason="" if state == "current" else anchor.why)


def unobservable_findings() -> list[Finding]:
    return [Finding(job, "unobservable", reason=why)
            for job, why in sorted(UNOBSERVABLE.items())]


def summarise(findings: list[Finding]) -> dict:
    """Counts that keep the three states distinct.

    `healthy` is false when anything is faulty. It is NOT true merely because
    nothing is faulty -- an evaluation with no observable anchors at all would
    otherwise report healthy while proving nothing.
    """
    observable = [f for f in findings if f.state != "unobservable"]
    faulty = [f for f in findings if f.faulty]
    return {
        "healthy": bool(observable) and not faulty,
        "current": sum(1 for f in findings if f.state == "current"),
        "stale": sum(1 for f in findings if f.state == "stale"),
        "broken": sum(1 for f in findings if f.state == "broken"),
        "unobservable": sum(1 for f in findings if f.state == "unobservable"),
    }
