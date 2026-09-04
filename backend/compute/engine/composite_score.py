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

# Extra columns this engine needs beyond the five factor signals
MB_EXTRA_COLS = [
    "roic", "roce", "earnings_stability_score",
    "gross_margin_expanding", "operating_margin_expanding",
    "shares_dilution_3y", "percent_insiders",
    "gross_margin_expansion", "operating_margin_expansion",
    "revenue_growth_3y_cagr", "eps_growth_3y_cagr",
    "revenue_cagr_5y", "earnings_growth_3y_cagr",
]

# Columns to pull from screener.universe
ALL_COLS = ["asx_code"] + sorted(
    {col for signals in FACTOR_SIGNALS.values() for col, _ in signals}
    | set(MB_EXTRA_COLS)
)


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



# -- Multibagger potential (MULTIBAGGER_POTENTIAL_V1) -------------------------
# A CHARACTERISTICS score, not a return prediction. It measures how strongly a
# business currently exhibits traits associated with long-term compounders. It
# does not estimate whether the stock will return 2x, 5x or 10x, and every
# surface that exposes it must say so.
#
# Deliberate design choices:
#   * quality_score is NOT a component. It already blends Piotroski, ROE, ROCE,
#     margins and leverage, all of which appear here - including it would count
#     the same evidence twice.
#   * ROIC and ROCE form ONE component (60/40), not two, so capital efficiency
#     cannot pick up accidental double weighting.
#   * Momentum is capped at 10%. This identifies compounding businesses, not
#     stocks that have already run; an extraordinary company with temporarily
#     weak price action should still score well.
#   * Insider alignment is 5% and uses a saturating curve rather than a
#     percentile. Ownership varies with company maturity: 25% in a founder-led
#     small cap is excellent alignment, 2% in a mature company is not damning.
#   * Dilution is asymmetric - heavy issuance is punished hard, but buybacks
#     earn only a capped benefit, so this cannot become a buyback score.

MULTIBAGGER_VERSION = "MULTIBAGGER_POTENTIAL_V1"
# The ownership curve is versioned separately so it can be recalibrated
# without implying the whole composite changed definition.

MB_WEIGHTS: dict[str, float] = {
    "growth":             0.25,
    "capital_efficiency": 0.20,
    "earnings_stability": 0.15,
    "margin_expansion":   0.15,
    "dilution":           0.10,
    "momentum":           0.10,
    "insider_alignment":  0.05,
}

MB_MIN_VALID_WEIGHT = 0.70      # below this the score is not published

# yearly_compute stores earnings_stability_score as a 0-3 proxy. Keep the
# rescaling explicit so a future change to that range is a one-line edit.
EARNINGS_STABILITY_MAX = 3.0

MB_GROWTH_SIGNALS = [
    ("revenue_growth_3y_cagr",  +1),
    ("eps_growth_3y_cagr",      +1),
    ("revenue_cagr_5y",         +1),
    ("earnings_growth_3y_cagr", +1),
]


def _dilution_curve(d: float) -> float:
    """
    Share-count change over 3 years (percent; positive = dilution) -> 0-100.

    Asymmetric on purpose. Heavy issuance is a strong negative signal because it
    means growth was bought with shareholder money. Buybacks are mildly positive
    and capped, so a shrinking share count alone cannot carry the score.
    """
    if d >= 25:   return 0.0                       # heavy dilution
    if d >= 10:   return 40.0 * (25 - d) / 15      # 10-25%  -> 40..0
    if d >= 3:    return 40 + 35.0 * (10 - d) / 7  # 3-10%   -> 75..40
    if d >= 0:    return 75 + 15.0 * (3 - d) / 3   # 0-3%    -> 90..75
    if d >= -10:  return 90 + 10.0 * (-d) / 10     # buyback -> 90..100
    return 100.0                                   # capped


OWNERSHIP_ALIGNMENT_VERSION = "OWNERSHIP_ALIGNMENT_V1"

# Knee points for the ownership curve, interpolated linearly between them.
# The first calibration saturated at 25 percent, which put 1,079 of 1,657
# stocks on the ceiling at exactly 95 - effectively a constant, and therefore
# useless as a ranking signal. Observed mean ownership is 36 percent, so the
# knees were moved out to spread the component across the real distribution.
_OWNERSHIP_KNEES = [(0, 40.0), (10, 60.0), (30, 75.0), (60, 90.0), (85, 95.0)]


