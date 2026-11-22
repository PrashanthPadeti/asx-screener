"""
Finding 24: a reusing run records the decision that authorised it
=================================================================
`DAILY_CANONICAL` reuses `yearly_compute`, so it writes no yearly stage --
and until v11.2.90 it wrote nothing about the reuse either. Run 61 is the
concrete case: DAILY_CANONICAL under FACTOR_MODEL_V4, 2,123 rows published,
inheriting yearly output, and nothing in `compute_run_stages` saying against
which fingerprint. The published surface could only be tied to its inputs
through the earlier FULL run it inherited from, and the comparison that
authorised the inheritance was unevidenced.

WHY IT WAS MISSING, WHICH IS NOT THE SAME AS AN OVERSIGHT

`open_plan` runs BEFORE `create_run`, deliberately: "a precondition failure
must leave no trace in the run table". So at the moment of the decision there
is no run id to attach it to. The decision has to be carried forward on
purpose. And it could not even be recorded as it stood, because
`ReuseDecision` compared two fingerprints and kept neither -- "unchanged" is
a verdict, and the value is the evidence.

THE ONE THING THAT WOULD BE DANGEROUS TO GET WRONG

The stage is named `yearly_reuse`, not `yearly_compute`.
`source_fingerprint.proven_by_latest_yearly` selects
`stage_name='yearly_compute' AND status='success'` to find the fingerprint
the NEXT reuse is checked against. Recording a reuse under that name would
make a run that computed nothing the authority for the next run's reuse --
and then a chain of daily runs could inherit from each other indefinitely
while the fundamentals moved underneath them. That is a worse defect than
the one being fixed, so it is asserted rather than left to a comment.
"""

import ast
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATABASE_URL_SYNC",
                      "postgresql://unused@127.0.0.1:1/unused")

from compute.engine.run_plans import (                        # noqa: E402
    DAILY_CANONICAL, FULL_FUNDAMENTALS_CANONICAL, ReuseDecision,
)
from compute.engine.run_stages import StageResult             # noqa: E402

DRIVER = BACKEND / "scripts" / "p0a_canonical_run.py"


def test_the_decision_carries_the_fingerprint_it_compared():
    """A verdict without the value is not evidence.

    `ReuseDecision` used to hold only permitted/reason/proven_by_run, so even
    in memory the comparison discarded both fingerprints it had just read.
    Nothing downstream could record what the decision was made on, which is
    why finding 24 could not be fixed by writing a row -- the row would have
    had nothing in it.
    """
    d = ReuseDecision(True, "unchanged", 60,
                      aggregate="c7ae712444f234ec", schema_version=2)
    assert d.aggregate == "c7ae712444f234ec"
    assert d.schema_version == 2
    text = " ".join(d.lines())
    assert "c7ae712444f234ec" in text, (
        "the human-readable lines do not name the fingerprint, so an "
        "operator reading the log still cannot tell which inputs were "
        "compared")


def test_a_permitted_reuse_reports_which_fingerprint_it_matched():
    """Asserted on the real function, with its database calls stubbed.

    Stubbing `source_fingerprint` rather than reaching for a database keeps
    this a statement about check_yearly_reuse's logic: given a proven
    fingerprint equal to the current one, the decision it returns must carry
    that value forward.
    """
    from compute.engine import run_plans
    from compute.engine import source_fingerprint as sfp

    class Fake:
        schema_version = 2
        aggregate = "deadbeefdeadbeef0000"

        def differences(self, other):
            return []

    real_proven, real_compute = sfp.proven_by_latest_yearly, sfp.compute
    try:
        sfp.proven_by_latest_yearly = lambda cur: (60, Fake())
        sfp.compute = lambda cur: Fake()
        d = run_plans.check_yearly_reuse(None)
    finally:
        sfp.proven_by_latest_yearly = real_proven
        sfp.compute = real_compute

    assert d.permitted is True
    assert d.proven_by_run == 60
    assert d.aggregate == "deadbeefdeadbeef0000", (
        "a permitted reuse did not carry the aggregate it matched, so the "
        "stage row would record a verdict with no evidence")
    assert d.schema_version == 2


def test_open_plan_returns_the_decision_only_when_something_is_reused():
    """The caller needs it, and needs to know when there is nothing to record.

    Asserted structurally, because `open_plan` reads a database. What matters
    is that the function's contract is a returned decision rather than a
    logged one -- a function that only logs cannot be recorded from.
    """
    src = (BACKEND / "compute" / "engine"
           / "run_plans.py").read_text(encoding="utf-8")
    fn = next((n for n in ast.walk(ast.parse(src))
               if isinstance(n, ast.FunctionDef) and n.name == "open_plan"),
              None)
    assert fn is not None, "open_plan not found"

    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert returns, "open_plan returns nothing, so the decision is unrecordable"
    returns_a_value = [r for r in returns
                       if r.value is not None
                       and not (isinstance(r.value, ast.Constant)
                                and r.value.value is None)]
    assert returns_a_value, (
        "open_plan has no return that yields a value -- the reuse decision "
        "still only reaches the log")

    assert "yearly_compute" in DAILY_CANONICAL.reuses, (
        "DAILY_CANONICAL no longer reuses yearly_compute, so this finding's "
        "population has changed and the test needs rewriting")
    assert not FULL_FUNDAMENTALS_CANONICAL.reuses, (
        "the FULL plan now reuses something; it is the plan that must compute "
        "everything for itself, and a reuse there would mean the fallback "
        "offered on a refusal no longer computes yearly output")


