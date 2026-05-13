"""
Historical Download Job — Run Once
====================================
Downloads all historical data from EODHD to the Raw Zone.
Does NOT touch the database beyond reading the stock code list.

Sequence (runs each script in order, waits for completion):
  1. Exchange symbol list    — 1 API call,  ~3 sec
  2. Fundamentals            — ~2,000 calls, ~10 min  (SLEEP 0.3s/stock)
  3. EOD Prices (historical) — ~2,000 calls, ~5  min  (SLEEP 0.15s/stock)
  4. Dividends               — ~2,000 calls, ~7  min  (SLEEP 0.2s/stock)
  5. Splits                  — ~2,000 calls, ~7  min  (SLEEP 0.2s/stock)

Total estimated time: ~30 minutes for full ASX universe.

All scripts skip already-downloaded files, so this is resumable:
  python jobs/historical_download.py --from-code WBC    # resume from W
  python jobs/historical_download.py --codes BHP CBA    # specific stocks

Outputs go to:
  {RAW_DATA_DIR}/eodhd/exchange=AU/
    ├── exchange_symbols/{DATE}.json.gz
    ├── fundamentals/full_snapshot/{CODE}.AU_{DATE}.json.gz
    ├── eod_prices/historical/{CODE}.AU_{DATE}.json.gz
    ├── dividends/historical/{CODE}.AU_{DATE}.json.gz
    └── splits/historical/{CODE}.AU_{DATE}.json.gz

Usage:
    cd /path/to/project
    nohup python scripts/eodhd/v2/jobs/historical_download.py \
        > logs/historical_download.log 2>&1 &

    # Resume from a specific code (if job was interrupted)
    python scripts/eodhd/v2/jobs/historical_download.py --from-code WBC

    # Specific stocks only
    python scripts/eodhd/v2/jobs/historical_download.py --codes BHP CBA ANZ

    # Skip exchange symbols step (already downloaded today)
    python scripts/eodhd/v2/jobs/historical_download.py --skip-exchange-symbols

    # Dry run (show what would run, no downloads)
    python scripts/eodhd/v2/jobs/historical_download.py --dry-run
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

# Resolve script directory relative to this file
JOBS_DIR   = Path(__file__).resolve().parent
V2_DIR     = JOBS_DIR.parent

SCRIPTS = {
    "exchange_symbols": V2_DIR / "download_exchange_symbols.py",
    "fundamentals":     V2_DIR / "download_fundamentals.py",
    "prices":           V2_DIR / "download_eod_prices.py",
    "dividends":        V2_DIR / "download_dividends.py",
    "splits":           V2_DIR / "download_splits.py",
}

ESTIMATES = {
    "exchange_symbols": "~3 sec",
    "fundamentals":     "~10 min",
    "prices":           "~5 min",
    "dividends":        "~7 min",
    "splits":           "~7 min",
}


def run(name: str, script: Path, extra_args: list[str], dry_run: bool) -> bool:
    cmd = [sys.executable, str(script)] + extra_args
    log.info(f"─── {name.upper()} ({ESTIMATES[name]}) ───")
    log.info(f"    {' '.join(cmd)}")
    if dry_run:
        log.info("    [DRY RUN — skipped]")
        return True
    t0 = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - t0
    ok = result.returncode == 0
    status = "✓ done" if ok else f"✗ FAILED (exit {result.returncode})"
    log.info(f"    {status} in {elapsed/60:.1f} min")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="One-time historical download of all EODHD data to Raw Zone.")
    parser.add_argument("--codes",                 nargs="+",
                        help="Limit to specific ASX codes")
    parser.add_argument("--from-code",
                        help="Resume fundamentals/prices/dividends/splits from this code")
    parser.add_argument("--skip-exchange-symbols", action="store_true",
                        help="Skip exchange symbol list download")
    parser.add_argument("--skip-fundamentals",     action="store_true")
    parser.add_argument("--skip-prices",           action="store_true")
    parser.add_argument("--skip-dividends",        action="store_true")
    parser.add_argument("--skip-splits",           action="store_true")
    parser.add_argument("--force-recheck",         action="store_true",
                        help="Re-download even if today's file already exists")
    parser.add_argument("--dry-run",               action="store_true",
                        help="Show commands without executing")
    args = parser.parse_args()

    # Build shared args for per-stock scripts
    per_stock_args = []
    if args.codes:
        per_stock_args += ["--codes"] + args.codes
    elif args.from_code:
        per_stock_args += ["--from-code", args.from_code]
    if args.force_recheck:
        per_stock_args.append("--force-recheck")

    t_total = time.time()
    results = {}

    log.info("=" * 60)
    log.info("HISTORICAL DOWNLOAD JOB")
    log.info("=" * 60)

    # 1. Exchange symbol list
    if not args.skip_exchange_symbols:
        extra = ["--force-recheck"] if args.force_recheck else []
        results["exchange_symbols"] = run(
            "exchange_symbols", SCRIPTS["exchange_symbols"], extra, args.dry_run)
    else:
        log.info("─── EXCHANGE_SYMBOLS — skipped")

    # 2. Fundamentals
    if not args.skip_fundamentals:
        results["fundamentals"] = run(
            "fundamentals", SCRIPTS["fundamentals"], per_stock_args, args.dry_run)
    else:
        log.info("─── FUNDAMENTALS — skipped")

    # 3. Prices (historical mode)
    if not args.skip_prices:
        price_args = ["--mode", "historical"] + per_stock_args
        results["prices"] = run(
            "prices", SCRIPTS["prices"], price_args, args.dry_run)
    else:
        log.info("─── PRICES — skipped")

    # 4. Dividends
    if not args.skip_dividends:
        results["dividends"] = run(
            "dividends", SCRIPTS["dividends"], per_stock_args, args.dry_run)
    else:
        log.info("─── DIVIDENDS — skipped")

    # 5. Splits
    if not args.skip_splits:
        results["splits"] = run(
            "splits", SCRIPTS["splits"], per_stock_args, args.dry_run)
    else:
        log.info("─── SPLITS — skipped")

    elapsed = (time.time() - t_total) / 60
    ok_count   = sum(1 for v in results.values() if v)
    fail_count = sum(1 for v in results.values() if not v)

    log.info("=" * 60)
    log.info(f"HISTORICAL DOWNLOAD COMPLETE — {elapsed:.1f} min")
    log.info(f"  Stages ok: {ok_count}  |  Failed: {fail_count}")
    if fail_count:
        for k, v in results.items():
            if not v:
                log.error(f"  FAILED: {k}")
        log.info("Tip: re-run with --from-code to resume or --skip-* to skip completed stages")
        sys.exit(1)
    else:
        log.info("")
        log.info("Next steps:")
        log.info("  Load to staging:  python scripts/eodhd/v2/pipeline_runner.py --stage staging")
        log.info("  Full pipeline:    python scripts/eodhd/v2/pipeline_runner.py")


if __name__ == "__main__":
    main()
