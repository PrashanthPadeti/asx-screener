"""
backfill_yfinance_prices.py
────────────────────────────
Fetch price history from Yahoo Finance for ASX stocks that have no rows
in market.daily_prices (i.e. price_date IS NULL in screener.universe).

Typical use case: ETFs not covered by EODHD's ASX bulk-download feed.

Usage:
    python scripts/eodhd/v2/backfill_yfinance_prices.py
    python scripts/eodhd/v2/backfill_yfinance_prices.py --days 30
    python scripts/eodhd/v2/backfill_yfinance_prices.py --codes AAA AGVT AESG
    python scripts/eodhd/v2/backfill_yfinance_prices.py --dry-run
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

DB_URL       = os.getenv("DATABASE_URL_SYNC",
                   "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
BATCH_COMMIT = 50   # commit every N codes
SLEEP_SEC    = 0.3  # polite delay between Yahoo requests

# ── SQL ────────────────────────────────────────────────────────────────────────

# Active stocks with no price data at all in market.daily_prices
MISSING_CODES_SQL = """
    SELECT DISTINCT u.asx_code
    FROM   screener.universe u
    JOIN   market.companies  c ON c.asx_code = u.asx_code
    WHERE  u.price_date IS NULL
    AND    c.status     = 'active'
    ORDER  BY u.asx_code
"""

UPSERT_SQL = """
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

# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_yahoo(code: str, period_days: int) -> list[tuple]:
    """
    Download OHLCV from Yahoo Finance for {code}.AX.
    Returns list of row tuples ready for UPSERT_SQL.
    """
    ticker = yf.Ticker(f"{code}.AX")
    start  = (datetime.now(timezone.utc) - timedelta(days=period_days)).strftime("%Y-%m-%d")
    hist   = ticker.history(start=start, auto_adjust=False)

    if hist.empty:
        return []

    rows = []
    for date_idx, row in hist.iterrows():
        # Normalise index to a plain date string
        if hasattr(date_idx, "strftime"):
            date_str = date_idx.strftime("%Y-%m-%d")
        else:
            date_str = str(date_idx)[:10]

        # ASX market close = 16:00 AEST (UTC+10)
        ts = f"{date_str} 16:00:00+10"

        rows.append((
            ts,
            code,
            float(row["Open"])   if row["Open"]   is not None else None,
            float(row["High"])   if row["High"]   is not None else None,
            float(row["Low"])    if row["Low"]    is not None else None,
            float(row["Close"])  if row["Close"]  is not None else None,
            float(row["Adj Close"]) if "Adj Close" in row and row["Adj Close"] is not None else None,
            int(row["Volume"])   if row["Volume"] is not None else None,
            "yahoo",
        ))

    return rows


def run(codes: list[str], period_days: int, dry_run: bool) -> None:
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    total_codes  = len(codes)
    total_rows   = 0
    skipped      = 0
    committed    = 0

    print(f"{'[DRY RUN] ' if dry_run else ''}Backfilling {total_codes} codes "
          f"({period_days} days of history from Yahoo Finance)\n")

    for i, code in enumerate(codes, 1):
        try:
            rows = fetch_yahoo(code, period_days)
        except Exception as exc:
            print(f"  [{i}/{total_codes}] {code}.AX  ERROR: {exc}")
            skipped += 1
            time.sleep(SLEEP_SEC)
            continue

        if not rows:
            print(f"  [{i}/{total_codes}] {code}.AX  — no data returned (not listed on Yahoo?)")
            skipped += 1
            time.sleep(SLEEP_SEC)
            continue

        print(f"  [{i}/{total_codes}] {code}.AX  {len(rows)} rows  "
              f"({rows[-1][0][:10]} → {rows[0][0][:10]})")

        if not dry_run:
            psycopg2.extras.execute_values(cur, UPSERT_SQL, rows, page_size=500)
            total_rows += len(rows)

            if i % BATCH_COMMIT == 0:
                conn.commit()
                committed += 1
                print(f"    ↳ committed batch ({committed})")

        time.sleep(SLEEP_SEC)

    if not dry_run:
        conn.commit()
        print(f"\nDone. {total_rows} rows upserted across "
              f"{total_codes - skipped} codes ({skipped} skipped).")
    else:
        print(f"\n[DRY RUN] Would have processed {total_codes} codes "
              f"({skipped} with no Yahoo data).")

    cur.close()
    conn.close()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Yahoo Finance prices for ETFs missing from EODHD")
    parser.add_argument("--codes",   nargs="+", metavar="CODE",
                        help="Specific ASX codes to backfill (default: all active with NULL price_date)")
    parser.add_argument("--days",    type=int, default=90,
                        help="Days of history to fetch (default: 90)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be fetched without writing to DB")
    args = parser.parse_args()

    if args.codes:
        codes = [c.upper() for c in args.codes]
        print(f"Using {len(codes)} codes from --codes argument")
    else:
        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor()
        cur.execute(MISSING_CODES_SQL)
        codes = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        print(f"Found {len(codes)} active codes with NULL price_date in screener.universe")

    if not codes:
        print("Nothing to do.")
        sys.exit(0)

    run(codes, args.days, args.dry_run)


if __name__ == "__main__":
    main()
