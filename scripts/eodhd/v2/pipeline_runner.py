"""
Pipeline Runner — Full EODHD Pipeline
======================================
Orchestrates the end-to-end pipeline:

  Stage 1: Load staging (staging.* tables from Raw Zone files)
  Stage 2: Transform (staging.* → market.* / financials.*)
  Stage 3: Build Golden Record (screener.universe)

Each stage can be run independently via --stage. Default: run all three.

Usage:
    # Full pipeline
    python scripts/eodhd/v2/pipeline_runner.py

    # Specific stocks only
    python scripts/eodhd/v2/pipeline_runner.py --codes BHP CBA ANZ

    # Single stage
    python scripts/eodhd/v2/pipeline_runner.py --stage staging
    python scripts/eodhd/v2/pipeline_runner.py --stage transform
    python scripts/eodhd/v2/pipeline_runner.py --stage golden-record

    # Skip golden record (just stage + transform)
    python scripts/eodhd/v2/pipeline_runner.py --skip-golden-record
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

SCRIPTS_DIR = Path(__file__).parent
V2_DIR      = SCRIPTS_DIR

STAGING_SCRIPTS = [
    ("fundamentals",    V2_DIR / "load_to_staging_fundamentals.py"),
    ("prices",          V2_DIR / "load_to_staging_prices.py"),
    ("dividends",       V2_DIR / "load_to_staging_dividends.py"),
]

TRANSFORM_SCRIPTS = [
    ("exchange",        V2_DIR / "transforms" / "transform_exchange.py"),
    ("companies",       V2_DIR / "transforms" / "transform_companies.py"),
    ("prices",          V2_DIR / "transforms" / "transform_prices.py"),
    ("financials",      V2_DIR / "transforms" / "transform_financials.py"),
    ("valuation",       V2_DIR / "transforms" / "transform_valuation.py"),
    ("analyst_ratings", V2_DIR / "transforms" / "transform_analyst_ratings.py"),
    ("earnings",        V2_DIR / "transforms" / "transform_earnings.py"),
    ("dividends",       V2_DIR / "transforms" / "transform_dividends.py"),
    ("splits",          V2_DIR / "transforms" / "transform_splits.py"),
]

GOLDEN_RECORD_SCRIPT = V2_DIR / "build_screener_universe.py"


def run_script(name: str, script: Path, extra_args: list[str]) -> bool:
    cmd = [sys.executable, str(script)] + extra_args
    log.info(f"  → {name}: {' '.join(cmd[-len(extra_args)-1:])}")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - t0
    if result.returncode != 0:
        log.error(f"  ✗ {name} FAILED (exit {result.returncode}) after {elapsed:.1f}s")
        return False
    log.info(f"  ✓ {name} done in {elapsed:.1f}s")
    return True


def build_staging_args(script_name: str, codes: list[str] | None) -> list[str]:
    """Build CLI args for staging scripts based on the script type."""
    args = []
    if codes:
        args += ["--codes"] + codes
    if "prices" in script_name and not codes:
        args += ["--mode", "historical"]
    elif "prices" in script_name and codes:
        args = ["--mode", "historical", "--codes"] + codes
    return args


def run_staging(codes: list[str] | None) -> bool:
    log.info("=== STAGE 1: Loading staging tables ===")
    all_ok = True
    for name, script in STAGING_SCRIPTS:
        if not script.exists():
            log.warning(f"  Skipping {name} — script not found: {script}")
            continue
        extra = build_staging_args(name, codes)
        ok = run_script(name, script, extra)
        if not ok:
            all_ok = False
    return all_ok


def run_transforms(codes: list[str] | None) -> bool:
    log.info("=== STAGE 2: Running transforms ===")
    all_ok = True
    for name, script in TRANSFORM_SCRIPTS:
        if not script.exists():
            log.warning(f"  Skipping {name} — script not found: {script}")
            continue
        extra = (["--codes"] + codes) if codes else []
        ok = run_script(name, script, extra)
        if not ok:
            all_ok = False
    return all_ok


def run_golden_record(codes: list[str] | None) -> bool:
    log.info("=== STAGE 3: Building Golden Record (screener.universe) ===")
    if not GOLDEN_RECORD_SCRIPT.exists():
        log.warning(f"  Skipping — script not found: {GOLDEN_RECORD_SCRIPT}")
        return True
    extra = (["--codes"] + codes) if codes else []
    return run_script("screener_universe", GOLDEN_RECORD_SCRIPT, extra)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",              nargs="+",
                        help="Limit pipeline to specific ASX codes")
    parser.add_argument("--stage",              choices=["staging", "transform", "golden-record"],
                        help="Run only one stage")
    parser.add_argument("--skip-golden-record", action="store_true",
                        help="Skip golden record build")
    parser.add_argument("--skip-staging",       action="store_true",
                        help="Skip staging load (run transforms + golden record only)")
    args = parser.parse_args()

    codes = [c.upper() for c in args.codes] if args.codes else None

    t_start = time.time()
    results = {}

    if args.stage == "staging":
        results["staging"] = run_staging(codes)
    elif args.stage == "transform":
        results["transform"] = run_transforms(codes)
    elif args.stage == "golden-record":
        results["golden-record"] = run_golden_record(codes)
    else:
        # Full pipeline
        if not args.skip_staging:
            results["staging"] = run_staging(codes)
        results["transform"] = run_transforms(codes)
        if not args.skip_golden_record:
            results["golden-record"] = run_golden_record(codes)

    elapsed = time.time() - t_start
    ok_count = sum(1 for v in results.values() if v)
    fail_count = len(results) - ok_count

    log.info(f"=== Pipeline complete in {elapsed:.1f}s — "
             f"{ok_count} stages ok, {fail_count} failed ===")

    if fail_count > 0:
        for stage, ok in results.items():
            if not ok:
                log.error(f"  FAILED: {stage}")
        sys.exit(1)


if __name__ == "__main__":
    main()
