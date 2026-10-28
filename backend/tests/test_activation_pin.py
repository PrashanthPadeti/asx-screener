"""The driver's pinned contract must agree with the one it would execute
=======================================================================
`p0a_canonical_run.verify_activation` compares the activated contract against
two hand-written constants, EXPECTED_MODEL and EXPECTED_GOVERNED, and refuses
to create a run when they disagree. That refusal is deliberate, and the
comment above the constants says why they are not derived:

    Stated here rather than derived from the constant it is checking, so a
    change to that constant fails this rather than silently redefining what
    "correct" means.

That reasoning is right and this test does not undo it. The pin stays
hand-written, and bumping LATEST_MODEL_VERSION still requires a human to come
here and confirm the new contract by editing two lines.

What this test changes is WHEN the disagreement is discovered. Without it the
only thing that notices is a canonical run in production: v11.2.63 shipped
through a green full-suite gate, deployed cleanly, passed its smoke tests, and
then refused to publish -- because nothing between the commit and the
publication attempt ever compared the two values. The release was correct and
the operator still lost a cycle to a two-line edit that could have been named
at gate time.

A failing test is not a silent redefinition. It cannot update the pin; it can
only report that the pin and the model disagree and name both values. The
deliberate act is unchanged, the feedback arrives earlier.

Read structurally, via the AST, rather than by importing the module: the
driver imports psycopg2 and the compute engine at module scope, and a test
that asserts a property of the SOURCE should not depend on that source's
runtime being installable. Textual matching is not used either -- a regex over
the file would match the constants where they appear in the docstring above
them, which is exactly the prose-read-as-code mistake this project keeps
finding.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from compute.engine.metric_states import GOVERNED_METRICS, LATEST_MODEL_VERSION

DRIVER = Path(__file__).resolve().parents[1] / "scripts" / "p0a_canonical_run.py"


def _module_constants(path: Path, names: set[str]) -> dict:
    """Module-level literal assignments, read from the AST.

    Only top-level `NAME = <literal>` bindings count. An assignment nested in a
    function or guarded by a conditional is not the module constant the driver
    compares against, and treating it as one would make this test pass against
    a value `verify_activation` never sees.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pytest.fail(
                        f"{target.id} in {path.name} is not a literal, so this "
                        f"test cannot read it without executing the module. "
                        f"Keep the pin a plain literal.")
    return found


@pytest.fixture(scope="module")
def pinned() -> dict:
    found = _module_constants(DRIVER, {"EXPECTED_MODEL", "EXPECTED_GOVERNED"})
    missing = {"EXPECTED_MODEL", "EXPECTED_GOVERNED"} - set(found)
    if missing:
        pytest.fail(
            f"{DRIVER.name} no longer defines {', '.join(sorted(missing))} at "
            f"module level. If the activation check was removed or renamed, "
            f"this test is now guarding nothing -- which is worse than its "
            f"absence, because it still passes.")
    return found


def test_the_pinned_model_is_the_model_the_driver_would_execute(pinned):
    """A canonical run publishes under LATEST_MODEL_VERSION. The pin must name
    it, or the driver refuses at publication time rather than here."""
    assert pinned["EXPECTED_MODEL"] == LATEST_MODEL_VERSION, (
        f"the canonical driver is pinned to {pinned['EXPECTED_MODEL']} but "
        f"LATEST_MODEL_VERSION is {LATEST_MODEL_VERSION}. A canonical run "
        f"would refuse with PRECONDITION FAILED and create nothing. Confirm "
        f"the new contract deliberately by editing EXPECTED_MODEL and "
        f"EXPECTED_GOVERNED in scripts/p0a_canonical_run.py.")


def test_the_pinned_metric_count_is_that_models_governed_count(pinned):
    """The count is a second, independent statement about the same contract:
    the version could match while the metric set under it has changed."""
    actual = len(GOVERNED_METRICS[LATEST_MODEL_VERSION])
    assert pinned["EXPECTED_GOVERNED"] == actual, (
        f"the canonical driver expects {pinned['EXPECTED_GOVERNED']} governed "
        f"metrics but {LATEST_MODEL_VERSION} governs {actual}. Either a metric "
        f"was added to or removed from the model without the contract being "
        f"re-confirmed, or the pin is stale.")


def test_the_pin_names_a_model_that_exists(pinned):
    """A pin naming an unknown version cannot be satisfied by any run, and the
    failure would read as a contract mismatch rather than as a typo."""
    assert pinned["EXPECTED_MODEL"] in GOVERNED_METRICS, (
        f"the canonical driver is pinned to {pinned['EXPECTED_MODEL']}, which "
        f"is not a key of GOVERNED_METRICS "
        f"({', '.join(sorted(GOVERNED_METRICS))}).")
