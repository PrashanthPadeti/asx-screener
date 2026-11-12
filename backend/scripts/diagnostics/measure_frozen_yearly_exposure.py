#!/usr/bin/env python
"""
How many customers are served a value no current run produces?
==============================================================
Read-only. Measures finding 6b/6d's EXPOSURE before the repair.

The census of 9 Nov 2026 established the population: 64 columns of
market.yearly_metrics are absent from its only writer's INSERT, 27 never
populated and 37 holding values on 2.9% to 22.6% of 33,864 rows, all of
them restamped daily with a fresh computed_at.

What the census did not establish is how much of that reaches a customer.
Code tracing says exactly one column does -- ym.p_fcf_ratio becomes
screener.universe.price_to_fcf -- and this counts it.

WHY THE LATEST FISCAL YEAR IS THE ONLY ONE THAT MATTERS
-------------------------------------------------------
The universe joins yearly_metrics through a lateral that takes the most
recent fiscal year per company. A frozen p_fcf_ratio on a 2019 row is
served to nobody. So the exposed population is not "rows with a value", it
is "companies whose LATEST row has one" -- and the two differ by an order
of magnitude.

THE INVERSION, RE-MEASURED
--------------------------
The claim that these values came from a rejected method rests on three
window pairs being inverted. Re-measured here rather than quoted, because
the whole finding turns on it: under average_over, a 10-year count can
never exceed a 7-year count, since a longer window is strictly harder to
satisfy. Only the superseded _avg helper -- which took the last n list
entries and dropped Nones -- can order them that way.

SAFETY
------
market.yearly_metrics is an ordinary table of ~34k rows, not a hypertable,
so a count over it is bounded. The transaction is READ ONLY and asserted,
every statement is bounded by a timeout, and the process names itself.

Usage:
    python scripts/diagnostics/measure_frozen_yearly_exposure.py \\
        --env-file /opt/asx-screener/backend/.env

Exit codes: 0 measured · 2 refused or could not run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
BACKEND = _HERE.parents[2] if len(_HERE.parents) > 2 else _HERE.parent
if (BACKEND / "app").is_dir():
    sys.path.insert(0, str(BACKEND))

STATEMENT_TIMEOUT_MS = 30_000
APPLICATION_NAME = "measure_frozen_yearly_exposure"

#: The served column, and the universe column it becomes.
SERVED = ("p_fcf_ratio", "price_to_fcf")

#: Pairs whose counts cannot invert under the written contract.
INVERSIONS = (("avg_roe_7y", "avg_roe_10y"),
              ("avg_roce_7y", "avg_roce_10y"),
              ("avg_ebit_5y", "avg_ebit_10y"))

EXPOSURE = """
SELECT count(*)                       AS universe_rows,
       count(u.price_to_fcf)          AS served_a_frozen_ratio,
       round(100.0 * count(u.price_to_fcf) / NULLIF(count(*), 0), 1)
                                      AS pct
  FROM screener.universe u
"""

#: The same question from the other side: companies whose LATEST fiscal
#: year carries the value. Should agree with the universe count; a
#: disagreement means the lateral is not taking the row this assumes.
LATEST_YEAR = """
WITH latest AS (
    SELECT DISTINCT ON (asx_code) asx_code, fiscal_year, p_fcf_ratio
      FROM market.yearly_metrics
     ORDER BY asx_code, fiscal_year DESC
)
SELECT count(*)                  AS companies,
       count(p_fcf_ratio)        AS latest_row_has_a_value
  FROM latest
"""

ALL_YEARS = """
SELECT count(*)            AS rows_total,
       count(p_fcf_ratio)  AS p_fcf_ratio_present,
       min(computed_at)::date AS oldest_stamp,
       max(computed_at)::date AS newest_stamp
  FROM market.yearly_metrics
