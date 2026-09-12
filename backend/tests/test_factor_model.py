"""
A declared model, and the difference between dropping and not declaring
======================================================================
The defect these tests exist for: compute_factor_score averaged constituent
ranks with ``skipna=True``, so a constituent that was NaN for any reason left
the average and the survivors absorbed its weight. A bank's quality_score was
therefore a five-signal blend wearing a six-signal name, and nothing in the
payload said so.

Two situations produced that NaN and they are not the same fact:

    NOT_MEANINGFUL   the signal does not apply to this company. Reweighting
                     may be right, but only as a declared policy whose
                     effective weights are visible.

    UNAVAILABLE      the signal applies and is missing. Reweighting publishes
                     a different model under the same name.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_factor_model.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.applicability import (  # noqa: E402
    Applicability,
    Assessment,
    Cause,
    Domain,
)
from compute.engine.factor_model import (  # noqa: E402
    FACTOR_MODELS,
    Constituent,
    FactorSpec,
    effective_weights,
    model_for,
)

V1 = "FACTOR_MODEL_V1"
V2 = "FACTOR_MODEL_V2"


def ok(metric: str, value: float = 1.0) -> Assessment:
    return Assessment(metric, Applicability.APPLICABLE, value, "",
                      Domain.GENERAL_CORPORATE)


def not_meaningful(metric: str) -> Assessment:
    return Assessment(metric, Applicability.NOT_MEANINGFUL, None,
                      "out of domain", Domain.BANK, cause=Cause.DOMAIN)


def unavailable(metric: str, cause: Cause = Cause.SOURCE_MISSING) -> Assessment:
    return Assessment(metric, Applicability.UNAVAILABLE, None, "no value",
                      Domain.GENERAL_CORPORATE, cause=cause)


def quality(version: str = V2) -> FactorSpec:
    return model_for(version)["quality"]


def all_applicable(spec: FactorSpec) -> dict:
    return {c.metric: ok(c.metric) for c in spec.constituents}


# ── The declared model is the model ──────────────────────────────────────────

def test_v2_quality_declares_five_constituents_without_piotroski():
    """Removing a constituent changes the declared model. It is not
    simulated by feeding the old model a NaN — which is what the previous
    implementation did, and why a bank's six-signal score was really five."""
    metrics = {c.metric for c in quality(V2).constituents}

    assert metrics == {"roe", "roce", "altman_z_score",
                       "debt_to_equity", "net_margin"}
    assert "piotroski_f_score" not in metrics
    assert "piotroski_f_score" in {c.metric for c in quality(V1).constituents}, \
        "V1 must keep its claim on record rather than being edited to match"


def test_piotroski_has_no_weight_because_it_is_not_declared():
    """Not because its value is missing. Under V2 the metric is simply not
    part of quality, so supplying an assessment for it changes nothing."""
    spec = quality(V2)
    assessments = all_applicable(spec)
    assessments["piotroski_f_score"] = ok("piotroski_f_score", 7.0)

    eff = effective_weights(spec, assessments)

    assert eff.usable
    assert "piotroski_f_score" not in eff.weights
    assert not eff.reweighted, "an undeclared metric is not a dropped one"


def test_declared_weights_must_sum_to_one():
    try:
        FactorSpec("bad", (Constituent("a", 0.5, 1), Constituent("b", 0.2, 1)))
    except ValueError as exc:
        assert "sum to" in str(exc)
    else:
        raise AssertionError("a model with no defined scale must not exist")


def test_an_unknown_model_version_fails_closed():
    try:
        model_for("FACTOR_MODEL_V99")
    except ValueError as exc:
        assert "unknown factor model version" in str(exc)
    else:
        raise AssertionError("scoring under semantics nobody asked for is the "
                             "failure versioning exists to prevent")


# ── An unavailable constituent cannot silently alter weights ─────────────────

def test_an_unavailable_constituent_makes_the_factor_unavailable():
    """The signal applies to this company and we do not have it. Computing
    quality from the other four would publish a four-signal model under the
    five-signal name — the exact skipna=True behaviour this replaces."""
    spec = quality(V2)
    assessments = all_applicable(spec)
    assessments["roe"] = unavailable("roe")

    eff = effective_weights(spec, assessments)

    assert not eff.usable
    assert eff.state is Applicability.UNAVAILABLE
    assert eff.weights == {}, "no partial model is served"
    assert "roe" in eff.reason


def test_the_cause_of_unavailability_survives():
    """An operator needs to know whether waiting will help: a stale feed
    clears itself, an unsupported computation does not."""
    spec = quality(V2)
    assessments = all_applicable(spec)
    assessments["roce"] = unavailable("roce", Cause.SOURCE_UNHEALTHY)

    eff = effective_weights(spec, assessments)
    assert eff.cause is Cause.SOURCE_UNHEALTHY


