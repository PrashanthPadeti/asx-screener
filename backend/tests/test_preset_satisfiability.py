"""
An empty screen must say which kind of empty it is
==================================================
"Advanced Mining Value Screen — 0 stocks matched" was indistinguishable from
an honest empty result. It was not one: 44 ASX miners cleared every condition
except ``piotroski_f_score >= 6``, and that metric is computed for NONE of the
2,113 companies in the universe. Ten of thirty-one presets filtered on it or
on ``beta_1y``, equally empty. They had been returning nothing since they
shipped.

Nothing was broken below the API. Every company carried an explicit state --

    unavailable    / computation_unsupported   1463
    not_meaningful / domain                     650

-- with a human reason attached. The sidecar recorded it, the universe stored
it, the API returned it, and the page rendered a bare zero. The absence
survived four layers and died at the fifth, where the customer was.

What is tested where
--------------------
The interesting property -- "this preset can return a row" -- is about DATA,
and the full-suite gate runs against a clone with the schema and a seeded run
but no universe rows. Asserted there, every column reads as empty: the check
would either fail all 31 presets or be loosened until it passed on anything.
A guard whose population is absent reports on nothing while printing PASS.

So that half lives in scripts/assert_presets_satisfiable.py, which runs where
the data is. This file asserts what is genuinely static:

  * every preset names fields the registry knows
  * the response can carry an explanation at all
  * the route asks for one on the empty path, and ONLY on the empty path
  * the diagnosis looks at both halves -- governed metrics with a withholding
    state AND ungoverned columns that are simply empty

That last one matters: checking only the governed half leaves someone
filtering on beta_1y with exactly the bare zero this release removes.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_preset_satisfiability.py
"""

import ast
import sys
from pathlib import Path

BACKEND   = Path(__file__).resolve().parents[1]
ROUTE     = BACKEND / "app/api/v1/routes/screener.py"
DIAGNOSIS = BACKEND / "app/core/screen_diagnosis.py"
SCHEMA    = BACKEND / "app/schemas/screener.py"
SCRIPT    = BACKEND / "scripts/assert_presets_satisfiable.py"

sys.path.insert(0, str(BACKEND))


class Skipped(Exception):
    """Needs a runtime dependency this environment does not have."""


def _literal(name: str):
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


def _presets() -> list:
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.AsyncFunctionDef)
                and node.name == "get_screener_presets"):
            for ret in ast.walk(node):
                if isinstance(ret, ast.Return):
                    return ast.literal_eval(ret.value).get("presets", [])
    raise AssertionError("get_screener_presets no longer returns a literal")


# ── The presets themselves ───────────────────────────────────────────────────

def test_the_preset_catalogue_is_still_there():
    """Population control. Every assertion below is vacuous over zero
    presets, and 31 shipped when this was written."""
    presets = _presets()
    assert len(presets) >= 20, (
        f"only {len(presets)} presets found; the checks below would pass over "
        f"a catalogue they can no longer see")


def test_every_preset_filters_on_fields_the_registry_knows():
    """A field the registry does not know cannot be evaluated at all, which
    is the most complete form of unsatisfiable."""
    allowed = _literal("ALLOWED_FIELDS")
    offences = []
    for preset in _presets():
        for f in preset.get("filters", []):
            if f["field"] not in allowed:
                offences.append(f"{preset.get('id')}: filter {f['field']}")
        sort_by = preset.get("sort_by")
        if sort_by and sort_by not in allowed:
            offences.append(f"{preset.get('id')}: sort_by {sort_by}")
    assert not offences, (
        "presets reference fields ALLOWED_FIELDS does not define, so they "
        "can never return a row:\n  " + "\n  ".join(offences))


def test_the_satisfiability_check_exists_and_fails_loudly():
    """The data half of this property, and its exit contract.

    A checker that cannot run must not exit 0: that is indistinguishable from
    a clean result and is how a scoped verdict goes unnoticed.
    """
    assert SCRIPT.exists(), "scripts/assert_presets_satisfiable.py is gone"
    src = SCRIPT.read_text(encoding="utf-8")
    for sentinel in ("return 2", "cannot reach the database",
                     "no presets found", "universe is empty"):
        assert sentinel in src, (
            f"the checker has no distinct outcome for {sentinel!r}; a run "
            f"that could not judge anything would report success")


def test_the_checker_screens_the_same_population_as_the_product():
    """A verdict over a different population answers a different question."""
    route_pop  = _literal("DIAGNOSIS_POPULATION")
    script_src = SCRIPT.read_text(encoding="utf-8")
    assert route_pop in script_src, (
        f"the checker does not use the route's own population "
        f"({route_pop!r}); the two could disagree about which companies a "
        f"screen draws from")


# ── The response can carry an explanation ────────────────────────────────────

