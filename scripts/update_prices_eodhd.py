"""
ASX Screener — EODHD Nightly Price Updater
==========================================
Fetches last 7 days of prices for all active ASX stocks.
Runs nightly after ASX close via cron:
    0 12 * * 1-5   (12:00 UTC = 10:00 PM AEST)

Usage:
    python scripts/update_prices_eodhd.py              # All active stocks
    python scripts/update_prices_eodhd.py --codes BHP  # Specific stocks
    python scripts/update_prices_eodhd.py --days 14    # Catch up after holiday
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

SLEEP_SEC   = 0.2
MAX_RETRIES = 3
DAYS_BACK   = 7

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def fetch_recent(asx_code: str, days: int) -> Optional[list]:
    ticker    = f"{asx_code}.AU"
    to_date   = date.today().strftime("%Y-%m-%d")
    from_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    url       = f"{EODHD_BASE}/eod/{ticker}"
    params    = {"api_token": EODHD_KEY, "fmt": "json",
                 "from": from_date, "to": to_date, "period": "d"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=20)
            if resp.status_code == 401:
                raise RuntimeError("EODHD API key invalid")
            if resp.status_code in (404, 422):
                return None
            if resp.status_code == 429:
                time.sleep(60); continue
            resp.raise_for_status()
            data = resp.json()
            if not data or data == "NA":
                return None

            rows = []
            for r in data:
                dt_str = r.get("date")
                close  = r.get("close")
                if not dt_str or close is None:
                    continue
                try:
                    price_dt = datetime.strptime(dt_str, "%Y-%m-%d")
                except ValueError:
                    continue
                rows.append((
                    price_dt, asx_code,
                    round(float(r["open"]),          4) if r.get("open")           else None,
                    round(float(r["high"]),          4) if r.get("high")           else None,
                    round(float(r["low"]),           4) if r.get("low")            else None,
                    round(float(r["close"]),         4),
                    round(float(r["adjusted_close"]),4) if r.get("adjusted_close") else round(float(close), 4),
                    int(r["volume"])                    if r.get("volume")          else None,
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
            open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
            close=EXCLUDED.close, adjusted_close=EXCLUDED.adjusted_close,
            volume=EXCLUDED.volume, data_source=EXCLUDED.data_source
    """
    execute_values(cur, sql, rows, page_size=500)
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    parser.add_argument("--days", type=int, default=DAYS_BACK)
    args = parser.parse_args()

    if not EODHD_KEY:
        log.error("EODHD_API_KEY not set"); sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("SELECT asx_code FROM market.companies WHERE status='active' ORDER BY asx_code")
        codes = [r[0] for r in cur.fetchall()]

    log.info(f"Nightly EODHD update — {len(codes)} stocks, last {args.days} days")

    updated = failed = 0
    total_rows = 0

    for i, code in enumerate(codes, 1):
        rows = fetch_recent(code, args.days)
        if rows:
            try:
                total_rows += upsert_prices(cur, rows)
                updated += 1
            except psycopg2.Error as e:
                conn.rollback(); failed += 1
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
    log.info(f"Done! {updated} updated, {failed} failed. {total_rows:,} rows upserted.")


if __name__ == "__main__":
    main()
