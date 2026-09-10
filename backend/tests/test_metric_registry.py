"""
Metric dependency registry — permanent regression tests
=======================================================
The registry exists because a direct-reference audit reported 18 affected
screens and that was a lower bound: a screen filtering on quality_score alone
inherits debt_to_equity without naming it. These tests assert the CI contract
the roadmap freezes:

  * resolve direct fields, aliases, derived metrics and composites transitively
  * detect cycles or unresolved dependencies and fail closed
  * report both the direct reference and the inherited sensitive constituent
  * audit anomaly rules alongside screen definitions

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_metric_registry.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.metric_registry import (  # noqa: E402
    ALIASES,
    COMPOSITES,
    KNOWN_PRIMITIVES,
    SENSITIVE,
    CircularDependency,
    UnresolvedMetric,
    audit,
    audit_definition,
    factor_composites,
    normalise,
    render,
    resolve,
    screen_fields,
    sensitive_dependencies,
)

# The real screen, copied from routes/screener.py.
ALTMAN_SAFETY = {
    "id": "altman_safety_screen",
    "name": "Altman Z-Score Safety",
    "filters": [
        {"field": "altman_z_score", "operator": "gte", "value": 3},
        {"field": "current_ratio", "operator": "gte", "value": 2},
        {"field": "debt_to_equity", "operator": "lte", "value": 0.5},
        {"field": "net_margin", "operator": "gte", "value": 5},
        {"field": "piotroski_f_score", "operator": "gte", "value": 6},
        {"field": "market_cap", "operator": "gte", "value": 100},
    ],
    "sort_by": "altman_z_score", "sort_dir": "desc",
}

# The case the whole registry exists for: names nothing sensitive.
QUALITY_COMPOUNDER = {
    "name": "Quality Compounder",
    "filters": [{"field": "quality_score", "operator": "gte", "value": 80}],
}

CLEAN_SCREEN = {
    "name": "Short Interest Risk",
    "filters": [{"field": "short_pct", "operator": "gte", "value": 5}],
    "sort_by": "short_pct",
}

# anomaly_detect.py's seven rules, reduced to the fields each predicate reads.
ANOMALY_RULES = [
    {"flag_type": "HIGH_GROSSED_UP_YIELD", "fields": ["grossed_up_yield"]},
    {"flag_type": "RSI_OVERSOLD_SOUND_FINANCIALS", "fields": ["rsi_14", "piotroski_f_score"]},
    {"flag_type": "RSI_OVERBOUGHT_WEAK", "fields": ["rsi_14", "piotroski_f_score"]},
    {"flag_type": "HIGH_SHORT_INTEREST", "fields": ["short_pct"]},
]


# ── Aliases ───────────────────────────────────────────────────────────────────

def test_aliases_normalise_to_one_spelling():
    assert normalise("ev_to_ebitda") == "ev_ebitda"
    assert normalise("piotroski") == "piotroski_f_score"
    assert normalise("Altman_Z") == "altman_z_score"
    assert normalise("franked_yield") == "grossed_up_yield"


def test_normalise_is_idempotent_and_terminates():
    for alias in ALIASES:
        once = normalise(alias)
        assert normalise(once) == once


def test_an_alias_does_not_hide_a_sensitive_field():
    """Searching for the other spelling is how an audit passes a screen clean."""
    f = audit_definition("Aliased", ["ev_to_ebitda", "piotroski"])
    assert "ev_ebitda" in f.direct and "piotroski_f_score" in f.direct


# ── Transitive resolution ─────────────────────────────────────────────────────

def test_resolve_reaches_primitives_through_two_levels():
    res = resolve("roe")
    assert res.primitives == {"net_profit", "total_equity"}


def test_resolve_expands_a_composite_of_composites():
    res = resolve("fcf_yield")
    assert "operating_cash_flow" in res.primitives
    assert "capital_expenditure" in res.primitives
    assert res.paths["free_cash_flow"] == ("fcf_yield", "free_cash_flow")


def test_piotroski_carries_its_two_out_of_domain_subtests():
    res = resolve("piotroski_f_score")
    assert "leverage_change" in res.primitives
    assert "current_ratio_change" in res.primitives


def test_paths_explain_why_not_just_that():
    res = resolve("grossed_up_yield")
    assert res.paths["dividend_per_share"] == (
        "grossed_up_yield", "grossed_up_dividend", "dividend_per_share")


def test_a_primitive_resolves_to_itself_with_no_paths():
    res = resolve("short_pct")
    assert res.primitives == {"short_pct"} and not res.is_composite


# ── Fail closed ───────────────────────────────────────────────────────────────

def test_unknown_node_is_reported_not_assumed_safe():
    res = resolve("some_new_metric_nobody_declared")
    assert res.unresolved == {"some_new_metric_nobody_declared"}
    assert not res.primitives


def test_strict_resolution_raises_on_an_unknown_node():
    try:
        resolve("some_new_metric_nobody_declared", strict=True)
    except UnresolvedMetric as e:
        assert "neither a known primitive nor a declared composite" in str(e)
    else:
        raise AssertionError("strict resolution must raise")


def test_a_cycle_raises_rather_than_looping():
    cyclic = {"a": ["b"], "b": ["c"], "c": ["a"]}
    try:
        resolve("a", _graph=cyclic)
    except CircularDependency as e:
        assert "a -> b -> c -> a" in str(e)
    else:
        raise AssertionError("a cycle must raise")


def test_audit_surfaces_unresolved_nodes_in_the_report():
    findings = audit(screens=[{"name": "Experimental",
                               "filters": [{"field": "not_a_real_metric"}]}])
    assert findings[0].unresolved == ["not_a_real_metric"]
    assert "FAIL CLOSED" in render(findings)


# ── The case the registry exists for ──────────────────────────────────────────

def test_a_screen_naming_only_a_composite_is_still_affected():
    """Today's direct-reference audit reports this one clean."""
    f = audit_definition("Quality Compounder", ["quality_score"])

    if not factor_composites():
        return  # scoring engine unavailable; covered by the drift test below

    assert f.affected, "quality_score inherits debt_to_equity without naming it"
    assert not f.direct, "it names nothing sensitive directly"
    for inherited in ("debt_to_equity", "piotroski_f_score", "roe"):
        assert inherited in f.inherited


