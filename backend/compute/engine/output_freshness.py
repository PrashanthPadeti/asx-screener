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
    #: How often the job is SUPPOSED to produce. The limit must be at least two
    #: of these, so one tolerated deferral never fires the alarm. Carried per
    #: anchor because the jobs genuinely differ: prices are daily, the monthly
    #: strategy is weekly, and a single blanket floor made the price anchor
    #: impossible to set usefully — a 7-day floor on daily prices would be
    #: slower to notice than the outage it exists to catch.
    cadence_hours: int = 24
    #: The file that writes this column. An anchor is a guess until it is
    #: checked against its writer: the first version of this registry anchored
    #: top5_strategy on `created_at` when the job writes `computed_at`. Stated
    #: rather than inferred from the job name, because the producers do not all
    #: live in one directory — prices are loaded from scripts/, not
    #: compute/engine/.
    writer: str = ""


#: Jobs whose output IS independently observable.
#:
#: max_age is the cadence plus one full period, so a single deferral is
#: tolerated and a second consecutive one is not. A threshold tighter than the
#: cadence would fire on exactly the behaviour the lease exists to produce.
ANCHORS: tuple[Anchor, ...] = (
    # Added 3 Oct 2026, after a customer reported week-old prices that nothing
    # here had noticed. market.daily_prices held NO rows for 24, 25, 28 and 29
    # September; this check reported FRESH throughout, truthfully, because it
    # had only ever been asked about short positions and a monthly strategy
    # table. The product's primary output was not in its population.
    #
    # The observable is max(time) — the newest trading day present — because
    # the table carries no ingestion timestamp. That is also the property a
    # customer actually experiences: "how recent is the newest price I can
    # see?"
    #
    # 120 hours, from the worst legitimate gap rather than from preference.
    # The pipeline loads a day's close at 08:30 UTC Mon-Fri. A Friday close is
    # 58h old by Sunday's 10:00 UTC check, and 106h old by Tuesday's if Monday
    # is a public holiday. 120h clears that and still fires on the real fault:
    # the September hole would have been caught on Monday 28th at 130h, two
    # trading days in, instead of never.
    Anchor("daily_prices", "market.daily_prices", "time", 24 * 5,
           "the newest trading day in the price table. No prices for five "
           "days means ingestion has stopped, which is the single most "
           "customer-visible failure this product has",
           cadence_hours=24, writer="scripts/eodhd/load_prices.py"),
    Anchor("screener_universe", "screener.universe", "universe_built_at", 24 * 5,
           "the canonical daily run rebuilds the served universe; if its "
           "timestamp stops advancing, every metric on the site is being "
           "served from an older computation than customers assume",
           cadence_hours=24,
           writer="scripts/eodhd/v2/build_screener_universe.py"),
    Anchor("short_positions", "market.short_positions", "updated_at", 24 * 10,
           "ASIC publishes weekly with a few days' lag; the job upserts on "
           "every successful download, so updated_at advances even when the "
           "report date does not",
           cadence_hours=24, writer="compute/engine/short_positions.py"),
    Anchor("top5_strategy", "strategy.monthly_picks", "computed_at", 24 * 15,
           "runs Sunday 22:00 UTC, inside the weekly canonical window, so it "
           "is the job most likely to defer; two missed Sundays is a fault",
           cadence_hours=24 * 7, writer="compute/engine/top5_strategy.py"),
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
    # A DATE column (market.daily_prices.time) comes back as `date`, which has
    # no tzinfo and would raise here. Midnight UTC is the conservative reading:
    # it makes the row look OLDER than any intraday timestamp would, so the
    # conversion can never understate staleness.
    if not isinstance(latest, datetime):
        latest = datetime(latest.year, latest.month, latest.day,
                          tzinfo=timezone.utc)
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


def coverage(relevant_tables: set[str]) -> dict:
    """How much of the freshness-relevant surface is actually watched.

    Added 3 Oct 2026. Before this, the check reported FRESH on two anchors and
    said nothing about the dozens of tables it had never been asked about —
    and `market.daily_prices`, the product's primary output, was one of them.
    A customer found a four-day hole that this check had been green through.

    "We enumerated some" must never again read as "we covered it", so the
    size of the unwatched set is reported every run. A shrinking `unclassified`
    count is progress; a silent two-anchor PASS is not.

    Pure: the caller derives `relevant_tables` and passes it in, because this
    module does no I/O. The intended derivation is the tables the API reads to
    serve customers AND that a scheduled job writes — staleness is only a
    fault where something is supposed to keep it fresh.
    """
    anchored = {a.table for a in ANCHORS}
    named = set(UNOBSERVABLE)
    unclassified = sorted(relevant_tables - anchored)
    return {
        "relevant": len(relevant_tables),
        "anchored": sorted(anchored & relevant_tables),
        "anchored_outside_population": sorted(anchored - relevant_tables),
        "named_unobservable": sorted(named),
        "unclassified": unclassified,
        "unclassified_count": len(unclassified),
        # Deliberately NOT a pass/fail. Classifying 41 tables is real work, and
        # gating on it today would either block the release or invite someone
        # to mark them all observable without checking. Visible and shrinking
        # beats hidden and complete-looking.
        "note": ("unclassified tables have no freshness anchor and no stated "
                 "reason; staleness in them would not be detected"),
    }


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
