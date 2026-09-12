"""
Period arithmetic, separable from the engine that uses it
=========================================================
``average_over`` is pure: fiscal years in, a number or nothing out. It lives
here rather than in ``yearly_compute`` because that module calls
``get_database_url_sync()`` at import, so every function inside it — including
the arithmetic — is unreachable without a database credential.

That pattern has cost this project real defects. ``composite_score`` imports
psycopg2 at module scope, which made ``FACTOR_SIGNALS`` unloadable in every
test run and reported as an import failure by ``metric_registry.graph_health``;
the rules it declared went unexercised for as long as they existed. The
correction is the same one: arithmetic that can be checked should not require
the infrastructure that consumes it.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional


def as_float(value: Any) -> Optional[float]:
    """A number, or None — with NaN treated as absent.

    None and NaN both mean "no observation"; 0.0 and negatives are
    observations. A truthiness test would collapse that distinction, which is
    the compaction defect that let daily_compute drop zero-revenue years and
    report growth between two historical ones.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def average_over(series: Mapping[int, Optional[float]], fy: int,
                 n: int) -> Optional[float]:
    """The mean of exactly n annual observations, or nothing.

    FACTOR_MODEL_V2's contract for every ``avg_*_ny`` metric:

        an average over n years means the average of exactly n annual
        observations from the required contiguous fiscal-year window. If that
        cannot be satisfied, it is not computed.

    No dropna, no last-n-rows, no partial mean. The years are named — fy,
    fy-1, ... fy-(n-1) — so the period claim in the column's own name is
    enforceable rather than assumed.

    What it replaces took ``values[-n:]``, the last n LIST ENTRIES, and then
    dropped every None among them before averaging. Two defects in three
    lines: a company reporting 2016, 2019, 2022 had its "3-year average"
    computed across seven years, and ``avg_roe_3y`` could be a single year's
    ROE labelled as three.

    Returning None loses the reason, deliberately — the numeric column carries
    no state. The distinction the contract needs,

        required fiscal year absent    -> INSUFFICIENT_HISTORY
        year present, observation NULL -> SOURCE_MISSING

    is recovered downstream from ``Observation.periods_available`` against the
    metric's declared period requirement, where the applicability gate already
    lives. It matters most for ROIC: 537 of 1,594 contiguous three-year
    windows hold fewer than three observations, and calling that insufficient
    history would blame the company's record for a sparse metric.
    """
    if n <= 0:
        raise ValueError(f"an average needs a positive window, got {n}")

    required = [fy - offset for offset in range(n)]
    if any(year not in series for year in required):
        return None

    values = [as_float(series[year]) for year in required]
    if any(value is None for value in values):
        return None

    return round(sum(values) / n, 4)
