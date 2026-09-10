"""
Anomaly evaluation — three states, and the flag that must be withdrawn
======================================================================
The pinned behaviours:

  all operands applicable + predicate true   -> FIRED
  all operands applicable + predicate false  -> NOT_FIRED
  any operand NM or unavailable              -> NOT_EVALUATED, with cause
  population-derived threshold               -> masked before the statistic
  several non-evaluation causes              -> the set is preserved
  active flag becomes non-evaluable          -> withdrawn, not left asserted
  source-wide failure                        -> counted, no new anomalies
  run mismatch / unsupported model           -> NOT_EVALUATED, fail closed

The last one is enforced upstream by RunScope and governed_for; here it
appears as the ordinary consequence of an operand that never arrived.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_anomaly_eval.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Cause,
    Domain,
    Observation,
    assess,
    unhealthy,
)
from compute.engine.anomaly_eval import (  # noqa: E402
    ActiveFlag,
    AnomalyOutcome,
    AnomalyRule,
    RuleError,
    SkipTally,
    deactivations,
    evaluate_all,
    evaluate_rule,
    valid_population,
)

HIGH_YIELD = AnomalyRule(
    "HIGH_GROSSED_UP_YIELD", ("grossed_up_yield",),
    lambda v: v["grossed_up_yield"] > 0.12)

OVERBOUGHT_WEAK = AnomalyRule(
    "RSI_OVERBOUGHT_WEAK", ("rsi_14", "piotroski_f_score"),
    lambda v: v["rsi_14"] > 70 and v["piotroski_f_score"] < 4)


def industrial(yield_=0.05, rsi=75.0, piotroski=3.0) -> dict:
    return {
        "grossed_up_yield": assess("grossed_up_yield", yield_,
                                   Domain.GENERAL_CORPORATE),
        "rsi_14": assess("rsi_14", rsi, Domain.GENERAL_CORPORATE),
        "piotroski_f_score": assess("piotroski_f_score", piotroski,
                                    Domain.GENERAL_CORPORATE),
    }


def bank() -> dict:
    return {
        "grossed_up_yield": assess("grossed_up_yield", 0.045, Domain.BANK),
        "rsi_14": assess("rsi_14", 75.0, Domain.BANK),
        "piotroski_f_score": assess("piotroski_f_score", 3.0, Domain.BANK),
    }


# ── The three states ──────────────────────────────────────────────────────────

def test_an_applicable_true_predicate_fires():
    r = evaluate_rule(HIGH_YIELD, "AAA", industrial(yield_=0.15))
    assert r.outcome is AnomalyOutcome.FIRED and r.evaluated


def test_an_applicable_false_predicate_does_not_fire():
    r = evaluate_rule(HIGH_YIELD, "AAA", industrial(yield_=0.05))
    assert r.outcome is AnomalyOutcome.NOT_FIRED and r.evaluated


def test_a_suppressed_operand_makes_the_rule_unevaluable():
    """CBA's Piotroski is out of domain, so the combined rule cannot fire —
    and must not silently report 'no anomaly', which reads as a clean bill."""
    r = evaluate_rule(OVERBOUGHT_WEAK, "CBA", bank())

    assert r.outcome is AnomalyOutcome.NOT_EVALUATED
    assert not r.evaluated
    assert r.blocked_on == ("piotroski_f_score",)
    assert Cause.DOMAIN in r.causes


def test_a_broken_feed_makes_the_yield_rule_unevaluable():
    row = industrial()
    row["grossed_up_yield"] = unhealthy("grossed_up_yield", "feed incomplete")
    r = evaluate_rule(HIGH_YIELD, "AAA", row)

    assert r.outcome is AnomalyOutcome.NOT_EVALUATED
    assert r.primary_cause is Cause.SOURCE_UNHEALTHY


def test_a_missing_operand_is_not_evaluated_rather_than_assumed():
    r = evaluate_rule(HIGH_YIELD, "AAA", {})
    assert r.outcome is AnomalyOutcome.NOT_EVALUATED
    assert r.blocked_on == ("grossed_up_yield",)


def test_the_predicate_never_receives_a_missing_value():
    def strict(values):
        assert all(v is not None for v in values.values())
        return True

    rule = AnomalyRule("STRICT", ("grossed_up_yield",), strict)
    evaluate_rule(rule, "CBA", {
        "grossed_up_yield": unhealthy("grossed_up_yield", "feed")})


# ── Several causes are preserved, not reduced to the first ───────────────────

def test_every_blocking_cause_is_kept():
    row = industrial()
    row["rsi_14"] = unhealthy("rsi_14", "price feed incomplete")
    row["piotroski_f_score"] = assess("piotroski_f_score", 3.0, Domain.BANK)

    r = evaluate_rule(OVERBOUGHT_WEAK, "MIX", row)

    assert r.causes == frozenset({Cause.SOURCE_UNHEALTHY, Cause.DOMAIN})
    assert r.blocked_on == ("piotroski_f_score", "rsi_14")


def test_source_failure_outranks_domain_for_the_one_line_summary():
    """An operator acts on the feed; it clears when the feed returns."""
    row = industrial()
    row["rsi_14"] = unhealthy("rsi_14", "price feed incomplete")
    row["piotroski_f_score"] = assess("piotroski_f_score", 3.0, Domain.BANK)

    r = evaluate_rule(OVERBOUGHT_WEAK, "MIX", row)
    assert r.primary_cause is Cause.SOURCE_UNHEALTHY
    assert Cause.DOMAIN in r.causes, "without discarding the other"


# ── Population-derived thresholds are masked first ───────────────────────────

def test_the_reference_population_excludes_suppressed_observations():
    rows = {
        "IND1": industrial(yield_=0.03),
        "IND2": industrial(yield_=0.05),
        "CBA": {"grossed_up_yield": assess("grossed_up_yield", 0.9,
                                           Domain.GENERAL_CORPORATE,
                                           Observation())},
        "FEED": {"grossed_up_yield": unhealthy("grossed_up_yield", "broken")},
    }
    population = valid_population("grossed_up_yield", rows)

    assert sorted(population) == [0.03, 0.05, 0.9]
    assert len(population) == 3, "the source-unhealthy company contributes none"


def test_a_suppressed_peer_cannot_move_a_percentile_threshold():
    """The contamination reaches companies the rule was right about."""
    clean = {f"IND{i}": industrial(yield_=0.02 + i * 0.01) for i in range(5)}
    contaminated = dict(clean)
    contaminated["CBA"] = {
        "grossed_up_yield": assess("grossed_up_yield", 4.6, Domain.BANK)}

    # A bank's grossed_up_yield is applicable, so use a genuinely suppressed
    # metric for the contamination: piotroski for a bank.
    pop_clean = valid_population("piotroski_f_score", clean)
    pop_dirty = valid_population("piotroski_f_score", {
        **clean,
        "CBA": {"piotroski_f_score": assess("piotroski_f_score", 9.0,
                                            Domain.BANK)}})

    assert pop_clean == pop_dirty, \
        "an out-of-domain 9/9 must not enter the reference distribution"


def test_a_rule_with_no_valid_population_cannot_evaluate():
    rule = AnomalyRule("PCTL", ("grossed_up_yield",),
                       lambda v: True, population_metric="grossed_up_yield")
    r = evaluate_rule(rule, "AAA", industrial(), population=[])

    assert r.outcome is AnomalyOutcome.NOT_EVALUATED
    assert "peer population" in r.reason


# ── Canonical identity only ───────────────────────────────────────────────────

def test_a_rule_naming_a_storage_column_is_rejected():
    try:
        AnomalyRule("BAD", ("ev_to_ebitda",), lambda v: True)
    except RuleError as e:
        assert "ev_ebitda" in str(e)
    else:
        raise AssertionError("a rule must not name a physical column")


def test_a_rule_naming_an_alias_is_rejected():
    try:
        AnomalyRule("BAD", ("piotroski",), lambda v: True)
    except RuleError as e:
        assert "piotroski_f_score" in str(e)
    else:
        raise AssertionError("an alias is not a canonical identity")


def test_a_population_metric_must_also_be_canonical():
    try:
        AnomalyRule("BAD", ("roe",), lambda v: True,
                    population_metric="return_on_equity")
    except RuleError:
        pass
    else:
        raise AssertionError("the population metric must be canonical too")


# ── The skipped tally ─────────────────────────────────────────────────────────

def test_skips_are_counted_by_rule_and_cause():
    rows = {}
    for i in range(812):
        row = industrial()
        row["grossed_up_yield"] = unhealthy("grossed_up_yield", "feed incomplete")
        rows[f"C{i}"] = row

    results, tally = evaluate_all([HIGH_YIELD], rows)

    assert tally.counts[("HIGH_GROSSED_UP_YIELD", "source_unhealthy")] == 812
    assert "812 HIGH_GROSSED_UP_YIELD evaluations skipped: source_unhealthy" \
        in tally.render()


def test_a_source_wide_failure_creates_no_anomalies():
    rows = {}
    for i in range(20):
        row = industrial(yield_=0.99)          # would fire, if it could
        row["grossed_up_yield"] = unhealthy("grossed_up_yield", "feed incomplete")
        rows[f"C{i}"] = row

    results, tally = evaluate_all([HIGH_YIELD], rows)

    assert not [r for r in results if r.outcome is AnomalyOutcome.FIRED]
    assert tally.total() == 20


def test_an_evaluated_run_records_no_skips():
    rows = {f"C{i}": industrial(yield_=0.05) for i in range(5)}
    _, tally = evaluate_all([HIGH_YIELD], rows)
    assert tally.total() == 0 and tally.render() == []


# ── Existing active flags must be withdrawn ──────────────────────────────────

def test_an_active_flag_is_withdrawn_when_the_rule_stops_firing():
    active = [ActiveFlag("HIGH_GROSSED_UP_YIELD", "AAA")]
    results, _ = evaluate_all([HIGH_YIELD], {"AAA": industrial(yield_=0.05)})

    assert deactivations(active, results) == active


def test_an_active_flag_is_withdrawn_when_the_rule_becomes_unevaluable():
    """The case that matters. 'The new evaluator does not fire it' is not
    enough — yesterday's flag is still on the page asserting something today's
    data cannot support, and an insert-only detector leaves it there."""
    active = [ActiveFlag("HIGH_GROSSED_UP_YIELD", "AAA")]
    row = industrial()
    row["grossed_up_yield"] = unhealthy("grossed_up_yield", "feed incomplete")
    results, _ = evaluate_all([HIGH_YIELD], {"AAA": row})

    assert deactivations(active, results) == active, \
        "an unproven assertion is not a weaker assertion, it is not one"


def test_a_still_firing_flag_is_left_alone():
    active = [ActiveFlag("HIGH_GROSSED_UP_YIELD", "AAA")]
    results, _ = evaluate_all([HIGH_YIELD], {"AAA": industrial(yield_=0.15)})

    assert deactivations(active, results) == []


def test_a_flag_for_a_company_not_in_this_run_is_not_touched():
    """A partial run must not withdraw flags it never considered."""
    active = [ActiveFlag("HIGH_GROSSED_UP_YIELD", "ZZZ")]
    results, _ = evaluate_all([HIGH_YIELD], {"AAA": industrial(yield_=0.05)})

    assert deactivations(active, results) == []


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
