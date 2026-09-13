"""
Transform: staging_au.dividends → market.dividends
================================================
Upserts all dividend records from staging into market.dividends.
staging_au.dividends now captures: value, unadjustedValue, currency,
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
import sys
from pathlib import Path

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from app.core.db import get_database_url_sync  # noqa: E402


load_dotenv()

DB_URL = get_database_url_sync()

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
        # NOT committed here. TRUNCATE is transactional in PostgreSQL, so it
        # belongs in the same transaction as the inserts that replace what it
        # removed.
        #
        # Committing the truncate on its own opens a window in which
        # market.dividends is empty and durably so: a crash, a bad row, or a
        # killed session between the two statements destroys the entire
        # dividend history with nothing to roll back to. The table is the sole
        # store — the raw zone could rebuild it, but only by re-running this
        # same script, and only if someone realised what had happened.
        #
        # Nothing had gone wrong here yet. The window was simply open, and
        # this is the script that was about to be run against production to
        # repair a four-month outage.
        log.info("Full run — truncating market.dividends (same transaction "
                 "as the reload) …")
        cur.execute("TRUNCATE TABLE market.dividends")

    if args.codes:
        placeholders = ",".join(["%s"] * len(args.codes))
        cur.execute(f"""
            SELECT asx_code, date, dividend, currency,
                   period, declaration_date, record_date, payment_date, franking_pct
            FROM staging_au.dividends
            WHERE asx_code IN ({placeholders})
            ORDER BY asx_code, date
        """, [c.upper() for c in args.codes])
    else:
        cur.execute("""
            SELECT asx_code, date, dividend, currency,
                   period, declaration_date, record_date, payment_date, franking_pct
            FROM staging_au.dividends
            ORDER BY asx_code, date
        """)

    rows = cur.fetchall()
    log.info(f"Processing {len(rows):,} dividend records …")

    # Bound before the branch. The empty-reload guard below reads it, and an
    # empty staging table is precisely the case that must reach that guard --
    # if `transformed` only existed when there was something to transform, the
    # check for having transformed nothing would raise NameError instead.
    transformed: list = []

    if rows:
        # Filter out rows where dividend amount is NULL (amount_per_share is NOT NULL)
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

    # A full run that produced nothing must not commit. With the truncate now
    # inside this transaction, committing an empty reload would replace the
    # entire dividend history with zero rows -- and the run would exit 0,
    # because reading no files and transforming no rows is not an error to any
    # code path above.
    #
    # The screener would then show every company as paying no dividend, which
    # is a false statement about 2,500 companies rather than a missing feed,
    # and the applicability contract would have no way to know: an empty table
    # and a table of genuine non-payers are identical.
    if is_full_run and not transformed:
        conn.rollback()
        log.error("Full run produced no rows. Rolling back rather than "
                  "committing an empty market.dividends. Check the raw zone: "
                  "%s", "data/raw/eodhd/exchange=AU/dividends/historical/")
        cur.close()
        conn.close()
        sys.exit(1)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {len(transformed) if rows else 0:,} rows upserted into market.dividends")


if __name__ == "__main__":
    main()
