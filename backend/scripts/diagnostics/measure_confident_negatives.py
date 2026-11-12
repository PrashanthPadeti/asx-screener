#!/usr/bin/env python
"""
How many served rows assert a signal they could not compute?
============================================================
Read-only. Measures finding 15 BEFORE the fix changes it.

THE DEFECT
----------
`technical_compute` wrote every boolean in market.daily_metrics as a bare
pandas comparison:

    df["above_sma200"] = c > df["sma_200"]

In pandas a comparison against NaN yields **False**, not NaN, and `_v()`
converts np.bool_(False) to False. So a stock with 100 bars -- enough for
an RSI, not enough for a 200-day average -- was published with
`above_sma200 = false`: a measured claim about an average that does not
exist.

Finding 10 closed partly on the claim that this table "already writes NULL
for an uncomputable signal". It does not, and unlike finding 10's weekly
equivalents these reach the customer: screener.universe reads above_sma50,
above_sma200, golden_cross and death_cross straight from here, and they are
registered filter fields.

WHY THIS MEASURES THE UNIVERSE AND NOT market.daily_metrics
-----------------------------------------------------------
market.daily_metrics is a TimescaleDB hypertable holding every trading day
for every company. Counting a predicate across it is the shape that
OOM-killed production on 28 Oct 2026, and it would answer a question nobody
asked: a false on a row from 2023 is not served to anyone.

screener.universe holds the LATEST row per company -- the one that is
actually published -- and it carries both the flags and the inputs they
were computed from. 2,569 ordinary rows answer the question that matters:
how many customers see a confident negative today.

The pairing is the evidence. `above_sma200 = false` beside `sma_200 IS
NULL` cannot be anything but a comparison against a value that was not
there.

SAFETY
------
  * READ ONLY, asserted rather than assumed
  * statement_timeout on every statement
  * application_name set, so the process is identifiable
  * market.daily_metrics and market.daily_prices are never touched

Usage:
    python scripts/diagnostics/measure_confident_negatives.py \\
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

STATEMENT_TIMEOUT_MS = 15_000
APPLICATION_NAME = "measure_confident_negatives"

#: flag column -> the inputs whose absence makes it unknowable.
#:
#: Taken from the producer, not guessed. A flag is unknowable when ANY of
#: its inputs is absent, so these are combined with OR below.
#:
#: golden_cross and death_cross need both averages AND both PREVIOUS
#: values; the universe carries only the current ones, so their counts are
#: a LOWER BOUND -- a row with sma_200 present may still have had no
#: sma_200_prev. Stated rather than quietly reporting the smaller number:
#: the measurement must not claim more precision than its inputs allow.
PAIRS = {
    "above_sma50":     ("sma_50",),
    "above_sma200":    ("sma_200",),
    "golden_cross":    ("sma_50", "sma_200"),
    "death_cross":     ("sma_50", "sma_200"),
    "volume_breakout": ("relative_volume",),
}

TOTAL = "SELECT count(*) AS universe_rows FROM screener.universe"

#: One statement per flag. A single wide statement would be faster and
#: would also make one surprise cost every other answer.
PER_FLAG = """
SELECT count(*)                                            AS rows_total,
       count(*) FILTER (WHERE u.{flag} IS TRUE)            AS flag_true,
       count(*) FILTER (WHERE u.{flag} IS FALSE)           AS flag_false,
       count(*) FILTER (WHERE u.{flag} IS NULL)            AS flag_null,
       count(*) FILTER (WHERE {absent})                    AS input_absent,
       count(*) FILTER (WHERE u.{flag} IS FALSE AND {absent})
         AS confident_negatives,
       count(*) FILTER (WHERE u.{flag} IS TRUE AND {absent})
         AS confident_positives
  FROM screener.universe u
