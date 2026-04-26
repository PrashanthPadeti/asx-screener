"""
ASX Screener — Compute Quarterly Metrics (Seq 4)
=================================================
Reads quarterly financial data from EODHD (stored in financials.annual_pnl
quarterly fields or via a dedicated quarterly source) and computes:
  - QoQ growth (vs previous quarter)
  - YoY quarterly growth (vs same quarter prior year)
  - Margin ratios per quarter

EODHD provides quarterly P&L for most ASX companies even though ASX
only mandates half-yearly reporting. Data quality varies by stock.

Usage:
    python jobs/compute/compute_quarterly.py
    python jobs/compute/compute_quarterly.py --codes BHP CBA
    python jobs/compute/compute_quarterly.py --mode historical
"""

import os
import time
import logging
import argparse
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_URL          = os.getenv("DATABASE_URL_SYNC",
                    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener")
COMPUTE_VERSION = "quarterly_v1.0"
SLEEP_SEC       = 0.02

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def safe_pct(num, denom):
    if num is None or denom is None or denom == 0:
        return None
    v = num / denom * 100
    return round(v, 4) if abs(v) < 99999 else None


def yoy_growth(curr, prev):
    if curr is None or prev is None or prev == 0:
        return None
    return round((curr - prev) / abs(prev) * 100, 4)


def fetch_quarterly_raw(cur, asx_code: str, mode: str) -> list[dict]:
    """
    Fetch quarterly data from EODHD-loaded table.
    EODHD stores quarterly financials in financials.annual_pnl with
    a quarterly flag, OR in a separate quarterly table if we add one.
    For now we read from the quarterly section of the fundamentals
    (loaded by load_eodhd_financials.py into a dedicated quarterly store).

    If no dedicated quarterly table exists yet, returns empty list —
    compute_quarterly will skip gracefully.
    """
    try:
        limit = "" if mode == "historical" else "LIMIT 8"
        cur.execute(f"""
            SELECT
                asx_code,
                fiscal_year,
                quarter,
                period_end_date,
                period_label,
                revenue,
                gross_profit,
                ebitda,
                ebit,
                other_income,
                interest_expense,
                depreciation,
                tax,
                net_income,
                extraordinary_items,
                equity_capital,
                eps
            FROM market.quarterly_metrics
            WHERE asx_code = %s
            ORDER BY fiscal_year DESC, quarter DESC {limit}
        """, (asx_code,))
        return cur.fetchall()
    except psycopg2.errors.UndefinedTable:
        return []


def compute_quarterly(asx_code: str, rows: list[dict]) -> list[dict]:
    """Compute QoQ and YoY growth rates for each quarterly record."""
    if not rows:
        return []

    # Index by (fiscal_year, quarter)
    by_key = {(r["fiscal_year"], r["quarter"]): r for r in rows}

    results = []
    for (fy, q), r in by_key.items():
        rev    = r.get("revenue")
        ebit   = r.get("ebit")
        ebitda = r.get("ebitda")
        gp     = r.get("gross_profit")
        pat    = r.get("net_income")
        eps    = r.get("eps")

        # Margins
        gm     = safe_pct(gp,   rev)
        ebit_m = safe_pct(ebit, rev)
        npm    = safe_pct(pat,  rev)

        # QoQ: vs previous quarter
        prev_q = (fy, q - 1) if q > 1 else (fy - 1, 4)
        pq = by_key.get(prev_q, {})
        rev_qoq = yoy_growth(rev,  pq.get("revenue"))
        pat_qoq = yoy_growth(pat,  pq.get("net_income"))
        ebt_qoq = yoy_growth(ebit, pq.get("ebit"))

        # YoY: vs same quarter prior year
        py = by_key.get((fy - 1, q), {})
        rev_yoy = yoy_growth(rev,  py.get("revenue"))
        pat_yoy = yoy_growth(pat,  py.get("net_income"))
        ebt_yoy = yoy_growth(ebit, py.get("ebit"))
        eps_yoy = yoy_growth(eps,  py.get("eps"))

        results.append({
            "asx_code":             asx_code,
            "fiscal_year":          fy,
            "quarter":              q,
            "period_end_date":      r.get("period_end_date"),
            "period_label":         r.get("period_label"),
            "revenue":              rev,
            "gross_profit":         gp,
            "ebitda":               ebitda,
            "ebit":                 ebit,
            "other_income":         r.get("other_income"),
            "interest_expense":     r.get("interest_expense"),
            "depreciation":         r.get("depreciation"),
            "tax":                  r.get("tax"),
            "net_income":           pat,
            "extraordinary_items":  r.get("extraordinary_items"),
            "equity_capital":       r.get("equity_capital"),
            "eps":                  eps,
            "gross_margin":         gm,
            "ebit_margin":          ebit_m,
            "net_margin":           npm,
            "revenue_growth_qoq":   rev_qoq,
            "net_income_growth_qoq": pat_qoq,
            "ebit_growth_qoq":      ebt_qoq,
            "revenue_growth_yoy":   rev_yoy,
            "net_income_growth_yoy": pat_yoy,
            "ebit_growth_yoy":      ebt_yoy,
            "eps_growth_yoy":       eps_yoy,
            "compute_version":      COMPUTE_VERSION,
            "computed_at":          datetime.utcnow(),
        })

    return results


def upsert_quarterly(cur, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    vals = [[r.get(c) for c in cols] for r in rows]
    upd  = ", ".join([f"{c} = EXCLUDED.{c}"
                      for c in cols if c not in ("asx_code", "fiscal_year", "quarter")])
    sql  = f"""
        INSERT INTO market.quarterly_metrics ({', '.join(cols)})
        VALUES %s
        ON CONFLICT (asx_code, fiscal_year, quarter) DO UPDATE SET {upd}
    """
    execute_values(cur, sql, vals, page_size=500)
    return len(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+")
    parser.add_argument("--mode",  choices=["latest", "historical"], default="latest")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    if args.codes:
        codes = [c.upper() for c in args.codes]
    else:
        cur.execute("""
            SELECT DISTINCT asx_code FROM market.quarterly_metrics
            ORDER BY asx_code
        """)
        codes = [r["asx_code"] for r in cur.fetchall()]

    total = len(codes)
    log.info(f"compute_quarterly.py — {total} stocks, mode={args.mode}")

    done = failed = rows_written = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            rows = fetch_quarterly_raw(cur, asx_code, args.mode)
            if not rows:
                failed += 1
                continue

            computed = compute_quarterly(asx_code, rows)
            if computed:
                upsert_quarterly(cur, computed)
                rows_written += len(computed)
                done += 1
            else:
                failed += 1

        except Exception as e:
            conn.rollback()
            failed += 1
            log.warning(f"  {asx_code}: {e}")
            continue

        if i % 200 == 0:
            conn.commit()
            log.info(f"  [{i:4d}/{total}] {done} done | {rows_written:,} rows")

        time.sleep(SLEEP_SEC)

    conn.commit()
    cur.close()
    conn.close()
    log.info(f"DONE — {done} stocks, {rows_written:,} rows. Failed: {failed}")


if __name__ == "__main__":
    main()
