"""
Peer statistics — valid peers only, with the denominator attached
================================================================
The three fixtures the contract requires:

  1. an entirely invalid peer population produces no median or quartiles;
  2. one invalid member cannot shift the valid peers' statistics;
  3. a mixed unavailable / suppressed population cannot satisfy the
     minimum-coverage gate by being counted in the valid denominator.

Plus the correction that prompted the module: the sector name decides nothing.
For a bank the rules suppress debt_to_equity, current_ratio, gross_margin,
ev_ebitda and net_margin — while roe and grossed_up_yield stay meaningful.
Withholding a bank dividend-yield median would be the industrial-defaults
error running in reverse.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_peer_benchmarks.py
"""

import statistics
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
from compute.engine.peer_benchmarks import (  # noqa: E402
    MIN_VALID_FRACTION,
    MIN_VALID_N,
    BenchmarkReason,
    benchmark,
    benchmark_all,
    by_sector,
)


def valid(metric: str, value: float) -> Assessment:
    return Assessment(metric, Applicability.APPLICABLE, value, "",
                      Domain.GENERAL_CORPORATE, observed=value)


def suppressed(metric: str, value: float) -> Assessment:
    """A genuinely NOT_MEANINGFUL assessment, whatever the metric.

    Constructed rather than obtained via assess(..., Domain.BANK), because
    that is precisely the assumption this module exists to refute: roe and
    grossed_up_yield come back APPLICABLE for a bank, so a helper that equated
    "bank" with "suppressed" would build fixtures asserting the error they
    were written to disprove. It did, on the first run.
    """
    return Assessment(metric, Applicability.NOT_MEANINGFUL, None,
                      "out of domain", Domain.BANK, observed=value,
                      cause=Cause.DOMAIN)


def domain_suppressed(metric: str, value: float) -> Assessment:
    """The real thing, for metrics that genuinely are out of domain for a bank."""
    a = assess(metric, value, Domain.BANK)
    assert a.suppressed, f"{metric} is applicable for a bank — check the fixture"
    return a


def valid_many(metric: str, values) -> list:
    return [valid(metric, v) for v in values]


# ── Fixture 1 · an entirely invalid population produces nothing ───────────────

def test_a_wholly_suppressed_population_yields_no_statistic():
    banks = [domain_suppressed("debt_to_equity", v)
             for v in (4.6, 5.1, 3.9, 4.2, 4.8, 5.5)]
    b = benchmark("debt_to_equity", banks)

    assert not b.ok
    assert b.state is Applicability.NOT_MEANINGFUL
    assert (b.median, b.p25, b.p75) == (None, None, None)
    assert b.n_valid_peers == 0 and b.n_total_peers == 6
    assert "out of domain for every peer" in b.reason


def test_a_wholly_source_failed_population_says_so_distinctly():
    """The remedy differs: a feed repair, not a wider sector."""
    peers = [unhealthy("grossed_up_yield", "dividend feed incomplete")
             for _ in range(8)]
    b = benchmark("grossed_up_yield", peers)

    assert b.state is Applicability.UNAVAILABLE
    assert b.cause is Cause.SOURCE_UNHEALTHY
    assert "source unhealthy for every applicable peer" in b.reason


def test_an_empty_peer_group_is_unavailable_not_zero():
    b = benchmark("roe", [])
    assert not b.ok and b.n_total_peers == 0 and b.median is None


# ── Fixture 2 · one invalid member cannot move the valid peers ────────────────

def test_a_suppressed_member_does_not_shift_the_statistic():
    industrials = valid_many("debt_to_equity", [0.2, 0.4, 0.6, 0.8, 1.0, 1.2])
    clean = benchmark("debt_to_equity", industrials)

    contaminated = benchmark(
        "debt_to_equity", industrials + [domain_suppressed("debt_to_equity", 4.6)])

    assert clean.median == contaminated.median
    assert (clean.p25, clean.p75) == (contaminated.p25, contaminated.p75)
    assert contaminated.n_total_peers == clean.n_total_peers + 1
    assert contaminated.n_applicable_peers == clean.n_applicable_peers, \
        "an out-of-domain peer leaves the coverage denominator entirely"
    assert contaminated.n_valid_peers == clean.n_valid_peers


def test_the_denominator_travels_with_the_statistic():
    peers = valid_many("roe", [0.10, 0.12, 0.14, 0.16, 0.18]) + \
        [suppressed("roe", 0.9)]
    b = benchmark("roe", peers, min_fraction=0.5)

    assert b.n_valid_peers == 5 and b.n_applicable_peers == 5
    assert b.n_total_peers == 6, "the suppressed peer is still a peer"
    assert "5 of 5 valid observations" in b.describe()


