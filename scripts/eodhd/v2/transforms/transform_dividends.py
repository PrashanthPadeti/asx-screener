"""
Transform: staging.dividends → market.dividends
================================================
Upserts all dividend records from staging into market.dividends.
staging.dividends has ex-date, amount, unadjusted_value, currency.
market.dividends adds payment_date, record_date, declared_date, div_type,
franking_pct — these are set to NULL (not available from EODHD bulk endpoint).

Full run: truncates market.dividends first.
Partial run (--codes): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_dividends.py
    python scripts/eodhd/v2/transforms/transform_dividends.py --codes BHP CBA
"""

import logging
import os
import argparse

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    args = parser.parse_args()

    is_full_run = not args.codes

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        log.info("Full run — truncating market.dividends …")
        cur.execute("TRUNCATE TABLE market.dividends")
        conn.commit()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        cur.execute(f"""
            SELECT asx_code, date, dividend, unadjusted_value, currency
            FROM staging.dividends
            WHERE asx_code IN ({placeholders})
            ORDER BY asx_code, date
        """, [c.upper() for c in args.codes])
    else:
        cur.execute("""
            SELECT asx_code, date, dividend, unadjusted_value, currency
            FROM staging.dividends
            ORDER BY asx_code, date
        """)

    rows = cur.fetchall()
    log.info(f"Processing {len(rows):,} dividend records …")

    if rows:
        transformed = [
            (r[0], r[1], r[2], r[3], r[4] or "AUD", "eodhd")
            for r in rows
        ]
        execute_values(cur, """
            INSERT INTO market.dividends
                (asx_code, ex_date, amount, unadjusted_value, currency, data_source)
            VALUES %s
            ON CONFLICT (asx_code, ex_date) DO UPDATE SET
                amount           = EXCLUDED.amount,
                unadjusted_value = EXCLUDED.unadjusted_value,
                currency         = EXCLUDED.currency,
                data_source      = EXCLUDED.data_source,
                loaded_at        = NOW()
        """, transformed, page_size=2000)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {len(rows):,} rows upserted into market.dividends")


if __name__ == "__main__":
    main()
