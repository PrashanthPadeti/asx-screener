#!/usr/bin/env python
"""
A script may open one event loop, not several
=============================================
`asyncio.run()` creates a loop, runs a coroutine, and CLOSES the loop. The
SQLAlchemy engine is module-level and its pool keeps the connections it
opened, bound to the loop that opened them. A second `asyncio.run()` in the
same process therefore hands the pool's existing connections to a loop that
did not create them:

    RuntimeError: got Future <Future pending> attached to a different loop

This has now happened twice, in two scripts, three commits apart:

    reconcile_contaminated_indices.py   died on the SECOND index
    repair_contaminated_index_history.py  died at the first write, after
                                        printing "APPLYING to 796 rows"

The second one is why this exists. Fixing the first instance and not the
class left a script that read its plan under one loop and wrote under
another -- and it failed at the point of writing to production history. It
failed safely, before any UPDATE executed, which was luck rather than
design.

Structural, not textual. The first attempt to count these with grep
reported two calls in a file that has one, because the other sits in a
docstring explaining this very bug. A text matcher reads its own
explanation.
"""

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if not (BACKEND / "scripts").is_dir():
    BACKEND = Path.cwd()

SCRIPTS = sorted((BACKEND / "scripts").glob("*.py"))


def _asyncio_run_calls(tree: ast.AST) -> list[int]:
    """Line numbers of real asyncio.run() calls — AST nodes, not matches."""
    out = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "run"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "asyncio"):
            out.append(n.lineno)
    return out


def test_no_script_opens_more_than_one_event_loop():
    assert SCRIPTS, f"no scripts found under {BACKEND / 'scripts'}"
    offenders = []
    for path in SCRIPTS:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            offenders.append(f"{path.name}: will not parse — {exc}")
            continue
        lines = _asyncio_run_calls(tree)
        if len(lines) > 1:
            offenders.append(f"{path.name}: {len(lines)} asyncio.run() calls "
                             f"at lines {lines}")
    assert not offenders, (
        "a second asyncio.run() hands the connection pool to a loop that did "
        "not open its connections, and the failure lands wherever the second "
        "loop first touches the database:\n  " + "\n  ".join(offenders))


def test_the_detector_reads_the_ast_not_the_text():
    """Mutation control, and the reason this is not a grep.

    Counting these textually reported two calls in a file containing one,
    because the second sits in a docstring describing the bug.
    """
    src = ('import asyncio\n'
           'def f():\n'
           '    """A docstring mentioning asyncio.run() twice: asyncio.run()."""\n'
           '    return asyncio.run(g())\n')
    assert src.count("asyncio.run(") == 3, "fixture no longer has the decoys"
    assert len(_asyncio_run_calls(ast.parse(src))) == 1, (
        "the detector is counting text, so it would both miss real calls "
        "and flag prose")


def test_the_detector_catches_two_real_calls():
    src = ('import asyncio\n'
           'asyncio.run(a())\n'
           'asyncio.run(b())\n')
    assert len(_asyncio_run_calls(ast.parse(src))) == 2, (
        "the detector cannot see the defect it exists to prevent")


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
