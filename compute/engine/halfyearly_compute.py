"""
ASX Screener — Half-Yearly Compute Engine
==========================================
Derives half-yearly metrics by aggregating quarterly data already loaded
into market.quarterly_metrics.

ASX companies report half-yearly (1H and 2H each fiscal year).
EODHD stores this as quarterly rows. Two reporting patterns handled:

  Quarterly reporters  (Q1–Q4 per FY):  Q1+Q2 → H1,  Q3+Q4 → H2
  Half-yearly reporters (Q1–Q2 per FY):  Q1    → H1,  Q2    → H2

Aggregation rules:
  Income items  (revenue, ebitda, …)   →  SUM of constituent quarters
  Per-share     (eps)                  →  SUM of constituent quarters
  Margins                              →  recomputed from aggregated income
  period_end_date                      →  MAX(period_end_date) of constituent quarters

Growth rates (stored as decimal ratios, e.g. 0.15 = 15%):
  HoH  — vs immediately prior half  (2H → 1H,  1H → prior 2H)
  YoY  — vs same half one year prior (1H FY25 → 1H FY24)

Usage:
    python compute/engine/halfyearly_compute.py
    python compute/engine/halfyearly_compute.py --codes BHP CBA ANZ
    python compute/engine/halfyearly_compute.py --limit 50
    python compute/engine/halfyearly_compute.py --min-year 2020
"""

import os
import logging
import argparse
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# Cast NUMERIC → float automatically
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

def _f(val) -> Optional[float]:
    """Convert to float; return None for NaN/inf/None."""
    if val is None:
        return None
    try:
        v = float(val)
        return None if (np.isnan(v) or np.isinf(v)) else v
    except Exception:
        return None


def _sum(*vals) -> Optional[float]:
    """Sum non-None values; return None if ALL are None."""
    floats = [_f(v) for v in vals if v is not None]
    non_null = [v for v in floats if v is not None]
    return round(sum(non_null), 6) if non_null else None


def _div(num, den, dp: int = 6, max_abs: float = 9_999.0) -> Optional[float]:
    """Safe division; returns None on zero/None/inf or if |result| > max_abs."""
    n, d = _f(num), _f(den)
    if n is None or d is None or d == 0:
        return None
    result = n / d
    if np.isnan(result) or np.isinf(result):
        return None
    if abs(result) > max_abs:
        return None
    return round(result, dp)


def _pct_change(new_val, old_val) -> Optional[float]:
    """(new - old) / |old| as decimal ratio. Returns None for zero/None denominators.
    Clamped to ±9.99 (±999%) to suppress near-zero base outliers in screener."""
    n, o = _f(new_val), _f(old_val)
    if n is None or o is None or o == 0:
        return None
    result = (n - o) / abs(o)
    if np.isnan(result) or np.isinf(result):
        return None
    # Cap at ±999% — ratios beyond this are near-zero base artefacts, not signals
    return round(result, 6) if abs(result) <= 9.99 else None


def _v(val):
    """Return None for NaN/inf; convert numpy types to Python."""
    if val is None:
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        return None if (np.isnan(val) or np.isinf(val)) else float(val)
    return val


# ── Data Fetching ─────────────────────────────────────────────────────────────

def fetch_codes(cur, codes=None, limit=None) -> list[str]:
    if codes:
        return [c.upper() for c in codes]
    sql = """
        SELECT DISTINCT asx_code
        FROM market.quarterly_metrics
        WHERE revenue IS NOT NULL
        ORDER BY asx_code
    """
    if limit:
        sql += f" LIMIT {limit}"
    cur.execute(sql)
    return [r[0] for r in cur.fetchall()]


def fetch_quarterly(cur, asx_code: str) -> pd.DataFrame:
    """Fetch all quarterly rows chronologically for a stock."""
    cur.execute("""
        SELECT
            fiscal_year, quarter, period_end_date,
            revenue, gross_profit, ebitda, ebit,
            other_income, interest_expense, depreciation, tax,
            net_income, eps
        FROM market.quarterly_metrics
        WHERE asx_code = %s
          AND fiscal_year IS NOT NULL
          AND quarter IS NOT NULL
        ORDER BY fiscal_year ASC, quarter ASC
    """, [asx_code])

    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame()

    cols = [
        "fiscal_year", "quarter", "period_end_date",
        "revenue", "gross_profit", "ebitda", "ebit",
        "other_income", "interest_expense", "depreciation", "tax",
        "net_income", "eps",
    ]
    return pd.DataFrame(rows, columns=cols)