def test_the_driver_records_the_reuse_as_a_stage_after_the_run_exists():
    """Captured from open_plan, recorded after create_run, in that order.

    Recording before the run exists is impossible; re-deciding after it
    exists would record a different decision than the one that authorised the
    run. So the AST is checked for both the capture and the ordering.
    """
    src = DRIVER.read_text(encoding="utf-8")
    assert "reuse_decision = open_plan(" in src, (
        "the driver discards open_plan's return value, so the decision is "
        "logged and lost exactly as before")
    assert 'stage_name="yearly_reuse"' in src, (
        "no yearly_reuse stage is recorded")

    i_open = src.index("reuse_decision = open_plan(")
    i_create = src.index("run = create_run(")
    i_record = src.index('stage_name="yearly_reuse"')
    assert i_open < i_create < i_record, (
        f"order is wrong (open={i_open}, create={i_create}, "
        f"record={i_record}). The decision must be captured before the run "
        f"is created and recorded after, or it is either unattachable or a "
        f"second decision.")

    # THE DRIVER'S OWN ARGUMENTS, not the dataclass's defaults. The identity
    # test below builds its own StageResult and so proves what the TYPE does;
    # it cannot see the driver passing grain="asx_code". A mutation doing
    # exactly that survived until this was added -- the same gap as asserting
    # assess() directly while the call site went unchecked.
    window = src[i_record:i_record + 1200]
    assert 'grain="reused_run_id"' in window, (
        "the driver does not label this stage's grain as reused_run_id, so "
        "the row reads as a population of companies -- '1 of 1 expected' "
        "beside stages measuring thousands of asx_codes")
    for key in ("fingerprint_aggregate", "fingerprint_schema",
                "proven_by_run"):
        assert key in window, (
            f"the driver does not record {key!r}, so the row carries a "
            f"verdict without the evidence it was made on")


def test_the_reuse_stage_is_not_named_yearly_compute():
    """The dangerous mistake, asserted.

    proven_by_latest_yearly() selects stage_name='yearly_compute' AND
    status='success' to find the fingerprint the NEXT reuse is checked
    against. If a reuse were recorded under that name, a run that computed
    nothing would become the authority for the next run's reuse, and daily
    runs could inherit from one another indefinitely while the fundamentals
    moved underneath them -- a worse defect than the one being fixed.
    """
    from compute.engine.source_fingerprint import STAGE_DETAIL_KEY

    src = DRIVER.read_text(encoding="utf-8")
    i_record = src.index('stage_name="yearly_reuse"')
    window = src[i_record - 400:i_record + 1200]
    assert 'stage_name="yearly_compute"' not in window, (
        "the reuse is recorded under yearly_compute, which makes a run that "
        "computed nothing the fingerprint authority for the next reuse")

    # And it must not write the key the fingerprint lookup reads, which would
    # achieve the same thing by a different route.
    assert STAGE_DETAIL_KEY not in window, (
        f"the reuse stage writes {STAGE_DETAIL_KEY!r}, the very key "
        f"proven_by_latest_yearly reads. Under a different stage name it "
        f"would not be selected today, but it invites exactly the "
        f"inherit-from-an-inheritor chain this test exists to prevent.")


def test_the_stage_is_an_identity_record_not_a_coverage_claim():
    """Equal populations, deliberately, and the grain says what they are.

    A reuse covers no entities, so expected == written is not a coverage
    proof -- it is how a record whose subject is an identity passes a
    mechanism built to compare populations. The grain is what stops a reader
    taking "1 of 1 expected" for a company count.
    """
    token = "yearly_compute@run:60"
    r = StageResult(stage_name="yearly_reuse",
                    expected=frozenset({token}),
                    written=frozenset({token}),
                    grain="reused_run_id",
                    details={"proven_by_run": 60,
                             "fingerprint_aggregate": "c7ae7124"})
    assert r.ok and r.status == "success"
    payload = r.payload()
    assert payload["grain"] == "reused_run_id", (
        "the grain is not recorded, so a reader cannot tell what the counts "
        "are populations of")
    assert payload["fingerprint_aggregate"] == "c7ae7124", (
        "the fingerprint did not reach the details payload, so the row "
        "records a verdict without its evidence")
    assert payload["proven_by_run"] == 60


if __name__ == "__main__":
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
