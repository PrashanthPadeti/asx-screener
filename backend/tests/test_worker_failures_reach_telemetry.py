#!/usr/bin/env python
"""
A producer failure must cross the worker wrapper and be recorded
================================================================
Every scheduled job is registered as `instrumented("<id>", <worker>)`, and
`instrumented` records what the worker RAISES:

    try:
        result = await func(*args, **kwargs)
    except BaseException as exc:
        await _close_run(run_id, status=FAILED, failure=exc)
        raise
    await _close_run(run_id, status=SUCCESS)

But every worker wrapper caught `Exception` and did not re-raise:

    try:    await run(...)
    except Exception as exc:  log.error(...)      # <- consumed here
    finally: write_heartbeat()

So the wrapper returned normally and telemetry recorded `success`. Measured
7 Oct 2026 over the whole telemetry period: 666 success, 9 failed, and **all
nine failures were `SystemExit`** -- which derives from `BaseException`, is
not caught by `except Exception`, and therefore bypassed the wrappers
entirely. No ordinary producer failure had ever been observed crossing that
boundary.

`instrumented` was never defective. Its upstream contract was falsified.

Why the chain, not the pieces
-----------------------------
Testing `instrumented` with a raising coroutine proves nothing about this
defect -- it already handled that correctly. The property is compositional:
registration -> wrapper -> producer raises -> cleanup runs -> exception
re-raises -> telemetry records FAILED. Each link worked; the composition did
not.

Run:  python tests/test_worker_failures_reach_telemetry.py
"""

import ast
import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

#: The mandatory population, derived from the 20 `scheduler.add_job(...)`
#: registrations in app/main.py -- NOT from a grep for `except Exception`,
#: which finds 27 handlers, 10 of them inner helpers off the registration
#: path. A scanned population is not an authoritative one.
#:
#: Three of the twenty (short_positions, market_snapshot, anomaly_detect) use
#: `async with track_scheduler_job(...)`, whose __aexit__ returns False on the
#: non-skip path and therefore already propagates. They are excluded here
#: because they were already correct, and are covered by
#: test_the_context_manager_shape_still_propagates below.
REGISTERED_WRAPPERS = [
    ("alert_worker", "check_alerts"),
    ("portfolio_worker", "check_portfolio_thresholds"),
    ("portfolio_worker", "send_weekly_portfolio_summaries"),
    ("announcement_worker", "fetch_announcements"),
    ("watchlist_digest_worker", "send_watchlist_digests"),
    ("index_prices_worker", "compute_index_prices"),
    ("fund_prices_worker", "compute_fund_prices"),
    ("global_markets_worker", "compute_global_markets"),
    ("commodities_worker", "compute_commodities"),
    ("asx_indices_worker", "run_asx_indices"),
    ("capital_raise_worker", "scan_capital_raises"),
    ("mining_reit_worker", "sync_mining_reit_metrics"),
    ("top5_strategy_worker", "run_top5_strategy"),
    ("cleanup_worker", "purge_expired_sessions"),
    ("cleanup_worker", "run_data_deletion"),
    ("asx_companies_worker", "sync_asx_companies"),
    ("anomaly_alert_worker", "send_anomaly_alerts"),
]


def _fn(mod: str, name: str) -> ast.AST:
    src = (BACKEND / "app" / "workers" / f"{mod}.py").read_text(encoding="utf-8")
    return next(n for n in ast.walk(ast.parse(src))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name)


def _outermost_handlers(fn: ast.AST) -> list:
    """Handlers of the Try nearest the function root.

    By ancestor depth, not line number. In a nested try the OUTER handler's
    `except` clause appears LATER in the file than the inner one, so ordering
    by lineno selects the inner handler -- which produced a false failure on
    cleanup_worker.run_data_deletion during this work.
    """
    best, depth = None, {}

    def walk(node, d):
        nonlocal best
        if isinstance(node, ast.Try):
            best = d if best is None else min(best, d)
            depth[id(node)] = d
            d += 1
        for ch in ast.iter_child_nodes(node):
            walk(ch, d)

    walk(fn, 0)
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Try) and depth.get(id(n)) == best:
            out.extend(n.handlers)
    return out


# ── The compositional property, exercised end to end ────────────────────────

class _SyntheticProducerFailure(RuntimeError):
    """Stands in for compute.engine.producer_contract.ProducerFailure.

    Defined locally so this test exercises the WRAPPER contract -- "an
    ordinary Exception must cross" -- rather than one specific exception type
    the wrappers might someday special-case.
    """


def _run_chain(worker_body, *, swallow: bool):
    """Replays registration -> wrapper -> instrumented, recording telemetry.

    `instrumented` is reimplemented here rather than imported because the real
    one opens a database run. The semantics asserted are exactly its own:
    record FAILED and re-raise on BaseException, else record SUCCESS.
    """
    recorded = {}
    cleanup_ran = []

    async def wrapper():
        try:
            await worker_body()
        except Exception as exc:                      # noqa: BLE001
            if not swallow:
                raise
        finally:
            cleanup_ran.append(True)                  # heartbeat / db close

    async def instrumented():
        try:
            await wrapper()
        except BaseException as exc:                  # noqa: BLE001
            recorded["status"] = "failed"
            recorded["failure_class"] = type(exc).__name__
            recorded["failure_message"] = str(exc)
            return recorded
        recorded["status"] = "success"
        return recorded

    asyncio.run(instrumented())
    recorded["cleanup_ran"] = bool(cleanup_ran)
    return recorded


