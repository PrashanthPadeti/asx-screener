"""
Daily Pipeline — ASX Screener
==============================
Runs after ASX market close each weekday (~18:30 AEST).

Steps:
  1. Download today's bulk EOD prices       → Raw Zone (.json.gz)
  2. Load prices to staging.eod_prices      → DELETE today + INSERT
  3. Transform to market.daily_prices       → upsert --from-date TODAY
  4. Run daily compute engine               → market.computed_metrics
  4b. Run technical compute engine          → market.daily_metrics (latest date)
  4c. Run half-yearly compute engine        → market.halfyearly_metrics
  4d. Run period metrics compute engine     → market.period_metrics (H/L/AvgVol all periods)
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

# Shared alert utility — path: backend/scripts/utils/alert.py
sys.path.insert(0, str(BASE_DIR / "scripts"))
from utils.alert import send_failure_alert  # noqa: E402

_target_date = "unknown"  # set in main() so run() can reference it for alerts


def run(label: str, cmd: list[str]) -> None:
    """Run a subprocess step; send failure alert and exit on non-zero return code."""
    log.info(f"▶  {label}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        log.error(f"✗  {label} failed (exit {result.returncode})")
        send_failure_alert(
            pipeline="daily",
            step=label,
            target_date=_target_date,
            exit_code=result.returncode,
        )
        sys.exit(result.returncode)
    log.info(f"✓  {label} done")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",          help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip step 1 (raw download) — use existing file")
    args = parser.parse_args()

    global _target_date
    target_date = args.date or date.today().isoformat()
    _target_date = target_date
    log.info(f"Daily pipeline starting — target date: {target_date}")

    # ── Step 1: Download bulk EOD prices ──────────────────────────────────────
    if not args.skip_download:
        run("Step 1: Download bulk EOD prices", [
            PYTHON, str(SCRIPTS / "download_eod_prices.py"),
            "--mode", "incremental",
            "--date", target_date,
        ])
    else:
        log.info("Step 1: Skipped (--skip-download)")

    # ── Step 2: Load staging prices ───────────────────────────────────────────
    run("Step 2: Load staging prices", [
        PYTHON, str(SCRIPTS / "load_to_staging_prices.py"),
        "--mode", "incremental",
        "--date", target_date,
    ])

    # ── Step 3: Transform to market.daily_prices ──────────────────────────────
    run("Step 3: Transform market.daily_prices", [
        PYTHON, str(SCRIPTS / "transforms" / "transform_prices.py"),
        "--from-date", target_date,
    ])

    # ── Step 4: Daily compute engine ──────────────────────────────────────────
    run("Step 4: Daily compute engine → market.computed_metrics", [
        PYTHON, str(COMPUTE / "daily_compute.py"),
    ])

    # ── Step 4b: Technical compute engine ─────────────────────────────────────
    # Writes latest-date indicators to market.daily_metrics for all stocks.
    # Fetches full OHLCV history per stock for warm-up accuracy; writes only
    # the latest row (~2-3 min for all stocks).
    run("Step 4b: Technical compute engine → market.daily_metrics", [
        PYTHON, str(COMPUTE / "technical_compute.py"),
    ])

    # ── Step 4c: Half-yearly compute engine ───────────────────────────────────
    # Aggregates quarterly → half-yearly, computes margins + HoH/YoY growth.
    # Fast (~30s) — runs weekly on Sunday but also daily to catch new quarters.
    run("Step 4c: Half-yearly compute engine → market.halfyearly_metrics", [
        PYTHON, str(COMPUTE / "halfyearly_compute.py"),
    ])

    # ── Step 4d: Period metrics compute engine ────────────────────────────────
    # Upserts H/L/AvgVol for 1D/1W/1M/3M/6M/1Y/52W into market.period_metrics.
    # Used by the Market Signals API for accurate period-aware highs/lows.
    run("Step 4d: Period metrics compute engine → market.period_metrics", [
        PYTHON, str(COMPUTE / "period_metrics_compute.py"),
    ])

    # ── Step 5: Build screener.universe ───────────────────────────────────────
    run("Step 5: Build screener.universe", [
        PYTHON, str(SCRIPTS / "build_screener_universe.py"),
    ])

    log.info(f"Daily pipeline complete for {target_date}")


if __name__ == "__main__":
    main()
