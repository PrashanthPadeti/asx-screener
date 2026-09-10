"""
Three-valued screening — pass, fail, and could-not-evaluate
===========================================================
"Company failed this screen" and "we cannot evaluate this condition" are
materially different statements, and collapsing the second into the first is
how a screen for buy-and-hold quality came to structurally exclude every
major bank.

The semantics are pinned per criterion type, because they are genuinely
asymmetric and the asymmetry is the point:

    REQUIRED     a positive claim the company must demonstrate.
                 Cannot evaluate -> does not match, surfaced as
                 "could not evaluate", never as "failed".

    EXCLUDED     a negative claim used to reject.
                 Cannot evaluate -> DOES NOT EXCLUDE. An unevaluable
                 predicate must never be the reason a security is rejected.

    PREFERRED    a soft contribution.
                 Cannot evaluate -> no contribution. Not a penalty, and not
                 a zero score that ranks below a genuine zero.

    ORDERED BY   a numeric position.
                 Cannot evaluate -> absent from the ordering entirely. Never
                 coerced to 0, which would sort a source-unhealthy dividend
                 yield as though the company paid nothing, and a bank's
                 suppressed leverage as either the best or worst in the market
                 depending on the direction.

Why REQUIRED and EXCLUDED differ: failing to evaluate must never *reject* a
security, and must never *admit* one on an unproven positive. Those pull in
opposite directions, so one rule cannot serve both.

The distinction between NOT_MEANINGFUL and UNAVAILABLE does not change any of
these behaviours — it changes what the user is told. "Not meaningful for a
bank" and "dividend feed incomplete" are both non-evaluations, and a customer
deserves to know which.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Mapping, Optional, Sequence

from compute.engine.applicability import (
    Applicability,
    Assessment,
    Cause,
    PredicateResult,
    predicate_result,
)


class CriterionType(str, Enum):
    REQUIRED = "required"
    EXCLUDED = "excluded"
    PREFERRED = "preferred"
    ORDERED_BY = "ordered_by"


class Outcome(str, Enum):
    """What a criterion decided about one company."""

    PASS = "pass"
    FAIL = "fail"
    #: Evaluated nothing. Distinct from FAIL for every criterion type, and the
    #: reason it is distinct differs by type — see the module docstring.
    UNEVALUATED = "unevaluated"


@dataclass(frozen=True)
class CriterionOutcome:
    """One criterion's verdict, with why it could not decide when it could not."""

    metric: str
    criterion: CriterionType
    outcome: Outcome
    cause: Optional[Cause] = None
    explanation: str = ""

    @property
    def evaluated(self) -> bool:
        return self.outcome is not Outcome.UNEVALUATED

    @property
    def rejects(self) -> bool:
        """Does this criterion, on its own, keep the company out of results?"""
        if self.outcome is Outcome.UNEVALUATED:
            # Never for EXCLUDED — an unevaluable predicate cannot be the
            # reason to reject. For REQUIRED the company simply has not shown
            # the property, which keeps it out without blaming it.
            return self.criterion is CriterionType.REQUIRED
        if self.criterion is CriterionType.REQUIRED:
            return self.outcome is Outcome.FAIL
        if self.criterion is CriterionType.EXCLUDED:
            return self.outcome is Outcome.PASS
        return False


def _explain(assessment: Assessment) -> str:
    """What to show a customer instead of a silent absence."""
    if assessment.state is Applicability.NOT_MEANINGFUL:
        return f"not meaningful for this company: {assessment.reason}"
    if assessment.cause is Cause.SOURCE_UNHEALTHY:
        return f"could not evaluate: {assessment.reason}"
    if assessment.state is Applicability.INSUFFICIENT_DATA:
        return f"could not evaluate: {assessment.reason}"
    return "could not evaluate: no value available"


def evaluate(assessment: Assessment, criterion: CriterionType,
             test: Callable[[float], bool]) -> CriterionOutcome:
    """Apply one criterion to one assessed metric.

    ``test`` is only ever called on an applicable value, so a predicate
    author cannot accidentally receive None and compare it.
    """
    if predicate_result(assessment) is not PredicateResult.EVALUATED:
        return CriterionOutcome(assessment.metric, criterion,
                                Outcome.UNEVALUATED, assessment.cause,
                                _explain(assessment))

    passed = test(assessment.value)
    return CriterionOutcome(assessment.metric, criterion,
                            Outcome.PASS if passed else Outcome.FAIL)


# ── Whole-screen resolution ───────────────────────────────────────────────────

@dataclass(frozen=True)
class ScreenResult:
    """Whether one company belongs in a screen's results, and what was skipped."""

    asx_code: str
    included: bool
    outcomes: tuple[CriterionOutcome, ...] = ()

    @property
    def unevaluated(self) -> tuple[CriterionOutcome, ...]:
        return tuple(o for o in self.outcomes if not o.evaluated)

    @property
    def preference_score(self) -> int:
        """How many PREFERRED criteria the company actually demonstrated.

        Unevaluated ones contribute nothing — neither a point nor a penalty.
        A company that could not be assessed on a preference is not worse than
        one assessed and found wanting; it is simply unknown on that axis.
        """
        return sum(1 for o in self.outcomes
                   if o.criterion is CriterionType.PREFERRED
                   and o.outcome is Outcome.PASS)

    def caveats(self) -> list[str]:
        """Lines a surface can show so a result never looks more certain than
        it is. A screen that silently skipped three criteria for a company is
        not the same claim as one that evaluated all of them."""
        return [f"{o.metric}: {o.explanation}" for o in self.unevaluated]


def resolve(asx_code: str, outcomes: Iterable[CriterionOutcome]) -> ScreenResult:
    """A company is included unless some criterion rejects it."""
    outcomes = tuple(outcomes)
    return ScreenResult(asx_code, not any(o.rejects for o in outcomes), outcomes)


# ── Ordering ──────────────────────────────────────────────────────────────────

def order_by(rows: Mapping[str, Assessment], descending: bool = True
             ) -> list[str]:
    """Rank companies on one assessed metric, omitting the unevaluable.

    Omitted, not sorted last and not coerced to zero. A source-unhealthy
    dividend yield sorted as 0% reads as "this company pays nothing", and a
    bank's suppressed leverage coerced to 0 becomes the least-levered company
    in the market. Both are assertions the data does not support, and both
    look like ordinary results.
    """
    rankable = {code: a.value for code, a in rows.items()
                if predicate_result(a) is PredicateResult.EVALUATED
                and a.value is not None}
    return sorted(rankable, key=lambda c: rankable[c], reverse=descending)


def excluded_from_ordering(rows: Mapping[str, Assessment]) -> dict[str, str]:
    """The companies the ordering left out, and why — so the omission is
    visible rather than looking like an absence from the universe."""
    return {code: _explain(a) for code, a in rows.items()
            if predicate_result(a) is not PredicateResult.EVALUATED}
