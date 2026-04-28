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


def transform_prices(cur, codes: list[str] | None, from_date: str | None, to_date: str | None) -> int:
    filters = []
    params = []

    if codes:
        placeholders = ",".join(["%s"] * len(codes))
        filters.append(f"asx_code IN ({placeholders})")
        params.extend([c.upper() for c in codes])
    if from_date:
        filters.append("date >= %s")
        params.append(from_date)
    if to_date:
        filters.append("date <= %s")
        params.append(to_date)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    cur.execute(f"""
        SELECT asx_code, date, open, high, low, close, adjusted_close, volume
        FROM staging.eod_prices
        {where}
        ORDER BY asx_code, date
    """, params)

    rows = cur.fetchall()
    if not rows:
        log.info("No rows in staging.eod_prices matching filters.")
        return 0

    # Convert date → TIMESTAMPTZ at ASX market close
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

    execute_values(cur, """
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
    """, transformed, page_size=2000)

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

    log.info("Transforming staging.eod_prices → market.daily_prices …")
    n = transform_prices(cur, args.codes, args.from_date, args.to_date)
    conn.commit()

    cur.close()
    conn.close()
    log.info(f"DONE — {n:,} rows upserted into market.daily_prices")


if __name__ == "__main__":
    main()
