"""
Why a return is absent
======================
Four things can empty a price-window column, and until now all four arrived
at the customer as the same blank cell:

    no close near the window's start   the stock did not trade around its
                                       anniversary -- a fact about the company
    not enough history                 the series does not reach back that far
    withheld over a corporate action   a split we cannot reconcile sits inside
                                       the window -- a fact about OUR data
    the column cannot store it         a consolidation compounded past the
                                       column's ceiling -- a fact about our
                                       schema

They have different remediations and one representation. The third sends
somebody to reconcile a split; the fourth sends somebody to widen a column;
the first two are simply true and need saying rather than fixing.

On 28 Oct 2026, after canonical run 30 published cleanly, 608 of 2,113 served
stocks carried a NULL return_1y with no state entry, 190 a NULL return_6m and
87 a NULL return_3m. metric_states.py already states the contract -- "a NULL
numeric column must never be the only signal" -- and violations() already
enforces it. It reported zero because the price windows were not governed, so
the guarantee was real and its population was empty.

Scope: the LATEST row only
--------------------------
market.daily_metrics holds a row per trading day, and a backfill writes
hundreds per company. Assessing every one of them would attach a reason
string to roughly 940,000 rows times sixteen windows, which is a sidecar far
larger than the table it annotates, to explain values nothing reads.

screener.universe takes the latest row, under an as-of guard, and that row is
what a customer sees. So that row is assessed and the rest are left NULL --
which the migration already defines as "never assessed", distinct from '{}'
meaning "assessed and clean". Both are honest; neither pretends a historical
row was examined.
"""

from __future__ import annotations

from typing import Mapping, Optional

import pandas as pd

from compute.engine.applicability import Applicability, Cause
from compute.engine.return_windows import (
    ALL_WINDOWS, HIGH_LOW_DAYS, HIGH_LOW_GRACE,
)

#: The 52-week extremes, canonical name -> storage column.
#:
#: Governed in V3 alongside the returns, and absent for a different reason:
#: rolling_extreme() blanks a row whose series does not yet span the window,
#: which stops a stock listed last Tuesday being handed a "52-week high"
#: drawn from four days. That is a statement about coverage, not about a
#: missing anchor, so it gets its own branch rather than the returns' one.
EXTREME_COLUMNS = {
    "week_52_high": "high_52w",
    "week_52_low": "low_52w",
}


def anchor_for(dates: pd.Series, row: int, offset, grace_days: int):
    """(target_date, anchor_date_or_None) for one row.

    Recomputed directly rather than via anchor_positions() over the whole
    series: only the latest row is assessed, and this is two comparisons
    instead of an array pass per window.

    Same rule as anchor_positions, deliberately: the last close AT OR BEFORE
    the target, and only if it is within the grace. If this ever disagrees
    with that function the sidecar would explain a value the producer did not
    compute, which is worse than no explanation at all --
    test_the_explanation_matches_the_producer pins them together.
    """
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates).reset_index(drop=True)))
    target = idx[row] - offset
    prior = idx[idx <= target]
    if len(prior) == 0:
        return target, None
    anchor = prior[-1]
    if (target - anchor).days > grace_days:
        return target, None
    return target, anchor


