"""
Feed-quality semantics — FEED_INCOMPLETE is not NOT_APPLICABLE
=============================================================
One rule, and every test here is a consequence of it:

    A REIT metric that does not apply to a bank is an applicability decision.
    A dividend metric that cannot be computed because the exchange-wide feed
    is incomplete is a data-quality failure.

Those two must not have identical downstream behaviour. The state is the same
(UNAVAILABLE — the metric is applicable and has no value); the *cause* is what
consumers branch on.

The sharpest consequence is AlphaFive. Reweighting around an inapplicable
factor describes the company. Reweighting around a broken feed describes
nothing: it converts a canonical five-factor strategy into a four-factor one
and keeps the name.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_feed_semantics.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Cause,
    Domain,
    PredicateResult,
    Weighting,
    assess,
    assess_composite,
    predicate_excludes,
    predicate_result,
    refresh_gate,
    to_payload,
    unhealthy,
    usable_values,
)
from compute.engine.dividends import (  # noqa: E402
    DividendSource,
    DividendState,
    FeedHealth,
)

TODAY = date(2026, 9, 10)

# Production, measured: latest ex-date 2026-08-03, 0 rows in 30 days.
BROKEN = FeedHealth(latest_ex_date=date(2026, 8, 3), as_of=TODAY,
                    recent_rows=0, recent_issuers=0)
CURRENT = FeedHealth(latest_ex_date=date(2026, 9, 5), as_of=TODAY,
                     recent_rows=180, recent_issuers=140)

CBA_ROWS = [
    {"ex_date": date(2026, 2, 18), "amount": 2.35, "franking_pct": 100.0,
     "grossed_up": 3.357143},
    {"ex_date": date(2025, 8, 20), "amount": 2.60, "franking_pct": 100.0,
     "grossed_up": 3.714286},
]


# ── Feed health ───────────────────────────────────────────────────────────────

def test_the_measured_production_feed_is_unhealthy():
    assert not BROKEN.healthy
    assert BROKEN.lag_days == 38
    assert "38 days behind" in BROKEN.reason


def test_a_current_feed_is_healthy():
    assert CURRENT.healthy and CURRENT.lag_days == 5


def test_an_empty_feed_is_unhealthy_not_merely_quiet():
    empty = FeedHealth(latest_ex_date=None, as_of=TODAY)
    assert not empty.healthy
    assert "no ex-dates" in empty.reason


# ── The source boundary applies the watermark, callers do not ─────────────────

def test_the_source_applies_the_watermark_without_being_asked():
    assert DividendSource(BROKEN).ttm(CBA_ROWS).state is DividendState.FEED_INCOMPLETE
    assert DividendSource(CURRENT).ttm(CBA_ROWS, as_of=date(2026, 3, 1)).state \
        is DividendState.APPLICABLE


def test_a_broken_feed_yields_no_dividend_numbers():
    m = DividendSource(BROKEN).metrics(CBA_ROWS, close=158.69)
    assert all(v is None for v in m.values())


# ── The cause survives to the consumer ────────────────────────────────────────

def test_source_failure_is_unavailable_with_a_distinguishing_cause():
    a = DividendSource(BROKEN).assessments(CBA_ROWS, 158.69)["grossed_up_yield"]

    assert a.state is Applicability.UNAVAILABLE
    assert a.cause is Cause.SOURCE_UNHEALTHY
    assert a.source_unhealthy


def test_it_is_not_confusable_with_an_applicability_decision():
    broken = unhealthy("grossed_up_yield", "feed incomplete")
    inapplicable = assess("debt_to_equity", 4.6, Domain.BANK)

    assert broken.state is not inapplicable.state
    assert broken.cause is not inapplicable.cause
    assert inapplicable.cause is Cause.DOMAIN


def test_a_company_specific_gap_is_not_a_feed_failure():
    """One issuer with no value is SOURCE_MISSING; the feed stopping is not."""
    missing = assess("dividend_yield", None, Domain.GENERAL_CORPORATE)
    assert missing.cause is Cause.SOURCE_MISSING
    assert not missing.source_unhealthy


def test_the_display_string_does_not_claim_the_company_pays_nothing():
    broken = unhealthy("dividend_yield", "feed incomplete")
    assert broken.display() == "Data unavailable"
    assert assess("dividend_yield", None, Domain.GENERAL_CORPORATE).display() == "—"


def test_the_cause_crosses_the_serialisation_boundary():
    payload = to_payload(unhealthy("dividend_yield", "feed incomplete"))
    assert payload["cause"] == "source_unhealthy"
    assert payload["value"] is None
    assert payload["display"] == "Data unavailable"


# ── Composites must not reweight around a broken feed ─────────────────────────

def test_a_composite_refuses_to_reweight_around_source_failure():
    constituents = [
        assess("value_score", 60.0, Domain.GENERAL_CORPORATE),
        assess("quality_score", 70.0, Domain.GENERAL_CORPORATE),
        unhealthy("income_score", "dividend feed incomplete"),
    ]
    c = assess_composite("composite_score", 65.0, constituents,
                         Domain.GENERAL_CORPORATE)

    assert c.state is Applicability.UNAVAILABLE
    assert c.cause is Cause.SOURCE_UNHEALTHY
    assert "income_score" in c.reason
    assert c.value is None


def test_a_composite_still_reweights_around_an_applicability_decision():
    """The legitimate case must keep working, or the rule is just a blocker."""
    constituents = [
        assess("roe", 0.128, Domain.BANK, None),
        assess("piotroski_f_score", 3.0, Domain.BANK),
    ]
    c = assess_composite("quality_score", 55.0, constituents, Domain.BANK,
                         material=["roe"])
    assert c.ok, "an inapplicable immaterial constituent does not block"


def test_reweightable_distinguishes_the_two():
    assert assess("debt_to_equity", 4.6, Domain.BANK).reweightable
    assert not unhealthy("income_score", "feed incomplete").reweightable


def test_weighting_refuses_effective_weights_when_a_source_failed():
    nominal = {"value": .2, "quality": .2, "growth": .2, "momentum": .2, "income": .2}

    applicability_driven = Weighting(nominal, frozenset(nominal) - {"income"})
    assert applicability_driven.may_reweight
    assert abs(sum(applicability_driven.effective.values()) - 1.0) < 1e-9

    source_driven = Weighting(nominal, frozenset(nominal) - {"income"},
                              unhealthy=frozenset({"income"}))
    assert not source_driven.may_reweight
    assert source_driven.effective == {}, \
        "25/25/25/25 would be a different strategy wearing the same name"


# ── Predicates: three outcomes, not two ───────────────────────────────────────

def test_an_nm_predicate_cannot_exclude_but_an_unavailable_one_cannot_match():
    nm = assess("debt_to_equity", 4.6, Domain.BANK)
    no_data = unhealthy("dividend_yield", "feed incomplete")

    assert predicate_result(nm) is PredicateResult.NOT_ELIGIBLE
    assert predicate_result(no_data) is PredicateResult.NO_DATA
    assert predicate_result(assess("roe", 0.18, Domain.GENERAL_CORPORATE)) \
        is PredicateResult.EVALUATED

    assert not predicate_excludes(nm), "a bank is not excluded by an NM D/E"
    assert not predicate_excludes(no_data), "and no yield filter can match it"


def test_a_dividend_anomaly_cannot_fire_on_a_broken_feed():
    a = unhealthy("grossed_up_yield", "feed incomplete")
    assert predicate_result(a) is not PredicateResult.EVALUATED
    assert a.metric not in usable_values([a])


# ── The canonical AlphaFive refresh boundary ──────────────────────────────────

FAMILIES = ["value_score", "quality_score", "growth_score",
            "momentum_score", "income_score"]


def test_alphafive_refuses_to_mint_a_cohort_without_income():
    assessments = [assess(f, 60.0, Domain.GENERAL_CORPORATE)
                   for f in FAMILIES[:4]]
    assessments.append(unhealthy("income_score", "dividend feed incomplete"))

    gate = refresh_gate(assessments, FAMILIES, last_published="2026-09-07")

    assert not gate.permitted
    assert gate.blocked_by == ("income_score",)
    assert "Refresh unavailable" in gate.message
    assert "income_score" in gate.message


def test_the_message_says_last_published_not_last_valid():
    """Earlier cohorts may themselves have used incomplete inputs."""
    gate = refresh_gate([unhealthy("income_score", "feed")], FAMILIES,
                        last_published="2026-09-07")
    assert "last published computation: 2026-09-07" in gate.message
    assert "valid" not in gate.message.lower()


def test_a_healthy_run_is_permitted():
    assessments = [assess(f, 60.0, Domain.GENERAL_CORPORATE) for f in FAMILIES]
    assert refresh_gate(assessments, FAMILIES).permitted


def test_an_inapplicable_factor_does_not_block_the_refresh():
    """Only source failure gates the refresh; applicability is business as usual."""
    assessments = [assess(f, 60.0, Domain.GENERAL_CORPORATE) for f in FAMILIES[:4]]
    assessments.append(assess("income_score", None, Domain.MINING_EXPLORER))
    assert refresh_gate(assessments, FAMILIES).permitted


def test_a_broken_family_outside_the_required_set_does_not_block():
    assessments = [assess(f, 60.0, Domain.GENERAL_CORPORATE) for f in FAMILIES]
    assessments.append(unhealthy("experimental_score", "some other feed"))
    assert refresh_gate(assessments, FAMILIES).permitted


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
