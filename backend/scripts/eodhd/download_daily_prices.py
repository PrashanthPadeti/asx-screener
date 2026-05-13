"""
EODHD Raw Zone — Download Daily Bulk Prices (Incremental)
==========================================================
Downloads all ASX stock prices for a given date in a single API call
using EODHD's bulk EOD endpoint, then saves the raw response to disk.

This replaces update_prices_eodhd.py's per-stock approach (~2,000 API
calls/day) with a single bulk call.  Much faster and cheaper on quota.

Output: data/raw/eodhd/incremental/prices/{YYYY-MM-DD}.json.gz

Usage:
    python scripts/eodhd/download_daily_prices.py              # today
    python scripts/eodhd/download_daily_prices.py --date 2026-04-25
    python scripts/eodhd/download_daily_prices.py --backfill-days 30
    python scripts/eodhd/download_daily_prices.py --force

Cron (nightly after ASX close — 10 PM AEST = 12:00 UTC):
    0 12 * * 1-5  cd /opt/asx-screener && python scripts/eodhd/download_daily_prices.py
"""

import gzip
import json
import logging
import os
import sys
import time
import argparse
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

EODHD_KEY   = os.getenv("EODHD_API_KEY", "")
EODHD_BASE  = "https://eodhd.com/api"
RAW_BASE    = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
OUT_DIR     = RAW_BASE / "eodhd" / "incremental" / "prices"
MAX_RETRIES = 3

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def fetch_bulk(target_date: str) -> list | None:
    """
    Bulk EOD endpoint: one call returns all ASX stocks for a given date.
    Each item: {code, exchange_short_name, date, open, high, low, close,
                adjusted_close, volume}
    """
    url    = f"{EODHD_BASE}/eod/bulk-download/AU"
    params = {"api_token": EODHD_KEY, "date": target_date, "fmt": "json"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=60)
            if resp.status_code == 401:
                raise RuntimeError("EODHD_API_KEY invalid")
            if resp.status_code == 429:
                log.warning("Rate limited — sleeping 60 s")
                time.sleep(60)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) and data else None
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                log.error(f"Fetch failed for {target_date}: {e}")
                return None
    return None


def save(target_date: str, data: list) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{target_date}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def trading_days_back(n: int) -> list[str]:
    """Return last N calendar days (bulk endpoint skips non-trading days itself)."""
    today  = date.today()
    return [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",          help="Specific date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill-days", type=int, default=1,
                        help="Download last N days (default: 1 = today only)")
    parser.add_argument("--force",         action="store_true",
                        help="Re-download even if file exists")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env"); sys.exit(1)

    if args.date:
        dates = [args.date]
    else:
        dates = trading_days_back(args.backfill_days)

    done = skipped = failed = 0

    for target_date in dates:
        path = OUT_DIR / f"{target_date}.json.gz"

        if path.exists() and not args.force:
            log.info(f"  {target_date}: already exists — skip (use --force to re-download)")
            skipped += 1
            continue

        log.info(f"  Downloading bulk prices for {target_date} ...")
        data = fetch_bulk(target_date)

        if data:
            saved_path = save(target_date, data)
            log.info(f"  {target_date}: {len(data):,} rows → {saved_path}")
            done += 1
        else:
            log.warning(f"  {target_date}: no data (weekend/holiday?)")
            failed += 1

    log.info(f"DONE — {done} downloaded, {skipped} skipped, {failed} no data")
    if done:
        log.info("Next step: python scripts/eodhd/load_prices.py")


if __name__ == "__main__":
    main()
