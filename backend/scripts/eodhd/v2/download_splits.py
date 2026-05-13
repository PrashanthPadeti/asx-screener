"""
EODHD Raw Zone v2 — Download Splits History
============================================
Downloads GET /splits/{ticker}.AU for every ASX stock.
Returns an array of {date, split} objects, e.g. [{"date": "2015-05-18", "split": "2:1"}].
Empty array [] is valid (no splits).

Output:
  {EXCHANGE_DIR}/splits/historical/{CODE}.AU_{YYYY-MM-DD}.json.gz

Usage:
    python scripts/eodhd/v2/download_splits.py
    python scripts/eodhd/v2/download_splits.py --codes BHP CBA
    python scripts/eodhd/v2/download_splits.py --from-code WBC
    nohup python scripts/eodhd/v2/download_splits.py > logs/dl_splits.log 2>&1 &
"""

import gzip
import logging
import os
import sys
import time
import argparse
from datetime import date
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DB_URL     = os.getenv("DATABASE_URL_SYNC",
               "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
EODHD_KEY  = os.getenv("EODHD_API_KEY", "")
EODHD_BASE = "https://eodhd.com/api"
RAW_BASE   = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

EXCHANGE_DIR = RAW_BASE / "eodhd" / "exchange=AU"
OUT_DIR      = EXCHANGE_DIR / "splits" / "historical"
AUDIT_DIR    = EXCHANGE_DIR / "audit"

SLEEP_SEC = 0.2
RUN_DATE  = date.today().strftime("%Y-%m-%d")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.eodhd.utils.quality_checks import check_http_status, check_splits
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


def fetch_with_retry(asx_code: str, handler: ErrorHandler) -> bytes:
    delays = [2, 8, 30]
    last_reason = ""
    for attempt, delay in enumerate(delays, 1):
        try:
            url    = f"{EODHD_BASE}/splits/{asx_code}.AU"
            params = {"api_token": EODHD_KEY, "fmt": "json", "from": "2000-01-01"}
            resp   = requests.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            last_reason = f"connection_error:{e}"
            handler.write_retry(asx_code, last_reason, attempt)
            if attempt < len(delays):
                time.sleep(delay)
            continue

        http = check_http_status(resp.status_code, resp.content)
        if http is None:
            return resp.content
        if http.destination == "retry":
            last_reason = http.reason
            handler.write_retry(asx_code, last_reason, attempt)
            wait = 60 if "rate_limited" in last_reason else delay
            if attempt < len(delays):
                time.sleep(wait)
            continue
        raise _NonRetryable(http.reason, resp.content)

    raise _MaxRetriesExceeded(last_reason)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",         nargs="+")
    parser.add_argument("--from-code",     help="Resume from this code")
    parser.add_argument("--limit",         type=int)
    parser.add_argument("--force-recheck", action="store_true")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env"); sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    known_checksums = load_known_checksums(AUDIT_DIR)

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

    total = len(codes)
    log.info(f"Downloading splits for {total} stocks → {OUT_DIR}")

    handler = ErrorHandler(EXCHANGE_DIR, RUN_DATE)
    auditor = AuditLogger("splits_historical", RUN_DATE, AUDIT_DIR)

    done = errors = retried = skipped = duplicates = has_splits = 0

    for i, code in enumerate(codes, 1):
        existing = list(OUT_DIR.glob(f"{code}.AU_{RUN_DATE}.json.gz"))
        if existing and not args.force_recheck:
            skipped += 1
            auditor.record(code, existing[0].name, "skip", reason="file_exists")
            continue

        try:
            raw = fetch_with_retry(code, handler)
        except _NonRetryable as e:
            errors += 1
            handler.write_error(code, e.reason, e.data)
            auditor.record(code, "", "error", reason=e.reason)
            time.sleep(SLEEP_SEC)
            continue
        except _MaxRetriesExceeded as e:
            retried += 1
            auditor.record(code, "", "retry", reason=e.reason)
            time.sleep(SLEEP_SEC)
            continue

        result = check_splits(raw, known_checksums)
        time.sleep(SLEEP_SEC)

        if result.destination == "skip":
            duplicates += 1
            auditor.record(code, "", "duplicate", reason=result.reason)
            continue

        if result.destination in ("errors", "quarantine"):
            errors += 1
            handler.write_error(code, result.reason, raw)
            auditor.record(code, "", result.destination, reason=result.reason)
            continue

        filename = f"{code}.AU_{RUN_DATE}.json.gz"
        out_path = OUT_DIR / filename
        with gzip.open(out_path, "wb") as f:
            f.write(raw)

        size = out_path.stat().st_size
        known_checksums.add(result.checksum)
        done += 1

        if result.data and len(result.data) > 0:
            has_splits += 1

        auditor.record(code, filename, "ok", size_bytes=size, checksum=result.checksum)

        if i % 200 == 0:
            log.info(f"  [{i:4d}/{total}]  ok={done} ({has_splits} with splits)  "
                     f"err={errors}  skip={skipped}")

    auditor.finish(total=total, success=done, errors=errors, quarantine=0,
                   retried=retried, skipped=skipped, duplicates=duplicates)
    log.info(f"DONE — ok={done} ({has_splits} with splits)  "
             f"errors={errors}  skipped={skipped}")


if __name__ == "__main__":
    main()
