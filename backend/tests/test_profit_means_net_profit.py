#!/usr/bin/env python
"""
"profit growth" means net profit
================================
The phrase was declared twice in the synonym map -- once as
`earnings_growth_1y` in the earnings block, once as `pbt_growth_1y` in the
PBT block. A dict literal keeps the last, so the earnings mapping never
applied and every query saying "profit growth > 20" was answered with
PRE-TAX profit growth. Silently, for as long as both lines existed.

v11.2.33 removed the duplicate and kept pre-tax, so saved queries would not
move. v11.2.39 resolves it the other way, deliberately:

  - "profit" means net to an ASX investor
  - every sibling already meant net. "profit growth 1y" -> earnings_growth_1y
    and "profit growth 3y" -> earnings_growth_3y_cagr. The bare phrase was
    the odd one out in its own family.

Saved queries using "profit growth" now return NPAT growth. The numbers
differ. That is the point, and "pretax profit growth" is unchanged for
anyone who wanted the other thing.

"profit growth last year" was REMOVED rather than remapped. There is no
`earnings_growth_prev_y` in the universe, so it could only ever be answered
with pre-tax -- which is the defect being fixed, in a different phrase. It
now fails with a message naming the alternatives instead of quietly
answering a question the customer did not ask.

Run:  python tests/test_profit_means_net_profit.py
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PARSER = BACKEND / "app" / "core" / "query_parser.py"


def _synonyms() -> dict:
    """The phrase map, read from source by AST.

    Imported would need pydantic; parsed does not, and the map is a literal.
    """
    tree = ast.parse(PARSER.read_text(encoding="utf-8"))
    best = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        pairs = {k.value: v.value for k, v in zip(node.keys, node.values)
                 if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
                 and isinstance(k.value, str) and isinstance(v.value, str)}
        if "revenue growth" in pairs or "profit growth" in pairs:
            if len(pairs) > len(best):
                best = pairs
    return best


SYN = _synonyms()


def test_the_map_was_actually_read():
    assert len(SYN) > 100, (
        f"only {len(SYN)} synonyms extracted; the map has moved and every "
        f"assertion below would pass vacuously")


def test_profit_growth_means_net_profit():
    assert SYN.get("profit growth") == "earnings_growth_1y", (
        f"'profit growth' maps to {SYN.get('profit growth')!r}. It must mean "
        f"NET profit: that is what an ASX investor means by profit, and what "
        f"every sibling phrase already meant.")


def test_the_family_agrees_with_itself():
    """The inconsistency that made the original defect invisible.

    "profit growth 1y" and "profit growth 3y" meant earnings while the bare
    phrase meant pre-tax. Nobody notices one phrase disagreeing with its own
    family until the numbers are compared.
    """
    for phrase in ("profit growth", "profit growth 1y", "net profit growth",
                   "npat growth", "earnings growth"):
        target = SYN.get(phrase)
        assert target is not None, f"{phrase!r} is no longer mapped"
        assert target.startswith("earnings_growth"), (
            f"{phrase!r} maps to {target!r}; everything in this family must "
            f"mean net profit or the family disagrees with itself again")


def test_pre_tax_is_reachable_and_says_so():
    """Anyone who wanted the old behaviour must be able to ask for it, by a
    name that cannot be mistaken for the other thing."""
    for phrase in ("pretax profit growth", "pbt growth",
                   "profit before tax growth"):
        assert SYN.get(phrase) == "pbt_growth_1y", (
            f"{phrase!r} maps to {SYN.get(phrase)!r}; pre-tax growth must stay "
            f"reachable after the bare phrase changed meaning")


def test_no_phrase_quietly_means_pre_tax():
    """The property, over the whole map rather than the phrases I thought of.

    Any phrase answered with a pre-tax metric must SAY pre-tax -- "pretax",
    "pbt" or "before tax". One that does not is the original bug wearing
    different words.
    """
    offenders = [
        phrase for phrase, target in SYN.items()
        if target.startswith("pbt_")
        and not any(m in phrase for m in ("pretax", "pre-tax", "pbt",
                                          "before tax"))]
    assert offenders == [], (
        f"these phrases are answered with a PRE-TAX metric without saying so: "
        f"{offenders}. A customer typing one gets a different number than the "
        f"words promise, which is exactly the defect this release fixed.")


def test_the_ambiguous_last_year_phrase_is_gone():
    """It could only ever have been answered with pre-tax.

    There is no earnings_growth_prev_y, so remapping was impossible and
    keeping it meant keeping the defect. Failing with a message that names
    the alternatives beats answering the wrong question.
    """
    assert "profit growth last year" not in SYN, (
        "'profit growth last year' is mapped again. If an "
        "earnings_growth_prev_y now exists, point it there and update this "
        "test; if it does not, the phrase promises net and delivers pre-tax.")
    assert SYN.get("pretax profit growth last year") == "pbt_growth_prev_y"


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