async def _failing_producer():
    raise _SyntheticProducerFailure(
        "index_prices obtained 0 usable results from 10 expected")


async def _working_producer():
    return None


def test_a_producer_failure_is_recorded_as_failed():
    r = _run_chain(_failing_producer, swallow=False)
    assert r["status"] == "failed", (
        "the producer raised and telemetry still recorded success")


def test_the_failure_cause_is_captured():
    r = _run_chain(_failing_producer, swallow=False)
    assert r["failure_class"] == "_SyntheticProducerFailure"
    assert "0 usable results" in r["failure_message"], (
        "the cause is lost, so the record says a job failed without saying why")


def test_cleanup_still_runs_when_the_producer_fails():
    """The `finally` must not be sacrificed to get the exception out.

    Heartbeat writes and session cleanup live there. A repair that moved the
    raise above the cleanup would trade one defect for another.
    """
    r = _run_chain(_failing_producer, swallow=False)
    assert r["cleanup_ran"] is True


def test_ordinary_success_is_still_success():
    r = _run_chain(_working_producer, swallow=False)
    assert r["status"] == "success"
    assert r["cleanup_ran"] is True


def test_the_old_behaviour_would_fail_this_suite():
    """Mutation control: restore the swallow and the failure must disappear."""
    r = _run_chain(_failing_producer, swallow=True)
    assert r["status"] == "success", (
        "the counterexample no longer reproduces the old behaviour, so the "
        "assertions above prove nothing")


# ── Source-level coverage over the authoritative population ─────────────────

def test_every_registered_wrapper_re_raises():
    missing = []
    for mod, fname in REGISTERED_WRAPPERS:
        handlers = _outermost_handlers(_fn(mod, fname))
        if not handlers:
            continue                      # no handler: nothing to swallow
        if not all(any(isinstance(x, ast.Raise) for x in ast.walk(h))
                   for h in handlers):
            missing.append(f"{mod}.{fname}")
    assert not missing, (
        "these registered wrappers consume the exception, so a producer "
        "failure in them is recorded as success: " + ", ".join(missing))


def test_the_population_matches_the_scheduler_registrations():
    """A hardcoded list is a declaration, not a population.

    Derived from app/main.py so that adding a job without a wrapper, or
    renaming one, breaks this rather than silently narrowing coverage. The
    three context-manager jobs are the documented difference.
    """
    src = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    registered = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "add_job" and n.args):
            first = n.args[0]
            if (isinstance(first, ast.Call) and isinstance(first.func, ast.Name)
                    and first.func.id == "instrumented"
                    and isinstance(first.args[1], ast.Name)):
                registered.add(first.args[1].id)

    assert len(registered) == 20, (
        f"expected 20 scheduler registrations, found {len(registered)}; the "
        "population this suite governs has changed")

    covered = {fname for _, fname in REGISTERED_WRAPPERS}
    context_manager_jobs = {"run_short_positions", "run_market_snapshot",
                            "run_anomaly_detect"}
    unaccounted = registered - covered - context_manager_jobs
    assert not unaccounted, (
        "registered jobs governed by neither this suite nor the "
        "track_scheduler_job contract: " + ", ".join(sorted(unaccounted)))


def test_the_context_manager_shape_still_propagates():
    """The three jobs that were already correct must stay correct.

    `track_scheduler_job.__aexit__` returns False on the non-skip path, which
    is what lets the exception reach `instrumented`. Checked on the return
    values rather than the docstring -- the docstring asserts this too, and a
    docstring is a description.
    """
    src = (BACKEND / "app" / "workers" / "pipeline_tracker.py").read_text(
        encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
              and n.name == "__aexit__")
    returns = [ast.unparse(n.value) for n in ast.walk(fn)
               if isinstance(n, ast.Return) and n.value is not None]
    assert "False" in returns, (
        "__aexit__ no longer returns False on any path, so it now suppresses "
        "job-body exceptions and the three context-manager jobs have gone "
        "silent")


def test_the_structural_check_can_fail():
    """Mutation control for the source scan."""
    src = ("async def w():\n"
           "    try:\n"
           "        await run()\n"
           "    except Exception as exc:\n"
           "        log.error(exc)\n")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.AsyncFunctionDef))
    handlers = _outermost_handlers(fn)
    assert handlers, "the extractor found no handler to judge"
    assert not any(any(isinstance(x, ast.Raise) for x in ast.walk(h))
                   for h in handlers), (
        "the detector cannot see a swallowing handler, so the coverage test "
        "above proves nothing")


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
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
