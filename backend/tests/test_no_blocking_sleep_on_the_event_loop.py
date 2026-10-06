#!/usr/bin/env python
"""
A coroutine may not block the event loop
========================================
`AsyncIOScheduler` runs coroutine jobs ON the event loop. A blocking call
inside one does not slow that job down -- it stops the API answering anything,
including /health, including login.

5 Oct 2026, 06:35 UTC. `compute_fund_prices` is `async def`. Its loop called

    time.sleep(2)                                    # between tickers
    fetch_fund_data(...)                             # sync, and inside it:
        time.sleep(30); time.sleep(60); time.sleep(90)   # on rate limit

Yahoo rate-limited every ticker, so each of 47 funds cost 182 seconds of
blocking sleep. Production returned Cloudflare 504 for 35 minutes until the
service was restarted, with ~1.8 hours still to run. The giveaway was

    load average: 0.00, 0.00, 0.00     the process was not busy
    health_http=000 time=10.002s       it was asleep

This was the SECOND outage from long external I/O inside the API process,
after 2 Oct. The first produced a queued remediation that was never done.

Checked with the AST, not a text scan: `time.sleep` appearing in a comment or
a docstring is not a call, and this codebase has repeatedly been caught by
guards that read their own explanations.

Run:  python tests/test_no_blocking_sleep_on_the_event_loop.py
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCANNED = ("app/workers", "compute/engine", "app/api")

#: Calls that block the thread they run on. In a coroutine that thread is the
#: event loop, and everything the process serves stops with it.
BLOCKING = {
    ("time", "sleep"): "await asyncio.sleep(...)",
    ("requests", "get"): "httpx.AsyncClient, or asyncio.to_thread(...)",
    ("requests", "post"): "httpx.AsyncClient, or asyncio.to_thread(...)",
}


def _files():
    for rel in SCANNED:
        root = BACKEND / rel
        if root.exists():
            yield from (p for p in root.rglob("*.py")
                        if "__pycache__" not in p.parts)


def _module_functions(tree: ast.AST) -> dict:
    """Module-level functions by name, with their async-ness."""
    return {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _direct_blocking(node) -> list:
    """Blocking calls in this function's own body, not nested defs."""
    out = []

    def walk(n):
        for c in ast.iter_child_nodes(n):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(c, ast.Call):
                f = c.func
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    key = (f.value.id, f.attr)
                    if key in BLOCKING:
                        out.append((c.lineno, ".".join(key), BLOCKING[key]))
            walk(c)

    walk(node)
    return out


def _calls_to(node, names: set) -> list:
    """Calls to any of `names`, by bare name, in this function's body.

    A function PASSED to asyncio.to_thread is an ast.Name argument, not an
    ast.Call -- so the remedy is invisible here by construction, which is what
    makes this check mean "called on the loop" rather than "mentioned".
    """
    out = []

    def walk(n):
        for c in ast.iter_child_nodes(n):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)                     and c.func.id in names:
                out.append((c.lineno, c.func.id))
            walk(c)

    walk(node)
    return out


def blocking_reachable_from_coroutines(tree: ast.AST) -> list:
    """Coroutines that block, directly OR through a sync function they call.

    The first version of this guard checked only the coroutine's own body. It
    would NOT have caught the defect it was written for: fund_prices.run called
    fetch_fund_data, a module-level sync function, and the 30/60/90 sleeps were
    in there. The one line it did catch -- a bare time.sleep(2) -- was the
    smaller half.

    It also missed index_prices entirely, which has the identical shape and
    took the API down for five minutes on 6 Oct 2026, the morning after the
    fund_prices fix shipped.

    So the call graph is followed one module deep: a sync function that blocks
    taints every coroutine that CALLS it. Passing it to asyncio.to_thread is
    not a call, so the remedy is distinguished from the defect structurally
    rather than by naming convention.
    """
    funcs = _module_functions(tree)

    # Sync functions that block, directly or by calling another that does.
    blockers = {n for n, f in funcs.items()
                if isinstance(f, ast.FunctionDef) and _direct_blocking(f)}
    changed = True
    while changed:
        changed = False
        for name, f in funcs.items():
            if name in blockers or isinstance(f, ast.AsyncFunctionDef):
                continue
            if _calls_to(f, blockers):
                blockers.add(name)
                changed = True

    findings = []
    for name, f in funcs.items():
        if not isinstance(f, ast.AsyncFunctionDef):
            continue
        for lineno, call, remedy in _direct_blocking(f):
            findings.append((lineno, f"{name}() calls {call}(...)", remedy))
        for lineno, callee in _calls_to(f, blockers):
            findings.append((
                lineno,
                f"{name}() calls {callee}(), which blocks",
                f"await asyncio.to_thread({callee}, ...)"))
    return findings


def _blocking_calls_in_coroutines(tree: ast.AST):
    """Blocking calls lexically inside an `async def`, in the coroutine's own
    body -- not inside a nested plain `def`, which runs on whatever thread
    calls it and is the legitimate way to hold blocking work.
    """
    found = []

    def walk(node, in_async: bool):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.AsyncFunctionDef):
                walk(child, True)
            elif isinstance(child, ast.FunctionDef):
                walk(child, False)          # nested sync def: allowed
            elif isinstance(child, ast.Lambda):
                walk(child, False)
            else:
                if in_async and isinstance(child, ast.Call):
                    f = child.func
                    if (isinstance(f, ast.Attribute)
                            and isinstance(f.value, ast.Name)):
                        key = (f.value.id, f.attr)
                        if key in BLOCKING:
                            found.append((child.lineno, ".".join(key),
                                          BLOCKING[key]))
                walk(child, in_async)

    walk(tree, False)
    return found


def test_no_coroutine_blocks_the_event_loop():
    offences = []
    for path in _files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, call, remedy in blocking_reachable_from_coroutines(tree):
            offences.append(
                f"{path.relative_to(BACKEND)}:{lineno}  {call}(...)  "
                f"-> use {remedy}")
    assert not offences, (
        "a coroutine blocks the event loop; while it sleeps the API answers "
        "nothing:\n  " + "\n  ".join(offences))


def test_the_scan_reaches_the_file_that_caused_the_outage():
    """A scanner that silently covers nothing passes forever."""
    scanned = {p.relative_to(BACKEND).as_posix() for p in _files()}
    assert "compute/engine/fund_prices.py" in scanned, (
        "the scan does not cover the file that took production down")
    assert len(scanned) > 20, f"only {len(scanned)} files scanned"


def test_the_check_can_actually_fail():
    """Mutation control, against the exact shape that caused the outage."""
    tree = ast.parse(
        "import time\n"
        "async def worker():\n"
        "    for i in range(3):\n"
        "        time.sleep(30)\n")
    assert _blocking_calls_in_coroutines(tree), (
        "the detector does not see a blocking sleep in a coroutine")


def test_a_nested_sync_def_is_allowed():
    """Holding blocking work in a sync function is the REMEDY, not the bug.

    fetch_fund_data still sleeps 30/60/90 on rate limits. That is fine: it is
    synchronous and now reached through asyncio.to_thread, so the sleeping
    happens on a worker thread rather than the loop. A guard that forbade it
    would push people toward deleting the backoff instead of moving it.
    """
    tree = ast.parse(
        "import time\n"
        "async def worker():\n"
        "    def blocking():\n"
        "        time.sleep(30)\n"
        "    await asyncio.to_thread(blocking)\n")
    assert not _blocking_calls_in_coroutines(tree)


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
