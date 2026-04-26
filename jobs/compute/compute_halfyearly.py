"""
ASX Screener — Compute Half-Yearly Metrics (Seq 3)
===================================================
Reads half-year P&L from financials.half_year_pnl and computes:
  - HoH growth (vs prior half)
  - YoY growth (vs same half prior year)
  - Margin ratios per half

ASX companies report half-yearly results (1H and 2H).
EODHD provides this as quarterly data — we aggregate Q1+Q2=1H, Q3+Q4=2H.

Usage:
    python jobs/compute/compute_halfyearly.py
    python jobs/compute/compute_halfyearly.py --codes BHP CBA
    python jobs/compute/compute_halfyearly.py --mode historical
"""

import os
import sys
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
COMPUTE_VERSION = "halfyearly_v1.0"
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


def compute_halfyearly(asx_code: str, rows: list[dict]) -> list[dict]:
    """
    Compute growth rates for each half-year record.
    Rows are sorted descending by period_end_date.
    """
    # Build lookup: (fiscal_year, half) → row
    by_key = {}
    for r in rows:
        fy   = r.get("fiscal_year") or _infer_fy(r["period_label"])
        half = r.get("period_label", "").startswith("1H") and 1 or 2
        if "1H" in (r.get("period_label") or ""):
            half = 1
        elif "2H" in (r.get("period_label") or ""):
            half = 2
        else:
            continue
        by_key[(fy, half)] = r

    results = []
    for (fy, half), r in by_key.items():
        rev     = r.get("revenue")
        ebit    = r.get("ebit")
        ebitda  = r.get("ebitda")
        pat     = r.get("net_profit")
        gp      = r.get("gross_profit")
        eps     = r.get("eps")
        dps_v   = r.get("dps")
        frank   = r.get("dps_franking_pct") or 0
        dep     = r.get("depreciation")
        int_exp = r.get("interest_expense")
        tax     = r.get("tax")

        # Margins
        gm      = safe_pct(gp,    rev)
        ebit_m  = safe_pct(ebit,  rev)
        npm     = safe_pct(pat,   rev)

        # HoH growth: compare with previous half
        prev_half = (fy, 1) if half == 2 else (fy - 1, 2)
        ph = by_key.get(prev_half, {})

        rev_hoh = yoy_growth(rev, ph.get("revenue"))
        pat_hoh = yoy_growth(pat, ph.get("net_profit"))
        eps_hoh = yoy_growth(eps, ph.get("eps"))

        # YoY growth: compare with same half prior year
        same_prior = (fy - 1, half)
        sp = by_key.get(same_prior, {})

        rev_yoy = yoy_growth(rev, sp.get("revenue"))
        pat_yoy = yoy_growth(pat, sp.get("net_profit"))
        eps_yoy = yoy_growth(eps, sp.get("eps"))

        results.append({
            "asx_code":             asx_code,
            "period_end_date":      r["period_end_date"],
            "fiscal_year":          fy,
            "half":                 half,
            "period_label":         r.get("period_label"),
            "revenue":              rev,
            "gross_profit":         gp,
            "ebitda":               ebitda,
            "ebit":                 ebit,
            "net_income":           pat,
            "other_income":         r.get("other_income"),
            "interest_expense":     int_exp,
            "tax":                  tax,
            "depreciation":         dep,
            "eps":                  eps,
            "dps":                  dps_v,
            "franking_pct":         frank,
            "gross_margin":         gm,
            "ebit_margin":          ebit_m,
            "net_margin":           npm,
            "revenue_growth_hoh":   rev_hoh,
            "revenue_growth_yoy":   rev_yoy,
            "net_income_growth_hoh": pat_hoh,
            "net_income_growth_yoy": pat_yoy,
            "eps_growth_hoh":       eps_hoh,
            "eps_growth_yoy":       eps_yoy,
            "compute_version":      COMPUTE_VERSION,
            "computed_at":          datetime.utcnow(),
        })

    return results


def _infer_fy(label: str) -> int:
    """Extract fiscal year from label like '1H FY2024' → 2024."""
    import re
    m = re.search(r"FY(\d{4})", label or "")
    return int(m.group(1)) if m else 0


def upsert_halfyearly(cur, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    vals = [[r.get(c) for c in cols] for r in rows]
    upd  = ", ".join([f"{c} = EXCLUDED.{c}"
                      for c in cols if c not in ("asx_code", "period_end_date")])
    sql  = f"""
        INSERT INTO market.halfyearly_metrics ({', '.join(cols)})
        VALUES %s
        ON CONFLICT (asx_code, period_end_date) DO UPDATE SET {upd}
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
            SELECT DISTINCT asx_code FROM financials.half_year_pnl
            ORDER BY asx_code
        """)
        codes = [r["asx_code"] for r in cur.fetchall()]

    total = len(codes)
    log.info(f"compute_halfyearly.py — {total} stocks")

    done = failed = rows_written = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            limit = "" if args.mode == "historical" else "LIMIT 4"
            cur.execute(f"""
                SELECT * FROM financials.half_year_pnl
                WHERE asx_code = %s
                ORDER BY period_end_date DESC {limit}
            """, (asx_code,))
            rows = cur.fetchall()
            if not rows:
                failed += 1
                continue

            computed = compute_halfyearly(asx_code, rows)
            if computed:
                upsert_halfyearly(cur, computed)
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
