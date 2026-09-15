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

``sector_benchmarks.py`` is the peer-aggregate instance of the same rule and
is handled in ``peer_benchmarks``. Note the correction there: it is **not**
true that every Financials input is out of domain. For a bank the frozen rules
suppress ``debt_to_equity``, ``current_ratio``, ``gross_margin`` and
``ev_ebitda`` and ``net_margin`` — but ``roe`` and ``grossed_up_yield`` remain
meaningful, and withholding a bank dividend-yield median would be the
industrial-defaults error running in reverse. The assessment decides, metric
by metric; the sector name decides nothing.

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

from compute.engine.applicability import Observation, assess, unhealthy
from compute.engine.domain_resolver import resolve_domain
from compute.engine.metric_registry import normalise  # noqa: F401
from compute.engine.universe_writer import canonical_for
from compute.engine.metric_states import (
    GOVERNED_METRICS,
    LATEST_MODEL_VERSION,
    encode,
)

#: Columns needed to resolve a domain, over and above the factor signals.
DOMAIN_COLS = ["sector", "industry", "is_reit", "is_miner", "revenue_ttm"]

#: Observation field -> the column that is genuinely that metric's denominator.
#:
#: Gate 2 was inert here. assess() was called with no Observation at all, so
#: POSITIVE_DENOMINATOR never fired in the production factor path: every NM in
#: a scoring run came from the domain gate, and not one from an observation.
#: The rule was implemented, tested in isolation, and unwired — so QAN's
#: negative equity still produced a 206% ROE that percentile-ranked as
#: exceptional quality, which is the original defect this contract was built
#: to remove.
#:
#: The bases are the metrics' own, not convenient substitutes. eps_fy0 is
#: COALESCE(pnl0.eps, ym.eps), which is the identical expression
#: build_screener_universe divides price by to derive pe_ratio — so a
#: non-positive eps_fy0 is exactly why that P/E is absent. Feeding net income
#: instead would recover coverage by answering a different question.
#:
#: invested_capital has no column in screener.universe, so roce and roic keep
#: no observation check. That is the honest state: a check that cannot run has
#: not passed, and inventing a proxy denominator would be the same error in
#: the other direction.
#: periods_available is the odd one out and belongs here anyway: it is not a
#: denominator but it is an observation, read by the same gate from the same
#: row. It is what lets an empty avg_*_ny say which of its two absences it is —
#: a window that does not exist, or a window that exists with a hole in it.
OBSERVATION_COLS: dict[str, str] = {
    "equity": "total_equity",
    "earnings": "eps_fy0",
    "revenue": "revenue_ttm",
    "ebitda": "ebitda_ttm",
    "periods_available": "annual_periods",
    # The observed TTM dividend, which is what separates "this company paid
    # nothing" from "we have no dividend data for this company". Only
    # trustworthy since build_screener_universe began taking dps_ttm from
    # market.computed_metrics -- while it came from valuation_snapshot the
    # value was neither governed nor current, and a zero from it would not
    # have supported any conclusion.
    "dividends_observed": "dps_ttm",
    # Consecutive paying years, which is what a dividend CAGR's window is
    # measured in. annual_periods counts reporting years and would pass a
    # company that has reported for a decade and paid for one.
    "dividend_years": "dividend_consecutive_yrs",
}

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
                 tally: Counter, source_failed: pd.Series,
                 assessments: Optional[dict] = None):
        self.frame = frame
        self.states = states                # asx_code -> sidecar payload
        self.tally = tally                  # for the run log
        self.source_failed = source_failed  # bool per row
        #: asx_code -> metric -> Assessment. The in-memory contract, kept so a
        #: peer engine can consume the decisions directly instead of
        #: reconstructing applicability from the masked frame's nulls — which
        #: would reintroduce exactly the ambiguity the sidecar removes.
        self.assessments = assessments or {}

    @property
    def any_source_failed(self) -> bool:
        return bool(self.source_failed.any())



