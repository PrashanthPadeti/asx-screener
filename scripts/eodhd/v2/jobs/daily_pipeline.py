"""
Daily Pipeline — ASX Screener
==============================
Runs after ASX market close each weekday (08:30 UTC = 18:30 AEST).

Steps:
  1.  Download today's EOD prices (per-stock, from yesterday) → Raw Zone
  2.  Download ASIC short positions                           → Raw Zone
  3.  Load prices → staging_au.eod_prices                    (today's files, UPSERT)
  4.  Load short positions → staging_au.short_positions
  5.  Transform prices → market.daily_prices                  (from yesterday)
  6.  Transform short positions → market.short_positions
  7.  Daily compute engine → market.computed_metrics
  8.  Technical compute engine → market.daily_metrics
  9.  Half-yearly compute engine → market.halfyearly_metrics
  10. Period metrics compute engine → market.period_metrics
  11. ASX index prices → market.index_prices                  (Yahoo Finance)
  12. ETF & fund prices → market.fund_prices                  (Yahoo Finance)
  13. Build screener.universe → Golden Record
  14. Market snapshots → index/sector/mover/exdiv snapshots

Usage:
    python scripts/eodhd/v2/jobs/daily_pipeline.py
    python scripts/eodhd/v2/jobs/daily_pipeline.py --skip-download

Crontab (08:30 UTC Mon-Fri — ~2.5 hours after ASX close):
    30 8 * * 1-5 cd /opt/asx-screener && /opt/asx-screener/asx-venv/bin/python scripts/eodhd/v2/jobs/daily_pipeline.py >> /opt/asx-screener/logs/daily_pipeline.log 2>&1
"""

import argparse
import logging
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_DIR  = Path(__file__).resolve().parents[4]   # /opt/asx-screener
SCRIPTS   = BASE_DIR / "scripts" / "eodhd" / "v2"
ASIC      = BASE_DIR / "scripts" / "asic"
COMPUTE   = BASE_DIR / "compute" / "engine"
PYTHON    = sys.executable
TODAY     = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def run(label: str, cmd: list[str]) -> None:
    log.info(f"▶  {label}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=BASE_DIR)
    elapsed = time.time() - t0
    if result.returncode != 0:
        log.error(f"✗  {label} failed (exit {result.returncode}) after {elapsed:.1f}s")
        sys.exit(result.returncode)
    log.info(f"✓  {label} done in {elapsed:.1f}s")


def run_optional(label: str, cmd: list[str]) -> None:
    """Run a step that is allowed to fail without stopping the pipeline."""
    log.info(f"▶  {label}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=BASE_DIR)
    elapsed = time.time() - t0
    if result.returncode != 0:
        log.warning(f"⚠  {label} failed (exit {result.returncode}) after {elapsed:.1f}s — continuing")
    else:
        log.info(f"✓  {label} done in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip steps 1-2 (raw downloads) — use existing files")
    args = parser.parse_args()

    DIVIDER = "─" * 60
    log.info(DIVIDER)
    log.info(f"ASX Screener — Daily Pipeline — {TODAY}")
    log.info(DIVIDER)
    t_start = time.time()

    # ── Step 1: Download EOD prices (per-stock from yesterday) ───────────────
    # Uses historical per-stock endpoint — bulk endpoint not available on this tier.
    # --from-date yesterday covers Mon (gets Fri+Mon) and all weekdays correctly.
    if not args.skip_download:
        run("Step 1: Download EOD prices", [
            PYTHON, str(SCRIPTS / "download_eod_prices.py"),
            "--mode", "historical",
            "--from-date", YESTERDAY,
        ])
    else:
        log.info("Step 1: Skipped (--skip-download)")

    # ── Step 2: Download ASIC short positions (non-fatal — page is JS-rendered) ─
    # ASIC publishes with ~2-3 business day lag; idempotent if already cached.
    # Step is optional: a scraping failure must not block prices/compute/universe.
    if not args.skip_download:
        run_optional("Step 2: Download ASIC short positions", [
            PYTHON, str(ASIC / "download_short_positions.py"),
        ])
    else:
        log.info("Step 2: Skipped (--skip-download)")

    # ── Step 3: Load today's price files → staging_au (UPSERT, no truncate) ──
    run("Step 3: Load prices → staging_au", [
        PYTHON, str(SCRIPTS / "load_to_staging_prices.py"),
        "--mode", "historical",
        "--run-date", TODAY,
    ])

    # ── Step 4: Load + transform short positions (non-fatal) ─────────────────
    run_optional("Step 4: Load short positions → staging_au", [
        PYTHON, str(ASIC / "load_to_staging_short.py"),
    ])

    # ── Step 5: Transform prices → market.daily_prices ───────────────────────
    run("Step 5: Transform prices → market.daily_prices", [
        PYTHON, str(SCRIPTS / "transforms" / "transform_prices.py"),
        "--from-date", YESTERDAY,
    ])

    # ── Step 6: Transform short positions (non-fatal) ────────────────────────
    run_optional("Step 6: Transform short positions → market.short_positions", [
        PYTHON, str(ASIC / "transforms" / "transform_short.py"),
    ])

    # ── Step 7: Daily compute engine ──────────────────────────────────────────
    run("Step 7: Daily compute → market.computed_metrics", [
        PYTHON, str(COMPUTE / "daily_compute.py"),
    ])

    # ── Step 8: Technical compute engine ──────────────────────────────────────
    run("Step 8: Technical compute → market.daily_metrics", [
        PYTHON, str(COMPUTE / "technical_compute.py"),
    ])

    # ── Step 9: Half-yearly compute ───────────────────────────────────────────
    run("Step 9: Half-yearly compute → market.halfyearly_metrics", [
        PYTHON, str(COMPUTE / "halfyearly_compute.py"),
    ])

    # ── Step 10: Period metrics ────────────────────────────────────────────────
    run("Step 10: Period metrics → market.period_metrics", [
        PYTHON, str(COMPUTE / "period_metrics_compute.py"),
    ])

    # ── Step 11: ASX index prices (Yahoo Finance) ─────────────────────────────
    run("Step 11: ASX index prices → market.index_prices", [
        PYTHON, str(COMPUTE / "index_prices.py"),
        "--days", "2",
    ])

    # ── Step 12: ETF & fund prices (Yahoo Finance) ────────────────────────────
    run("Step 12: ETF & fund prices → market.fund_prices", [
        PYTHON, str(COMPUTE / "fund_prices.py"),
        "--days", "2",
    ])

    # ── Step 13: Build screener.universe ──────────────────────────────────────
    run("Step 13: Build screener.universe", [
        PYTHON, str(SCRIPTS / "build_screener_universe.py"),
    ])

    # ── Step 14: Market snapshots (runs after universe rebuild) ───────────────
    run("Step 14: Market snapshots → index/sector/mover/exdiv", [
        PYTHON, str(COMPUTE / "market_snapshot.py"),
    ])

    elapsed = time.time() - t_start
    log.info(DIVIDER)
    log.info(f"Daily pipeline complete in {elapsed / 60:.1f} min")
    log.info(DIVIDER)


if __name__ == "__main__":
    main()
