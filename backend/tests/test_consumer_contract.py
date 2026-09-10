"""
Consumer contract — a suppressed metric must not leak back in
=============================================================
The applicability layer decides. This suite is about how the decision *leaves*,
because the dangerous failure was never a missing check — it is:

    float(a.value or 0)

which turns a suppressed metric into a real number that sorts last, scores
zero, and reads on a page as a fact. That is the same class of bug as the
original defect, arriving through the back door, and no amount of correct
gating upstream survives it.

So these tests walk the four boundaries a value can cross — composite, sort,
filter/predicate, and serialisation — and assert the suppressed metric cannot
be reconstructed on the far side.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_consumer_contract.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Domain,
    Observation,
    Weighting,
    assess,
    assess_all,
    assess_composite,
    predicate_excludes,
    to_payload,
    usable_values,
)
from compute.engine.dividends import dividend_metrics  # noqa: E402
from compute.engine.metric_registry import (  # noqa: E402
    Unresolved,
    audit_definition,
    graph_health,
    normalise,
    resolve,
)

# CBA as the engine sees it: four suppressed, two valid.
CBA = assess_all(
    {"altman_z_score": -0.15, "debt_to_equity": 4.6, "current_ratio": 0.1,
     "piotroski_f_score": 3.0, "roe": 0.1284, "dividend_yield": 0.0326},
    Domain.BANK, Observation(equity=8e10, earnings=1e10),
)


# ── Boundary 1 · into a composite ─────────────────────────────────────────────

def test_usable_values_omits_rather_than_zeroes():
    """The whole trick: absent, not zero. There is nothing to rank on."""
    vals = usable_values(CBA)

    assert set(vals) == {"roe", "dividend_yield"}
    for suppressed in ("altman_z_score", "debt_to_equity", "current_ratio",
                       "piotroski_f_score"):
        assert suppressed not in vals, "a zero here ranks the bank last"


def test_the_naive_coercion_is_what_usable_values_prevents():
    """Documents the bug being designed against, so the intent is not lost."""
    naive = {a.metric: (a.value or 0) for a in CBA.values()}
    assert naive["debt_to_equity"] == 0, "this is what a caller would get wrong"
    assert "debt_to_equity" not in usable_values(CBA), "and what the API prevents"


def test_a_suppressed_constituent_cannot_be_averaged_back_in():
    quality = assess_composite("quality_score", 41.0, list(CBA.values()), Domain.BANK,
                               material=["debt_to_equity", "piotroski_f_score", "roe"])
    assert quality.value is None
    assert quality.value is not quality.observed, "observed must not be the value"
    assert quality.observed == 41.0, "but it is still available as evidence"


def test_effective_weighting_declares_the_smaller_basis():
    """A four-factor mean competing against five-factor stocks must say so."""
    nominal = {"value": .2, "quality": .2, "growth": .2, "momentum": .2, "income": .2}
    w = Weighting(nominal, frozenset({"value", "growth", "momentum", "income"}))

    assert w.is_reweighted and w.coverage == "4/5 applicable"
    assert abs(sum(w.effective.values()) - 1.0) < 1e-9


# ── Boundary 2 · into a sort ──────────────────────────────────────────────────

def test_sorting_on_usable_values_cannot_see_suppressed_metrics():
    rows = {"CBA": CBA,
            "WES": assess_all({"debt_to_equity": 0.8}, Domain.GENERAL_CORPORATE)}

    ranked = sorted(
        (code for code in rows if "debt_to_equity" in usable_values(rows[code])),
        key=lambda code: usable_values(rows[code])["debt_to_equity"],
    )
    assert ranked == ["WES"], "CBA is absent from the ranking, not last in it"


def test_a_suppressed_value_is_not_recoverable_from_the_assessment():
    a = CBA["debt_to_equity"]
    assert a.value is None
    assert not a.ok
    assert a.observed == 4.6, "remembered for evidence"
    # The only numeric accessor a consumer is offered ignores it entirely.
    assert usable_values([a]) == {}


# ── Boundary 3 · into a predicate ─────────────────────────────────────────────

def test_an_nm_predicate_neither_includes_nor_excludes():
    """It does not evaluate FALSE — it fails to evaluate."""
    a = CBA["debt_to_equity"]
    assert not predicate_excludes(a)

    # A filter written the obvious way would exclude on the coerced zero.
    assert (a.value or 0) <= 1.5, "the naive predicate 'passes', by accident"
    assert not predicate_excludes(a), "the contract refuses to answer instead"


def test_anomaly_predicate_on_a_suppressed_input_cannot_fire():
    """3 of 7 anomaly types read metrics that may be NM for the issuer."""
    piotroski = assess("piotroski_f_score", 3.0, Domain.BANK)
    rsi = assess("rsi_14", 72.0, Domain.BANK)

    combined = assess_composite("rsi_overbought_weak_fundamentals", 1.0,
                                [rsi, piotroski], Domain.BANK)
    assert combined.state is Applicability.NOT_MEANINGFUL
    assert not predicate_excludes(combined)
    assert "piotroski_f_score" in combined.reason, \
        "must not silently keep the technical half and the fundamental wording"


def test_the_yield_anomaly_reads_a_corrected_number():
    """End to end: dividends module -> anomaly threshold."""
    rows = [{"ex_date": __import__("datetime").date(2026, 8, 15), "amount": 0.35,
             "franking_pct": 100.0, "grossed_up": None},
            {"ex_date": __import__("datetime").date(2026, 2, 15), "amount": 0.35,
             "franking_pct": 100.0, "grossed_up": None},
            {"ex_date": __import__("datetime").date(2025, 8, 15), "amount": 0.35,
             "franking_pct": 100.0, "grossed_up": None}]
    m = dividend_metrics(rows, close=10.0,
                         as_of=__import__("datetime").date(2026, 9, 9))
    assert m["grossed_up_yield"] <= 0.12, "no false HIGH_GROSSED_UP_YIELD"


# ── Boundary 4 · into a response body ─────────────────────────────────────────

def test_serialisation_preserves_the_invariant():
    """The frontend must not re-acquire the freedom this module removed."""
    payload = to_payload(CBA["altman_z_score"])

    assert payload["value"] is None
    assert payload["state"] == "not_meaningful"
    assert payload["display"] == "NM"
    assert payload["reason"]
    assert "observed_value" not in payload, "not emitted unless asked for"


def test_observed_is_opt_in_and_separately_named():
    payload = to_payload(CBA["altman_z_score"], include_observed=True)
    assert payload["observed_value"] == -0.15
    assert payload["value"] is None, "value never weakens, whatever else is emitted"


def test_an_applicable_metric_serialises_its_number():
    payload = to_payload(CBA["roe"])
    assert payload["value"] == 0.1284 and payload["state"] == "applicable"


def test_no_payload_field_carries_a_suppressed_number():
    for a in CBA.values():
        if a.ok:
            continue
        payload = to_payload(a)
        assert a.observed not in [v for k, v in payload.items()
                                  if k != "reason" and isinstance(v, (int, float))]


# ── Unresolved diagnostics carry an owner ─────────────────────────────────────

def test_unresolved_says_why_not_just_that():
    res = resolve("some_metric_nobody_declared")
    assert res.unresolved_reasons["some_metric_nobody_declared"] is Unresolved.UNKNOWN_METRIC


def test_import_failure_is_distinguishable_from_a_missing_declaration():
    """quality_score unresolved for want of pandas is a packaging problem."""
    health = graph_health()
    res = resolve("quality_score")

    if health["factor_layer_loaded"]:
        assert not res.unresolved, "the factor layer resolves it"
    else:
        assert res.unresolved_reasons["quality_score"] is Unresolved.IMPORT_FAILURE
        assert health["factor_load_error"], "and the error is reported"


def test_the_report_labels_each_unresolved_node_with_its_reason():
    f = audit_definition("Experimental", ["not_a_real_metric"])
    assert f.reasons["not_a_real_metric"] is Unresolved.UNKNOWN_METRIC
    assert "unknown_metric" in f.render()


# ── Policy runs on canonical identity, reports keep the spelling ──────────────

def test_policy_runs_on_the_canonical_id():
    for spelling in ("ev_to_ebitda", "EV_TO_EBITDA", " ev_ebitda "):
        assert normalise(spelling) == "ev_ebitda"


def test_the_report_retains_the_source_spelling():
    f = audit_definition("Aliased Screen", ["piotroski", "ev_to_ebitda"])

    assert "piotroski_f_score" in f.direct, "policy on canonical identity"
    assert f.spellings["piotroski_f_score"] == "piotroski"
    assert "as piotroski" in f.render(), "reader can find the line to edit"


def test_a_canonical_spelling_is_not_annotated():
    f = audit_definition("Plain", ["piotroski_f_score"])
    assert not f.spellings
    assert "(as " not in f.render()


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
    print(f"\ngraph health: {graph_health()['factor_layer_loaded']=}")
    sys.exit(1 if failures else 0)