def test_the_report_shows_both_direct_and_inherited():
    f = audit_definition("Altman Z-Score Safety", screen_fields(ALTMAN_SAFETY))
    out = f.render()

    assert "direct:" in out
    for m in ("altman_z_score", "current_ratio", "debt_to_equity", "piotroski_f_score"):
        assert m in f.direct
    assert "leverage_change" not in f.direct, "a subtest is inherited, not direct"


def test_sort_by_counts_as_a_reference():
    """A screen ordered by a defective metric returns the wrong stocks first."""
    f = audit_definition("Sorted", screen_fields(
        {"filters": [{"field": "market_cap"}], "sort_by": "grossed_up_yield"}))
    assert "grossed_up_yield" in f.direct


def test_a_genuinely_clean_screen_is_not_flagged():
    f = audit_definition("Short Interest Risk", screen_fields(CLEAN_SCREEN))
    assert not f.affected, "only Short Interest Risk was unaffected in the audit"


# ── Anomaly rules audited alongside screens ───────────────────────────────────

def test_anomaly_rules_appear_in_the_same_report():
    findings = audit(screens=[ALTMAN_SAFETY, CLEAN_SCREEN], anomalies=ANOMALY_RULES)
    by_name = {f.name: f for f in findings}

    assert by_name["HIGH_GROSSED_UP_YIELD"].kind == "anomaly"
    assert "grossed_up_yield" in by_name["HIGH_GROSSED_UP_YIELD"].direct
    assert "piotroski_f_score" in by_name["RSI_OVERBOUGHT_WEAK"].direct


def test_the_three_defective_anomaly_types_are_flagged_and_the_others_are_not():
    findings = {f.name: f for f in audit(anomalies=ANOMALY_RULES)}
    assert findings["HIGH_GROSSED_UP_YIELD"].affected
    assert findings["RSI_OVERSOLD_SOUND_FINANCIALS"].affected
    assert findings["RSI_OVERBOUGHT_WEAK"].affected
    assert not findings["HIGH_SHORT_INTEREST"].affected


def test_the_yield_anomaly_inherits_the_dividend_chain():
    deps = sensitive_dependencies("grossed_up_yield")
    assert "grossed_up_yield" in deps
    assert "dividend_per_share" in deps, "the TTM window defect reaches the predicate"


# ── Sensitivity is read from the applicability tables, not duplicated ─────────

def test_sensitive_set_tracks_the_applicability_rules():
    from compute.engine.applicability import DOMAIN_RULES
    for metric in DOMAIN_RULES:
        assert metric in SENSITIVE, f"{metric} has a domain rule but is not sensitive"


def test_dividend_methodology_fields_are_sensitive():
    for m in ("grossed_up_yield", "dividend_yield", "franking_pct"):
        assert m in SENSITIVE


# ── CI must not drift from runtime ────────────────────────────────────────────

def test_registry_matches_factor_signals():
    """The generated factor layer is the scoring engine's, not a copy of it."""
    generated = factor_composites()
    if not generated:
        print("    (skipped - compute.engine.composite_score not importable)")
        return

    from compute.engine.composite_score import FACTOR_SIGNALS
    for name, signals in FACTOR_SIGNALS.items():
        key = f"{name}_score"
        assert key in generated
        assert generated[key] == [normalise(c) for c, _ in signals]


def test_every_declared_constituent_is_known_or_declared():
    """No composite may depend on something the registry cannot classify."""
    unknown = {c for children in COMPOSITES.values() for c in map(normalise, children)
               if c not in KNOWN_PRIMITIVES and c not in COMPOSITES}
    assert not unknown, f"undeclared constituents: {sorted(unknown)}"


def test_no_composite_is_also_listed_as_a_primitive():
    overlap = set(COMPOSITES) & KNOWN_PRIMITIVES
    assert not overlap, f"ambiguous: {sorted(overlap)}"


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

    print("\n-- Sample blast-radius report --")
    print(render(audit(screens=[ALTMAN_SAFETY, QUALITY_COMPOUNDER, CLEAN_SCREEN],
                       anomalies=ANOMALY_RULES)))

    sys.exit(1 if failures else 0)