def _class_fields(path: Path, name: str) -> set:
    """Annotated attributes of a class, from the AST.

    Read structurally rather than by slicing the source after the class
    name: the first version of this test took a fixed character window and
    failed because the docstring explaining the defect was longer than the
    window. It was testing its own formatting.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next((n for n in ast.walk(tree)
                if isinstance(n, ast.ClassDef) and n.name == name), None)
    assert cls is not None, f"{name} is gone from {path.name}"
    return {n.target.id for n in cls.body
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}


def test_the_response_can_say_why_it_is_empty():
    assert "unevaluable_criteria" in _class_fields(SCHEMA, "ScreenerResponse"), (
        "ScreenerResponse has nowhere to put the reason a screen is empty, "
        "so the API can only ever return a bare zero")
    carried = _class_fields(SCHEMA, "UnevaluableCriterion")
    missing = {"field", "state", "cause", "reason", "affected", "universe"} - carried
    assert not missing, (
        f"UnevaluableCriterion carries no {sorted(missing)}; the sidecar "
        f"records it and the customer never sees it")


def test_the_route_diagnoses_only_the_empty_path():
    """Cost control, and the instrument rule.

    A diagnosis on every response would add two queries to every screen in
    the product to answer a question only an empty one is asking. An
    instrument must not consume the resources of the system it observes.
    """
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)
             and n.func.id == "diagnose_empty_screen"]
    assert calls, "the route never diagnoses an empty screen"

    guarded = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if "total" not in ast.dump(node.test):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == "diagnose_empty_screen"):
                guarded += 1
    assert guarded == len(calls), (
        f"{len(calls) - guarded} diagnosis call(s) run regardless of the "
        f"result count, adding queries to screens that matched rows")


def test_both_paths_that_return_a_screen_can_explain_themselves():
    """Filter Screen (where presets run) and Query Mode. Fixing one and
    leaving the other is how `piotroski_f_score >= 6` would still render a
    bare zero when typed by hand."""
    calls = ROUTE.read_text(encoding="utf-8").count("diagnose_empty_screen(")
    assert calls >= 2, (
        f"only {calls} response path(s) diagnose an empty screen; presets "
        f"and Query Mode both need it")


# ── The diagnosis covers both kinds of absence ───────────────────────────────

def test_the_diagnosis_covers_ungoverned_columns_too():
    """beta_1y has no sidecar entry -- it is simply NULL for everyone. A
    check that only consults metric_states would report nothing for it."""
    src = DIAGNOSIS.read_text(encoding="utf-8")
    assert "count(" in src, (
        "the diagnosis never counts non-null values, so a column that is "
        "empty without a withholding state is invisible to it")
    assert "metric_states" in src, (
        "the diagnosis never reads the sidecar, so a governed metric's "
        "recorded reason is never surfaced")


def test_the_diagnosis_reads_both_sides_of_a_comparison():
    """A field-to-field criterion (v11.2.67) names two fields, and the
    right-hand one can just as easily be the reason nothing matched.

    AST, not substring. The first version asserted `".fields()" in src` and
    passed a mutation that removed the call -- because the module's own
    docstring says "Reads Criterion.fields() rather than .field". The guard
    was reading its explanation instead of its code.
    """
    tree = ast.parse(DIAGNOSIS.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "fields"]
    assert calls, (
        "the diagnosis never calls .fields() on a criterion, so it reads "
        "only the left-hand field and the right-hand side of a comparison "
        "is never examined")


def test_the_diagnosis_is_bounded():
    """An instrument must not become a load source."""
    try:
        from app.core.screen_diagnosis import MAX_CRITERIA
    except ImportError as e:
        raise Skipped(f"screen_diagnosis' dependencies ({e.name})")
    assert 0 < MAX_CRITERIA <= 20, (
        f"MAX_CRITERIA={MAX_CRITERIA} does not bound the work a single "
        f"empty screen can cause")


def test_the_diagnosis_returns_nothing_when_there_is_nothing_to_say():
    """The other outcome. A diagnosis that always reports something trains
    the customer to ignore it, and an honest strict screen must stay
    distinguishable from a broken one."""
    src = DIAGNOSIS.read_text(encoding="utf-8")
    assert src.count("return None") >= 3, (
        "the diagnosis has no early exits; a screen that is simply strict "
        "would be annotated as though a criterion were broken")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures, skipped = [], []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Skipped as e:
            skipped.append(name)
            print(f"  SKIP  {name}  - needs {e}")
        except AssertionError as e:
            failures.append(name)
            print(f"  FAIL  {name}  - {e}")
        except Exception as e:                                 # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    passed = len(tests) - len(failures) - len(skipped)
    print(f"\n{passed}/{len(tests)} passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    sys.exit(1 if failures else 0)
