"""
Peer statistics computed only from valid peers
==============================================
A sector benchmark is a cross-sectional statistic, so it falls under the same
rule as the factor ranks:

    Applicability suppression occurs before any cross-sectional statistic,
    including ranks, percentiles, peer aggregates and population-derived
    thresholds.

``sector_benchmarks.py`` currently computes median / P25 / P75 straight from
the unmasked universe. Where a metric is out of domain for the companies in a
sector, the published benchmark is a statistic with no valid observation
behind it.

**The sector name does not decide this — the assessment does.** For a bank the
frozen rules suppress ``debt_to_equity``, ``current_ratio``, ``gross_margin``
and ``ev_ebitda``, while ``roe``, ``net_margin`` and ``grossed_up_yield``
remain perfectly meaningful. A "Financials benchmarks are all invalid" rule
would be as wrong as the industrial defaults it replaces, in the other
direction: it would withhold a bank dividend-yield median that customers can
legitimately use.

Two further properties a peer statistic needs and a rank does not:

  * **the denominator travels with it.** "4.8%, 18 of 22 valid observations"
    is an honest statistic; "4.8%" alone conceals whether it rests on
    eighteen companies or one.
  * **a minimum-coverage gate.** A median over one surviving company is
    computable and financially useless. The engine fails closed rather than
    manufacturing quartiles from whatever survived.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from compute.engine.applicability import Applicability, Assessment, Cause

#: Absolute floor. Below this the quartiles describe individuals, not a peer
#: group, whatever the coverage fraction says.
MIN_VALID_N = 5

#: And a share of the sector, so a large sector cannot pass the floor on a
#: small unrepresentative remnant. Both must hold.
MIN_VALID_FRACTION = 0.30


@dataclass(frozen=True)
class Benchmark:
    """One sector-metric statistic, with its denominator and its state."""

    metric: str
    state: Applicability
    n_total: int = 0
    n_valid: int = 0
    p25: Optional[float] = None
    median: Optional[float] = None
    p75: Optional[float] = None
    reason: str = ""
    cause: Optional[Cause] = None

    @property
    def ok(self) -> bool:
        return self.state is Applicability.APPLICABLE

    @property
    def coverage(self) -> float:
        return self.n_valid / self.n_total if self.n_total else 0.0

    def describe(self) -> str:
        """What a surface can show without concealing the denominator."""
        if not self.ok:
            return f"unavailable: {self.reason}"
        return (f"{self.median:g}, {self.n_valid} of {self.n_total} "
                f"valid observations")


def _quartiles(values: Sequence[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    median = statistics.median(ordered)
    if len(ordered) < 4:
        # quantiles() needs n >= 2 per cut; below four the halves are the
        # honest answer rather than an interpolation pretending to precision.
        return ordered[0], median, ordered[-1]
    p25, _, p75 = statistics.quantiles(ordered, n=4, method="inclusive")
    return p25, median, p75


def benchmark(metric: str, assessments: Iterable[Assessment],
              min_n: int = MIN_VALID_N,
              min_fraction: float = MIN_VALID_FRACTION) -> Benchmark:
    """Median / P25 / P75 over the surviving valid peer population only.

    Every non-APPLICABLE observation is removed *before* aggregation, so a
    suppressed value cannot shift the statistic of the peers that are valid.
    The denominator counts the whole peer group, so coverage is visible: a
    benchmark resting on 18 of 22 is not the same claim as one resting on
    18 of 400.
    """
    peers = list(assessments)
    n_total = len(peers)
    valid = [a for a in peers if a.ok and a.value is not None]
    n_valid = len(valid)

    if n_total == 0:
        return Benchmark(metric, Applicability.UNAVAILABLE, 0, 0,
                         reason="no peer companies", cause=Cause.SOURCE_MISSING)

    # If every peer failed for the same source reason, say so — the fix is a
    # feed repair, not a wider sector.
    if n_valid == 0 and all(a.cause is Cause.SOURCE_UNHEALTHY for a in peers):
        return Benchmark(metric, Applicability.UNAVAILABLE, n_total, 0,
                         reason="source unhealthy for every peer",
                         cause=Cause.SOURCE_UNHEALTHY)

    if n_valid == 0:
        return Benchmark(metric, Applicability.NOT_MEANINGFUL, n_total, 0,
                         reason="no valid peer observations",
                         cause=Cause.DOMAIN)

    if n_valid < min_n or (n_valid / n_total) < min_fraction:
        return Benchmark(
            metric, Applicability.INSUFFICIENT_DATA, n_total, n_valid,
            reason=(f"{n_valid} of {n_total} valid "
                    f"({n_valid / n_total:.0%}); needs at least {min_n} "
                    f"and {min_fraction:.0%}"),
            cause=Cause.INSUFFICIENT_HISTORY)

    p25, median, p75 = _quartiles([a.value for a in valid])
    return Benchmark(metric, Applicability.APPLICABLE, n_total, n_valid,
                     p25=p25, median=median, p75=p75)


def benchmark_all(metrics: Iterable[str],
                  by_metric: Mapping[str, Iterable[Assessment]],
                  **kwargs) -> dict[str, Benchmark]:
    """Benchmark several metrics over the same peer group, metric by metric.

    Deliberately per metric: within one sector some metrics are meaningful and
    others are not, and a sector-wide verdict would be the industrial-defaults
    error running in reverse.
    """
    return {m: benchmark(m, by_metric.get(m, ()), **kwargs) for m in metrics}


def valid_population(assessments: Iterable[Assessment]) -> list[str]:
    """Which companies actually participate in a cross-sectional statistic.

    Exposed because it is the thing that must survive a persistence round
    trip. A codec can preserve every individual state correctly and still
    change *who participates* once the row is reconstructed, and that would
    move every peer statistic without any single metric looking wrong.
    """
    return sorted(a.metric for a in assessments if a.ok and a.value is not None)