def assess_row(dates: pd.Series,
               row: int,
               computed: Mapping[str, bool],
               after_withholding: Mapping[str, bool],
               final: Mapping[str, bool]) -> dict:
    """The sparse sidecar for one row: metric -> {state, cause, reason}.

    The three mappings are "this window held a value" at three points:

        computed            straight out of compute_indicators
        after_withholding   after corporate-action withholding
        final               after the column-limit withholding

    Diffing them is what separates the causes. A single look at the final
    frame cannot: every one of them is NaN by then.

    Entries only for metrics that are not APPLICABLE, matching
    screener.universe.metric_states -- absence of an entry IS the applicable
    signal, and that is what keeps the payload proportional to the problem.
    """
    out: dict[str, dict] = {}

    for metric, (offset, grace) in ALL_WINDOWS.items():
        if final.get(metric, False):
            continue                                    # applicable

        if after_withholding.get(metric, False):
            # Survived the corporate-action check and was removed by the
            # column limit. Our schema, not the company's data, and it clears
            # by widening a column -- never by waiting. INSUFFICIENT_HISTORY
            # would blame the company for our ceiling.
            out[metric] = {
                "state": Applicability.UNAVAILABLE.value,
                "cause": Cause.COMPUTATION_UNSUPPORTED.value,
                "reason": "the computed return exceeds what the column can "
                          "store; a consolidation compounded past its ceiling",
            }
            continue

        if computed.get(metric, False):
            # Computed, then withheld: a corporate action we could not
            # reconcile sits inside this window. SOURCE_MISSING because what
            # is missing is the split record, not the price.
            out[metric] = {
                "state": Applicability.UNAVAILABLE.value,
                "cause": Cause.SOURCE_MISSING.value,
                "reason": "an unreconciled corporate action falls inside this "
                          "window; the prices either side are not comparable",
            }
            continue

        # Never computed. Either the series does not reach the target, or it
        # reaches it and no close sits close enough to it.
        target, anchor = anchor_for(dates, row, offset, grace)
        if anchor is None:
            out[metric] = {
                "state": Applicability.INSUFFICIENT_DATA.value,
                "cause": Cause.INSUFFICIENT_HISTORY.value,
                "reason": f"no close within {grace} days of "
                          f"{target.date().isoformat()}",
            }
        else:
            # An anchor exists and the value is still absent, which leaves
            # the denominator: a zero or non-finite opening price. The window
            # is fine and the arithmetic is not.
            out[metric] = {
                "state": Applicability.UNAVAILABLE.value,
                "cause": Cause.OBSERVATION.value,
                "reason": f"the close on {anchor.date().isoformat()} is zero "
                          f"or unusable as a denominator",
            }

    # The 52-week extremes. Absent for one reason only: the series does not
    # span the window yet. rolling_extreme() blanks those rows deliberately,
    # because pandas' own rolling('365D') has min_periods=1 and would hand a
    # stock listed last Tuesday a "52-week high" drawn from four days.
    idx = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates).reset_index(drop=True)))
    spanned = (idx[row] - idx[0]).days
    required = HIGH_LOW_DAYS - HIGH_LOW_GRACE

    for metric in EXTREME_COLUMNS:
        if final.get(metric, False):
            continue
        if spanned < required:
            out[metric] = {
                "state": Applicability.INSUFFICIENT_DATA.value,
                "cause": Cause.INSUFFICIENT_HISTORY.value,
                "reason": f"the series spans {spanned} days; a 52-week "
                          f"extreme needs {required}",
            }
        else:
            out[metric] = {
                "state": Applicability.UNAVAILABLE.value,
                "cause": Cause.OBSERVATION.value,
                "reason": "the series spans the window but carries no usable "
                          "high or low over it",
            }

    return out


def window_assessment(metric: str, value, states_payload) -> "Assessment":
    """Rebuild one window's Assessment from the stored row.

    The canonical writer re-emits the WHOLE sidecar for its model version in
    one statement, so the window entries have to be handed back to it or they
    are dropped between the two producers -- the builder writes them, the
    writer overwrites them, and the explanation disappears between two
    statements that are each individually correct.

    Faithful, not tidy. An entry present means the producer decided the
    metric is not applicable and the value must be None; a value present with
    no entry means applicable. If a row ever carries both, this builds the
    contradiction rather than hiding it, and assert_complete refuses the
    write -- which is the behaviour every other governed metric already gets.
    """
    from compute.engine.applicability import Assessment     # local: cycle

    entry = (states_payload or {}).get(metric)

    if entry is not None:
        return Assessment(
            metric=metric,
            state=Applicability(entry["state"]),
            value=None,
            cause=Cause(entry["cause"]) if entry.get("cause") else None,
            reason=entry.get("reason", ""),
        )

    missing = value is None or (isinstance(value, float) and pd.isna(value))
    if not missing:
        return Assessment(metric=metric,
                          state=Applicability.APPLICABLE,
                          value=float(value))

    # Absent with no recorded reason. That is a row technical_compute has not
    # assessed -- written before this contract existed, or by a run that
    # predates it. Not APPLICABLE, because the value is not there; and not a
    # claim about the company either, because we genuinely do not know.
    return Assessment(
        metric=metric,
        state=Applicability.UNAVAILABLE,
        value=None,
        cause=Cause.SOURCE_MISSING,
        reason="no value and no recorded reason: this row predates the "
               "window-state contract or was written without assessment",
    )


def presence(df: pd.DataFrame, row: int) -> dict[str, bool]:
    """Which governed price metrics hold a value on one row.

    Keyed by CANONICAL metric name and read from the STORAGE column, because
    the two differ for the extremes (week_52_high -> high_52w). Keying this
    by column would silently report both as absent for every row.
    """
    out = {metric: (metric in df.columns and pd.notna(df[metric].iloc[row]))
           for metric in ALL_WINDOWS}
    for metric, column in EXTREME_COLUMNS.items():
        out[metric] = column in df.columns and pd.notna(df[column].iloc[row])
    return out


def assess_latest(df: pd.DataFrame,
                  computed: Mapping[str, bool],
                  after_withholding: Mapping[str, bool]) -> Optional[dict]:
    """The sidecar for the last row of df, or None for an empty frame."""
    if df is None or len(df) == 0:
        return None
    row = len(df) - 1
    return assess_row(df["date"], row, computed, after_withholding,
                      presence(df, row))
