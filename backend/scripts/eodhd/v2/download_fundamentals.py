"""
EODHD Raw Zone v2 — Download Fundamentals
==========================================
Downloads /fundamentals/{ticker}.AU for every ASX stock.

Output directory (per architecture):
  {RAW_BASE}/eodhd/exchange=AU/fundamentals/full_snapshot/
  Filename: {CODE}.AU_{YYYY-MM-DD}.json.gz

Features vs v1:
  - Proper raw zone folder layout (exchange=AU partition)
  - Date-stamped filenames (never overwrite)
  - Quality checks before writing (errors/, quarantine/, retry/)
  - Audit manifest written to audit/ folder
  - Checksum deduplication — skip if file content unchanged
  - Retry logic: up to 3 attempts with exponential backoff

Usage:
    python scripts/eodhd/v2/download_fundamentals.py
    python scripts/eodhd/v2/download_fundamentals.py --codes BHP CBA
    python scripts/eodhd/v2/download_fundamentals.py --from-code WBC
    python scripts/eodhd/v2/download_fundamentals.py --force-recheck
    nohup python scripts/eodhd/v2/download_fundamentals.py > logs/dl_fund_v2.log 2>&1 &
"""

import gzip
import json
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

# ── Paths ─────────────────────────────────────────────────────────────────────
DB_URL      = os.getenv("DATABASE_URL_SYNC",
                "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
EODHD_KEY   = os.getenv("EODHD_API_KEY", "")
EODHD_BASE  = "https://eodhd.com/api"
RAW_BASE    = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

EXCHANGE_DIR = RAW_BASE / "eodhd" / "exchange=AU"
OUT_DIR      = EXCHANGE_DIR / "fundamentals" / "full_snapshot"
AUDIT_DIR    = EXCHANGE_DIR / "audit"

SLEEP_SEC    = 0.3
RUN_DATE     = date.today().strftime("%Y-%m-%d")

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# Budget guard — see app/core/api_budget.py. Announcements once billed 144,000
# calls a day against a 100,000 limit, so every EODHD job now prices itself
# first and measures what it was actually billed.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.api_budget import may_start_sync, measure, cost_of  # noqa: E402
from scripts.eodhd.utils.sharding import (  # noqa: E402
    SHARD_COUNT, current_shard, filter_to_shard,
)

# ── Import utils (add project root to path) ───────────────────────────────────
from scripts.eodhd.utils.quality_checks import check_http_status, check_fundamentals
from scripts.eodhd.utils.audit_logger import AuditLogger, load_known_checksums
from scripts.eodhd.utils.error_handler import ErrorHandler


# ─── Fetch ────────────────────────────────────────────────────────────────────

def fetch_raw(asx_code: str) -> tuple[int, bytes]:
    """Return (status_code, raw_bytes). Raises on connection error."""
    ticker = f"{asx_code}.AU"
    url    = f"{EODHD_BASE}/fundamentals/{ticker}"
    params = {"api_token": EODHD_KEY, "fmt": "json"}
    resp   = requests.get(url, params=params, timeout=30)
    return resp.status_code, resp.content


def fetch_with_retry(asx_code: str, handler: ErrorHandler) -> tuple[bytes, str]:
    """
    Fetch with exponential backoff for 5xx/429.
    Returns (raw_bytes, checksum_or_empty) or raises on unrecoverable failure.
    Writes to retry/ on intermediate failures; raises after MAX_RETRIES.
    """
    delays = [2, 8, 30]
    last_reason = ""

    for attempt, delay in enumerate(delays, 1):
        try:
            status, data = fetch_raw(asx_code)
        except requests.RequestException as e:
            last_reason = f"connection_error:{e}"
            handler.write_retry(asx_code, last_reason, attempt)
            if attempt < len(delays):
                time.sleep(delay)
            continue

        # Check HTTP status
        http_result = check_http_status(status, data)
        if http_result is None:
            return data, ""             # 200 OK — proceed to quality check

        if http_result.destination == "retry":
            last_reason = http_result.reason
            handler.write_retry(asx_code, last_reason, attempt)
            if attempt < len(delays):
                wait = 60 if "rate_limited" in last_reason else delay
                log.warning(f"  {asx_code}: {last_reason} — retry in {wait}s")
                time.sleep(wait)
            continue

        # Non-retryable (4xx) — raise immediately
        raise _NonRetryable(http_result.reason, data)

    raise _MaxRetriesExceeded(last_reason)


class _NonRetryable(Exception):
    def __init__(self, reason: str, data: bytes = b""):
        super().__init__(reason)
        self.reason = reason
        self.data   = data

class _MaxRetriesExceeded(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",        nargs="+")
    parser.add_argument("--from-code",    help="Resume from this code")
    parser.add_argument("--limit",        type=int)
    parser.add_argument("--force-recheck", action="store_true",
                        help="Ignore existing files — re-download and re-check")
    parser.add_argument("--shard", type=int, metavar="N",
                        help=f"Refresh only shard N of {SHARD_COUNT} (0-{SHARD_COUNT - 1}). "
                             "Use --shard-this-week to pick it from the calendar.")
    parser.add_argument("--shard-this-week", action="store_true",
                        help="Refresh the shard due this ISO week.")
    args = parser.parse_args()

    if not EODHD_KEY:
        print("ERROR: EODHD_API_KEY not set in .env"); sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    # Load known checksums for deduplication
    known_checksums = load_known_checksums(AUDIT_DIR)
    log.info(f"Loaded {len(known_checksums):,} known checksums from audit/")

    # Get stock list from DB
    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor()
        cur.execute("SELECT asx_code FROM market.companies "
                    "WHERE is_current AND status='active' ORDER BY asx_code")
        codes = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()

    if args.from_code:
        codes = [c for c in codes if c >= args.from_code.upper()]
    # Weekly shard: a quarter of the universe per Sunday, so the ~21,000-call
    # full refresh becomes ~5,250 and leaves room for dividends and splits.
    shard = args.shard if args.shard is not None else (
        current_shard() if args.shard_this_week else None)
    if shard is not None and not args.codes:
        before = len(codes)
        codes = filter_to_shard(codes, shard)
        log.info(f"Shard {shard} of {SHARD_COUNT}: {len(codes)} of {before} stocks")

    if args.limit:
        codes = codes[:args.limit]

    total = len(codes)
    log.info(f"Downloading fundamentals for {total} stocks → {OUT_DIR}")
    log.info(f"Run date: {RUN_DATE}  |  Est. time: ~{total * SLEEP_SEC / 60:.0f} min")

    handler = ErrorHandler(EXCHANGE_DIR, RUN_DATE)
    auditor = AuditLogger("fundamentals_full_snapshot", RUN_DATE, AUDIT_DIR)

    done = errors = quarantined = retried = skipped = duplicates = 0

    # EODHD bills /fundamentals at 10 calls per symbol, so a full refresh of
    # the universe is roughly 21,000 calls — two thirds of the entire ASX
    # share. It is deferrable, so it yields to the reserve.
    est = cost_of("fundamentals", total)
    if not may_start_sync(est, job="fundamentals_full_snapshot", critical=False):
        log.error("Deferred — a full fundamentals refresh would exhaust the ASX EODHD budget.")
        raise SystemExit(2)

    with measure("fundamentals_full_snapshot", expected=est):
        for i, code in enumerate(codes, 1):
            # Skip if today's file already exists and not force mode
            existing = list(OUT_DIR.glob(f"{code}.AU_{RUN_DATE}.json.gz"))
            if existing and not args.force_recheck:
                skipped += 1
                auditor.record(code, existing[0].name, "skip", reason="file_exists")
                continue

            try:
                raw_bytes, _ = fetch_with_retry(code, handler)
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

            # Quality checks
            result = check_fundamentals(raw_bytes, code, known_checksums)
            time.sleep(SLEEP_SEC)

            if result.destination == "skip":
                duplicates += 1
                auditor.record(code, "", "duplicate", reason=result.reason)
                continue

            if result.destination == "errors":
                errors += 1
                handler.write_error(code, result.reason, raw_bytes)
                auditor.record(code, "", "error", reason=result.reason)
                continue

            if result.destination == "quarantine":
                quarantined += 1
                handler.write_quarantine(code, result.reason, raw_bytes)
                auditor.record(code, "", "quarantine", reason=result.reason)
                continue

            # All checks passed — write to output
            filename = f"{code}.AU_{RUN_DATE}.json.gz"
            out_path = OUT_DIR / filename
            with gzip.open(out_path, "wb") as f:
                f.write(raw_bytes)

            size = out_path.stat().st_size
            known_checksums.add(result.checksum)
            done += 1
            auditor.record(code, filename, "ok",
                           size_bytes=size, checksum=result.checksum)

            if i % 100 == 0:
                log.info(f"  [{i:4d}/{total}]  ok={done}  err={errors}  "
                         f"qua={quarantined}  skip={skipped}  dup={duplicates}")

        auditor.finish(
            total=total, success=done, errors=errors, quarantine=quarantined,
            retried=retried, skipped=skipped, duplicates=duplicates,
        )
        log.info(f"DONE — ok={done}  errors={errors}  quarantine={quarantined}  "
                 f"retried={retried}  skipped={skipped}  duplicates={duplicates}")
    log.info(f"Files → {OUT_DIR}")
    log.info("Next step: python scripts/eodhd/v2/load_to_staging_fundamentals.py")


if __name__ == "__main__":
    main()
