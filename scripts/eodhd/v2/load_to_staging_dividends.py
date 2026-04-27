"""
Staging Load — Dividends
=========================
Reads raw dividend files from the Raw Zone and loads them into staging.dividends.

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

load_dotenv()

DB_URL   = os.getenv("DATABASE_URL_SYNC",
             "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
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
        rows.append((
            asx_code,
            ex_date,
            sf(item.get("dividends")),
            sf(item.get("unadjustedValue")),
            (item.get("currency") or "AUD")[:5],
            path.name,
        ))

    if not rows:
        return 0

    # Mark older rows for this code as not-latest
    cur.execute("""
        UPDATE staging.dividends SET is_latest = FALSE
        WHERE asx_code = %s AND is_latest = TRUE AND source_file != %s
    """, (asx_code, path.name))

    execute_values(cur, """
        INSERT INTO staging.dividends
            (asx_code, date, dividend, unadjusted_value, currency,
             source_file, is_latest)
        VALUES %s
        ON CONFLICT (asx_code, date, source_file) DO UPDATE SET
            dividend          = EXCLUDED.dividend,
            unadjusted_value  = EXCLUDED.unadjusted_value,
            currency          = EXCLUDED.currency,
            is_latest         = TRUE
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
    log.info(f"Loading {total} dividend files → staging.dividends")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    done = failed = total_rows = stocks_with_divs = 0

    for i, path in enumerate(files, 1):
        try:
            n = load_file(cur, path)
            if n > 0:
                stocks_with_divs += 1
                total_rows += n
            done += 1
        except Exception as e:
            conn.rollback()
            failed += 1
            code = path.name[:-len(".json.gz")].split("_")[0]
            log.warning(f"  {code}: {e}")
            continue

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}]  stocks_with_divs={stocks_with_divs}  "
                     f"rows={total_rows:,}  err={failed}")

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {stocks_with_divs} stocks with dividends | "
             f"{total_rows:,} rows | {failed} errors")


if __name__ == "__main__":
    main()
