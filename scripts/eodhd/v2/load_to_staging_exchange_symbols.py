"""
Staging Load — Exchange Symbols
================================
Reads the latest exchange_symbols/{DATE}.json.gz from the Raw Zone
and loads into staging.exchange_symbols (TRUNCATE + reload).

Usage:
    python scripts/eodhd/v2/load_to_staging_exchange_symbols.py
    python scripts/eodhd/v2/load_to_staging_exchange_symbols.py --date 2026-04-28
"""

import gzip
import json
import logging
import os
import sys
import argparse
from datetime import date
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL   = os.getenv("DATABASE_URL_SYNC",
             "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))

EXCHANGE_DIR  = RAW_BASE / "eodhd" / "exchange=AU"
SYMBOLS_DIR   = EXCHANGE_DIR / "exchange_symbols"

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def find_latest_file(target_date: str | None) -> Path:
    if target_date:
        p = SYMBOLS_DIR / f"{target_date}.json.gz"
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        return p
    # Find the most recent file
    files = sorted(SYMBOLS_DIR.glob("*.json.gz"), reverse=True)
    if not files:
        raise FileNotFoundError(f"No exchange symbol files in {SYMBOLS_DIR}")
    return files[0]


def parse_rows(data: list, snapshot_date: date, source_file: str) -> list[tuple]:
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        code = item.get("Code", "").strip()
        if not code:
            continue
        rows.append((
            code,
            item.get("Name"),
            item.get("Country"),
            item.get("Exchange"),
            item.get("Currency"),
            item.get("Type"),
            item.get("Isin") or None,
            snapshot_date,
            source_file,
        ))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Specific snapshot date YYYY-MM-DD (default: latest file)")
    args = parser.parse_args()

    path          = find_latest_file(args.date)
    snapshot_date = date.fromisoformat(path.stem)   # filename = YYYY-MM-DD

    log.info(f"Loading exchange symbols from {path.name}")

    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        log.error("Expected JSON array — got unexpected format"); sys.exit(1)

    rows = parse_rows(data, snapshot_date, path.name)
    log.info(f"Parsed {len(rows):,} symbols")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    # Truncate and reload
    cur.execute("TRUNCATE TABLE staging.exchange_symbols RESTART IDENTITY")
    log.info("staging.exchange_symbols truncated")

    execute_values(cur, """
        INSERT INTO staging.exchange_symbols
            (code, name, country, exchange, currency, type, isin,
             snapshot_date, source_file)
        VALUES %s
        ON CONFLICT (code) DO UPDATE SET
            name          = EXCLUDED.name,
            country       = EXCLUDED.country,
            exchange      = EXCLUDED.exchange,
            currency      = EXCLUDED.currency,
            type          = EXCLUDED.type,
            isin          = EXCLUDED.isin,
            snapshot_date = EXCLUDED.snapshot_date,
            source_file   = EXCLUDED.source_file,
            loaded_at     = NOW()
    """, rows, page_size=5000)

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"DONE — {len(rows):,} symbols loaded into staging.exchange_symbols")


if __name__ == "__main__":
    main()
