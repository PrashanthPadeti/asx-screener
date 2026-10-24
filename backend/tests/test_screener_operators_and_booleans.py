#!/usr/bin/env python
"""
The screener's operators and boolean filters
============================================
Three defects, all reaching customers as 500s on `/api/v1/screener`, found
in the same log that produced a refund request:

    4  syntax error at or near "neq"
    3  invalid input for query argument $1: 'true' (a boolean is required
       (got type str))

**neq.** The API's `FilterOperator` enum says `neq`; the compiler's
`OPERATORS` map said only `ne`. Two vocabularies for one concept, neither
aware of the other. Every "≠" filter a customer built reached Postgres as
the literal word `neq`.

**The fallback.** It got there through
`OPERATORS.get(node.operator) or node.operator`, which hands any
unrecognised string to the database — defeating, in one expression, the
closed set the comment directly above it promises ("a screen cannot inject
an operator, and an unknown one is a definition error rather than something
that reaches the database").

**Booleans.** `Criterion.kind` defaults to `"number"` and the API never
sets it, so the boolean branch was unreachable for every filter a customer
built. `is_reit` fell through to the numeric path and bound the string
`"true"` to a boolean column. `bool("false")` is also True, so even had it
bound, "is REIT: No" would have meant "Yes".

And a fourth, found while fixing these: the UI offered
`{"value": "in", "label": "in list"}` for text fields, and `in` has never
been in `OPERATORS`. v11.2.29 turned the 500 into a 400 naming the problem
-- an honest refusal of a filter the UI still invited customers to pick.
v11.2.36 withdrew the option: an operator that cannot run is worse offered
than absent, because the attempt is how the customer finds out. The
compiler still refuses `in`, because a saved screen or a stale client can
send one long after the UI stopped offering it.

Run:  python tests/test_screener_operators_and_booleans.py
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "compute" / "engine").is_dir() else Path.cwd()
sys.path.insert(0, str(BACKEND))

from compute.engine.screen_sql import (                        # noqa: E402
    OPERATORS, UnknownOperator, _as_bool, _sql_operator)

SRC = (BACKEND / "compute" / "engine" / "screen_sql.py").read_text(
    encoding="utf-8")


# ── The two vocabularies must agree ─────────────────────────────────────────

def test_every_operator_the_ui_offers_compiles():
    """Derived from what the UI actually renders, not a list retyped here.

    This is the root cause: the API offered an operator the compiler had
    never heard of, and nothing compared the two. A filter a customer can
    SELECT must be one the compiler can BUILD.
    """
    import re
    routes = (BACKEND / "app" / "api" / "v1" / "routes"
              / "screener.py").read_text(encoding="utf-8")
    block = routes[routes.index('"operators": {'):]
    block = block[:block.index("total_fields")]
    offered = set(re.findall(r'\{"value":\s*"(\w+)"', block))
    assert offered, "could not read the operator list the UI is served"

    unsupported = sorted(offered - set(OPERATORS))
    assert unsupported == [], (
        f"the UI offers operators the compiler cannot build: {unsupported}. "
        f"Each one is a filter a customer can select and the system cannot "
        f"run. Either implement it in OPERATORS or withdraw the option; "
        f"`in list` was withdrawn in v11.2.36 for exactly this reason.")


def test_every_operator_query_mode_can_emit_compiles():
    """The regression v11.2.29 shipped, as a population check.

    Query Mode's parser maps the documented symbols to SQL in `_OP_SQL`
    and hands the RESULT to this compiler. Before v11.2.29 the compiler
    had `OPERATORS.get(op) or op`, so `>` was forwarded verbatim and
    worked by accident. Removing that fallback fixed `neq` reaching
    Postgres as a word and simultaneously refused every symbol, so
    `return_1y > 0` -- the syntax the UI's own hint bar, error messages
    and Field Reference panel all advertise -- failed to parse. A Premium
    feature went dark.

    Derived from _OP_SQL by AST rather than retyped here: a list copied
    into a test is a list that drifts from the thing it is meant to
    protect, which is the fault being guarded against.
    """
    import ast
    src = (BACKEND / "app" / "core" / "query_parser.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    emitted = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.AnnAssign)
                and getattr(node.target, "id", None) == "_OP_SQL"
                and isinstance(node.value, ast.Dict)):
            emitted = {k.value for k in node.value.keys
                       if isinstance(k, ast.Constant)}
        elif (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "_OP_SQL" for t in node.targets)
                and isinstance(node.value, ast.Dict)):
            emitted = {k.value for k in node.value.keys
                       if isinstance(k, ast.Constant)}
    assert emitted, "could not read _OP_SQL from query_parser.py"
    assert ">" in emitted, "the parser no longer emits '>'; re-read this test"

    # The parser emits the VALUES of _OP_SQL, not its keys -- the keys are
    # what a customer types. Both must compile: the keys because an operator
    # may arrive unmapped from a saved query, the values because that is what
    # the compiler is actually handed.
    values = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and any(
                isinstance(k, ast.Constant) and k.value == ">"
                for k in node.keys):
            values = {v.value for v in node.values
                      if isinstance(v, ast.Constant)}
            break

    unsupported = sorted((emitted | values) - set(OPERATORS))
    assert unsupported == [], (
        f"Query Mode can emit operators the compiler refuses: {unsupported}. "
        f"Every one is a Parse Error on a query written in the documented "
        f"syntax.")


def test_in_is_still_unimplemented_and_refuses_cleanly():
    """`in` has never been implemented, and is no longer offered.

    v11.2.36 withdrew `{"value": "in", "label": "in list"}` from the text
    operators: an option a customer can select and the system cannot run is
    worse than an absent one, because the attempt is how they find out.

    Kept as a test because the compiler must still REFUSE it rather than
    forward it -- a filter can arrive from a saved screen, a stale client or
    a hand-written request long after the UI stopped offering it. Turns red
    if `in` is ever implemented, which is the signal to re-offer it.
    """
    try:
        _sql_operator("in")
    except UnknownOperator as exc:
        assert "not a permitted operator" in str(exc)
        return
    raise AssertionError(
        "`in` now compiles — implement it properly, then re-add "
        "{\"value\": \"in\", \"label\": \"in list\"} to the text "
        "operators and update this test")


def test_neq_and_ne_mean_the_same_thing():
    assert _sql_operator("neq") == _sql_operator("ne") == "<>"


# ── No operator may reach the database unrecognised ─────────────────────────

def test_an_unknown_operator_is_refused_not_forwarded():
    """The fallback let any string through, which is how `neq` became SQL.

    Includes the spellings a client might plausibly send and one that is
    outright hostile: none of them may come back as something to put in a
    query.
    """
    # "=" and "<>" were in this list until v11.2.36 and are now PERMITTED:
    # they are Query Mode's documented syntax, and refusing them is what
    # broke that feature. The property under test is unchanged -- an
    # operator outside the closed set is refused rather than forwarded --
    # only the set is now honest about both vocabularies. Everything below
    # is still outside it, including the two that would be an injection.
    for bogus in ("neqq", "NEQ", "=>", "=<", "==", "like", "between", "",
                  "1=1", "; DROP TABLE universe --", ">>", "'"):
        try:
            compiled = _sql_operator(bogus)
        except UnknownOperator:
            continue
        raise AssertionError(
            f"{bogus!r} was accepted and compiled to {compiled!r} — an "
            f"unrecognised operator reached the SQL builder")


def test_the_fallback_is_gone():
    assert "or node.operator" not in SRC, (
        "the fallback is back: an unrecognised operator would reach the "
        "database verbatim")
    assert "_sql_operator(node.operator)" in SRC


def test_a_refusal_names_the_operator_and_the_permitted_set():
    try:
        _sql_operator("; DROP TABLE universe --")
    except UnknownOperator as exc:
        assert "not a permitted operator" in str(exc)
        for known in ("gte", "neq", "lt"):
            assert known in str(exc), "the refusal does not say what IS allowed"
        return
    raise AssertionError("an arbitrary string was accepted as an operator")


# ── Booleans ────────────────────────────────────────────────────────────────

def test_a_string_true_is_true_and_a_string_false_is_false():
    """`ScreenerFilter.value` is typed `Any`, so the UI sends "true".

    `bool("false")` is True, which would have made "is REIT: No" return the
    REITs.
    """
    for yes in (True, "true", "True", " TRUE ", "yes", "1", 1):
        assert _as_bool(yes) is True, f"{yes!r} should be true"
    for no in (False, "false", "False", "no", "0", 0, "", None):
        assert _as_bool(no) is False, f"{no!r} should be false"


def test_the_definition_decides_what_is_boolean_not_the_criterion():
    """Criterion.kind defaults to "number" and the API never sets it, so
    keying the branch off the criterion made it unreachable. The field
    definition already knows — `_scaled` keys off definition.type for
    exactly this reason."""
    assert 'definition.type == "boolean" or node.kind == "boolean"' in SRC, (
        "the boolean branch keys off the criterion's claim rather than the "
        "column's own type, so a boolean filter from the API binds a string")


def test_the_api_never_sets_kind_which_is_why_this_matters():
    """The premise, asserted so the fix's justification cannot rot.

    If the route starts passing kind, this test fails and the comment
    explaining the fix needs revisiting.
    """
    routes = (BACKEND / "app" / "api" / "v1" / "routes"
              / "screener.py").read_text(encoding="utf-8")
    call = routes[routes.index("TypedCriterion(f.field.lower()"):][:200]
    assert "kind=" not in call, (
        "the route now sets kind; the definition-based branch is still "
        "correct but this test's reasoning should be re-read")


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
