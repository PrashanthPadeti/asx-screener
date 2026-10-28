"""The driver's pinned contract must agree with the one it would execute
=======================================================================
`p0a_canonical_run.verify_activation` compares the activated contract against
two hand-written constants, EXPECTED_MODEL and EXPECTED_GOVERNED, and refuses
to create a run when they disagree. That refusal is deliberate, and the
comment above the constants says why they are not derived:

    Stated here rather than derived from the constant it is checking, so a
    change to that constant fails this rather than silently redefining what
    "correct" means.

That reasoning is right and this file does not undo it. The pin stays
hand-written, and bumping LATEST_MODEL_VERSION still requires a human to go
there and confirm the new contract by editing two lines.

What this changes is WHEN the disagreement is discovered. Without it the only
thing that notices is a canonical run in production: v11.2.63 shipped through
a green full-suite gate, deployed cleanly, passed twelve smoke checks, and
then refused to publish -- because nothing between the commit and the
publication attempt ever compared the two values.

A failing test is not a silent redefinition. It cannot update the pin; it can
only report that the pin and the model disagree, and name both. The deliberate
act is unchanged; the feedback arrives at the gate instead of at 20:26 on a
production console.

Two conventions this file had to learn the hard way
---------------------------------------------------
The first version imported pytest, used fixtures, and was reported
INCONCLUSIVE -- ModuleNotFoundError. The gate runs each suite as a standalone
script (`python tests/foo.py`), not under pytest, so conftest.py never
executes and its sys.path insert never happens. The path insert below is not
boilerplate; without it this file cannot import the thing it exists to check.

It would also have been inconclusive even with the imports fixed, because the
gate requires positive evidence of execution -- an "N/M passed" line from a
__main__ runner. A file that defines test functions and never calls them
exits 0 and claims nothing. The gate is explicit that exit 0 is absence of
failure, not evidence of execution.

The constants are read via the AST, not a regex: the re-pin comment in the
driver names "FACTOR_MODEL_V3" and "72" in prose immediately above the
constants, so a text matcher would read the explanation instead of the code.
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.metric_states import (                       # noqa: E402
    GOVERNED_METRICS, LATEST_MODEL_VERSION,
)

DRIVER = BACKEND / "scripts" / "p0a_canonical_run.py"
PINS = {"EXPECTED_MODEL", "EXPECTED_GOVERNED"}


def _module_constants(path: Path, names: set) -> dict:
    """Module-level literal assignments, read from the AST.

    Only top-level `NAME = <literal>` bindings count. An assignment nested in
    a function or guarded by a conditional is not the module constant
    `verify_activation` compares against, and treating it as one would let
    this pass against a value the driver never sees.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                found[target.id] = ast.literal_eval(node.value)
    return found


def _pinned() -> dict:
    found = _module_constants(DRIVER, PINS)
    missing = PINS - set(found)
    assert not missing, (
        f"{DRIVER.name} no longer defines {', '.join(sorted(missing))} at "
        f"module level. If the activation check was removed or renamed, this "
        f"suite is guarding nothing -- which is worse than its absence, "
        f"because it still passes.")
    return found


def test_the_pinned_model_is_the_model_the_driver_would_execute():
    """A canonical run publishes under LATEST_MODEL_VERSION. The pin must name
    it, or the driver refuses at publication time rather than here."""
    pinned = _pinned()
    assert pinned["EXPECTED_MODEL"] == LATEST_MODEL_VERSION, (
        f"the canonical driver is pinned to {pinned['EXPECTED_MODEL']} but "
        f"LATEST_MODEL_VERSION is {LATEST_MODEL_VERSION}. A canonical run "
        f"would refuse with PRECONDITION FAILED and create nothing. Confirm "
        f"the new contract deliberately by editing EXPECTED_MODEL and "
        f"EXPECTED_GOVERNED in scripts/p0a_canonical_run.py.")


def test_the_pinned_metric_count_is_that_models_governed_count():
    """A second, independent statement about the same contract: the version
    can match while the metric set under it has changed."""
    pinned = _pinned()
    actual = len(GOVERNED_METRICS[LATEST_MODEL_VERSION])
    assert pinned["EXPECTED_GOVERNED"] == actual, (
        f"the canonical driver expects {pinned['EXPECTED_GOVERNED']} governed "
        f"metrics but {LATEST_MODEL_VERSION} governs {actual}. Either a metric "
        f"was added to or removed from the model without the contract being "
        f"re-confirmed, or the pin is stale.")


def test_the_pin_names_a_model_that_exists():
    """A pin naming an unknown version cannot be satisfied by any run, and the
    failure would read as a contract mismatch rather than as a typo."""
    pinned = _pinned()
    assert pinned["EXPECTED_MODEL"] in GOVERNED_METRICS, (
        f"the canonical driver is pinned to {pinned['EXPECTED_MODEL']}, which "
        f"is not a key of GOVERNED_METRICS "
        f"({', '.join(sorted(GOVERNED_METRICS))}).")


def test_this_suite_can_actually_read_the_drivers_pin():
    """The AST reader is the whole mechanism, so prove it reads something.

    If the driver is refactored so the constants stop being module-level
    literals, `_pinned` raises and every assertion above fails loudly. This
    names that dependency directly rather than leaving it implicit, and it is
    the check that would catch the reader silently returning {}.
    """
    found = _module_constants(DRIVER, PINS)
    assert set(found) == PINS, (
        f"read {sorted(found)} from {DRIVER.name}, expected both of "
        f"{sorted(PINS)}")
    assert isinstance(found["EXPECTED_MODEL"], str)
    assert isinstance(found["EXPECTED_GOVERNED"], int)


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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
