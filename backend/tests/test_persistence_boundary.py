"""
The whole chain — source to consumer, across persistence
========================================================
Serialisation was covered; persistence is where the contract was going to be
lost. ``daily_compute`` reduces an assessment to a nullable numeric column, and
a route reading it back gets ``NULL`` with no way to recover the cause.

So this walks the entire path, with a real JSON round-trip in the middle
standing in for the database:

    source -> assessment -> compute -> persistence -> API -> consumer

and asserts the four invariants at the far end:

    1. source-unhealthy dividend metrics cannot satisfy filters
    2. they cannot generate anomalies
    3. they cannot trigger composite reweighting
    4. their cause survives persistence and serialisation

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_persistence_boundary.py
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Cause,
    Domain,
    Observation,
    PredicateResult,
    Weighting,
    assess,
    assess_composite,
    predicate_result,
    refresh_gate,
    usable_values,
)
from compute.engine.dividends import DividendSource, FeedHealth  # noqa: E402
from compute.engine.metric_states import (  # noqa: E402
    SourceHealth,
    assert_complete,
    decode,
    decode_all,
    encode,
    encode_json,
    load_states,
    row_payload,
    violations,
)

TODAY = date(2026, 9, 10)
BROKEN_FEED = FeedHealth(latest_ex_date=date(2026, 8, 3), as_of=TODAY,
                         recent_rows=0, recent_issuers=0)

CBA_ROWS = [
    {"ex_date": date(2026, 2, 18), "amount": 2.35, "franking_pct": 100.0,
     "grossed_up": 3.357143},
    {"ex_date": date(2025, 8, 20), "amount": 2.60, "franking_pct": 100.0,
     "grossed_up": 3.714286},
]


def compute_cba() -> dict:
    """What the engine produces for CBA today: a bank, on a broken feed."""
    source = DividendSource(BROKEN_FEED)
    out = source.assessments(CBA_ROWS, close=158.690, domain=Domain.BANK)
    out.update(assess_all_bank())
    return out


def assess_all_bank() -> dict:
    values = {"altman_z_score": -0.15, "debt_to_equity": 4.6,
              "current_ratio": 0.1, "roe": 0.1284}
    return {m: assess(m, v, Domain.BANK) for m, v in values.items()}


def round_trip(assessments: dict) -> tuple[dict, dict]:
    """Write to columns + sidecar, then read back the way a route would."""
    values = {m: a.value for m, a in assessments.items()}
    stored_json = encode_json(assessments)           # the ::jsonb parameter
    states = load_states(stored_json)                 # what the driver returns
    return values, states


# ── The sidecar itself ────────────────────────────────────────────────────────

def test_only_non_applicable_metrics_are_recorded():
    payload = encode(compute_cba())

    assert "roe" not in payload, "applicable metrics stay out of the sidecar"
    assert payload["altman_z_score"]["cause"] == "domain"
    assert payload["grossed_up_yield"]["cause"] == "source_unhealthy"


def test_the_payload_is_json_serialisable_and_stable():
    a = encode_json(compute_cba())
    assert json.loads(a)
    assert a == encode_json(compute_cba()), "sorted keys, stable across runs"


def test_a_null_with_no_state_entry_is_a_violation_not_a_default():
    """The rule that makes sparseness safe."""
    assert violations({"roe": 0.18, "pe_ratio": None}, {}) == ["pe_ratio"]
    assert violations({"roe": 0.18}, {}) == []


def test_assert_complete_refuses_to_write_an_unexplained_null():
    try:
        assert_complete({"grossed_up_yield": None}, {})
    except ValueError as e:
        assert "grossed_up_yield" in str(e)
    else:
        raise AssertionError("the write path must refuse")


def test_a_row_written_by_the_engine_has_no_violations():
    values, states = round_trip(compute_cba())
    assert violations(values, states) == []
    assert_complete(values, states)


# ── Invariant 4 · the cause survives the round trip ───────────────────────────

def test_the_cause_survives_persistence():
    values, states = round_trip(compute_cba())
    back = decode_all(values, states, Domain.BANK)

    assert back["grossed_up_yield"].cause is Cause.SOURCE_UNHEALTHY
    assert back["altman_z_score"].cause is Cause.DOMAIN
    assert back["roe"].ok and back["roe"].value == 0.1284


def test_the_five_causes_are_distinguishable_after_a_round_trip():
    originals = {
        "altman_z_score": assess("altman_z_score", -0.15, Domain.BANK),
        "roe": assess("roe", 2.06, Domain.GENERAL_CORPORATE,
                      Observation(equity=-1.0)),
        "pe_ratio": assess("pe_ratio", None, Domain.GENERAL_CORPORATE),
        "revenue_cagr_5y": assess(
            "revenue_cagr_5y", 0.3, Domain.GENERAL_CORPORATE,
            Observation(periods_available=3, periods_required=5)),
        "grossed_up_yield": DividendSource(BROKEN_FEED).assessments(
            CBA_ROWS, 158.69, domain=Domain.BANK)["grossed_up_yield"],
    }
    values, states = round_trip(originals)
    back = decode_all(values, states, Domain.BANK)

    assert {m: a.cause for m, a in back.items()} == {
        "altman_z_score": Cause.DOMAIN,
        "roe": Cause.OBSERVATION,
        "pe_ratio": Cause.SOURCE_MISSING,
        "revenue_cagr_5y": Cause.INSUFFICIENT_HISTORY,
        "grossed_up_yield": Cause.SOURCE_UNHEALTHY,
    }


def test_a_legacy_row_fails_closed_rather_than_inventing_a_cause():
    """A row written before the sidecar existed must not read as applicable."""
    a = decode("grossed_up_yield", None, states={})
    assert not a.ok
    assert "contract violation" in a.reason


def test_a_reconstructed_assessment_still_hides_the_value():
    values, states = round_trip(compute_cba())
    back = decode_all(values, states, Domain.BANK)
    assert back["altman_z_score"].value is None
    assert usable_values(back).keys() == {"roe"}


# ── The API shape a route returns ─────────────────────────────────────────────

def test_the_route_payload_never_makes_the_client_infer_a_cause():
    values, states = round_trip(compute_cba())
    health = SourceHealth(run_at=datetime(2026, 9, 10, 8, 30),
                          unhealthy_sources=("dividends",),
                          detail={"dividends": BROKEN_FEED.reason},
                          factor_model_version="FACTOR_MODEL_V1")

    payload = row_payload(values, states, health, Domain.BANK)

    assert payload["metrics"]["grossed_up_yield"] is None
    assert payload["states"]["grossed_up_yield"]["cause"] == "source_unhealthy"
    assert payload["states"]["grossed_up_yield"]["display"] == "Data unavailable"
    assert payload["source_health"]["unhealthy_sources"] == ["dividends"]
    assert "roe" not in payload["states"], "applicable metrics carry no state"


def test_source_health_round_trips():
    health = SourceHealth(run_at=datetime(2026, 9, 10, 8, 30),
                          unhealthy_sources=("dividends",),
                          detail={"dividends": "38 days behind"})
    back = SourceHealth.from_payload(json.loads(json.dumps(health.to_payload())))

    assert back.unhealthy_sources == ("dividends",)
    assert not back.healthy


def test_a_healthy_run_records_no_unhealthy_sources():
    assert SourceHealth(run_at=datetime(2026, 9, 10, 8, 30)).healthy


# ── Invariant 1 · cannot satisfy a filter, after persistence ──────────────────

def test_a_persisted_source_failure_cannot_match_a_yield_filter():
    values, states = round_trip(compute_cba())
    back = decode_all(values, states, Domain.BANK)

    assert predicate_result(back["grossed_up_yield"]) is PredicateResult.NO_DATA
    assert "grossed_up_yield" not in usable_values(back)


def test_a_persisted_nm_still_cannot_exclude_a_bank():
    values, states = round_trip(compute_cba())
    back = decode_all(values, states, Domain.BANK)

    assert predicate_result(back["debt_to_equity"]) is PredicateResult.NOT_ELIGIBLE


# ── Invariant 2 · cannot generate an anomaly, after persistence ───────────────

def test_a_persisted_source_failure_cannot_fire_the_yield_anomaly():
    values, states = round_trip(compute_cba())
    back = decode_all(values, states, Domain.BANK)
    a = back["grossed_up_yield"]

    assert a.value is None
    assert predicate_result(a) is not PredicateResult.EVALUATED
    # The naive predicate would coerce and fire at the 12% threshold.
    assert (a.value or 0) <= 0.12
    assert "grossed_up_yield" not in usable_values(back)


# ── Invariant 3 · cannot trigger composite reweighting, after persistence ─────

def test_a_persisted_source_failure_blocks_the_composite():
    values, states = round_trip(compute_cba())
    back = decode_all(values, states, Domain.BANK)

    income = back["grossed_up_yield"]
    assert not income.reweightable

    c = assess_composite("composite_score", 65.0,
                         [back["roe"], income], Domain.BANK)
    assert c.cause is Cause.SOURCE_UNHEALTHY
    assert c.value is None


def test_weighting_built_from_persisted_state_refuses_to_renormalise():
    values, states = round_trip(compute_cba())
    back = decode_all(values, states, Domain.BANK)

    nominal = {"value": .2, "quality": .2, "growth": .2, "momentum": .2,
               "income": .2}
    unhealthy_families = frozenset(
        {"income"} if back["grossed_up_yield"].source_unhealthy else set())
    w = Weighting(nominal, frozenset(nominal) - unhealthy_families,
                  unhealthy=unhealthy_families)

    assert not w.may_reweight and w.effective == {}


def test_alphafive_refresh_is_declined_from_persisted_state():
    values, states = round_trip(compute_cba())
    back = decode_all(values, states, Domain.BANK)

    income = back["grossed_up_yield"]
    families = ["value_score", "quality_score", "growth_score",
                "momentum_score", "grossed_up_yield"]
    gate = refresh_gate(list(back.values()), families,
                        last_published="2026-09-07")

    assert income.source_unhealthy
    assert not gate.permitted
    assert "last published computation" in gate.message


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
