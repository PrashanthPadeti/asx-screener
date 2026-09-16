"""
Orchestration invariants the schedulers must not silently break
===============================================================
P0-A-1 proved the database matched canonical intent **at commit time**. The
P0-A-2 audit found that the production scheduler did not preserve that over
time: the daily universe rebuild overwrites governed values while retaining
the previous run's ``metric_states`` and ``compute_run_id``, because
``build_screener_universe.py`` never writes those columns and
``composite_score.py`` runs only in the weekly pipeline.

A row in that state is worse than an unassessed one. It *claims* to be
canonically assessed, so the projector trusts it and serves it.

The invariant, frozen:

    Any writer that changes one of the 72 governed storage columns must
    either be part of a canonical run ending in full persistence, read-back
    validation and finalisation, or invalidate the previous contract
    atomically with its write. There is no third state where governed values
    change and old attribution survives.

These tests hold the two properties that audit established, so neither can
drift back without failing:

    the four non-canonical universe writers touch 0 of 72 governed columns
    the orchestrators resolve exactly one compute-engine tree

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_orchestration_contract.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND = Path(__file__).resolve().parents[1]
JOBS = BACKEND / "scripts" / "eodhd" / "v2" / "jobs"
ENGINE = BACKEND / "compute" / "engine"

#: Producers that write screener.universe WITHOUT being part of a canonical
#: run. Safe to schedule after a finalisation only while their write sets
#: stay disjoint from the governed storage set — which is a property, not a
#: promise, so it is asserted rather than assumed.
NON_CANONICAL_WRITERS = (
    "asx_indices", "dilution_metrics", "pros_cons", "short_positions",
)


def _governed_columns() -> set:
    from compute.engine.metric_states import GOVERNED_METRICS, LATEST_MODEL_VERSION
    from compute.engine.universe_writer import column_for
    return {column_for(m) for m in GOVERNED_METRICS[LATEST_MODEL_VERSION]}


def _assigned_columns(source: str) -> set:
    """Column names on the left of an assignment inside an UPDATE/SET.

    Deliberately over-broad: it will catch a column this producer merely
    mentions as well as one it writes. For a guard whose failure mode is
    "a governed column started being mutated outside a canonical run", a
    false positive costs a conversation and a false negative costs the
    contract.
    """
    code = "\n".join(ln for ln in source.splitlines()
                     if not ln.strip().startswith("#"))
    out = set()
    for m in re.finditer(r"\bSET\b(.*?)(?:\bWHERE\b|\bFROM\b|\"\"\"|$)",
                         code, re.S | re.I):
        for assign in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", m.group(1)):
            out.add(assign.group(1))
    return out


def test_non_canonical_writers_touch_no_governed_column():
    """The negative evidence from the P0-A-2 audit, made permanent.

    These four run after publication — index flags at 17:50, short positions
    at 18:30, pros/cons and dilution in the weekly tail. They may do so only
    because their write sets intersect the governed set at zero. Adding a
    governed column to any of them would let a value change under a
    finalisation that still vouches for the old one.
    """
    governed = _governed_columns()
    offenders = {}
    for name in NON_CANONICAL_WRITERS:
        path = ENGINE / f"{name}.py"
        assert path.exists(), f"{name}.py has moved; this guard is now inert"
        hits = sorted(_assigned_columns(path.read_text(encoding="utf-8"))
                      & governed)
        if hits:
            offenders[name] = hits

    assert not offenders, (
        f"non-canonical writers now assign governed columns: {offenders}. "
        f"Either fold the producer into the canonical run, or have it "
        f"invalidate compute_run_id and metric_states atomically with its "
        f"write. A governed value must never change while an earlier run's "
        f"attribution survives on the row.")


def test_the_universe_builder_does_not_write_the_canonical_columns():
    """Stated so the reason is recorded, not because it is desirable.

    build_screener_universe leaving metric_states and compute_run_id alone is
    exactly what lets them survive its rebuild. That is the defect, and the
    fix is a canonical tail after every governed rebuild — not making the
    builder write a sidecar it cannot compute.

    If this ever fails, the builder has started writing canonical state
    outside the canonical writer, which is a different and equally serious
    problem.
    """
    src = (BACKEND / "scripts" / "eodhd" / "v2"
           / "build_screener_universe.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("--"))

    for canonical in ("metric_states", "compute_run_id"):
        assert canonical not in code, (
            f"build_screener_universe now references {canonical}; canonical "
            f"state must be written only by the canonical writer, under a "
            f"run that finalises")


def test_each_orchestrator_resolves_exactly_one_compute_tree():
    """No fallback, and no second candidate.

    daily_pipeline resolved two paths and took whichever existed. BASE_DIR is
    `backend`, so the branch named "canonical" pointed at
    backend/backend/compute/engine and could never exist, while the one named
    "fallback" was the maintained tree. It worked by accident, with the names
    inverted — and correcting BASE_DIR to the repo root, the obvious reading
    of its comment, would have selected <repo>/compute/engine: the stale
    April copies the deployment contract records as a live hazard.
    """
    for name in ("daily_pipeline.py", "weekly_pipeline.py"):
        code = "\n".join(
            ln for ln in (JOBS / name).read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("#"))

        assigns = re.findall(r"^COMPUTE\s*=\s*(.+)$", code, re.M)
        assert len(assigns) == 1, (
            f"{name} assigns COMPUTE {len(assigns)} times; there must be "
            f"exactly one engine tree")
        assert "if" not in assigns[0] and "else" not in assigns[0], (
            f"{name} selects its compute tree conditionally: {assigns[0]!r}. "
            f"A pipeline that silently picks a second tree is worse than one "
            f"that cannot start.")
        assert 'BASE_DIR / "compute" / "engine"' in assigns[0], (
            f"{name} does not resolve the maintained backend/compute/engine "
            f"tree: {assigns[0]!r}")


def test_the_daily_orchestrator_fails_loudly_without_its_engine():
    """Absence must stop the pipeline, not select an alternative."""
    code = (JOBS / "daily_pipeline.py").read_text(encoding="utf-8")
    assert re.search(r"COMPUTE\.is_dir\(\)[\s\S]{0,300}SystemExit", code), (
        "daily_pipeline does not abort when its compute tree is missing")


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
