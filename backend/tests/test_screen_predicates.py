"""
Three-valued screening — the table, pinned
==========================================
    Criterion    PASS        FAIL          UNAVAILABLE
    REQUIRED     matches     no match      no match, "could not evaluate"
    EXCLUDED     excludes    no exclude    DOES NOT EXCLUDE
    PREFERRED    contributes no contrib    no contrib, not a penalty
    ORDERED BY   ranks       ranks         absent, never coerced to 0

Pinned per criterion type because the semantics are genuinely asymmetric:
failing to evaluate must never *reject* a security, and must never *admit*
one on an unproven positive. Those pull opposite ways, so one rule cannot
serve both.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_screen_predicates.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Assessment,
    Cause,
    Domain,
    Observation,
    assess,
    unhealthy,
)
from compute.engine.screen_predicates import (  # noqa: E402
    CriterionType,
    Outcome,
    evaluate,
    excluded_from_ordering,
    order_by,
    resolve,
)

BANK_DE = assess("debt_to_equity", 4.6, Domain.BANK)          # NOT_MEANINGFUL
BANK_ROE = assess("roe", 0.1284, Domain.BANK, Observation(equity=8e10))
BROKEN_YIELD = unhealthy("grossed_up_yield", "dividend feed incomplete")
IND_DE = assess("debt_to_equity", 0.4, Domain.GENERAL_CORPORATE)


def lt(threshold):
    return lambda v: v < threshold


def gt(threshold):
    return lambda v: v > threshold


# ── REQUIRED ──────────────────────────────────────────────────────────────────

def test_required_passes_and_fails_normally():
    assert evaluate(IND_DE, CriterionType.REQUIRED, lt(1.5)).outcome is Outcome.PASS
    assert evaluate(IND_DE, CriterionType.REQUIRED, lt(0.1)).outcome is Outcome.FAIL


def test_required_on_an_unevaluable_metric_does_not_match_but_does_not_blame():
    o = evaluate(BANK_DE, CriterionType.REQUIRED, lt(1.5))

    assert o.outcome is Outcome.UNEVALUATED, "not FAIL — nothing was compared"
    assert o.rejects, "the company has not demonstrated the property"
    assert "not meaningful" in o.explanation


def test_required_distinguishes_not_meaningful_from_a_broken_feed():
    """Both are non-evaluations; the customer deserves to know which."""
    nm = evaluate(BANK_DE, CriterionType.REQUIRED, lt(1.5))
    broken = evaluate(BROKEN_YIELD, CriterionType.REQUIRED, gt(0.04))

    assert nm.cause is Cause.DOMAIN
    assert broken.cause is Cause.SOURCE_UNHEALTHY
    assert "not meaningful" in nm.explanation
    assert "dividend feed incomplete" in broken.explanation


# ── EXCLUDED · the rule that started all of this ─────────────────────────────

def test_excluded_never_rejects_on_a_metric_it_could_not_evaluate():
    """Observed live: 'Top 25 stocks to buy and hold forever', no bank in it.

        EXCLUDED  debt_to_equity gt 1.5
        CBA       D/E 4.6x -> "fails", excluded

    The predicate never evaluated. It cannot be the reason to reject.
    """
    o = evaluate(BANK_DE, CriterionType.EXCLUDED, gt(1.5))

    assert o.outcome is Outcome.UNEVALUATED
    assert not o.rejects, "an unevaluable predicate cannot exclude a security"


def test_excluded_still_rejects_when_it_genuinely_evaluates():
    """Applicability must not disable real filters."""
    levered = assess("debt_to_equity", 3.0, Domain.GENERAL_CORPORATE)
    o = evaluate(levered, CriterionType.EXCLUDED, gt(1.5))

    assert o.outcome is Outcome.PASS and o.rejects


def test_excluded_does_not_reject_when_the_test_is_false():
    o = evaluate(IND_DE, CriterionType.EXCLUDED, gt(1.5))
    assert o.outcome is Outcome.FAIL and not o.rejects


def test_required_and_excluded_treat_the_same_non_evaluation_differently():
    """The asymmetry, asserted directly."""
    req = evaluate(BANK_DE, CriterionType.REQUIRED, lt(1.5))
    exc = evaluate(BANK_DE, CriterionType.EXCLUDED, gt(1.5))

    assert req.outcome is exc.outcome is Outcome.UNEVALUATED
    assert req.rejects and not exc.rejects


# ── PREFERRED ─────────────────────────────────────────────────────────────────

def test_preferred_never_rejects():
    for assessment in (BANK_DE, IND_DE, BROKEN_YIELD):
        assert not evaluate(assessment, CriterionType.PREFERRED,
                            lt(1.5)).rejects


def test_an_unevaluable_preference_is_not_a_penalty():
    demonstrated = resolve("IND", [
        evaluate(IND_DE, CriterionType.PREFERRED, lt(1.5))])
    unknown = resolve("CBA", [
        evaluate(BANK_DE, CriterionType.PREFERRED, lt(1.5))])
    failed = resolve("LEV", [
        evaluate(assess("debt_to_equity", 3.0, Domain.GENERAL_CORPORATE),
                 CriterionType.PREFERRED, lt(1.5))])

    assert demonstrated.preference_score == 1
    assert unknown.preference_score == 0
    assert failed.preference_score == 0
    assert unknown.included and failed.included, "neither is rejected"
    assert unknown.caveats() and not failed.caveats(), \
        "only the unknown one carries a caveat — the failure is a real result"


# ── ORDERED BY · never coerced to zero ───────────────────────────────────────

def test_ordering_omits_the_unevaluable_rather_than_sorting_it_last():
    rows = {
        "AAA": assess("grossed_up_yield", 0.06, Domain.GENERAL_CORPORATE),
        "BBB": assess("grossed_up_yield", 0.04, Domain.GENERAL_CORPORATE),
        "CCC": BROKEN_YIELD,
    }
    assert order_by(rows) == ["AAA", "BBB"]
    assert "CCC" not in order_by(rows, descending=False)


def test_a_broken_feed_does_not_sort_as_a_zero_yield():
    rows = {
        "PAYER": assess("grossed_up_yield", 0.05, Domain.GENERAL_CORPORATE),
        "NONE": assess("grossed_up_yield", 0.0, Domain.GENERAL_CORPORATE),
        "BROKEN": BROKEN_YIELD,
    }
    ascending = order_by(rows, descending=False)

    assert ascending == ["NONE", "PAYER"], "a genuine zero still ranks"
    assert "BROKEN" not in ascending, \
        "coercing it to 0 would assert the company pays nothing"


def test_a_suppressed_leverage_does_not_become_the_best_in_the_market():
    """Coerced to 0 and sorted ascending, a bank's NM D/E leads the market."""
    rows = {
        "IND1": assess("debt_to_equity", 0.2, Domain.GENERAL_CORPORATE),
        "IND2": assess("debt_to_equity", 0.8, Domain.GENERAL_CORPORATE),
        "CBA": BANK_DE,
    }
    assert order_by(rows, descending=False) == ["IND1", "IND2"]
    assert order_by(rows, descending=True) == ["IND2", "IND1"], \
        "and not the worst either"


