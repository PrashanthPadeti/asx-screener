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
from datetime import datetime, timezone
from typing import Mapping, Optional

import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import sys
from pathlib import Path

# The database credential lives in the environment, never in source.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# Both of these resolve only after the path insert above. Run as a script,
# sys.path[0] is compute/engine/, so `compute.engine.*` is not importable
# until the repo root is on the path — importing them at the top of the file
# is the exact ordering that took the pipeline down before.
from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.applicability import (  # noqa: E402
    Applicability, Assessment, Cause, unhealthy,
)
from compute.engine.factor_applicability import (  # noqa: E402
    OBSERVATION_COLS,  # noqa: E402
    DOMAIN_COLS,
    apply_applicability,
    withhold_source_failed,
)
# The declaration lives in its own module and is imported, never defined or
# mutated here. This module cannot be loaded without psycopg2, which is why
# the factor tables were previously unreadable to every test run and to
# metric_registry.graph_health(). Scoring depends on the model; the model must
# not depend on scoring.
from compute.engine.factor_model import (  # noqa: E402
    FactorSpec, composite_for, effective_weights, model_for,
)
from compute.engine.metric_states import (  # noqa: E402
    LATEST_MODEL_VERSION, SourceHealth,
)
from compute.engine.universe_writer import (  # noqa: E402
    ComputeRun,
    WriteRefused,
    column_for,
    commit_canonical,
    persisted_governed,
)

#: The frame carries asx_code as a column; assessments are keyed by it.
CODE_COLUMN = "asx_code"


load_dotenv()

DB_URL = get_database_url_sync()

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


def compute_factor(df: pd.DataFrame, factor_name: str,
                   spec: Optional[FactorSpec] = None,
                   assessments: Optional[dict] = None,
                   model_version: str = LATEST_MODEL_VERSION,
                   states_out: Optional[dict] = None) -> pd.Series:
    """One factor score, from the weights the model declares.

    The invariant this enforces:

        Factor weights come from the declared model specification, never from
        whatever values happen to be non-null at runtime.

    What it replaces was ``stacked.mean(axis=1, skipna=True)``. A constituent
    that was NaN for any reason left the average and the survivors absorbed
    its weight, so a bank's quality_score was a five-signal blend wearing a
    six-signal name with nothing in the payload to say so. Worse, the two
    reasons a constituent goes missing have opposite correct answers and that
    form could not tell them apart:

      NOT_MEANINGFUL   the signal does not describe this company's economics.
                       Reweighting is right — a bank has no meaningful
                       leverage ratio — but only as declared policy, with the
                       effective weights recoverable.

      UNAVAILABLE      the signal applies and is missing. Reweighting
                       publishes a different model under this one's name.

    ``assessments`` is asx_code -> metric -> Assessment, as produced by
    apply_applicability. Without it this falls back to the old behaviour, and
    logs that it has done so: a silent fallback would restore the defect in
    exactly the conditions that make it hardest to notice.
    """
    spec = spec or model_for(model_version)[factor_name]

    declared = list(spec.constituents)

    # The model declares canonical identities; the frame carries storage
    # spellings; the assessments are keyed canonically. Indexing the frame by
    # the canonical name would KeyError on ev_ebitda while the column is
    # ev_to_ebitda — the alias failure this codebase has now produced at three
    # separate layers.
    column = {c.metric: column_for(c.metric) for c in declared}

    absent = [f"{m} ({col})" for m, col in column.items()
              if col not in df.columns]
    if absent:
        # A contract error, not financial unavailability: the model names a
        # column the frame does not carry. Returning NaN would look like a
        # company with no data.
        raise KeyError(
            f"{factor_name}: declared constituents missing from the frame: "
            f"{', '.join(sorted(absent))}")

    ranks = pd.concat(
        [pct_rank(df[column[c.metric]], c.direction).clip(0, 100)
         for c in declared],
        axis=1)
    ranks.columns = [c.metric for c in declared]

    if assessments is None:
        log.warning("%s scored without assessments — weights fall back to "
                    "whatever is non-null, which is the defect this signature "
                    "exists to remove", factor_name)
        return ranks.mean(axis=1, skipna=True).round(0).clip(0, 100)

    assessments = assessments or {}

    codes = df[CODE_COLUMN] if CODE_COLUMN in df.columns else pd.Series(
        df.index, index=df.index)

    # One policy, in one place. This used to reimplement the rules as a
    # vectorised weight table, which meant the declared contract existed twice
    # — and two implementations of the same semantics diverge, which is the
    # failure mode this whole model exists to remove. effective_weights() is
    # now the only thing that decides.
    score = pd.Series(float("nan"), index=df.index)

    for position, code in zip(df.index, codes):
        assessed = dict(assessments.get(code, {}))

        # An ungoverned constituent has no assessment because no gate ran for
        # it, so its value is all the evidence there is. Synthesising one here
        # keeps effective_weights the single authority rather than teaching
        # compute_factor a second, quieter rule for a subset of signals.
        for c in declared:
            if c.metric in assessed:
                continue
            raw = df.at[position, column[c.metric]]
            assessed[c.metric] = (
                Assessment(c.metric, Applicability.UNAVAILABLE, None,
                           "ungoverned constituent with no value", None,
                           cause=Cause.SOURCE_MISSING)
                if pd.isna(raw) else
                Assessment(c.metric, Applicability.APPLICABLE, float(raw), "",
                           None))

        effective = effective_weights(spec, assessed)
        if states_out is not None:
            states_out[code] = effective
        if not effective.usable:
            continue

        total = 0.0
        for metric, weight in effective.weights.items():
            rank = ranks.at[position, metric]
            if pd.isna(rank):
                # Applicable with no rank means the column is empty for a
                # metric the assessment called usable — a contradiction the
                # persistence validator exists to catch. Withhold rather than
                # score it as zero.
                total = float("nan")
                break
            total += rank * weight
        score.at[position] = total

    return score.round(0).clip(0, 100)


