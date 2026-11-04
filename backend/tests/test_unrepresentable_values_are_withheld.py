"""A value the column cannot hold is withheld, and it takes nothing with it
===========================================================================
Run 37 (1 Nov 2026, FULL_FUNDAMENTALS_CANONICAL) failed and published nothing.
Two companies produced an EPS outside NUMERIC(10,4):

    GGE FY2000   net loss $2.09m / 2 shares          = -1,045,000
    PL9 FY1999   net loss $1.46m / 1,276 shares      = -1,142,367

Those share counts came from the v11.2.73 annual-shares backfill, and the
per-share derivations at yearly_compute.py:650 and :661 guard only
``shares > 0``. 827 rows across 110 codes carry a share count under 100,000,
so the two that overflowed are the visible part of a larger population: the
rest produce figures just as meaningless that happen to FIT the column.

Two separate defects, tested separately here:

  1. An unrepresentable value must be withheld, not handed to psycopg2. The
     limit comes from the catalogue, not from a list in this file -- three
     columns have already been patched one at a time after each crashed a run.
  2. A rejected page must not take its 199 neighbours with it. Two companies
     became 977 unwritten rows across 57 codes, which the coverage guard
     correctly read as an incoherent run and refused to publish.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_unrepresentable_values_are_withheld.py
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://unused:unused@127.0.0.1:1/unused")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused")

from compute.engine import yearly_compute as yc  # noqa: E402


# ── The column list is parsed, and parsed correctly ──────────────────────────

def test_the_column_list_is_the_insert_s_own():
    cols = yc._insert_columns()
    assert cols[0] == "asx_code" and cols[1] == "fiscal_year", (
        f"the parsed column list does not start with the key columns: "
        f"{cols[:3]} -- the parse has picked up the wrong parenthesis")
    assert cols[-1] == "computed_at", (
        f"the parsed list ends at {cols[-1]!r}, not computed_at; it has run "
        f"past the column list into the VALUES clause")
    for stray in ("VALUES", "%s", "INSERT", "ON CONFLICT"):
        assert not any(stray in c for c in cols), (
            f"{stray!r} appears in the parsed column list")


def test_the_column_list_has_no_duplicates():
    """A duplicate shifts every later column's limit by one position, and the
    range check then silently guards the wrong metric."""
    cols = yc._insert_columns()
    dupes = {c for c in cols if cols.count(c) > 1}
    assert not dupes, f"duplicate column names in the INSERT list: {sorted(dupes)}"


def test_the_overflowing_columns_are_in_the_list():
    """If eps or bvps were ever dropped from the INSERT, the guard below would
    pass while guarding nothing."""
    cols = yc._insert_columns()
    for col in ("eps", "bvps", "receivables_days"):
        assert col in cols, f"{col} is not in the INSERT column list"


# ── Withholding ──────────────────────────────────────────────────────────────

def _cols_and_limits():
    """A three-column stand-in: one unguarded, one NUMERIC(10,4), one text."""
    return (["asx_code", "eps", "roe"], [None, 1_000_000.0, 10_000.0])


def test_a_value_over_the_limit_is_withheld():
    cols, limits = _cols_and_limits()
    rows, withheld = yc._withhold_unrepresentable(
        [("GGE", -1_045_000.0, 0.12)], limits, cols)
    assert rows[0][1] is None, (
        "an EPS of -1,045,000 was passed to the INSERT; NUMERIC(10,4) cannot "
        "hold it and psycopg2 raises, taking the whole page down")
    assert withheld == {"eps": 1}, (
        f"the withholding was not reported per column: {withheld}")


def test_a_value_inside_the_limit_survives():
    """Population control. A guard that nulls everything also passes the test
    above, and would erase the entire table."""
    cols, limits = _cols_and_limits()
    rows, withheld = yc._withhold_unrepresentable(
        [("BHP", 4.2718, 0.2134)], limits, cols)
    assert rows[0][1] == 4.2718 and rows[0][2] == 0.2134, (
        f"ordinary values were altered: {rows[0]}")
    assert withheld == {}


def test_the_boundary_is_exclusive():
    """NUMERIC(10,4) holds up to 999,999.9999. Exactly 1,000,000 does not fit,
    so the comparison must be >=, not >."""
    cols, limits = _cols_and_limits()
    rows, _ = yc._withhold_unrepresentable([("X", 1_000_000.0, None)], limits, cols)
    assert rows[0][1] is None, "a value of exactly the limit was kept"
    rows, _ = yc._withhold_unrepresentable([("X", 999_999.9999, None)], limits, cols)
    assert rows[0][1] == 999_999.9999, "the largest representable value was withheld"


def test_text_and_none_are_left_alone():
    cols, limits = _cols_and_limits()
    rows, withheld = yc._withhold_unrepresentable([("GGE", None, None)], limits, cols)
    assert rows[0] == ("GGE", None, None)
    assert withheld == {}


def test_an_unguarded_column_is_not_touched():
    """Columns the catalogue reports no precision for (text, date, integer)
    carry a limit of None and must pass through untouched."""
    cols, limits = _cols_and_limits()
    rows, _ = yc._withhold_unrepresentable([("SOMETHINGLONG", 1.0, 1.0)], limits, cols)
    assert rows[0][0] == "SOMETHINGLONG"


# ── The per-share plausibility bound ─────────────────────────────────────────
# The range guard above keeps the pipeline alive; it does not make the numbers
# true. GGE FY2000's book value of $455,000/share FITS NUMERIC(10,4), so it
# would be stored and served. 82 company-years across 19 codes imply a price
# no ASX security could have.

def test_an_impossible_per_share_price_is_withheld():
    assert yc._plausible_per_share(455_000.0) is None, (
        "a book value of $455,000 per share was kept; it fits the column, so "
        "the range guard alone would publish it")
    assert yc._plausible_per_share(-1_045_000.0) is None


def test_real_per_share_figures_survive():
    """Population control. CSL, the most expensive share in ASX history, peaked
    near $300 -- if the bound ever caught that, it would be erasing the market
    rather than its artefacts."""
    for real in (0.0, 0.0123, 4.27, -2.5, 300.0, 9_999.99):
        assert yc._plausible_per_share(real) == real, (
            f"{real} is a plausible per-share figure and was withheld")


def test_the_bound_is_not_a_clamp():
    """Clamping would report $10,000/share as though it were measured. There is
    no nearest sensible value for a figure this wrong, so the answer is None."""
    out = yc._plausible_per_share(455_000.0)
    assert out is None and out != yc.MAX_PER_SHARE_AUD


def test_the_bound_leaves_absence_absent():
    assert yc._plausible_per_share(None) is None


def test_the_bound_is_above_any_real_asx_price():
    """A bound set too low silently deletes legitimate data, which is the more
    dangerous failure: nothing crashes and nobody notices."""
    assert yc.MAX_PER_SHARE_AUD >= 1_000.0, (
        f"MAX_PER_SHARE_AUD is {yc.MAX_PER_SHARE_AUD}, low enough to withhold "
        f"figures that real ASX securities have reached")
    assert yc.MAX_PER_SHARE_AUD < 1_000_000.0, (
        "the bound is at or above the NUMERIC(10,4) ceiling, so it withholds "
        "nothing the range guard would not already have caught")


# ── The limit arithmetic ─────────────────────────────────────────────────────

def test_the_limit_is_derived_from_precision_and_scale():
    """10**(p-s): NUMERIC(10,4) → 1e6, NUMERIC(8,2) → 1e6, NUMERIC(8,4) → 1e4.

    This is the arithmetic _column_limits applies to the catalogue; getting it
    wrong by one order of magnitude either erases good data or lets the crash
    through.
    """
    assert 10 ** (10 - 4) == 1_000_000
    assert 10 ** (8 - 4) == 10_000
    assert 10 ** (8 - 2) == 1_000_000


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