def test_describe_conceals_nothing_when_unavailable():
    b = benchmark("debt_to_equity", [domain_suppressed("debt_to_equity", 4.6)] * 6)
    assert b.describe().startswith("unavailable:")


# ── Fixture 3 · suppressed members cannot pad the coverage gate ───────────────

def test_suppressed_members_do_not_count_toward_the_minimum():
    """Two valid companies plus twenty suppressed is not a peer group."""
    peers = valid_many("debt_to_equity", [0.3, 0.7]) + \
        [domain_suppressed("debt_to_equity", 4.6) for _ in range(20)]
    b = benchmark("debt_to_equity", peers)

    assert b.state is Applicability.INSUFFICIENT_DATA
    assert b.n_valid_peers == 2 and b.n_total_peers == 22
    assert b.median is None, "two companies do not have quartiles"


def test_a_mixed_unavailable_and_suppressed_population_still_fails_closed():
    peers = (valid_many("grossed_up_yield", [0.03, 0.04, 0.05])
             + [unhealthy("grossed_up_yield", "feed incomplete") for _ in range(6)]
             + [suppressed("grossed_up_yield", 0.9) for _ in range(3)])
    b = benchmark("grossed_up_yield", peers)

    assert not b.ok
    assert b.n_valid_peers == 3, "only the genuinely valid ones count"
    assert b.n_applicable_peers == 9, "the six unavailable stay in the denominator"
    assert b.n_total_peers == 12


def test_the_absolute_floor_and_the_fraction_both_bind():
    # Passes the fraction (100% of applicable) but not the floor.
    assert benchmark("roe", valid_many("roe", [0.1, 0.2, 0.3])).state \
        is Applicability.INSUFFICIENT_DATA

    # Passes the floor but not the fraction. The thirty must be *unavailable*
    # rather than suppressed: an unavailable peer is one the metric applies to
    # and we could not measure, so it stays in the denominator and the gap is
    # real. A suppressed peer leaves the denominator entirely.
    peers = valid_many("roe", [0.1] * 6) + \
        [Assessment("roe", Applicability.UNAVAILABLE, None, "no value",
                    Domain.GENERAL_CORPORATE, cause=Cause.SOURCE_MISSING)
         for _ in range(30)]
    b = benchmark("roe", peers)
    assert b.state is Applicability.INSUFFICIENT_DATA
    assert b.n_applicable_peers == 36 and b.n_valid_peers == 6

    # Passes both.
    assert benchmark("roe", valid_many("roe", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])).ok


def test_out_of_domain_peers_do_not_depress_coverage():
    """The other half of the denominator rule, and the reason it matters.

    Six industrials with valid leverage sitting in a sector of thirty-six,
    thirty of which are banks, is 100% coverage of the applicable population —
    not 17% of everything. Counting the banks would withhold a benchmark that
    is entirely sound.
    """
    peers = valid_many("debt_to_equity", [0.2, 0.4, 0.6, 0.8, 1.0, 1.2]) + \
        [domain_suppressed("debt_to_equity", 4.6) for _ in range(30)]
    b = benchmark("debt_to_equity", peers)

    assert b.ok, "the six industrials are a complete applicable population"
    assert b.coverage_pct == 100.0
    assert b.n_total_peers == 36 and b.n_applicable_peers == 6


def test_a_small_sector_is_not_told_its_coverage_is_poor():
    """3 of 3 valid is 100% coverage and still unpublishable. Saying
    'insufficient coverage' would send an operator looking for missing data
    that does not exist — the sector is simply small, which may never change.
    """
    b = benchmark("roe", valid_many("roe", [0.1, 0.2, 0.3]))

    assert b.reason_code is BenchmarkReason.INSUFFICIENT_PEER_POPULATION
    assert b.coverage_pct == 100.0
    assert "only 3 peers can carry this metric" in b.reason
    assert "coverage" not in b.reason


def test_a_large_sector_with_a_data_gap_is_told_exactly_that():
    peers = valid_many("roe", [0.1] * 6) + \
        [Assessment("roe", Applicability.UNAVAILABLE, None, "no value",
                    Domain.GENERAL_CORPORATE, cause=Cause.SOURCE_MISSING)
         for _ in range(30)]
    b = benchmark("roe", peers)

    assert b.reason_code is BenchmarkReason.INSUFFICIENT_COVERAGE
    assert "17%" in b.reason
    assert b.n_applicable_peers == 36


