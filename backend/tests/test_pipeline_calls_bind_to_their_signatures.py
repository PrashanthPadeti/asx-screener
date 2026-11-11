"""Every call in the daily pipeline must bind to the signature it names.

On 10 Nov 2026 the canonical driver failed. The pipeline's error handler then
failed too, on this:

    tracker.finish_step(5, success=False, error=...)
    TypeError: finish_step() got an unexpected keyword argument 'error'

The parameter is `error_msg`. The four older call sites pass `error_msg`; the
two added when the canonical driver was wrapped pass `error`. Both of those
two are reached ONLY when something has already gone wrong, so in the weeks
since they were written neither had ever executed, and nothing noticed.

The cost is not the TypeError. It is that the handler reporting a failure
destroyed the report: the run's step row was never marked failed, the
pipeline raised out of a context manager with a different exception than the
one that mattered, and the operator reading the log sees a traceback about a
keyword argument instead of the database error that caused it. A failure path
that fails replaces a diagnosis with a distraction.

This is the standing rule in its plainest form: a gate has two outcomes, and
only one of them is ever exercised by a passing system. The refusing path,
the error path, the "this should never happen" path -- those run on the worst
day, which is the day they must not be broken.

Python cannot catch this at import: the call is inside a function, and the
name resolves at runtime. But the property is syntactic. Every call here
names a method defined in this same file, with literal arguments, so each
one can be bound against the real signature without running anything.

So: parse the module, build each method's true signature from its def, and
bind every matching call site to it. Calls that splat (*args / **kwargs)
cannot be checked statically and are reported as unchecked rather than
silently passed, so the number cannot drift upward unobserved.

Matching is by attribute name, so calls on imported modules are excluded:
`psycopg2.connect(url)` is not `PipelineTracker.connect(self)`, and the
first version of this guard reported both as defects. Imported names are
read from the module's own import statements rather than guessed.
"""

import ast
import inspect
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

MODULES = (
    BACKEND / "scripts" / "eodhd" / "v2" / "jobs" / "daily_pipeline.py",
)

#: Methods that MUST be found and checked. These are the lifecycle calls that
#: record a run's outcome; if a refactor renames one, this guard must fail
#: rather than check nothing.
REQUIRED_METHODS = {"finish_step", "finish_pipeline", "start_step"}

#: Call sites expected at minimum. A guard that silently matches zero calls
#: passes forever.
MIN_CALLS = 6


def _signature_of(fn: ast.FunctionDef) -> inspect.Signature:
    """An inspect.Signature built from a def, without importing it."""
    a = fn.args
    params = []

    def add(names, kind, defaults, offset=0):
        n_req = len(names) - len(defaults)
        for i, arg in enumerate(names):
            if arg.arg == "self":
                continue
            default = (inspect.Parameter.empty if i < n_req
                       else "<default>")
            params.append(inspect.Parameter(arg.arg, kind, default=default))

    add(a.posonlyargs, inspect.Parameter.POSITIONAL_ONLY, [])
    add(a.args, inspect.Parameter.POSITIONAL_OR_KEYWORD, a.defaults)
    if a.vararg:
        params.append(inspect.Parameter(a.vararg.arg,
                                        inspect.Parameter.VAR_POSITIONAL))
    kw_defaults = [d for d in a.kw_defaults if d is not None]
    add(a.kwonlyargs, inspect.Parameter.KEYWORD_ONLY, kw_defaults)
    if a.kwarg:
        params.append(inspect.Parameter(a.kwarg.arg,
                                        inspect.Parameter.VAR_KEYWORD))
    return inspect.Signature(params)


def _methods(tree: ast.AST) -> dict[str, inspect.Signature]:
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[item.name] = _signature_of(item)
    return out


def _imported_names(tree: ast.AST) -> set[str]:
    """Names bound by import statements, which are never our own objects."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _check_module(path: Path) -> tuple[list[str], list[str], int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sigs = _methods(tree)
    imported = _imported_names(tree)

    failures, unchecked, n_checked = [], [], 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        name = node.func.attr
        if name not in sigs:
            continue
        # psycopg2.connect is not PipelineTracker.connect.
        recv = node.func.value
        if isinstance(recv, ast.Name) and recv.id in imported:
            continue

        where = f"{path.name}:{node.lineno} {name}(...)"
        if any(isinstance(arg, ast.Starred) for arg in node.args) or \
           any(kw.arg is None for kw in node.keywords):
            unchecked.append(where)
            continue

        n_checked += 1
        try:
            sigs[name].bind(*[object()] * len(node.args),
                            **{kw.arg: object() for kw in node.keywords})
        except TypeError as exc:
            failures.append(f"{where} -- {exc}")

    return failures, unchecked, n_checked


def test_every_call_binds_to_its_definition():
    failures, unchecked, total = [], [], 0
    for path in MODULES:
        assert path.exists(), f"{path} is gone; MODULES is stale"
        f, u, n = _check_module(path)
        failures += f
        unchecked += u
        total += n

    assert total >= MIN_CALLS, (
        f"only {total} call sites were checked, expected at least "
        f"{MIN_CALLS}. Either the module shrank or the matching broke; "
        f"either way this guard is no longer watching what it claims to.")

    assert not failures, (
        "these calls would raise TypeError the moment they are reached:\n  "
        + "\n  ".join(failures)
        + "\n\nEvery one of them is on a path that only runs when something "
          "has already failed, which is why nothing caught it.")

    assert not unchecked, (
        f"{unchecked} splat their arguments and cannot be bound statically. "
        f"That is allowed, but it must be a deliberate addition to this "
        f"list, not a silent reduction in coverage.")


def test_the_lifecycle_methods_are_still_the_ones_being_checked():
    """The watched methods must still exist under these names."""
    for path in MODULES:
        sigs = _methods(ast.parse(path.read_text(encoding="utf-8")))
        missing = sorted(REQUIRED_METHODS - set(sigs))
        assert not missing, (
            f"{missing} are no longer methods in {path.name}. If they were "
            f"renamed, rename them here too; if they were removed, say so "
            f"deliberately. Leaving this list stale turns the guard above "
            f"into a check of whatever happens to remain.")


def test_error_reporting_parameters_are_named_consistently():
    """One name for the failure message, across every lifecycle method.

    The defect was possible because a reader had to remember which of
    `error` and `error_msg` this particular method took. Two names for one
    idea in one class is the condition that produced the bug, so it is the
    condition worth forbidding.
    """
    for path in MODULES:
        sigs = _methods(ast.parse(path.read_text(encoding="utf-8")))
        offenders = sorted(
            name for name, sig in sigs.items()
            if "error" in sig.parameters)
        assert not offenders, (
            f"{offenders} take a parameter named 'error'. The established "
            f"name in this module is 'error_msg'; two spellings for the "
            f"same argument is what produced the 10 Nov 2026 failure.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:                         # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