def compute_composite(df_scores: pd.DataFrame,
                      source_failed: Optional[pd.Series] = None,
                      factor_states: Optional[dict] = None,
                      model_version: str = LATEST_MODEL_VERSION) -> pd.Series:
    """Equal-weight composite of the 5 factor scores; requires >= 2 non-null.

    ``source_failed`` marks rows where a factor is missing because its *feed*
    broke rather than because it does not apply. Those get no composite at
    all, however many factors survive.

    The distinction is the whole point. Averaging four factors for a bank
    whose Piotroski is out of domain describes the bank. Averaging four
    factors because the dividend feed stopped describes nothing — it silently
    converts a five-factor model into a four-factor one and keeps the name,
    and the resulting number looks entirely ordinary next to a genuine one.
    """
    spec = composite_for(model_version)

    if factor_states is None:
        # The old behaviour: an equal-weight mean of whatever is non-null,
        # requiring two. That is the skipna defect one level up — a company
        # with two surviving factors received a "composite" built from 40% of
        # the declared model, indistinguishable from one built on all five.
        # Kept only so a caller without factor states is not silently broken,
        # and loud because it should not happen in the pipeline.
        log.warning("composite computed without factor states — falling back "
                    "to a mean of whatever is non-null, which is the defect "
                    "this signature exists to remove")
        stacked = df_scores[[c.metric for c in spec.constituents
                             if c.metric in df_scores.columns]]
        composite = stacked.mean(axis=1, skipna=True).round(0).clip(0, 100)
        return withhold_source_failed(
            composite.where(stacked.notna().sum(axis=1) >= 2), source_failed)

    codes = df_scores[CODE_COLUMN]
    composite = pd.Series(float("nan"), index=df_scores.index)

    for position, code in zip(df_scores.index, codes):
        # A factor's own EffectiveWeights becomes this composite's assessment
        # of it. NOT_MEANINGFUL travels as NOT_MEANINGFUL so the composite may
        # reweight within its floor; UNAVAILABLE travels as UNAVAILABLE so it
        # refuses — including when the cause is a dividend feed outage three
        # layers down, which is exactly the case that must not quietly become
        # a four-factor model.
        assessments = {}
        for c in spec.constituents:
            effective = (factor_states.get(c.metric.removesuffix("_score"), {})
                         .get(code))
            if effective is None:
                assessments[c.metric] = Assessment(
                    c.metric, Applicability.UNAVAILABLE, None,
                    "factor not scored", None, cause=Cause.SOURCE_MISSING)
                continue
            assessments[c.metric] = Assessment(
                c.metric, effective.state,
                df_scores.at[position, c.metric]
                if c.metric in df_scores.columns else None,
                effective.reason, None, cause=effective.cause)

        resolved = effective_weights(spec, assessments)
        if not resolved.usable:
            continue

        total = 0.0
        for metric, weight in resolved.weights.items():
            value = df_scores.at[position, metric]
            if pd.isna(value):
                total = float("nan")
                break
            total += float(value) * weight
        composite.at[position] = total

    return withhold_source_failed(composite.round(0).clip(0, 100),
                                  source_failed)





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


