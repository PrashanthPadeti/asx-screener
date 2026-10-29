"""
A text column coerced to a number becomes a column of nothing
==============================================================
Run 7, 30 Sep 2026. Applicability gate 1b was written, tested, wired through
the loader, the migration, the universe build and the SELECT -- and published
BHP's P/E anyway, computed from USD earnings against an AUD price.

The frame did carry `reporting_currency`. Then composite_score ran every
selected column through `pd.to_numeric(..., errors="coerce")` except a
hard-coded three, so "USD" became NaN before the gate saw it. The gate
correctly reported APPLICABLE for a company whose currency it had been told
was missing.

    NM state count, run 3 -> run 7:  16,768 -> 16,765

Nothing in the run failed. Every stage proved set equality, the read-back
passed, 0 violations. A silent coercion two layers above the gate is not
visible to any of those.

The rule that prevents the next one: every field the applicability layer
reads as TEXT must be excluded from numeric coercion. Derived from the
Observation dataclass rather than listed by hand, so a future string field
cannot be added in one place and forgotten in the other.

It happened again anyway. Run 33, 29 Oct 2026
---------------------------------------------
v11.2.63 added `window_states` to the SELECT -- the sidecar carrying the
reason each price window is empty, which is the whole point of that release.
It is not a field of Observation, so the derivation above never covered it,
and the hand-written list was not updated. Every dict in the column became
NaN, and composite_score died reading one:

    AttributeError: 'float' object has no attribute 'get'

The crash was luck a second time. `window_assessment` guarded its payload
with `or {}`, and a NaN is truthy, so it reached .get() and raised. Had the
guard been written `if not payload` the run would have COMPLETED, publishing
every window as absent-for-no-recorded-reason -- the defect the sidecar was
built to remove, erased by the statement that reads it, with 0 persistence
violations and a passing read-back.

So the lesson is not "add window_states to the list". The list is the wrong
authority: it is maintained by hand, consulted at a point far from where
columns are chosen, and has now been wrong twice in the same shape. The
coercion asks the DATABASE what each column is, via the type codes on the
cursor that fetched it, and refuses the run when the declaration and the
result set disagree. The list remains as a declaration of intent, which is
checked -- declared and enforced, rather than declared and hoped for.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_non_numeric_columns.py
"""

import ast
import sys
from dataclasses import fields
from pathlib import Path
from typing import get_args, get_origin, Optional, Union

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.applicability import Observation  # noqa: E402

SCORER = BACKEND / "compute/engine/composite_score.py"


class Skipped(Exception):
    """Needs a runtime dependency this environment does not have.

    Reported as SKIP rather than passed over: a test that quietly disappears
    where it cannot run is indistinguishable from one that ran and agreed.
    """


def _non_numeric() -> set[str]:
    """NON_NUMERIC as composite_score declares it.

    Read from the source rather than imported: the module needs psycopg2 to
    import, and this property does not need a database to be true.
    """
    tree = ast.parse(SCORER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "NON_NUMERIC" for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError("composite_score declares no NON_NUMERIC set")


def _text_observation_fields() -> set[str]:
    """Observation fields typed as text rather than as a quantity."""
    out = set()
    for f in fields(Observation):
        ann = f.type
        # Annotations may arrive as strings under `from __future__`.
        if isinstance(ann, str):
            if "str" in ann:
                out.add(f.name)
            continue
        args = get_args(ann) if get_origin(ann) is Union else (ann,)
        if str in args:
            out.add(f.name)
    return out


def test_every_text_observation_field_is_excluded_from_coercion():
    """The general rule, derived rather than listed.

    A new string field on Observation that nobody excludes here arrives at the
    gate as NaN, and the gate reports applicable for a company it was never
    told about.
    """
    missing = _text_observation_fields() - _non_numeric()
    assert not missing, (
        f"these Observation fields are read as text but would be coerced to "
        f"NaN before the gate sees them: {sorted(missing)}")


def test_the_currency_specifically():
    """The instance that actually shipped."""
    assert "reporting_currency" in _non_numeric()


def test_the_exclusion_is_not_empty_and_keeps_the_originals():
    """The mutation control. An empty NON_NUMERIC would satisfy the derived
    rule vacuously if Observation ever had no text fields, and dropping
    asx_code would break the frame's identity column."""
    declared = _non_numeric()
    assert {"asx_code", "sector", "industry"} <= declared


def test_coercion_really_does_destroy_a_currency():
    """Proof that the guard is load-bearing rather than decorative.

    Without this, the tests above assert a rule whose consequence nobody has
    checked -- and the whole reason this file exists is that the consequence
    was invisible.
    """
    try:
        import pandas as pd
    except ImportError:
        raise Skipped("pandas — run this on the server, where scoring runs")
    assert pd.isna(pd.to_numeric(pd.Series(["USD"]), errors="coerce")[0])


def test_the_scorer_uses_the_declared_set_rather_than_a_literal():
    """A second hard-coded tuple inside the function would pass every test
    above while the frame kept being coerced by the old list."""
    src = SCORER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and any("numeric_cols" in ast.dump(c) for c in ast.walk(n)))
    assigns = [n for n in ast.walk(fn)
               if isinstance(n, ast.Assign)
               and any(getattr(t, "id", "") == "numeric_cols" for t in n.targets)]
    assert assigns, "numeric_cols is no longer assigned where expected"
    assert all("NON_NUMERIC" in ast.dump(a) for a in assigns), (
        "numeric_cols must filter on the declared NON_NUMERIC set")


