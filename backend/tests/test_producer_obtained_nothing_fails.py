#!/usr/bin/env python
"""
A producer that obtained nothing did not succeed
================================================
Measured on production, 3-6 October 2026:

    index_prices   4 runs   ~375s each    status success   0 rows
    fund_prices    4 runs   ~8,920s each  status success   0 rows

`market.index_prices` has not advanced past 1 October; the site's headline
index charts have been four trading days stale. `fund_prices` spent about ten
hours of execution producing nothing. Every run reported terminal `success`.

The cause was that `None` meant two things:

    df = await asyncio.to_thread(fetch_..., ticker, start, end)
    if df is None:
        continue

-- returned both when the source had nothing for a ticker and when the source
refused the request. Every ticker was refused, every iteration continued, and
the coroutine returned normally.

The counts here are the observed ones. 10 indices and 47 funds, all refused,
is not a hypothetical.

Run:  python tests/test_producer_obtained_nothing_fails.py
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.producer_contract import (            # noqa: E402
    ProducerFailure, ProducerTally, SourceRefused)


def _raises(fn) -> ProducerFailure | None:
    try:
        fn()
    except ProducerFailure as exc:
        return exc
    return None


def test_the_october_index_run_is_a_failure():
    """10 indices, every one refused, 0 rows. Reported success for four days."""
    t = ProducerTally("index_prices", expected=10)
    for ticker in ("^ATLI", "^AFLI", "^AXTO", "^AXJO", "^AXKO",
                   "^AXFJ", "^AXMJ", "^AXEJ", "^AXHJ", "^AXJO"):
        t.refusal(ticker)
    exc = _raises(t.verify)
    assert exc is not None, (
        "the exact production run that reported success for four days still "
        "does not fail")
    assert "source_refused" in str(exc)
    assert "10" in str(exc)


def test_the_october_fund_run_is_a_failure():
    """47 funds, every one refused, ~8,920s, 0 rows."""
    t = ProducerTally("fund_prices", expected=47)
    for i in range(47):
        t.refusal(f"FUND{i}.AX")
    exc = _raises(t.verify)
    assert exc is not None
    assert "47" in str(exc)


def test_the_cause_distinguishes_refusal_from_absence():
    """Two different events that both produce zero rows.

    "The source declined to serve us" and "the market was closed" are not the
    same finding, and an operator reading the failure needs to know which.
    """
    refused = ProducerTally("p", expected=3)
    for i in range(3):
        refused.refusal(f"T{i}")
    assert "source_refused" in str(_raises(refused.verify))

    nothing = ProducerTally("p", expected=3)
    for _ in range(3):
        nothing.nothing_available()
    assert "no_observations" in str(_raises(nothing.verify))


def test_a_partial_run_is_not_a_failure():
    """9 of 10 obtained is not nothing, and the threshold question is open.

    Deciding today that some percentage must fail would be inventing a
    completeness rule without evidence. What IS proven is that zero must fail.
    """
    t = ProducerTally("index_prices", expected=10)
    for i in range(9):
        t.obtained(rows=4)
    t.refusal("^AXHJ")
    assert _raises(t.verify) is None
    assert t.rows == 36


def test_one_success_among_total_refusal_still_passes():
    """The boundary is zero, not "mostly"."""
    t = ProducerTally("fund_prices", expected=47)
    for i in range(46):
        t.refusal(f"F{i}.AX")
    t.obtained(rows=1)
    assert _raises(t.verify) is None


def test_an_empty_population_is_vacuous_not_failed():
    """Nothing expected, nothing obtained, nothing stale.

    Raising here would make an empty configuration look like an outage.
    """
    assert _raises(ProducerTally("p", expected=0).verify) is None


def test_the_failure_is_raised_so_telemetry_records_it():
    """`instrumented` records what the job RAISES and re-raises it unchanged.

    A returned status object would leave ops.job_executions saying `success`
    -- which is the entire defect. This asserts the mechanism, not the value.
    """
    assert issubclass(ProducerFailure, Exception)
    t = ProducerTally("p", expected=1)
    t.refusal("X")
    try:
        t.verify()
    except ProducerFailure:
        return
    raise AssertionError("verify() did not raise, so the job would still "
                         "report success")


def test_refusal_is_a_distinct_exception_type():
    """Not an empty frame, not None. The producers must be able to catch it
    separately from an ordinary empty result."""
    assert issubclass(SourceRefused, Exception)
    assert not issubclass(SourceRefused, ProducerFailure)
    exc = SourceRefused("^AXJO", "Too Many Requests")
    assert "^AXJO" in str(exc)


# ── Structural: the defect was a shape, so the shape is guarded ──────────────

def _run_body(path: Path) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            return node
    raise AssertionError(f"{path.name} has no async run()")


def test_both_producers_verify_before_returning():
    for name in ("index_prices.py", "fund_prices.py"):
        body = _run_body(BACKEND / "compute" / "engine" / name)
        calls = [n for n in ast.walk(body)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "verify"]
        assert calls, (
            f"{name}'s run() never calls tally.verify(), so a run that "
            f"obtains nothing still returns normally and is recorded as "
            f"success")


def test_no_retry_cascade_survives_in_either_fetcher():
    """The 5/10/15 and 30/60/90 backoffs are gone.

    Checked on string constants and numeric literals inside the fetch
    functions rather than on file text, because this module's own docstring
    names those numbers -- a text scan would read its own explanation and
    report the cascade it just removed. That has now happened five times in
    this codebase.
    """
    for name, fn_name in (("index_prices.py", "fetch_index_data"),
                          ("fund_prices.py", "fetch_fund_data")):
        path = BACKEND / "compute" / "engine" / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == fn_name),
                  None)
        assert fn is not None, f"{name} has no {fn_name}"

        sleeps = [n for n in ast.walk(fn)
                  if isinstance(n, ast.Call)
                  and ((isinstance(n.func, ast.Attribute)
                        and n.func.attr == "sleep")
                       or (isinstance(n.func, ast.Name)
                           and n.func.id == "sleep"))]
        assert not sleeps, (
            f"{fn_name} still sleeps. Every request was refused before the "
            f"first ticker was asked for, so waiting inside the run cannot "
            f"help -- it cost 2.5 hours a day for zero rows")

        loops = [n for n in ast.walk(fn)
                 if isinstance(n, (ast.For, ast.While))]
        assert not loops, (
            f"{fn_name} still retries in a loop over attempts")


def test_the_structural_checks_can_fail():
    """Mutation control for both guards above."""
    src = (
        "import time\n"
        "def fetch_index_data(t, s, e, retries=3):\n"
        "    for attempt in range(retries):\n"
        "        time.sleep(5 * (attempt + 1))\n"
        "    return None\n")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef))
    sleeps = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "sleep"]
    loops = [n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.While))]
    assert sleeps and loops, (
        "the detector cannot see the cascade it replaced, so the guards above "
        "prove nothing")


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
