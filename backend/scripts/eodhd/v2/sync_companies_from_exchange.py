"""
Sync Companies Universe from Exchange Symbol List
==================================================
Ensures market.companies has a row for every ASX stock in
staging.exchange_symbols (EODHD /exchange-symbol-list/AU).

Why:
  market.companies is normally populated by transform_companies.py, which
  only creates rows for stocks whose fundamentals JSON has been downloaded.
  New listings and lightly-covered stocks are missing until their first
  fundamentals download. This script fills that gap so the screener
  universe is complete.

What it does:
  1. Reads all stocks from staging.exchange_symbols (type = 'Common Stock').
  2. Finds codes NOT already in market.companies (is_current = TRUE).
  3. Inserts a minimal market.companies row for each gap stock so the
     download and compute pipelines can pick it up.
  4. Logs additions for review.

Safe to re-run at any time — INSERT is guarded by the partial unique index
(asx_code WHERE is_current = TRUE), so duplicates are impossible.

Pre-requisite:
  Run download_exchange_symbols.py + load_to_staging_exchange_symbols.py first
  to ensure staging.exchange_symbols is up to date.

Usage:
    python scripts/eodhd/v2/sync_companies_from_exchange.py
    python scripts/eodhd/v2/sync_companies_from_exchange.py --dry-run
    python scripts/eodhd/v2/sync_companies_from_exchange.py --include-etfs
"""

import argparse
import logging
import os
from datetime import date

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TODAY = date.today()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be inserted without writing to DB",
    )
    parser.add_argument(
        "--include-etfs", action="store_true",
        help="Also sync ETF/Fund codes (default: Common Stock only)",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    # ── Step 1: check staging has data ────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM staging.exchange_symbols")
    staging_count = cur.fetchone()[0]
    if staging_count == 0:
        log.error(
            "staging.exchange_symbols is empty. "
            "Run download_exchange_symbols.py + load_to_staging_exchange_symbols.py first."
        )
        cur.close()
        conn.close()
        return

    log.info(f"staging.exchange_symbols has {staging_count:,} rows")

    # ── Step 2: find codes not yet in market.companies ─────────────────────────
    type_filter = "" if args.include_etfs else "AND UPPER(es.type) LIKE '%COMMON%'"

    cur.execute(f"""
        SELECT
            es.code            AS asx_code,
            es.name            AS company_name,
            es.type            AS stock_type,
            es.isin,
            es.currency
        FROM staging.exchange_symbols es
        WHERE es.exchange = 'AU'
          {type_filter}
          AND es.code IS NOT NULL
          AND LENGTH(es.code) BETWEEN 2 AND 6
          AND es.code ~ '^[A-Z0-9]+$'
          AND NOT EXISTS (
              SELECT 1 FROM market.companies mc
              WHERE mc.asx_code = es.code
                AND mc.is_current = TRUE
          )
        ORDER BY es.code
    """)

    new_stocks = cur.fetchall()
    log.info(f"Found {len(new_stocks):,} codes not in market.companies")

    if not new_stocks:
        log.info("Universe is already complete — nothing to add.")
        cur.close()
        conn.close()
        return

    # ── Step 3: preview ───────────────────────────────────────────────────────
    log.info("New codes to add:")
    for r in new_stocks[:20]:
        log.info(f"  {r[0]:6s}  {(r[1] or '')[:50]}")
    if len(new_stocks) > 20:
        log.info(f"  … and {len(new_stocks) - 20} more")

    if args.dry_run:
        log.info("DRY RUN — no changes written.")
        cur.close()
        conn.close()
        return

    # ── Step 4: insert missing stocks ─────────────────────────────────────────
    # Minimal row: only fields we know from exchange symbols.
    # All financial metrics / sector data will be filled by subsequent
    # fundamentals download + transform_companies.py run.
    rows = [
        (
            r[0],                          # asx_code
            r[1] or r[0],                  # company_name (fallback to code)
            r[2],                          # company_type
            r[3],                          # isin
            "active",                      # status
            TODAY,                         # valid_from
            None,                          # valid_to
            True,                          # is_current
        )
        for r in new_stocks
    ]

    execute_values(cur, """
        INSERT INTO market.companies
            (asx_code, company_name, company_type, isin,
             status, valid_from, valid_to, is_current)
        VALUES %s
        ON CONFLICT DO NOTHING
    """, rows, page_size=500)

    conn.commit()
    inserted = cur.rowcount
    log.info(f"Inserted {inserted:,} new company rows into market.companies")

    # ── Step 5: verify ────────────────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(*) FROM market.companies WHERE is_current = TRUE
    """)
    total = cur.fetchone()[0]
    log.info(f"market.companies total current rows: {total:,}")

    cur.close()
    conn.close()
    log.info("DONE")


if __name__ == "__main__":
    main()
