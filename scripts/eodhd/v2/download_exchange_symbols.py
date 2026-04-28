"""
EODHD Raw Zone v2 — Download Exchange Symbol List
==================================================
Single API call to GET /exchange-symbol-list/AU.
Returns all ASX-listed instruments (stocks, ETFs, funds, etc.)

Output:
  {EXCHANGE_DIR}/exchange_symbols/{YYYY-MM-DD}.json.gz

Run this first — the historical job uses this file to build the code list
when market.companies is empty or when you want a fresh universe.

Usage:
    python scripts/eodhd/v2/download_exchange_symbols.py
    python scripts/eodhd/v2/download_exchange_symbols.py --force-recheck
"""

import gzip
import logging
import os
import sys
import argparse
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

EODHD_KEY  = os.getenv("EODHD_API_KEY", "")
EODHD_BASE = "https://eodhd.com/api"
RAW_BASE   = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

EXCHANGE_DIR = RAW_BASE / "eodhd" / "exchange=AU"
OUT_DIR      = EXCHANGE_DIR / "exchange_symbols"
AUDIT_DIR    = EXCHANGE_DIR / "audit"

RUN_DATE = date.today().strftime("%Y-%m-%d")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.eodhd.utils.quality_checks import check_http_status, check_symbol_list
from scripts.eodhd.utils.audit_logger import AuditLogger, load_known_checksums
from scripts.eodhd.utils.error_handler import ErrorHandler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-recheck", action="store_true")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env"); sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    out_path = OUT_DIR / f"{RUN_DATE}.json.gz"
    if out_path.exists() and not args.force_recheck:
        log.info(f"Already exists: {out_path.name} — skip (use --force-recheck to re-download)")
        sys.exit(0)

    known_checksums = load_known_checksums(AUDIT_DIR)
    handler = ErrorHandler(EXCHANGE_DIR, RUN_DATE)
    auditor = AuditLogger("exchange_symbols", RUN_DATE, AUDIT_DIR)

    log.info(f"Downloading exchange symbol list for AU → {out_path.name}")

    url    = f"{EODHD_BASE}/exchange-symbol-list/AU"
    params = {"api_token": EODHD_KEY, "fmt": "json"}

    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as e:
        log.error(f"Connection error: {e}")
        sys.exit(1)

    http = check_http_status(resp.status_code, resp.content)
    if http is not None:
        log.error(f"HTTP error: {http.reason}")
        handler.write_error("exchange_symbols", http.reason, resp.content)
        sys.exit(1)

    result = check_symbol_list(resp.content, min_rows=1000,
                               known_checksums=known_checksums)

    if result.destination == "skip":
        log.info(f"Duplicate content (unchanged since last download) — skip")
        auditor.record("exchange_symbols", "", "duplicate", reason=result.reason)
        auditor.finish(total=1, success=0, errors=0, quarantine=0,
                       retried=0, skipped=0, duplicates=1)
        sys.exit(0)

    if result.destination in ("errors", "quarantine"):
        log.error(f"Quality check failed: {result.reason}")
        handler.write_error("exchange_symbols", result.reason, resp.content)
        auditor.record("exchange_symbols", "", result.destination, reason=result.reason)
        auditor.finish(total=1, success=0, errors=1, quarantine=0,
                       retried=0, skipped=0, duplicates=0)
        sys.exit(1)

    with gzip.open(out_path, "wb") as f:
        f.write(resp.content)

    size = out_path.stat().st_size
    log.info(f"Saved {size:,} bytes → {out_path}")
    log.info(f"Symbol count: {len(result.data):,} instruments")

    known_checksums.add(result.checksum)
    auditor.record("exchange_symbols", out_path.name, "ok",
                   size_bytes=size, checksum=result.checksum)
    auditor.finish(total=1, success=1, errors=0, quarantine=0,
                   retried=0, skipped=0, duplicates=0)
    log.info("Next step: python scripts/eodhd/v2/load_to_staging_exchange_symbols.py")


if __name__ == "__main__":
    main()
