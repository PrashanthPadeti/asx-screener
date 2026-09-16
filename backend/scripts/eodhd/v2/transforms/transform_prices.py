"""
Transform: staging_au.eod_prices → market.daily_prices
=====================================================
Converts staging DATE rows to TIMESTAMPTZ (ASX market close = 16:00 AEST = 06:00 UTC)
and upserts into the TimescaleDB hypertable.

Full run (no filters): truncates market.daily_prices first for a clean reload.
Partial run (--codes / --from-date / --to-date): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_prices.py
    python scripts/eodhd/v2/transforms/transform_prices.py --codes BHP CBA
    python scripts/eodhd/v2/transforms/transform_prices.py --from-date 2024-01-01 --to-date 2024-12-31
"""

import logging
import os
import sys
import argparse
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from app.core.db import get_database_url_sync  # noqa: E402


load_dotenv()

DB_URL = get_database_url_sync()

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

BATCH_COMMIT = 100
# ASX close = 16:00 AEST = UTC+10 → 06:00 UTC
CLOSE_TIME = "16:00:00+10"


INSERT_SQL = """
    INSERT INTO market.daily_prices
        (time, asx_code, open, high, low, close, adjusted_close, volume, data_source)
    VALUES %s
    ON CONFLICT (time, asx_code) DO UPDATE SET
        open           = EXCLUDED.open,
        high           = EXCLUDED.high,
        low            = EXCLUDED.low,
        close          = EXCLUDED.close,
        adjusted_close = EXCLUDED.adjusted_close,
        volume         = EXCLUDED.volume,
        data_source    = EXCLUDED.data_source
"""


#: The exact inverse of the write.
#:
#: A row is stored at `date 16:00:00+10`, so converting back at a fixed +10
#: offset returns precisely the staging date it came from. 'Australia/Sydney'
#: would be the tempting spelling and is wrong in principle: it shifts to +11
#: under daylight saving, and the write does not. The two would still agree
#: today, because 06:00 UTC falls on the same calendar day at both offsets --
#: an agreement by luck, which is the kind that stops holding quietly.
STAGING_DATE = "(time AT TIME ZONE INTERVAL '+10:00')::date"

#: A per-code fingerprint of the complete set of dates held for that code.
#:
#: Set equality over (asx_code, digest) is set equality over (asx_code, date):
#: the digest covers every date the code has, in a canonical order, so two
#: sides agreeing on it agree member by member. That is what makes this a
#: proof rather than a sample -- and it is why counts are not the instrument.
#: Equal row counts over different days is a real failure mode here, and
#: min/max dates alone would miss a hole in the middle of the history.
#:
#: Done in SQL because the honest grain is roughly 6.7 million (code, date)
#: pairs. Materialising those in Python to compare them would cost more memory
#: than the transform itself, so the comparison is pushed to where the data is
#: and only ~1,900 digests come back.
def _digest_sql(table: str, date_expr: str, where: str) -> str:
    return f"""
        SELECT asx_code,
               COUNT(*)                                        AS n,
               md5(string_agg({date_expr}::text, ',' ORDER BY {date_expr})) AS digest
          FROM {table}
          {where}
         GROUP BY asx_code
    """


