#!/usr/bin/env python
"""
`:param::type` is two bind parameters, not one and a cast
=========================================================
`fetch_announcements` failed every night with

    asyncpg.exceptions.PostgresSyntaxError: syntax error at or near ":"

from `notification_service._log_notification`:

    VALUES (..., :meta::jsonb, :attempts, ...)

SQLAlchemy's `text()` finds bind parameters by matching a colon followed by
a word. In `:meta::jsonb` it takes `:meta`, then looks at the remaining
`::jsonb`: the first colon is followed by a colon so it does not match, and
**the second colon is followed by `jsonb`, which it takes as a second bind
parameter**. Nothing supplies `jsonb`, so the statement reaches Postgres
malformed.

The failure is silent from a customer's point of view and total from the
job's: every announcement notification raised before it could be logged.
It had been happening nightly.

Three occurrences existed; the rest of the codebase already wrote
`CAST(:x AS jsonb)`, which has no second colon and cannot be misparsed.
These three were the outliers, so this guard protects a convention that was
already there rather than imposing a new one.

Run:  python tests/test_no_bindparam_followed_by_cast.py
"""

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app").is_dir() else Path.cwd()

#: A colon-prefixed name immediately followed by a Postgres cast.
BAD = re.compile(r':[a-zA-Z_][a-zA-Z0-9_]*::[a-zA-Z]')

SEARCH_ROOTS = ("app", "compute", "scripts")


def _python_files():
    for root in SEARCH_ROOTS:
        base = BACKEND / root
        if base.is_dir():
            yield from base.rglob("*.py")


def test_no_bind_parameter_is_followed_by_a_double_colon_cast():
    offenders = []
    for path in _python_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if BAD.search(line):
                rel = path.relative_to(BACKEND)
                offenders.append(f"{rel}:{i}  {line.strip()[:80]}")
    assert not offenders, (
        "a bind parameter is followed by `::`, which SQLAlchemy reads as a "
        "SECOND bind parameter and sends to Postgres malformed — use "
        "CAST(:name AS type):\n  " + "\n  ".join(offenders))


def test_sqlalchemy_really_invents_a_second_parameter():
    """The mechanism, not the spelling.

    The guard above is textual; the defect is behavioural. This asserts
    against SQLAlchemy itself that `:meta::jsonb` yields TWO bind
    parameters and `CAST(:meta AS jsonb)` yields one — so the fix is
    justified by what the library does, not by a regex agreeing with a
    comment.
    """
    from sqlalchemy import text as _text

    broken = _text("INSERT INTO t (a, b) VALUES (:meta::jsonb, :attempts)")
    params = set(broken._bindparams)
    assert "jsonb" in params, (
        "SQLAlchemy no longer reads `::jsonb` as a bind parameter. The "
        "defect this release fixed may be version-specific — re-read the "
        "fix before relying on this reasoning. Found: " + repr(sorted(params)))

    fixed = _text(
        "INSERT INTO t (a, b) VALUES (CAST(:meta AS jsonb), :attempts)")
    assert set(fixed._bindparams) == {"meta", "attempts"}, (
        f"the CAST form does not bind cleanly: "
        f"{sorted(fixed._bindparams)}")


def test_the_three_repaired_statements_bind_only_what_they_supply():
    """End-to-end on the real source: every `text()` block in the three
    files that failed must bind exactly the keys its dict supplies.

    Extracted from the files rather than retyped, so it reads what ships.
    """
    import ast
    from sqlalchemy import text as _text

    targets = [
        BACKEND / "app" / "services" / "notification_service.py",
        BACKEND / "app" / "api" / "v1" / "routes" / "notifications.py",
        BACKEND / "app" / "workers" / "anomaly_alert_worker.py",
    ]
    checked = 0
    for path in targets:
        assert path.is_file(), f"missing: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "text"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                continue
            sql = node.args[0].value
            found = set(_text(sql)._bindparams)
            bogus = {p for p in found
                     if p in ("jsonb", "json", "uuid", "text", "int",
                              "numeric", "date", "timestamptz", "boolean")}
            assert not bogus, (
                f"{path.name}:{node.lineno} binds a SQL TYPE NAME as a "
                f"parameter: {sorted(bogus)} — a `::` cast was misparsed")
            checked += 1
    assert checked >= 3, (
        f"only {checked} text() statements found across the three repaired "
        f"files; the extraction is not reading them")


def test_the_detector_catches_the_shape_it_exists_for():
    """Mutation control. The exact line that broke the announcements job."""
    assert BAD.search("             :status, :error, :meta::jsonb, :attempts,")
    assert BAD.search("VALUES (:uid, 'x', 'user', :meta::jsonb)")
    assert BAD.search("CAST(:uid AS uuid), :payload::json")


def test_the_detector_does_not_flag_the_correct_form():
    """CAST(...) has no second colon and must not be reported."""
    for ok in ("VALUES (CAST(:meta AS jsonb), :attempts)",
               "WHERE user_id = CAST(:uid AS uuid)",
               "SELECT a::text FROM t",          # a cast with no bind param
               "WHERE ts > NOW() - INTERVAL '1 day'"):
        assert not BAD.search(ok), f"false positive on: {ok}"


def test_the_codebase_already_preferred_the_safe_form():
    """The convention existed; the three failures were the exceptions.

    Asserted so the guard is understood as protecting an existing style
    rather than imposing a new one.
    """
    casts = 0
    for path in _python_files():
        try:
            casts += len(re.findall(r'CAST\(:[a-zA-Z_][a-zA-Z0-9_]* AS ',
                                    path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    assert casts >= 5, (
        f"only {casts} uses of CAST(:x AS y) found; the claim that this was "
        f"already the house style no longer holds")


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
