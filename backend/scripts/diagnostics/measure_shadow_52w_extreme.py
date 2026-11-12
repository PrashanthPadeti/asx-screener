#!/usr/bin/env python
"""
The shadow 52-week extreme, and what it has published
=====================================================
Read-only. Measures finding 13 BEFORE the fix changes it.

WHAT THE DEFECT ACTUALLY IS
---------------------------
The finding records it as "a derived metric escapes the governance of its
input". Reading the code says something narrower and more fixable: the
builder computes the 52-week extreme a SECOND time, with no coverage rule,
and derives four columns from that second number.

    build_screener_universe.py:1150
    LEFT JOIN LATERAL (
        SELECT MAX(high) AS high_52w, MIN(low) AS low_52w
        FROM market.daily_prices
        WHERE asx_code = c.asx_code
          AND time >= NOW() - INTERVAL '365 days'
    ) dp52 ON TRUE

MAX(high) over whatever rows happen to exist inside the window. No minimum
span, no anchor, nothing recorded. The governed producer --
technical_compute.rolling_extreme -> market.daily_metrics.high_52w -- blanks
a row whose series does not span 365 days and records why in window_states.

So two definitions of one quantity coexist, and the canonical commit
overwrites screener.universe.high_52w with the governed one while the four
columns derived from dp52 keep the shadow number. That is why the finding's
own measurement saw high_present = 0 and ratio_present = the whole row count:
the two columns never came from the same computation.

WHAT THIS MEASURES
------------------
  Q1  whether FACTOR_MODEL_V3 is frozen, which decides whether governing the
      four derived metrics needs V4
  Q2  the current state of all four derived columns, split by whether the
      governed extreme was withheld -- including the two BOOLEANS the
      finding did not count
  Q3  how far the shadow number is from the governed one where BOTH exist,
      which says whether the defect is confined to short histories or is
      general

SAFETY
------
Instruments are side-effect-free by default: the observer must not join the
system it observes nor consume its resources. A read-only query OOM-killed
production on 28 Oct 2026, so:

  * the transaction is READ ONLY and that is ASSERTED, not assumed
  * statement_timeout bounds every statement
  * application_name identifies this process in pg_stat_activity
  * market.daily_prices is NEVER touched. Reconstructing dp52 from it would
    be MAX(high) over 365 days for 2,566 companies against a hypertable,
    which is the exact shape of the 28 Oct incident. Q3 obtains the same
    answer from the 2,566-row table that already holds both numbers.

Usage:
    python scripts/diagnostics/measure_shadow_52w_extreme.py
    python scripts/diagnostics/measure_shadow_52w_extreme.py \\
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

#: Per-statement ceiling. Every statement here reads an ordinary table of a
#: few thousand rows; if one cannot finish in this long, something is wrong
#: with the assumption and the run should stop rather than persist.
STATEMENT_TIMEOUT_MS = 15_000

APPLICATION_NAME = "measure_shadow_52w_extreme"

#: Which version the code currently claims. Printed beside Q1 so the freeze
#: question is answered against the running contract rather than from memory.
try:
    from compute.engine.metric_states import LATEST_MODEL_VERSION
except Exception:                                              # noqa: BLE001
    LATEST_MODEL_VERSION = "(could not import metric_states)"


Q1 = """
SELECT r.factor_model_version,
       count(*)            AS runs,
       count(f.run_id)     AS finalised,
       min(r.run_at)::date AS first_run,
       max(r.run_at)::date AS last_run
  FROM screener.compute_runs r
  LEFT JOIN screener.compute_run_finalizations f ON f.run_id = r.id
 GROUP BY 1
 ORDER BY 1
"""

#: One statement per extreme rather than one wide statement over both.
#: Keeping them apart means a surprise in one does not cost the other, and
#: the high and the low are separate defects that happen to share a cause.
Q2 = """
SELECT (u.{extreme} IS NULL)                             AS extreme_withheld,
       count(*)                                          AS row_count,
       count(u.{ratio})                                  AS ratio_present,
       count(*) FILTER (WHERE u.{flag} IS TRUE)          AS flag_true,
       count(*) FILTER (WHERE u.{flag} IS FALSE)         AS flag_false,
       count(*) FILTER (WHERE u.{flag} IS NULL)          AS flag_null
  FROM screener.universe u
 GROUP BY 1
 ORDER BY 1
"""

#: The decisive one. Since v11.2.78 the builder computes the ratio from
#: dp52 while the stored extreme is the governed value, so differencing the
#: stored ratio against one recomputed from the stored extreme measures the
#: disagreement between the two producers with no access to either producer.
Q3 = """
SELECT count(*) AS both_present,
       count(*) FILTER (
         WHERE abs(u.{ratio} - (u.price / NULLIF(u.{extreme}, 0))) > 0.01
       ) AS differs_gt_1pct,
       round(max(abs(u.{ratio}
                     - (u.price / NULLIF(u.{extreme}, 0))))::numeric, 4)
         AS max_diff
  FROM screener.universe u
 WHERE u.{ratio} IS NOT NULL
   AND u.{extreme} > 0
   AND u.price IS NOT NULL
