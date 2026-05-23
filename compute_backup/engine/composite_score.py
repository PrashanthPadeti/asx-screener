"""
ASX Screener — Composite Factor Score Engine
=============================================
Computes 5-factor percentile-rank scores (0–100) for every stock in
screener.universe, then writes them back to the same table.

Factors:
  value_score    — low PE/PB/EV·EBITDA, high FCF yield
  quality_score  — high Piotroski, ROE, ROCE, low D/E
  growth_score   — revenue/EPS growth, HoH acceleration
  momentum_score — price returns (1M, 3M, 6M), trend confirmation
  income_score   — grossed-up yield, franking %, consecutive years

composite_score = equal-weight average of all 5 non-null factors (0–100).

Percentile rank: higher value = better rank (i.e., for PE: lower PE → higher score).

Run after build_screener_universe.py completes.

Usage:
    python compute/engine/composite_score.py
    python compute/engine/composite_score.py --dry-run
"""

import argparse
import logging
import os
from typing import Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv

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

_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values, "DEC2FLOAT",
    lambda v, c: float(v) if v is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)


# ── Factor definitions ────────────────────────────────────────────────────────
# Each factor is a list of (column_name, direction) tuples.
# direction = +1: higher raw value → higher score (e.g. ROE)
# direction = -1: lower raw value  → higher score (e.g. PE ratio)
#
# Multiple signals per factor are each ranked 0-100 then averaged.

FACTOR_SIGNALS: dict[str, list[tuple[str, int]]] = {
    "value": [
        ("pe_ratio",       -1),   # lower PE  = better value
        ("price_to_book",  -1),   # lower PB
        ("ev_to_ebitda",   -1),   # lower EV/EBITDA
        ("fcf_yield",      +1),   # higher FCF yield = better value
        ("price_to_sales", -1),   # lower P/S
    ],
    "quality": [
        ("piotroski_f_score",  +1),   # higher = healthier
        ("roe",                +1),   # higher ROE
        ("roce",               +1),   # higher ROCE
        ("altman_z_score",     +1),   # higher Z = less distress
        ("debt_to_equity",     -1),   # lower leverage (null-safe: high D/E = low score)
        ("net_margin",         +1),
    ],
    "growth": [
        ("revenue_growth_1y",      +1),
        ("earnings_growth_1y",     +1),
        ("eps_growth_3y_cagr",     +1),
        ("revenue_growth_hoh",     +1),
        ("eps_growth_hoh",         +1),
        ("revenue_cagr_5y",        +1),
    ],
    "momentum": [
        ("return_1m",   +1),
        ("return_3m",   +1),
        ("return_6m",   +1),
        ("rsi_14",      +1),   # trending stocks have higher RSI
        ("adx_14",      +1),   # trending strength
    ],
    "income": [
        ("grossed_up_yield",        +1),
        ("dividend_yield",          +1),
        ("franking_pct",            +1),
        ("dividend_consecutive_yrs",+1),
        ("dividend_cagr_3y",        +1),
        ("payout_ratio",            -1),   # lower payout = more sustainable
    ],
}

# Columns to pull from screener.universe
ALL_COLS = ["asx_code"] + sorted({
    col
    for signals in FACTOR_SIGNALS.values()
    for col, _ in signals
})


def pct_rank(series: pd.Series, direction: int) -> pd.Series:
    """
    Percentile rank a series 0–100.
    direction=+1: higher raw value → higher rank.
    direction=-1: lower raw value  → higher rank.
    NaN values stay NaN (excluded from factor average).
    """
    s = series if direction == 1 else -series
    # rank(pct=True) gives 0–1 excluding NaN
    return s.rank(method="average", pct=True, na_option="keep") * 100


def compute_factor(df: pd.DataFrame, factor_name: str) -> pd.Series:
    """Compute one factor score as the mean percentile rank of its signals."""
    signals = FACTOR_SIGNALS[factor_name]
    ranks = []
    for col, direction in signals:
        if col not in df.columns:
            continue
        r = pct_rank(df[col], direction)
        # Clamp edge values
        r = r.clip(0, 100)
        ranks.append(r)

    if not ranks:
        return pd.Series(np.nan, index=df.index)

    # Stack and take row-wise mean (ignoring NaN)
    stacked = pd.concat(ranks, axis=1)
    return stacked.mean(axis=1, skipna=True).round(0).clip(0, 100)


