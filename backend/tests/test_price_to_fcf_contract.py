"""
Price/FCF publishes under one contract, or not at all
=====================================================
`p_fcf_ratio` was emptied in v11.2.85 because every value it held came from
a code path that no longer existed. v11.2.86 gives it a producer again, and
this file is the contract that producer must satisfy.

The contract has one publishing case and three declining ones, and the
three are NOT interchangeable:

    fcf > 0, inputs present, AUD     publish mc / fcf
    an input is missing              NULL -- nothing to divide
    fcf <= 0                         NULL -- a REPORTED input that makes
                                     the ratio meaningless, not a missing
                                     one
    reporting currency is foreign    NULL -- an AUD market capitalisation
                                     over a foreign cash flow has no unit

WHY fcf <= 0 IS THE INTERESTING ONE

A negative Price/FCF is not merely odd, it is actively misleading in the
one place customers meet it. The screener sorts this column, and ascending
order means "cheapest first". A company that burned $40m of cash against a
$400m market capitalisation gets -10.0, which sorts AHEAD of a genuinely
cheap company at 4.0. The worse the cash burn, the closer to zero and the
cheaper it looks; a company that burned almost nothing sorts worst of all.

`fcf_yield` publishes the same fact safely, because -10% reads as bad to
everyone and -10x reads as cheap. That asymmetry is why these two
reciprocal metrics do NOT share a guard, and the test below pins it so a
later "consistency" refactor cannot quietly align them.

WHY THE CURRENCY GUARD IS HERE AND NOT IN CROSS_CURRENCY

Applicability gate 1b suppresses exactly this mismatch for eight ratios.
It runs on `governed | model_constituents`, and p_fcf_ratio is neither.
FACTOR_MODEL_V3 is frozen by finalised production runs, so it cannot join
GOVERNED_METRICS without a V4. Declaring it in CROSS_CURRENCY would have
been an entry no code path reads -- declared, not enforced. So the guard
lives in the producer, where it is reached, and the test asserts the
BEHAVIOUR rather than the declaration.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# yearly_compute resolves DATABASE_URL_SYNC at MODULE scope, so importing
# build_yearly_rows -- a pure function over a DataFrame -- needs the variable
# to exist. setdefault, never an assignment: on the gate and in CI a real URL
# is already present and must win. Nothing here opens a connection.
os.environ.setdefault("DATABASE_URL_SYNC",
                      "postgresql://unused@127.0.0.1:1/unused")

from compute.engine.yearly_compute import (          # noqa: E402
    INSERT_SQL, build_yearly_rows,
)
from compute.engine.applicability import (           # noqa: E402
    BASE_CURRENCY, CROSS_CURRENCY,
)

COLUMN = "p_fcf_ratio"


# ── The column position, derived not assumed ─────────────────────────────

def _insert_columns() -> list[str]:
    """The INSERT column list, in order, read from the real statement."""
    head = INSERT_SQL.split("VALUES", 1)[0]
    inner = head[head.index("(") + 1: head.rindex(")")]
    return [c.strip() for c in inner.replace("\n", " ").split(",") if c.strip()]


@pytest.fixture(scope="module")
def col_index() -> int:
    cols = _insert_columns()
    assert COLUMN in cols, (
        f"{COLUMN} is not in the INSERT column list. The producer writes a "
        f"value the statement never carries, so nothing below can be true.")
    return cols.index(COLUMN)


# ── A minimal company that CAN produce a ratio ───────────────────────────

def _financials(fcf: float | None,
                shares: float | None = 100_000_000.0) -> pd.DataFrame:
    """One fiscal year with every input p_fcf needs, and fcf set by caller.

    Deliberately minimal: if a future change makes p_fcf depend on another
    column, these rows stop producing a value and the publishing test fails
    rather than silently testing a different expression.
    """
    return pd.DataFrame([{
        "fiscal_year": 2025,
        "period_end_date": pd.Timestamp("2025-06-30"),
        "revenue": 500.0, "gross_profit": 200.0, "ebitda": 90.0,
        "ebit": 70.0, "interest_expense": 5.0,
        "net_profit": 50.0, "eps": None, "eps_diluted": None,
        "dps": None, "dps_franking_pct": None,
        "gpm": None, "opm": None, "npm": None, "ebitda_margin": None,
        "total_assets": 900.0, "total_equity": 400.0,
        "total_current_assets": 300.0, "total_current_liab": 150.0,
        "total_debt": 200.0, "net_debt": 150.0,
        "cash_equivalents": 50.0, "long_term_debt": 120.0,
        "retained_earnings": 100.0, "working_capital": 150.0,
        "book_value_per_share": None, "shares_outstanding": shares,
        "trade_receivables": 60.0, "inventory": 40.0,
        "cfo": 110.0, "capex": -30.0, "fcf": fcf,
        "equity_raised": 0.0, "cfi": -30.0, "dividends_paid": -10.0,
        "derived_dps": None, "derived_franking_pct": None,
    }])


def _prices() -> pd.Series:
    idx = pd.date_range("2024-07-01", "2025-06-30", freq="D")
    return pd.Series(np.full(len(idx), 4.0), index=idx)


def _ratio(fcf, currency=None, shares=100_000_000.0, idx=None):
    rows = build_yearly_rows("TST", _financials(fcf, shares), _prices(),
                             current_shares=shares,
                             reporting_currency=currency)
    assert rows, "the fixture produced no row at all; the inputs are wrong"
    return rows[0][idx]


# ── The publishing case ──────────────────────────────────────────────────

def test_positive_fcf_publishes_the_ratio(col_index):
    """mc / fcf, from the same pair fcf_yield uses."""
    # price 4.00 x 100m shares / 1e6 = 400.0 (AUD millions); fcf 40.0
    value = _ratio(40.0, idx=col_index)
    assert value == pytest.approx(10.0), (
        f"expected mc/fcf = 400/40 = 10.0, got {value!r}")


def test_the_ratio_is_the_reciprocal_of_the_yield(col_index):
    """Both describe one pair, so their product is 1 within rounding.

    Not an aesthetic check. If a later change computes p_fcf from different
    inputs than fcf_yield -- a different price anchor, a per-share path, a
    TTM cash flow -- the site would publish two numbers that cannot both be
    right, and the screener would sort on one while the company page showed
    the other.
    """
    cols = _insert_columns()
    rows = build_yearly_rows("TST", _financials(40.0), _prices(),
                             current_shares=100_000_000.0,
                             reporting_currency=BASE_CURRENCY)
    row = rows[0]
    p_fcf = row[cols.index("p_fcf_ratio")]
    yld = row[cols.index("fcf_yield")]
    assert p_fcf is not None and yld is not None
    assert p_fcf * yld == pytest.approx(1.0, rel=1e-3), (
        f"p_fcf={p_fcf} and fcf_yield={yld} are not reciprocal; their "
        f"product is {p_fcf * yld}. They no longer describe one pair.")


# ── The three declining cases ────────────────────────────────────────────

def test_div_returns_none_on_zero_denominator():
    """The second of the two guarantees that exclude fcf == 0.

    `fcf > 0` in the producer and `_div`'s zero-denominator rule both
    decline a zero free cash flow, so mutating `> 0` to `>= 0` changes no
    output -- an equivalent mutant, recorded as such in the mutation run
    rather than chased.

    Equivalent only while BOTH hold. This pins the half that lives
    somewhere else, so a change to _div cannot silently make the producer's
    test the only thing standing between a zero denominator and a division.
    """
    from compute.engine.yearly_compute import _div
    assert _div(400.0, 0.0) is None
    assert _div(400.0, 0) is None
    assert _div(400.0, None) is None


@pytest.mark.parametrize("fcf", [-40.0, -0.01, 0.0])
def test_non_positive_fcf_withholds(col_index, fcf):
    """Zero and negative both decline, and for the same stated reason.

    Negative would publish a number that sorts as cheap while meaning the
    opposite. Zero has no finite ratio at all.
    """
    assert _ratio(fcf, currency=BASE_CURRENCY, idx=col_index) is None, (
        f"fcf={fcf} produced a ratio. On an ascending 'cheapest first' "
        f"sort this value ranks ahead of genuinely cheap companies.")


def test_negative_fcf_still_publishes_the_yield():
    """The asymmetry is deliberate and must survive refactoring.

    fcf_yield reports a cash burn as a negative percentage, which reads as
    bad. p_fcf reports it as a negative multiple, which reads as cheap. A
    later change that gave them one shared guard would either lose a true
    fact or keep a misleading one.
    """
    cols = _insert_columns()
    rows = build_yearly_rows("TST", _financials(-40.0), _prices(),
                             current_shares=100_000_000.0,
                             reporting_currency=BASE_CURRENCY)
    row = rows[0]
    assert row[cols.index("p_fcf_ratio")] is None
    assert row[cols.index("fcf_yield")] is not None, (
        "fcf_yield was withheld on negative FCF. A negative free cash flow "
        "yield is a reportable fact, and withholding it loses information "
        "the customer had before.")


def test_missing_fcf_withholds(col_index):
    assert _ratio(None, currency=BASE_CURRENCY, idx=col_index) is None


def test_missing_shares_withholds_via_market_cap(col_index):
    """No shares means no market capitalisation, so no numerator."""
    assert _ratio(40.0, currency=BASE_CURRENCY, shares=None,
                  idx=col_index) is None


@pytest.mark.parametrize("currency", ["USD", "NZD", "usd", " usd "])
def test_foreign_reporting_currency_withholds(col_index, currency):
    """An AUD market cap over a foreign cash flow has no unit.

    Case and whitespace included: the producer upper-cases and strips at
    the fetch, and a guard that only matched an exact "USD" would publish
    for every source that wrote it differently.
    """
    normalised = currency.strip().upper()
    assert _ratio(40.0, currency=normalised, idx=col_index) is None, (
        f"reporting_currency={currency!r} published a ratio mixing an AUD "
        f"market capitalisation with a {normalised} cash flow.")


def test_aud_publishes(col_index):
    assert _ratio(40.0, currency=BASE_CURRENCY, idx=col_index) is not None


def test_unknown_currency_publishes(col_index):
    """Silence is not evidence of a mismatch.

    1,016 of 2,019 ASX codes state no reporting currency, because they have
    no financial statements at all. Reading None as "not AUD" would suppress
    half the exchange to fix roughly 160 companies, and this is the same
    rule applicability.unit_gate follows for the eight ratios it covers.
    """
    assert _ratio(40.0, currency=None, idx=col_index) is not None, (
        "an unstated reporting currency withheld the ratio. None means the "
        "source said nothing, which is not the same as saying USD.")


# ── The guard is enforced here BECAUSE it cannot be enforced there ───────

def test_the_declaration_route_is_still_closed():
    """Pins the reason this guard lives in the producer.

    If p_fcf_ratio ever becomes assessable -- a V4, or a model that names it
    as a constituent -- then CROSS_CURRENCY becomes the right home and this
    producer-side guard becomes a second implementation of one rule. This
    test fails at that moment, which is when someone should move it.
    """
    from compute.engine.factor_applicability import _model_constituents
    from compute.engine.metric_states import (
        GOVERNED_METRICS, LATEST_MODEL_VERSION,
    )
    assessable = (set(GOVERNED_METRICS[LATEST_MODEL_VERSION])
                  | _model_constituents(LATEST_MODEL_VERSION))
    for name in ("p_fcf_ratio", "price_to_fcf"):
        assert name not in assessable, (
            f"{name} is now assessable under {LATEST_MODEL_VERSION}, so "
            f"gate 1b can reach it. Move the currency rule into "
            f"CROSS_CURRENCY and delete the producer-side guard -- keeping "
            f"both is how one rule drifts into two answers.")
        assert name not in CROSS_CURRENCY, (
            f"{name} is declared in CROSS_CURRENCY but is not assessable, "
            f"so nothing reads that entry. It is a declaration without "
            f"enforcement, which reads as a guard and is not one.")
