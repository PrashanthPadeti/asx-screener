"""
A plan names stages, never executables
======================================
The driver's stage dispatcher, and the two properties that keep it boring:

    every stage a plan can name has a FIXED command in this module
    the arguments are production-shaped, matching the real cadence

The second is easy to lose. Running production code with rehearsal-shaped
arguments proves that the code runs, not that the nightly sequence composes.
transform_prices is the case that matters: the daily pipeline passes
--from-date, and its full-replacement mode is a rare manual path whose
atomicity was proved separately. Exercising that here would answer a different
question and quietly claim to have answered this one.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_stage_dispatch.py
"""

import importlib.util
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.run_plans import EXECUTABLE_PLANS, PLANS  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "p0a_driver", BACKEND / "scripts" / "p0a_canonical_run.py")
driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(driver)


# ── Coverage ─────────────────────────────────────────────────────────────────

def test_every_stage_any_plan_can_run_has_a_command():
    """An unknown stage must be a defect found before the run starts, not a
    subprocess failure halfway through one — after a run id exists."""
    for name, plan in PLANS.items():
        for stage in plan.stages[:-1]:
            assert stage in driver.STAGE_COMMANDS, (
                f"{name} runs '{stage}' and the driver has no command for it")


def test_the_canonical_tail_is_not_in_the_producer_dispatcher():
    """It is invoked separately, after the fault seam, with --plan. Dispatching
    it as an ordinary producer would put it before the boundary it must come
    after."""
    for plan in PLANS.values():
        assert plan.stages[-1] == "composite_score"
    assert "composite_score" not in driver.STAGE_COMMANDS


def test_an_unknown_stage_is_refused_before_anything_runs():
    try:
        driver.dispatch("rm_minus_rf", 1)
    except driver.PreconditionFailed as e:
        assert "no command is defined" in str(e)
    else:
        raise AssertionError("the plan was allowed to name its own executable")


# ── The arguments are production-shaped ──────────────────────────────────────

def test_transform_prices_uses_the_nightly_incremental_window():
    """Not full-replacement mode.

    A full run truncates and rebuilds the whole price history — a rare manual
    operation. The daily pipeline passes --from-date, so that is what a
    production-shaped rehearsal must pass; otherwise the rehearsal proves the
    atomicity of a path production does not take that night, and says nothing
    about whether the nightly sequence composes.
    """
    argv = driver.dispatch("transform_prices", 42)
    assert "--from-date" in argv, (
        "transform_prices would run in full-replacement mode, which is not "
        "what the nightly pipeline does")

    window = argv[argv.index("--from-date") + 1]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", window), window

    from datetime import datetime, timedelta, timezone
    expected = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    assert window == expected, (
        f"the window is {window}, the nightly pipeline's is {expected}")

    for flag in ("--codes", "--allow-shrink"):
        assert flag not in argv, f"{flag} is not part of the nightly shape"


def test_every_producer_is_told_the_run_it_belongs_to():
    """Without --run-id a producer computes and records no evidence, so the
    plan's required stages could never be satisfied."""
    for stage in driver.STAGE_COMMANDS:
        argv = driver.dispatch(stage, 42)
        assert "--run-id" in argv, f"{stage} is dispatched with no run id"
        assert argv[argv.index("--run-id") + 1] == "42"


def test_no_producer_is_dispatched_with_a_scoping_flag():
    """--codes or --limit narrows the population, and every producer treats a
    scoped run as one that records no evidence. The plan would then wait for
    stage rows that are never written."""
    for stage in driver.STAGE_COMMANDS:
        argv = driver.dispatch(stage, 42)
        for flag in ("--codes", "--limit", "--dry-run"):
            assert flag not in argv, f"{stage} is dispatched scoped ({flag})"


