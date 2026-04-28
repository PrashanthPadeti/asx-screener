"""
Incremental Daily Download Job — Run Every Trading Day
=======================================================
Downloads today's EOD bulk prices from EODHD to the Raw Zone.
Does NOT load to database — just files on disk.

What it does:
  - Prices (bulk):  GET /eod/bulk-download/AU?date=TODAY
                    → eod_prices/incremental/{DATE}.json.gz

What it does NOT do:
  - Does NOT load to staging tables
  - Does NOT run transforms
  - Does NOT update screener.universe

Run this daily AFTER ASX close (~16:30 AEST).
Weekends / public holidays: EODHD returns empty or 400 — script handles gracefully.

Schedule (cron — runs at 18:00 AEST = 08:00 UTC):
  0 8 * * 1-5  cd /opt/asx-screener && \
    python scripts/eodhd/v2/jobs/incremental_daily.py >> logs/incremental_daily.log 2>&1

Usage:
    python scripts/eodhd/v2/jobs/incremental_daily.py
    python scripts/eodhd/v2/jobs/incremental_daily.py --date 2026-04-28
    python scripts/eodhd/v2/jobs/incremental_daily.py --backfill-days 5
"""

import logging
import os
import sys
import argparse
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

JOBS_DIR = Path(__file__).resolve().parent
V2_DIR   = JOBS_DIR.parent
PRICE_SCRIPT = V2_DIR / "download_eod_prices.py"


def run(cmd: list[str]) -> bool:
    log.info(f"  {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Daily incremental price download — Raw Zone only, no DB writes.")
    parser.add_argument("--date",          help="Specific date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill-days", type=int,
                        help="Download last N days (for catching up after outage)")
    parser.add_argument("--force-recheck", action="store_true",
                        help="Re-download even if file already exists")
    args = parser.parse_args()

    if args.backfill_days:
        today  = date.today()
        dates  = [(today - timedelta(days=i)).strftime("%Y-%m-%d")
                  for i in range(args.backfill_days)]
    elif args.date:
        dates = [args.date]
    else:
        dates = [date.today().strftime("%Y-%m-%d")]

    log.info(f"=== INCREMENTAL DAILY DOWNLOAD: {', '.join(dates)} ===")
    t0 = time.time()
    all_ok = True

    for target_date in dates:
        log.info(f"  Downloading prices for {target_date} …")
        cmd = [sys.executable, str(PRICE_SCRIPT),
               "--mode", "incremental",
               "--date", target_date]
        if args.force_recheck:
            cmd.append("--force-recheck")

        ok = run(cmd)
        if not ok:
            # Non-trading day (weekend/holiday): EODHD returns empty
            # The price script logs a warning but exits 0 — a real failure would be exit 1
            log.warning(f"  {target_date}: download returned non-zero (non-trading day?)")
            all_ok = False

    elapsed = time.time() - t0
    log.info(f"=== Done in {elapsed:.1f}s ===")
    log.info(f"Files saved to: $RAW_DATA_DIR/eodhd/exchange=AU/eod_prices/incremental/")
    log.info("")
    log.info("To load prices into the database when ready:")
    log.info("  python scripts/eodhd/v2/load_to_staging_prices.py "
             f"--mode incremental --date {dates[0]}")

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