def compute_composite(df_scores: pd.DataFrame) -> pd.Series:
    """Equal-weight composite of the 5 factor scores; requires >= 2 non-null factors."""
    score_cols = ["value_score", "quality_score", "growth_score", "momentum_score", "income_score"]
    available = [c for c in score_cols if c in df_scores.columns]
    stacked = df_scores[available]
    # Require at least 2 valid factors to produce a composite
    composite = stacked.mean(axis=1, skipna=True).round(0).clip(0, 100)
    # Null out stocks with fewer than 2 valid factor scores
    valid_count = stacked.notna().sum(axis=1)
    composite = composite.where(valid_count >= 2)
    return composite


def run(conn, dry_run: bool = False) -> int:
    """Load universe, compute scores, upsert. Returns number of rows updated."""
    log.info("Loading screener.universe for scoring…")

    cur = conn.cursor()
    col_list = ", ".join(ALL_COLS)
    cur.execute(f"""
        SELECT {col_list}
        FROM screener.universe
        WHERE status = 'active'
          AND price IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()

    if not rows:
        log.error("No active rows in screener.universe")
        return 0

    df = pd.DataFrame(rows, columns=ALL_COLS)
    log.info(f"  Loaded {len(df):,} stocks")

    # Coerce numerics
    for col in ALL_COLS[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Filter obviously bad values ───────────────────────────────────────────
    # PE < 0 or > 500 → exclude from value ranking (distorts percentiles)
    df.loc[df["pe_ratio"] < 0,   "pe_ratio"]  = np.nan
    df.loc[df["pe_ratio"] > 500, "pe_ratio"]  = np.nan
    df.loc[df["debt_to_equity"] < 0, "debt_to_equity"] = np.nan

    # ── Compute factor scores ─────────────────────────────────────────────────
    df["value_score"]    = compute_factor(df, "value")
    df["quality_score"]  = compute_factor(df, "quality")
    df["growth_score"]   = compute_factor(df, "growth")
    df["momentum_score"] = compute_factor(df, "momentum")
    df["income_score"]   = compute_factor(df, "income")
    df["composite_score"]= compute_composite(df)

    # Convert float scores → nullable int (NaN → None)
    score_cols = ["value_score", "quality_score", "growth_score",
                  "momentum_score", "income_score", "composite_score"]
    for col in score_cols:
        df[col] = df[col].where(df[col].notna(), other=None)

    log.info("  Scores computed. Sample composite scores (top 10):")
    top = df.nlargest(10, "composite_score", keep="all")[["asx_code", "composite_score"]]
    for _, r in top.iterrows():
        log.info(f"    {r['asx_code']:6s}  {r['composite_score']}")

    if dry_run:
        log.info("Dry-run mode — skipping DB write.")
        return len(df)

    # ── Upsert scores back to screener.universe ───────────────────────────────
    UPDATE_SQL = """
        UPDATE screener.universe
        SET
            value_score    = data.value_score,
            quality_score  = data.quality_score,
            growth_score   = data.growth_score,
            momentum_score = data.momentum_score,
            income_score   = data.income_score,
            composite_score= data.composite_score
        FROM (VALUES %s) AS data(
            asx_code, value_score, quality_score,
            growth_score, momentum_score, income_score, composite_score
        )
        WHERE screener.universe.asx_code = data.asx_code
    """

    update_rows = [
        (
            row["asx_code"],
            _to_smallint(row["value_score"]),
            _to_smallint(row["quality_score"]),
            _to_smallint(row["growth_score"]),
            _to_smallint(row["momentum_score"]),
            _to_smallint(row["income_score"]),
            _to_smallint(row["composite_score"]),
        )
        for _, row in df.iterrows()
    ]

    cur = conn.cursor()
    execute_values(
        cur, UPDATE_SQL, update_rows,
        template="(%s, %s::SMALLINT, %s::SMALLINT, %s::SMALLINT, %s::SMALLINT, %s::SMALLINT, %s::SMALLINT)",
        page_size=500,
    )
    conn.commit()
    cur.close()

    log.info(f"  ✓ {len(update_rows):,} rows updated in screener.universe")
    return len(update_rows)


def _to_smallint(v) -> Optional[int]:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return int(round(v))


def main():
    parser = argparse.ArgumentParser(description="Compute composite factor scores")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute scores without writing to DB")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    try:
        n = run(conn, dry_run=args.dry_run)
    finally:
        conn.close()

    log.info(f"Composite score engine complete — {n} stocks processed.")


if __name__ == "__main__":
    main()
