#!/usr/bin/env python
"""
How much served evidence is stale, or wearing another metric's name?
====================================================================
Read-only. Measures the exposure the P0-A reopening covers, BEFORE the patch
changes it.

Two populations, measured separately because they are different defects:

  FRESHNESS   a daily technical row served whose as-of date does not match
              the instrument's latest price date
  IDENTITY    a daily-semantic field populated from a weekly/monthly/yearly
              source because the daily value was absent

The second needs no staleness at all. Every source row can be perfectly
current and `rsi_14` still be a 14-MONTH oscillator, because the universe
COALESCEd into monthly_metrics whenever the daily row was missing. Reporting
"current exposure is zero" from the freshness measurement alone was wrong, and
that is why these are counted apart.

The mappings are EXTRACTED FROM THE DEPLOYED BUILDER, not listed here. A
hand-kept list drifts from the SQL it claims to describe; this one cannot
describe a fallback the builder no longer has, or miss one it gained.

Source identity is derived from COALESCE semantics, never by comparing values:

    dm.<col> non-null                      -> DAILY
    dm.<col> null, fallback non-null       -> FALLBACK   (identity exposure)
    both null                              -> ABSENT

Two independently computed indicators can coincide numerically. Only the
coalesce order says which one won.

Usage:
    python scripts/diagnostics/measure_evidence_identity_exposure.py
    python scripts/diagnostics/measure_evidence_identity_exposure.py --csv out.csv
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

#: The five constituents of governed momentum_score. Marked, because a
#: fallback into one of these is not merely a mislabelled chart line -- it is
#: invalid evidence reaching a governed metric.
MOMENTUM = ("return_1m", "return_3m", "return_6m", "rsi_14", "adx_14")

LATERALS = {
    "dm": ("market.daily_metrics",   "date"),
    "wm": ("market.weekly_metrics",  "week_date"),
    "mm": ("market.monthly_metrics", "month_date"),
    "ym": ("market.yearly_metrics",  "fiscal_year"),
}


def mappings(builder: Path = None) -> list[tuple[str, str, str, str]]:
    """(served_as, daily_col, fallback_alias, fallback_col) from the builder."""
    raw = (builder or BUILDER).read_text(encoding="utf-8")
    source = "\n".join(l for l in raw.splitlines()
                       if not l.strip().startswith("--"))
    out = []
    for m in re.finditer(
            r"COALESCE\(\s*dm\.(\w+)\s*,\s*(wm|mm|ym)\.(\w+)[^)]*\)\s*AS\s*(\w+)",
            source):
        daily, alias, fb_col, served = m.groups()
        out.append((served, daily, alias, fb_col))
    return out


def measure(conn, maps) -> list[dict]:
    rows = []
    with conn.cursor() as cur:
        for served, daily, alias, fb_col in maps:
            fb_table, fb_key = LATERALS[alias]
            cur.execute(f"""
                WITH src AS (
                  SELECT u.asx_code, u.compute_run_id,
                         (SELECT d.{daily} FROM market.daily_metrics d
                           WHERE d.asx_code = u.asx_code
                           ORDER BY d.date DESC LIMIT 1) AS daily_v,
                         (SELECT f.{fb_col} FROM {fb_table} f
                           WHERE f.asx_code = u.asx_code
                           ORDER BY f.{fb_key} DESC LIMIT 1) AS fb_v,
                         u.{served} AS stored
                    FROM screener.universe u)
                SELECT count(*) FILTER (WHERE daily_v IS NOT NULL),
                       count(*) FILTER (WHERE daily_v IS NULL AND fb_v IS NOT NULL),
                       count(*) FILTER (WHERE daily_v IS NULL AND fb_v IS NULL),
                       count(*) FILTER (WHERE daily_v IS NULL AND fb_v IS NOT NULL
                                          AND compute_run_id IS NOT NULL),
                       -- Reconstruction control.
                       --
                       -- Everything above REPLAYS the builder's lateral
                       -- selection; it does not read what the universe
                       -- actually stored. If an older build wrote that row
                       -- with different logic, the replay describes a
                       -- publication that never happened.
                       --
                       -- So compare the replay against the stored value. A
                       -- non-zero count here means the counts are estimates
                       -- and must be recorded as such.
                       count(*) FILTER (
                         WHERE COALESCE(daily_v, fb_v) IS DISTINCT FROM stored)
                  FROM src
            """)
            d, f, absent, f_active, mismatch = cur.fetchone()
            rows.append(dict(served_as=served, daily=daily,
                             fallback=f"{fb_table}.{fb_col}",
                             daily_won=d, fallback_won=f, absent=absent,
                             fallback_won_active=f_active,
                             reconstruction_mismatches=mismatch,
                             momentum_input=served in MOMENTUM))
    return rows


def freshness(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute("""
            WITH lag AS (
              SELECT d.asx_code, max(d.date) AS latest_metric,
                     (SELECT max((p.time AT TIME ZONE INTERVAL '+10:00')::date)
                        FROM market.daily_prices p
                       WHERE p.asx_code = d.asx_code) AS latest_price
                FROM market.daily_metrics d GROUP BY d.asx_code)
            SELECT count(*),
                   count(*) FILTER (WHERE EXISTS (
                     SELECT 1 FROM screener.universe u
                      WHERE u.asx_code = lag.asx_code
                        AND u.compute_run_id IS NOT NULL))
              FROM lag WHERE latest_metric < latest_price
        """)
        return cur.fetchone()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--builder", type=Path,
                    help="read the mappings from this builder instead. "
                         "Needed to measure the PRE-patch exposure from a "
                         "worktree whose builder is already patched.")
    args = ap.parse_args()

    maps = mappings(args.builder)
    conn = psycopg2.connect(get_database_url_sync())
    try:
        if not maps:
            print("no cross-frequency fallbacks in the deployed builder "
                  "-- identity exposure is zero BY CONSTRUCTION")
            rows = []
        else:
            rows = measure(conn, maps)
        stale, stale_served = freshness(conn)
    finally:
        conn.close()

    print(f"\n── freshness exposure")
    print(f"  {stale} codes have a daily metric row behind their latest price")
    print(f"  {stale_served} of those are actually served")

    if rows:
        print(f"\n── identity exposure ({len(rows)} fallback mappings found)")
        print(f"  {'served_as':22s} {'fallback source':34s} "
              f"{'daily':>7s} {'fallb':>7s} {'active':>7s}  momentum")
        for r in sorted(rows, key=lambda r: -r["fallback_won"]):
            print(f"  {r['served_as']:22s} {r['fallback']:34s} "
                  f"{r['daily_won']:7d} {r['fallback_won']:7d} "
                  f"{r['fallback_won_active']:7d}  "
                  f"{'YES' if r['momentum_input'] else ''}")
        bad = sum(r["reconstruction_mismatches"] for r in rows)
        if bad:
            print(f"\n  RECONSTRUCTION MISMATCHES: {bad} -- the replay "
                  f"disagrees with what the universe stored, so the counts "
                  f"above are ESTIMATES, not served-history evidence")
        else:
            print("\n  reconstruction control: 0 mismatches -- the replay "
                  "reproduces every stored value, so the counts are evidence")
        gov = sum(r["fallback_won_active"] for r in rows if r["momentum_input"])
        print(f"\n  governed exposure: {gov} active rows where a momentum "
              f"constituent was supplied by a coarser cadence")

    if args.csv and rows:
        import csv
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwritten to {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
