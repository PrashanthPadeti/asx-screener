#!/usr/bin/env python
"""
Unknown is served as unknown, and a closed-world absence still means no
======================================================================
v11.2.32 repaired the data: 205 companies classified, 24 corrected, miners
685 -> 821. It deliberately left **563** universe rows unclassified --

    111  operating companies with only a sector (GICS Materials covers
         chemicals and packaging; classifying from it manufactures a
         different set of wrong answers)
     11  with no industry data anywhere
    441  ETFs, notes and funds, where "is this a REIT" has no answer

and then the API collapsed every one of them to `false` on the way out:
`COALESCE(u.is_reit, FALSE)` in three SELECTs, and `bool = False` in the
response schemas. v11.2.27 added the second to stop a 500 -- a real fix
for a real crash that converted "we never looked" into "we checked, and
no".

That claim reached every API consumer and every CSV export, and made a
genuine negative indistinguishable from an unassessed row everywhere
downstream.

The distinction this file protects
----------------------------------
`is_reit` and `is_miner` are OPEN-world: absence of an industry
classification is evidence of nothing.

`is_asx200` and its siblings are CLOSED-world: the index list is
enumerable, so absence from it genuinely IS non-membership. Those keep
`bool = False`, and that is a decision rather than an oversight.

The two look identical in the database. They are not the same fact.

Run:  python tests/test_unknown_flags_are_not_false.py
"""

import ast
import os
import sys
import typing
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

for _k, _v in (("DATABASE_URL", "postgresql+asyncpg://unused/unused"),
               ("DATABASE_URL_SYNC", "postgresql://unused/unused"),
               ("JWT_SECRET", "test-only-not-a-secret")):
    os.environ.setdefault(_k, _v)

OPEN_WORLD = ("is_reit", "is_miner")
SCREENER_ROUTE = BACKEND / "app" / "api" / "v1" / "routes" / "screener.py"


def _optional(annotation) -> bool:
    return type(None) in typing.get_args(annotation)


def _models():
    from app.schemas import company, screener
    import pydantic
    for module in (company, screener):
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type)
                    and issubclass(obj, pydantic.BaseModel)
                    and obj is not pydantic.BaseModel):
                yield f"{module.__name__}.{name}", obj


def test_the_open_world_flags_can_say_unknown():
    checked = 0
    for label, model in _models():
        for field in OPEN_WORLD:
            meta = model.model_fields.get(field)
            if meta is None:
                continue
            checked += 1
            assert _optional(meta.annotation), (
                f"{label}.{field} is declared {meta.annotation} — a company "
                f"nobody has classified will be served as False, which is a "
                f"claim we cannot make about 563 of 2,552 rows")
    assert checked >= 4, (
        f"only {checked} declarations of is_reit/is_miner found across the "
        f"response schemas; the models have moved and this proves nothing")


def test_the_closed_world_flags_still_mean_no():
    """The deliberate other half.

    Absence from the ASX 200 list is non-membership, because the list is
    enumerable. Making these Optional too would push an unanswerable
    question onto consumers for a question that IS answerable.
    """
    import pydantic
    from app.schemas import company
    found = 0
    for name in dir(company):
        obj = getattr(company, name)
        if not (isinstance(obj, type) and issubclass(obj, pydantic.BaseModel)
                and obj is not pydantic.BaseModel):
            continue
        for field, meta in obj.model_fields.items():
            if field.startswith("is_asx") or field == "is_all_ords":
                found += 1
                assert not _optional(meta.annotation), (
                    f"company.{name}.{field} became Optional. Index "
                    f"membership is a closed-world list: absence from it is "
                    f"evidence of non-membership. If this changed on "
                    f"purpose, say why here.")
    assert found >= 4, f"only {found} index flags found"


def test_the_screener_does_not_coalesce_the_open_world_flags():
    """The collapse happened in SQL, before the schema ever saw the value.

    Structural over the file: a fourth SELECT added later with a COALESCE
    would reinstate the defect for one endpoint only, which is the hardest
    kind to notice.
    """
    src = SCREENER_ROUTE.read_text(encoding="utf-8")
    offenders = []
    for i, line in enumerate(src.splitlines(), 1):
        if line.strip().startswith("--") or line.strip().startswith("#"):
            continue
        for field in OPEN_WORLD:
            if f"COALESCE(u.{field}" in line or f"COALESCE({field}" in line:
                offenders.append(f"screener.py:{i}  {line.strip()[:70]}")
    assert not offenders, (
        "an open-world flag is coalesced to FALSE in SQL, so the schema "
        "never sees the unknown:\n  " + "\n  ".join(offenders))


def test_the_closed_world_flags_are_still_coalesced():
    """Control for the test above: it must be checking something.

    If every COALESCE disappeared, the test above would pass vacuously.
    """
    src = SCREENER_ROUTE.read_text(encoding="utf-8")
    assert "COALESCE(u.is_asx200" in src, (
        "the index flags are no longer coalesced either — either that was "
        "deliberate (then update this test) or the SELECT has been rewritten "
        "and the test above is no longer watching anything")


def test_the_null_to_false_helper_leaves_optional_fields_alone():
    """_bool_nulls_to_false exists to stop a 500 on a non-optional bool.

    It must not touch a field the schema deliberately made Optional -- that
    would re-collapse the distinction one layer later, which is exactly how
    v11.2.27's crash fix destroyed it the first time.
    """
    from app.api.v1.routes.companies import _bool_nulls_to_false
    from app.schemas.company import CompanySearchResult

    out = _bool_nulls_to_false(
        CompanySearchResult,
        {"asx_code": "XYZ", "company_name": "Example Ltd",
         "gics_sector": None, "is_reit": None, "is_miner": None})
    assert out["is_reit"] is None, (
        "the helper overwrote an Optional field; unknown became False one "
        "layer below the schema that exists to preserve it")
    assert out["is_miner"] is None


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