def test_the_sidecar_specifically():
    """The second instance that shipped."""
    assert "window_states" in _non_numeric(), (
        "window_states is selected by the canonical writer and holds jsonb. "
        "Coerced, it becomes a column of NaN and every price window is "
        "published with no recorded reason.")


def test_coercion_is_decided_by_the_result_set_not_only_by_the_list():
    """The structural half: the list must have stopped being the authority.

    Both defects in this file's history were a column missing from a
    hand-written set. A test that only checks membership of that set is a
    test of the same mechanism that failed, so this checks that the mechanism
    changed: the column selection must consult the types the cursor reported.
    """
    src = SCORER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and any("numeric_cols" in ast.dump(c) for c in ast.walk(n)))
    assigns = [n for n in ast.walk(fn)
               if isinstance(n, ast.Assign)
               and any(getattr(t, "id", "") == "numeric_cols" for t in n.targets)]
    assert assigns, "numeric_cols is no longer assigned where expected"
    for node in assigns:
        dumped = ast.dump(node)
        assert "_is_numeric_type" in dumped, (
            "numeric_cols is selected without asking what the database "
            "returned. A column added to the SELECT and forgotten in "
            "NON_NUMERIC becomes a column of NaN again.")
    # And the types must come from the cursor that fetched the rows.
    assert any(isinstance(n, ast.Assign)
               and any(getattr(t, "id", "") == "result_types" for t in n.targets)
               and "description" in ast.dump(n)
               for n in ast.walk(fn)), (
        "result_types must be read from cur.description, not assembled from "
        "a second hand-written list.")


def test_a_disagreement_between_declaration_and_result_set_refuses():
    """Declared and enforced: the run must stop, not pick one quietly."""
    fn_src = SCORER.read_text(encoding="utf-8")
    assert "undeclared" in fn_src and "WriteRefused" in fn_src, (
        "no refusal path for a selected column that is non-numeric in the "
        "database and undeclared here")


def test_the_type_classifier_answers_correctly():
    """The classifier is the new authority, so exercise both verdicts.

    Checked against the PostgreSQL catalog's own type codes. If these ever
    disagree with the server, every column is misclassified at once.
    """
    try:
        from compute.engine.composite_score import _is_numeric_type
    except ImportError as e:
        raise Skipped(f"composite_score's dependencies ({e.name})")
    # smallint, bigint, integer, real, double precision, numeric, boolean
    for oid in (21, 20, 23, 700, 701, 1700, 16):
        assert _is_numeric_type(oid), f"type {oid} survives coercion intact"
    # text, varchar, jsonb, json, date, timestamptz, text[]
    for oid in (25, 1043, 3802, 114, 1082, 1184, 1009):
        assert not _is_numeric_type(oid), f"type {oid} must not be coerced"
    assert not _is_numeric_type(None)


def test_the_classifier_admits_booleans_for_the_stated_reason():
    """Boolean is admitted on a claim about pandas, so check the claim.

    The dry-run of v11.2.66 refused four boolean columns -- is_reit,
    is_miner and the two margin-expansion flags -- which the scorer has
    always coerced. Admitting them is only correct if coercion really is
    lossless for them; if that ever stops being true, four flags silently
    become NaN and this test is what says so.
    """
    try:
        import pandas as pd
    except ImportError:
        raise Skipped("pandas — run this on the server, where scoring runs")
    out = pd.to_numeric(pd.Series([True, False, None], dtype=object),
                        errors="coerce")
    assert out[0] == 1 and out[1] == 0 and pd.isna(out[2]), (
        f"boolean coercion is no longer lossless: {list(out)}. Remove 16 "
        f"from NUMERIC_TYPE_CODES and declare the boolean columns instead.")
    # And the types the classifier rejects really are destroyed.
    for val in ("USD", {"return_1y": {"state": "x"}}, pd.Timestamp("2026-10-29")):
        assert pd.isna(pd.to_numeric(pd.Series([val], dtype=object),
                                     errors="coerce")[0])


def test_a_mangled_sidecar_stops_the_run_rather_than_emptying_it():
    """window_assessment must not read a destroyed payload as 'no entry'.

    This is the half that turns the next occurrence from a silent wrong
    answer into a stopped run. `or {}` passed a NaN straight through because
    NaN is truthy; the fix must reject any payload that is neither a mapping
    nor SQL NULL.
    """
    try:
        from compute.engine.window_states import window_assessment
    except ImportError as e:
        raise Skipped(f"window_states' dependencies ({e.name})")
    try:
        window_assessment("return_1y", 1.0, float("nan"))
    except TypeError:
        pass
    else:
        raise AssertionError(
            "a NaN sidecar was accepted. Every window would be published "
            "with no recorded reason, and the run would report success.")
    # SQL NULL is the one absence that is legitimate.
    assert window_assessment("return_1y", 0.5, None).value == 0.5


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
        except Exception as e:                                     # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    passed = len(tests) - len(failures) - len(skipped)
    print(f"\n{passed}/{len(tests)} passed"
          + (f", {len(skipped)} skipped" if skipped else ""))
    sys.exit(1 if failures else 0)
