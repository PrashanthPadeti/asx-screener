"""
Weekly Pipeline — ASX Screener
================================
Runs every Monday morning before ASX opens (~07:00 AEST).

Steps:
  1. Load staging from raw fundamentals  → all staging tables (from Sunday's download)
  2. Transform valuation snapshot        → market.valuation_snapshot
  3. Transform analyst ratings           → market.analyst_ratings
  3b. Dividends: load → transform → ASSERT FEED HEALTHY
      The three steps whose absence let market.dividends age four months
      while the raw downloads kept arriving. The assertion fails the job,
      so a committed transform over a stale feed is not a success.
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
from datetime import date, timedelta
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

# Shared alert utility — path: backend/scripts/utils/alert.py
sys.path.insert(0, str(BASE_DIR / "scripts"))
from utils.alert import send_failure_alert  # noqa: E402

_from_date = "unknown"  # set in main() so run() can reference it for alerts


def run(label: str, cmd: list[str]) -> None:
    """Run a subprocess step; send failure alert and exit on non-zero return code."""
    log.info(f"▶  {label}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        log.error(f"✗  {label} failed (exit {result.returncode})")
        send_failure_alert(
            pipeline="weekly",
            step=label,
            target_date=_from_date,
            exit_code=result.returncode,
        )
        sys.exit(result.returncode)
    log.info(f"✓  {label} done")


def run_optional(label: str, cmd: list[str]) -> None:
    """Run a step whose failure must not stop the pipeline.

    ASIC short positions are supplementary market data. They write none of the
    72 governed columns, and daily_pipeline already treats the same transform
    as non-fatal -- so the project had already decided they are ancillary. The
    weekly pipeline had not: steps 0a-0c ran through run(), which exits, and a
    flaky ASIC CSV therefore blocked the entire fundamentals refresh behind it.

    Four of the eight Sundays to 20 Sep 2026 died at Step 0b with "No rows
    loaded -- check CSV format". Only one of those eight completed. The value,
    quality and growth factors are computed from yearly_metrics, which sits
    downstream of this gate, so a short-interest CSV nobody was watching had
    been holding the screener's fundamentals at 30 August.

    The alert still fires; only the exit is removed.
    """
    log.info(f"▶  {label}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        log.warning(f"⚠  {label} failed (exit {result.returncode}) — continuing; "
                    f"this step is supplementary and does not gate fundamentals")
        send_failure_alert(
            pipeline="weekly",
            step=f"{label} (optional — pipeline continued)",
            target_date=_from_date,
            exit_code=result.returncode,
        )
        return
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
    # timedelta, not replace(day=...).
    #
    # replace() cannot cross a month boundary, so `day=today.day - N` raises
    # ValueError whenever last Monday fell in the previous month. This crashed
    # the weekly pipeline on 11 of 2026's 52 Sundays -- roughly one a month --
    # and worked perfectly the other three, which is why it went unnoticed
    # from at least June. The 6 Sep 2026 run died here (day=6, weekday=6,
    # replace(day=0)) and market.yearly_metrics has read 30 Aug ever since.
    last_monday = today - timedelta(days=days_since_monday)
    from_date   = args.from_date or last_monday.isoformat()

    global _from_date
    _from_date = from_date
    log.info(f"Weekly pipeline starting — from_date: {from_date}")

    # ── Step 0: ASIC short interest — download → staging → transform ──────────
    # Downloads the most recent ASIC aggregate short position CSV (free, public).
    # Published with ~2–3 business-day lag; idempotent if already cached.
    run_optional("Step 0a: ASIC download short positions", [
        PYTHON, str(ASIC / "download_short_positions.py"),
    ])
    run_optional("Step 0b: ASIC load → staging_au.short_positions", [
        PYTHON, str(ASIC / "load_to_staging_short.py"),
    ])
    run_optional("Step 0c: ASIC transform → market.short_positions (+ back-fill short_interest)", [
        PYTHON, str(ASIC / "transforms" / "transform_short.py"),
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

    # ── Step 3b: Dividends — load → transform → assert healthy ────────────────
    #
    # These three were missing, and their absence was the outage.
    #
    # weekly_refresh.py downloads dividend JSON every Sunday and always has:
    # the raw acquisition never stopped. Nothing loaded those files into
    # staging, and nothing transformed staging into market.dividends. So the
    # raw zone stayed current while the table the engine reads aged from May to
    # September 2026 — four months — and every dividend metric on the site
    # decayed with it, silently, because no job was failing. A pipeline cannot
    # report a step it does not have.
    #
    # Repaired by hand in September 2026: 19,063 -> 29,804 rows, 750 -> 1,235
    # issuers. 485 issuers had no dividend history at all. That repair is not
    # durable until it is scheduled, which is what these steps are.
    #
    # The assertion is the point, not the load. `run()` exits on any non-zero
    # step, so a committed transform followed by an unhealthy feed fails the
    # weekly job — which is the distinction that was missing throughout:
    # a producer's transaction committing is not successful output.
    run("Step 3b-i: Load dividends → staging_au.dividends", [
        PYTHON, str(SCRIPTS / "load_to_staging_dividends.py"),
    ])
    run("Step 3b-ii: Transform → market.dividends", [
        PYTHON, str(SCRIPTS / "transforms" / "transform_dividends.py"),
    ])
    # No --warn-only. The classifier is the same one the factor engine uses to
    # decide whether to withhold Income, so "healthy" means here exactly what
    # it means there. A second operational definition would drift from the
    # financial one and neither would be wrong by its own lights.
    run("Step 3b-iii: Assert dividend feed healthy", [
        PYTHON, str(BASE_DIR / "scripts" / "assert_feed_health.py"),
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

    # ── Step 9: Post-universe enrichment ──────────────────────────────────────
    # Runs after the golden record is fully rebuilt.
    run("Step 9a: Composite factor scores → screener.universe", [
        PYTHON, str(COMPUTE / "composite_score.py"),
    ])
    run("Step 9b: Pros/Cons signals → screener.universe", [
        PYTHON, str(COMPUTE / "pros_cons.py"),
    ])
    run("Step 9c: Sector benchmarks → market.sector_benchmarks", [
        PYTHON, str(COMPUTE / "sector_benchmarks.py"),
    ])

    log.info(f"Weekly pipeline complete for {today}")


if __name__ == "__main__":
    main()
