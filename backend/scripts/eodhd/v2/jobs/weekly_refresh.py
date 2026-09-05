"""
Weekly Refresh Download Job
============================
Re-downloads dividends, splits and the exchange symbol list for all stocks,
and fundamentals for one quarter of the universe. Checksum deduplication skips
files whose content hasn't changed — so running this weekly adds a new file
only when EODHD data actually changed.

Fundamentals are sharded four ways because EODHD bills them at 10 calls per
symbol: a full refresh is ~21,000 calls against the 30,000 allocated to this
screener, which left nothing for the dividends and splits jobs behind it. One
shard is ~5,250, and each company is still refreshed roughly monthly.
Use --full-fundamentals for a deliberate complete rebuild.

Run once per week (Sunday night or Monday morning before trading opens).

Schedule (cron — Sunday 22:00 AEST = 12:00 UTC):
  0 12 * * 0  cd /opt/asx-screener && \
    python scripts/eodhd/v2/jobs/weekly_refresh.py >> logs/weekly_refresh.log 2>&1

Does NOT load to database — just raw zone files.

Usage:
    python scripts/eodhd/v2/jobs/weekly_refresh.py
    python scripts/eodhd/v2/jobs/weekly_refresh.py --from-code WBC
    python scripts/eodhd/v2/jobs/weekly_refresh.py --codes BHP CBA
"""

import logging
import os
import sys
import argparse
import subprocess
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

JOBS_DIR = Path(__file__).resolve().parent
V2_DIR   = JOBS_DIR.parent

SCRIPTS = {
    "exchange_symbols": V2_DIR / "download_exchange_symbols.py",
    "fundamentals":     V2_DIR / "download_fundamentals.py",
    "dividends":        V2_DIR / "download_dividends.py",
    "splits":           V2_DIR / "download_splits.py",
}

ESTIMATES = {
    "exchange_symbols": "~3 sec",
    "fundamentals":     "~3 min (weekly shard)",
    "dividends":        "~7 min",
    "splits":           "~7 min",
}


def run(name: str, script: Path, extra_args: list[str]) -> bool:
    cmd = [sys.executable, str(script)] + extra_args
    log.info(f"─── {name.upper()} ({ESTIMATES[name]}) ───")
    t0 = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - t0
    ok = result.returncode == 0
    log.info(f"    {'✓' if ok else '✗'} {elapsed/60:.1f} min")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Weekly fundamentals/dividends/splits refresh — Raw Zone only.")
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-code")
    parser.add_argument("--skip-exchange-symbols", action="store_true")
    parser.add_argument("--skip-fundamentals",     action="store_true")
    parser.add_argument("--skip-dividends",        action="store_true")
    parser.add_argument("--skip-splits",           action="store_true")
    parser.add_argument("--full-fundamentals", action="store_true",
                        help="Refresh every stock instead of this week's shard. "
                             "Costs ~21,000 EODHD calls, so the budget guard may "
                             "defer it — use only for a deliberate full rebuild.")
    args = parser.parse_args()

    per_stock = []
    if args.codes:
        per_stock += ["--codes"] + args.codes
    elif args.from_code:
        per_stock += ["--from-code", args.from_code]

    t_total = time.time()
    results = {}

    log.info("=" * 60)
    log.info("WEEKLY REFRESH DOWNLOAD")
    log.info("=" * 60)

    if not args.skip_exchange_symbols:
        results["exchange_symbols"] = run(
            "exchange_symbols", SCRIPTS["exchange_symbols"], [])

    if not args.skip_fundamentals:
        # A quarter of the universe each Sunday. Every company still gets
        # refreshed roughly monthly, but the ~21,000-call spike that pushed
        # dividends and splits into the reserve is spread over four weeks.
        fundamentals_args = list(per_stock)
        if not args.codes and not args.full_fundamentals:
            fundamentals_args.append("--shard-this-week")
        results["fundamentals"] = run(
            "fundamentals", SCRIPTS["fundamentals"], fundamentals_args)

    if not args.skip_dividends:
        results["dividends"] = run(
            "dividends", SCRIPTS["dividends"], per_stock)

    if not args.skip_splits:
        results["splits"] = run(
            "splits", SCRIPTS["splits"], per_stock)

    elapsed = (time.time() - t_total) / 60
    fail_count = sum(1 for v in results.values() if not v)

    log.info("=" * 60)
    log.info(f"WEEKLY REFRESH COMPLETE — {elapsed:.1f} min | {fail_count} failures")
    if fail_count:
        for k, v in results.items():
            if not v:
                log.error(f"  FAILED: {k}")
        sys.exit(1)


if __name__ == "__main__":
    main()
