"""
Three-state anomaly evaluation
==============================
An anomaly is an assertion about a company, published to a page and — once
the outbound worker is repaired — to an inbox. So the difference between "the
rule did not fire" and "the rule could not be evaluated" is not a nicety: the
first is a finding, the second is a gap, and only one of them should reduce
the count of anomalies a customer sees without explanation.

    FIRED          every required operand applicable, predicate true
    NOT_FIRED      every required operand applicable, predicate false
    NOT_EVALUATED  some required operand non-meaningful or unavailable

The third is never collapsed into the second. When the dividend feed breaks
you want to read "812 DIVIDEND_YIELD_SPIKE evaluations skipped:
source_unhealthy", not merely notice that there are fewer anomalies than
usual and wonder why.

Two further rules carried over from the factor and peer engines, because an
anomaly threshold is a cross-sectional statistic like any other:

  * a population-derived threshold — percentile, z-score, median — is built
    from masked observations only. A suppressed value must not sit in the
    reference distribution even when the target company's own operands are
    perfectly valid.
  * rules declare **canonical** metric identity. Given how often
    ``ev_to_ebitda`` has already surfaced, a rule naming a physical storage
    column is rejected rather than resolved.

And the one that is not about evaluation at all: an existing active anomaly
whose rule can no longer be evaluated must not remain asserted. "The new
evaluator does not fire it" is insufficient — yesterday's flag is still on
the page, still claiming something today's data cannot support.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Mapping, Optional, Sequence

from compute.engine.applicability import (
    Assessment,
    Cause,
    PredicateResult,
    predicate_result,
)
from compute.engine.metric_registry import normalise


class AnomalyOutcome(str, Enum):
    FIRED = "fired"
    NOT_FIRED = "not_fired"
    NOT_EVALUATED = "not_evaluated"


class RuleError(Exception):
    """A rule that cannot be evaluated honestly as written."""


@dataclass(frozen=True)
class AnomalyRule:
    """One detector, declared over canonical metric identity."""

    flag_type: str
    required_metrics: tuple[str, ...]
    predicate: Callable[[Mapping[str, float]], bool]
    #: Metric whose peer distribution the threshold is drawn from, if any.
    population_metric: Optional[str] = None

    def __post_init__(self) -> None:
        for metric in self.required_metrics:
            if normalise(metric) != metric:
                raise RuleError(
                    f"{self.flag_type}: {metric!r} is a storage spelling or an "
                    f"alias; declare {normalise(metric)!r}. A rule naming a "
                    f"physical column is how ev_to_ebitda escaped assessment.")
        if self.population_metric and normalise(self.population_metric) != \
                self.population_metric:
            raise RuleError(
                f"{self.flag_type}: population metric must be canonical")


@dataclass(frozen=True)
class AnomalyResult:
    """One rule's verdict on one company."""

    flag_type: str
    asx_code: str
    outcome: AnomalyOutcome
    #: Every reason evaluation was impossible, not just the first. Discarding
    #: the others would hide that a rule is blocked on two different problems.
    causes: frozenset = frozenset()
    blocked_on: tuple[str, ...] = ()
    reason: str = ""

    @property
    def evaluated(self) -> bool:
        return self.outcome is not AnomalyOutcome.NOT_EVALUATED

    @property
    def sorted_causes(self) -> tuple[str, ...]:
        """The cause set in a stable order, for logs and persistence.

        A frozenset deduplicates but does not order, and an unordered set
        rendered into a log or a JSON payload produces different text on
        different runs for identical facts — which makes a diff of two runs
        unreadable and a stored payload uncomparable.
        """
        return tuple(sorted(c.value for c in self.causes))

    @property
    def primary_cause(self) -> Optional[Cause]:
        """A single cause for a one-line log, without discarding the set.

        Source failure outranks domain: if a feed is down, that is the thing
        an operator acts on, and it will clear the moment the feed returns.

        **Presentation only.** It never decides whether the result is
        NOT_EVALUATED, never changes what is persisted, and never removes a
        cause from ``causes``. Ranking one cause above another is a choice
        about what to show an operator first, and choices about display must
        not become choices about semantics.
        """
        for cause in (Cause.SOURCE_UNHEALTHY, Cause.SOURCE_MISSING,
                      Cause.INSUFFICIENT_HISTORY, Cause.OBSERVATION,
                      Cause.DOMAIN):
            if cause in self.causes:
                return cause
        return None


