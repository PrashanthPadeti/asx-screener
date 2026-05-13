"""
Transform: staging.eod_prices → market.daily_prices
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

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

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
        FROM staging.eod_prices
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
    args = parser.parse_args()

    is_full_run = not args.codes and not args.from_date and not args.to_date

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        log.info("Full run — truncating market.daily_prices …")
        cur.execute("TRUNCATE TABLE market.daily_prices")
        conn.commit()
        log.info("Truncated.")

    # Get list of codes to process
    # Use company_profile (1878 rows) instead of DISTINCT on 6.7M row eod_prices table
    if args.codes:
        all_codes = [c.upper() for c in args.codes]
    else:
        cur.execute("SELECT asx_code FROM staging.company_profile ORDER BY asx_code")
        all_codes = [r[0] for r in cur.fetchall()]

    total_codes = len(all_codes)
    log.info(f"Transforming {total_codes:,} codes from staging.eod_prices → market.daily_prices …")

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
    cur.close()
    conn.close()
    log.info(f"DONE — {done} codes  |  {total_rows:,} rows upserted  |  {failed} errors")


if __name__ == "__main__":
    main()