DILUTION_QUALITY_VERSION = "DILUTION_QUALITY_V1"

# Annualised share-count change (percent, positive = dilution) -> score.
# Interpolated linearly between knees.
#
# Calibrated against the observed ASX distribution rather than fitted to it.
# Median annual dilution here is 6.2 percent, p75 is 20.6 and 26 percent of the
# market exceeds 20 percent a year — far more dilutive than a developed-market
# baseline. That is an argument for absolute economic anchors, NOT percentile
# ranking: rank-normalising would make a 20 percent diluter merely average,
# grading on a curve where the curve is itself the problem. Twenty percent a
# year destroys per-share compounding however many peers do the same.
#
# The floor sits at 60 rather than 25 percent. Saturating at 25 would collapse a
# quarter of the market to a flat zero and lose all ordering inside the worst
# group — the same defect as the ownership curve saturating at 25 percent
# ownership. Beyond about 60 there is little value separating one extreme from
# another for a compounding measure.
#
# Buybacks are capped at 100 and worth at most 10 points above a stable
# register, so a shrinking share count can improve this component but never
# compensate for weak growth, returns or stability.
_DILUTION_KNEES = [
    (-20.0, 100.0),   # sustained buyback, capped
    (  0.0,  90.0),   # stable register
    (  2.0,  80.0),
    (  5.0,  65.0),
    ( 10.0,  45.0),
    ( 20.0,  20.0),
    ( 40.0,   5.0),
    ( 60.0,   0.0),   # floor
]


def _dilution_curve(d: float) -> float:
    """Share-count change over the window (percent, positive = dilution) -> 0-100."""
    if d <= _DILUTION_KNEES[0][0]:
        return _DILUTION_KNEES[0][1]
    for (x0, y0), (x1, y1) in zip(_DILUTION_KNEES, _DILUTION_KNEES[1:]):
        if d <= x1:
            return y0 + (y1 - y0) * (d - x0) / (x1 - x0)
    return _DILUTION_KNEES[-1][1]


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

