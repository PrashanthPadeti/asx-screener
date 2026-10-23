#!/usr/bin/env python
"""
`:param::type` is never substituted, and registers a truncated phantom
=====================================================================
`fetch_announcements` failed every night with

    asyncpg.exceptions.PostgresSyntaxError: syntax error at or near ":"

from `notification_service._log_notification`, which wrote `:meta::jsonb`.

Measured against SQLAlchemy 2.0.36, not reasoned about:

    text("INSERT INTO t (a,b) VALUES (:meta::jsonb, :attempts)")
      binds    -> ['attempts', 'met']
      compiled -> INSERT INTO t (a,b) VALUES (:meta::jsonb, $1)

Two things go wrong at once:

1. **The cast expression is left in the SQL verbatim.** `:attempts`
   became `$1`; `:meta::jsonb` was not substituted at all. Postgres
   received a literal colon and stopped there. That is the reported error.
2. **A truncated phantom parameter is registered.** Not `meta`, and not
   `jsonb` — `met`. The scanner stops one character short of the `::` and
   keeps the shortened name. It is registered as a bind and then never
   rendered, so nothing supplies it and nothing complains.

`:uid::uuid` behaves identically, registering `ui`.

The correct form substitutes cleanly:

    text("... VALUES (CAST(:meta AS jsonb), :attempts)")
      binds    -> ['attempts', 'meta']
      compiled -> ... VALUES (CAST($1 AS jsonb), $2)

The general property, which is what this file actually enforces: **every
bind parameter a statement registers must appear as a `$n` placeholder in
the compiled SQL.** The broken form registers two and renders one. That
holds regardless of what the scanner's regex happens to be, and it catches
any construct that defeats substitution, not only `::`.

Run:  python tests/test_no_bindparam_followed_by_cast.py
      (requires sqlalchemy: /opt/asx-screener/asx-venv/bin/python)
"""

import ast
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app").is_dir() else Path.cwd()

#: A colon-prefixed name immediately followed by a Postgres cast.
BAD = re.compile(r':[a-zA-Z_][a-zA-Z0-9_]*::[a-zA-Z]')

#: An asyncpg positional placeholder in compiled output.
PLACEHOLDER = re.compile(r'\$\d+')

SEARCH_ROOTS = ("app", "compute", "scripts")


def _python_files():
    for root in SEARCH_ROOTS:
        base = BACKEND / root
        if base.is_dir():
            yield from base.rglob("*.py")


def _text_literals():
    """Every `text("...")` string literal in the searched tree, by AST.

    Read out of the source rather than retyped, so these tests exercise
    what ships.
    """
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "text"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                yield path, node.lineno, node.args[0].value


# ── The property: what is registered must be what is rendered ───────────────

def test_every_registered_bind_is_actually_rendered():
    """The real defect, as a property over every text() in the tree.

    `:meta::jsonb` registers `met` and renders nothing. Any construct that
    defeats substitution leaves a literal colon in the SQL for Postgres to
    choke on, so this is the check that would have caught the outage —
    unlike a list of known-bad type names, which `met` would have passed.
    """
    from sqlalchemy.dialects import postgresql

    dialect = postgresql.asyncpg.dialect()
    offenders, checked = [], 0
    for path, lineno, sql in _text_literals():
        from sqlalchemy import text as _text
        stmt = _text(sql)
        registered = set(stmt._bindparams)
        try:
            compiled = str(stmt.compile(dialect=dialect))
        except Exception as exc:                               # noqa: BLE001
            offenders.append(
                f"{path.relative_to(BACKEND)}:{lineno} failed to compile: "
                f"{type(exc).__name__}: {exc}")
            continue
        rendered = set(PLACEHOLDER.findall(compiled))
        checked += 1
        if len(rendered) != len(registered):
            offenders.append(
                f"{path.relative_to(BACKEND)}:{lineno} registers "
                f"{len(registered)} bind(s) {sorted(registered)} but renders "
                f"{len(rendered)} placeholder(s) — a parameter was not "
                f"substituted and its colon reaches Postgres")
    assert not offenders, (
        "bind parameters are registered but not rendered:\n  "
        + "\n  ".join(offenders))
    assert checked >= 20, (
        f"only {checked} text() statements compiled; the AST extraction is "
        f"not reading the population it claims to cover")


