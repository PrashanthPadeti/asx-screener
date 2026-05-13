"""
Monthly Pipeline — ASX Screener
==================================
Runs on the 1st of each month (after weekly_pipeline.py on the same day).

Steps:
  1. Compute monthly metrics       → market.monthly_metrics  (full previous month)
  2. Build screener.universe       → Golden Record

This pipeline is additive — it never downloads from EODHD.
Source data is market.daily_prices which was already loaded by daily_pipeline.py.

Note: If run on the same day as weekly_pipeline.py (1st Monday of month),
      weekly_pipeline.py already handles the monthly compute via --force-monthly
      or the is_first_monday_of_month check.  Run this script directly only
      when the 1st of month falls on a non-Monday weekday.

Schedule (cron — 1st of each month 07:30 AEST = previous-day 21:30 UTC):
  30 21 L * *  is complex — simpler: let weekly_pipeline handle it on 1st Monday.
  Alternatively:
  30 21 * * 0  cd /opt/asx-screener && \\
    asx-venv/bin/python scripts/eodhd/v2/jobs/weekly_pipeline.py --force-monthly \\
    >> logs/weekly_pipeline.log 2>&1

Usage:
    python scripts/eodhd/v2/jobs/monthly_pipeline.py
    python scripts/eodhd/v2/jobs/monthly_pipeline.py --month 2026-03-01
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[4]   # /opt/asx-screener
SCRIPTS  = BASE_DIR / "scripts" / "eodhd" / "v2"
COMPUTE  = BASE_DIR / "compute" / "engine"
PYTHON   = sys.executable


def run(label: str, cmd: list[str]) -> None:
    """Run a subprocess step; exit on failure."""
    log.info(f"▶  {label}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        log.error(f"✗  {label} failed (exit {result.returncode})")
        sys.exit(result.returncode)
    log.info(f"✓  {label} done")


def main():
    parser = argparse.ArgumentParser(description="ASX Monthly Pipeline")
    parser.add_argument(
        "--month",
        help="Compute from this date YYYY-MM-DD (default: 1st of current month)",
    )
    args = parser.parse_args()

    today      = date.today()
    from_date  = args.month or today.replace(day=1).isoformat()

    log.info(f"Monthly pipeline starting — from_date: {from_date}")

    # ── Step 1: Monthly compute ────────────────────────────────────────────────
    run("Step 1: Monthly compute → market.monthly_metrics", [
        PYTHON, str(COMPUTE / "monthly_compute.py"),
        "--from-date", from_date,
    ])

    # ── Step 2: Rebuild Golden Record ─────────────────────────────────────────
    run("Step 2: Build screener.universe", [
        PYTHON, str(SCRIPTS / "build_screener_universe.py"),
    ])

    log.info(f"Monthly pipeline complete for {today}")


if __name__ == "__main__":
    main()