# ── Aggregation ───────────────────────────────────────────────────────────────

_INCOME_COLS = [
    "revenue", "gross_profit", "ebitda", "ebit",
    "other_income", "interest_expense", "depreciation", "tax",
    "net_income", "eps",
]


def _agg_halves(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate quarters into half-yearly rows.

    Quarterly reporters  (4 qtrs/FY):  Q1+Q2 → H1 (half=1),  Q3+Q4 → H2 (half=2)
    Half-yearly reporters (2 qtrs/FY):  Q1    → H1,            Q2    → H2
    Mixed years handled independently.

    Returns a DataFrame with columns:
        fiscal_year, half, period_end_date, revenue, ..., eps
    """
    halves = []

    for fy, fy_df in df.groupby("fiscal_year"):
        fy_df = fy_df.sort_values("quarter").reset_index(drop=True)
        qtrs  = sorted(fy_df["quarter"].tolist())
        n_qtrs = len(qtrs)

        if n_qtrs == 0:
            continue
        elif n_qtrs <= 2:
            # Half-yearly reporter: Q1=H1, Q2=H2 (or only Q1 available)
            for q_idx, half in enumerate([1, 2], start=0):
                if q_idx >= len(fy_df):
                    break
                row = fy_df.iloc[q_idx]
                h = {
                    "fiscal_year":    int(fy),
                    "half":           half,
                    "period_end_date": row["period_end_date"],
                }
                for c in _INCOME_COLS:
                    h[c] = _f(row.get(c))
                halves.append(h)
        else:
            # Quarterly reporter: Q1+Q2=H1, Q3+Q4=H2
            for half, q_list in [(1, [1, 2]), (2, [3, 4])]:
                subset = fy_df[fy_df["quarter"].isin(q_list)]
                if subset.empty:
                    continue
                h = {
                    "fiscal_year":    int(fy),
                    "half":           half,
                    "period_end_date": subset["period_end_date"].max(),
                }
                for c in _INCOME_COLS:
                    h[c] = _sum(*subset[c].tolist())
                halves.append(h)

    if not halves:
        return pd.DataFrame()

    result = pd.DataFrame(halves)
    result = result.sort_values(["fiscal_year", "half"]).reset_index(drop=True)
    return result


# ── Compute Metrics ───────────────────────────────────────────────────────────

def compute_halfyearly(asx_code: str, df: pd.DataFrame) -> list[tuple]:
    """
    Given the aggregated half-year DataFrame, compute margins and growth rates.
    Returns list of tuples matching UPSERT_COLS order.
    """
    if df.empty:
        return []

    n = len(df)
    rows = []
    now  = datetime.now(tz=timezone.utc)

    for i in range(n):
        r   = df.iloc[i]
        fy  = int(r["fiscal_year"])
        half = int(r["half"])

        rev   = _f(r["revenue"])
        gp    = _f(r["gross_profit"])
        ebitda= _f(r["ebitda"])
        ebit  = _f(r["ebit"])
        ni    = _f(r["net_income"])
        eps   = _f(r["eps"])
        oi    = _f(r["other_income"])
        ie    = _f(r["interest_expense"])
        dep   = _f(r["depreciation"])
        tax   = _f(r["tax"])

        # Margins (decimal ratios)
        gm   = _div(gp,   rev)
        em   = _div(ebit, rev)
        npm  = _div(ni,   rev)

        # ── HoH growth: current vs immediately prior half ─────────────────────
        # H2 → H1 of same FY;  H1 → H2 of (FY-1)
        if half == 2:
            prev_hoh = df[(df["fiscal_year"] == fy) & (df["half"] == 1)]
        else:
            prev_hoh = df[(df["fiscal_year"] == fy - 1) & (df["half"] == 2)]

        if not prev_hoh.empty:
            ph = prev_hoh.iloc[0]
            rev_hoh = _pct_change(rev, _f(ph["revenue"]))
            ni_hoh  = _pct_change(ni,  _f(ph["net_income"]))
            eps_hoh = _pct_change(eps, _f(ph["eps"]))
        else:
            rev_hoh = ni_hoh = eps_hoh = None

        # ── YoY growth: same half, prior FY ──────────────────────────────────
        prev_yoy = df[(df["fiscal_year"] == fy - 1) & (df["half"] == half)]

        if not prev_yoy.empty:
            py = prev_yoy.iloc[0]
            rev_yoy = _pct_change(rev, _f(py["revenue"]))
            ni_yoy  = _pct_change(ni,  _f(py["net_income"]))
            eps_yoy = _pct_change(eps, _f(py["eps"]))
        else:
            rev_yoy = ni_yoy = eps_yoy = None

        # period_label e.g. "1H FY2024"
        label = f"{'1H' if half == 1 else '2H'} FY{fy}"
        ped   = r["period_end_date"]

        rows.append((
            asx_code,
            ped,
            fy,
            half,
            label,
            rev,   gp,    ebitda, ebit, ni,
            oi,    ie,    tax,    dep,
            eps,
            # No DPS in quarterly_metrics — leave NULL
            None,  # dps
            None,  # franking_pct
            gm,    em,    npm,
            rev_hoh, rev_yoy,
            ni_hoh,  ni_yoy,
            eps_hoh, eps_yoy,
            COMPUTE_VERSION,
            now,
        ))

    return rows


# ── Database Write ────────────────────────────────────────────────────────────

UPSERT_COLS = [
    "asx_code", "period_end_date",
    "fiscal_year", "half", "period_label",
    # Income
    "revenue", "gross_profit", "ebitda", "ebit", "net_income",
    "other_income", "interest_expense", "tax", "depreciation",
    # Per share
    "eps", "dps", "franking_pct",
    # Margins
    "gross_margin", "ebit_margin", "net_margin",
    # Growth
    "revenue_growth_hoh", "revenue_growth_yoy",
    "net_income_growth_hoh", "net_income_growth_yoy",
    "eps_growth_hoh", "eps_growth_yoy",
    # Meta
    "compute_version", "computed_at",
]

UPSERT_SQL = f"""
    INSERT INTO market.halfyearly_metrics ({', '.join(UPSERT_COLS)})
    VALUES %s
    ON CONFLICT (asx_code, period_end_date) DO UPDATE SET
        {', '.join(f"{c} = EXCLUDED.{c}" for c in UPSERT_COLS
                   if c not in ("asx_code", "period_end_date"))}
"""


def upsert_rows(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    execute_values(cur, UPSERT_SQL, rows, page_size=500)
    return len(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASX Half-Yearly Compute Engine")
    parser.add_argument("--codes",    nargs="+", help="Specific ASX codes")
    parser.add_argument("--limit",    type=int,  help="Max stocks to process")
    parser.add_argument("--min-year", type=int,  help="Only upsert rows for fiscal_year >= N")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    codes = fetch_codes(cur, args.codes, args.limit)
    total = len(codes)
    log.info(f"Half-yearly compute — {total} stocks"
             + (f" | min-year {args.min_year}" if args.min_year else " (all years)"))
    log.info("─" * 60)

    processed = skipped = errors = total_rows = 0

    for i, asx_code in enumerate(codes, 1):
        try:
            qdf = fetch_quarterly(cur, asx_code)
            if qdf.empty:
                skipped += 1
                continue

            hdf = _agg_halves(qdf)
            if hdf.empty:
                skipped += 1
                continue

            rows = compute_halfyearly(asx_code, hdf)
            if not rows:
                skipped += 1
                continue

            # Apply min-year filter
            if args.min_year:
                rows = [r for r in rows if r[2] >= args.min_year]  # r[2] = fiscal_year
            if not rows:
                skipped += 1
                continue

            upsert_rows(cur, rows)
            total_rows += len(rows)
            processed  += 1

            if i % BATCH_COMMIT == 0:
                conn.commit()
                log.info(f"  [{i:4d}/{total}] {processed} done | "
                         f"{skipped} skipped | {errors} errors | "
                         f"{total_rows:,} rows so far")

        except Exception as e:
            errors += 1
            log.warning(f"  {asx_code}: {e}", exc_info=(errors <= 3))
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    log.info("─" * 60)
    log.info(f"Done! {processed} stocks | {skipped} skipped | "
             f"{errors} errors | {total_rows:,} rows upserted")


if __name__ == "__main__":
    main()
