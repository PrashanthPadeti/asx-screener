"""
Transform: staging.analyst_ratings → market.analyst_ratings
============================================================
Upserts analyst consensus per stock into market.analyst_ratings.
One row per stock (snapshot table — overwritten each refresh).

Full run: truncates market.analyst_ratings first.
Partial run (--codes): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_analyst_ratings.py
    python scripts/eodhd/v2/transforms/transform_analyst_ratings.py --codes BHP CBA
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
        log.info("Full run — truncating market.analyst_ratings …")
        cur.execute("TRUNCATE TABLE market.analyst_ratings")
        conn.commit()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        cur.execute(f"""
            SELECT asx_code, rating, target_price,
                   strong_buy, buy, hold, sell, strong_sell
            FROM staging.analyst_ratings
            WHERE asx_code IN ({placeholders})
        """, [c.upper() for c in args.codes])
    else:
        cur.execute("""
            SELECT asx_code, rating, target_price,
                   strong_buy, buy, hold, sell, strong_sell
            FROM staging.analyst_ratings
        """)

    rows = cur.fetchall()
    log.info(f"Processing {len(rows):,} analyst rating records …")

    if rows:
        execute_values(cur, """
            INSERT INTO market.analyst_ratings
                (asx_code, rating, target_price,
                 strong_buy, buy, hold, sell, strong_sell,
                 data_source, updated_at)
            VALUES %s
            ON CONFLICT (asx_code) DO UPDATE SET
                rating       = EXCLUDED.rating,
                target_price = EXCLUDED.target_price,
                strong_buy   = EXCLUDED.strong_buy,
                buy          = EXCLUDED.buy,
                hold         = EXCLUDED.hold,
                sell         = EXCLUDED.sell,
                strong_sell  = EXCLUDED.strong_sell,
                data_source  = EXCLUDED.data_source,
                updated_at   = NOW()
        """, [r + ("eodhd",) for r in rows], page_size=1000)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {len(rows):,} rows upserted into market.analyst_ratings")


if __name__ == "__main__":
    main()
