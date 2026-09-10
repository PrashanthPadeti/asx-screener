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
    GOVERNED_METRICS,
    LATEST_MODEL_VERSION,
    ROW,
    SourceHealth,
    UnsupportedModelVersion,
    supported_version,
    assert_complete,
    decode,
    decode_all,
    encode,
    encode_json,
    governed_for,
    load_states,
    persist_row,
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


def kinds(vs) -> dict:
    return {v.metric: v.kind for v in vs}


def test_a_null_with_no_state_entry_is_a_violation_not_a_default():
    """The rule that makes sparseness safe."""
    assert kinds(violations({"roe": 0.18, "pe_ratio": None}, {})) == \
        {"pe_ratio": "unexplained_null"}
    assert violations({"roe": 0.18}, {}) == []


def test_a_stale_entry_beside_a_populated_value_is_equally_a_violation():
    """The other direction: a suppressed -> applicable transition that only
    half-applied. A contract-aware reader suppresses a number that is now
    perfectly good, which is a silent regression the opposite way."""
    stale = {"roe": {"state": "not_meaningful", "cause": "domain"}}
    assert kinds(violations({"roe": 0.18}, stale)) == \
        {"roe": "contradictory_state"}


def test_assert_complete_refuses_to_write_an_unexplained_null():
    try:
        assert_complete({"grossed_up_yield": None}, {})
    except ValueError as e:
        assert "grossed_up_yield" in str(e) and "unexplained_null" in str(e)
    else:
        raise AssertionError("the write path must refuse")


def test_assert_complete_refuses_to_write_a_contradiction():
    try:
        assert_complete({"roe": 0.18},
                        {"roe": {"state": "not_meaningful"}})
    except ValueError as e:
        assert "contradictory_state" in str(e)
    else:
        raise AssertionError("the write path must refuse")


# ── Lock 2 · atomic transitions, both directions ──────────────────────────────

def test_persist_row_produces_a_consistent_pair_by_construction():
    """Two statements can half-apply; one function returning both cannot."""
    values, states = persist_row(compute_cba())
    assert violations(values, states) == []
    assert values["altman_z_score"] is None and "altman_z_score" in states
    assert values["roe"] == 0.1284 and "roe" not in states


def test_suppressed_to_applicable_drops_the_entry_and_populates_the_value():
    before = {"roe": assess("roe", 2.06, Domain.GENERAL_CORPORATE,
                            Observation(equity=-1.0))}
    after = {"roe": assess("roe", 0.18, Domain.GENERAL_CORPORATE,
                           Observation(equity=5e8))}

    v0, s0 = persist_row(before)
    v1, s1 = persist_row(after)

    assert v0["roe"] is None and "roe" in s0
    assert v1["roe"] == 0.18 and "roe" not in s1
    assert violations(v1, s1) == [], "no stale key survives the transition"


def test_applicable_to_suppressed_nulls_the_value_and_adds_the_entry():
    """The same metric on the same company, reclassified as a bank."""
    before = {"debt_to_equity": assess("debt_to_equity", 4.6,
                                       Domain.GENERAL_CORPORATE)}
    after = {"debt_to_equity": assess("debt_to_equity", 4.6, Domain.BANK)}

    v0, s0 = persist_row(before)
    v1, s1 = persist_row(after)

    assert v0["debt_to_equity"] == 4.6 and "debt_to_equity" not in s0
    assert v1["debt_to_equity"] is None and "debt_to_equity" in s1
    assert s1["debt_to_equity"]["cause"] == "domain"
    assert s1["debt_to_equity"]["observed"] == 4.6, "forensics kept in the sidecar"
    assert violations(v1, s1) == []


def test_repeated_transitions_each_leave_exactly_one_interpretation():
    """SOURCE_UNHEALTHY -> APPLICABLE -> INSUFFICIENT_HISTORY -> APPLICABLE."""
    from compute.engine.applicability import unhealthy

    sequence = [
        (unhealthy("grossed_up_yield", "dividend feed incomplete"),
         Applicability.UNAVAILABLE, Cause.SOURCE_UNHEALTHY, None),
        (assess("grossed_up_yield", 0.045, Domain.GENERAL_CORPORATE),
         Applicability.APPLICABLE, None, 0.045),
        (assess("grossed_up_yield", 0.045, Domain.GENERAL_CORPORATE,
                Observation(periods_available=1, periods_required=3)),
         Applicability.INSUFFICIENT_DATA, Cause.INSUFFICIENT_HISTORY, None),
        (assess("grossed_up_yield", 0.051, Domain.GENERAL_CORPORATE),
         Applicability.APPLICABLE, None, 0.051),
    ]

    for step, (assessment, state, cause, expected_value) in enumerate(sequence):
        values, states = persist_row({assessment.metric: assessment})
        assert violations(values, states) == [], f"step {step} left a contradiction"

        back = decode("grossed_up_yield", values["grossed_up_yield"], states)
        assert back.state is state, f"step {step}"
        assert back.cause is cause, f"step {step}"
        assert back.value == expected_value, f"step {step}"


