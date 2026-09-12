"""
Two ways for an average to be empty, and they are not the same fact
===================================================================
``average_over`` enforces the window and returns None for both of its refusal
cases, because a numeric column carries no state. The distinction is recovered
here, at the gate, from ``Observation.periods_available``:

    the required fiscal years do not exist   INSUFFICIENT_DATA / INSUFFICIENT_HISTORY
    the years exist, an observation is NULL  UNAVAILABLE      / SOURCE_MISSING

Why it is worth a test rather than a comment: the gate has been present and
inert. ``PERIOD_REQUIREMENT`` only fires when a caller supplies
``periods_available``, and until ``screener.universe.annual_periods`` existed
no caller could. An inert gate passes every test that only asks "is the value
withheld" — both branches withhold — so the assertions here are on the *cause*,
which is the only thing that separates them.

The cause is not cosmetic. It is what an operator acts on: INSUFFICIENT_HISTORY
says wait for the company to report, SOURCE_MISSING says go and look at our
feed. Getting it backwards for roic would send someone hunting for 537 sets of
fiscal years that are already in the database.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_period_cause.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Cause,
    Domain,
    Observation,
    PERIOD_REQUIREMENT,
    assess,
)


def reported(n: int) -> Observation:
    """A company with n consecutive annual periods ending at FY0."""
    return Observation(periods_available=n)


# ── The distinction itself ───────────────────────────────────────────────────

def test_a_window_that_does_not_exist_is_insufficient_history():
    """Two years of reporting cannot produce a three-year average, and the
    reason is the company's record, not our feed."""
    a = assess("avg_roe_3y", None, Domain.GENERAL_CORPORATE, reported(2))

    assert a.state is Applicability.INSUFFICIENT_DATA
    assert a.cause is Cause.INSUFFICIENT_HISTORY
    assert not a.ok
    assert a.value is None


def test_a_window_that_exists_with_a_hole_is_source_missing():
    """The roic case. Three contiguous years are present; the metric is sparse
    within them. Blaming history here would be a false statement about the
    company."""
    a = assess("avg_roic_3y", None, Domain.GENERAL_CORPORATE, reported(9))

    assert a.state is Applicability.UNAVAILABLE
    assert a.cause is Cause.SOURCE_MISSING


def test_the_two_causes_differ_on_identical_inputs_but_for_history():
    """Same metric, same absent value, same domain. Only the reporting record
    differs — and that alone must decide the cause."""
    short = assess("avg_net_margin_5y", None, Domain.GENERAL_CORPORATE, reported(4))
    deep = assess("avg_net_margin_5y", None, Domain.GENERAL_CORPORATE, reported(5))

    assert short.cause is Cause.INSUFFICIENT_HISTORY
    assert deep.cause is Cause.SOURCE_MISSING


def test_exactly_enough_periods_is_enough():
    """The boundary is >=, not >. A five-year average needs five years, and a
    company with exactly five has them."""
    a = assess("avg_roe_5y", 0.12, Domain.GENERAL_CORPORATE, reported(5))

    assert a.state is Applicability.APPLICABLE
    assert a.value == 0.12


def test_one_period_short_withholds_a_value_that_is_present():
    """The defect this replaces did the opposite: it averaged whatever rows it
    had and labelled the result a five-year average. A value arriving from the
    source does not make the window exist."""
    a = assess("avg_roe_5y", 0.12, Domain.GENERAL_CORPORATE, reported(4))

    assert not a.ok
    assert a.cause is Cause.INSUFFICIENT_HISTORY
    assert a.value is None


# ── What the gate must not do ────────────────────────────────────────────────

def test_an_unknown_reporting_record_does_not_assert_insufficiency():
    """annual_periods is NULL for a company with no FY0 anchor. A check that
    cannot run has not failed — and has not passed either: the value is still
    absent, so it is still withheld, just not as a claim about history."""
    a = assess("avg_roe_3y", None, Domain.GENERAL_CORPORATE, Observation())

    assert not a.ok
    assert a.cause is Cause.SOURCE_MISSING


def test_the_period_gate_does_not_touch_metrics_that_make_no_period_claim():
    """roe is not an average. A company with one year of history has a
    perfectly meaningful current ROE."""
    a = assess("roe", 0.15, Domain.GENERAL_CORPORATE,
               Observation(periods_available=1, equity=500.0))

    assert a.state is Applicability.APPLICABLE


def test_domain_still_outranks_history():
    """Gate 1 before gate 2, without exception. A bank's gross margin is not
    meaningful however many years it has reported, and answering
    INSUFFICIENT_HISTORY would invite someone to wait for data that would not
    help."""
    a = assess("avg_gross_margin_3y", None, Domain.BANK, reported(1))

    assert a.state is Applicability.NOT_MEANINGFUL
    assert a.cause is not Cause.INSUFFICIENT_HISTORY


def test_period_sufficiency_is_checked_before_the_denominator():
    """Both gates would fire. The window is the prior question: there is no
    equity base to judge for a year that was never reported, and reporting the
    denominator would describe a computation that never got that far."""
    a = assess("avg_roe_3y", None, Domain.GENERAL_CORPORATE,
               Observation(periods_available=1, equity=-500.0))

    assert a.cause is Cause.INSUFFICIENT_HISTORY


# ── The map matches what the columns claim ───────────────────────────────────

def test_every_requirement_matches_the_horizon_in_its_own_name():
    """The map is generated, so this guards a future hand-written entry: a
    requirement of 3 on a column named _5y would withhold two fewer years than
    the name promises and nothing else would notice."""
    for metric, required in PERIOD_REQUIREMENT.items():
        assert metric.endswith(f"_{required}y"), (
            f"{metric} requires {required} periods")


def test_the_requirement_covers_every_exposed_rolling_average():
    """A governed avg_* with no entry here is the inert state this work
    removed: it would withhold with SOURCE_MISSING universally, and no test
    asserting only absence would catch it."""
    from compute.engine.metric_states import ROLLING_AVERAGES

    missing = sorted(m for m in ROLLING_AVERAGES if m not in PERIOD_REQUIREMENT)

    assert not missing, f"governed but no period requirement: {missing}"


# ── Standalone runner ────────────────────────────────────────────────────────

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
