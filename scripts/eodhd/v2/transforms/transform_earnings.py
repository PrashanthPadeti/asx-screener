"""
Transform: staging.earnings → financials.earnings_quarterly
============================================================
Transforms EPS actuals/estimates from staging into financials.earnings_quarterly.
Derives beat_miss:
  eps_actual > eps_estimate  → 'beat'
  eps_actual < eps_estimate  → 'miss'
  eps_actual == eps_estimate → 'met'
  either NULL                → NULL

Only processes rows where period_type = 'actual' (not forward estimates).

Full run: truncates financials.earnings_quarterly first.
Partial run (--codes): upsert only.

Usage:
    python scripts/eodhd/v2/transforms/transform_earnings.py
    python scripts/eodhd/v2/transforms/transform_earnings.py --codes BHP CBA
"""

import logging
import os
import argparse
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL_SYNC",
           "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def _beat_miss(actual, estimate) -> str | None:
    if actual is None or estimate is None:
        return None
    if actual > estimate:
        return "beat"
    if actual < estimate:
        return "miss"
    return "met"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    args = parser.parse_args()

    is_full_run = not args.codes

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        log.info("Full run — truncating financials.earnings_quarterly …")
        cur.execute("TRUNCATE TABLE financials.earnings_quarterly RESTART IDENTITY")
        conn.commit()

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        cur.execute(f"""
            SELECT asx_code, date, eps_actual, eps_estimate, eps_difference, surprise_percent
            FROM staging.earnings
            WHERE period_type = 'actual'
              AND asx_code IN ({placeholders})
            ORDER BY asx_code, date
        """, [c.upper() for c in args.codes])
    else:
        cur.execute("""
            SELECT asx_code, date, eps_actual, eps_estimate, eps_difference, surprise_percent
            FROM staging.earnings
            WHERE period_type = 'actual'
            ORDER BY asx_code, date
        """)

    rows = cur.fetchall()
    log.info(f"Processing {len(rows):,} earnings records …")

    if rows:
        transformed = [
            (
                r[0],  # asx_code
                r[1],  # period_end_date
                r[2],  # eps_actual
                r[3],  # eps_estimate
                r[4],  # eps_difference
                r[5],  # surprise_pct
                _beat_miss(r[2], r[3]),  # beat_miss
                "eodhd",
            )
            for r in rows
        ]

        execute_values(cur, """
            INSERT INTO financials.earnings_quarterly
                (asx_code, period_end_date, eps_actual, eps_estimate,
                 eps_difference, surprise_pct, beat_miss, data_source)
            VALUES %s
            ON CONFLICT (asx_code, period_end_date) DO UPDATE SET
                eps_actual      = EXCLUDED.eps_actual,
                eps_estimate    = EXCLUDED.eps_estimate,
                eps_difference  = EXCLUDED.eps_difference,
                surprise_pct    = EXCLUDED.surprise_pct,
                beat_miss       = EXCLUDED.beat_miss,
                data_source     = EXCLUDED.data_source,
                loaded_at       = NOW()
        """, transformed, page_size=2000)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {len(rows):,} rows upserted into financials.earnings_quarterly")


if __name__ == "__main__":
    main()
