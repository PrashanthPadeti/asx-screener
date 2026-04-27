"""
EODHD Raw Zone — Download Historical Prices
============================================
Step 1: API → disk.  Run load_prices.py to push data into the DB.

Downloads full daily OHLCV price history (from 2000) for every active
ASX stock and saves each response as a gzipped JSON file.

Output: data/raw/eodhd/historical/prices/{CODE}.json.gz

Usage:
    python scripts/eodhd/download_historical_prices.py
    python scripts/eodhd/download_historical_prices.py --from-code WBC
    python scripts/eodhd/download_historical_prices.py --codes BHP CBA
    python scripts/eodhd/download_historical_prices.py --from 2015-01-01
    python scripts/eodhd/download_historical_prices.py --force
    nohup python scripts/eodhd/download_historical_prices.py > logs/dl_prices.log 2>&1 &

Expected runtime: ~1–2 hours for 1,978 stocks.
"""

import gzip
import json
import logging
import os
import sys
import time
import argparse
from datetime import date
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DB_URL        = os.getenv("DATABASE_URL_SYNC",
                    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
EODHD_KEY     = os.getenv("EODHD_API_KEY", "")
EODHD_BASE    = "https://eodhd.com/api"
RAW_BASE      = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
OUT_DIR       = RAW_BASE / "eodhd" / "historical" / "prices"

DEFAULT_FROM  = "2000-01-01"
SLEEP_SEC     = 0.2
MAX_RETRIES   = 3

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def fetch(asx_code: str, from_date: str, to_date: str) -> list | None:
    ticker = f"{asx_code}.AU"
    url    = f"{EODHD_BASE}/eod/{ticker}"
    params = {
        "api_token": EODHD_KEY,
        "fmt":       "json",
        "from":      from_date,
        "to":        to_date,
        "period":    "d",
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 401:
                raise RuntimeError("EODHD_API_KEY invalid")
            if resp.status_code in (404, 422):
                return None
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
                log.debug(f"  {asx_code}: fetch failed — {e}")
                return None
    return None


def save(asx_code: str, data: list) -> Path:
    path = OUT_DIR / f"{asx_code}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--limit",     type=int)
    parser.add_argument("--from",      dest="from_date", default=DEFAULT_FROM)
    parser.add_argument("--to",        dest="to_date",
                        default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--from-code", help="Resume from this code")
    parser.add_argument("--force",     action="store_true")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env"); sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("SELECT asx_code FROM market.companies WHERE status='active' ORDER BY asx_code")
        codes = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()

    if args.from_code:
        codes = [c for c in codes if c >= args.from_code.upper()]
    if args.limit:
        codes = codes[:args.limit]

    total   = len(codes)
    done    = skipped = failed = 0

    log.info(f"Downloading prices for {total} stocks ({args.from_date} → {args.to_date})")
    log.info(f"Output: {OUT_DIR}")

    for i, code in enumerate(codes, 1):
        path = OUT_DIR / f"{code}.json.gz"

        if path.exists() and not args.force:
            skipped += 1
            continue

        data = fetch(code, args.from_date, args.to_date)
        time.sleep(SLEEP_SEC)

        if data:
            save(code, data)
            done += 1
        else:
            failed += 1

        if i % 100 == 0:
            log.info(f"  [{i:4d}/{total}] {done} downloaded, {skipped} skipped, {failed} failed")

    log.info(f"DONE — {done} downloaded, {skipped} skipped, {failed} no data")
    log.info("Next step: python scripts/eodhd/load_prices.py")


if __name__ == "__main__":
    main()
