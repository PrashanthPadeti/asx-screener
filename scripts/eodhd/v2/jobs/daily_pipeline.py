"""
Daily Pipeline — ASX Screener
==============================
Runs after ASX market close each weekday (~18:30 AEST).

Steps:
  1. Download today's bulk EOD prices       → Raw Zone (.json.gz)
  2. Load prices to staging.eod_prices      → DELETE today + INSERT
  3. Transform to market.daily_prices       → upsert --from-date TODAY
  4. Run compute engine                     → market.computed_metrics
  5. Build screener.universe                → Golden Record

Usage:
    python scripts/eodhd/v2/jobs/daily_pipeline.py
    python scripts/eodhd/v2/jobs/daily_pipeline.py --date 2026-04-29
    python scripts/eodhd/v2/jobs/daily_pipeline.py --skip-download
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",          help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip step 1 (raw download) — use existing file")
    args = parser.parse_args()

    target_date = args.date or date.today().isoformat()
    log.info(f"Daily pipeline starting — target date: {target_date}")

    # ── Step 1: Download bulk EOD prices ──────────────────────────────────────
    if not args.skip_download:
        run("Step 1: Download bulk EOD prices", [
            PYTHON, str(SCRIPTS / "download_eod_bulk.py"),
            "--date", target_date,
        ])
    else:
        log.info("Step 1: Skipped (--skip-download)")

    # ── Step 2: Load staging.eod_prices ───────────────────────────────────────
    run("Step 2: Load staging.eod_prices", [
        PYTHON, str(SCRIPTS / "load_to_staging_eod_prices.py"),
        "--date", target_date,
    ])

    # ── Step 3: Transform to market.daily_prices ──────────────────────────────
    run("Step 3: Transform market.daily_prices", [
        PYTHON, str(SCRIPTS / "transforms" / "transform_prices.py"),
        "--from-date", target_date,
    ])

    # ── Step 4: Compute engine ────────────────────────────────────────────────
    run("Step 4: Compute engine → market.computed_metrics", [
        PYTHON, str(COMPUTE / "daily_compute.py"),
    ])

    # ── Step 5: Build screener.universe ───────────────────────────────────────
    run("Step 5: Build screener.universe", [
        PYTHON, str(SCRIPTS / "build_screener_universe.py"),
    ])

    log.info(f"Daily pipeline complete for {target_date}")


if __name__ == "__main__":
    main()
