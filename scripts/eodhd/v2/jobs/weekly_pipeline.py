"""
Weekly Pipeline — ASX Screener
================================
Runs every Monday morning before ASX opens (~07:00 AEST).

Steps:
  1. Load staging from raw fundamentals  → all staging tables (from Sunday's download)
  2. Transform valuation snapshot        → market.valuation_snapshot
  3. Transform analyst ratings           → market.analyst_ratings
  4. Compute yearly metrics              → market.yearly_metrics
  5. Compute half-yearly metrics         → market.halfyearly_metrics
  6. Compute weekly metrics              → market.weekly_metrics (incremental, last week)
  7. Compute monthly metrics             → market.monthly_metrics (1st Mon of month only)
  8. Build screener.universe             → Golden Record

weekly_refresh.py (Sunday 22:00 AEST) downloads raw files to disk first.
This pipeline loads + computes from those files Monday morning.

Schedule (cron — Monday 07:00 AEST = Sunday 21:00 UTC):
  0 21 * * 0  cd /opt/asx-screener && \\
    asx-venv/bin/python scripts/eodhd/v2/jobs/weekly_pipeline.py \\
    >> logs/weekly_pipeline.log 2>&1

Usage:
    python scripts/eodhd/v2/jobs/weekly_pipeline.py
    python scripts/eodhd/v2/jobs/weekly_pipeline.py --from-date 2026-04-21
    python scripts/eodhd/v2/jobs/weekly_pipeline.py --skip-monthly
    python scripts/eodhd/v2/jobs/weekly_pipeline.py --force-monthly
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
ASIC     = BASE_DIR / "scripts" / "asic"
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


def is_first_monday_of_month(today: date) -> bool:
    """True if today is the first Monday of its calendar month."""
    return today.weekday() == 0 and today.day <= 7


def main():
    parser = argparse.ArgumentParser(description="ASX Weekly Pipeline")
    parser.add_argument(
        "--from-date",
        help="Compute weeks/months from this date (default: last Monday)",
    )
    parser.add_argument(
        "--skip-monthly",
        action="store_true",
        help="Skip monthly compute step regardless of date",
    )
    parser.add_argument(
        "--force-monthly",
        action="store_true",
        help="Force monthly compute even if not first Monday of month",
    )
    args = parser.parse_args()

    today      = date.today()
    # Default from-date: last Monday (start of the just-completed week)
    days_since_monday = today.weekday()   # Monday=0
    last_monday = today.replace(day=today.day - days_since_monday) if days_since_monday > 0 else today
    from_date   = args.from_date or last_monday.isoformat()

    log.info(f"Weekly pipeline starting — from_date: {from_date}")

    # ── Step 0: ASIC short interest — download + load ─────────────────────────
    # Downloads the most recent ASIC aggregate short position CSV (free, public).
    # Published with ~2–3 business-day lag; idempotent if already cached.
    run("Step 0a: ASIC download short positions", [
        PYTHON, str(ASIC / "download_short_positions.py"),
    ])
    run("Step 0b: ASIC load → market.short_interest", [
        PYTHON, str(ASIC / "load_short_positions.py"),
    ])

    # ── Step 1: Load staging from raw fundamentals ────────────────────────────
    # Parses Sunday's downloaded JSON files → staging tables (highlights,
    # valuation, income, balance_sheet, cashflow, analyst_ratings, shares_stats)
    run("Step 1: Load staging fundamentals", [
        PYTHON, str(SCRIPTS / "load_to_staging_fundamentals.py"),
    ])

    # ── Step 2: Transform valuation snapshot ──────────────────────────────────
    run("Step 2: Transform → market.valuation_snapshot", [
        PYTHON, str(SCRIPTS / "transforms" / "transform_valuation.py"),
    ])

    # ── Step 3: Transform analyst ratings ─────────────────────────────────────
    run("Step 3: Transform → market.analyst_ratings", [
        PYTHON, str(SCRIPTS / "transforms" / "transform_analyst_ratings.py"),
    ])

    # ── Step 4: Yearly compute ────────────────────────────────────────────────
    run("Step 4: Yearly compute → market.yearly_metrics", [
        PYTHON, str(COMPUTE / "yearly_compute.py"),
    ])

    # ── Step 5: Half-yearly compute ───────────────────────────────────────────
    run("Step 5: Half-yearly compute → market.halfyearly_metrics", [
        PYTHON, str(COMPUTE / "halfyearly_compute.py"),
    ])

    # ── Step 6: Weekly compute ────────────────────────────────────────────────
    run("Step 6: Weekly compute → market.weekly_metrics", [
        PYTHON, str(COMPUTE / "weekly_compute.py"),
        "--from-date", from_date,
    ])

    # ── Step 7: Monthly compute (only on 1st Monday of month, unless forced) ──
    run_monthly = (
        args.force_monthly or
        (not args.skip_monthly and is_first_monday_of_month(today))
    )

    if run_monthly:
        month_start = today.replace(day=1).isoformat()
        run("Step 7: Monthly compute → market.monthly_metrics", [
            PYTHON, str(COMPUTE / "monthly_compute.py"),
            "--from-date", month_start,
        ])
    else:
        log.info("Step 7: Monthly compute skipped "
                 "(not first Monday of month — use --force-monthly to override)")

    # ── Step 8: Rebuild Golden Record ─────────────────────────────────────────
    run("Step 8: Build screener.universe", [
        PYTHON, str(SCRIPTS / "build_screener_universe.py"),
    ])

    log.info(f"Weekly pipeline complete for {today}")


if __name__ == "__main__":
    main()
