"""
ASX Screener — Quarterly Compute Engine
=========================================
Computes QoQ and YoY growth rates for quarterly financials already loaded
into market.quarterly_metrics by the EODHD transform pipeline.

Source:  market.quarterly_metrics (raw income / margin columns already set)
Output:  market.quarterly_metrics (updates growth-rate columns in-place)

Growth rates computed per row:
  - revenue_growth_qoq      vs Q-1 (previous quarter)
  - net_income_growth_qoq   vs Q-1
  - ebit_growth_qoq         vs Q-1
  - revenue_growth_yoy      vs same quarter prior year
  - net_income_growth_yoy   vs same quarter prior year
  - ebit_growth_yoy         vs same quarter prior year
  - eps_growth_yoy          vs same quarter prior year

Also populates margin columns if NULL:
  - gross_margin   = gross_profit / revenue
  - ebit_margin    = ebit / revenue
  - net_margin     = net_income / revenue

Usage:
    python compute/engine/quarterly_compute.py
    python compute/engine/quarterly_compute.py --codes BHP CBA ANZ
    python compute/engine/quarterly_compute.py --limit 50
    python compute/engine/quarterly_compute.py --min-year 2022
"""

import os
import logging
import argparse
from datetime import datetime, timezone

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Cast PostgreSQL NUMERIC → Python float automatically
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

load_dotenv()

DB_URL = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql://asx_user:asx_secure_2024@localhost:5432/asx_screener"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

COMPUTE_VERSION = "1.0.0"
BATCH_COMMIT    = 50


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nan_to_none(val):
    if val is None:
        return None
    if isinstance(val, float) and np.isnan(val):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return None if np.isnan(val) else float(val)
    return val


def _pct_change(new_val, old_val) -> float | None:
    """(new - old) / |old| — handles sign changes gracefully."""
    try:
        if old_val is None or new_val is None:
            return None
        n, o = float(new_val), float(old_val)
        if o == 0 or np.isnan(o) or np.isnan(n):
            return None
        result = (n - o) / abs(o)
        return round(result, 6) if not np.isinf(result) else None
    except Exception:
        return None


def _safe_div(num, den, dp=4):
    try:
        if den is None or den == 0 or np.isnan(float(den)):
            return None
        result = float(num) / float(den)
        return round(result, dp) if not np.isnan(result) and not np.isinf(result) else None
    except Exception:
        return None


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def fetch_codes(cur, codes=None, limit=None):
    if codes:
        return [c.upper() for c in codes]
    sql = """
        SELECT DISTINCT asx_code
        FROM market.quarterly_metrics
        ORDER BY asx_code
    """
    if limit:
        sql += f" LIMIT {limit}"
    cur.execute(sql)
    return [r[0] for r in cur.fetchall()]


def fetch_quarterly_data(cur, asx_code: str) -> pd.DataFrame:
    """Fetch all quarterly rows for a stock, ordered chronologically."""
    cur.execute("""
        SELECT
            fiscal_year, quarter, period_end_date,
            revenue, gross_profit, ebit, net_income, eps,
            gross_margin, ebit_margin, net_margin,
            compute_version
        FROM market.quarterly_metrics
        WHERE asx_code = %s
        ORDER BY fiscal_year ASC, quarter ASC
    """, [asx_code])

    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    cols = [
        "fiscal_year", "quarter", "period_end_date",
        "revenue", "gross_profit", "ebit", "net_income", "eps",
        "gross_margin", "ebit_margin", "net_margin",
        "compute_version",
    ]
    df = pd.DataFrame(rows, columns=cols)
    return df


# ── Growth Rate Computation ───────────────────────────────────────────────────