def test_the_omissions_are_reportable_not_silent():
    rows = {"AAA": assess("grossed_up_yield", 0.06, Domain.GENERAL_CORPORATE),
            "CCC": BROKEN_YIELD, "CBA": BANK_DE}
    omitted = excluded_from_ordering(rows)

    assert set(omitted) == {"CCC", "CBA"}
    assert "dividend feed incomplete" in omitted["CCC"]
    assert "not meaningful" in omitted["CBA"]


# ── Whole screens ─────────────────────────────────────────────────────────────

def test_a_bank_survives_the_buy_and_hold_screen():
    """The AI Query fixture, as a whole screen rather than one predicate."""
    outcomes = [
        evaluate(BANK_DE, CriterionType.EXCLUDED, gt(1.5)),
        evaluate(assess("piotroski_f_score", 3.0, Domain.BANK),
                 CriterionType.EXCLUDED, lambda v: v < 5),
        evaluate(assess("altman_z_score", -0.15, Domain.BANK),
                 CriterionType.EXCLUDED, lambda v: v < 1.5),
        evaluate(BANK_ROE, CriterionType.REQUIRED, gt(0.10)),
    ]
    result = resolve("CBA", outcomes)

    assert result.included, "three unevaluable exclusions cannot reject it"
    assert len(result.unevaluated) == 3
    assert len(result.caveats()) == 3


def test_a_screen_that_evaluated_everything_carries_no_caveats():
    outcomes = [evaluate(IND_DE, CriterionType.EXCLUDED, gt(1.5)),
                evaluate(IND_DE, CriterionType.REQUIRED, lt(1.0))]
    result = resolve("IND", outcomes)

    assert result.included and not result.caveats()


def test_a_genuine_failure_still_excludes():
    outcomes = [evaluate(assess("debt_to_equity", 3.0,
                                Domain.GENERAL_CORPORATE),
                         CriterionType.EXCLUDED, gt(1.5))]
    assert not resolve("LEV", outcomes).included


def test_a_required_criterion_nobody_could_evaluate_keeps_the_company_out():
    outcomes = [evaluate(BROKEN_YIELD, CriterionType.REQUIRED, gt(0.05))]
    result = resolve("XYZ", outcomes)

    assert not result.included, "it has not shown the property"
    assert result.caveats(), "but the reason is stated, not implied as failure"


def test_the_test_function_never_sees_a_none():
    """A predicate author cannot accidentally compare None."""
    def strict(v):
        assert v is not None, "evaluate() called the test on a missing value"
        return v > 0

    for assessment in (BANK_DE, BROKEN_YIELD):
        evaluate(assessment, CriterionType.REQUIRED, strict)


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