"""

#: Restated: of the rows CARRYING the value, how old is the oldest stamp?
#: If it equals the newest, there is no population of untouched old rows
#: and the values are being restamped as current.
STAMPS_OF_CARRIERS = """
SELECT count(*)               AS carrying_a_value,
       min(computed_at)::date AS oldest,
       max(computed_at)::date AS newest
  FROM market.yearly_metrics
 WHERE p_fcf_ratio IS NOT NULL
"""

INVERSION = """
SELECT count({short}) AS shorter_window,
       count({long})  AS longer_window
  FROM market.yearly_metrics
"""


def _dsn(env_file: str | None) -> str:
    if env_file:
        path = Path(env_file)
        if not path.exists():
            raise SystemExit(f"2  --env-file {path} does not exist")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(("DATABASE_URL_SYNC=", "DATABASE_URL=")):
                key, _, value = line.partition("=")
                os.environ.setdefault(key, value.strip().strip("\"'"))
    from app.core.db import get_database_url_sync
    return get_database_url_sync()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file")
    args = ap.parse_args()

    try:
        import psycopg2
        conn = psycopg2.connect(_dsn(args.env_file),
                                application_name=APPLICATION_NAME)
    except Exception as exc:                               # noqa: BLE001
        raise SystemExit(f"2  cannot reach the database: {exc}")

    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur.execute("SELECT current_setting('transaction_read_only')")
            if cur.fetchone()[0] != "on":
                raise SystemExit(
                    "2  transaction_read_only is not 'on' -- refusing")

            print("── served exposure: screener.universe.price_to_fcf "
                  "─────────────")
            cur.execute(EXPOSURE)
            rows, served, pct = cur.fetchone()
            print(f"  universe rows             {rows}")
            print(f"  serving a frozen ratio    {served}  ({pct}%)")
            print()
            print("  Every one of these is a number produced by a code path")
            print("  that no longer exists, sitting beside a computed_at "
                  "refreshed today.")

            print()
            print("── the same question from market.yearly_metrics "
                  "────────────────")
            cur.execute(LATEST_YEAR)
            companies, latest_has = cur.fetchone()
            print(f"  companies                       {companies}")
            print(f"  latest fiscal year has a value  {latest_has}")
            if served and abs(latest_has - served) > max(5, served * 0.02):
                print(f"  ** disagrees with the universe count ({served}). "
                      f"The lateral is not")
                print(f"     taking the row this measurement assumes; "
                      f"investigate before trusting either.")
            else:
                print("  agrees with the universe count, so the lateral "
                      "takes the latest year.")

            print()
            print("── all years, and whether the carriers are restamped "
                  "───────────")
            cur.execute(ALL_YEARS)
            total, present, oldest, newest = cur.fetchone()
            print(f"  rows {total}   p_fcf_ratio present {present}   "
                  f"computed_at {oldest} .. {newest}")
            cur.execute(STAMPS_OF_CARRIERS)
            carrying, c_old, c_new = cur.fetchone()
            print(f"  of the {carrying} carrying a value: computed_at "
                  f"{c_old} .. {c_new}")
            if c_old == c_new:
                print("  ** min == max: there is NO population of untouched "
                      "old rows.")
                print("     The values are being restamped as freshly "
                      "computed.")

            print()
            print("── the inversion: counts that the written contract cannot "
                  "produce ──")
            for short, long in INVERSIONS:
                cur.execute(INVERSION.format(short=short, long=long))
                s, l = cur.fetchone()
                mark = "  INVERTED" if l > s else ""
                print(f"  {short:<14} {s:>7}   {long:<15} {l:>7}{mark}")
            print()
            print("  A longer window is strictly harder to satisfy, so the "
                  "longer count can")
            print("  never exceed the shorter one under average_over. Where "
                  "it does, the")
            print("  values were produced by the superseded _avg helper.")

        conn.rollback()
    finally:
        conn.close()

    print()
    print("read-only, rolled back")
    print()
    print("EXPECTED AFTER THE REPAIR: serving a frozen ratio -> 0, and "
          "every")
    print("p_fcf_ratio_present -> 0, on the first yearly run that rewrites "
          "the rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
