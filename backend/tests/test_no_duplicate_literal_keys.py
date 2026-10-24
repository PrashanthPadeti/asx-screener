#!/usr/bin/env python
"""
A repeated key in a dict literal silently discards the earlier value
===================================================================
Python keeps the last. No error, no warning, and the discarded definition
goes on sitting in the file looking authoritative.

Found 24 Oct 2026 by pointing ruff at a codebase whose CI had been failing
for days under 1,268 mostly-cosmetic findings. Seven real ones were in
there:

  app/api/v1/routes/screener.py   bb_pct, above_sma50, above_sma200,
                                  golden_cross, death_cross,
                                  cash_conversion_cycle
  app/core/query_parser.py        "profit growth"

and the definitions DIFFERED, so the discarded one was not a harmless
restatement:

  bb_pct               computed (price-bb_lower)/(bb_upper-bb_lower)*100
                       labelled "%"   -- discarded
                       raw column u.bb_pct, no unit       -- in force
  above_sma50          (u.price > u.sma_50 AND NOT NULL)  -- discarded
                       precomputed column u.above_sma50   -- in force
  cash_conversion_cycle  category "Financial Health"      -- discarded
                         category "Profitability"         -- in force
  "profit growth"      -> earnings_growth_1y (net)        -- discarded
                       -> pbt_growth_1y (pre-tax)         -- in force

The last one matters most: every natural-language query saying "profit
growth" has been answered with PRE-TAX profit growth, while a line in the
earnings section said it meant net. Nobody chose that; a dict did.

This guard is deliberately independent of ruff. The finding came from a
linter that is unpinned, unconfigured and had been red for days with the
signal buried, so the project cannot rely on it being run or being read.

Run:  python tests/test_no_duplicate_literal_keys.py
"""

import ast
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app").is_dir() else Path.cwd()

SEARCH_ROOTS = ("app", "compute", "scripts")


def _python_files():
    for root in SEARCH_ROOTS:
        base = BACKEND / root
        if base.is_dir():
            yield from base.rglob("*.py")


def _duplicate_keys(tree):
    """(lineno, key) for every repeated literal key in a dict literal.

    Only constant keys are considered: a computed key may legitimately
    repeat, and we cannot know its value without running the code.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen = {}
        for key in node.keys:
            if key is None or not isinstance(key, ast.Constant):
                continue                      # **spread, or computed
            if not isinstance(key.value, (str, int, float, bool)):
                continue
            marker = (type(key.value).__name__, key.value)
            if marker in seen:
                found.append((key.lineno, key.value, seen[marker]))
            else:
                seen[marker] = key.lineno
    return found


def test_no_dict_literal_repeats_a_key():
    offenders = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for lineno, key, first in _duplicate_keys(tree):
            offenders.append(
                f"{path.relative_to(BACKEND)}:{lineno} repeats key {key!r} "
                f"(first defined at line {first}) — the earlier definition "
                f"is silently discarded")
    assert not offenders, (
        "a dict literal repeats a key; Python keeps the LAST and the earlier "
        "definition is dead while still looking authoritative:\n  "
        + "\n  ".join(offenders))


def test_the_detector_catches_the_shape_it_exists_for():
    """Mutation control, on the two literals that were actually wrong."""
    src = '''
D = {
    "bb_pct": {"col": "computed", "unit": "%"},
    "rsi_21": {"col": "u.rsi_21"},
    "bb_pct": {"col": "u.bb_pct", "unit": ""},
}
'''
    dupes = _duplicate_keys(ast.parse(src))
    assert len(dupes) == 1, dupes
    assert dupes[0][1] == "bb_pct"


def test_the_detector_does_not_flag_distinct_keys():
    src = 'D = {"a": 1, "b": 2, "c": 3}\nE = {**D, "d": 4}\n'
    assert _duplicate_keys(ast.parse(src)) == []


def test_separate_dicts_may_reuse_a_key():
    """The same key in two different dicts is normal and must not flag."""
    src = 'A = {"x": 1}\nB = {"x": 2}\n'
    assert _duplicate_keys(ast.parse(src)) == []


def test_a_computed_key_is_not_assumed_to_repeat():
    """We cannot know a computed key's value without running the code, so
    it is left alone rather than guessed at."""
    src = 'D = {name: 1, name: 2}\n'
    assert _duplicate_keys(ast.parse(src)) == []


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                print(f"  FAIL  {name}\n        {exc}")
                failures.append(name)
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
