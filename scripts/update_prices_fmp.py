"""
ASX Screener — FMP Nightly Price Updater
=========================================
Fetches the last 7 days of prices for all active stocks using FMP.
Replaces update_prices.py (Yahoo Finance) — commercially licensed.

Runs nightly after ASX close via cron:
    0 12 * * 1-5   (12:00 UTC = 10:00 PM AEST = after ASX 4:15 PM close)

Usage:
    python scripts/update_prices_fmp.py               # All active stocks
    python scripts/update_prices_fmp.py --codes BHP   # Specific stock(s)
    python scripts/update_prices_fmp.py --days 14     # Catch up 14 days
"""

import os
import sys
import time
import logging
import argparse
from datetime import date, datetime, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)
FMP_KEY = os.getenv("FMP_API_KEY", "")

FMP_BASE    = "https://financialmodelingprep.com/api/v3"
SLEEP_SEC   = 0.2
MAX_RETRIES = 3
DAYS_BACK   = 7     # Fetch last 7 days — catches weekends and holidays

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── FMP Fetcher ───────────────────────────────────────────────────────────────

def fetch_recent_fmp(asx_code: str, days: int = DAYS_BACK) -> Optional[list]:
    """Fetch last N days of OHLCV from FMP for one ASX stock."""
    if not FMP_KEY:
        raise RuntimeError("FMP_API_KEY not set in .env")

    ticker    = f"{asx_code}.AX"
    to_date   = date.today().strftime("%Y-%m-%d")
    from_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    url       = f"{FMP_BASE}/historical-price-full/{ticker}"
    params    = {"from": from_date, "to": to_date, "apikey": FMP_KEY}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=20)

            if resp.status_code == 401:
                raise RuntimeError("FMP API key invalid")
            if resp.status_code in (404, 422):
                return None
            if resp.status_code == 429:
                log.warning("Rate limited — sleeping 60s")
                time.sleep(60)
                continue
            resp.raise_for_status()

            data = resp.json()
            if isinstance(data, dict) and "Error Message" in data:
                return None
            historical = data.get("historical", [])
            if not historical:
                return None

            rows = []
            for r in historical:
                dt_str = r.get("date")
                close  = r.get("close")
                if not dt_str or close is None:
                    continue
                try:
                    price_dt = datetime.strptime(dt_str, "%Y-%m-%d")
                except ValueError:
                    continue

                open_  = r.get("open")
                high   = r.get("high")
                low    = r.get("low")
                volume = r.get("volume")
                adj_close = r.get("adjClose") or close

                rows.append((
                    price_dt,
                    asx_code,
                    round(float(open_),     4) if open_     else None,
                    round(float(high),      4) if high      else None,
                    round(float(low),       4) if low       else None,
                    round(float(close),     4),
                    round(float(adj_close), 4),
                    int(volume)                if volume     else None,
                    "fmp",
                ))
            return rows

        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                return None

    return None


# ── DB Upsert ─────────────────────────────────────────────────────────────────

def upsert_prices(cur, rows: list) -> int:
    sql = """
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
    execute_values(cur, sql, rows, page_size=500)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FMP Nightly Price Updater")
    parser.add_argument("--codes", nargs="+", help="Specific ASX codes")
    parser.add_argument("--days",  type=int, default=DAYS_BACK,
                        help=f"Days of history to fetch (default: {DAYS_BACK})")
    args = parser.parse_args()

    if not FMP_KEY:
        log.error("FMP_API_KEY not set in .env — cannot run nightly update")
        sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("""
            SELECT asx_code FROM market.companies
            WHERE status = 'active'
            ORDER BY asx_code
        """)
        codes = [r[0] for r in cur.fetchall()]

    log.info(f"Nightly FMP price update — {len(codes)} stocks, last {args.days} days")

    updated = failed = 0
    total_rows = 0

    for i, code in enumerate(codes, 1):
        rows = fetch_recent_fmp(code, days=args.days)
        if rows:
            try:
                n = upsert_prices(cur, rows)
                total_rows += n
                updated += 1
            except psycopg2.Error as e:
                conn.rollback()
                failed += 1
                log.warning(f"  {code}: DB error — {e}")
        else:
            failed += 1

        if i % 200 == 0:
            conn.commit()
            log.info(f"  [{i}/{len(codes)}] {updated} updated, {failed} failed | {total_rows:,} rows")

        time.sleep(SLEEP_SEC)

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"Done! {updated} updated, {failed} not found. {total_rows:,} rows upserted.")


if __name__ == "__main__":
    main()