def _numeric(value) -> Optional[float]:
    """A denominator, or None when there is no observation at all.

    Distinguishing these matters more than usual here: None means the check
    cannot run, while 0.0 or a negative number means it runs and fails. A
    truthiness test would collapse the two and silently pass every company
    whose equity is exactly zero.
    """
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _model_constituents(model_version: str) -> set:
    """Every canonical metric the declared model scores on.

    Imported inside the function: factor_model is a peer of this module and a
    top-level import would make the dependency circular.
    """
    from compute.engine.factor_model import model_for
    return {c.metric
            for spec in model_for(model_version).values()
            for c in spec.constituents}


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

    # Columns are matched by canonical name, not by spelling. screener.universe
    # calls it ev_to_ebitda; the governed set and the applicability rules call
    # it ev_ebitda. Comparing raw names silently skipped that column — the
    # exact alias failure the registry exists to prevent, one layer up from
    # where it was being prevented. The frame keeps its own spelling; the
    # assessment is keyed canonically, because that is what a peer engine and
    # the sidecar both look up.
    # canonical_for, not normalise.
    #
    # normalise knows the metric registry's aliases -- ev_to_ebitda ->
    # ev_ebitda -- and nothing about the ones declared only in
    # universe_writer.STORAGE_COLUMN: dps_ttm -> dividend_per_share,
    # fcf_fy0 -> free_cash_flow, and the three-year CAGRs stored as
    # revenue_growth_3y_cagr, eps_growth_3y_cagr, earnings_growth_3y_cagr.
    #
    # Under normalise those five columns were read into the frame, failed to
    # match any governed name, and were never assessed. The canonical writer
    # then refused every row, correctly: "dividend_per_share is governed and
    # was read, but no assessment was produced for it".
    #
    # canonical_for consults the writer's inverse map first and falls back to
    # normalise, so it is a superset. One translation function, used
    # everywhere a column name becomes a metric identity -- which is the whole
    # point of having a single translation boundary, and the ev_to_ebitda
    # defect repeating itself one layer along when there are two.
    # Assess everything the contract OR the model depends on.
    #
    # This filtered on `governed` alone, and governed means "persisted in the
    # sidecar". That is a storage question, and it was silently deciding a
    # semantic one: a metric absent from GOVERNED_METRICS was never assessed
    # at all, so the model scored it with no contract.
    #
    # Two of Income's six declared constituents were in that position --
    # dividend_cagr_3y and dividend_consecutive_yrs -- which is why
    # discovery-11 came back byte-identical to discovery-10 after a correct
    # fix to the dividend CAGR rules. The rules were right and unreachable.
    # An inert gate passes every test that only asks whether the value was
    # withheld, and this codebase has now been caught by that twice: the
    # period gate before annual_periods existed, and this.
    #
    # The invariant, stated so it cannot rot: a metric the declared model
    # names as a constituent must be assessed, whether or not anyone chose to
    # persist it. Persistence stays governed-only -- the sidecar is unchanged
    # -- because what to store and what to reason about are different
    # questions and conflating them is what caused this.
    assessable = set(governed) | _model_constituents(model_version)
    metric_cols = [(c, canonical_for(c)) for c in df.columns]
    metric_cols = [(c, canon) for c, canon in metric_cols if canon in assessable]

    feed_broken = dividend_source is not None and not dividend_source.healthy
    feed_reason = dividend_source.health.reason if feed_broken else ""

    masked = df.copy()
    states: dict[str, dict] = {}
    by_code: dict[str, dict] = {}
    tally: Counter = Counter()
    failed: list[bool] = []

    for idx, row in df.iterrows():
        result = resolve_domain(row)
        tally[f"domain:{result.domain.value}"] += 1

        # One observation per company, from the columns that are genuinely
        # each metric's denominator. A field whose column is absent from the
        # frame stays None, which means that particular check cannot run —
        # not that it passed.
        values = {field: _numeric(row.get(column))
                  for field, column in OBSERVATION_COLS.items()
                  if column in df.columns}
        # A period count is a count. It arrives through pd.to_numeric as a
        # float like every other column, and left that way the withheld
        # metric's reason reads "2.0 consecutive annual periods available".
        periods = values.get("periods_available")
        if periods is not None:
            values["periods_available"] = int(periods)
        observation = Observation(**values)
        if any(getattr(observation, f) is not None
               for f in OBSERVATION_COLS):
            tally["observation:supplied"] += 1

        assessments = []
        row_failed = False

        for col, canon in metric_cols:
            value = row[col]
            if value is not None and pd.isna(value):
                value = None

            if feed_broken and canon in INCOME_METRICS:
                a = unhealthy(canon, feed_reason, result.domain)
                row_failed = True
            else:
                a = assess(canon, None if value is None else float(value),
                           result.domain, observation)

            assessments.append(a)
            if not a.ok:
                masked.at[idx, col] = np.nan
                tally[f"state:{a.state.value}"] += 1

        failed.append(row_failed)
        by_code[row["asx_code"]] = {a.metric: a for a in assessments}
        payload = encode(assessments)
        if payload:
            states[row["asx_code"]] = payload

    return Masked(masked, states, tally,
                  pd.Series(failed, index=df.index, dtype=bool), by_code)


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