# ── Lock 3 · version-aware completeness ───────────────────────────────────────

def test_a_governed_metric_absent_from_the_row_is_a_violation():
    vs = violations({"roe": 0.18}, {}, model_version=LATEST_MODEL_VERSION)
    by_kind = {v.kind for v in vs}
    assert "missing_governed" in by_kind
    assert any(v.metric == "grossed_up_yield" for v in vs)


def test_not_checking_a_version_is_distinct_from_a_row_having_none():
    """UNSPECIFIED is the in-memory pre-write check, where no version exists
    yet. It is not a claim that the row is unversioned."""
    assert violations({"roe": 0.18}, {}) == []


# ── Unknown model version fails closed ────────────────────────────────────────

def test_an_unknown_version_cannot_pass_completeness_validation():
    """Unknown model version means unknown contract, not no contract.

    Returning an empty governed set here would let a row from a future model
    validate clean precisely because nothing could check it.
    """
    vs = violations({"roe": 0.18}, {}, model_version="FACTOR_MODEL_V99")
    assert kinds(vs) == {ROW: "unsupported_model_version"}
    assert vs != [], "fail-open is the defect this replaces"

    try:
        assert_complete({"roe": 0.18}, {}, model_version="FACTOR_MODEL_V99")
    except ValueError as e:
        assert "unsupported_model_version" in str(e)
    else:
        raise AssertionError("completeness must refuse an unknown contract")


def test_an_unversioned_row_is_reported_distinctly_from_an_unknown_one():
    """Both fail closed; they are different remediations. Unversioned means
    the canonical writer has not been through yet — the expected state during
    rollout. Unsupported means this build is older than the row."""
    assert kinds(violations({"roe": 0.18}, {}, model_version=None)) == \
        {ROW: "unversioned"}


def test_an_unknown_version_row_cannot_be_served():
    values, states = persist_row(compute_cba())
    try:
        row_payload(values, states, None, Domain.BANK,
                    model_version="FACTOR_MODEL_V99")
    except UnsupportedModelVersion as e:
        assert "FACTOR_MODEL_V99" in str(e)
    else:
        raise AssertionError("a row whose semantics are unknown must not be "
                             "served as if they were known")


def test_governed_for_raises_rather_than_returning_empty():
    for bad in ("FACTOR_MODEL_V99", None):
        try:
            governed_for(bad)
        except UnsupportedModelVersion:
            pass
        else:
            raise AssertionError(f"governed_for({bad!r}) must raise")

    assert governed_for(LATEST_MODEL_VERSION), "known versions still resolve"
    assert supported_version(LATEST_MODEL_VERSION)
    assert not supported_version("FACTOR_MODEL_V99")


def test_rollout_validation_reports_unsupported_not_zero():
    """The rollout gate must not read an uninterpretable row as clean."""
    values, states = persist_row(compute_cba())
    vs = violations(values, states, model_version="FACTOR_MODEL_V99")

    assert any(v.kind == "unsupported_model_version" for v in vs)
    assert len(vs) > 0, "zero violations would mean 'safe to enable consumers'"


# ── UNSPECIFIED must not survive the persistence boundary ────────────────────

def test_unspecified_is_a_computation_time_state_only():
    """It is legal while an assessment is being built and never after.

    By the time anything is written or served there is a real run, and that
    run has a version — so a surviving sentinel means a write path skipped
    version attribution entirely, and the row would validate against nothing.
    """
    values, states = persist_row(compute_cba())

    # Computation time: no version assigned yet, and that is fine.
    assert violations(values, states) == []

    # Serving time: every path that takes a version rejects the sentinel.
    for version, expected in ((None, "unversioned"),
                              ("FACTOR_MODEL_V99", "unsupported_model_version")):
        assert kinds(violations(values, states, model_version=version)) \
            .get(ROW) == expected


def test_a_write_must_carry_a_version_by_the_time_it_lands():
    """The lifecycle assertion: validating a persisted row without naming its
    version is not a pass, it is a check that was never run."""
    values, states = persist_row(compute_cba())

    unchecked = violations(values, states)
    checked = violations(values, states, model_version=None)

    assert unchecked == [], "the sentinel suppresses the version check"
    assert checked, "naming the row's actual version surfaces the problem"
    assert unchecked != checked, \
        "UNSPECIFIED and None must not be the same call"


def test_serving_with_the_sentinel_does_not_assert_validity():
    """row_payload with UNSPECIFIED renders, but claims nothing about the
    contract — the caller has not asked it to check one."""
    values, states = persist_row(compute_cba())
    payload = row_payload(values, states, None, Domain.BANK)

    assert "compute_run_id" not in payload
    assert payload["states"]["grossed_up_yield"]["cause"] == "source_unhealthy"


# ── The round trip must preserve who participates, not just what each is ─────

