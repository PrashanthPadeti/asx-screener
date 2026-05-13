"""
Transform: staging.dividends → market.dividends
================================================
Upserts all dividend records from staging into market.dividends.
staging.dividends now captures: value, unadjustedValue, currency,
period (Final/Interim/Special), declarationDate, recordDate,
paymentDate, franking_pct — all mapped to market.dividends columns.

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
            SELECT asx_code, date, dividend, currency,
                   period, declaration_date, record_date, payment_date, franking_pct
            FROM staging.dividends
            WHERE asx_code IN ({placeholders})
            ORDER BY asx_code, date
        """, [c.upper() for c in args.codes])
    else:
        cur.execute("""
            SELECT asx_code, date, dividend, currency,
                   period, declaration_date, record_date, payment_date, franking_pct
            FROM staging.dividends
            ORDER BY asx_code, date
        """)

    rows = cur.fetchall()
    log.info(f"Processing {len(rows):,} dividend records …")

    if rows:
        # Filter out rows where dividend amount is NULL (amount_per_share is NOT NULL)
        transformed = []
        for r in rows:
            asx_code, ex_date, dividend, currency, period, decl_date, rec_date, pay_date, franking_pct = r
            if dividend is None:
                continue
            # Normalise period → dividend_type
            div_type = period.lower() if period else None
            transformed.append((
                asx_code, ex_date, float(dividend),
                currency or "AUD",
                franking_pct,
                div_type,
                decl_date, rec_date, pay_date,
            ))

        skipped = len(rows) - len(transformed)
        if skipped:
            log.info(f"  Skipped {skipped} rows with NULL dividend amount")

        if transformed:
            execute_values(cur, """
                INSERT INTO market.dividends
                    (asx_code, ex_date, amount_per_share, currency,
                     franking_pct, dividend_type,
                     declared_date, record_date, pay_date)
                VALUES %s
                ON CONFLICT (asx_code, ex_date, dividend_type) DO UPDATE SET
                    amount_per_share = EXCLUDED.amount_per_share,
                    currency         = EXCLUDED.currency,
                    franking_pct     = EXCLUDED.franking_pct,
                    declared_date    = EXCLUDED.declared_date,
                    record_date      = EXCLUDED.record_date,
                    pay_date         = EXCLUDED.pay_date
            """, transformed, page_size=2000)
            log.info(f"  Inserted {len(transformed):,} rows")

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {len(transformed) if rows else 0:,} rows upserted into market.dividends")


if __name__ == "__main__":
    main()
