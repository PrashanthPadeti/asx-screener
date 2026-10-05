#!/usr/bin/env python
"""
Does every served technical value equal its matching-as-of source row?
======================================================================
Read-only. The behavioural half of the v11.2.4 acceptance.

v11.2.4 bound `screener.universe`'s technical columns to the
`market.daily_metrics` row whose date matches the instrument's latest
published price, and removed twenty cross-frequency fallbacks that let a
weekly or monthly value occupy a daily metric's name.

Two different claims follow from that, and only one of them is about
behaviour:

  STRUCTURAL   the deployed projection contains no cross-frequency fallback.
               True the moment it deploys; proves nothing about served rows.
  BEHAVIOURAL  every served daily-semantic value EQUALS the value on the
               matching-as-of row.

A first attempt at the behavioural check asked only whether a matching row
EXISTS whenever a technical value is served. That returns zero while a stale
value sits in screener.universe beside a perfectly current daily_metrics row
-- existence of the right source is not provenance of the served value. So
this compares values, NULL-safely, with IS DISTINCT FROM.

The field population is PARSED FROM THE DEPLOYED BUILDER, not listed here.
Hand-listing would have covered the three fields someone happened to think of;
the repair touched twenty. If the builder gains a field, this follows it; if
the projection changes shape so nothing parses, the run says so and fails
rather than reporting a vacuous zero over an empty field set.

Usage:
    python scripts/diagnostics/assert_served_technicals_match_source.py
    python scripts/diagnostics/assert_served_technicals_match_source.py --builder PATH
"""

import argparse
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import psycopg2                                                    # noqa: E402

from app.core.db import get_database_url_sync                      # noqa: E402

BUILDER = BACKEND / "scripts" / "eodhd" / "v2" / "build_screener_universe.py"

#: The five constituents of governed momentum_score, marked in the report: a
#: mismatch here is invalid evidence reaching a governed metric, not a
#: mislabelled chart line.
MOMENTUM = {"return_1m", "return_3m", "return_6m", "rsi_14", "adx_14"}


def projection(builder: Path) -> list[tuple[str, str]]:
    """[(served_as, daily_metrics_column)] straight out of the SELECT list.

    TWO forms, and the second is easy to miss:

        dm.return_3m  AS return_3m     aliased
        dm.adx_14,                     bare -- served under its own name

    The first version of this function matched only the aliased form and
    found 21 of 43 fields. Among the 22 it missed was adx_14, a governed
    momentum constituent -- so the instrument would have reported a clean
    behavioural zero while covering under half the repair, including a field
    whose corruption reaches a governed metric.

    Caught by asserting momentum coverage rather than trusting the count,
    which is the only reason it is not still wrong.
    """
    raw = builder.read_text(encoding="utf-8")
    source = "\n".join(l for l in raw.splitlines()
                       if not l.strip().startswith("--"))

    found: dict[str, str] = {}
    for col, served in re.findall(r"\bdm\.(\w+)\s+AS\s+(\w+)\b", source):
        found[served] = col
    for col in re.findall(r"^\s+dm\.(\w+)\s*,\s*$", source, re.MULTILINE):
        found.setdefault(col, col)          # bare: served under its own name
    return sorted(found.items())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--builder", type=Path, default=BUILDER)
    args = ap.parse_args()

    fields = projection(args.builder)
    if not fields:
        print("REFUSING: no dm.<col> AS <alias> projections parsed from\n"
              f"  {args.builder}\n"
              "An empty field set would report zero mismatches over nothing.")
        return 2

    conn = psycopg2.connect(get_database_url_sync())
    cur = conn.cursor()

    print(f"  builder : {args.builder}")
    print(f"  fields  : {len(fields)} daily-semantic columns")

    # Coverage assertion, not a printed note.
    #
    # The parser once found 21 of 43 fields and would have reported a clean
    # zero over that subset. Momentum is the population whose corruption
    # reaches a governed metric, so its absence is a refusal rather than a
    # smaller number in a report nobody reads closely.
    covered = {s for s, _ in fields} & MOMENTUM
    if covered != MOMENTUM:
        print(f"REFUSING: the projection parser did not find "
              f"{sorted(MOMENTUM - covered)}, which feed governed "
              f"momentum_score. A zero over a partial field set is not "
              f"an acceptance.")
        conn.close()
        return 2
    print(f"  momentum constituents covered: {sorted(covered)}\n")

    # One pass, one predicate per field, so a single scan answers for all of
    # them and the per-field counts come back together.
    checks = ",\n".join(
        f"       count(*) FILTER (WHERE u.{served} IS DISTINCT FROM d.{col})"
        f" AS {served}"
        for served, col in fields)

    cur.execute(f"""
        WITH latest_price AS (
          SELECT asx_code,
                 max((time AT TIME ZONE INTERVAL '+10:00')::date) AS price_date
            FROM market.daily_prices GROUP BY asx_code),
        matching AS (
          SELECT d.* FROM market.daily_metrics d
            JOIN latest_price p
              ON p.asx_code = d.asx_code AND p.price_date = d.date)
        SELECT count(*) AS served,
{checks}
          FROM screener.universe u
          LEFT JOIN matching d ON d.asx_code = u.asx_code
         WHERE u.compute_run_id IS NOT NULL
    """)
    row = cur.fetchone()
    served, counts = row[0], row[1:]
    conn.rollback()
    conn.close()

    mismatched = [(s, n) for (s, _), n in zip(fields, counts) if n]
    total_mismatched_values = sum(counts)
    print(f"  active rows checked      : {served}")
    print(f"  field comparisons        : {served * len(fields):,} "
          f"({served} rows x {len(fields)} fields)")
    print(f"  mismatching field-values : {total_mismatched_values}")
    print(f"  fields with any mismatch : {len(mismatched)}")
    if not mismatched:
        print("\n  every served daily-semantic value equals its "
              "matching-as-of source row")
        return 0

    print("\n  MISMATCHES -- a served value does not equal the matching-as-of "
          "row:")
    for served_as, n in sorted(mismatched, key=lambda t: -t[1]):
        flag = "  <- GOVERNED MOMENTUM INPUT" if served_as in MOMENTUM else ""
        print(f"    {served_as:24s} {n:6d} rows{flag}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
