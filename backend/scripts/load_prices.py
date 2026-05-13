"""
ASX Screener — Load Historical Daily Prices
=============================================
Fetches 2 years of daily OHLCV data from Yahoo Finance for all ASX stocks
and inserts into market.daily_prices (TimescaleDB hypertable).

Usage:
    python scripts/load_prices.py                    # All stocks
    python scripts/load_prices.py --codes BHP CBA    # Specific stocks
    python scripts/load_prices.py --limit 50         # First 50 stocks only

Yahoo Finance ASX codes: append .AX suffix (e.g. BHP.AX, CBA.AX)
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)

YEARS_HISTORY = 2
BATCH_SIZE    = 50    # stocks per batch before committing
SLEEP_BETWEEN = 0.3  # seconds between Yahoo requests (be polite)
MAX_RETRIES   = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Yahoo Finance Fetch ───────────────────────────────────────

def fetch_yahoo(asx_code: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV from Yahoo Finance.
    Returns DataFrame with columns: time, open, high, low, close, adj_close, volume
    or None if the stock is not found / delisted.
    """
    ticker = f"{asx_code}.AX"
    start_ts = int(start.timestamp())
    end_ts   = int(end.timestamp())

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d&events=history"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ASXScreener/1.0)",
        "Accept": "application/json",
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 404:
                return None   # Stock not found on Yahoo
            if resp.status_code == 429:
                log.warning(f"  Rate limited — sleeping 30s")
                time.sleep(30)
                continue
            resp.raise_for_status()

            data = resp.json()
            result = data.get("chart", {}).get("result")
            if not result:
                return None

            r = result[0]
            timestamps = r.get("timestamp", [])
            if not timestamps:
                return None

            quotes = r["indicators"]["quote"][0]
            adjclose = r["indicators"].get("adjclose", [{}])[0].get("adjclose", [])

            df = pd.DataFrame({
                "time":          [datetime.fromtimestamp(ts, tz=timezone.utc) for ts in timestamps],
                "open":          quotes.get("open", []),
                "high":          quotes.get("high", []),
                "low":           quotes.get("low", []),
                "close":         quotes.get("close", []),
                "adjusted_close": adjclose if adjclose else quotes.get("close", []),
                "volume":        quotes.get("volume", []),
            })

            # Drop rows where close is None (trading halts, data gaps)
            df = df.dropna(subset=["close"])
            df["asx_code"] = asx_code

            return df if not df.empty else None

        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                log.warning(f"  Failed {asx_code}: {e}")
                return None

    return None


# ── Database Insert ───────────────────────────────────────────

def upsert_prices(cur, df: pd.DataFrame) -> int:
    """Upsert price rows into market.daily_prices. Returns rows inserted."""
    rows = [
        (
            row.time,
            row.asx_code,
            round(row.open, 4)          if pd.notna(row.open)          else None,
            round(row.high, 4)          if pd.notna(row.high)          else None,
            round(row.low, 4)           if pd.notna(row.low)           else None,
            round(row.close, 4)         if pd.notna(row.close)         else None,
            round(row.adjusted_close, 4) if pd.notna(row.adjusted_close) else None,
            int(row.volume)             if pd.notna(row.volume)        else None,
            "yahoo",
        )
        for row in df.itertuples()
    ]

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


# ── Main ──────────────────────────────────────────────────────

def get_asx_codes(conn, limit: Optional[int] = None) -> list[str]:
    """Fetch active ASX codes from DB, ordered by market importance."""
    cur = conn.cursor()
    sql = """
        SELECT asx_code FROM market.companies
        WHERE status = 'active'
        ORDER BY
            is_asx200 DESC,
            is_asx300 DESC,
            asx_code ASC
    """
    if limit:
        sql += f" LIMIT {limit}"
    cur.execute(sql)
    codes = [r[0] for r in cur.fetchall()]
    cur.close()
    return codes


def main():
    parser = argparse.ArgumentParser(description="Load ASX historical prices from Yahoo Finance")
    parser.add_argument("--codes", nargs="+", help="Specific ASX codes to load")
    parser.add_argument("--limit", type=int, help="Max number of stocks to load")
    parser.add_argument("--years", type=int, default=YEARS_HISTORY, help="Years of history")
    args = parser.parse_args()

    end   = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=365 * args.years)

    log.info(f"Connecting to database...")
    conn = psycopg2.connect(DB_URL)

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        codes = get_asx_codes(conn, limit=args.limit)

    log.info(f"Loading {len(codes)} stocks | {args.years} years | {start.date()} → {end.date()}")
    log.info("─" * 60)

    cur = conn.cursor()
    total_rows = 0
    found = 0
    not_found = []

    for i, asx_code in enumerate(codes, 1):
        df = fetch_yahoo(asx_code, start, end)

        if df is None or df.empty:
            not_found.append(asx_code)
            log.info(f"  [{i:4d}/{len(codes)}] {asx_code:<8} — not found on Yahoo")
        else:
            rows = upsert_prices(cur, df)
            total_rows += rows
            found += 1
            log.info(f"  [{i:4d}/{len(codes)}] {asx_code:<8} — {rows:4d} days inserted")

        # Commit every BATCH_SIZE stocks
        if i % BATCH_SIZE == 0:
            conn.commit()
            log.info(f"  ── committed batch {i // BATCH_SIZE} ──")

        time.sleep(SLEEP_BETWEEN)

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {found} stocks loaded | {total_rows:,} price rows inserted")
    if not_found:
        log.info(f"Not found on Yahoo ({len(not_found)}): {', '.join(not_found[:20])}")
        if len(not_found) > 20:
            log.info(f"  ... and {len(not_found) - 20} more")


if __name__ == "__main__":
    main()
