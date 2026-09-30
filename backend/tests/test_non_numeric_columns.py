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
