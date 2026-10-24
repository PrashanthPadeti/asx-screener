#!/usr/bin/env python
"""
A missing industry is not a negative answer
===========================================
`transform_companies.py` derived the structural flags like this:

    "is_reit":  "reit" in (sn(row.get("gic_industry")) or "").lower()
    "is_miner": any(k in (sn(row.get("gic_industry")) or "").lower() ...)

When `gic_industry` is absent, `sn()` returns None, `(None or "")` becomes
the empty string, and both expressions evaluate to **False**. A company we
know nothing about was recorded as a confirmed non-REIT and a confirmed
non-miner.

Measured on production, 24 Oct 2026:

    2,589 current companies
      884 have no gics_industry at all
      805 carry NULL flags (never classified by any producer)
       80 were written as definite FALSE with no industry to justify it
    2,552 rows in screener.universe, 768 of them unclassified -- 30%

The site then showed all of them as "Is REIT: No", because v11.2.27 made
NULL render as False to stop a 500. That fixed the crash and entrenched
the wrong answer. Of a sample of the unclassified: Altitude Minerals,
Gorilla Gold Mines, Linq Minerals, Verity Resources -- all sector
Materials, all displayed as "not a miner".

Three states, because there are three situations:

    TRUE / FALSE   an industry was known and it did or did not match
    None           no industry was available -- failed to obtain
    None           the instrument is an ETF, note or fund -- cannot apply

The last two are both unknown to a consumer, but they are not the same
fact, and neither is FALSE. 439 of the 805 are ETFs: "is this ETF a REIT"
has no answer, and writing FALSE is as much an invention as writing TRUE.

Run:  python tests/test_structural_flags_are_derived_not_assumed.py
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts" / "eodhd" / "v2" / "transforms"))

# classification.py is deliberately free of database and environment imports,
# so these rules are testable as what they are: pure functions over a row.
# They previously lived in transform_companies, behind `import psycopg2` and
# `load_dotenv()`, where testing them meant stubbing a chain of drivers.
from classification import (                                     # noqa: E402
    NON_OPERATING_TYPES, classify_miner as _is_miner,
    classify_reit as _is_reit)


def row(**kw):
    return kw


# ── Absence must not become a negative ──────────────────────────────────────

def test_a_missing_industry_yields_unknown_not_false():
    """The defect, directly. This is the assertion that would have stopped
    805 companies being published as confirmed non-REITs."""
    for r in (row(), row(gic_industry=None), row(gic_industry=""),
              row(gic_industry="  "), row(gic_industry="N/A"),
              row(gic_industry="None")):
        assert _is_reit(r) is None, f"is_reit claimed a value for {r}"
        assert _is_miner(r) is None, f"is_miner claimed a value for {r}"


def test_unknown_is_not_falsy_by_accident():
    """None and False are both falsy, so a consumer that writes
    `if not is_reit` treats them alike. The producer must still emit the
    distinction; this pins that `is None` holds, not merely falsiness."""
    unknown = _is_reit(row(gic_industry=None))
    known_no = _is_reit(row(gic_industry="Software"))
    assert unknown is None
    assert known_no is False
    assert unknown is not known_no, (
        "unknown and a known negative have collapsed into the same value")


# ── Non-operating instruments: the question does not apply ──────────────────

def test_an_etf_is_neither_a_reit_nor_not_a_reit():
    for t in sorted(NON_OPERATING_TYPES):
        assert _is_reit(row(type=t, gic_industry="Software")) is None, (
            f"{t} was given a REIT verdict even with an industry present; "
            f"the question does not apply to it")
        assert _is_miner(row(type=t, gic_industry="Gold Mining")) is None, (
            f"{t} was given a miner verdict; the question does not apply")


def test_a_reit_instrument_type_still_classifies():
    """Type can settle it positively: EODHD marks some listings REIT by type
    even where the industry string does not say so."""
    assert _is_reit(row(type="REIT")) is True
    assert _is_reit(row(type="reit", gic_industry=None)) is True


# ── The flags must still work when the evidence IS there ────────────────────

def test_a_known_industry_classifies_as_before():
    assert _is_reit(row(gic_industry="Equity REIT - Retail")) is True
    assert _is_reit(row(gic_industry="Software")) is False

    for industry in ("Gold Mining", "Coal & Consumable Fuels",
                     "Metals & Mining", "Other Industrial Metals & Mining"):
        assert _is_miner(row(gic_industry=industry)) is True, industry
    assert _is_miner(row(gic_industry="Software")) is False
    assert _is_miner(row(gic_industry="Banks")) is False


def test_industries_named_for_the_commodity_are_mining():
    """The gap the dry run exposed before anything was written.

    The original keywords -- mining, gold, metals, coal -- matched the
    activity but not the industries named for the commodity. Measured
    against the live vocabulary: Copper (6 companies), Uranium (3),
    Aluminum (1), every one recorded as a confirmed non-miner.
    """
    for industry in ("Copper", "Uranium", "Aluminum", "Aluminium",
                     "Nickel", "Lithium", "Silver", "Platinum", "Zinc",
                     "Iron Ore", "Rare Earth Minerals"):
        assert _is_miner(row(gic_industry=industry)) is True, (
            f"{industry!r} is not classified as mining")


def test_the_exclusions_are_deliberate_and_stay_excluded():
    """Pinned so a later 'while we're here' widening has to argue for it.

    Steel covers manufacturers as well as miners; oil and gas is 127
    companies that are not miners; construction materials is cement.
    """
    for industry in ("Steel", "Oil & Gas E&P", "Oil, Gas & Consumable Fuels",
                     "Construction Materials", "Chemicals",
                     "Specialty Chemicals", "Paper & Forest Products"):
        assert _is_miner(row(gic_industry=industry)) is False, (
            f"{industry!r} is now classified as mining; if that is "
            f"intended, say why here -- it was excluded on purpose")


def test_real_estate_that_is_not_a_reit_stays_out():
    """REIT industries all contain the word; real-estate operating
    companies must not be swept in with them."""
    for industry in ("Diversified REITs", "Retail REITs", "REIT - Industrial",
                     "REIT - Specialty"):
        assert _is_reit(row(gic_industry=industry)) is True, industry
    for industry in ("Real Estate Management & Development",
                     "Real Estate Services", "Real Estate - Diversified",
                     "Real Estate - Development"):
        assert _is_reit(row(gic_industry=industry)) is False, industry


def test_the_classification_is_case_insensitive():
    assert _is_reit(row(gic_industry="EQUITY REIT")) is True
    assert _is_miner(row(gic_industry="GOLD MINING")) is True


# ── The regression this replaces ────────────────────────────────────────────

def test_the_old_expression_would_fail_these_cases():
    """Mutation control, stated as the old code rather than a mutation.

    Recorded so the defect cannot be reintroduced by someone 'simplifying'
    the helpers back into a one-liner.
    """
    def old_is_reit(r):
        v = r.get("gic_industry")
        return "reit" in ((v or "")).lower()

    absent = row(gic_industry=None)
    assert old_is_reit(absent) is False, "control is not reproducing the bug"
    assert _is_reit(absent) is None, (
        "the fix no longer distinguishes absent evidence from a negative")


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
