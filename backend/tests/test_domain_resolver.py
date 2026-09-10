"""
Domain resolution — precedence and coverage
===========================================
Precedence is the contract:

    structural flags -> industry mapping -> defensible sector fallback -> UNKNOWN

and UNKNOWN is conservative. These tests pin the ordering and, more
importantly, pin the *refusals*: the cases where the resolver declines to
guess. Widening the mapping to improve a coverage number is the failure mode
being designed against, so the tests that matter most are the ones asserting
something stays UNKNOWN.

INDUSTRY_DOMAIN is empty until authored from the production vocabulary, so the
mapping tests populate it locally rather than asserting on entries that do not
exist yet.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_domain_resolver.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import Applicability, Domain, assess  # noqa: E402
from compute.engine.domain_resolver import (  # noqa: E402
    INDUSTRY_DOMAIN,
    PRE_REVENUE_CEILING,
    Source,
    coverage,
    resolve_domain,
)


# ── 1 · structural flags outrank everything ───────────────────────────────────

def test_is_reit_wins_over_industry_and_sector():
    r = resolve_domain({"is_reit": True, "industry": "banks", "sector": "Financials"})
    assert r.domain is Domain.REIT
    assert r.source is Source.STRUCTURAL_FLAG


def test_a_producing_miner_and_an_explorer_are_split_on_revenue():
    producer = resolve_domain({"is_miner": True, "revenue": 5e9, "sector": "Materials"})
    explorer = resolve_domain({"is_miner": True, "revenue": 0.0, "sector": "Materials"})

    assert producer.domain is Domain.MINING_PRODUCER
    assert explorer.domain is Domain.MINING_EXPLORER


def test_a_nominal_revenue_line_does_not_promote_an_explorer():
    """Interest or tenement recharges are not production."""
    r = resolve_domain({"is_miner": True, "revenue": PRE_REVENUE_CEILING - 1})
    assert r.domain is Domain.MINING_EXPLORER


def test_a_miner_with_unknown_revenue_refuses_to_guess():
    """Producer and explorer have opposite applicability — ARU is the reason."""
    r = resolve_domain({"is_miner": True, "sector": "Materials"})
    assert r.domain is Domain.UNKNOWN
    assert "revenue unknown" in r.evidence


# ── 2 · industry mapping ──────────────────────────────────────────────────────

# Tests that add an entry must use a fictional industry and remove only that.
# Using a real one and popping it in cleanup deletes the authored mapping for
# every test that runs afterwards — which is exactly what happened once the
# table stopped being empty.
FICTIONAL = "widget banking"


def test_industry_mapping_resolves_when_authored():
    INDUSTRY_DOMAIN[FICTIONAL] = Domain.BANK
    try:
        r = resolve_domain({"industry": "Widget Banking", "sector": "Financials"})
        assert r.domain is Domain.BANK
        assert r.source is Source.INDUSTRY_MAPPING
    finally:
        INDUSTRY_DOMAIN.pop(FICTIONAL, None)


def test_industry_mapping_outranks_the_sector_fallback():
    r = resolve_domain({"industry": "Insurance", "sector": "Financials"})
    assert r.domain is Domain.INSURER
    assert r.source is Source.INDUSTRY_MAPPING, "not a sector fallback"


def test_industry_matching_is_case_and_whitespace_insensitive():
    assert resolve_domain({"industry": "  Capital Markets "}).domain \
        is Domain.CAPITAL_MARKETS


# ── 3 · the fallback is conservative, not convenient ──────────────────────────

def test_financials_sector_does_not_fall_back_at_all():
    """OTHER_FINANCIAL is strictly weaker than UNKNOWN, so it is not a fallback.

    It sits in FINANCIAL (Altman suppressed) but not in DEPOSIT_FUNDED, so
    debt_to_equity and current_ratio stay applicable — an unmapped bank would
    still be told its leverage is elevated and its current ratio a liquidity
    risk, through the fallback meant to prevent exactly that.
    """
    r = resolve_domain({"sector": "Financials", "industry": "Diversified Widgets"})
    assert r.domain is Domain.UNKNOWN
    assert r.source is Source.UNRESOLVED


def test_other_financial_would_have_leaked_two_of_the_three_cba_lines():
    """Pins the reason, so nobody re-adds the fallback as an improvement."""
    leaked = [m for m, v in (("altman_z_score", -0.15), ("debt_to_equity", 4.6),
                             ("current_ratio", 0.1))
              if assess(m, v, Domain.OTHER_FINANCIAL).ok]
    assert leaked == ["debt_to_equity", "current_ratio"]

    for metric, value in (("altman_z_score", -0.15), ("debt_to_equity", 4.6),
                          ("current_ratio", 0.1)):
        assert assess(metric, value, Domain.UNKNOWN).state \
            is Applicability.NOT_MEANINGFUL, "UNKNOWN suppresses all three"


def test_real_estate_sector_has_no_fallback():
    """That sector holds developers and agencies; only is_reit is trustworthy."""
    r = resolve_domain({"sector": "Real Estate"})
    assert r.domain is Domain.UNKNOWN


def test_industrial_sectors_resolve_explicitly_not_by_default():
    for sector in ("Consumer Staples", "Health Care", "Information Technology"):
        r = resolve_domain({"sector": sector})
        assert r.domain is Domain.GENERAL_CORPORATE
        assert r.source is Source.SECTOR_FALLBACK, "explicit, not an absent rule"


# ── 4 · UNKNOWN, conservatively ───────────────────────────────────────────────

def test_an_unmapped_industry_stays_unknown():
    r = resolve_domain({"industry": "Something Nobody Mapped", "sector": ""})
    assert r.domain is Domain.UNKNOWN
    assert "unmapped" in r.evidence


def test_no_industry_and_no_known_sector_is_unknown():
    r = resolve_domain({})
    assert r.domain is Domain.UNKNOWN
    assert r.source is Source.UNRESOLVED


def test_unknown_suppresses_domain_sensitive_metrics():
    """The point of refusing to guess: the contract still protects the user."""
    domain = resolve_domain({"industry": "Unmapped"}).domain
    assert assess("debt_to_equity", 4.6, domain).state is Applicability.NOT_MEANINGFUL
    assert assess("dividend_yield", 0.04, domain).ok, "but not everything goes quiet"


# ── Resolver coverage ─────────────────────────────────────────────────────────

UNIVERSE = [
    {"asx_code": "CBA", "sector": "Financials", "industry": "Banks"},
    {"asx_code": "NAB", "sector": "Financials", "industry": "Banks"},
    {"asx_code": "QBE", "sector": "Financials", "industry": "Insurance"},
    {"asx_code": "BHP", "sector": "Materials", "industry": "Metals & Mining",
     "is_miner": True, "revenue": 5e10},
    {"asx_code": "ARU", "sector": "Materials", "industry": "Metals & Mining",
     "is_miner": True, "revenue": 0.0},
    {"asx_code": "GMG", "sector": "Real Estate", "industry": "Industrial REITs",
     "is_reit": True},
    {"asx_code": "WOW", "sector": "Consumer Staples", "industry": "Food Retail"},
    {"asx_code": "XYZ", "sector": "", "industry": ""},
]


def test_coverage_counts_domains_sources_and_unmapped():
    cov = coverage(UNIVERSE)

    assert cov.total == 8
    assert cov.by_domain[Domain.REIT] == 1
    assert cov.by_domain[Domain.MINING_PRODUCER] == 1
    assert cov.by_domain[Domain.MINING_EXPLORER] == 1
    assert cov.by_domain[Domain.GENERAL_CORPORATE] == 1


def test_coverage_names_the_industries_worth_authoring_first():
    """The output that turns 'coverage is low' into a work list."""
    rows = UNIVERSE + [
        {"asx_code": "P1", "sector": "Financials", "industry": "Widget Banking"},
        {"asx_code": "P2", "sector": "Financials", "industry": "Widget Banking"},
    ]
    top = dict(coverage(rows).unmapped_industries)

    assert top.get("widget banking") == 2, "two companies blocked on one entry"
    assert "(no industry)" in top


def test_coverage_measures_after_the_mapping_not_before():
    """Data coverage and resolver coverage are different questions.

    Every company here has an industry, so data coverage is 100%. Resolver
    coverage is not, until the industry is in the table.
    """
    rows = [{"asx_code": "AAA", "sector": "Financials", "industry": "Widget Banking"},
            {"asx_code": "BBB", "sector": "Financials", "industry": "Widget Banking"}]

    assert coverage(rows).unknown == 2, "an industry is not a domain"

    INDUSTRY_DOMAIN["widget banking"] = Domain.BANK
    try:
        after = coverage(rows)
        assert after.unknown == 0
        assert after.by_domain[Domain.BANK] == 2
        assert after.by_source[Source.INDUSTRY_MAPPING] == 2
    finally:
        INDUSTRY_DOMAIN.pop("widget banking", None)


def test_the_authored_mapping_resolves_the_real_exemplars():
    """B4, as a permanent test: the vocabulary the mapping was written from."""
    cases = [
        ({"asx_code": "CBA", "sector": "Financials", "industry": "Banks"}, Domain.BANK),
        ({"asx_code": "WBC", "sector": "Financials", "industry": "Banks"}, Domain.BANK),
        ({"asx_code": "QBE", "sector": "Financials", "industry": "Insurance"}, Domain.INSURER),
        ({"asx_code": "SUN", "sector": "Financials", "industry": "Insurance"}, Domain.INSURER),
        ({"asx_code": "NWL", "sector": "Financials", "industry": "Capital Markets"},
         Domain.CAPITAL_MARKETS),
        ({"asx_code": "GMG", "sector": "Real Estate", "industry": "Diversified REITs",
          "is_reit": True}, Domain.REIT),
        ({"asx_code": "SCG", "sector": "Real Estate", "industry": "Retail REITs",
          "is_reit": True}, Domain.REIT),
    ]
    for row, expected in cases:
        assert resolve_domain(row).domain is expected, row["asx_code"]


def test_macquarie_is_overridden_to_bank():
    """GICS says Capital Markets, which is a defensible label and the wrong
    applicability: MQG is a deposit-taking ADI, and CAPITAL_MARKETS would leave
    debt_to_equity and current_ratio applicable."""
    r = resolve_domain({"asx_code": "MQG", "sector": "Financials",
                        "industry": "Capital Markets"})
    assert r.domain is Domain.BANK
    assert r.source is Source.OVERRIDE
    assert r.evidence, "an override must carry a reason a reviewer can check"

    assert assess("debt_to_equity", 5.2, r.domain).state is Applicability.NOT_MEANINGFUL
    assert assess("debt_to_equity", 5.2, Domain.CAPITAL_MARKETS).ok, \
        "which is what the override exists to prevent"


def test_oil_and_gas_is_never_flagged_so_the_industry_set_carries_it():
    """Measured: is_miner covers Metals & Mining 566/566 and Oil & Gas 0/110.

    Without MINING_INDUSTRIES those 110 fall to sector Energy ->
    GENERAL_CORPORATE, and a pre-revenue oil explorer gets ARU's treatment.
    """
    explorer = resolve_domain({"asx_code": "OIL", "sector": "Energy",
                               "industry": "Oil, Gas & Consumable Fuels",
                               "is_miner": False, "revenue_ttm": 0.0})
    assert explorer.domain is Domain.MINING_EXPLORER
    assert assess("altman_z_score", 2853.0, explorer.domain).state \
        is Applicability.NOT_MEANINGFUL

    producer = resolve_domain({"asx_code": "WDS", "sector": "Energy",
                               "industry": "Oil, Gas & Consumable Fuels",
                               "is_miner": False, "revenue_ttm": 1.4e10})
    assert producer.domain is Domain.MINING_PRODUCER


def test_revenue_is_read_from_the_real_column_names():
    """screener.universe has no plain `revenue` column; it has revenue_ttm."""
    assert resolve_domain({"is_miner": True, "revenue_ttm": 5e9}).domain \
        is Domain.MINING_PRODUCER
    assert resolve_domain({"is_miner": True, "revenue_fy0": 5e9}).domain \
        is Domain.MINING_PRODUCER
    assert resolve_domain({"is_miner": True, "revenue_ttm": None,
                           "revenue_fy0": 0.0}).domain is Domain.MINING_EXPLORER


def test_an_unflagged_miner_still_takes_the_revenue_split():
    """566 companies sit in Metals & Mining; if is_miner is not set on all of
    them, sector alone would send a pre-revenue explorer to GENERAL_CORPORATE
    — the ARU defect by a different route."""
    explorer = resolve_domain({"sector": "Materials", "industry": "Metals & Mining",
                               "is_miner": False, "revenue": 0.0})
    assert explorer.domain is Domain.MINING_EXPLORER

    unknown = resolve_domain({"sector": "Materials", "industry": "Metals & Mining",
                              "is_miner": False})
    assert unknown.domain is Domain.UNKNOWN, "no revenue, no guess"


def test_every_company_with_an_industry_can_still_be_unknown():
    """A company can have an industry and remain unresolved — that is the gap."""
    rows = [{"sector": "Utilities", "industry": "Something Unmapped"}]
    cov = coverage(rows)
    assert cov.by_domain[Domain.GENERAL_CORPORATE] == 1, \
        "sector fallback catches it here"

    rows = [{"sector": "", "industry": "Something Unmapped"}]
    assert coverage(rows).unknown == 1, "with no sector, the gap is visible"


def test_coverage_renders_a_readable_report():
    out = coverage(UNIVERSE).render()
    assert "resolver coverage:" in out
    assert "top unmapped industries" in out


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
    print("\n-- Sample coverage report (mapping table still empty) --")
    print(coverage(UNIVERSE).render())
    sys.exit(1 if failures else 0)
