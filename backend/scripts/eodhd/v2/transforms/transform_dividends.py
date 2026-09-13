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

#: A full refresh may not drop the table below this fraction of what it is
#: replacing. Loose on purpose: dividend history is append-mostly, so growth is
#: normal and unbounded, while a sharp contraction means the inputs were
#: incomplete rather than that the market stopped paying.
SHRINK_FLOOR = 0.50


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="Permit a full refresh that would shrink the "
                             "table below the %d%% floor. For a genuinely "
                             "intended contraction only." % int(SHRINK_FLOOR * 100))
    args = parser.parse_args()

    is_full_run = not args.codes

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    # What is about to be replaced, measured before it is destroyed. This is
    # the inexpensive baseline: the table's own current contents. A full
    # refresh that would shrink it sharply is either a truncated raw zone or a
    # source that has stopped answering, and neither should be allowed to
    # overwrite a good dataset just because it technically produced rows.
    prior_rows = prior_issuers = 0
    if is_full_run:
        cur.execute("SELECT count(*), count(DISTINCT asx_code) "
                    "FROM market.dividends")
        prior_rows, prior_issuers = cur.fetchone()

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
    if is_full_run:
        new_issuers = len({t[0] for t in transformed})
        log.info("── full refresh, before commit")
        log.info("   staging rows read   : %s", f"{len(rows):,}")
        log.info("   rows transformed    : %s", f"{len(transformed):,}")
        log.info("   distinct issuers    : %s", f"{new_issuers:,}")
        log.info("   replacing           : %s rows / %s issuers",
                 f"{prior_rows:,}", f"{prior_issuers:,}")

        if not transformed:
            conn.rollback()
            log.error("Full run produced no rows. Rolling back rather than "
                      "committing an empty market.dividends. Check the raw "
                      "zone: data/raw/eodhd/exchange=AU/dividends/historical/")
            cur.close(); conn.close()
            sys.exit(1)

        # Technically non-zero is not the same as complete. A raw zone that is
        # half-downloaded, or a staging load that stopped partway, produces a
        # perfectly valid-looking set of rows that would silently replace a
        # good dataset with a worse one -- and nothing downstream could tell,
        # because a dividend that is absent and a dividend that never happened
        # are the same NULL.
        #
        # The threshold is deliberately loose. The September 2026 repair grew
        # the table 19,063 -> 29,804 (+56%), so growth is expected and never
        # blocked; this only refuses a sharp contraction, which no legitimate
        # refresh of an append-mostly history produces. Dividends are not
        # revised away.
        floor_rows = int(prior_rows * SHRINK_FLOOR)
        floor_issuers = int(prior_issuers * SHRINK_FLOOR)
        shrunk = (len(transformed) < floor_rows or new_issuers < floor_issuers)
        if shrunk and not args.allow_shrink:
            conn.rollback()
            log.error(
                "Full refresh would shrink market.dividends from %s rows / %s "
                "issuers to %s / %s, below the %.0f%% floor. Rolling back. "
                "A dividend history does not contract: check the raw zone is "
                "complete and the staging load finished. Pass --allow-shrink "
                "if the contraction is genuinely intended.",
                f"{prior_rows:,}", f"{prior_issuers:,}",
                f"{len(transformed):,}", f"{new_issuers:,}",
                SHRINK_FLOOR * 100)
            cur.close(); conn.close()
            sys.exit(1)
        if shrunk:
            log.warning("Refresh shrinks the table and --allow-shrink was "
                        "passed. Committing %s rows over %s.",
                        f"{len(transformed):,}", f"{prior_rows:,}")

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {len(transformed) if rows else 0:,} rows upserted into market.dividends")


if __name__ == "__main__":
    main()