def test_the_valid_population_survives_the_round_trip():
    """A codec can preserve every individual state correctly and still change
    *who participates* once the row is reconstructed — which would move every
    peer statistic without any single metric looking wrong.
    """
    from compute.engine.peer_benchmarks import valid_population

    before = compute_cba()
    values, states = persist_row(before)
    after = decode_all(values, states, Domain.BANK)

    assert valid_population(before.values()) == valid_population(after.values())


def test_a_reconstructed_row_produces_an_identical_benchmark():
    """The consumer-level version of the same assertion."""
    from compute.engine.peer_benchmarks import benchmark

    peers_before, peers_after = [], []
    for i in range(8):
        row = assess_all_bank()
        row["roe"] = assess("roe", 0.10 + i * 0.01, Domain.BANK,
                            Observation(equity=8e10))
        values, states = persist_row(row)
        back = decode_all(values, states, Domain.BANK)

        peers_before.append(row["roe"])
        peers_after.append(back["roe"])

    b_before = benchmark("roe", peers_before)
    b_after = benchmark("roe", peers_after)

    assert b_before.ok and b_after.ok
    assert (b_before.n_valid_peers, b_before.median) == (b_after.n_valid_peers, b_after.median)
    assert (b_before.p25, b_before.p75) == (b_after.p25, b_after.p75)


def test_a_suppressed_metric_stays_out_of_the_population_after_persistence():
    from compute.engine.peer_benchmarks import benchmark

    rows = [persist_row(assess_all_bank()) for _ in range(6)]
    restored = [decode_all(v, s, Domain.BANK)["debt_to_equity"] for v, s in rows]

    b = benchmark("debt_to_equity", restored)
    assert b.n_valid_peers == 0 and b.median is None, \
        "a suppressed value must not become a peer observation on reload"


def test_a_known_version_still_validates_normally():
    """Fail-closed on unknown must not break the supported path."""
    governed = GOVERNED_METRICS[LATEST_MODEL_VERSION]
    values = {m: None for m in governed}
    states = {m: {"state": "unavailable", "cause": "source_missing"}
              for m in governed}
    assert violations(values, states, LATEST_MODEL_VERSION) == []


def test_the_governed_set_is_pinned_not_derived():
    """If it were computed from SENSITIVE live, adding a metric next quarter
    would retroactively make every existing V1 row incomplete."""
    from compute.engine.metric_registry import SENSITIVE

    v1 = GOVERNED_METRICS["FACTOR_MODEL_V1"]
    missing = SENSITIVE - v1
    assert not missing, (
        f"{sorted(missing)} became sensitive after V1 was pinned. Add them to "
        f"a NEW model version rather than to V1, or old rows retroactively "
        f"fail validation for lacking a state they never promised.")


def test_a_fully_governed_row_passes():
    governed = GOVERNED_METRICS[LATEST_MODEL_VERSION]
    values = {m: None for m in governed}
    states = {m: {"state": "unavailable", "cause": "source_missing"}
              for m in governed}
    assert violations(values, states, LATEST_MODEL_VERSION) == []


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
                          detail={"dividends": "38 days behind"},
                          run_id=4711)
    back = SourceHealth.from_payload(json.loads(json.dumps(health.to_payload())))

    assert back.unhealthy_sources == ("dividends",)
    assert back.run_id == 4711
    assert not back.healthy


# ── Lock 4 · run provenance is a join, not a timestamp guess ──────────────────

def test_the_row_carries_the_run_that_produced_it():
    values, states = persist_row(compute_cba())
    health = SourceHealth(run_at=datetime(2026, 9, 10, 8, 30),
                          unhealthy_sources=("dividends",),
                          detail={"dividends": BROKEN_FEED.reason},
                          factor_model_version=LATEST_MODEL_VERSION,
                          run_id=4711)

    payload = row_payload(values, states, health, Domain.BANK, compute_run_id=4711)

    assert payload["compute_run_id"] == 4711
    assert payload["source_health"]["run_id"] == 4711
    assert payload["source_health"]["factor_model_version"] == LATEST_MODEL_VERSION


def test_a_row_cannot_be_served_with_another_runs_health():
    """The failure this closes: a SOURCE_UNHEALTHY row whose justifying feed
    observation has been overwritten by two later runs."""
    values, states = persist_row(compute_cba())
    health = SourceHealth(run_at=datetime(2026, 9, 10, 8, 30), run_id=4712)

    try:
        row_payload(values, states, health, Domain.BANK, compute_run_id=4711)
    except ValueError as e:
        assert "4711" in str(e) and "4712" in str(e)
    else:
        raise AssertionError("mismatched provenance must not serve")


def test_a_legacy_row_has_no_run_and_says_so():
    values, states = persist_row(compute_cba())
    payload = row_payload(values, states, None, Domain.BANK)
    assert "compute_run_id" not in payload, "absent, not zero or guessed"


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
