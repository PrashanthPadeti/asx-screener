#!/usr/bin/env python
"""
Every preference column a worker reads must be one that exists
==============================================================
Two workers selected `np.email_enabled`:

    anomaly_alert_worker.py   COALESCE(np.email_enabled, TRUE)
    watchlist_digest_worker.py  COALESCE(np.email_enabled, TRUE)

`users.notification_preferences` has no such column and never has. Both
queries raised `UndefinedColumn` on every run, so the watchlist digest
never sent -- nightly, since the column was first referenced.

The table's real flags are per notification type: `alerts_email`,
`announcements_email`, `portfolio_weekly_email`, `portfolio_threshold_email`
and their SMS counterparts. There is no global switch, which is why
inventing one silently produced a column name that reads perfectly and
cannot work.

Why nothing caught it
---------------------
The same reason as the `:meta::jsonb` outage in this release: no test
executes these statements. The workers that DO work (`portfolio_worker`,
`announcement_worker`) use real columns, so the table was never wrong --
only these two readers were, and nothing compared readers against the
table.

What this checks
----------------
The authoritative column set is derived from the INSERT in
`app/api/v1/routes/notifications.py`, which demonstrably executes against
the live table -- not retyped here, and not taken from the Pydantic model,
which is the API's view of the data rather than the database's.

Every `np.<column>` reference in any worker or route is then checked
against that set. A column that does not exist fails with its location.

Run:  python tests/test_notification_preference_columns.py
"""

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app").is_dir() else Path.cwd()

PREFS_ROUTE = BACKEND / "app" / "api" / "v1" / "routes" / "notifications.py"

#: Columns the table has that the INSERT does not name (keys and bookkeeping).
STRUCTURAL = {"user_id", "id", "created_at", "updated_at"}

#: `np.<name>` as an alias-qualified column reference in SQL.
NP_REF = re.compile(r'\bnp\.([a-z_][a-z0-9_]*)', re.IGNORECASE)


def real_columns() -> set:
    """The column list from the INSERT that writes this table."""
    src = PREFS_ROUTE.read_text(encoding="utf-8")
    start = src.index("INSERT INTO users.notification_preferences (")
    block = src[start:src.index(") VALUES", start)]
    block = block[block.index("(") + 1:]
    cols = {c.strip() for c in block.replace("\n", " ").split(",")}
    cols = {c for c in cols if re.fullmatch(r"[a-z_][a-z0-9_]*", c)}
    return cols | STRUCTURAL


def _sql_literals():
    """Every `text("...")` literal under app/, by AST.

    Scoped to SQL deliberately. The first version of this test scanned raw
    source lines for `np.<name>` and reported seven failures in
    `predictions.py`, where `np` is numpy -- a matcher reading Python as
    SQL. The alias is resolved from each statement rather than assumed, so
    a query that aliases the table `prefs` is checked too.
    """
    import ast
    base = BACKEND / "app"
    for path in base.rglob("*.py"):
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


#: `notification_preferences <alias>` — the alias the statement gives it.
ALIAS = re.compile(
    r'users\.notification_preferences\s+(?:AS\s+)?([a-z_][a-z0-9_]*)',
    re.IGNORECASE)


def test_the_column_set_was_actually_extracted():
    """A population check. If the INSERT moves or is reworded, this test
    must fail loudly rather than validate every reference against an empty
    set and pass."""
    cols = real_columns()
    assert len(cols) >= 12, (
        f"only {len(cols)} columns extracted from the INSERT: {sorted(cols)}. "
        f"The extraction has lost its source; every reference below would "
        f"pass against an empty set.")
    for expected in ("alerts_email", "announcements_email",
                     "portfolio_weekly_email", "portfolio_threshold_email"):
        assert expected in cols, f"{expected} missing from the extracted set"


def test_every_preference_column_reference_exists():
    cols = real_columns()
    offenders, statements = [], 0
    for path, lineno, sql in _sql_literals():
        aliases = {a.lower() for a in ALIAS.findall(sql)}
        if not aliases:
            continue
        statements += 1
        stripped = "\n".join(ln for ln in sql.splitlines()
                             if not ln.strip().startswith("--"))
        for alias in aliases:
            ref = re.compile(rf'\b{alias}\.([a-z_][a-z0-9_]*)', re.IGNORECASE)
            for col in ref.findall(stripped):
                if col.lower() not in cols:
                    offenders.append(
                        f"{path.relative_to(BACKEND)}:{lineno} reads "
                        f"{alias}.{col} — users.notification_preferences "
                        f"has no such column")
    assert statements >= 3, (
        f"only {statements} statements join users.notification_preferences; "
        f"the extraction is not finding the queries it claims to check")
    assert not offenders, (
        "a worker reads a preference column that does not exist; the query "
        "raises UndefinedColumn and the notification silently never "
        "sends:\n  " + "\n  ".join(offenders)
        + "\n\n  Real columns: " + ", ".join(sorted(cols)))


def test_the_detector_would_have_caught_the_defect():
    """Mutation control, on the exact reference that was shipping."""
    cols = real_columns()
    assert "email_enabled" not in cols, (
        "a global email_enabled column now exists. If it was added "
        "deliberately, the per-type mapping in the two workers should be "
        "revisited; this test no longer describes the system.")
    assert NP_REF.findall("COALESCE(np.email_enabled, TRUE) = TRUE") == [
        "email_enabled"]


def test_each_worker_uses_the_flag_for_its_own_notification_type():
    """The mapping chosen when this was fixed, pinned so a later edit that
    quietly reaches for a different flag has to say so here.

    The watchlist digest's use of portfolio_weekly_email is a REUSE: there
    is no watchlist-specific preference, so turning off the weekly
    portfolio summary also turns off the digest. Recorded because it is a
    product behaviour nobody chose explicitly.
    """
    expected = {
        "anomaly_alert_worker.py":   "alerts_email",
        "watchlist_digest_worker.py": "portfolio_weekly_email",
    }
    for filename, flag in expected.items():
        path = BACKEND / "app" / "workers" / filename
        assert path.is_file(), f"missing: {path}"
        body = "\n".join(
            ln for ln in path.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith(("#", "--")))
        refs = {c.lower() for c in NP_REF.findall(body)}
        assert flag in refs, (
            f"{filename} no longer gates on np.{flag}; it references "
            f"{sorted(refs)}. If the mapping changed deliberately, update "
            f"this test and say which flag now governs it.")


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
