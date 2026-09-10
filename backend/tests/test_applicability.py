"""
Applicability contract — permanent regression tests
===================================================
The roadmap names four of these as required fixtures. They assert on the
applicability layer itself rather than on rendered output, so they hold
whatever the page later looks like:

  * CBA  — the system must not manufacture distress from an invalid model,
           and must not rank banks down for structurally high leverage.
  * ARU  — the system must not manufacture safety from an invalid model.
  * QAN  — observation validity: ROE on negative equity.
  * AI Query non-exclusion — an NM predicate cannot exclude a security.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_applicability.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Assessment,
    Domain,
    Observation,
    Weighting,
    assess,
    assess_all,
    assess_composite,
    predicate_excludes,
)

# The six lines the company page shows for Commonwealth Bank today.
CBA_VALUES = {
    "altman_z_score": -0.15,
    "debt_to_equity": 4.6,
    "current_ratio": 0.1,
    "gross_margin": 0.42,
    "earnings_quality": -0.08,
    "piotroski_f_score": 3.0,
}

# ARU: pre-revenue explorer, $7M total liabilities. The same bug, inverted.
ARU_VALUES = {
    "altman_z_score": 2853.0,
    "price_to_sales": 1148.0,
    "piotroski_f_score": 2.0,
}


# ── Fixture · CBA, manufactured distress ──────────────────────────────────────

def test_cba_every_distress_line_is_suppressed():
    out = assess_all(CBA_VALUES, Domain.BANK)
    for metric, a in out.items():
        assert a.state is Applicability.NOT_MEANINGFUL, f"{metric} still reaches the page"
        assert a.reason, f"{metric} suppressed without a reason"


def test_cba_suppressed_metrics_carry_no_value():
    """A ranking built on assessment.value cannot silently keep using them."""
    for a in assess_all(CBA_VALUES, Domain.BANK).values():
        assert a.value is None


def test_cba_renders_nm_not_an_em_dash():
    a = assess("altman_z_score", -0.15, Domain.BANK)
    assert a.display() == "NM", "NM and missing data are different things"


def test_cba_metrics_that_are_valid_for_a_bank_still_pass():
    """Suppression is per metric, not a blanket sector exclusion."""
    out = assess_all({"roe": 0.1284, "pe_ratio": 19.2, "dividend_yield": 0.0326},
                     Domain.BANK, Observation(equity=8e10, earnings=1e10))
    assert all(a.ok for a in out.values())
    assert out["roe"].value == 0.1284


# ── Fixture · ARU, manufactured safety ────────────────────────────────────────

def test_aru_safety_reading_is_suppressed():
    out = assess_all(ARU_VALUES, Domain.MINING_EXPLORER)
    assert out["altman_z_score"].state is Applicability.NOT_MEANINGFUL
    assert out["price_to_sales"].state is Applicability.NOT_MEANINGFUL
    assert out["piotroski_f_score"].state is Applicability.NOT_MEANINGFUL


def test_a_producing_miner_is_not_an_explorer():
    """The contract generalises across economic models, not sector labels."""
    a = assess("price_to_sales", 2.4, Domain.MINING_PRODUCER, Observation(revenue=5e9))
    assert a.ok


# ── Fixture · QAN, observation validity ───────────────────────────────────────

def test_qan_roe_on_negative_equity_is_not_meaningful():
    a = assess("roe", 2.0630, Domain.GENERAL_CORPORATE, Observation(equity=-1.2e9))
    assert a.state is Applicability.NOT_MEANINGFUL
    assert a.value is None, "206.30% must not reach a percentile rank"


def test_negative_earnings_do_not_make_a_cheap_pe():
    a = assess("pe_ratio", -4.2, Domain.GENERAL_CORPORATE, Observation(earnings=-8e6))
    assert a.state is Applicability.NOT_MEANINGFUL


def test_positive_denominators_pass():
    a = assess("roe", 0.18, Domain.GENERAL_CORPORATE, Observation(equity=5e8))
    assert a.ok and a.value == 0.18


def test_five_year_cagr_with_three_years_is_insufficient_not_absent():
    a = assess("revenue_cagr_5y", 0.31, Domain.GENERAL_CORPORATE,
               Observation(periods_available=3, periods_required=5))
    assert a.state is Applicability.INSUFFICIENT_DATA
    assert "3 of 5" in a.reason


# ── The four states are genuinely distinct ────────────────────────────────────

def test_unavailable_is_not_not_meaningful():
    absent = assess("current_ratio", None, Domain.GENERAL_CORPORATE)
    suppressed = assess("current_ratio", 0.1, Domain.BANK)

    assert absent.state is Applicability.UNAVAILABLE
    assert suppressed.state is Applicability.NOT_MEANINGFUL
    assert absent.display() == "—" and suppressed.display() == "NM"


def test_domain_gate_outranks_availability():
    """A metric meaningless for a bank is NM whether or not a number arrived."""
    assert assess("altman_z_score", None, Domain.BANK).state is Applicability.NOT_MEANINGFUL


# ── UNKNOWN must be conservative ──────────────────────────────────────────────

def test_unknown_domain_does_not_inherit_industrial_defaults():
    """No rule said 'treat CBA as an industrial company'. The absence did."""
    a = assess("debt_to_equity", 4.6, Domain.UNKNOWN)
    assert a.state is Applicability.NOT_MEANINGFUL
    assert "not resolved" in a.reason


def test_unknown_domain_still_passes_domain_neutral_metrics():
    a = assess("dividend_yield", 0.045, Domain.UNKNOWN)
    assert a.ok, "suppressing everything would be conservative to the point of useless"


# ── Composite inheritance ─────────────────────────────────────────────────────

def test_composite_is_nm_when_a_material_constituent_is_out_of_domain():
    constituents = [
        assess("debt_to_equity", 4.6, Domain.BANK),
        assess("roe", 0.128, Domain.BANK, Observation(equity=8e10)),
        assess("roce", 0.09, Domain.BANK, Observation(invested_capital=5e10)),
        assess("piotroski_f_score", 3.0, Domain.BANK),
    ]
    q = assess_composite("quality_score", 41.0, constituents, Domain.BANK)

    assert q.state is Applicability.NOT_MEANINGFUL
    assert "debt_to_equity" in q.reason and "piotroski_f_score" in q.reason
    assert q.value is None, "a bank must not be ranked down on this score"


def test_composite_survives_when_only_immaterial_constituents_fail():
    constituents = [
        assess("roe", 0.18, Domain.GENERAL_CORPORATE, Observation(equity=5e8)),
        assess("roce", None, Domain.GENERAL_CORPORATE),
    ]
    q = assess_composite("quality_score", 72.0, constituents,
                         Domain.GENERAL_CORPORATE, material=["roe"])
    assert q.ok and q.value == 72.0


def test_composite_cannot_be_more_applicable_than_its_constituents():
    """The invariant, stated directly."""
    for state, value in ((Applicability.NOT_MEANINGFUL, None),
                         (Applicability.INSUFFICIENT_DATA, None),
                         (Applicability.UNAVAILABLE, None)):
        c = Assessment("x", state, value, "because")
        out = assess_composite("composite", 50.0, [c], Domain.GENERAL_CORPORATE)
        assert not out.ok
        assert out.value is None


def test_piotroski_is_nm_for_a_bank_without_naming_the_sector():
    """The rule generalises: explorers fail it too, for different subtests."""
    assert assess("piotroski_f_score", 3.0, Domain.BANK).suppressed
    assert assess("piotroski_f_score", 2.0, Domain.MINING_EXPLORER).suppressed
    assert assess("piotroski_f_score", 7.0, Domain.GENERAL_CORPORATE).ok


# ── Fixture · AI Query non-exclusion ──────────────────────────────────────────

def test_an_nm_predicate_cannot_exclude_a_security():
    """Observed live: "Top 25 stocks to buy and hold forever" returned no bank.

        EXCLUDED  debt_to_equity gt 1.5 | piotroski lt 5 | altman_z lt 1.5
        CBA       D/E 4.6x  Piotroski 3/9  Altman -0.15  -> fails all three

    Phrased as non-exclusion, not membership: CBA may legitimately fail some
    other valid criterion later. The invariant targets the architectural bug.
    """
    for bank in ("CBA", "NAB", "WBC"):
        for metric, value in (("debt_to_equity", 4.6),
                              ("piotroski_f_score", 3.0),
                              ("altman_z_score", -0.15)):
            a = assess(metric, value, Domain.BANK)
            assert not a.ok, f"{bank} {metric} should not evaluate"
            assert not predicate_excludes(a), \
                f"{bank} excluded by an NM {metric} predicate"


def test_an_applicable_predicate_still_excludes_normally():
    a = assess("dividend_yield", 0.01, Domain.BANK)
    assert predicate_excludes(a), "applicability must not disable real filters"


# ── Effective weighting is declared, not implicit ─────────────────────────────

NOMINAL = {"value": 0.2, "quality": 0.2, "growth": 0.2, "momentum": 0.2, "income": 0.2}


def test_effective_weights_renormalise_over_applicable_factors():
    w = Weighting(NOMINAL, frozenset({"value", "quality", "growth", "momentum"}))
    eff = w.effective

    assert w.coverage == "4/5 applicable"
    assert w.is_reweighted
    assert abs(sum(eff.values()) - 1.0) < 1e-9
    assert all(abs(v - 0.25) < 1e-9 for v in eff.values())
    assert "income" not in eff


def test_a_full_five_factor_stock_is_not_flagged_as_reweighted():
    w = Weighting(NOMINAL, frozenset(NOMINAL))
    assert not w.is_reweighted
    assert w.coverage == "5/5 applicable"


def test_no_applicable_factors_yields_no_weights():
    assert Weighting(NOMINAL, frozenset()).effective == {}


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
            print(f"  FAIL  {name}  — {e}")
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  — {type(e).__name__}: {e}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