def _ownership_curve(pct: float) -> float:
    """
    Ownership concentration (percent of shares held per percent_insiders)
    -> 0-100, monotonic and saturating.

    Named "ownership alignment", not "insider alignment", deliberately. What
    EODHD encodes in this field is not established: ERA scores 98.7 on it, which
    is Rio Tinto's controlling parent stake, not directors buying shares. A
    controlling parent and a founder-operator are not the same economic signal,
    and until the dataset lets us separate founder, management, parent,
    institutional and government holdings, this is a proxy rather than a
    governance measure. It is held at 5 percent weight for that reason.
    """
    if pct <= _OWNERSHIP_KNEES[0][0]:
        return _OWNERSHIP_KNEES[0][1]
    for (x0, y0), (x1, y1) in zip(_OWNERSHIP_KNEES, _OWNERSHIP_KNEES[1:]):
        if pct <= x1:
            return y0 + (y1 - y0) * (pct - x0) / (x1 - x0)
    return _OWNERSHIP_KNEES[-1][1]


def compute_multibagger(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns the seven components, the valid-weight percentage and the composite
    score. Components are 0-100, NaN where the data is unusable.
    """
    out = pd.DataFrame(index=df.index)

    # Growth - mean percentile across whichever growth signals are present
    ranks = [pct_rank(df[c], d).clip(0, 100)
             for c, d in MB_GROWTH_SIGNALS if c in df.columns]
    out["growth"] = (pd.concat(ranks, axis=1).mean(axis=1, skipna=True)
                     if ranks else np.nan)

    # Capital efficiency - ONE component, ROIC 60 / ROCE 40, renormalised when
    # only one is present so a missing ROIC does not halve the score.
    nan_series = pd.Series(np.nan, index=df.index)
    roic_r = pct_rank(df["roic"], +1).clip(0, 100) if "roic" in df.columns else nan_series
    roce_r = pct_rank(df["roce"], +1).clip(0, 100) if "roce" in df.columns else nan_series
    w_roic = roic_r.notna() * 0.6
    w_roce = roce_r.notna() * 0.4
    w_sum = w_roic + w_roce
    out["capital_efficiency"] = (
        (roic_r.fillna(0) * w_roic + roce_r.fillna(0) * w_roce) / w_sum.replace(0, np.nan)
    )

    # Earnings stability - the upstream value is a 0-3 proxy (low EPS volatility,
    # consecutive positive FCF, growing revenue), NOT a 0-100 score. Consuming it
    # raw made a perfect 3 contribute 3/100 and dragged every composite down by
    # roughly 8 points. Rescale to 0-100 so a 3 means 100.
    if "earnings_stability_score" in df.columns:
        out["earnings_stability"] = (
            pd.to_numeric(df["earnings_stability_score"], errors="coerce")
            / EARNINGS_STABILITY_MAX * 100.0
        ).clip(0, 100)
    else:
        out["earnings_stability"] = np.nan

    # Margin expansion - booleans, mean of whichever are present
    # Rank the MAGNITUDE, not the boolean. A flag cannot separate a tenth of a
    # point of margin improvement from eight points, and with the flag every one
    # of the top 20 scored exactly 100 here. Percentile-ranking the percentage
    # point change restores the gradient. Falls back to the flags only where the
    # magnitude is unavailable.
    mflags = []
    for mag, flag in (("gross_margin_expansion",     "gross_margin_expanding"),
                      ("operating_margin_expansion", "operating_margin_expanding")):
        if mag in df.columns and pd.to_numeric(df[mag], errors="coerce").notna().any():
            mflags.append(pct_rank(pd.to_numeric(df[mag], errors="coerce"), +1).clip(0, 100))
        elif flag in df.columns:
            v = pd.to_numeric(df[flag], errors="coerce")
            mflags.append(v.where(v.isna(), (v > 0) * 100.0))
    out["margin_expansion"] = (pd.concat(mflags, axis=1).mean(axis=1, skipna=True)
                               if mflags else np.nan)

    # Dilution - asymmetric curve. The column holds a RATIO (0.05 = 5% p.a.),
    # so convert to percent first; feeding the ratio straight in would read 5%
    # annual dilution as 0.05% and score it "stable".
    if "shares_dilution_3y" in df.columns:
        dil_pct = pd.to_numeric(df["shares_dilution_3y"], errors="coerce") * 100.0
        out["dilution"] = dil_pct.apply(
            lambda v: np.nan if pd.isna(v) else _dilution_curve(float(v)))
    else:
        out["dilution"] = np.nan

    # Momentum - reuse the factor score computed earlier in this run
    out["momentum"] = df["momentum_score"] if "momentum_score" in df.columns else np.nan

    # Ownership alignment - saturating curve, OWNERSHIP_ALIGNMENT_V1
    if "percent_insiders" in df.columns:
        out["insider_alignment"] = df["percent_insiders"].apply(
            lambda v: np.nan if pd.isna(v) else _ownership_curve(float(v)))
    else:
        out["insider_alignment"] = np.nan

    # -- Eligibility ---------------------------------------------------------
    # Growth is required, plus at least one capital-quality component, plus 70%
    # of the total component weight. Without these, a stock with only momentum,
    # dilution and insider data could score 85 on almost no evidence.
    valid_weight = sum(out[k].notna() * w for k, w in MB_WEIGHTS.items())
    eligible = (
        out["growth"].notna()
        & (out["capital_efficiency"].notna() | out["earnings_stability"].notna())
        & (valid_weight >= MB_MIN_VALID_WEIGHT)
    )

    # Weighted mean over the valid components only, renormalised
    weighted = sum(out[k].fillna(0) * w for k, w in MB_WEIGHTS.items())
    score = (weighted / valid_weight.replace(0, np.nan)).where(eligible)

    out["valid_weight_pct"] = (valid_weight * 100).round(1)
    out["score"] = score.round(1).clip(0, 100)
    return out


MB_BANDS = [
    (85, "Exceptional compounding characteristics"),
    (75, "Strong"),
    (65, "Above Average"),
    (50, "Moderate"),
    (35, "Weak"),
    (0,  "Very Weak"),
]


def multibagger_band(score: Optional[float]) -> Optional[str]:
    """Characteristics-based label. Deliberately avoids predictive language."""
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return None
    for floor, label in MB_BANDS:
        if score >= floor:
            return label
    return MB_BANDS[-1][1]

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

    # Multibagger potential — computed after momentum_score, which it consumes.
    mb = compute_multibagger(df)
    df["mb_score"]              = mb["score"]
    df["mb_growth"]             = mb["growth"].round(1)
    df["mb_capital_efficiency"] = mb["capital_efficiency"].round(1)
    df["mb_earnings_stability"] = mb["earnings_stability"].round(1)
    df["mb_margin_expansion"]   = mb["margin_expansion"].round(1)
    df["mb_dilution"]           = mb["dilution"].round(1)
    df["mb_momentum"]           = mb["momentum"].round(1)
    df["mb_insider_alignment"]  = mb["insider_alignment"].round(1)
    df["mb_valid_weight_pct"]   = mb["valid_weight_pct"]

    scored = int(df["mb_score"].notna().sum())
    log.info(f"  Multibagger potential ({MULTIBAGGER_VERSION}): "
             f"{scored:,} of {len(df):,} stocks met the eligibility rules")
    if scored:
        log.info("    Top 5 by multibagger potential:")
        for _, r in df.nlargest(5, "mb_score")[
                ["asx_code", "mb_score", "mb_valid_weight_pct"]].iterrows():
            log.info(f"      {r['asx_code']:6s}  {r['mb_score']:5.1f}  "
                     f"({multibagger_band(r['mb_score'])}, "
                     f"{r['mb_valid_weight_pct']:.0f}% of weight valid)")

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

    # Multibagger score + components, written separately so a problem here
    # cannot undo the five factor scores above.
    MB_UPDATE_SQL = """
        UPDATE screener.universe
        SET
            multibagger_potential_score     = data.score,
            multibagger_version             = data.version,
            mb_growth_component             = data.growth,
            mb_capital_efficiency_component = data.capeff,
            mb_earnings_stability_component = data.earnstab,
            mb_margin_expansion_component   = data.marginexp,
            mb_dilution_component           = data.dilution,
            mb_momentum_component           = data.momentum,
            mb_insider_alignment_component  = data.insider,
            mb_valid_weight_pct             = data.validw
        FROM (VALUES %s) AS data(
            asx_code, score, version, growth, capeff, earnstab,
            marginexp, dilution, momentum, insider, validw
        )
        WHERE screener.universe.asx_code = data.asx_code
    """

    def _num(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), 1)

    mb_rows = [
        (
            row["asx_code"],
            _num(row["mb_score"]),
            MULTIBAGGER_VERSION,
            _num(row["mb_growth"]),
            _num(row["mb_capital_efficiency"]),
            _num(row["mb_earnings_stability"]),
            _num(row["mb_margin_expansion"]),
            _num(row["mb_dilution"]),
            _num(row["mb_momentum"]),
            _num(row["mb_insider_alignment"]),
            _num(row["mb_valid_weight_pct"]),
        )
        for _, row in df.iterrows()
    ]

    cur = conn.cursor()
    execute_values(
        cur, MB_UPDATE_SQL, mb_rows,
        template=("(%s, %s::NUMERIC, %s::VARCHAR, %s::NUMERIC, %s::NUMERIC, %s::NUMERIC, "
                  "%s::NUMERIC, %s::NUMERIC, %s::NUMERIC, %s::NUMERIC, %s::NUMERIC)"),
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
