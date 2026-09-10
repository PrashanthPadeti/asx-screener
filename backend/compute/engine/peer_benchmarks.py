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

# These two are an OPERATIONAL SUFFICIENCY POLICY, not a financially
# calibrated truth. They say when this system is willing to publish a peer
# statistic; they carry no statistical authority and are expected to be tuned
# once there is evidence about which sectors and metrics actually behave.

#: Absolute floor. Below this the quartiles describe individuals, not a peer
#: group, whatever the coverage fraction says.
MIN_VALID_N = 5

#: And a share of the *applicable* peers, so a large sector cannot pass the
#: floor on a small unrepresentative remnant. Both must hold.
MIN_VALID_FRACTION = 0.30


@dataclass(frozen=True)
class Benchmark:
    """One sector-metric statistic, with its denominator and its state."""

    metric: str
    state: Applicability
    #: Every company in the peer group, whatever its state.
    n_total_peers: int = 0
    #: Those for which the metric is economically applicable at all — the
    #: total minus the NOT_MEANINGFUL ones. This is the coverage denominator.
    n_applicable_peers: int = 0
    #: Those that produced a usable observation.
    n_valid_peers: int = 0
    p25: Optional[float] = None
    median: Optional[float] = None
    p75: Optional[float] = None
    reason: str = ""
    cause: Optional[Cause] = None

    @property
    def ok(self) -> bool:
        return self.state is Applicability.APPLICABLE

    @property
    def coverage_pct(self) -> float:
        """Valid observations over *applicable* peers, not over survivors.

        Dividing by the surviving sample would report 100% for a sector with
        twenty applicable peers of which six are valid and fourteen
        unavailable — the number would describe the sample rather than the
        gap it was meant to expose. Out-of-domain peers are excluded from the
        denominator instead, because a bank was never going to contribute a
        debt-to-equity observation and its absence is not a coverage failure.
        """
        if not self.n_applicable_peers:
            return 0.0
        return 100.0 * self.n_valid_peers / self.n_applicable_peers

    def describe(self) -> str:
        """What a surface can show without concealing the denominator."""
        if not self.ok:
            return f"unavailable: {self.reason}"
        return (f"{self.median:g}, {self.n_valid_peers} of "
                f"{self.n_applicable_peers} valid observations")


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

    # Out-of-domain peers leave the denominator entirely: a bank was never
    # going to contribute a debt-to-equity observation, and counting its
    # absence as a coverage failure would withhold benchmarks that are fine.
    applicable = [a for a in peers if not a.suppressed]
    n_applicable = len(applicable)

    valid = [a for a in applicable if a.ok and a.value is not None]
    n_valid = len(valid)

    if n_total == 0:
        return Benchmark(metric, Applicability.UNAVAILABLE,
                         reason="no peer companies", cause=Cause.SOURCE_MISSING)

    if n_applicable == 0:
        return Benchmark(metric, Applicability.NOT_MEANINGFUL, n_total, 0, 0,
                         reason="metric is out of domain for every peer",
                         cause=Cause.DOMAIN)

    # If every applicable peer failed for the same source reason, say so — the
    # remedy is a feed repair, not a wider sector.
    if n_valid == 0 and all(a.cause is Cause.SOURCE_UNHEALTHY for a in applicable):
        return Benchmark(metric, Applicability.UNAVAILABLE, n_total, n_applicable, 0,
                         reason="source unhealthy for every applicable peer",
                         cause=Cause.SOURCE_UNHEALTHY)

    if n_valid == 0:
        return Benchmark(metric, Applicability.UNAVAILABLE, n_total, n_applicable, 0,
                         reason="no valid observations among applicable peers",
                         cause=Cause.SOURCE_MISSING)

    coverage = n_valid / n_applicable
    if n_valid < min_n or coverage < min_fraction:
        return Benchmark(
            metric, Applicability.INSUFFICIENT_DATA, n_total, n_applicable, n_valid,
            reason=(f"{n_valid} of {n_applicable} applicable peers valid "
                    f"({coverage:.0%}); needs at least {min_n} "
                    f"and {min_fraction:.0%}"),
            cause=Cause.INSUFFICIENT_HISTORY)

    p25, median, p75 = _quartiles([a.value for a in valid])
    return Benchmark(metric, Applicability.APPLICABLE, n_total, n_applicable,
                     n_valid, p25=p25, median=median, p75=p75)


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
