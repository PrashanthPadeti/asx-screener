"""
EODHD Raw Zone v2 — Download EOD Prices
=========================================
Two modes:

  Historical (per-stock):
    GET /eod/{CODE}.AU?from=2000-01-01
    Output: {EXCHANGE_DIR}/eod_prices/historical/{CODE}.AU_{DATE}.json.gz

  Incremental (bulk daily):
    GET /eod/bulk-download/AU?date={DATE}
    Output: {EXCHANGE_DIR}/eod_prices/incremental/{DATE}.json.gz

Usage:
    # Full historical download for all stocks
    python scripts/eodhd/v2/download_eod_prices.py --mode historical

    # Single incremental day
    python scripts/eodhd/v2/download_eod_prices.py --mode incremental --date 2026-04-27

    # Backfill last 5 trading days
    python scripts/eodhd/v2/download_eod_prices.py --mode incremental --backfill-days 5

    # Resume historical from code
    python scripts/eodhd/v2/download_eod_prices.py --mode historical --from-code WBC

    nohup python scripts/eodhd/v2/download_eod_prices.py --mode historical > logs/dl_prices_v2.log 2>&1 &
"""

import gzip
import logging
import os
import sys
import time
import argparse
from datetime import date, timedelta
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DB_URL      = os.getenv("DATABASE_URL_SYNC",
                "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
EODHD_KEY   = os.getenv("EODHD_API_KEY", "")
EODHD_BASE  = "https://eodhd.com/api"
RAW_BASE    = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

EXCHANGE_DIR  = RAW_BASE / "eodhd" / "exchange=AU"
HIST_DIR      = EXCHANGE_DIR / "eod_prices" / "historical"
INCR_DIR      = EXCHANGE_DIR / "eod_prices" / "incremental"
AUDIT_DIR     = EXCHANGE_DIR / "audit"

SLEEP_HIST  = 0.15    # per-stock historical
DEFAULT_FROM = "2000-01-01"
RUN_DATE     = date.today().strftime("%Y-%m-%d")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.eodhd.utils.quality_checks import (
    check_http_status, check_prices_historical, check_prices_bulk,
)
from scripts.eodhd.utils.audit_logger import AuditLogger, load_known_checksums
from scripts.eodhd.utils.error_handler import ErrorHandler


class _NonRetryable(Exception):
    def __init__(self, reason, data=b""):
        super().__init__(reason)
        self.reason = reason
        self.data   = data

class _MaxRetriesExceeded(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _fetch_with_retry(url: str, params: dict, handler: ErrorHandler,
                      code: str) -> bytes:
    delays = [2, 8, 30]
    for attempt, delay in enumerate(delays, 1):
        try:
            resp = requests.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            reason = f"connection_error:{e}"
            handler.write_retry(code, reason, attempt)
            if attempt < len(delays):
                time.sleep(delay)
            continue

        http = check_http_status(resp.status_code, resp.content)
        if http is None:
            return resp.content
        if http.destination == "retry":
            handler.write_retry(code, http.reason, attempt)
            wait = 60 if "rate_limited" in http.reason else delay
            if attempt < len(delays):
                time.sleep(wait)
            continue
        raise _NonRetryable(http.reason, resp.content)

    raise _MaxRetriesExceeded("max_retries_exceeded")


# ─── Historical mode ──────────────────────────────────────────────────────────

def run_historical(codes: list[str], force: bool) -> None:
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    known_checksums = load_known_checksums(AUDIT_DIR)
    handler = ErrorHandler(EXCHANGE_DIR, RUN_DATE)
    auditor = AuditLogger("eod_prices_historical", RUN_DATE, AUDIT_DIR)

    total = len(codes)
    done = errors = quarantined = retried = skipped = 0

    log.info(f"Historical prices: {total} stocks → {HIST_DIR}")

    for i, code in enumerate(codes, 1):
        existing = list(HIST_DIR.glob(f"{code}.AU_{RUN_DATE}.json.gz"))
        if existing and not force:
            skipped += 1
            auditor.record(code, existing[0].name, "skip", reason="file_exists")
            continue

        url    = f"{EODHD_BASE}/eod/{code}.AU"
        params = {"api_token": EODHD_KEY, "fmt": "json", "from": DEFAULT_FROM}

        try:
            raw = _fetch_with_retry(url, params, handler, code)
        except _NonRetryable as e:
            errors += 1
            handler.write_error(code, e.reason, e.data)
            auditor.record(code, "", "error", reason=e.reason)
            time.sleep(SLEEP_HIST)
            continue
        except _MaxRetriesExceeded as e:
            retried += 1
            auditor.record(code, "", "retry", reason=e.reason)
            time.sleep(SLEEP_HIST)
            continue

        result = check_prices_historical(raw, code, known_checksums)
        time.sleep(SLEEP_HIST)

        if result.destination == "skip":
            auditor.record(code, "", "duplicate", reason=result.reason)
            continue
        if result.destination == "errors":
            errors += 1
            handler.write_error(code, result.reason, raw)
            auditor.record(code, "", "error", reason=result.reason)
            continue
        if result.destination == "quarantine":
            quarantined += 1
            handler.write_quarantine(code, result.reason, raw)
            auditor.record(code, "", "quarantine", reason=result.reason)
            continue

        filename = f"{code}.AU_{RUN_DATE}.json.gz"
        out_path = HIST_DIR / filename
        with gzip.open(out_path, "wb") as f:
            f.write(raw)

        known_checksums.add(result.checksum)
        done += 1
        auditor.record(code, filename, "ok",
                       size_bytes=out_path.stat().st_size, checksum=result.checksum)

        if i % 100 == 0:
            log.info(f"  [{i:4d}/{total}]  ok={done}  err={errors}  skip={skipped}")

    auditor.finish(total=total, success=done, errors=errors, quarantine=quarantined,
                   retried=retried, skipped=skipped)
    log.info(f"DONE historical — ok={done}  errors={errors}  skip={skipped}")


# ─── Incremental (bulk daily) mode ────────────────────────────────────────────

def run_incremental(dates: list[str], force: bool) -> None:
    INCR_DIR.mkdir(parents=True, exist_ok=True)
    known_checksums = load_known_checksums(AUDIT_DIR)
    handler = ErrorHandler(EXCHANGE_DIR, RUN_DATE)
    auditor = AuditLogger("eod_prices_incremental", RUN_DATE, AUDIT_DIR)

    done = errors = 0

    for target_date in dates:
        out_path = INCR_DIR / f"{target_date}.json.gz"
        if out_path.exists() and not force:
            log.info(f"  {target_date}: already exists — skip")
            auditor.record(target_date, out_path.name, "skip", reason="file_exists")
            continue

        url    = f"{EODHD_BASE}/eod/bulk-download/AU"
        params = {"api_token": EODHD_KEY, "fmt": "json", "date": target_date}

        try:
            raw = _fetch_with_retry(url, params, handler, target_date)
        except (_NonRetryable, _MaxRetriesExceeded) as e:
            errors += 1
            handler.write_error(target_date, e.reason)
            auditor.record(target_date, "", "error", reason=e.reason)
            continue

        result = check_prices_bulk(raw, min_rows=1500, known_checksums=known_checksums)

        if result.destination == "skip":
            auditor.record(target_date, "", "duplicate", reason=result.reason)
            continue
        if result.destination in ("errors", "quarantine"):
            errors += 1
            if result.destination == "quarantine":
                handler.write_quarantine(target_date, result.reason, raw)
            else:
                handler.write_error(target_date, result.reason, raw)
            auditor.record(target_date, "", result.destination, reason=result.reason)
            continue

        with gzip.open(out_path, "wb") as f:
            f.write(raw)

        known_checksums.add(result.checksum)
        done += 1
        auditor.record(target_date, out_path.name, "ok",
                       size_bytes=out_path.stat().st_size, checksum=result.checksum)
        log.info(f"  {target_date}: saved → {out_path.name}")

    auditor.finish(total=len(dates), success=done, errors=errors, quarantine=0,
                   retried=0, skipped=len(dates) - done - errors)
    log.info(f"DONE incremental — ok={done}  errors={errors}")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["historical", "incremental"],
                        required=True)
    parser.add_argument("--codes",         nargs="+")
    parser.add_argument("--from-code",     help="Historical: resume from this code")
    parser.add_argument("--limit",         type=int)
    parser.add_argument("--date",          help="Incremental: specific date YYYY-MM-DD")
    parser.add_argument("--backfill-days", type=int, default=1,
                        help="Incremental: load last N days (default 1)")
    parser.add_argument("--force-recheck", action="store_true")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env"); sys.exit(1)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    if args.mode == "historical":
        if args.codes:
            codes = [c.upper() for c in args.codes]
        else:
            conn = psycopg2.connect(DB_URL)
            cur  = conn.cursor()
            cur.execute("SELECT asx_code FROM market.companies "
                        "WHERE status='active' ORDER BY asx_code")
            codes = [r[0] for r in cur.fetchall()]
            cur.close(); conn.close()

        if args.from_code:
            codes = [c for c in codes if c >= args.from_code.upper()]
        if args.limit:
            codes = codes[:args.limit]

        run_historical(codes, force=args.force_recheck)

    else:  # incremental
        if args.date:
            dates = [args.date]
        else:
            today = date.today()
            dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d")
                     for i in range(args.backfill_days)]

        run_incremental(dates, force=args.force_recheck)

    log.info("Next step: python scripts/eodhd/v2/load_to_staging_prices.py")


if __name__ == "__main__":
    main()
