"""A withdrawn field is refused with a reason, everywhere, and offered nowhere.

`beta_1y` was a registered screener filter over a column populated on 0 of
33,864 rows, whose writer carries a TODO rather than an implementation. A
customer could select "Beta (1Y)", get zero results, and have no way to tell
a strict screen from a metric that has never existed.

Deleting the field would have been the obvious fix and the wrong one. A
saved screen naming it would then fail with "unknown field: 'beta_1y'",
which tells the customer they made a mistake. They did not. So the field
stays in the registry, is marked withdrawn with its reason, and every path
that could resolve it refuses with that reason instead.

The contract this file holds:

  * a withdrawn field is neither filterable nor sortable
  * resolving one raises WithdrawnField, not UnknownField -- they are
    different failures with different remedies
  * every route that catches UnknownField catches WithdrawnField FIRST,
    since WithdrawnField would otherwise be reported as a bad request
  * the field catalogue still lists it, marked unavailable with the reason
  * no preset filters on one, because a preset is a screen we ship
"""

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FIELDS = BACKEND / "app" / "core" / "screener_fields.py"
ROUTE = BACKEND / "app" / "api" / "v1" / "routes" / "screener.py"
PARSER = BACKEND / "app" / "core" / "query_parser.py"

EXPECT_WITHDRAWN = {"beta_1y"}


def _module_value(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found at module level in {path.name}")


def withdrawn() -> dict:
    return _module_value(FIELDS, "WITHDRAWN_FIELDS")


# ── The declaration ─────────────────────────────────────────────────────────

def test_the_withdrawn_set_is_what_we_think_it_is():
    assert set(withdrawn()) == EXPECT_WITHDRAWN, (
        f"WITHDRAWN_FIELDS is {sorted(withdrawn())}, expected "
        f"{sorted(EXPECT_WITHDRAWN)}. Adding one is a product decision and "
        f"removing one needs a measurement showing the column is populated.")


def test_every_withdrawal_states_a_reason_a_customer_can_read():
    thin = [k for k, v in withdrawn().items()
            if not v or len(v) < 40 or k in v.split()[0:1]]
    assert not thin, (
        f"{thin} are withdrawn without a usable reason. The reason is shown "
        f"to the customer in place of results, so 'not available' on its own "
        f"is the same silence the withdrawal exists to end.")


def test_a_withdrawn_field_is_still_a_registered_field():
    """Otherwise a saved screen naming it reads as the customer's error."""
    src = ROUTE.read_text(encoding="utf-8")
    missing = [k for k in withdrawn()
               if not re.search(rf'^\s*"{re.escape(k)}":\s*\{{', src,
                                re.MULTILINE)]
    assert not missing, (
        f"{missing} are withdrawn and absent from ALLOWED_FIELDS. A "
        f"withdrawn field must still resolve, or the response becomes "
        f"'unknown field' and blames the customer for our gap.")


# ── The refusal ─────────────────────────────────────────────────────────────

def test_resolve_refuses_a_withdrawn_field_distinctly():
    src = FIELDS.read_text(encoding="utf-8")
    assert "class WithdrawnField" in src, (
        "WithdrawnField does not exist; a withdrawal cannot be told from a "
        "typo")
    body = src[src.index("def resolve("):]
    body = body[:body.index("\ndef ", 1)] if "\ndef " in body[1:] else body
    assert "WithdrawnField" in body, (
        "resolve() does not raise WithdrawnField, so nothing refuses a "
        "withdrawn field by name")
    assert body.index("withdrawn") < body.index("sortable"), (
        "resolve() checks sortability before withdrawal, so a withdrawn "
        "field is reported as 'not sortable' and the reason is buried")


def test_every_unknown_field_handler_handles_withdrawn_first():
    """Order matters: WithdrawnField must not fall through to the 400.

    Both are caught in the same try. If UnknownField were caught first and
    WithdrawnField were a subclass, or if the withdrawn handler were absent,
    the customer would get "bad request" for a field we removed.
    """
    lines = ROUTE.read_text(encoding="utf-8").splitlines()
    unknown_at = [i for i, ln in enumerate(lines)
                  if ln.strip().startswith("except UnknownField")]
    assert unknown_at, "no UnknownField handler found at all"

    unguarded = []
    for i in unknown_at:
        # The withdrawn handler must be the clause immediately before.
        preceding = "\n".join(lines[max(0, i - 8):i])
        if "except WithdrawnField" not in preceding:
            unguarded.append(i + 1)
    assert not unguarded, (
        f"UnknownField is caught at lines {unguarded} with no WithdrawnField "
        f"clause before it. A withdrawn field would be answered 400 bad "
        f"request, which says the customer got the name wrong.")


def test_the_refusal_names_the_field_and_the_reason():
    src = ROUTE.read_text(encoding="utf-8")
    for required in ('"error": "filter_unavailable"', '"field": exc.field',
                     '"reason": exc.reason'):
        assert required in src, (
            f"the withdrawn-field response does not carry {required}. A "
            f"client cannot tell the customer which filter is unavailable "
            f"or why.")


# ── Offered nowhere ─────────────────────────────────────────────────────────

def test_no_preset_filters_on_a_withdrawn_field():
    """A preset is a screen we ship; one that cannot return a row is ours."""
    src = ROUTE.read_text(encoding="utf-8")
    offenders = [k for k in withdrawn()
                 if re.search(rf'"field":\s*"{re.escape(k)}"', src)]
    assert not offenders, (
        f"{offenders} are filtered on by a preset. The preset would answer "
        f"422 for every customer who opened it.")


def test_the_field_catalogue_reports_withdrawal_rather_than_hiding_it():
    src = PARSER.read_text(encoding="utf-8")
    assert "WITHDRAWN_FIELDS" in src, (
        "get_field_reference does not consult WITHDRAWN_FIELDS, so the "
        "catalogue still offers a withdrawn field as though it worked")
    for key in ('"available"', '"unavailable_reason"'):
        assert key in src, (
            f"the catalogue entry has no {key}; a client cannot grey the "
            f"field out or say why")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
