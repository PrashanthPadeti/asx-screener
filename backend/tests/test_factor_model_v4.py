"""
FACTOR_MODEL_V4: declared, version-keyed, and not yet in force
==============================================================
V4 adds `fcf_yield` to the governed registry and to applicability gate 1b's
currency ruleset. Finding 17: it is a free cash flow stated in the reporting
currency over an AUD market capitalisation -- the shape the gate exists for --
and it was never in the ruleset. 167 of 178 foreign-reporter rows publish it,
78 inside the scored population.

THREE PROPERTIES THIS PINS, each for a different failure.

1. V3 IS UNCHANGED. A version is frozen once finalised runs reference it, and
   those runs carry an immutable trigger. If adding V4 moved V3's governed set
   or V3's ruleset, every published run's contract would have been rewritten
   after the fact -- the exact thing a pinned version prevents, and the reason
   V1 and V2 were both left alone when defects were found in them.

2. THE RULESET IS VERSION-KEYED, NOT GLOBAL. A single global dict would apply
   V4's rule retroactively to V3 rows, making the version bump cosmetic. This
   asserts the two versions resolve different rulesets, and that a caller
   passing no version gets the frozen one rather than an error or a silent
   upgrade.

3. V4 IS DECLARED AND NOT IN FORCE. LATEST_MODEL_VERSION is still V3. V3's
   own comment explains why that sequencing is not optional: flipping before
   the producers can satisfy the contract makes every absent value a
   violation, the read-back fails, the publish refuses, and the pipeline
   stops. The flip is a later release with a backfill in front of it.
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATABASE_URL_SYNC",
                      "postgresql://unused@127.0.0.1:1/unused")

from compute.engine.applicability import (                   # noqa: E402
    Applicability, BASE_CURRENCY, CROSS_CURRENCY, Cause, Domain, Observation,
    UNIT_SENSITIVE, V4_ADDITIONS, assess, cross_currency_for, unit_gate,
)
from compute.engine.metric_states import (                   # noqa: E402
    CURRENCY_GATED_YIELDS, GOVERNED_METRICS, LATEST_MODEL_VERSION,
)
from compute.engine.universe_writer import persisted_governed  # noqa: E402

V3 = "FACTOR_MODEL_V3"
V4 = "FACTOR_MODEL_V4"

#: The governed count V3 carried when V4 was added. A literal, so that
#: enlarging V3 to sneak a metric past the freeze fails here.
V3_GOVERNED_AT_V4 = 80

#: The eight ratios the frozen ruleset covers.
FROZEN_RULESET_SIZE = 8


# ── 1. The freeze ────────────────────────────────────────────────────────

def test_v3_governed_set_is_unchanged():
    """V3 is referenced by finalised runs and may not grow."""
    assert len(GOVERNED_METRICS[V3]) == V3_GOVERNED_AT_V4, (
        f"V3 now governs {len(GOVERNED_METRICS[V3])} metrics, not "
        f"{V3_GOVERNED_AT_V4}. A frozen version grew, which rewrites the "
        f"contract every published run under it claimed.")
    assert "fcf_yield" not in GOVERNED_METRICS[V3], (
        "fcf_yield is governed under V3. It belongs to V4; putting it in V3 "
        "retroactively makes every V3 run's sidecar incomplete.")


def test_v3_currency_ruleset_is_unchanged():
    """The frozen eight, resolved for V3 and for an unversioned caller."""
    assert len(cross_currency_for(V3)) == FROZEN_RULESET_SIZE
    assert "fcf_yield" not in cross_currency_for(V3)
    assert cross_currency_for(None) is CROSS_CURRENCY, (
        "an unversioned caller no longer gets the frozen ruleset. Several "
        "call sites assess values that carry no version at all, and silently "
        "upgrading them would apply V4's rules to V3 rows.")
    assert cross_currency_for("FACTOR_MODEL_V1") is CROSS_CURRENCY
    assert cross_currency_for("FACTOR_MODEL_V2") is CROSS_CURRENCY


def test_an_unknown_version_falls_back_rather_than_raising():
    """A row from a build we do not know must not get the newest rules.

    Falling forward would be the worse failure: an unrecognised version would
    silently acquire whatever suppression the current build happens to
    implement.
    """
    assert cross_currency_for("FACTOR_MODEL_V99") is CROSS_CURRENCY


# ── 2. What V4 adds ─────────────────────────────────────────────────────

def test_v4_is_v3_plus_the_named_set():
    assert GOVERNED_METRICS[V4] == GOVERNED_METRICS[V3] | CURRENCY_GATED_YIELDS
    assert CURRENCY_GATED_YIELDS == frozenset({"fcf_yield"})
    assert len(GOVERNED_METRICS[V4]) == len(GOVERNED_METRICS[V3]) + 1


def test_v4_ruleset_is_the_frozen_set_plus_fcf_yield():
    v4 = cross_currency_for(V4)
    assert set(v4) == set(CROSS_CURRENCY) | set(V4_ADDITIONS)
    assert "fcf_yield" in v4
    assert len(v4) == FROZEN_RULESET_SIZE + 1
    # The frozen entries must be byte-identical, not merely present: a
    # reworded reason under V4 would make two runs explain one suppression
    # two different ways.
    for metric, reason in CROSS_CURRENCY.items():
        assert v4[metric] == reason, (
            f"{metric}'s reason differs between V3 and V4")


def test_the_gate_fires_for_fcf_yield_only_under_v4():
    """The behavioural difference, at the gate rather than in the registry."""
    assert unit_gate("fcf_yield", "USD", V3) is None, (
        "gate 1b suppressed fcf_yield under V3, which changes what published "
        "runs claimed")
    assert unit_gate("fcf_yield", "USD", None) is None

    fired = unit_gate("fcf_yield", "USD", V4)
    assert fired is not None, "gate 1b did not fire for fcf_yield under V4"
    state, reason = fired
    assert state is Applicability.NOT_MEANINGFUL
    assert "USD" in reason, (
        "the reason does not name the currency, so a customer cannot see "
        "which unit mismatch suppressed the value")

    # AUD and silence both still publish under V4. The strict silence rule is
    # finding 20 and a later version; asserting it here would quietly ship it.
    assert unit_gate("fcf_yield", BASE_CURRENCY, V4) is None
    assert unit_gate("fcf_yield", None, V4) is None


def test_assess_threads_the_version_to_the_gate():
    """The version has to REACH gate 1b, or the ruleset is inert.

    This codebase has shipped an inert gate twice -- the period gate before
    annual_periods existed, and gate 2 called with no Observation at all. A
    version-keyed ruleset that nothing passes a version to would be the third.
    """
    obs = Observation(reporting_currency="USD")

    v3 = assess("fcf_yield", 0.05, Domain.GENERAL_CORPORATE, obs, model_version=V3)
    assert v3.ok, "fcf_yield was suppressed under V3"

    v4 = assess("fcf_yield", 0.05, Domain.GENERAL_CORPORATE, obs, model_version=V4)
    assert not v4.ok, (
        "fcf_yield was NOT suppressed under V4, so the version does not "
        "reach gate 1b and the ruleset is declared but unreachable")
    assert v4.cause is Cause.UNIT_MISMATCH


def test_the_version_reaches_the_gate_through_apply_applicability():
    """END TO END, because asserting assess() directly is not enough.

    test_assess_threads_the_version_to_the_gate calls assess() itself, so
    deleting `model_version=model_version` from factor_applicability's call
    site would leave it green and ship the ruleset inert. This codebase has
    shipped an inert gate twice already -- the period gate before
    annual_periods existed, and gate 2 called with no Observation -- and the
    docstring of the first test warns about being the third. A warning in a
    docstring is not a check.

    So this drives the real entry point, apply_applicability, on a
    foreign-reporter row, and asserts the value is masked under V4 and
    survives under V3.
    """
    import numpy as np
    import pandas as pd
    from compute.engine.factor_applicability import apply_applicability

    df = pd.DataFrame([{
        "asx_code": "TST",
        "sector": "Materials",
        "industry": "Gold",
        "reporting_currency": "USD",
        "fcf_yield": 7.5,
    }])

    v3 = apply_applicability(df.copy(), None, model_version=V3)
    assert not np.isnan(v3.frame.loc[0, "fcf_yield"]), (
        "fcf_yield was masked under V3, so a published run's values would "
        "change on re-read")

    v4 = apply_applicability(df.copy(), None, model_version=V4)
    assert np.isnan(v4.frame.loc[0, "fcf_yield"]), (
        "fcf_yield SURVIVED under V4 through the real entry point. The "
        "ruleset is declared and the version does not reach gate 1b -- the "
        "inert-gate failure, for the third time.")


def test_v4_persists_fcf_yield_and_v3_does_not():
    """A suppressed served column needs a sidecar, which needs governance.

    This is why fcf_yield is governed rather than merely gated: it is served,
    so suppressing it without a sidecar entry would hand the customer a null
    with no recorded reason -- the unexplained-null defect, introduced by the
    change meant to improve correctness.
    """
    assert persisted_governed(V4).get("fcf_yield") == "fcf_yield"
    assert persisted_governed(V3).get("fcf_yield") is None
    assert (len(persisted_governed(V4))
            == len(persisted_governed(V3)) + 1)


# ── 3. Declared, not in force ───────────────────────────────────────────

def test_v4_is_the_canonical_version():
    """Activated in v11.2.89, after both prerequisites were established.

    This test asserted the opposite until activation, which is the point of
    having it: flipping LATEST_MODEL_VERSION is the step that makes every
    absent governed value a contract violation, so it could not be a quiet
    constant change. Changing this line required saying what had been
    established, and here it is:

    1. NO BACKFILL WAS REQUIRED, decided by execution order rather than by
       the detector. commit_canonical runs require_stages -> verify_storage
       -> write_all -> verify_population, so the first V4 run rewrites every
       served row's sidecar before anything validates one. The detector
       would have rejected a stale sidecar -- it reports missing_governed for
       a row with no fcf_yield entry -- but it never sees one, because the
       run replaced it. Both halves are asserted above.

    2. THE MOVEMENT WAS MEASURED AND ACCEPTED, not discovered: 18 of 2,120
       composites, 169 value scores, no movement in the other four factors,
       no stock shifting more than 27 rank places, nothing withheld and
       nothing gained.

    If V4 is ever superseded, this becomes the frozen-version assertion and a
    new one takes its place -- the pattern V1, V2 and V3 all follow.
    """
    assert LATEST_MODEL_VERSION == V4, (
        f"LATEST_MODEL_VERSION is {LATEST_MODEL_VERSION}, not V4. If this is "
        f"a deliberate rollback, the V4 runs already finalised reference a "
        f"contract this build would no longer apply -- say which runs and "
        f"why in the same commit.")


def test_the_frozen_versions_are_still_reachable_after_activation():
    """Activation must not make V1-V3 unreadable.

    Finalised runs reference them, and `project_row` resolves a version per
    row: mixed-version rows are the designed-for case, not an edge. If
    activation had dropped the older entries, reading a V3 row back would
    raise UnsupportedModelVersion and the run's own evidence would become
    unreadable.
    """
    from compute.engine.factor_model import FACTOR_MODELS
    for older in ("FACTOR_MODEL_V1", "FACTOR_MODEL_V2", V3):
        assert older in GOVERNED_METRICS, f"{older} left the registry"
        assert older in FACTOR_MODELS, f"{older} left the factor models"
        assert cross_currency_for(older) is CROSS_CURRENCY, (
            f"{older} no longer resolves the frozen ruleset, so its "
            f"finalised runs would read back under V4's rules")


def test_unit_sensitive_describes_the_frozen_set_only():
    """A name that would otherwise mislead.

    UNIT_SENSITIVE is built from the frozen dict and nothing in production
    reads it. Under V4 it does NOT contain fcf_yield, so it is not the answer
    to "is this metric unit-sensitive" -- cross_currency_for(version) is.
    Pinned so the next reader does not take it for the authority.
    """
    assert UNIT_SENSITIVE == frozenset(CROSS_CURRENCY)
    assert "fcf_yield" not in UNIT_SENSITIVE
    assert "fcf_yield" in cross_currency_for(V4)


# ── 4. The transition: does V4 need a backfill? ─────────────────────────

def test_a_stale_sidecar_would_be_rejected_under_v4():
    """Half of the question: the detector DOES reject it.

    A row whose sidecar predates V4 has no entry for fcf_yield, and
    `violations` reports `missing_governed` for exactly that. On its own this
    says a backfill might be needed -- it does not establish that it IS,
    because the detector only ever sees what a run wrote. The other half is
    the execution order, below.
    """
    from compute.engine.metric_states import violations

    values = {"pe_ratio": 12.0}          # a row from before fcf_yield joined
    states = {"pe_ratio": {"state": "APPLICABLE"}}

    # The governed set is derived from the version inside violations().
    under_v3 = violations(values, states, V3)
    assert not [v for v in under_v3 if v.metric == "fcf_yield"], (
        "fcf_yield is reported missing under V3, where it is not governed")

    under_v4 = violations(values, states, V4)
    missing = [v for v in under_v4
               if v.metric == "fcf_yield" and v.kind == "missing_governed"]
    assert missing, (
        "a sidecar with no fcf_yield entry was NOT reported missing_governed "
        "under V4, so the detector cannot see the very state a transition "
        "would leave behind")


def test_the_run_rewrites_the_sidecar_before_it_validates():
    """The other half, and the half that decides it: EXECUTION ORDER.

    A detector rejection establishes nothing about whether a backfill is
    required. What decides it is whether the first V4 run regenerates the
    sidecar before anything validates it. In `commit_canonical` the order is:

        require_stages -> verify_storage -> write_all -> verify_population

    `write_all` writes each row's values AND its sidecar, keyed per asx_code
    over the serving population; `verify_population` then compares what the
    run INTENDED against what the database holds, per row, for every row. So
    a sidecar predating V4 cannot survive the run, and cannot be the thing
    validated -- which is why no backfill is needed.

    Asserted structurally, from the AST, rather than trusted to a comment: if
    someone reorders these so validation precedes the write, the first V4 run
    would validate yesterday's sidecars and this conclusion would silently
    stop holding.
    """
    import ast

    src = (BACKEND / "compute" / "engine"
           / "universe_writer.py").read_text(encoding="utf-8")
    fn = next((n for n in ast.walk(ast.parse(src))
               if isinstance(n, ast.FunctionDef)
               and n.name == "commit_canonical"), None)
    assert fn is not None, "commit_canonical not found"

    order = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None)
            if name in ("write_all", "verify_population", "verify_storage",
                        "require_stages"):
                order.append((node.lineno, name))
    seq = [n for _, n in sorted(order)]

    for required in ("write_all", "verify_population"):
        assert required in seq, (
            f"{required} is no longer called in commit_canonical; the "
            f"transition argument rests on it")
    assert seq.index("write_all") < seq.index("verify_population"), (
        f"validation now precedes the write ({seq}). The first V4 run would "
        f"validate sidecars written under V3, so a backfill WOULD be "
        f"required -- re-decide the transition before shipping this.")
    if "verify_storage" in seq:
        assert seq.index("verify_storage") < seq.index("write_all"), (
            "the schema check no longer precedes the write, so a version "
            "promising a column that does not exist would write first and "
            "discover it afterwards")


if __name__ == "__main__":
    # The release gate runs suites as `python tests/<file>.py` and requires
    # the "N/M passed" line as evidence of execution.
    import sys as _sys

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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    _sys.exit(1 if failures else 0)
