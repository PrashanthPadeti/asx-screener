#!/usr/bin/env python
"""
Assert that deferrable jobs actually produced output
=====================================================
A job that takes the auxiliary lease and finds a canonical run in flight
returns without writing. That is correct -- better no refresh than one
computed from PROVISIONAL rows -- and it is indistinguishable from a quiet
week. The process exits 0 either way.

    short_positions: canonical execution holds the lease — skipping this cycle

Nothing in the system reads that line. So "deferred" can become "never
refreshed again" and the first evidence is a number on the site that nobody
can date.

The rule this enforces, from [[engineering-rule-output-freshness]]:

    Output freshness proves a scheduled job is healthy. Not process exit,
    not alert delivery, not the absence of errors in a log.

`top5_strategy` is the sharpest case. It runs 0 22 * * 0 against a weekly
pipeline declared 0 21 * * 0 that took 1h46m on 1 Oct 2026, so deferral is
likely rather than rare.

WHAT THIS DELIBERATELY DOES NOT CLAIM
-------------------------------------
Two of the four deferrable jobs write only into `screener.universe`, which
the canonical run rebuilds wholesale. Their output carries no timestamp of
their own, so their freshness is NOT independently observable and this says
so rather than inventing a proxy. A check that cannot run has not passed.

Usage:
    python scripts/assert_output_freshness.py            # assert
    python scripts/assert_output_freshness.py --report   # never exits non-zero
"""

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2                                                    # noqa: E402

from app.core.db import get_database_url_sync                      # noqa: E402


class Anchor:
    """A job, the output that proves it ran, and how stale is too stale."""

    def __init__(self, job, table, column, max_age_hours, why):
        self.job = job
        self.table = table
        self.column = column
        self.max_age_hours = max_age_hours
        self.why = why


#: Jobs whose output IS independently observable.
#:
#: max_age is the cadence plus one full period, so a single deferral is
#: tolerated and a second consecutive one is not. A threshold tighter than the
#: cadence would fire on the behaviour the lease exists to produce.
ANCHORS = [
    Anchor("short_positions", "market.short_positions", "updated_at", 24 * 10,
           "ASIC publishes weekly with a few days' lag; the job upserts on "
           "every successful download, so updated_at advances even when the "
           "report date does not"),
    Anchor("top5_strategy", "strategy.monthly_picks", "computed_at", 24 * 15,
           "runs Sunday 22:00 UTC, inside the weekly canonical window, so it "
           "is the job most likely to defer; two missed Sundays is a fault"),
]

#: Jobs whose freshness CANNOT be observed from their own output, and why.
#:
#: Named rather than omitted. An unchecked job missing from a report reads as
#: a healthy one, which is the failure mode this whole file exists to remove.
UNOBSERVABLE = {
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


def _column_exists(cur, table: str, column: str) -> bool:
    schema, name = table.split(".", 1)
    cur.execute("""
        SELECT count(*) = 1 FROM information_schema.columns
         WHERE table_schema = %s AND table_name = %s AND column_name = %s
    """, (schema, name, column))
    return bool(cur.fetchone()[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true",
                        help="print findings and exit 0 regardless")
    args = parser.parse_args()

    conn = psycopg2.connect(get_database_url_sync())
    cur = conn.cursor()

    stale, broken = [], []
    print("── output freshness")
    for a in ANCHORS:
        # Verify the instrument before trusting it. A missing column would
        # otherwise raise, and an operator reading a traceback learns the
        # script is broken, not whether the job ran.
        if not _column_exists(cur, a.table, a.column):
            broken.append(f"{a.job}: {a.table}.{a.column} does not exist")
            print(f"  BROKEN  {a.job:18s} {a.table}.{a.column} missing")
            continue

        cur.execute(f"""
            SELECT max({a.column}),
                   EXTRACT(EPOCH FROM (NOW() - max({a.column}))) / 3600
              FROM {a.table}
        """)
        latest, age_hours = cur.fetchone()

        if latest is None:
            broken.append(f"{a.job}: {a.table} is empty")
            print(f"  EMPTY   {a.job:18s} {a.table} has no rows at all")
            continue

        age_hours = float(age_hours)
        ok = age_hours <= a.max_age_hours
        print(f"  {'OK   ' if ok else 'STALE'}   {a.job:18s} "
              f"{a.table}.{a.column} = {latest} "
              f"({age_hours:.1f}h old, limit {a.max_age_hours}h)")
        if not ok:
            stale.append(f"{a.job}: {a.table}.{a.column} is {age_hours:.1f}h "
                         f"old, limit {a.max_age_hours}h. {a.why}")

    print("\n── not independently observable")
    for job, why in sorted(UNOBSERVABLE.items()):
        print(f"  n/a     {job:18s} {why}")

    cur.close()
    conn.close()

    problems = stale + broken
    if not problems:
        print(f"\nFRESH — {len(ANCHORS)} observable output(s) current, "
              f"{len(UNOBSERVABLE)} not observable and named")
        return 0

    print("\nSTALE OUTPUT:")
    for p in problems:
        print(f"  - {p}")
    print("\nA deferred job is correct behaviour; a job that has deferred "
          "every cycle since its last success is not, and the two look "
          "identical in a log.")
    return 0 if args.report else 1


if __name__ == "__main__":
    sys.exit(main())