"""

#: The second layer, and the one the finding never saw.
#:
#: technical_compute reads SPLIT-ADJUSTED highs -- `_series("high")` returns
#: high_adj where the column exists -- because computing indicators from raw
#: prices put the exchange's worst performers at the top of "best 1-year
#: return" after their consolidations. dp52 reads RAW `high` from
#: market.daily_prices.
#:
#: So the two producers disagree for every stock that split inside the
#: window, by the split factor. A 1-for-10 consolidation leaves the raw high
#: ten times the adjusted one, so price_to_52w_high computed from dp52 is
#: ten times too SMALL: a stock sitting at its 52-week high is published at
#: 10% of it. That is not a short-history edge case -- it is the stocks the
#: split-adjustment work exists for.
#:
#: Counted from market.splits, which is small and not a hypertable.
Q4 = """
SELECT count(DISTINCT s.asx_code) AS companies_split_in_window,
       count(*)                   AS splits_in_window,
       min(s.split_date)          AS earliest,
       max(s.split_date)          AS latest
  FROM market.splits s
  JOIN screener.universe u ON u.asx_code = s.asx_code
 WHERE s.split_date >= CURRENT_DATE - 365
"""

#: Of those, how many are actually exposed: a split in the window AND a
#: published ratio. A company with no ratio cannot be showing a wrong one.
Q5 = """
SELECT count(DISTINCT u.asx_code) AS exposed_companies
  FROM screener.universe u
  JOIN market.splits s ON s.asx_code = u.asx_code
 WHERE s.split_date >= CURRENT_DATE - 365
   AND (u.price_to_52w_high IS NOT NULL OR u.price_to_52w_low IS NOT NULL)
"""

#: extreme column, derived ratio, derived boolean. Listed rather than
#: derived from a naming rule: price_to_52w_high pairs with high_52w by
#: meaning, not by spelling, and a rule that guessed it would also
#: confidently guess wrong for the next pair.
PAIRS = (
    ("high_52w", "price_to_52w_high", "new_52w_high"),
    ("low_52w",  "price_to_52w_low",  "new_52w_low"),
)


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


def _rows(cur, sql: str) -> tuple[list[str], list[tuple]]:
    cur.execute(sql)
    return [d[0] for d in cur.description], cur.fetchall()


def _table(header: list[str], rows: list[tuple]) -> None:
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows
              else len(str(h)) for i, h in enumerate(header)]
    print("  " + "  ".join(f"{h:<{widths[i]}}" for i, h in enumerate(header)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(f"{str(v):<{widths[i]}}"
                               for i, v in enumerate(r)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file",
                    help="path to the .env holding the credential, for when "
                         "this runs from outside the checkout")
    args = ap.parse_args()

    try:
        import psycopg2
        conn = psycopg2.connect(
            _dsn(args.env_file), application_name=APPLICATION_NAME)
    except Exception as exc:                                   # noqa: BLE001
        raise SystemExit(f"2  cannot reach the database: {exc}")

    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")

            # Asserted, not assumed. set_session is a client-side request and
            # a pooler or a server default could leave the session writable;
            # a measurement that believes it is read-only without checking is
            # the instrument joining the system it observes.
            cur.execute("SELECT current_setting('transaction_read_only')")
            state = cur.fetchone()[0]
            if state != "on":
                raise SystemExit(
                    f"2  transaction_read_only is {state!r}, not 'on' -- "
                    f"refusing to run a diagnostic that could write")

            print(f"code claims LATEST_MODEL_VERSION = {LATEST_MODEL_VERSION}")
            print()
            print("── Q1  model versions and whether they are frozen "
                  "───────────────────")
            header, rows = _rows(cur, Q1)
            _table(header, rows)
            frozen = sorted(r[0] for r in rows if r[2] and int(r[2]) > 0)
            print()
            print(f"  frozen (a finalised run references them): "
                  f"{', '.join(frozen) if frozen else 'none'}")
            if LATEST_MODEL_VERSION in frozen:
                print(f"  => {LATEST_MODEL_VERSION} is FROZEN. Governing the "
                      f"four derived metrics needs the NEXT version.")
            else:
                print(f"  => {LATEST_MODEL_VERSION} is still amendable.")

            for extreme, ratio, flag in PAIRS:
                print()
                print(f"── Q2  {extreme} and what is derived from it "
                      f"────────────────────")
                header, rows = _rows(
                    cur, Q2.format(extreme=extreme, ratio=ratio, flag=flag))
                _table(header, rows)
                # By name, not by position. A column added to Q2 later would
                # silently shift a positional read and the sentence below
                # would report the wrong number while still looking right.
                withheld = [dict(zip(header, r)) for r in rows
                            if r[0] is True]
                if withheld:
                    w = withheld[0]
                    print()
                    print(f"  {extreme} withheld on {w['row_count']} rows: "
                          f"{ratio} present on {w['ratio_present']}, "
                          f"{flag} FALSE on {w['flag_false']}, "
                          f"NULL on {w['flag_null']}")

                print()
                print(f"── Q3  shadow vs governed where both exist "
                      f"({ratio}) ─────────")
                header, rows = _rows(
                    cur, Q3.format(extreme=extreme, ratio=ratio))
                _table(header, rows)

            print()
            print("── Q4  splits inside the window: the raw-vs-adjusted layer "
                  "────────")
            header, rows = _rows(cur, Q4)
            _table(header, rows)

            print()
            print("── Q5  of those, how many publish a derived ratio "
                  "─────────────────")
            header, rows = _rows(cur, Q5)
            _table(header, rows)

        conn.rollback()
    finally:
        conn.close()

    print()
    print("read-only, rolled back, market.daily_prices untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