def test_a_declared_constituent_never_assessed_fails_closed():
    """A wiring fault, not a company fault. Treating it as absent data would
    blame the company for a gap in our own pipeline."""
    spec = quality(V2)
    assessments = all_applicable(spec)
    del assessments["net_margin"]

    eff = effective_weights(spec, assessments)

    assert not eff.usable
    assert "never assessed" in eff.reason


# ── Domain reweighting is a policy, and it is visible ────────────────────────

def test_a_bank_reweights_explicitly_and_says_which_signals_ran():
    """The adversarial case. D/E and net margin are NOT_MEANINGFUL for a bank,
    so quality legitimately runs on the remaining three — but the drop is
    declared policy, the surviving weights are renormalised to one, and the
    dropped names are returned so a surface can show them."""
    spec = quality(V2)
    assessments = all_applicable(spec)
    assessments["debt_to_equity"] = not_meaningful("debt_to_equity")
    assessments["net_margin"] = not_meaningful("net_margin")

    eff = effective_weights(spec, assessments)

    assert eff.usable and eff.reweighted
    assert eff.dropped_for_domain == ("debt_to_equity", "net_margin")
    assert set(eff.weights) == {"roe", "roce", "altman_z_score"}
    assert abs(sum(eff.weights.values()) - 1.0) < 1e-9
    assert all(abs(w - 1 / 3) < 1e-9 for w in eff.weights.values())


def test_domain_and_unavailable_are_not_interchangeable():
    """The distinction the NaN destroyed. Same arity of loss, opposite
    outcomes: out of domain reweights, unavailable refuses."""
    spec = quality(V2)

    domain = all_applicable(spec)
    domain["debt_to_equity"] = not_meaningful("debt_to_equity")

    absent = all_applicable(spec)
    absent["debt_to_equity"] = unavailable("debt_to_equity")

    assert effective_weights(spec, domain).usable
    assert not effective_weights(spec, absent).usable


def test_a_model_that_refuses_to_reweight_says_so():
    spec = FactorSpec("strict", (Constituent("a", 0.5, 1),
                                 Constituent("b", 0.5, 1)),
                      domain_reweight=False)
    eff = effective_weights(spec, {"a": ok("a"), "b": not_meaningful("b")})

    assert eff.state is Applicability.NOT_MEANINGFUL
    assert "does not reweight" in eff.reason


def test_every_constituent_out_of_domain_is_no_score_not_a_low_one():
    spec = quality(V2)
    assessments = {c.metric: not_meaningful(c.metric)
                   for c in spec.constituents}

    eff = effective_weights(spec, assessments)

    assert eff.state is Applicability.NOT_MEANINGFUL
    assert eff.weights == {}


# ── The models themselves are well formed ────────────────────────────────────

def test_every_declared_model_is_internally_consistent():
    """Constructing a FactorSpec validates its weights, so this proves every
    shipped model was built through that check rather than around it."""
    for version, model in FACTOR_MODELS.items():
        assert model, f"{version} declares no factors"
        for name, spec in model.items():
            assert spec.name == name
            assert abs(sum(c.weight for c in spec.constituents) - 1.0) < 1e-9
            assert all(c.direction in (+1, -1) for c in spec.constituents)


