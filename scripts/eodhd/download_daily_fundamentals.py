"""
EODHD Raw Zone — Download Daily Fundamentals Refresh (Incremental)
===================================================================
Downloads updated fundamentals for stocks whose financial data may have
changed (e.g. after earnings announcements).

Strategy: re-download fundamentals for stocks where the most recent
annual_pnl row has a period_end_date within the last N months.  This
catches companies that just reported results.

Alternatively, use --codes to refresh specific stocks, or --all to
refresh every stock (good for a quarterly bulk refresh).

Output: data/raw/eodhd/incremental/fundamentals/{YYYY-MM-DD}/{CODE}.json.gz

Usage:
    python scripts/eodhd/download_daily_fundamentals.py          # recent reporters
    python scripts/eodhd/download_daily_fundamentals.py --all    # all stocks
    python scripts/eodhd/download_daily_fundamentals.py --codes BHP CBA
    python scripts/eodhd/download_daily_fundamentals.py --months 3

Cron (weekly refresh of recent reporters):
    0 14 * * 6  cd /opt/asx-screener && python scripts/eodhd/download_daily_fundamentals.py
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

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DB_URL      = os.getenv("DATABASE_URL_SYNC",
                "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
EODHD_KEY   = os.getenv("EODHD_API_KEY", "")
EODHD_BASE  = "https://eodhd.com/api"
RAW_BASE    = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
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
            if resp.status_code in (404, 422):
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
                return None
    return None


def save(run_date: str, asx_code: str, data: dict) -> Path:
    out_dir = RAW_BASE / "eodhd" / "incremental" / "fundamentals" / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{asx_code}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, default=str)
    return path


def get_recent_reporters(cur, months: int) -> list[str]:
    """Stocks whose latest annual report period ended within the last N months."""
    cutoff = date.today() - timedelta(days=months * 30)
    cur.execute("""
        SELECT DISTINCT p.asx_code
        FROM financials.annual_pnl p
        JOIN market.companies c ON c.asx_code = p.asx_code
        WHERE c.status = 'active'
          AND p.period_end_date >= %s
          AND p.period_end_date = (
              SELECT MAX(p2.period_end_date)
              FROM financials.annual_pnl p2
              WHERE p2.asx_code = p.asx_code
          )
        ORDER BY p.asx_code
    """, (cutoff,))
    return [r[0] for r in cur.fetchall()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",  nargs="+", help="Specific ASX codes")
    parser.add_argument("--all",    action="store_true", help="Refresh all active stocks")
    parser.add_argument("--months", type=int, default=4,
                        help="Recent reporters: stocks with results in last N months (default: 4)")
    parser.add_argument("--force",  action="store_true")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env"); sys.exit(1)

    run_date = date.today().strftime("%Y-%m-%d")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if args.codes:
        codes = [c.upper() for c in args.codes]
    elif args.all:
        cur.execute("SELECT asx_code FROM market.companies WHERE status='active' ORDER BY asx_code")
        codes = [r[0] for r in cur.fetchall()]
    else:
        codes = get_recent_reporters(cur, args.months)

    cur.close(); conn.close()

    total = len(codes)
    done  = skipped = failed = 0

    log.info(f"Downloading fundamentals refresh for {total} stocks → incremental/{run_date}/")

    for i, code in enumerate(codes, 1):
        out_dir = RAW_BASE / "eodhd" / "incremental" / "fundamentals" / run_date
        path    = out_dir / f"{code}.json.gz"

        if path.exists() and not args.force:
            skipped += 1
            continue

        data = fetch(code)
        time.sleep(SLEEP_SEC)

        if data:
            save(run_date, code, data)
            done += 1
        else:
            failed += 1

        if i % 50 == 0:
            log.info(f"  [{i:4d}/{total}] {done} done, {skipped} skipped, {failed} failed")

    log.info(f"DONE — {done} downloaded, {skipped} skipped, {failed} no data")
    if done:
        log.info(f"Next step: python scripts/eodhd/load_fundamentals.py --date {run_date}")


if __name__ == "__main__":
    main()