def test_adequate_population_and_coverage_but_too_few_numbers():
    """The third case: neither of the other two describes it."""
    peers = valid_many("roe", [0.1, 0.2, 0.3, 0.4]) + \
        [Assessment("roe", Applicability.UNAVAILABLE, None, "no value",
                    Domain.GENERAL_CORPORATE, cause=Cause.SOURCE_MISSING)
         for _ in range(2)]
    b = benchmark("roe", peers)

    assert b.n_applicable_peers == 6, "population is adequate"
    assert b.coverage_pct > 60.0, "coverage is adequate"
    assert b.reason_code is BenchmarkReason.INSUFFICIENT_VALID_OBSERVATIONS


def test_every_withheld_benchmark_carries_a_machine_readable_reason():
    withheld = [
        benchmark("roe", []),
        benchmark("debt_to_equity", [domain_suppressed("debt_to_equity", 4.6)] * 6),
        benchmark("grossed_up_yield",
                  [unhealthy("grossed_up_yield", "feed") for _ in range(8)]),
        benchmark("roe", valid_many("roe", [0.1, 0.2, 0.3])),
    ]
    for b in withheld:
        assert not b.ok and b.reason_code is not None


def test_a_published_benchmark_carries_no_reason_code():
    assert benchmark("roe", valid_many("roe", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])) \
        .reason_code is None


def test_a_healthy_benchmark_reports_real_quartiles():
    b = benchmark("roe", valid_many("roe", [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]))
    assert b.ok
    assert b.median == 0.175
    assert b.p25 < b.median < b.p75


# ── The sector name decides nothing ───────────────────────────────────────────

BANK_METRICS = ["debt_to_equity", "current_ratio", "gross_margin", "ev_ebitda",
                "roe", "net_margin", "grossed_up_yield"]


def bank_peer_group() -> dict:
    obs = Observation(equity=8e10, earnings=1e10, ebitda=1e10)
    out = {}
    for m in BANK_METRICS:
        out[m] = [assess(m, 0.1 + i * 0.01, Domain.BANK, obs) for i in range(8)]
    return out


def test_a_financials_sector_is_not_uniformly_invalid():
    """The correction that prompted this module. Five suppressed, two not.

    net_margin joined the suppressed side when it was governed before the V1
    freeze — a generic net income over revenue presumes an industrial revenue
    line. The point of the test is unchanged and is the ratio, not the count:
    a bank is neither wholly invalid nor wholly fine, and only the assessment
    can say which is which.
    """
    results = benchmark_all(BANK_METRICS, bank_peer_group())

    withheld = sorted(m for m, b in results.items() if not b.ok)
    published = sorted(m for m, b in results.items() if b.ok)

    assert withheld == ["current_ratio", "debt_to_equity", "ev_ebitda",
                        "gross_margin", "net_margin"]
    assert published == ["grossed_up_yield", "roe"]


def test_a_bank_dividend_yield_median_is_publishable():
    """Withholding it would be the industrial-defaults error in reverse."""
    b = benchmark_all(["grossed_up_yield"], bank_peer_group())["grossed_up_yield"]
    assert b.ok and b.median is not None and b.n_valid_peers == 8


def test_thresholds_are_named_constants_not_magic():
    assert MIN_VALID_N >= 2 and 0 < MIN_VALID_FRACTION <= 1


# ── The pair that guards against "sector determines applicability" ────────────

def test_cba_is_excluded_from_leverage_but_included_in_dividend_yield():
    """The permanent guard. Both halves must hold at once, for the same
    company, in the same run — one excluded, one included, decided per metric.
    """
    from compute.engine.dividends import DividendSource, FeedHealth
    from compute.engine.factor_applicability import apply_applicability

    import pandas as pd
    from datetime import date

    healthy = DividendSource(FeedHealth(latest_ex_date=date(2026, 9, 5),
                                        as_of=date(2026, 9, 10)))

    rows = [{"asx_code": "CBA", "sector": "Financials", "industry": "Banks",
             "is_reit": False, "is_miner": False, "revenue_ttm": 2.7e10,
             "debt_to_equity": 4.6, "grossed_up_yield": 0.0466}]
    for i, code in enumerate(["NAB", "WBC", "ANZ", "BEN", "BOQ"]):
        rows.append({"asx_code": code, "sector": "Financials",
                     "industry": "Banks", "is_reit": False, "is_miner": False,
                     "revenue_ttm": 1e10, "debt_to_equity": 4.0 + i * 0.2,
                     "grossed_up_yield": 0.04 + i * 0.002})

    df = pd.DataFrame(rows)
    masked = apply_applicability(df, healthy)
    sectors = {r["asx_code"]: r["sector"] for r in rows}

    results = by_sector(masked.assessments, sectors,
                        ["debt_to_equity", "grossed_up_yield"])["Financials"]

    leverage = results["debt_to_equity"]
    assert not leverage.ok, "CBA must not participate in a D/E peer statistic"
    assert leverage.reason_code is BenchmarkReason.OUT_OF_DOMAIN_FOR_ALL
    assert leverage.n_applicable_peers == 0

    yield_bm = results["grossed_up_yield"]
    assert yield_bm.ok, "CBA must participate in a dividend-yield statistic"
    assert yield_bm.n_valid_peers == 6
    assert yield_bm.median is not None


