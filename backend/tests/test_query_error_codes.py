"""
The API names the error class; the panel heads it. Both halves or neither
=========================================================================
Query Mode answered two unrelated refusals with one heading. ``roe > net
net_margin`` is a typo. ``roe > net_margin`` is a capability this build does
not have -- it parses perfectly, both field names are valid, and the compiler
refuses it because a governed metric can be inapplicable rather than merely
above or below. Both returned 422 with prose, and the panel headed both
"Parse Error" and advised checking the Field Reference for valid field names.

In the second case that advice is actively wrong, and it sent a customer
hunting for a mistake they had not made.

So the raising site names the class and the panel reads the name. The obvious
alternative -- classifying by matching the message prose -- is the defect this
project already has a rule about: a textual matcher tests the wording rather
than the property, and the wording is meant to be improved.

**That makes this a paired contract across two languages**, which is exactly
the shape that drifts. Add a code in Python, forget the map in TypeScript, and
the customer sees the generic "Query Error" heading for a refusal that has a
perfectly good one -- with nothing failing anywhere. No typechecker spans the
two files and no test did either, so this one reads both and holds them in
agreement.

Structural, not textual: the Python constants come from the AST and the
TypeScript keys from the object literal's own syntax, so a constant that is
renamed, computed or moved fails loudly rather than being silently missed by
a regex that still matches something.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_query_error_codes.py
"""

import ast
import re
import sys
from pathlib import Path

BACKEND  = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"
ROUTE    = BACKEND / "app/api/v1/routes/screener.py"
PAGE     = FRONTEND / "app/screener/page.tsx"

sys.path.insert(0, str(BACKEND))


def _python_codes() -> dict:
    """ERROR_* constants as the route defines them, read from the AST."""
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Name)
                    and target.id.startswith("ERROR_")
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)):
                out[target.id] = node.value.value
    return out


def _typescript_codes() -> set:
    """Keys of QUERY_ERROR_PRESENTATION, from the literal's own syntax.

    Depth-aware on purpose. The first ``{`` after the declaration belongs to
    the TYPE ANNOTATION, not the value -- reading it yields the shape's field
    names and none of the codes, which is how this check first ran green on
    the wrong object. And a line-anchored key regex would promote every
    nested ``title:`` to a code the moment somebody reformats the literal
    across lines. Only identifiers at depth 1 are keys.
    """
    src = PAGE.read_text(encoding="utf-8")
    start = src.find("const QUERY_ERROR_PRESENTATION")
    assert start >= 0, (
        "QUERY_ERROR_PRESENTATION is gone from the screener page. The panel "
        "no longer heads errors by class, so this contract is guarding "
        "nothing.")

    assign = re.search(r"=\s*\{", src[start:])
    assert assign, "QUERY_ERROR_PRESENTATION is declared but never assigned"
    body = src[start + assign.end() - 1:]

    keys, depth, token, quote = set(), 0, "", None
    for i, ch in enumerate(body):
        if quote:
            if ch == quote and body[i - 1] != "\\":
                quote = None
            continue
        if ch in "'\"`":
            quote, token = ch, ""
            continue
        if ch == "{":
            depth += 1
            token = ""
        elif ch == "}":
            depth -= 1
            token = ""
            if depth == 0:
                return keys
        elif ch == ":" and depth == 1 and token:
            keys.add(token)
            token = ""
        elif ch.isalnum() or ch == "_":
            token += ch
        else:
            token = ""
    raise AssertionError("unbalanced braces in QUERY_ERROR_PRESENTATION")


def _raise_sites() -> list:
    """Every HTTPException whose detail is built by _query_error."""
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    sites = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_query_error"):
            continue
        if node.args and isinstance(node.args[0], ast.Name):
            sites.append((node.lineno, node.args[0].id))
        else:
            sites.append((node.lineno, None))
    return sites


def test_the_route_still_defines_error_codes():
    codes = _python_codes()
    assert codes, "the route defines no ERROR_* codes; the panel has nothing to read"
    assert "ERROR_PARSE" in codes and "ERROR_COMPARISON_UNSUPPORTED" in codes, \
        f"the two classes that prompted this are gone: {sorted(codes)}"


def test_every_code_the_api_can_send_has_a_heading():
    """The drift direction that actually happens.

    A new refusal is added in Python with a new code, and the panel -- a
    different file, a different language, no shared type -- falls through to
    the generic heading. Nothing fails; the customer simply gets a worse
    message than the one that was written for them.
    """
    missing = sorted(set(_python_codes().values()) - _typescript_codes())
    assert not missing, (
        f"these error codes are sent by the API and unknown to the screener "
        f"panel, so they render under the generic heading: {missing}. Add "
        f"them to QUERY_ERROR_PRESENTATION in app/screener/page.tsx.")


def test_every_heading_corresponds_to_a_real_code():
    """The other direction: a heading for a code nothing sends is dead
    weight that reads like coverage."""
    orphans = sorted(_typescript_codes() - set(_python_codes().values()))
    assert not orphans, (
        f"the panel heads these codes but the API never sends them: "
        f"{orphans}. Either a code was renamed in Python or these are dead.")


def test_no_raise_site_passes_a_literal_code():
    """A string typed at the call site is outside the contract above.

    `_query_error("comparison_unsuported", exc)` -- a typo -- would pass
    every test here if literals were allowed, because the constants would
    still agree with the panel while the wire carried something else.
    """
    literals = [line for line, name in _raise_sites() if name is None]
    assert not literals, (
        f"_query_error is called with a non-constant code at line(s) "
        f"{literals}. Use an ERROR_* constant so the cross-language check "
        f"above actually covers it.")


def test_the_raise_sites_are_still_there():
    """Population control. Three sites when written: two parse refusals and
    the comparison refusal, plus the planner's. If they vanish the checks
    above pass over nothing."""
    sites = _raise_sites()
    assert len(sites) >= 4, (
        f"only {len(sites)} structured-error raise sites found. Query Mode, "
        f"AI Query and the planner each have one; fewer means a path went "
        f"back to raising bare prose.")
    used = {name for _, name in sites if name}
    assert used == set(_python_codes()), (
        f"declared codes {sorted(_python_codes())} but only {sorted(used)} "
        f"are raised anywhere — an unraisable code is not a contract.")


def test_the_detail_body_carries_both_halves():
    """The shape the frontend destructures. A dict missing `message` renders
    as an object, and React throws on an object child — a blank page where a
    handled 422 should be."""
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_query_error"),
              None)
    assert fn is not None, "_query_error is gone"
    returned = next((n.value for n in ast.walk(fn)
                     if isinstance(n, ast.Return)), None)
    assert isinstance(returned, ast.Dict), "_query_error must return a dict"
    keys = {k.value for k in returned.keys if isinstance(k, ast.Constant)}
    assert keys == {"code", "message"}, (
        f"the 422 body must carry exactly code and message, got {sorted(keys)}")


def test_the_frontend_normalises_before_rendering():
    """AI Query shares these raise sites and shows `detail` as text.

    Assigning an object to that state and rendering it throws, turning a
    handled refusal into a blank page. Both callers must go through the
    normaliser rather than reaching into response.data.detail themselves.
    """
    src = PAGE.read_text(encoding="utf-8")
    assert "function toQueryError" in src, "the normaliser is gone"
    direct = re.findall(r"data\?\.detail", src)
    assert len(direct) <= 1, (
        f"{len(direct)} call sites reach into response.data.detail directly; "
        f"only toQueryError may. A caller that assigns that object to string "
        f"state and renders it throws on an object child.")


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
        except Exception as e:                                 # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
