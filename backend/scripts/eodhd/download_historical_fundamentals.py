"""
EODHD Raw Zone — Download Historical Fundamentals
==================================================
Step 1: API → disk.  Run load_fundamentals.py to push data into the DB.

Downloads full fundamentals JSON for every active ASX stock and saves
each response as a gzipped file.  The blob contains everything EODHD
provides: annual + quarterly IS/BS/CF, dividends, splits, analyst
ratings, earnings estimates, share stats, and more.

Output: data/raw/eodhd/historical/fundamentals/{CODE}.json.gz

Usage:
    python scripts/eodhd/download_historical_fundamentals.py
    python scripts/eodhd/download_historical_fundamentals.py --from-code WBC
    python scripts/eodhd/download_historical_fundamentals.py --codes BHP CBA
    python scripts/eodhd/download_historical_fundamentals.py --force     # re-download existing
    nohup python scripts/eodhd/download_historical_fundamentals.py > logs/dl_fundamentals.log 2>&1 &

Expected runtime: ~3–5 hours for 1,978 stocks at 0.3 s/call.
EODHD ALL-IN-ONE plan: 100,000 API calls/day — well within limits.
"""

import gzip
import json
import logging
import os
import sys
import time
import argparse
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DB_URL     = os.getenv("DATABASE_URL_SYNC",
                "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
EODHD_KEY  = os.getenv("EODHD_API_KEY", "")
EODHD_BASE = "https://eodhd.com/api"
RAW_BASE   = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
OUT_DIR    = RAW_BASE / "eodhd" / "historical" / "fundamentals"

SLEEP_SEC   = 0.3
MAX_RETRIES = 3

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def fetch(asx_code: str) -> dict | None:
    ticker = f"{asx_code}.AU"
    url    = f"{EODHD_BASE}/fundamentals/{ticker}"
    params = {"api_token": EODHD_KEY, "fmt": "json"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 401:
                raise RuntimeError("EODHD_API_KEY invalid")
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                log.warning("Rate limited — sleeping 60 s")
                time.sleep(60)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else None
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                log.debug(f"  {asx_code}: fetch failed — {e}")
                return None
    return None


def save(asx_code: str, data: dict) -> Path:
    path = OUT_DIR / f"{asx_code}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, default=str)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+", help="Specific ASX codes")
    parser.add_argument("--limit",     type=int)
    parser.add_argument("--from-code", help="Resume from this code (alphabetical)")
    parser.add_argument("--force",     action="store_true",
                        help="Re-download even if file already exists")
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

    log.info(f"Downloading fundamentals for {total} stocks → {OUT_DIR}")
    log.info(f"Est. time: ~{total * SLEEP_SEC / 60:.0f} min")

    for i, code in enumerate(codes, 1):
        path = OUT_DIR / f"{code}.json.gz"

        if path.exists() and not args.force:
            skipped += 1
            if i % 200 == 0:
                log.info(f"  [{i:4d}/{total}] {done} downloaded, {skipped} skipped, {failed} failed")
            continue

        data = fetch(code)
        time.sleep(SLEEP_SEC)

        if data:
            save(code, data)
            done += 1
        else:
            failed += 1
            log.debug(f"  {code}: no data")

        if i % 100 == 0:
            log.info(f"  [{i:4d}/{total}] {done} downloaded, {skipped} skipped, {failed} failed")

    log.info(f"DONE — {done} downloaded, {skipped} skipped (already exist), {failed} no data")
    log.info(f"Files in: {OUT_DIR}")
    log.info("Next step: python scripts/eodhd/load_fundamentals.py")


if __name__ == "__main__":
    main()
