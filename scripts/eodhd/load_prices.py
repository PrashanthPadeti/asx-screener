"""
EODHD Raw Zone — Load Prices from Disk → DB
============================================
Step 2: disk → database.  Reads gzipped JSON files saved by the
download scripts and upserts into market.daily_prices.

Handles two file layouts:
  Historical (per-stock):   data/raw/eodhd/historical/prices/{CODE}.json.gz
      Each file is a JSON array of daily OHLCV rows for one stock.
  Incremental (bulk/date):  data/raw/eodhd/incremental/prices/{DATE}.json.gz
      Each file is a JSON array of all ASX stocks for one date.

Usage:
    # Load all historical price files
    python scripts/eodhd/load_prices.py

    # Load one incremental date
    python scripts/eodhd/load_prices.py --date 2026-04-27

    # Load last N incremental days
    python scripts/eodhd/load_prices.py --last-days 5

    # Load specific stocks from historical
    python scripts/eodhd/load_prices.py --codes BHP CBA

    # Resume historical load from a code
    python scripts/eodhd/load_prices.py --from-code WBC
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

DB_URL       = os.getenv("DATABASE_URL_SYNC",
                  "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE     = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
HIST_DIR     = RAW_BASE / "eodhd" / "historical" / "prices"
INCR_DIR     = RAW_BASE / "eodhd" / "incremental" / "prices"
BATCH_COMMIT = 50         # commit every N files

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def sf(val) -> Optional[float]:
    if val is None or val == "" or val == "None":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_price_rows(data: list, asx_code: Optional[str] = None) -> list[tuple]:
    """
    Convert JSON rows to DB tuples.

    Historical format (per-stock): each item has 'date', 'open', 'high', 'low',
        'close', 'adjusted_close', 'volume'.  asx_code is the stock code.

    Bulk format (all stocks): each item also has 'code' and 'exchange_short_name'.
    """
    rows = []
    for r in data:
        dt_str = r.get("date")
        if not dt_str:
            continue
        try:
            price_dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
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
            price_dt,
            code,
            round(sf(r.get("open")),   4) if sf(r.get("open"))   is not None else None,
            round(sf(r.get("high")),   4) if sf(r.get("high"))   is not None else None,
            round(sf(r.get("low")),    4) if sf(r.get("low"))    is not None else None,
            round(close,               4) if close                is not None else None,
            round(adj_close,           4) if adj_close            is not None
                                          else round(close, 4),
            int(r["volume"]) if r.get("volume") is not None else None,
            "eodhd",
        ))
    return rows


def upsert_prices(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO market.daily_prices
            (time, asx_code, open, high, low, close, adjusted_close, volume, data_source)
        VALUES %s
        ON CONFLICT (time, asx_code) DO UPDATE SET
            open           = EXCLUDED.open,
            high           = EXCLUDED.high,
            low            = EXCLUDED.low,
            close          = EXCLUDED.close,
            adjusted_close = EXCLUDED.adjusted_close,
            volume         = EXCLUDED.volume,
            data_source    = EXCLUDED.data_source
    """
    execute_values(cur, sql, rows, page_size=2000)
    return len(rows)


def load_historical_file(cur, path: Path) -> int:
    """Load one per-stock historical file."""
    code = path.name
    if code.endswith(".json.gz"):
        code = code[:-len(".json.gz")]

    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return 0

    rows = parse_price_rows(data, asx_code=code)
    return upsert_prices(cur, rows)


def load_bulk_file(cur, path: Path) -> int:
    """Load one bulk-by-date incremental file."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return 0

    rows = parse_price_rows(data)
    return upsert_prices(cur, rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",      help="Load a single incremental date YYYY-MM-DD")
    parser.add_argument("--last-days", type=int, help="Load last N incremental days")
    parser.add_argument("--codes",     nargs="+", help="Load specific stocks from historical")
    parser.add_argument("--from-code", help="Resume historical load from this code")
    parser.add_argument("--limit",     type=int)
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    total_rows = 0
    done = failed = 0

    # ── Incremental mode ────────────────────────────────────────
    if args.date or args.last_days:
        if args.date:
            dates = [args.date]
        else:
            today = date.today()
            dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d")
                     for i in range(args.last_days)]

        log.info(f"Loading {len(dates)} incremental price file(s)")

        for target_date in dates:
            path = INCR_DIR / f"{target_date}.json.gz"
            if not path.exists():
                log.warning(f"  {target_date}: file not found — run download_daily_prices.py first")
                failed += 1
                continue
            try:
                n = load_bulk_file(cur, path)
                conn.commit()
                log.info(f"  {target_date}: {n:,} rows upserted")
                total_rows += n
                done += 1
            except Exception as e:
                conn.rollback()
                failed += 1
                log.warning(f"  {target_date}: {e}")

    # ── Historical mode ─────────────────────────────────────────
    else:
        if not HIST_DIR.exists():
            print(f"ERROR: {HIST_DIR} does not exist.")
            print("Run download_historical_prices.py first.")
            sys.exit(1)

        if args.codes:
            files = [HIST_DIR / f"{c.upper()}.json.gz" for c in args.codes
                     if (HIST_DIR / f"{c.upper()}.json.gz").exists()]
        else:
            files = sorted(HIST_DIR.glob("*.json.gz"))

        if args.from_code:
            files = [f for f in files if f.name >= f"{args.from_code.upper()}.json.gz"]
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
                log.info(f"  [{i:4d}/{total}] {done} ok, {failed} err | {total_rows:,} rows total")

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"DONE — {done} files loaded, {failed} errors | {total_rows:,} rows upserted")


if __name__ == "__main__":
    main()