@dataclass
class SkipTally:
    """rule_type x cause -> count, per detector run.

    Aggregate rather than a row per failed evaluation: 2,152 companies times
    seven rules is a lot of rows to say one thing. What an operator needs is
    the shape of the gap, not an inventory of it.
    """

    counts: Counter = field(default_factory=Counter)

    def record(self, result: AnomalyResult) -> None:
        if result.evaluated:
            return
        cause = result.primary_cause
        self.counts[(result.flag_type, cause.value if cause else "unknown")] += 1

    def render(self) -> list[str]:
        return [f"{count} {flag_type} evaluations skipped: {cause}"
                for (flag_type, cause), count in
                sorted(self.counts.items(), key=lambda kv: -kv[1])]

    def total(self) -> int:
        return sum(self.counts.values())


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_rule(rule: AnomalyRule, asx_code: str,
                  assessments: Mapping[str, Assessment],
                  population: Optional[Sequence[float]] = None) -> AnomalyResult:
    """Apply one rule to one company.

    The predicate is only ever called when every required operand is
    applicable, so a rule author cannot receive None and compare it — the same
    guarantee ``screen_predicates.evaluate`` gives.
    """
    causes: set = set()
    blocked: list[str] = []
    values: dict[str, float] = {}

    for metric in rule.required_metrics:
        assessment = assessments.get(metric)
        if assessment is None:
            blocked.append(metric)
            causes.add(Cause.SOURCE_MISSING)
            continue
        if predicate_result(assessment) is not PredicateResult.EVALUATED:
            blocked.append(metric)
            if assessment.cause is not None:
                causes.add(assessment.cause)
            continue
        values[metric] = assessment.value

    if blocked:
        return AnomalyResult(
            rule.flag_type, asx_code, AnomalyOutcome.NOT_EVALUATED,
            frozenset(causes), tuple(sorted(blocked)),
            f"cannot evaluate: {', '.join(sorted(blocked))}")

    if rule.population_metric is not None and not population:
        return AnomalyResult(
            rule.flag_type, asx_code, AnomalyOutcome.NOT_EVALUATED,
            frozenset({Cause.SOURCE_MISSING}), (rule.population_metric,),
            "cannot evaluate: no valid peer population for the threshold")

    fired = rule.predicate(values)
    return AnomalyResult(
        rule.flag_type, asx_code,
        AnomalyOutcome.FIRED if fired else AnomalyOutcome.NOT_FIRED)


def valid_population(metric: str,
                     assessments_by_code: Mapping[str, Mapping[str, Assessment]]
                     ) -> list[float]:
    """The reference distribution a threshold may be drawn from.

    Masked before the statistic, exactly as with factor percentiles and sector
    medians. A suppressed observation left in the distribution moves the
    threshold for every company evaluated against it, including the ones whose
    own operands are entirely valid — so the contamination reaches companies
    the rule was right about.
    """
    canonical = normalise(metric)
    out = []
    for assessments in assessments_by_code.values():
        assessment = assessments.get(canonical)
        if assessment is not None and \
                predicate_result(assessment) is PredicateResult.EVALUATED:
            out.append(assessment.value)
    return out


def evaluate_all(rules: Sequence[AnomalyRule],
                 assessments_by_code: Mapping[str, Mapping[str, Assessment]],
                 ) -> tuple[list[AnomalyResult], SkipTally]:
    """Every rule against every company, with the skipped shape recorded."""
    populations = {
        rule.population_metric: valid_population(rule.population_metric,
                                                 assessments_by_code)
        for rule in rules if rule.population_metric
    }

    results: list[AnomalyResult] = []
    tally = SkipTally()

    for asx_code, assessments in assessments_by_code.items():
        for rule in rules:
            result = evaluate_rule(
                rule, asx_code, assessments,
                populations.get(rule.population_metric))
            results.append(result)
            tally.record(result)

    return results, tally


# ── Reconciling what is already asserted ─────────────────────────────────────

@dataclass(frozen=True)
class ActiveFlag:
    """An anomaly currently asserted on the product."""

    flag_type: str
    asx_code: str


class WithdrawalReason(str, Enum):
    """Why an active flag stopped being asserted.

    None of these keeps the flag on the active surface. They differ in the
    history, and the history matters: "the condition no longer holds" and
    "we can no longer check" are different events, and collapsing them
    rewrites a feed outage as a resolved anomaly. Anyone later measuring
    anomaly quality, or asking why a flag vanished, would be reading fiction.
    """

    FALSE = "withdrawn_false"                    # evaluated, no longer holds
    UNAVAILABLE = "withdrawn_unavailable"        # cannot currently substantiate
    NOT_MEANINGFUL = "withdrawn_not_meaningful"  # rule no longer applies


@dataclass(frozen=True)
class Withdrawal:
    """One flag leaving the active surface, with the reason preserved."""

    flag: ActiveFlag
    reason: WithdrawalReason
    cause: Optional[Cause] = None
    detail: str = ""

    @property
    def was_resolved(self) -> bool:
        """True only when the condition genuinely stopped holding.

        The property a quality metric should count. Everything else is a gap
        in the evidence wearing the same shape.
        """
        return self.reason is WithdrawalReason.FALSE


def _withdrawal_reason(result: AnomalyResult) -> WithdrawalReason:
    if result.outcome is AnomalyOutcome.NOT_FIRED:
        return WithdrawalReason.FALSE
    if result.primary_cause is Cause.DOMAIN:
        return WithdrawalReason.NOT_MEANINGFUL
    return WithdrawalReason.UNAVAILABLE


def deactivations(active: Iterable[ActiveFlag],
                  results: Sequence[AnomalyResult]) -> list[Withdrawal]:
    """Flags that must be withdrawn because they can no longer be substantiated.

    "The new evaluator does not fire it" is not enough. Yesterday's flag is
    still on the page asserting something today's data cannot support, and a
    detector that only ever inserts will leave it there indefinitely. Both
    NOT_FIRED and NOT_EVALUATED withdraw it — the first because the finding is
    gone, the second because it is unproven, and an unproven assertion is not
    a weaker assertion, it is not one.

    The reason travels with the withdrawal so the audit trail keeps the
    distinction the active surface deliberately drops.
    """
    by_key = {(r.flag_type, r.asx_code): r for r in results}

    out: list[Withdrawal] = []
    for flag in active:
        result = by_key.get((flag.flag_type, flag.asx_code))
        if result is None:
            # This run never considered the company; a partial run must not
            # withdraw what it did not examine.
            continue
        if result.outcome is AnomalyOutcome.FIRED:
            continue
        out.append(Withdrawal(flag, _withdrawal_reason(result),
                              result.primary_cause, result.reason))
    return out