def test_the_same_bank_loses_its_dividend_yield_when_the_feed_breaks():
    """And the other axis: applicability unchanged, availability gone."""
    from compute.engine.dividends import DividendSource, FeedHealth
    from compute.engine.factor_applicability import apply_applicability

    import pandas as pd
    from datetime import date

    broken = DividendSource(FeedHealth(latest_ex_date=date(2026, 8, 3),
                                       as_of=date(2026, 9, 10)))

    rows = [{"asx_code": c, "sector": "Financials", "industry": "Banks",
             "is_reit": False, "is_miner": False, "revenue_ttm": 1e10,
             "grossed_up_yield": 0.04}
            for c in ["CBA", "NAB", "WBC", "ANZ", "BEN", "BOQ"]]

    masked = apply_applicability(pd.DataFrame(rows), broken)
    sectors = {r["asx_code"]: r["sector"] for r in rows}
    b = by_sector(masked.assessments, sectors, ["grossed_up_yield"])["Financials"]

    result = b["grossed_up_yield"]
    assert result.reason_code is BenchmarkReason.SOURCE_UNHEALTHY_FOR_ALL
    assert result.n_applicable_peers == 6, \
        "the metric still applies to a bank — only the data is missing"


# ── net_margin · banks leave the population, the sector still publishes ───────

def financials_group() -> tuple[dict, dict]:
    """Six banks and six other financials, all with a net margin recorded."""
    obs = Observation(equity=8e10, earnings=1e10)
    assessments, sectors = {}, {}

    for i, code in enumerate(["CBA", "NAB", "WBC", "ANZ", "BEN", "BOQ"]):
        assessments[code] = {
            "net_margin": assess("net_margin", 0.30 + i * 0.01, Domain.BANK, obs)}
        sectors[code] = "Financials"

    for i, code in enumerate(["QBE", "IAG", "SUN", "MPL", "NWL", "PNI"]):
        domain = Domain.INSURER if i < 4 else Domain.CAPITAL_MARKETS
        assessments[code] = {
            "net_margin": assess("net_margin", 0.10 + i * 0.01, domain, obs)}
        sectors[code] = "Financials"

    return assessments, sectors


def test_a_financials_net_margin_benchmark_excludes_banks_and_still_publishes():
    assessments, sectors = financials_group()
    b = by_sector(assessments, sectors, ["net_margin"])["Financials"]["net_margin"]

    assert b.ok, "the six non-bank financials are a complete applicable population"
    assert b.n_total_peers == 12
    assert b.n_applicable_peers == 6, "the six banks left the population"
    assert b.n_valid_peers == 6
    assert b.coverage_pct == 100.0


def test_bank_net_margins_cannot_move_the_remaining_statistic():
    """The mask-before-statistic rule, on the metric just governed.

    Bank net margins sit at 0.30-0.35 and the others at 0.10-0.15, so leaving
    the banks in would drag the median from 0.125 to about 0.225 — nearly
    doubling the number a customer compares an insurer against.
    """
    assessments, sectors = financials_group()
    with_banks = [a["net_margin"] for a in assessments.values()]
    without = [a["net_margin"] for c, a in assessments.items()
               if c not in ("CBA", "NAB", "WBC", "ANZ", "BEN", "BOQ")]

    published = by_sector(assessments, sectors,
                          ["net_margin"])["Financials"]["net_margin"]
    non_bank_only = benchmark("net_margin", without)

    assert published.median == non_bank_only.median
    assert (published.p25, published.p75) == (non_bank_only.p25, non_bank_only.p75)
    assert published.median < 0.16, \
        "a median above 0.16 means bank margins are still in the aggregate"

    # And the raw arithmetic the contract prevents, asserted so the size of
    # the distortion is on the record rather than implied.
    raw = statistics.median([a.observed for a in with_banks])
    assert raw > published.median * 1.7


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
