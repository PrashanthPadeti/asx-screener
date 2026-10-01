#!/usr/bin/env python
"""
Assert that deferrable jobs actually produced output
=====================================================
One of two consumers of `compute.engine.output_freshness`. The other is the
admin `/system-health` endpoint, which evaluates the same registry through the
same classifier with its own driver — rather than reading this script's log,
which would make the surface a report of a report. A log that stopped being
written looks exactly like a log with nothing to say.

This one is the gate: it exits non-zero so a scheduled run means something.

A job that takes the auxiliary lease and finds a canonical run in flight
returns without writing. That is correct -- better no refresh than one
computed from PROVISIONAL rows -- and it is indistinguishable from a quiet
week, because the process exits 0 either way:

    short_positions: canonical execution holds the lease — skipping this cycle

Usage:
    python scripts/assert_output_freshness.py            # assert
    python scripts/assert_output_freshness.py --report   # never exits non-zero
    python scripts/assert_output_freshness.py --json     # machine-readable
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2                                                    # noqa: E402

from app.core.db import get_database_url_sync                      # noqa: E402
from compute.engine.output_freshness import (                      # noqa: E402
    ANCHORS, classify, existence_sql, latest_sql, summarise,
    unobservable_findings,
)


def evaluate(conn) -> list:
    """Execute the shared queries with psycopg2 and classify the results."""
    findings = []
    with conn.cursor() as cur:
        for anchor in ANCHORS:
            cur.execute(existence_sql(anchor))
            exists = bool(cur.fetchone()[0])

            latest = None
            if exists:
                cur.execute(latest_sql(anchor))
                latest = cur.fetchone()[0]

            findings.append(classify(anchor, exists, latest))
    return findings + unobservable_findings()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true",
                        help="print findings and exit 0 regardless")
    parser.add_argument("--json", action="store_true",
                        help="emit the same structure the admin surface returns")
    args = parser.parse_args()

    conn = psycopg2.connect(get_database_url_sync())
    try:
        findings = evaluate(conn)
    finally:
        conn.close()

    summary = summarise(findings)

    if args.json:
        print(json.dumps({"summary": summary,
                          "findings": [f.as_dict() for f in findings]},
                         indent=2))
        return 0 if (summary["healthy"] or args.report) else 1

    print("── output freshness")
    for f in findings:
        if f.state == "unobservable":
            continue
        label = {"current": "OK   ", "stale": "STALE",
                 "broken": "BROKEN"}[f.state]
        detail = (f"{f.table}.{f.column} = {f.observed_at} "
                  f"({f.age_hours:.1f}h old, limit {f.limit_hours}h)"
                  if f.age_hours is not None else f.reason)
        print(f"  {label}   {f.job:18s} {detail}")

    print("\n── not independently observable")
    for f in findings:
        if f.state == "unobservable":
            print(f"  n/a     {f.job:18s} {f.reason}")

    if summary["healthy"]:
        print(f"\nFRESH — {summary['current']} observable output(s) current, "
              f"{summary['unobservable']} not observable and named")
        return 0

    print("\nSTALE OUTPUT:")
    for f in findings:
        if f.faulty:
            print(f"  - {f.job}: {f.reason}")
    print("\nA deferred job is correct behaviour; a job that has deferred "
          "every cycle since its last success is not, and the two look "
          "identical in a log.")
    return 0 if args.report else 1


if __name__ == "__main__":
    sys.exit(main())
