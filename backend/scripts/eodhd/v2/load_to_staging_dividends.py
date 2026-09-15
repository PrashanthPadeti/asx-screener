"""
Staging Load — Dividends
=========================
Reads raw dividend files from the Raw Zone and loads them into staging_au.dividends.

Source: {RAW_BASE}/eodhd/exchange=AU/dividends/historical/{CODE}.AU_{DATE}.json.gz

EODHD /div format:
  [{"date": "2024-09-12", "dividends": 2.30, "unadjustedValue": 2.30, "currency": "AUD"}]

NO transforms — column names match EODHD fields.

Usage:
    python scripts/eodhd/v2/load_to_staging_dividends.py
    python scripts/eodhd/v2/load_to_staging_dividends.py --codes BHP CBA
    python scripts/eodhd/v2/load_to_staging_dividends.py --from-code WBC
"""

import gzip
import json
import logging
import os
import sys
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.db import get_database_url_sync  # noqa: E402


load_dotenv()

DB_URL = get_database_url_sync()
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

DIV_DIR     = RAW_BASE / "eodhd" / "exchange=AU" / "dividends" / "historical"
BATCH_COMMIT = 100

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def sf(v) -> Optional[float]:
    if v is None or v in ("", "None", "N/A"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def sd(v) -> Optional[date]:
    if not v or str(v) in ("", "None", "0000-00-00"):
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def load_file(cur, path: Path) -> int:
    # Filename: {CODE}.AU_{YYYY-MM-DD}.json.gz
    stem = path.name[:-len(".json.gz")]
    parts = stem.split("_")
    asx_code = parts[0].replace(".AU", "")

    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        return 0

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        ex_date = sd(item.get("date"))
        if not ex_date:
            continue

        # Parse franking: "100%" → 100.0, None → None
        franking_raw = item.get("franking") or ""
        try:
            franking_pct = float(franking_raw.replace("%", "").strip()) if "%" in franking_raw else None
        except (ValueError, AttributeError):
            franking_pct = None

        rows.append((
            asx_code,
            ex_date,
            sf(item.get("value")),          # EODHD field is "value", not "dividends"
            sf(item.get("unadjustedValue")),
            (item.get("currency") or "AUD")[:5],
            item.get("period"),              # "Final", "Interim", "Special", etc.
            sd(item.get("declarationDate")),
            sd(item.get("recordDate")),
            sd(item.get("paymentDate")),
            franking_pct,
            path.name,
        ))

    if not rows:
        return 0

    execute_values(cur, """
        INSERT INTO staging_au.dividends
            (asx_code, date, dividend, unadjusted_value, currency,
             period, declaration_date, record_date, payment_date, franking_pct,
             source_file)
        VALUES %s
        ON CONFLICT (asx_code, date) DO UPDATE SET
            dividend         = EXCLUDED.dividend,
            unadjusted_value = EXCLUDED.unadjusted_value,
            currency         = EXCLUDED.currency,
            period           = EXCLUDED.period,
            declaration_date = EXCLUDED.declaration_date,
            record_date      = EXCLUDED.record_date,
            payment_date     = EXCLUDED.payment_date,
            franking_pct     = EXCLUDED.franking_pct,
            source_file      = EXCLUDED.source_file,
            loaded_at        = NOW()
    """, rows, page_size=500)
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-code")
    parser.add_argument("--limit",     type=int)
    args = parser.parse_args()

    if not DIV_DIR.exists():
        print(f"ERROR: {DIV_DIR} not found. Run download_dividends.py first.")
        sys.exit(1)

    if args.codes:
        files = []
        for c in args.codes:
            files.extend(sorted(DIV_DIR.glob(f"{c.upper()}.AU_*.json.gz")))
    else:
        files = sorted(DIV_DIR.glob("*.json.gz"))

    if args.from_code:
        files = [f for f in files if f.name >= f"{args.from_code.upper()}.AU"]
    if args.limit:
        files = files[:args.limit]

    total = len(files)
    is_full_run = not args.codes and not args.from_code
    log.info(f"Loading {total} dividend files → staging_au.dividends")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    if is_full_run:
        cur.execute("TRUNCATE TABLE staging_au.dividends RESTART IDENTITY")
        conn.commit()
        log.info("staging_au.dividends truncated.")

    # Named for what they actually count.
    #
    # These were `stocks_with_divs` and `total_rows`, and neither was true.
    # One file per code per download date means 3,556 files carry 1,236 codes,
    # so "3,555 stocks with dividends" was 3,555 FILES; and rows offered to
    # execute_values are deduplicated by ON CONFLICT (asx_code, date), so
    # "103,714 rows" landed as 29,804. Both figures sat in the job log beside a
    # table a third the size, which on 16 Sep 2026 read as two-thirds of all
    # issuers being silently dropped. It cost a full investigation to establish
    # that nothing was wrong.
    done = failed = rows_offered = files_with_rows = 0
    codes_seen: set[str] = set()

    for i, path in enumerate(files, 1):
        try:
            n = load_file(cur, path)
            if n > 0:
                files_with_rows += 1
                rows_offered += n
                codes_seen.add(path.name.split(".AU_")[0])
            done += 1
        except Exception as e:
            conn.rollback()
            failed += 1
            code = path.name[:-len(".json.gz")].split("_")[0]
            log.warning(f"  {code}: {e}")
            continue

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}]  files_with_rows={files_with_rows}  "
                     f"codes={len(codes_seen)}  rows_offered={rows_offered:,}  "
                     f"err={failed}")

    conn.commit()

    # Prove the population, do not report the loop.
    #
    # The expected set is derived from the filenames of files that actually
    # yielded rows, independently of anything the loop tallied, and compared
    # against what the table holds. A counter cannot distinguish "wrote every
    # code" from "wrote the ones it was admitted to see", which is why this is
    # a query rather than a summary line.
    cur.execute("SELECT DISTINCT asx_code FROM staging_au.dividends")
    persisted = {r[0] for r in cur.fetchall()}
    missing = sorted(codes_seen - persisted)

    cur.execute("SELECT count(*) FROM staging_au.dividends")
    rows_persisted = cur.fetchone()[0]

    cur.close()
    conn.close()

    log.info("DONE — %s files parsed, %s carried rows, %s distinct codes",
             f"{done:,}", f"{files_with_rows:,}", f"{len(codes_seen):,}")
    log.info("      %s rows offered -> %s persisted "
             "(the difference is ON CONFLICT (asx_code, date) deduplication, "
             "not loss)", f"{rows_offered:,}", f"{rows_persisted:,}")
    log.info("      %s codes persisted, %s errors",
             f"{len(persisted):,}", failed)

    if missing:
        log.error("COVERAGE FAILURE: %s codes had rows parsed but are absent "
                  "from staging_au.dividends: %s%s", len(missing),
                  ", ".join(missing[:25]),
                  " ..." if len(missing) > 25 else "")
        return 1
    if failed:
        log.error("%s files failed to parse; staging is incomplete. A code "
                  "whose only file failed appears in neither set above, so "
                  "this is the check that catches it.", failed)
        return 1
    return 0


if __name__ == "__main__":
    # sys.exit(main()), not main(). The bare call discarded the return value,
    # so the coverage check above could return 1 and the process would still
    # exit 0 — and weekly_pipeline's run() decides success from the exit code.
    # A completeness proof nothing reads is a completeness proof that does not
    # exist.
    sys.exit(main())
