"""A percent sign in SQL text is a bind parameter unless it is doubled
===================================================================
psycopg2 scans the entire query string for percent signs before it reaches
the server. It does not know what a SQL comment is, and -- this is the part
that cost a run -- it does not validate the conversion character. Its parser
does one of three things at each percent sign:

    '%%'      emit a literal percent sign
    '%(x)s'   substitute the named parameter x
    anything  TAKE THE NEXT ITEM FROM THE PARAMETER SEQUENCE

That last branch is unconditional. There is no "unsupported format character"
check, so a stray percent sign in a comment silently consumes a bind
parameter meant for a real placeholder.

On 28 Oct 2026 a comment was added to build_screener_universe's UPSERT_SQL
recording why the multi-year return columns exist. It quoted two figures as
percentages. Those two percent signs consumed both bound company types; the
two genuine placeholders in the WHERE clause then asked for parameters three
and four, and the run died with

    IndexError: list index out of range

That is the lucky outcome. The parameter list happened to be exactly two
items long, so the overrun ran off the end and raised. Had it been two items
longer the query would have RUN -- binding the excluded company types into a
comment, and feeding the wrong two values to the filter that decides which
companies enter the screener. A silent wrong answer, not a crash.

It shipped through a green full-suite gate, a clean deploy and twelve smoke
checks, because nothing in the suite executes that statement. The defect is
textual and sits in a string, so no amount of exercising the surrounding
Python finds it. This file reads the strings.

Scope and strictness
--------------------
The scan covers SQL assigned to a *SQL-named constant and SQL passed as a
literal to .execute()/.executemany(), which is where this project keeps it.
It is deliberately strict: ANY percent sign that is not doubled and not part
of a placeholder fails, including in a comment and including in a query that
currently passes no parameters. A query without parameters is safe today and
one parameter away from not being, and the distinction is not visible here.

The strictness has a known edge. Under asyncpg, which this project also uses,
percent signs are ordinary characters and `LIKE '%x%'` is correct as written
-- doubling it there would be a bug. No such literal exists today (339 were
scanned, 0 flagged besides the defect above). If one is ever written this
suite will fail on it, and the right response is to decide deliberately which
driver that string belongs to, not to double the sign to quiet the test.
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

#: Below this, the collector has lost its population rather than found a clean
#: tree. 339 literals were in scope when this was written; the floor is set
#: well under that so ordinary churn does not trip it, and far above zero so a
#: refactor that moves SQL somewhere this file cannot see fails loudly instead
#: of passing over nothing.
MINIMUM_LITERALS = 200

SQL_NAME = re.compile(r"(?i)sql$")


def _percent_violations(text: str) -> list:
    """Offsets of percent signs psycopg2 would read as a bind parameter.

    Walks left to right the way its parser does, so a doubled sign consumes
    both characters and cannot be miscounted as two separate ones.
    """
    bad, i = [], 0
    while True:
        i = text.find("%", i)
        if i < 0:
            return bad
        nxt = text[i + 1:i + 2]
        if nxt == "%":
            i += 2
        elif nxt == "(":
            close = text.find(")s", i)
            i = close + 2 if close > 0 else i + 1
        elif nxt == "s":
            i += 2
        else:
            bad.append(i)
            i += 1


def _sql_literals() -> list:
    """Every (file, line, label, text) this project would hand to a driver."""
    found = []
    for path in sorted(BACKEND.rglob("*.py")):
        if ".venv" in path.parts or "node_modules" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        rel = path.relative_to(BACKEND)
        for node in ast.walk(tree):
            # SQL parked in a constant and executed elsewhere, usually after
            # .format() -- which is how UPSERT_SQL reaches the cursor.
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (isinstance(target, ast.Name)
                            and SQL_NAME.search(target.id)
                            and isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str)):
                        found.append((rel, node.lineno, target.id,
                                      node.value.value))
            # SQL written at the call site.
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("execute", "executemany")
                    and node.args):
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.append((rel, node.lineno, node.func.attr, arg.value))
                elif isinstance(arg, ast.JoinedStr):
                    # Only the literal segments; an interpolated value is not
                    # scanned by the driver as format text.
                    text = "".join(v.value for v in arg.values
                                   if isinstance(v, ast.Constant)
                                   and isinstance(v.value, str))
                    found.append((rel, node.lineno, f"{node.func.attr} f-string",
                                  text))
    return found


def test_no_sql_literal_contains_an_undoubled_percent_sign():
    """The property itself, over every literal rather than the two that bit."""
    offences = []
    for rel, lineno, label, text in _sql_literals():
        for off in _percent_violations(text):
            line = text[:off].count("\n")
            offences.append(
                f"    {rel}:{lineno} [{label}]\n"
                f"        {text.split(chr(10))[line].strip()[:90]}")
    assert not offences, (
        f"{len(offences)} SQL literal line(s) contain a percent sign that is "
        f"neither doubled nor part of a placeholder. psycopg2 will consume a "
        f"bind parameter at each one -- raising IndexError if it runs off the "
        f"end of the parameter list, and binding the wrong values silently if "
        f"it does not:\n" + "\n".join(offences))


def test_the_collector_still_sees_the_projects_sql():
    """A scan of nothing passes. Prove the population is still there.

    The assertion above cannot distinguish a clean tree from a collector that
    has stopped finding SQL -- after a rename, a move, or a change in how
    queries are built. This is the check that fails in that case.
    """
    literals = _sql_literals()
    assert len(literals) >= MINIMUM_LITERALS, (
        f"collected only {len(literals)} SQL literals, expected at least "
        f"{MINIMUM_LITERALS}. The percent-sign check above is passing over a "
        f"population it can no longer see, which is worse than its absence.")


def test_the_scanner_rejects_what_it_is_meant_to_reject():
    """The scanner is the whole mechanism, so exercise both verdicts directly.

    Without this the suite proves only that the scanner found nothing, which a
    scanner that can find nothing also achieves.
    """
    assert _percent_violations("-- served at +144,900%, which is wrong")
    assert _percent_violations("SELECT 1 -- 90% done")
    assert _percent_violations("a bare % at the end\n")
    assert not _percent_violations("WHERE t ILIKE '%%Placement%%'")
    assert not _percent_violations("WHERE a = %s AND b = %s")
    assert not _percent_violations("WHERE a = %(code)s")
    assert not _percent_violations("no percent signs at all")


def test_the_statement_that_failed_is_clean_now():
    """Name the regression directly, so a revert of the fix is unambiguous."""
    driver = BACKEND / "scripts" / "eodhd" / "v2" / "build_screener_universe.py"
    tree = ast.parse(driver.read_text(encoding="utf-8"), filename=str(driver))
    upserts = [n.value.value for n in ast.walk(tree)
               if isinstance(n, ast.Assign)
               for t in n.targets
               if isinstance(t, ast.Name) and t.id == "UPSERT_SQL"
               and isinstance(n.value, ast.Constant)]
    assert upserts, ("build_screener_universe no longer defines UPSERT_SQL at "
                     "module level; this check is guarding nothing.")
    assert not _percent_violations(upserts[0]), (
        "UPSERT_SQL has an undoubled percent sign again. This is the exact "
        "defect that made run 32 die with IndexError on 28 Oct 2026.")


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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
