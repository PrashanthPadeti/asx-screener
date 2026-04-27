"""
EODHD Raw Zone — Load Dividends from Disk → DB
===============================================
Reads gzipped dividend JSON files saved by download_historical_dividends.py
and upserts into market.dividends.

Also updates annual DPS in financials.annual_pnl by summing dividends per FY.

EODHD /div/{ticker} response format:
  [{"date": "2024-09-12", "dividends": 2.30, "unadjustedValue": 2.30,
    "currency": "AUD"}, ...]

Usage:
    python scripts/eodhd/load_dividends.py
    python scripts/eodhd/load_dividends.py --codes BHP CBA
    python scripts/eodhd/load_dividends.py --from-code WBC
"""

import gzip
import json
import logging
import os
import sys
import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_URL       = os.getenv("DATABASE_URL_SYNC",
                  "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
RAW_BASE     = Path(os.getenv("RAW_DATA_DIR", "/opt/asx-screener/data/raw"))
DIV_DIR      = RAW_BASE / "eodhd" / "historical" / "dividends"
BATCH_COMMIT = 100

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


def sd(val) -> Optional[date]:
    if not val or val in ("", "None", "NA", "0000-00-00"):
        return None
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_dividend_file(asx_code: str, data: list) -> tuple[list[dict], dict[int, float]]:
    """
    Returns (div_rows, dps_by_fy).
    EODHD /div format: {"date": ex_date, "dividends": amount,
                         "unadjustedValue": raw_amount, "currency": "AUD"}
    """
    rows: list[dict] = []
    dps_by_fy: dict[int, float] = {}

    for item in data:
        if not isinstance(item, dict):
            continue

        ex_date = sd(item.get("date"))
        if not ex_date:
            continue

        # EODHD /div uses "dividends" (adjusted) and "unadjustedValue"
        amount = sf(item.get("unadjustedValue") or item.get("dividends"))
        adj    = sf(item.get("dividends"))
        if amount is None and adj is None:
            continue

        use_amount = amount if amount is not None else adj
        currency   = (item.get("currency") or "AUD")[:3]

        rows.append({
            "asx_code":         asx_code,
            "ex_date":          ex_date,
            "pay_date":         None,    # not provided by /div endpoint
            "record_date":      None,
            "declared_date":    None,
            "amount_per_share": round(use_amount, 6),
            "unadjusted_value": round(amount, 6) if amount else None,
            "currency":         currency,
            "dividend_type":    "Cash Dividend",
        })

        # Sum into annual DPS (use unadjusted value = what shareholders actually received)
        fy = ex_date.year
        dps_by_fy[fy] = round((dps_by_fy.get(fy) or 0) + use_amount, 6)

    return rows, dps_by_fy


def upsert_dividends(cur, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO market.dividends
            (asx_code, ex_date, pay_date, record_date, declared_date,
             amount_per_share, unadjusted_value, currency, dividend_type)
        VALUES %s
        ON CONFLICT (asx_code, ex_date, dividend_type) DO UPDATE SET
            amount_per_share = EXCLUDED.amount_per_share,
            unadjusted_value = EXCLUDED.unadjusted_value,
            currency         = EXCLUDED.currency
    """
    vals = [(r["asx_code"], r["ex_date"], r["pay_date"], r["record_date"],
             r["declared_date"], r["amount_per_share"], r["unadjusted_value"],
             r["currency"], r["dividend_type"]) for r in rows]
    execute_values(cur, sql, vals, page_size=500)
    return len(rows)


def update_annual_dps(cur, asx_code: str, dps_by_fy: dict):
    for fy, dps in dps_by_fy.items():
        cur.execute("""
            UPDATE financials.annual_pnl
            SET dps = %s
            WHERE asx_code = %s AND fiscal_year = %s
        """, (dps, asx_code, fy))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes",     nargs="+")
    parser.add_argument("--from-code")
    parser.add_argument("--limit",     type=int)
    args = parser.parse_args()

    if not DIV_DIR.exists():
        print(f"ERROR: {DIV_DIR} not found.")
        print("Run download_historical_dividends.py first.")
        sys.exit(1)

    if args.codes:
        files = [DIV_DIR / f"{c.upper()}.json.gz" for c in args.codes
                 if (DIV_DIR / f"{c.upper()}.json.gz").exists()]
    else:
        files = sorted(DIV_DIR.glob("*.json.gz"))

    if args.from_code:
        files = [f for f in files if f.name >= f"{args.from_code.upper()}.json.gz"]
    if args.limit:
        files = files[:args.limit]

    total = len(files)
    log.info(f"Loading dividends from {DIV_DIR} — {total} files")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    done = failed = total_rows = stocks_with_divs = 0

    for i, path in enumerate(files, 1):
        code = path.name[:-len(".json.gz")]
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list) or not data:
                done += 1
                continue

            rows, dps_by_fy = parse_dividend_file(code, data)

            if rows:
                n = upsert_dividends(cur, rows)
                update_annual_dps(cur, code, dps_by_fy)
                total_rows += n
                stocks_with_divs += 1

            done += 1

        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {code}: {e}")
            continue

        if i % BATCH_COMMIT == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}] {stocks_with_divs} with divs | "
                     f"{total_rows:,} rows | {failed} errors")

    conn.commit()
    cur.close()
    conn.close()

    log.info(f"DONE — {stocks_with_divs} stocks have dividends | "
             f"{total_rows:,} rows upserted | {failed} errors")


if __name__ == "__main__":
    main()
