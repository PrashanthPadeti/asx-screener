#!/usr/bin/env python
"""
Governed momentum must fail closed when its ungoverned inputs are absent
=======================================================================
`momentum_score` is one of the 72 governed metrics. Its five constituents are
NOT governed -- they are technical columns served from `market.daily_metrics`:

    return_1m, return_3m, return_6m, rsi_14, adx_14

A governed output built from ungoverned inputs is only safe if the absence of
those inputs propagates into a governed cause. Otherwise the fix for stale
serving (see docs/p0a_reopened_2026-10-03_momentum_input_freshness.md) would
trade a score computed from three-month-old evidence for a score that is
simply, silently, gone.

Production evidence on 4 Oct 2026, run 6, 2,121 served rows:

    all five inputs absent        21
    scored anyway                  0
    carrying a governed state     21

    {"cause": "source_missing", "state": "unavailable",
     "reason": "required constituents unavailable:
                adx_14, return_1m, return_3m, return_6m, rsi_14"}

That measurement proved the contract held on one day's data. This asserts it
as a property, so it keeps holding -- and so the stale-serving patch has
regression coverage that does not depend on an artificial stale row surviving
a `technical_compute` pass.

Run:  python tests/test_momentum_fails_closed.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.applicability import Applicability, Cause     # noqa: E402
from compute.engine.factor_model import (                          # noqa: E402
    Assessment, FACTOR_MODEL_V2, effective_weights,
)

MOMENTUM = FACTOR_MODEL_V2["momentum"]
INPUTS = tuple(c.metric for c in MOMENTUM.constituents)


def _assess(state: Applicability, cause=None, value=None) -> dict:
    return {m: Assessment(metric=m, state=state, value=value, cause=cause)
            for m in INPUTS}


def test_momentum_is_built_from_ungoverned_technical_columns():
    """The premise. If this changes, the rest of the file is about nothing."""
    from compute.engine.metric_states import GOVERNED_METRICS
    governed = GOVERNED_METRICS["FACTOR_MODEL_V2"]
    assert "momentum_score" in governed, "momentum_score is no longer governed"
    ungoverned = [m for m in INPUTS if m not in governed]
    assert ungoverned == list(INPUTS), (
        f"some momentum constituents are now governed ({ungoverned}); the "
        "dependency this file guards has changed shape")


def test_all_inputs_absent_yields_unavailable_with_a_cause():
    ew = effective_weights(MOMENTUM, _assess(Applicability.UNAVAILABLE,
                                             Cause.SOURCE_MISSING))
    assert ew.state is Applicability.UNAVAILABLE, (
        f"momentum resolved to {ew.state} with every constituent absent")
    assert ew.cause is not None, (
        "momentum is unavailable with no cause -- a governed metric that "
        "vanishes without explanation is the second defect this guards")
    assert not ew.weights, (
        f"momentum kept weights {ew.weights} while unavailable, so something "
        "downstream can still compute a score from nothing")
    for metric in INPUTS:
        assert metric in ew.reason, (
            f"the reason does not name {metric}; an operator cannot tell "
            f"which input is missing from {ew.reason!r}")


def test_one_absent_input_is_enough():
    """No renormalisation around a missing signal.

    A momentum score computed from four of five constituents is a different
    model wearing this one's name. The spec's own docstring says so; this
    makes it a test rather than a comment.
    """
    assessments = _assess(Applicability.APPLICABLE, value=1.0)
    assessments["rsi_14"] = Assessment(metric="rsi_14",
                                       state=Applicability.UNAVAILABLE,
                                       cause=Cause.SOURCE_MISSING)
    ew = effective_weights(MOMENTUM, assessments)
    assert ew.state is Applicability.UNAVAILABLE, (
        "momentum renormalised around a missing constituent and scored anyway")
    assert "rsi_14" in ew.reason


def test_insufficient_data_also_fails_closed():
    """A short history is not a low score.

    The 72 instruments with almost no price history reach this path, and the
    distinction matters: INSUFFICIENT_DATA says the observation window is not
    satisfied, which is a different claim from the source being missing.
    """
    ew = effective_weights(MOMENTUM, _assess(Applicability.INSUFFICIENT_DATA,
                                             Cause.INSUFFICIENT_HISTORY))
    assert ew.state is Applicability.UNAVAILABLE
    assert ew.cause is Cause.INSUFFICIENT_HISTORY, (
        f"the cause was flattened to {ew.cause}; an operator needs to know "
        "whether waiting will help")


def test_the_control_still_scores():
    """Mutation control in the other direction.

    Without it, a rule that suppressed momentum unconditionally would pass
    every assertion above.
    """
    ew = effective_weights(MOMENTUM, _assess(Applicability.APPLICABLE,
                                             value=1.0))
    assert ew.state is Applicability.APPLICABLE, (
        f"momentum is {ew.state} with every constituent applicable")
    assert ew.weights, "momentum produced no weights from valid evidence"


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}\n        {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
