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

def test_the_raw_row_really_does_fail():
    """Control. If this ever stops raising, the fix below proves nothing."""
    try:
        CompanySearchResult(**NULL_ROW)
    except Exception as exc:                                   # noqa: BLE001
        assert "2 validation errors" in str(exc), (
            f"expected the two NULL flags to fail validation, got: {exc}")
        return
    raise AssertionError(
        "a row with NULL is_reit/is_miner now validates on its own — the "
        "schema or the data changed and this guard is testing nothing")


def test_a_company_with_unknown_flags_can_be_searched():
    """The 500 that 805 companies produced."""
    row = CompanySearchResult(**_bool_nulls_to_false(CompanySearchResult, NULL_ROW))
    assert row.asx_code == "BTL"
    assert row.is_reit is False and row.is_miner is False


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