def compute_growth_rates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add QoQ and YoY growth columns to a stock's quarterly DataFrame.
    Rows must be sorted ascending by (fiscal_year, quarter).
    """
    df = df.copy().reset_index(drop=True)
    n  = len(df)

    # Initialise growth columns
    for col in ["revenue_growth_qoq", "net_income_growth_qoq", "ebit_growth_qoq",
                "revenue_growth_yoy", "net_income_growth_yoy",
                "ebit_growth_yoy", "eps_growth_yoy"]:
        df[col] = None

    # Also fill missing margin columns
    for i in range(n):
        if df.at[i, "gross_margin"] is None and df.at[i, "revenue"] not in (None, 0):
            df.at[i, "gross_margin"] = _safe_div(df.at[i, "gross_profit"], df.at[i, "revenue"])
        if df.at[i, "ebit_margin"] is None and df.at[i, "revenue"] not in (None, 0):
            df.at[i, "ebit_margin"] = _safe_div(df.at[i, "ebit"], df.at[i, "revenue"])
        if df.at[i, "net_margin"] is None and df.at[i, "revenue"] not in (None, 0):
            df.at[i, "net_margin"] = _safe_div(df.at[i, "net_income"], df.at[i, "revenue"])

    for i in range(n):
        fy  = int(df.at[i, "fiscal_year"])
        qtr = int(df.at[i, "quarter"])

        # ── QoQ: find row with (fy, q-1) or (fy-1, q=4 if current q=1)
        if qtr > 1:
            prev_qoq_mask = (df["fiscal_year"] == fy) & (df["quarter"] == qtr - 1)
        else:
            prev_qoq_mask = (df["fiscal_year"] == fy - 1) & (df["quarter"] == 4)

        prev_qoq_rows = df[prev_qoq_mask]
        if not prev_qoq_rows.empty:
            prev = prev_qoq_rows.iloc[0]
            df.at[i, "revenue_growth_qoq"]    = _pct_change(df.at[i, "revenue"],    prev["revenue"])
            df.at[i, "net_income_growth_qoq"] = _pct_change(df.at[i, "net_income"], prev["net_income"])
            df.at[i, "ebit_growth_qoq"]       = _pct_change(df.at[i, "ebit"],       prev["ebit"])

        # ── YoY: same quarter, prior fiscal year
        prev_yoy_mask = (df["fiscal_year"] == fy - 1) & (df["quarter"] == qtr)
        prev_yoy_rows = df[prev_yoy_mask]
        if not prev_yoy_rows.empty:
            prev = prev_yoy_rows.iloc[0]
            df.at[i, "revenue_growth_yoy"]    = _pct_change(df.at[i, "revenue"],    prev["revenue"])
            df.at[i, "net_income_growth_yoy"] = _pct_change(df.at[i, "net_income"], prev["net_income"])
            df.at[i, "ebit_growth_yoy"]       = _pct_change(df.at[i, "ebit"],       prev["ebit"])
            df.at[i, "eps_growth_yoy"]        = _pct_change(df.at[i, "eps"],        prev["eps"])

    return df


# ── Database Write ────────────────────────────────────────────────────────────

UPDATE_SQL = """
    UPDATE market.quarterly_metrics SET
        gross_margin            = %(gross_margin)s,
        ebit_margin             = %(ebit_margin)s,
        net_margin              = %(net_margin)s,
        revenue_growth_qoq      = %(revenue_growth_qoq)s,
        net_income_growth_qoq   = %(net_income_growth_qoq)s,
        ebit_growth_qoq         = %(ebit_growth_qoq)s,
        revenue_growth_yoy      = %(revenue_growth_yoy)s,
        net_income_growth_yoy   = %(net_income_growth_yoy)s,
        ebit_growth_yoy         = %(ebit_growth_yoy)s,
        eps_growth_yoy          = %(eps_growth_yoy)s,
        compute_version         = %(compute_version)s,
        computed_at             = NOW()
    WHERE asx_code = %(asx_code)s
      AND fiscal_year = %(fiscal_year)s
      AND quarter     = %(quarter)s
"""


def update_rows(cur, asx_code: str, df: pd.DataFrame, min_year: int = None) -> int:
    """Execute UPDATE for each row in the computed DataFrame."""
    count = 0
    for _, row in df.iterrows():
        if min_year and int(row["fiscal_year"]) < min_year:
            continue

        cur.execute(UPDATE_SQL, {
            "asx_code":             asx_code,
            "fiscal_year":          int(row["fiscal_year"]),
            "quarter":              int(row["quarter"]),
            "gross_margin":         _nan_to_none(row["gross_margin"]),
            "ebit_margin":          _nan_to_none(row["ebit_margin"]),
            "net_margin":           _nan_to_none(row["net_margin"]),
            "revenue_growth_qoq":   _nan_to_none(row["revenue_growth_qoq"]),
            "net_income_growth_qoq":_nan_to_none(row["net_income_growth_qoq"]),
            "ebit_growth_qoq":      _nan_to_none(row["ebit_growth_qoq"]),
            "revenue_growth_yoy":   _nan_to_none(row["revenue_growth_yoy"]),
            "net_income_growth_yoy":_nan_to_none(row["net_income_growth_yoy"]),
            "ebit_growth_yoy":      _nan_to_none(row["ebit_growth_yoy"]),
            "eps_growth_yoy":       _nan_to_none(row["eps_growth_yoy"]),
            "compute_version":      COMPUTE_VERSION,
        })
        count += 1
    return count


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASX Quarterly Compute Engine")
    parser.add_argument("--codes",    nargs="+", help="Specific ASX codes")
    parser.add_argument("--limit",    type=int,  help="Max stocks to process")
    parser.add_argument("--min-year", type=int,  help="Only update rows for fiscal_year >= N")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    codes = fetch_codes(cur, args.codes, args.limit)
    total = len(codes)
    log.info(f"Quarterly compute — {total} stocks"
             + (f" | min-year {args.min_year}" if args.min_year else " (all years)"))
    log.info("─" * 60)

    processed = skipped = errors = total_rows = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            df = fetch_quarterly_data(cur, asx_code)
            if df.empty:
                skipped += 1
                continue

            df = compute_growth_rates(df)

            n = update_rows(cur, asx_code, df, args.min_year)
            if n == 0:
                skipped += 1
                continue

            total_rows += n
            processed  += 1

            if i % BATCH_COMMIT == 0:
                conn.commit()
                log.info(f"  [{i:4d}/{total}] {processed} done | "
                         f"{skipped} skipped | {errors} errors | "
                         f"{total_rows:,} rows so far")

        except Exception as e:
            errors += 1
            log.warning(f"  {asx_code}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} stocks | {skipped} skipped | "
             f"{errors} errors | {total_rows:,} rows updated")


if __name__ == "__main__":
    main()
