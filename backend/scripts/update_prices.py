"""
ASX Screener — Daily Price Updater
====================================
Fetches yesterday's prices for all active stocks.
Runs nightly after ASX close (via cron at 8pm AEST = 10am UTC).

Much faster than the full historical load — only fetches 5 days
of data per stock (catches weekends/holidays) then upserts.

Usage:
    python scripts/update_prices.py              # All active stocks
    python scripts/update_prices.py --codes BHP  # Specific stock
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values
import requests
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)

SLEEP_BETWEEN = 0.2   # polite delay between Yahoo requests
MAX_RETRIES   = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def fetch_recent(asx_code: str, days: int = 7):
    """Fetch last N days of prices from Yahoo Finance."""
    ticker = f"{asx_code}.AX"
    end   = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={int(start.timestamp())}&period2={int(end.timestamp())}"
        f"&interval=1d&events=history"
    )
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ASXScreener/1.0)"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code in (404, 422):
                return None
            if resp.status_code == 429:
                time.sleep(30)
                continue
            resp.raise_for_status()

            data   = resp.json()
            result = data.get("chart", {}).get("result")
            if not result:
                return None

            r          = result[0]
            timestamps = r.get("timestamp", [])
            if not timestamps:
                return None

            quotes   = r["indicators"]["quote"][0]
            adjclose = r["indicators"].get("adjclose", [{}])[0].get("adjclose", [])

            rows = []
            for i, ts in enumerate(timestamps):
                close = quotes.get("close", [])[i] if i < len(quotes.get("close", [])) else None
                if close is None:
                    continue
                rows.append((
                    datetime.fromtimestamp(ts, tz=timezone.utc),
                    asx_code,
                    round(quotes.get("open",   [])[i], 4) if quotes.get("open",   [])[i] else None,
                    round(quotes.get("high",   [])[i], 4) if quotes.get("high",   [])[i] else None,
                    round(quotes.get("low",    [])[i], 4) if quotes.get("low",    [])[i] else None,
                    round(close, 4),
                    round(adjclose[i], 4) if adjclose and i < len(adjclose) and adjclose[i] else round(close, 4),
                    int(quotes.get("volume", [])[i]) if quotes.get("volume", [])[i] else None,
                    "yahoo",
                ))
            return rows

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                return None
    return None


def upsert_prices(cur, rows):
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
            volume         = EXCLUDED.volume
    """
    execute_values(cur, sql, rows, page_size=500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+", help="Specific ASX codes")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("SELECT asx_code FROM market.companies WHERE status = 'active' ORDER BY asx_code")
        codes = [r[0] for r in cur.fetchall()]

    log.info(f"Updating prices for {len(codes)} stocks...")
    updated = 0
    failed  = 0

    for i, code in enumerate(codes, 1):
        rows = fetch_recent(code, days=7)
        if rows:
            upsert_prices(cur, rows)
            updated += 1
            if i % 100 == 0:
                conn.commit()
                log.info(f"  [{i}/{len(codes)}] {updated} updated, {failed} failed")
        else:
            failed += 1
        time.sleep(SLEEP_BETWEEN)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"Done! {updated} updated, {failed} not found. Total: {len(codes)}")


if __name__ == "__main__":
    main()
