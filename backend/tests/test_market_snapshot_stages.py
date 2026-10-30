"""
A rollback in stage 3 destroyed stages 1 and 2, daily, for five months
=======================================================================
On 30 October 2026 the Market Overview page showed 199 ASX 200 constituents
with 99 gainers and 80 losers. The twenty missing were not a rounding error:
the page was serving index figures from **30 May 2026**, five months stale,
beside a sector heatmap that was equally stale and movers that were current to
yesterday.

    index_snapshots    last written 2026-05-30
    sector_snapshots   last written 2026-05-30
    mover_snapshots    last written 2026-10-29
    exdiv_snapshots    last written 2026-10-29
    job heartbeat      2026-10-29, run_count 127

The job ran every night and reported success every night.

The mechanism
-------------
``run()`` wrote all four stages into one session with a single commit at the
end. Stage 3 looped over mover periods, and its per-query handler ended with

    except Exception:
        ...
        await session.rollback()

``session.rollback()`` does not undo one statement. It discards every
uncommitted write in the session -- which, at that point, was stages 1 and 2.

What made it total rather than occasional is that the first mover period asks
for ``return_1d``, and ``screener.universe`` has never had that column. The
handler was reached on every run, so the index and sector snapshots were
destroyed on every run. Movers and ex-div, written afterwards, committed
normally. The log then said "Committed snapshot for <date>".

Three defects, smallest first
-----------------------------
1. A handler meaning "undo this statement" could undo somebody else's work.
   Now a SAVEPOINT (``begin_nested``), and each finished stage commits its own
   transaction rather than waiting for the end of the run.
2. A column that CANNOT exist was discovered by running a query and catching
   the error. Availability is now established from information_schema before
   any statement runs -- cannot-exist is a fact, not a runtime failure.
3. The run reported success while producing two of four outputs. Stage
   outcomes are now recorded and an empty required stage raises, AFTER the
   commit, so partial data survives but the claim of success does not.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_market_snapshot_stages.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND  = Path(__file__).resolve().parents[1]
ENGINE   = BACKEND / "compute/engine/market_snapshot.py"
PAGE     = BACKEND.parent / "frontend/app/market/page.tsx"

sys.path.insert(0, str(BACKEND))


class Skipped(Exception):
    """Needs a runtime dependency this environment does not have."""


def _tree() -> ast.AST:
    return ast.parse(ENGINE.read_text(encoding="utf-8"))


def _run_fn() -> ast.AsyncFunctionDef:
    fn = next((n for n in ast.walk(_tree())
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "run"), None)
    assert fn is not None, "market_snapshot.run() is gone"
    return fn


def _calls(fn, attr: str) -> list:
    """Line numbers of `<something>.<attr>()` calls inside fn."""
    return [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == attr]


# ── 1. The rollback ──────────────────────────────────────────────────────────

def test_the_engine_never_rolls_back_the_whole_session():
    """The defect itself, named directly.

    Structural rather than textual: the file's comments quote
    `session.rollback()` deliberately, and a grep would match its own
    explanation. Only a real call node counts.
    """
    offenders = _calls(_run_fn(), "rollback")
    assert not offenders, (
        f"session.rollback() is called at line(s) {offenders}. It discards "
        f"every uncommitted write in the session, not the one statement the "
        f"handler meant to undo. That destroyed the index and sector "
        f"snapshots on every run for five months. Use begin_nested().")


def test_a_failing_mover_query_is_contained_in_a_savepoint():
    """The replacement must actually be there, not merely the absence."""
    assert _calls(_run_fn(), "begin_nested"), (
        "no begin_nested() in run(). Without a savepoint a failing mover "
        "query either takes the transaction with it or is not contained at "
        "all.")


def test_each_stage_commits_before_the_next_one_can_undo_it():
    """One commit at the end is what made the blast radius the whole run."""
    commits = _calls(_run_fn(), "commit")
    assert len(commits) >= 3, (
        f"only {len(commits)} commit(s) in run(). Stages 1 and 2 must be "
        f"durable before stage 3 executes; a single trailing commit leaves "
        f"them exposed to anything that happens in between.")


# ── 2. The column that cannot exist ──────────────────────────────────────────

def test_mover_periods_are_filtered_by_what_the_table_has():
    """`return_1d` has never existed. Asking the database and catching the
    error is how the rollback was reached every single night."""
    src = ENGINE.read_text(encoding="utf-8")
    assert "_available_return_columns" in src, (
        "nothing establishes which return columns exist before querying them")
    fn = _run_fn()
    assert any(isinstance(n, ast.Call)
               and isinstance(n.func, ast.Name)
               and n.func.id == "_available_return_columns"
               for n in ast.walk(fn)), (
        "run() does not consult _available_return_columns; a missing column "
        "is still discovered by failing")


def test_the_engine_still_wants_a_period_it_cannot_currently_have():
    """Population control, and a live one.

    RETURN_PERIODS must still contain return_1d. If somebody 'fixes' this by
    deleting the period, the filter above has nothing to filter and the test
    passes over an empty hazard. The 1D period is a real product gap -- the
    column should be computed -- not something to quietly drop.
    """
    try:
        from compute.engine.snapshot_stages import RETURN_PERIODS
    except ImportError as e:
        raise Skipped(f"snapshot_stages ({e.name}) — it should need nothing")
    cols = [c for _, c in RETURN_PERIODS]
    assert "return_1d" in cols, (
        f"return_1d was removed from RETURN_PERIODS ({cols}) rather than "
        f"handled. The availability filter now guards nothing.")


# ── 3. Success must mean something ───────────────────────────────────────────

def test_the_exact_five_month_condition_is_a_failure():
    """index=0, sector=0, movers and exdiv fine. This ran 127 times and was
    reported as success every time."""
    try:
        from compute.engine.snapshot_stages import incomplete_stages
    except ImportError as e:
        raise Skipped(f"snapshot_stages ({e.name}) — it should need nothing")
    empty = incomplete_stages({"index": 0, "sector": 0,
                               "movers": 80, "exdiv": 12})
    assert empty == ["index", "sector"], (
        f"the production failure state was not reported as incomplete: "
        f"{empty}")


def test_a_complete_run_is_not_reported_as_incomplete():
    """The other outcome. A checker that calls everything a failure is as
    useless as one that calls everything a success."""
    try:
        from compute.engine.snapshot_stages import incomplete_stages
    except ImportError as e:
        raise Skipped(f"snapshot_stages ({e.name}) — it should need nothing")
    assert incomplete_stages({"index": 2, "sector": 11,
                              "movers": 60, "exdiv": 12}) == []


def test_an_empty_run_names_every_required_stage():
    try:
        from compute.engine.snapshot_stages import (
            REQUIRED_STAGES, incomplete_stages)
    except ImportError as e:
        raise Skipped(f"snapshot_stages ({e.name}) — it should need nothing")
    assert incomplete_stages({}) == list(REQUIRED_STAGES)
    assert REQUIRED_STAGES, "no stage is required, so nothing can be incomplete"


def test_no_stage_counter_sits_inside_a_dry_run_guard():
    """The instrument must measure the work, not the write.

    The first version of this release counted index and sector inside the
    `if not dry_run:` block that performs the INSERT, while movers and ex-div
    were counted outside theirs. A dry run that had just computed 2 index rows
    and 12 sector rows therefore reported

        Stage outcomes: index=0, sector=0, movers=110, exdiv=7

    which reads exactly like the five-month production failure this release
    exists to fix. An instrument that reports zero for work that happened is
    worse than no instrument: it manufactures the alarm it was built to raise.
    """
    fn = _run_fn()

    def _guards_dry_run(node) -> bool:
        return isinstance(node, ast.If) and any(
            isinstance(n, ast.Name) and n.id == "dry_run"
            for n in ast.walk(node.test))

    offenders = []
    for node in ast.walk(fn):
        if not _guards_dry_run(node):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Assign)
                    and any(isinstance(t, ast.Subscript)
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "written"
                            for t in inner.targets)):
                offenders.append(inner.lineno)

    assert not offenders, (
        f"stage counters at line(s) {offenders} are inside a dry_run guard, "
        f"so a dry run reports those stages as empty whatever they computed.")


def test_every_required_stage_is_actually_counted():
    """A stage nobody increments is permanently 'incomplete'."""
    src = ENGINE.read_text(encoding="utf-8")
    from compute.engine.snapshot_stages import REQUIRED_STAGES
    for stage in REQUIRED_STAGES:
        assert f'written["{stage}"]' in src, (
            f"'{stage}' is required but never counted, so the run can only "
            f"ever raise SnapshotIncomplete")


def test_the_run_raises_rather_than_logging_a_warning():
    """A warning in a log nobody greps is how five months happen."""
    fn = _run_fn()
    assert any(isinstance(n, ast.Raise) for n in ast.walk(fn)), (
        "run() never raises; an incomplete snapshot would still be recorded "
        "as a successful job")
    assert "SnapshotIncomplete" in ENGINE.read_text(encoding="utf-8")


# ── 4. Unknown is not zero ───────────────────────────────────────────────────

def test_unchanged_does_not_absorb_missing_returns():
    """`return_1w = 0 OR return_1w IS NULL AS unchanged` reported a company we
    have no return for as one whose price did not move."""
    src = ENGINE.read_text(encoding="utf-8")
    sql_lines = [ln for ln in src.splitlines()
                 if "AS unchanged" in ln and not ln.strip().startswith("--")]
    assert sql_lines, "the unchanged aggregate is gone from the index query"
    for line in sql_lines:
        assert "IS NULL" not in line.upper(), (
            f"unchanged still counts rows with no return: {line.strip()}")


def test_missing_returns_are_counted_and_refused_rather_than_hidden():
    """There is no column for 'we do not know', so the run must stop instead
    of folding those rows into a bucket that claims to know."""
    src = ENGINE.read_text(encoding="utf-8")
    assert "AS no_return" in src, (
        "nothing counts constituents with no return_1w, so the condition "
        "that would re-create the defect is invisible")
    assert re.search(r"no_return.*\n.*SnapshotIncomplete", src) \
        or "no_return" in src.split("SnapshotIncomplete")[0], \
        "no_return is counted but never acted on"


# ── 5. The page shows what the API returns ───────────────────────────────────

def test_the_market_page_renders_the_unchanged_count():
    """99 + 80 under a total of 199 is not a bug in the arithmetic; it is a
    category the page declined to display."""
    if not PAGE.exists():
        raise Skipped("the frontend tree (not present in this checkout)")
    src = PAGE.read_text(encoding="utf-8")
    assert "snap.unchanged" in src, (
        "the market page renders gainers and losers but not unchanged, so "
        "the three numbers cannot reconcile with stock_count")


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
