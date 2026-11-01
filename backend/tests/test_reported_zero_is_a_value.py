"""A reported zero is a value, not a missing observation
=======================================================
``sm()`` converted every reported zero to None:

    return round(f / 1_000_000, 4) if f != 0 else None

so the loader silently overrode the provider on every money field the balance
sheet carries. A company disclosing no long-term debt, no goodwill, no
inventory arrived in the table indistinguishable from a company that had told
us nothing.

Measured cost on one criterion: EODHD states no non-current debt as "0.00" on
5,842 balance-sheet years, 5,837 of them for companies with real assets, and
all of them became NULL. Piotroski F5 was assessable for 838 companies where
the payload supports far more.

The defence for the old behaviour -- "a provider sends 0 when it means
missing" -- was tested rather than assumed, and is false here. If EODHD did
that, totalAssets would read zero thousands of times across 33,201 years; it
reads zero 19 times. Where an independent check exists, a zero
longTermDebtTotal is corroborated by shortLongTermDebtTotal equalling the
current portion 1,429 times against 60 contradictions. Those 60 are the
provider contradicting itself and remain visible as what it said.

These tests are BEHAVIOURAL. The property is about values, so they call the
functions. A source matcher would pass on a docstring describing the bug --
which is how three guards were fooled on 30 Oct 2026.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_reported_zero_is_a_value.py
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts/eodhd"))

# load_fundamentals resolves its DSN at import time and refuses to carry a
# built-in default, which is correct and means a test must supply one. Nothing
# here connects; the value is never used.
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://unused:unused@127.0.0.1:1/unused")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused")

import load_fundamentals as lf  # noqa: E402


# ── The scalar converter ─────────────────────────────────────────────────────

def test_a_reported_zero_survives_conversion():
    assert lf.sm("0.00") == 0.0, (
        "sm() turns a reported zero into None, so a company that discloses no "
        "long-term debt is stored as a company that reported nothing")
    assert lf.sm(0) == 0.0
    assert lf.sm("0") == 0.0


def test_absence_still_converts_to_none():
    """The other half. If this ever fails, absence has become a number and the
    repair has overshot into the defect it was fixing."""
    for absent in (None, "", "NA", "None", "not-a-number"):
        assert lf.sm(absent) is None, f"sm({absent!r}) should be None"


def test_ordinary_values_are_unaffected():
    assert lf.sm("5000000") == 5.0
    assert lf.sm("-2500000") == -2.5


# ── Ratios ───────────────────────────────────────────────────────────────────

def test_a_zero_numerator_is_a_real_ratio():
    assert lf.margin(0, 100) == 0.0, (
        "margin() rejects a numerator of zero, so zero gross profit on real "
        "revenue reports no margin instead of a margin of 0.0")


def test_a_zero_denominator_has_no_ratio():
    assert lf.margin(10, 0) is None
    assert lf.margin(10, None) is None
    assert lf.margin(None, 100) is None


# ── Key fallbacks ────────────────────────────────────────────────────────────

def test_a_present_zero_beats_a_later_key():
    """``r.get("a") or r.get("b")`` falls through whenever a is zero -- the
    same erasure one layer up, and invisible because the fallback usually
    agrees."""
    assert lf.pick({"a": 0, "b": 5}, "a", "b") == 0
    assert lf.pick({"a": "0.00", "b": "5"}, "a", "b") == "0.00"


def test_an_absent_key_falls_through():
    assert lf.pick({"a": None, "b": 5}, "a", "b") == 5
    assert lf.pick({"a": "", "b": 5}, "a", "b") == 5
    assert lf.pick({"a": "NA", "b": 5}, "a", "b") == 5
    assert lf.pick({}, "a", "b") is None


# ── End to end through the parser ────────────────────────────────────────────

def _payload(**overrides) -> dict:
    row = {
        "totalAssets": "10000000", "totalLiab": "4000000",
        "totalStockholderEquity": "6000000", "cash": "2000000",
        "longTermDebt": "0.00", "longTermDebtTotal": "0.00",
        "shortTermDebt": "0.00",
        "totalCurrentAssets": "5000000", "totalCurrentLiabilities": "5000000",
        "commonStockSharesOutstanding": "1000000",
    }
    row.update(overrides)
    return {"Financials": {"Balance_Sheet": {"yearly": {"2025-06-30": row}}}}


def test_a_debt_free_balance_sheet_parses_as_debt_free():
    rows = lf.parse_annual_bs("TEST", _payload())
    assert len(rows) == 1
    r = rows[0]
    assert r["long_term_debt_total"] == 0.0, (
        "a company stating no non-current debt is stored as not having "
        "reported it, which is what made Piotroski F5 unassessable for "
        "hundreds of companies that plainly disclose the figure")
    assert r["long_term_debt"] == 0.0
    assert r["total_debt"] == 0.0, (
        "total_debt is derived with a truthiness test, so it erases its own "
        "zeros even once sm() keeps them")


def test_derived_fields_keep_their_zeros():
    r = lf.parse_annual_bs("TEST", _payload())[0]
    assert r["net_debt"] == -2.0, (
        "net debt for a debt-free company holding cash is minus its cash, "
        "not unknown")
    assert r["working_capital"] == 0.0, (
        "current assets exactly matching current liabilities is working "
        "capital of zero, not an absent observation")


def test_a_genuinely_absent_field_is_still_absent():
    """Population control. If every field now arrives as a number, the parser
    has stopped distinguishing the two states at all and every test above
    passes for the wrong reason."""
    r = lf.parse_annual_bs("TEST", _payload(longTermDebtTotal=None,
                                            longTermDebt=None,
                                            shortTermDebt=None))[0]
    assert r["long_term_debt_total"] is None
    assert r["long_term_debt"] is None
    assert r["total_debt"] is None, (
        "with neither debt field reported, total_debt is unknown -- not zero")
    assert r["net_debt"] is None


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
