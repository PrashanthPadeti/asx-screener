"""
ASIC Short Position Report — Downloader
=========================================
Downloads the daily aggregate short position CSV from ASIC and saves it
to the raw data zone as a gzipped CSV.

ASIC publishes reports with a ~2–3 business-day lag after each trading day.
This script tries dates backwards from today (or a given date) to find
the most recently available file.

URL pattern:
    https://asic.gov.au/Reports/Daily/{YYYY}/{MM}/RR{YYYYMMDD}-001-SSDailyAggShortPos.csv

Output:
    {RAW_DATA_DIR}/asic/short_positions/{YYYYMMDD}.csv.gz

Usage:
    python scripts/asic/download_short_positions.py
    python scripts/asic/download_short_positions.py --date 2026-04-29
    python scripts/asic/download_short_positions.py --lookback 15
    python scripts/asic/download_short_positions.py --force          # re-download even if cached
"""

import argparse
import gzip
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
OUT_DIR  = RAW_BASE / "asic" / "short_positions"

ASIC_URL = (
    "https://asic.gov.au/Reports/Daily/{yyyy}/{mm}/"
    "RR{yyyymmdd}-001-SSDailyAggShortPos.csv"
)

# How many calendar days to look back when searching for the latest available file
DEFAULT_LOOKBACK = 14
SLEEP_BETWEEN_TRIES = 1.0   # seconds — be polite to ASIC servers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def prev_business_days(start: date, n: int) -> list[date]:
    """Return the last n business days (Mon–Fri) at or before `start`, newest first."""
    days = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:  # Monday=0 … Friday=4
            days.append(d)
        d -= timedelta(days=1)
    return days


def build_url(d: date) -> str:
    return ASIC_URL.format(
        yyyy=d.strftime("%Y"),
        mm=d.strftime("%m"),
        yyyymmdd=d.strftime("%Y%m%d"),
    )


def local_path(d: date) -> Path:
    return OUT_DIR / f"{d.strftime('%Y%m%d')}.csv.gz"


def download_date(d: date, force: bool = False) -> bool:
    """
    Try to download the ASIC short position report for date `d`.
    Returns True if successful, False if 404/unavailable.
    """
    dest = local_path(d)
    if dest.exists() and not force:
        log.info(f"  Already cached: {dest.name}")
        return True

    url = build_url(d)
    log.info(f"  Trying {d.isoformat()} → {url}")

    try:
        resp = requests.get(url, timeout=30)
    except requests.RequestException as e:
        log.warning(f"  Request error: {e}")
        return False

    if resp.status_code == 404:
        log.debug(f"  404 — not yet available for {d.isoformat()}")
        return False

    if resp.status_code != 200:
        log.warning(f"  HTTP {resp.status_code} for {d.isoformat()}")
        return False

    # Sanity-check: the file should be a CSV with the expected header
    content = resp.content
    try:
        first_line = content[:500].decode("utf-8", errors="replace").splitlines()[0]
    except Exception:
        first_line = ""

    if "Product" not in first_line and "Short Position" not in first_line:
        log.warning(f"  Unexpected content (not a short positions CSV): {first_line[:80]}")
        return False

    # Write gzipped to disk
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dest, "wb") as f:
        f.write(content)

    size_kb = len(content) / 1024
    log.info(f"  ✓ Downloaded {d.isoformat()} ({size_kb:.1f} KB) → {dest}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Download ASIC Short Position Reports")
    parser.add_argument(
        "--date",
        help="Target date YYYY-MM-DD (default: search backwards from today)",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK,
        help=f"How many business days to look back (default: {DEFAULT_LOOKBACK})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if already cached locally",
    )
    args = parser.parse_args()

    if args.date:
        # Specific date requested — try just that one date
        target = date.fromisoformat(args.date)
        log.info(f"ASIC downloader — targeting {target.isoformat()}")
        success = download_date(target, force=args.force)
        if success:
            log.info("Done.")
        else:
            log.error(f"Could not download report for {target.isoformat()}")
            raise SystemExit(1)
    else:
        # Search backwards for the most recent available file
        start    = date.today()
        to_check = prev_business_days(start, args.lookback)
        log.info(f"ASIC downloader — searching {args.lookback} business days back from {start.isoformat()}")

        found = False
        for d in to_check:
            dest = local_path(d)
            if dest.exists() and not args.force:
                log.info(f"  Most recent cached: {d.isoformat()} ({dest})")
                found = True
                break

            success = download_date(d, force=args.force)
            if success:
                found = True
                break

            time.sleep(SLEEP_BETWEEN_TRIES)

        if not found:
            log.error(f"No ASIC short position file found in last {args.lookback} business days")
            raise SystemExit(1)

    log.info("ASIC download complete.")


if __name__ == "__main__":
    main()
