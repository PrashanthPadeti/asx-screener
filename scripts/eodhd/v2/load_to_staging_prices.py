"""
Staging Load — EOD Prices
==========================
Reads raw EOD price files from the Raw Zone and loads them into staging.eod_prices.

Handles two layouts:
  Historical (per-stock): {EXCHANGE_DIR}/eod_prices/historical/{CODE}.AU_{DATE}.json.gz
  Incremental (bulk):     {EXCHANGE_DIR}/eod_prices/incremental/{DATE}.json.gz

NO transforms — column names match EODHD fields.

Usage:
    # Load all historical files
    python scripts/eodhd/v2/load_to_staging_prices.py --mode historical

    # Load one incremental date
    python scripts/eodhd/v2/load_to_staging_prices.py --mode incremental --date 2026-04-27

    # Load last N incremental days
    python scripts/eodhd/v2/load_to_staging_prices.py --mode incremental --last-days 5

    # Load specific stocks
    python scripts/eodhd/v2/load_to_staging_prices.py --mode historical --codes BHP CBA
"""

import gzip
import json
import logging
import os
import sys
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL   = os.getenv("DATABASE_URL_SYNC",
             "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

EXCHANGE_DIR = RAW_BASE / "eodhd" / "exchange=AU"
HIST_DIR     = EXCHANGE_DIR / "eod_prices" / "historical"
INCR_DIR     = EXCHANGE_DIR / "eod_prices" / "incremental"
BATCH_COMMIT = 50

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def sf(v) -> Optional[float]:
    if v is None or v in ("", "None"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_rows(data: list, asx_code: Optional[str], source_file: str) -> list[tuple]:
    rows = []
    for r in data:
        if not isinstance(r, dict):
            continue
        dt_str = r.get("date")
        if not dt_str:
            continue
        try:
            price_dt = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue

        code = asx_code or r.get("code")
        if not code:
            continue

        close     = sf(r.get("close"))
        adj_close = sf(r.get("adjusted_close"))
        if close is None and adj_close is None:
            continue

        rows.append((
            code, price_dt,
            round(sf(r.get("open")),   4) if sf(r.get("open"))   is not None else None,
            round(sf(r.get("high")),   4) if sf(r.get("high"))   is not None else None,
            round(sf(r.get("low")),    4) if sf(r.get("low"))    is not None else None,
            round(close,               4) if close                is not None else None,
            round(adj_close,           4) if adj_close            is not None else None,
            int(r["volume"])               if r.get("volume")     is not None else None,
            source_file,
        ))
    return rows


def upsert_prices(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    execute_values(cur, """
        INSERT INTO staging.eod_prices
            (asx_code, date, open, high, low, close, adjusted_close,
             volume, source_file)
        VALUES %s
        ON CONFLICT (asx_code, date, source_file) DO UPDATE SET
            open           = EXCLUDED.open,
            high           = EXCLUDED.high,
            low            = EXCLUDED.low,
            close          = EXCLUDED.close,
            adjusted_close = EXCLUDED.adjusted_close,
            volume         = EXCLUDED.volume
    """, rows, page_size=2000)
    return len(rows)


def load_historical_file(cur, path: Path) -> int:
    stem = path.name[:-len(".json.gz")]
    parts = stem.split("_")
    asx_code = parts[0].replace(".AU", "")

    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return 0

    rows = parse_rows(data, asx_code=asx_code, source_file=path.name)
    return upsert_prices(cur, rows)


def load_bulk_file(cur, path: Path) -> int:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return 0

    rows = parse_rows(data, asx_code=None, source_file=path.name)
    return upsert_prices(cur, rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["historical", "incremental"], required=True)
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-code")
    parser.add_argument("--limit",     type=int)
    parser.add_argument("--date",      help="Incremental: specific date YYYY-MM-DD")
    parser.add_argument("--last-days", type=int, help="Incremental: load last N days")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    total_rows = done = failed = 0

    if args.mode == "incremental":
        if args.date:
            dates = [args.date]
        elif args.last_days:
            today = date.today()
            dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d")
                     for i in range(args.last_days)]
        else:
            dates = [date.today().strftime("%Y-%m-%d")]

        log.info(f"Loading {len(dates)} incremental price file(s)")
        for target_date in dates:
            path = INCR_DIR / f"{target_date}.json.gz"
            if not path.exists():
                log.warning(f"  {target_date}: file not found")
                failed += 1
                continue
            try:
                n = load_bulk_file(cur, path)
                conn.commit()
                log.info(f"  {target_date}: {n:,} rows")
                total_rows += n
                done += 1
            except Exception as e:
                conn.rollback()
                failed += 1
                log.warning(f"  {target_date}: {e}")

    else:  # historical
        if not HIST_DIR.exists():
            print(f"ERROR: {HIST_DIR} not found."); sys.exit(1)

        if args.codes:
            files = []
            for c in args.codes:
                files.extend(sorted(HIST_DIR.glob(f"{c.upper()}.AU_*.json.gz")))
        else:
            files = sorted(HIST_DIR.glob("*.json.gz"))

        if args.from_code:
            files = [f for f in files if f.name >= f"{args.from_code.upper()}.AU"]
        if args.limit:
            files = files[:args.limit]

        total = len(files)
        log.info(f"Loading {total} historical price files from {HIST_DIR}")

        for i, path in enumerate(files, 1):
            try:
                n = load_historical_file(cur, path)
                total_rows += n
                done += 1
            except Exception as e:
                conn.rollback()
                failed += 1
                log.warning(f"  {path.name}: {e}")
                continue

            if i % BATCH_COMMIT == 0:
                conn.commit()
                log.info(f"  [{i:4d}/{total}]  ok={done}  err={failed}  "
                         f"rows={total_rows:,}")

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {done} files loaded | {total_rows:,} rows | {failed} errors")


if __name__ == "__main__":
    main()