def test_the_property_catches_the_statement_that_broke_production():
    """Mutation control, on the exact statement from the traceback.

    If this stops failing, the check above is no longer protecting
    anything and the whole file needs re-reading.
    """
    from sqlalchemy import text as _text
    from sqlalchemy.dialects import postgresql

    broken = _text("INSERT INTO t (a,b) VALUES (:meta::jsonb, :attempts)")
    compiled = str(broken.compile(dialect=postgresql.asyncpg.dialect()))
    registered = set(broken._bindparams)
    rendered = set(PLACEHOLDER.findall(compiled))

    assert len(rendered) < len(registered), (
        f"the broken form now substitutes correctly (registered "
        f"{sorted(registered)}, rendered {sorted(rendered)}). SQLAlchemy's "
        f"behaviour has changed; re-derive the defect before trusting the "
        f"check above.")
    assert ":meta::jsonb" in compiled, (
        "the cast expression is no longer left verbatim in the SQL; the "
        "documented mechanism has changed")


def test_the_phantom_parameter_is_truncated_not_the_type_name():
    """Recorded because the first fix got this wrong.

    I claimed `:meta::jsonb` registered `jsonb` as a second parameter. It
    does not — it registers `met`, one character short. A guard written
    around the wrong story (rejecting SQL type names) would have passed
    the live defect.
    """
    from sqlalchemy import text as _text

    assert set(_text(":meta::jsonb")._bindparams) == {"met"}
    assert set(_text(":uid::uuid")._bindparams) == {"ui"}


def test_the_fixed_form_substitutes_cleanly():
    from sqlalchemy import text as _text
    from sqlalchemy.dialects import postgresql

    fixed = _text(
        "INSERT INTO t (a,b) VALUES (CAST(:meta AS jsonb), :attempts)")
    compiled = str(fixed.compile(dialect=postgresql.asyncpg.dialect()))
    assert set(fixed._bindparams) == {"meta", "attempts"}
    assert "CAST($1 AS jsonb)" in compiled, compiled
    assert ":" not in compiled, f"a colon survived compilation: {compiled}"


# ── The cheap textual guard, kept as a fast tripwire ────────────────────────

def test_no_bind_parameter_is_followed_by_a_double_colon_cast():
    """Subsumed by the property above, but runs without a database or a
    dialect and names the offending line directly."""
    offenders = []
    for path in _python_files():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(source.splitlines(), 1):
            if BAD.search(line):
                offenders.append(
                    f"{path.relative_to(BACKEND)}:{i}  {line.strip()[:80]}")
    assert not offenders, (
        "a bind parameter is followed by `::`, which defeats substitution "
        "and sends a literal colon to Postgres — use CAST(:name AS type):"
        "\n  " + "\n  ".join(offenders))


def test_the_detector_catches_the_shape_it_exists_for():
    assert BAD.search("             :status, :error, :meta::jsonb, :attempts,")
    assert BAD.search("VALUES (:uid, 'x', 'user', :meta::jsonb)")
    assert BAD.search("CAST(:uid AS uuid), :payload::json")


def test_the_detector_does_not_flag_the_correct_form():
    for ok in ("VALUES (CAST(:meta AS jsonb), :attempts)",
               "WHERE user_id = CAST(:uid AS uuid)",
               "SELECT a::text FROM t",          # a cast with no bind param
               "WHERE ts > NOW() - INTERVAL '1 day'"):
        assert not BAD.search(ok), f"false positive on: {ok}"


def test_the_codebase_already_preferred_the_safe_form():
    """The convention existed; the three failures were the exceptions."""
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