def test_every_declared_constituent_resolves_to_a_real_frame_column():
    """The guard that would have caught eps_cagr_3y.

    The model declares canonical identities, the frame carries storage
    spellings, and compute_factor bridges them with column_for(). A
    constituent whose column does not exist raises on every score for that
    factor — and the failure lands at compute time, on the server, not here.

    V1's signal table is the authority for what the engine actually ranked,
    read by AST so this stays runnable without psycopg2. V2 may only narrow
    it: a V2 constituent that V1 never ranked would be a new signal smuggled
    in under a version bump.
    """
    import ast

    source = (Path(__file__).resolve().parents[1]
              / "compute/engine/composite_score.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    table = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        and node.target.id == "FACTOR_SIGNALS")

    ranked_columns = {col for signals in table.values() for col, _ in signals}

    from compute.engine.universe_writer import column_for

    for version, model in FACTOR_MODELS.items():
        for name, spec in model.items():
            for c in spec.constituents:
                column = column_for(c.metric)
                assert column in ranked_columns, (
                    f"{version} {name}: {c.metric} -> {column}, which the "
                    f"engine has never ranked")


def test_v2_changes_exactly_two_factors_and_only_by_removal():
    """A version bump that quietly changed several models would make "what did
    V2 change" unanswerable from the code, so the difference is pinned.

    Quality drops piotroski_f_score, which cannot be computed faithfully from
    available data. Growth drops eps_growth_hoh, which is NULL for all 2,117
    active companies and has no producer — a specification naming something
    that does not exist. Both are removals; V2 introduces no new signal.
    """
    v1, v2 = model_for(V1), model_for(V2)

    assert set(v1) == set(v2), "V2 neither adds nor removes a factor"

    changes = {name: (
        {c.metric for c in v1[name].constituents}
        - {c.metric for c in v2[name].constituents})
        for name in v1
        if v1[name].constituents != v2[name].constituents}

    assert changes == {"quality": {"piotroski_f_score"},
                       "growth": {"eps_growth_hoh"}}, changes

    for name in v1:
        added = ({c.metric for c in v2[name].constituents}
                 - {c.metric for c in v1[name].constituents})
        assert not added, f"V2 {name} introduces {added} under a version bump"


# ── The minimum semantic coverage floor ──────────────────────────────────────
# Unlimited reweighting reproduces the defect it was meant to fix: a factor
# keeps its name after most of its declared dimensions have gone. 0.60 with
# five equal constituents means 3/5 scores and 2/5 does not.


def retained(spec, *not_meaningful):
    assessments = all_applicable(spec)
    for metric in not_meaningful:
        assessments[metric] = not_meaningful_assessment(metric)
    return effective_weights(spec, assessments)


def not_meaningful_assessment(metric):
    return Assessment(metric, Applicability.NOT_MEANINGFUL, None,
                      "out of domain", Domain.BANK, cause=Cause.DOMAIN)


def test_a_bank_gets_no_v2_quality_score():
    """The consequence, recorded rather than discovered.

    debt_to_equity, net_margin and altman_z_score are all structurally NM for
    a bank, leaving {roe, roce} — 40% of declared weight. V2's Quality is a
    general-corporate methodology and a bank is outside its reach.

    NOT_MEANINGFUL, not UNAVAILABLE: the bank's ROE and ROCE may be perfectly
    healthy. Nothing is missing. The model simply has too few applicable
    dimensions left to be itself.
    """
    eff = retained(quality(V2), "debt_to_equity", "net_margin",
                   "altman_z_score")

    assert not eff.usable
    assert eff.state is Applicability.NOT_MEANINGFUL
    assert eff.cause is Cause.DOMAIN
    assert eff.weights == {}
    assert "insufficient applicable factor weight" in eff.reason
    assert "0.40" in eff.reason and "0.60" in eff.reason


def test_an_explorer_gets_no_v2_value_score():
    """429 companies on production, almost all pre-revenue explorers, scored
    Value on {fcf_yield, price_to_book} after legitimately losing revenue,
    earnings and EBITDA. That pair may describe an explorer; it is not the
    five-signal Value model, and a future explorer Value methodology should be
    designed rather than arrived at by attrition."""
    eff = retained(model_for(V2)["value"], "pe_ratio", "price_to_sales",
                   "ev_ebitda")

    assert eff.state is Applicability.NOT_MEANINGFUL
    assert eff.weights == {}


def test_three_of_five_scores_with_explicit_thirds():
    eff = retained(quality(V2), "debt_to_equity", "net_margin")

    assert eff.usable and eff.reweighted
    assert set(eff.weights) == {"roe", "roce", "altman_z_score"}
    assert all(abs(w - 1 / 3) < 1e-9 for w in eff.weights.values())


def test_four_of_five_scores_with_explicit_quarters():
    eff = retained(quality(V2), "debt_to_equity")

    assert eff.usable
    assert all(abs(w - 0.25) < 1e-9 for w in eff.weights.values())


def test_the_floor_does_not_apply_to_an_unavailable_constituent():
    """Ordering matters. Four applicable constituents retain 80%, comfortably
    above the floor — but one UNAVAILABLE refuses regardless, because missing
    evidence and narrowed applicability are not interchangeable however much
    weight survives."""
    spec = quality(V2)
    assessments = all_applicable(spec)
    assessments["roe"] = unavailable("roe")

    eff = effective_weights(spec, assessments)
    assert eff.state is Applicability.UNAVAILABLE
    assert eff.cause is Cause.SOURCE_MISSING


def test_the_floor_is_declared_per_spec_and_validated():
    assert model_for(V2)["quality"].min_effective_weight_fraction == 0.60
    try:
        FactorSpec("bad", (Constituent("a", 1.0, 1),),
                   min_effective_weight_fraction=0.0)
    except ValueError as exc:
        assert "min_effective_weight_fraction" in str(exc)
    else:
        raise AssertionError("a floor of zero permits any residue")


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
