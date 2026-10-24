#!/usr/bin/env python
"""
Search must not 500 because a flag is unknown
=============================================
`/api/v1/companies/search` failed 136 times — the most frequent error on
the site, more than eight times the premium-gate bug that prompted a refund
request. Nobody reported it.

Measured 23 Oct 2026 across 2,589 current companies:

    is_reit    1784 / 2589   68.9%
    is_miner   1784 / 2589   68.9%

805 companies have NULL for both. `CompanySearchResult` declares them
`bool`. A Pydantic default covers a MISSING key; it does not accept an
explicit None. Two NULL columns, "2 validation errors for
CompanySearchResult", 500 — for roughly a third of the company list,
through the search box in the site header.

The same cause broke `/api/v1/companies/{code}` for those companies, which
is the two `CompanyDetail` errors seen on BTL and DSM.

This was already fixed once. Commit 9c50b4c (23 June) added
"COALESCE is_reit/is_miner/is_asx200/is_asx300 in screener SELECT to
prevent Pydantic bool validation error on NULL rows" — to the screener, by
listing the columns. The same defect in these two endpoints survived,
because a list only covers what someone remembered to put in it.

v11.2.38 changed the schema rather than the value: is_reit and is_miner
are now `Optional[bool] = None`, so an unclassified company validates
without being coerced. Both fixes stop the 500; only the second stops
claiming that 563 companies are confirmed non-REITs.

That also reverses half of 9c50b4c above, deliberately. COALESCE was the
right fix for a crash and the wrong fix for the truth -- it made the
endpoint work by answering a question nobody could answer. The index
flags it also coalesced keep that treatment, because absence from an
enumerable list IS non-membership.

The helper remains for the bools that are still non-optional (index
membership, is_bank, is_insurer), and must leave Optional fields alone --
collapsing one would destroy the distinction one layer below the schema
that declares it.

Run:  python tests/test_search_survives_null_flags.py
Requires pydantic.
"""

import ast
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parents[1]
BACKEND = _HERE if (_HERE / "app" / "api").is_dir() else Path.cwd()
sys.path.insert(0, str(BACKEND))

from pydantic import BaseModel                                 # noqa: E402

from app.api.v1.routes.companies import _bool_nulls_to_false   # noqa: E402
from app.schemas.company import CompanySearchResult            # noqa: E402

ROUTES = BACKEND / "app" / "api" / "v1" / "routes" / "companies.py"
SRC = ROUTES.read_text(encoding="utf-8")


class _Model(BaseModel):
    asx_code: str
    is_reit: bool = False
    is_miner: bool = False
    maybe: Optional[bool] = None
    name: Optional[str] = None


#: The production row shape: both flags NULL, as they are for 805 companies.
NULL_ROW = {"asx_code": "BTL", "company_name": "Brightstar", "gics_sector": None,
            "is_reit": None, "is_miner": None}


# ── The defect, and that it is really a defect ──────────────────────────────

def test_a_null_in_a_non_optional_bool_still_fails():
    """Control. If this stops raising, the helper below proves nothing.

    It used to use CompanySearchResult, whose is_reit/is_miner were
    `bool = False`. v11.2.38 made those Optional -- unknown is not false --
    so that model no longer fails on them and could no longer serve as the
    control. The helper is still needed for the bools that remain
    non-optional (index membership, is_bank, is_insurer), and `_Model`
    declares one, so the control moves there rather than being deleted.
    """
    try:
        _Model(asx_code="BTL", is_reit=None)
    except Exception as exc:                                   # noqa: BLE001
        assert "validation error" in str(exc).lower(), (
            f"expected a NULL in a non-optional bool to fail, got: {exc}")
        return
    raise AssertionError(
        "a NULL in a non-optional bool now validates on its own — every "
        "model's bools became Optional, or pydantic changed, and this guard "
        "is testing nothing")


def test_the_search_schema_now_accepts_an_unclassified_company():
    """The other half of v11.2.38, asserted directly.

    805 companies crashed /companies/search with "2 validation errors"
    because the schema demanded a bool and the column held NULL. The first
    fix coerced NULL to False, which stopped the 500 and asserted something
    untrue about 563 companies. The schema now admits the unknown, so the
    row validates WITHOUT being coerced.
    """
    row = CompanySearchResult(**NULL_ROW)
    assert row.asx_code == "BTL"
    assert row.is_reit is None and row.is_miner is None, (
        "the unknown was collapsed; a company nobody has classified is "
        "being reported as a confirmed non-REIT")


