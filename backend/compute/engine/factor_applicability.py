"""
Applying the applicability contract to the factor frame
=======================================================
Separate from ``composite_score`` for one practical reason: that module
imports psycopg2 at module scope, so nothing in it can be exercised without a
database driver installed. This is the subtlest step in the whole wiring and
it needs to be testable on its own.

The ordering is the substance here, not the masking:

    **Applicability suppression occurs before any cross-sectional statistic,
    not after scoring.**

``pct_rank`` is the instance that surfaced it, but the rule is deliberately
not about ranking. The same contamination arrives through winsorisation,
z-scores, quantile buckets, medians, peer averages, sector-relative
normalisation, or any clipping threshold derived from the population. Mask
first, then compute the population statistic.

KNOWN GAP, recorded rather than silently left: ``sector_benchmarks.py``
computes per-sector median / P25 / P75 for ``debt_to_equity``,
``current_ratio``, ``gross_margin``, ``roe``, ``net_margin``, ``ev_to_ebitda``
and ``grossed_up_yield`` straight from the unmasked universe. For the
Financials sector every one of those inputs is out of domain, so the published
"Financials sector median debt_to_equity" is a statistic computed entirely
from suppressed observations. It is a separate engine and a separate wiring
step; it must not ship enabled until it takes the masked frame.

``pct_rank`` ranks a whole column. An out-of-domain value left in place does
not merely mislabel its own row — it moves the percentile of every other
company in the market. Suppressing after the ranking would show CBA an ``NM``
for ``debt_to_equity`` while its 4.6x had already pushed every industrial
company's leverage percentile down, which is the original defect surviving in
a form nobody would think to look for.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

import numpy as np
import pandas as pd

from compute.engine.applicability import assess, unhealthy
from compute.engine.domain_resolver import resolve_domain
from compute.engine.metric_states import (
    GOVERNED_METRICS,
    LATEST_MODEL_VERSION,
    encode,
)

#: Columns needed to resolve a domain, over and above the factor signals.
DOMAIN_COLS = ["sector", "industry", "is_reit", "is_miner", "revenue_ttm"]

#: The income family. When the dividend feed is unhealthy these are withheld
#: as a source failure rather than assessed, because the feed's state is a
#: fact about the exchange and not about any company's economic model.
INCOME_METRICS = frozenset({
    "dividend_yield", "grossed_up_yield", "franking_pct",
    "dividend_per_share", "grossed_up_dividend", "dividend_payout_ratio",
})


class Masked:
    """The result of applying applicability to a factor frame."""

    def __init__(self, frame: pd.DataFrame, states: dict,
                 tally: Counter, source_failed: pd.Series):
        self.frame = frame
        self.states = states                # asx_code -> sidecar payload
        self.tally = tally                  # for the run log
        self.source_failed = source_failed  # bool per row

    @property
    def any_source_failed(self) -> bool:
        return bool(self.source_failed.any())


def apply_applicability(df: pd.DataFrame,
                        dividend_source=None,
                        model_version: str = LATEST_MODEL_VERSION) -> Masked:
    """NaN out every metric that is not APPLICABLE, per row, before ranking.

    The frame keeps its shape: nothing is dropped, because a company with a
    suppressed metric is still a company and still belongs in the universe.
    What changes is that the suppressed value stops participating — in its own
    row's factor, and in everyone else's percentile.
    """
    governed = GOVERNED_METRICS[model_version]
    metric_cols = [c for c in df.columns if c in governed]

    feed_broken = dividend_source is not None and not dividend_source.healthy
    feed_reason = dividend_source.health.reason if feed_broken else ""

    masked = df.copy()
    states: dict[str, dict] = {}
    tally: Counter = Counter()
    failed: list[bool] = []

    for idx, row in df.iterrows():
        result = resolve_domain(row)
        tally[f"domain:{result.domain.value}"] += 1

        assessments = []
        row_failed = False

        for col in metric_cols:
            value = row[col]
            if value is not None and pd.isna(value):
                value = None

            if feed_broken and col in INCOME_METRICS:
                a = unhealthy(col, feed_reason, result.domain)
                row_failed = True
            else:
                a = assess(col, None if value is None else float(value),
                           result.domain)

            assessments.append(a)
            if not a.ok:
                masked.at[idx, col] = np.nan
                tally[f"state:{a.state.value}"] += 1

        failed.append(row_failed)
        payload = encode(assessments)
        if payload:
            states[row["asx_code"]] = payload

    return Masked(masked, states, tally,
                  pd.Series(failed, index=df.index, dtype=bool))


def withhold_source_failed(composite: pd.Series,
                           source_failed: Optional[pd.Series]) -> pd.Series:
    """Null the composite for rows where a factor's *source* failed.

    Averaging four factors for a bank whose Piotroski is out of domain
    describes the bank. Averaging four because the dividend feed stopped
    describes nothing: it converts a five-factor model into a four-factor one,
    keeps the name, and produces a number that looks entirely ordinary beside
    a genuine one.
    """
    if source_failed is None:
        return composite
    mask = source_failed.reindex(composite.index).fillna(False).astype(bool)
    return composite.where(~mask)