def test_commands_are_argv_lists_naming_the_interpreter():
    for stage in driver.STAGE_COMMANDS:
        argv = driver.dispatch(stage, 1)
        assert isinstance(argv, list) and len(argv) >= 2
        assert argv[0] == driver.PYBIN, (
            f"{stage} names its own interpreter rather than this process's")
        assert argv[1].endswith(".py")
        assert all(isinstance(a, str) for a in argv)


# ── Nothing becomes a shell command ──────────────────────────────────────────

def _driver_code():
    """Executable source only: no comments, and no docstrings.

    The module docstring describes this ordering in prose, so a guard that
    searched the raw text found `discovery_fault("after_provisional_rebuild")`
    on line 21 and concluded the seam came before the loop. It would have
    passed just as happily with the real call deleted — an inert guard reading
    its own documentation, which is the failure mode this codebase keeps
    producing.
    """
    import ast
    src = (BACKEND / "scripts" / "p0a_canonical_run.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))


def test_the_driver_never_invokes_a_shell():
    code = _driver_code()
    assert "shell=True" not in code, (
        "a stage name would become part of a shell command line")
    assert "os.system" not in code and "subprocess.call(" not in code
    assert "shell=False" in code, (
        "the explicit default is stated so a later edit has to argue with it")


def test_exit_zero_is_not_treated_as_completion():
    """A producer can exit 0 having written a subset of its population. The
    evidence is what says whether it covered the population it owed."""
    code = _driver_code()
    body = code[code.index("def run_producer("):]
    body = body[:body.index("\ndef ", 1)] if "\ndef " in body[1:] else body
    assert "require_stage(" in body, (
        "run_producer accepts a zero exit as proof of completion")
    assert "plan.required" in body, (
        "evidence is demanded of stages the plan does not require, or of none")


def test_producers_run_before_the_fault_seam_and_the_tail_after():
    """The seam sits between a committed provisional rebuild and the canonical
    tail — the one boundary where today's values exist with no attribution."""
    code = _driver_code()
    loop = code.index("for stage in plan.stages[:-1]:")
    seam = code.index('discovery_fault("after_provisional_rebuild"')
    tail = code.index("composite_score (canonical commit)")
    assert loop < seam < tail, (
        "the fault seam is not between the producers and the canonical tail")


# ── The attestation marker is clone infrastructure ───────────────────────────

def test_no_lifecycle_code_creates_or_repairs_the_scratch_marker():
    """If it is absent or inconsistent, discovery refuses.

    No writer gets to helpfully manufacture the attestation its own permission
    depends on — that would let the lifecycle grant itself the isolation it is
    supposed to be proving. Only the clone step, which is not part of any run,
    may write it.
    """
    allowed = {"scripts/p0a_discovery.sh"}
    offenders = []
    for path in list(BACKEND.rglob("*.py")) + list(BACKEND.rglob("*.sh")) \
            + list(BACKEND.rglob("*.sql")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel in allowed or "/tests/" in f"/{rel}" or "__pycache__" in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "p0a_scratch_marker" not in text:
            continue
        for verb in ("CREATE TABLE", "INSERT INTO", "UPDATE ", "DELETE FROM",
                     "DROP TABLE"):
            if re.search(verb + r"[^;]{0,80}p0a_scratch_marker", text,
                         re.I | re.S):
                offenders.append(f"{rel} ({verb.strip()})")
    assert not offenders, (
        f"these write the scratch marker: {offenders}. It is clone "
        f"infrastructure, not application schema: a writer that can create it "
        f"can grant itself the isolation it is meant to be proving.")


def test_the_envelope_only_reads_the_marker():
    code = (BACKEND / "compute/engine/runtime_envelope.py"
            ).read_text(encoding="utf-8")
    assert "to_regclass" in code, (
        "the marker is read without to_regclass, so on a database that has "
        "none the SELECT aborts the caller's transaction")
    for verb in ("CREATE TABLE", "INSERT INTO", "DROP TABLE"):
        assert verb not in code.upper(), f"the envelope {verb}s"


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