def test_a_company_with_unknown_flags_can_be_searched():
    """The 500 that 805 companies produced — still gone, and now the
    unknown survives the helper rather than being flattened by it."""
    row = CompanySearchResult(**_bool_nulls_to_false(CompanySearchResult, NULL_ROW))
    assert row.asx_code == "BTL"
    assert row.is_reit is None and row.is_miner is None, (
        "_bool_nulls_to_false overwrote an Optional field; unknown became "
        "False one layer below the schema that exists to preserve it")


# ── It must not do more than it was asked to ────────────────────────────────

def test_an_optional_bool_keeps_its_unknown():
    """`Optional[bool]` means the schema WANTS to distinguish unknown from
    false. Collapsing it would destroy exactly the distinction it declares."""
    out = _bool_nulls_to_false(_Model, {"asx_code": "X", "is_reit": None,
                                        "is_miner": None, "maybe": None})
    assert out["maybe"] is None, "Optional[bool] was collapsed to False"


def test_non_boolean_nulls_are_untouched():
    out = _bool_nulls_to_false(_Model, {"asx_code": "X", "name": None})
    assert out["name"] is None, "a non-bool field was rewritten"


def test_a_real_true_survives():
    """A REIT must not be turned into a non-REIT."""
    out = _bool_nulls_to_false(_Model, {"asx_code": "X", "is_reit": True,
                                        "is_miner": None})
    assert out["is_reit"] is True
    assert out["is_miner"] is False


# ── Derived, not listed ─────────────────────────────────────────────────────

def test_the_fields_come_from_the_model_not_a_hardcoded_list():
    """This defect was fixed once in June by listing columns, and survived
    here because a list only covers what someone remembered.

    A boolean added to the schema tomorrow must be covered without anyone
    editing this helper.
    """
    fn = next(n for n in ast.walk(ast.parse(SRC))
              if isinstance(n, ast.FunctionDef) and n.name == "_bool_nulls_to_false")
    body = ast.unparse(fn)
    assert "model_fields" in body, (
        "the helper no longer derives its fields from the model")
    names = {c.value for c in ast.walk(fn)
             if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert "is_reit" not in names and "is_miner" not in names, (
        "the helper names specific columns, so the next NULL boolean will "
        "break the endpoint exactly as these two did")


def test_the_search_route_is_bound_to_the_search_function():
    """v11.2.27 shipped with the helper defined BETWEEN the decorator and
    the function it was meant to decorate:

        @router.get("/search", response_model=list[CompanySearchResult])
        def _bool_nulls_to_false(model, row) -> dict:

    FastAPI registered the HELPER as the endpoint, read its two
    no-default parameters as required query params, and returned 422 to
    every search. `search_companies` was not registered at all. The fix
    for a 500 affecting 598 companies became a 422 affecting all of them.

    The source-text check below passed throughout, because the call string
    really was present — in a function nothing reached. This asserts the
    ROUTING TABLE instead of the file.
    """
    from app.api.v1.routes.companies import router, search_companies
    routes = [r for r in router.routes if getattr(r, "path", None) == "/search"]
    assert routes, "no /search route is registered at all"
    assert len(routes) == 1, f"{len(routes)} routes claim /search"
    bound = routes[0].endpoint
    assert bound is search_companies, (
        f"/search is bound to {bound.__name__!r}, not search_companies — "
        f"a decorator landed on the wrong function")


def test_no_private_helper_is_registered_as_an_endpoint():
    """The general form, so the next misplaced decorator fails here.

    A name beginning with an underscore is internal by convention; if one
    is serving HTTP, a decorator has slipped onto the wrong definition.
    """
    from app.api.v1.routes.companies import router
    exposed = [(r.path, r.endpoint.__name__) for r in router.routes
               if getattr(r, "endpoint", None)
               and r.endpoint.__name__.startswith("_")]
    assert not exposed, (
        f"private helpers are serving HTTP routes: {exposed}")


def test_both_endpoints_use_it():
    """Declaring the helper changes nothing a customer can see unless the
    endpoints call it. The search bug and the company-detail bug are one
    cause and must have one fix."""
    assert "_bool_nulls_to_false(CompanySearchResult" in SRC, (
        "the search endpoint does not use the helper")
    assert "_bool_nulls_to_false(CompanyDetail" in SRC, (
        "the company detail endpoint does not use the helper, so /company/"
        "{code} still 500s for the same companies")


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
