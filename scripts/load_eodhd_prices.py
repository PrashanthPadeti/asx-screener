"""
ASX Screener — EODHD Historical Price Loader
=============================================
One-time bulk load of 30+ years of daily OHLCV for all ASX stocks.
Replaces load_prices.py (Yahoo Finance) with officially licensed EODHD data.

Usage:
    python scripts/load_eodhd_prices.py                    # All stocks
    python scripts/load_eodhd_prices.py --codes BHP CBA    # Specific stocks
    python scripts/load_eodhd_prices.py --from 2020-01-01  # Custom start date
    python scripts/load_eodhd_prices.py --from-code WBC    # Resume from code
    nohup python scripts/load_eodhd_prices.py > logs/eodhd_prices.log 2>&1 &
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

DB_URL     = os.getenv("DATABASE_URL_SYNC",
                "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
EODHD_KEY  = os.getenv("EODHD_API_KEY", "")
EODHD_BASE = "https://eodhd.com/api"

SLEEP_SEC    = 0.2
MAX_RETRIES  = 3
BATCH_COMMIT = 100
DEFAULT_FROM = "2000-01-01"   # EODHD has 30+ years — load from 2000

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def fetch_prices(asx_code: str, from_date: str, to_date: str) -> Optional[list]:
    """Fetch daily OHLCV from EODHD for one ASX stock."""
    ticker = f"{asx_code}.AU"
    url    = f"{EODHD_BASE}/eod/{ticker}"
    params = {
        "api_token": EODHD_KEY,
        "fmt":       "json",
        "from":      from_date,
        "to":        to_date,
        "period":    "d",          # daily
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 401:
                raise RuntimeError("EODHD API key invalid")
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                log.warning("Rate limited — sleeping 60s")
                time.sleep(60)
                continue
            resp.raise_for_status()

            data = resp.json()
            if not data or data == "NA":
                return None

            rows = []
            for r in data:
                dt_str = r.get("date")
                close  = r.get("close") or r.get("adjusted_close")
                if not dt_str or close is None:
                    continue
                try:
                    price_dt = datetime.strptime(dt_str, "%Y-%m-%d")
                except ValueError:
                    continue

                rows.append((
                    price_dt,
                    asx_code,
                    round(float(r["open"]),          4) if r.get("open")          else None,
                    round(float(r["high"]),          4) if r.get("high")          else None,
                    round(float(r["low"]),           4) if r.get("low")           else None,
                    round(float(r["close"]),         4) if r.get("close")         else None,
                    round(float(r["adjusted_close"]),4) if r.get("adjusted_close") else round(float(close), 4),
                    int(r["volume"])                    if r.get("volume")         else None,
                    "eodhd",
                ))
            return rows

        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                return None

    return None


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
    execute_values(cur, sql, rows, page_size=1000)
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--limit",     type=int)
    parser.add_argument("--from",      dest="from_date", default=DEFAULT_FROM)
    parser.add_argument("--to",        dest="to_date",
                        default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--from-code", help="Resume from ASX code")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env"); sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("SELECT asx_code FROM market.companies WHERE status='active' ORDER BY asx_code")
        codes = [r[0] for r in cur.fetchall()]

    if args.from_code:
        codes = [c for c in codes if c >= args.from_code.upper()]
        log.info(f"Resuming from {args.from_code.upper()} — {len(codes)} remaining")

    if args.limit:
        codes = codes[:args.limit]

    total      = len(codes)
    loaded     = failed = 0
    total_rows = 0

    log.info(f"Loading prices for {total} stocks ({args.from_date} → {args.to_date})")

    for i, code in enumerate(codes, 1):
        rows = fetch_prices(code, args.from_date, args.to_date)
        if rows:
            try:
                total_rows += upsert_prices(cur, rows)
                loaded += 1
            except psycopg2.Error as e:
                conn.rollback()
                failed += 1
                log.warning(f"  {code}: DB error — {e}")
        else:
            failed += 1

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(f"[{i:4d}/{total}] {loaded} loaded, {failed} failed | {total_rows:,} rows")

        time.sleep(SLEEP_SEC)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE! {loaded} stocks, {total_rows:,} rows. Failed: {failed}")


if __name__ == "__main__":
    main()