def run(conn, dry_run: bool = False, run_id: Optional[int] = None) -> int:
    """Load universe, compute scores, upsert. Returns number of rows updated."""
    log.info("Loading screener.universe for scoring…")

    from compute.engine.dividends import DividendSource
    from compute.engine.daily_compute import fetch_feed_health

    cur = conn.cursor()
    select_cols = ALL_COLS + [c for c in DOMAIN_COLS if c not in ALL_COLS]
    # Gate 2 needs each metric's own denominator, or it cannot run
    # and every non-positive-denominator ratio passes as applicable.
    select_cols += [c for c in OBSERVATION_COLS.values() if c not in select_cols]

    # Every column this model version persists, because this is now the
    # canonical commit boundary: it re-emits all of them together with the
    # sidecar and the attribution, in one statement per row. A column it does
    # not read it cannot write, and a governed column it does not write keeps
    # the previous run's value beside this run's states.
    canonical_columns = persisted_governed(LATEST_MODEL_VERSION)
    select_cols += [c for c in canonical_columns.values()
                    if c not in select_cols]
    col_list = ", ".join(select_cols)
    cur.execute(f"""
        SELECT {col_list}
        FROM screener.universe
        WHERE status = 'active'
          AND price IS NOT NULL
    """)
    rows = cur.fetchall()

    # One watermark for the run. The income factor cannot be scored over a
    # window the dividend feed has not observed, and that has to be decided
    # once for the whole universe rather than inferred per company.
    feed_health = fetch_feed_health(cur)
    dividend_source = DividendSource(feed_health)
    cur.close()

    if not rows:
        log.error("No active rows in screener.universe")
        return 0

    df = pd.DataFrame(rows, columns=select_cols)
    log.info(f"  Loaded {len(df):,} stocks")

    # Coerce numerics — domain columns stay as they are.
    numeric_cols = [c for c in select_cols
                    if c != "asx_code" and c not in ("sector", "industry")]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Applicability, before ranking ─────────────────────────────────────────
    # Supersedes the hand-rolled guards that used to live here (pe_ratio < 0 or
    # > 500, debt_to_equity < 0). Those were observation validity done by
    # threshold; the contract does it by rule, and records why rather than
    # silently discarding.
    if not feed_health.healthy:
        log.warning("Dividend feed unhealthy: %s. Income factor and composite "
                    "will be withheld rather than computed on four factors.",
                    feed_health.reason)

    masked = apply_applicability(df, dividend_source)
    df, metric_states = masked.frame, masked.states
    for key, count in sorted(masked.tally.items()):
        log.info("  %-40s %5d", key, count)

    # ── Compute factor scores ─────────────────────────────────────────────────
    # The assessments are passed, not re-derived from the frame's nulls. A
    # NaN cannot say whether it is out of domain or merely absent, and those
    # two have opposite correct answers.
    model = model_for(LATEST_MODEL_VERSION)
    factor_states: dict[str, dict] = {}
    for factor in ("value", "quality", "growth", "momentum", "income"):
        states: dict = {}
        df[f"{factor}_score"] = compute_factor(
            df, factor, model[factor], masked.assessments,
            model_version=LATEST_MODEL_VERSION, states_out=states)
        factor_states[factor] = states
    df["composite_score"]= compute_composite(
        df, masked.source_failed, factor_states,
        model_version=LATEST_MODEL_VERSION)

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

    # ── The canonical commit ─────────────────────────────────────────────────
    # Everything above this point is PROVISIONAL. The build's governed columns
    # and these score updates are inputs to canonicalisation, not contract
    # rows: no resolver may treat them as authoritative until the transaction
    # below commits values, states and attribution together.
    #
    # Without a run id there is nothing to attribute to, so the run stays
    # provisional and nothing becomes servable. That is the correct default —
    # a build that did not declare itself part of a canonical run has not
    # earned publication.
    if run_id is None:
        log.warning("No --run-id: rows remain PROVISIONAL. No sidecar, no "
                    "attribution, and no resolver will serve them.")
        return len(update_rows)

    # The feed's state, recorded once for the run rather than per company. A
    # broken dividend feed is an exchange-wide fact, and writing it onto every
    # row would let it disagree with itself halfway through.
    source_health = SourceHealth(
        run_at=datetime.now(timezone.utc),
        unhealthy_sources=() if feed_health.healthy else ("dividends",),
        detail={} if feed_health.healthy else {"dividends": feed_health.reason},
        factor_model_version=LATEST_MODEL_VERSION,
        run_id=run_id)

    by_code = canonical_assessments(df, masked, factor_states,
                                    masked.source_failed)
    written = commit_canonical(
        conn, ComputeRun(run_id, "composite_score", LATEST_MODEL_VERSION,
                         source_health),
        by_code,
        required_stages=REQUIRED_STAGES,
        details={"universe_rows": len(df),
                 "dividend_feed_healthy": feed_health.healthy})

    log.info("  ✓ canonical commit: %s rows published under run %s",
             f"{written:,}", run_id)
    return written