"""


#: How many of the five flags a single instrument carries as a confident
#: negative, and how many instruments sit at each count.
#:
#: WHY THIS EXISTS. The first run reported 38, 547, 547, 547 and 72, and the
#: write-up concluded "547 rows carried three confident negatives each".
#: That was published from equal COUNTS, which do not establish identical
#: ROWS: three flags at 547 is equally consistent with 547 overlapping rows
#: and with 1,641 distinct ones.
#:
#: The conclusion does follow from the numbers, and the derivation is worth
#: writing down because it is not obvious:
#:
#:   absent(above_sma200) is `sma_200 IS NULL`
#:   absent(golden_cross) is `sma_50 IS NULL OR sma_200 IS NULL`
#:   so the first is a SUBSET of the second, and both measured 754 --
#:   a subset of equal size is the same set.
#:
#:   Inside that 754: TRUE was 0 and FALSE was 547, so NULL inside absent
#:   is 207 -- which equals the whole-table NULL count, so every NULL lies
#:   inside absent. The FALSE set is therefore absent minus those 207: the
#:   same 547 rows for all three flags.
#:
#: Sound, and still an inference drawn from a subset relation read out of
#: SQL by hand. This measures it per instrument instead, so the claim rests
#: on the database rather than on my reading of the predicate.
#:
#: Built from PAIRS rather than written out, so a flag added above cannot
#: silently drop out of the overlap.
OVERLAP = """
SELECT flags_affected, count(*) AS instruments
  FROM (
    SELECT u.asx_code,
           {terms} AS flags_affected
      FROM screener.universe u
  ) t
 GROUP BY 1
 ORDER BY 1
"""


def _overlap_sql() -> str:
    terms = "\n         + ".join(
        "(CASE WHEN u.{flag} IS FALSE AND ({absent}) THEN 1 ELSE 0 END)".format(
            flag=flag,
            absent=" OR ".join(f"u.{i} IS NULL" for i in inputs))
        for flag, inputs in PAIRS.items())
    return OVERLAP.format(terms=terms)


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
            state = cur.fetchone()[0]
            if state != "on":
                raise SystemExit(
                    f"2  transaction_read_only is {state!r}, not 'on' -- "
                    f"refusing to run a diagnostic that could write")

            cur.execute(TOTAL)
            total = cur.fetchone()[0]
            print(f"screener.universe: {total} rows\n")

            header = ("flag", "TRUE", "FALSE", "NULL", "input absent",
                      "confident NEG", "confident POS")
            print("  {:<18} {:>7} {:>7} {:>7} {:>13} {:>14} {:>14}"
                  .format(*header))
            print("  " + "-" * 86)

            worst = []
            for flag, inputs in PAIRS.items():
                # OR, not AND. A signal is unknowable when ANY input it
                # compares is absent. Joining with AND would have counted
                # only rows missing BOTH averages and silently skipped the
                # common case -- sma_50 present, sma_200 absent -- which is
                # the entire population this measurement exists to find.
                absent = "(" + " OR ".join(
                    f"u.{i} IS NULL" for i in inputs) + ")"
                cur.execute(PER_FLAG.format(flag=flag, absent=absent))
                (_rows, t, f, n, absent_n, neg, pos) = cur.fetchone()
                print("  {:<18} {:>7} {:>7} {:>7} {:>13} {:>14} {:>14}"
                      .format(flag, t, f, n, absent_n, neg, pos))
                worst.append((flag, neg, pos, absent_n))

            print()
            served = sum(n for _f, n, _p, _a in worst)
            print(f"  confident negatives across the five flags: {served} "
                  f"FLAG-ROWS, not instruments")
            print()

            print("── how many flags a single instrument carries "
                  "──────────────────")
            cur.execute(_overlap_sql())
            rows = cur.fetchall()
            print("  {:>14}  {:>11}".format("flags affected", "instruments"))
            print("  " + "-" * 29)
            affected = 0
            for count, instruments in rows:
                print("  {:>14}  {:>11}".format(count, instruments))
                if count:
                    affected += instruments
            print(f"\n  instruments carrying at least one: {affected}")
            print("  This is the number to quote. Equal per-flag counts do "
                  "NOT establish")
            print("  identical rows, and the earlier write-up published "
                  "that inference")
            print("  before measuring it.")
            print()
            print("  A 'confident negative' is FALSE where the input the "
                  "comparison needed is NULL.")
            print("  A 'confident positive' is TRUE in the same state, "
                  "which should be impossible")
            print("  and is reported separately so it cannot hide inside "
                  "the negatives.")
            print()
            print("  golden_cross and death_cross also need the PREVIOUS "
                  "averages, which the")
            print("  universe does not carry, so their counts are a LOWER "
                  "BOUND.")

        conn.rollback()
    finally:
        conn.close()

    print()
    print("read-only, rolled back; the hypertables were not touched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