def transform_prices_for_code(cur, code: str, from_date: str | None, to_date: str | None) -> int:
    """Fetch, transform and insert rows for a single ASX code. Returns row count."""
    filters = ["asx_code = %s"]
    params  = [code]
    if from_date:
        filters.append("date >= %s"); params.append(from_date)
    if to_date:
        filters.append("date <= %s"); params.append(to_date)

    where = "WHERE " + " AND ".join(filters)
    cur.execute(f"""
        SELECT asx_code, date, open, high, low, close, adjusted_close, volume
        FROM staging_au.eod_prices
        {where}
        ORDER BY date
    """, params)

    rows = cur.fetchall()
    if not rows:
        return 0

    transformed = [
        (
            f"{r[1]} {CLOSE_TIME}",  # time
            r[0],                    # asx_code
            r[2], r[3], r[4],        # open, high, low
            r[5],                    # close
            r[6],                    # adjusted_close
            r[7],                    # volume
            "eodhd",                 # data_source
        )
        for r in rows
    ]

    execute_values(cur, INSERT_SQL, transformed, page_size=2000)
    return len(transformed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-date", help="YYYY-MM-DD inclusive")
    parser.add_argument("--to-date",   help="YYYY-MM-DD inclusive")
    parser.add_argument("--run-id",    type=int, default=None,
                        help="Record stage evidence against this compute run")
    args = parser.parse_args()

    is_full_run = not args.codes and not args.from_date and not args.to_date

    conn = psycopg2.connect(DB_URL)
    # Prove where this process ACTUALLY connected, before any mutation.
    # An inherited environment is intent; a live connection is fact. Outside
    # a discovery run this only logs, so the nightly pipeline is unaffected.
    from compute.engine.runtime_envelope import prove as _prove_envelope
    _prove_envelope("transform_prices", conn)
    cur  = conn.cursor()

    if is_full_run:
        # The destructive step needs a precondition. A full run truncates the
        # entire price history and rebuilds it from staging; if staging is
        # empty -- a failed load upstream, a wrong database -- the truncate
        # succeeds, the reload writes nothing, and every downstream producer
        # then computes correctly over no data.
        cur.execute("SELECT COUNT(*) FROM staging_au.eod_prices")
        staged = cur.fetchone()[0]
        if staged == 0:
            log.error("REFUSING full run: staging_au.eod_prices is empty. "
                      "Truncating market.daily_prices against an empty source "
                      "would destroy the price history and report success.")
            return 1
        log.info("Full run — truncating market.daily_prices (staging holds "
                 "%s rows) …", f"{staged:,}")
        cur.execute("TRUNCATE TABLE market.daily_prices")
        conn.commit()
        log.info("Truncated.")

    # Get list of codes to process.
    #
    # From eod_prices, which is the actual source of the rows, NOT from
    # staging_au.company_profile. The profile table was used for speed -- 1,878
    # rows against a DISTINCT over 6.7M -- and it is a different population. A
    # code present in the price feed but absent from the profile was never
    # transformed, and because a full run TRUNCATES first, its entire price
    # history was destroyed and not rebuilt, while `done` counted a clean run
    # and every downstream producer read the gap as an absence of trading.
    #
    # The DISTINCT is paid once per run. The proof below would have failed on
    # this, and the selection is fixed here rather than left for the proof to
    # report every night.
    if args.codes:
        all_codes = [c.upper() for c in args.codes]
    else:
        cur.execute("SELECT DISTINCT asx_code FROM staging_au.eod_prices "
                    "ORDER BY asx_code")
        all_codes = [r[0] for r in cur.fetchall()]

    total_codes = len(all_codes)
    log.info(f"Transforming {total_codes:,} codes from staging_au.eod_prices → market.daily_prices …")

    total_rows = done = failed = 0
    for i, code in enumerate(all_codes, 1):
        try:
            n = transform_prices_for_code(cur, code, args.from_date, args.to_date)
            total_rows += n
            done += 1
        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {code}: {e}")
            continue

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total_codes}]  ok={done}  err={failed}  rows={total_rows:,}")

    conn.commit()
    log.info(f"DONE — {done} codes  |  {total_rows:,} rows upserted  |  {failed} errors")

    ok = prove_population(cur, args, {"codes_failed": failed,
                                      "full_run": is_full_run})
    conn.commit()
    cur.close()
    conn.close()
    return 0 if ok else 1


def prove_population(cur, args, details: dict) -> bool:
    """Does market.daily_prices now hold exactly what staging holds?

    Asked of the TARGET AFTER the write, both directions, over the same window
    on both sides -- never as "does the target contain each expected code".
    market.daily_prices is a historical table: a containment query is satisfied
    by rows loaded months ago, so a run that transformed nothing at all would
    pass it for every company. That is the failure this is built to catch, and
    it is the one a containment check is structurally blind to.

    Comparing digests over a bounded window also makes a partial run provable
    on the same mechanism: if today's rows were missed, the target's digest for
    the window lacks today's date and the member differs, however much correct
    history sits beside it.
    """
    from compute.engine.run_stages import StageResult, report_population

    if args.codes:
        return report_population(
            cur, getattr(args, "run_id", None), None, log,
            scoped_reason="a scoped run's expected population is not the "
                          "source domain")

    # The same date window applied to both sides. Applying it to one side only
    # would report every row outside the window as a difference.
    src_where, tgt_where, params = [], [], []
    if args.from_date:
        src_where.append("date >= %s")
        tgt_where.append(f"{STAGING_DATE} >= %s")
        params.append(args.from_date)
    if args.to_date:
        src_where.append("date <= %s")
        tgt_where.append(f"{STAGING_DATE} <= %s")
        params.append(args.to_date)
    src_w = ("WHERE " + " AND ".join(src_where)) if src_where else ""
    tgt_w = ("WHERE " + " AND ".join(tgt_where)) if tgt_where else ""

    cur.execute(_digest_sql("staging_au.eod_prices", "date", src_w), params)
    expected = {(r[0], r[1], r[2]) for r in cur.fetchall()}

    cur.execute(_digest_sql("market.daily_prices", STAGING_DATE, tgt_w), params)
    written = {(r[0], r[1], r[2]) for r in cur.fetchall()}

    result = StageResult(
        "transform_prices",
        frozenset(expected), frozenset(written), details,
        grain="asx_code+row_count+date_set_digest")
    return report_population(cur, getattr(args, "run_id", None), result, log)


if __name__ == "__main__":
    # sys.exit, not a bare call: a price table that does not match its source
    # must stop the pipeline, not annotate it.
    sys.exit(main())