#: Every full producer whose output the canonical writer re-emits. Both must
#: have proven their own population, or the attribution would assert a
#: coherence nobody established. yearly_compute alone is not enough: it can
#: prove perfect coverage while the build silently misses rows, and the
#: canonical writer would then faithfully publish stale provisional values —
#: the same defect wearing a completeness certificate.
REQUIRED_STAGES = ("yearly_compute", "universe_build")

#: Computed here rather than read, so their assessments are built from this
#: run's results and never from the previous run's columns — which the frame
#: now also contains, because the canonical writer must read every governed
#: column in order to re-emit it.
SCORE_METRICS = frozenset({
    "value_score", "quality_score", "growth_score",
    "momentum_score", "income_score", "composite_score",
})


def _score_assessment(metric: str, value, code: str,
                      factor_states: Mapping[str, Mapping],
                      row_source_failed: bool) -> Assessment:
    """Why a factor score is absent, taken from the model rather than guessed.

    EffectiveWeights already records the state, cause and reason for a factor
    the model declined to compute — a bank below the minimum semantic coverage
    for V2 Quality, say. Reading it here keeps the methodology in one place.
    Inventing a cause at the writer would be a second opinion about the model,
    expressed where nobody would look for it.
    """
    if value is not None and not (isinstance(value, float) and np.isnan(value)):
        return Assessment(metric, Applicability.APPLICABLE, float(value), "",
                          None)

    if row_source_failed:
        return unhealthy(metric, "a constituent factor's source was unhealthy")

    effective = factor_states.get(metric.removesuffix("_score"), {}).get(code)
    if effective is not None and not effective.usable:
        return Assessment(metric, effective.state, None, effective.reason,
                          None, cause=effective.cause)

    return Assessment(metric, Applicability.UNAVAILABLE, None,
                      "not computed by this run", None,
                      cause=Cause.SOURCE_MISSING)


def canonical_assessments(df, masked, factor_states,
                          source_failed) -> dict[str, dict[str, Assessment]]:
    """Every governed metric, for every company, with nothing left implicit.

    The canonical row is complete by definition: 72 of 72 under V2, each with
    a value or a stated reason for its absence. A metric missing here would be
    written as NULL with no sidecar entry — an unexplained null created by the
    statement meant to prevent one — so the writer refuses rather than
    completing the row on the caller's behalf.
    """
    mapping = persisted_governed(LATEST_MODEL_VERSION)
    failed = source_failed.reindex(df.index).fillna(False).astype(bool)

    out: dict[str, dict[str, Assessment]] = {}
    for idx, row in df.iterrows():
        code = row["asx_code"]
        assessed = dict(masked.assessments.get(code, {}))

        for metric in mapping:
            if metric in SCORE_METRICS:
                assessed[metric] = _score_assessment(
                    metric, row.get(metric), code, factor_states,
                    bool(failed.loc[idx]))
            elif metric not in assessed:
                # The frame carries every governed column, so applicability
                # should have assessed it. Reaching here means a column was
                # read and not assessed, which is an application defect and
                # must not be published as though the company had no value.
                raise WriteRefused(
                    f"{code}: {metric} is governed and was read, but no "
                    f"assessment was produced for it")
        out[code] = assessed
    return out


def _to_smallint(v) -> Optional[int]:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return int(round(v))


def main():
    parser = argparse.ArgumentParser(description="Compute composite factor scores")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute scores without writing to DB")
    parser.add_argument("--run-id", type=int,
                        help="The compute run to publish under. Without it "
                             "the scores are written but stay PROVISIONAL: no "
                             "sidecar, no attribution, and no resolver will "
                             "serve them.")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    try:
        n = run(conn, dry_run=args.dry_run, run_id=args.run_id)
    finally:
        conn.close()

    log.info(f"Composite score engine complete — {n} stocks processed.")


if __name__ == "__main__":
    main()
