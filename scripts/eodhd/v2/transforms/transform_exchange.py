"""
Transform: staging.exchange_symbols → market.exchange_list
==========================================================
Upserts ASX exchange symbol list into market.exchange_list.

Full run: truncates market.exchange_list first.
Partial run (--codes): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_exchange.py
    python scripts/eodhd/v2/transforms/transform_exchange.py --codes BHP CBA
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
        log.info("Full run — truncating market.exchange_list …")
        cur.execute("TRUNCATE TABLE market.exchange_list")
        conn.commit()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        cur.execute(f"""
            SELECT code, name, country, exchange, currency, type, isin, snapshot_date
            FROM staging.exchange_symbols
            WHERE code IN ({placeholders})
        """, [c.upper() for c in args.codes])
    else:
        cur.execute("""
            SELECT code, name, country, exchange, currency, type, isin, snapshot_date
            FROM staging.exchange_symbols
            ORDER BY code
        """)

    rows = cur.fetchall()
    log.info(f"Processing {len(rows):,} exchange symbol records …")

    if rows:
        execute_values(cur, """
            INSERT INTO market.exchange_list
                (asx_code, company_name, country, exchange, currency,
                 stock_type, isin, snapshot_date)
            VALUES %s
            ON CONFLICT (asx_code) DO UPDATE SET
                company_name  = EXCLUDED.company_name,
                country       = EXCLUDED.country,
                exchange      = EXCLUDED.exchange,
                currency      = EXCLUDED.currency,
                stock_type    = EXCLUDED.stock_type,
                isin          = EXCLUDED.isin,
                snapshot_date = EXCLUDED.snapshot_date,
                updated_at    = NOW()
        """, rows, page_size=2000)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {len(rows):,} rows upserted into market.exchange_list")


if __name__ == "__main__":
    main()
