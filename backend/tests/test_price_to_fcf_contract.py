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


def _col_index() -> int:
    cols = _insert_columns()
    assert COLUMN in cols, (
        f"{COLUMN} is not in the INSERT column list. The producer writes a "
        f"value the statement never carries, so nothing below can be true.")
    return cols.index(COLUMN)


@pytest.fixture(scope="module")
def col_index() -> int:
    """A thin fixture over a plain function.

    The body lives in `_col_index` so the __main__ runner at the bottom can
    call it. A pytest fixture cannot be invoked directly, and this suite has
    to run both under pytest AND as a standalone script, because the release
    gate executes `python tests/<file>.py` -- see that block for what happened
    when this file could not.
    """
    return _col_index()


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


@pytest.mark.parametrize("shares", [0.0, -100_000_000.0])
def test_non_positive_market_cap_withholds(col_index, shares):
    """The numerator must be POSITIVE, not merely present.

    `mc = px * shares / 1e6 if (px and shares) else None` already drops a zero
    price and a zero share count through truthiness, so for shares == 0 this
    test and the `mc > 0` guard agree by two routes. A NEGATIVE share count
    reaches the guard and nothing else: it produces a negative market
    capitalisation, a negative ratio, and a company at the top of a "cheapest
    first" sort -- the same customer-visible failure as negative FCF, arriving
    from the numerator instead.

    Both parameters are impossible as facts and representable in the source,
    which is the only reason the guard is explicit. A condition that holds
    only through two other expressions' internals is not the policy being
    enforced, it is the policy being coincided with.
    """
    assert _ratio(40.0, currency=BASE_CURRENCY, shares=shares,
                  idx=col_index) is None, (
        f"shares={shares} produced a ratio from a non-positive market "
        f"capitalisation.")


def test_a_market_cap_that_rounds_to_zero_withholds(col_index):
    """The one input that distinguishes `mc > 0` from `mc >= 0`.

    mc is rounded to 2dp, so a tiny-but-positive market capitalisation becomes
    exactly 0.0 -- here one share at $4.00 gives round(4e-6, 2) == 0.0. The
    truthiness test that builds mc cannot catch this: both px and shares are
    truthy, and the zero appears in the rounding.

    Under `mc >= 0` the producer would divide 0.0 by the cash flow and publish
    a Price/FCF of 0.0, which is the CHEAPEST value the column can hold and
    sorts above every real company on an ascending screen. That is why the
    comparison is strict, and this is the row that proves it.
    """
    assert _ratio(40.0, currency=BASE_CURRENCY, shares=1.0,
                  idx=col_index) is None, (
        "a market capitalisation that rounded to 0.0 published a ratio of "
        "0.00, which sorts first on 'cheapest'.")


def test_the_clamp_suppresses_rather_than_substituting(col_index):
    """A ratio over 9,999 is withheld, NOT stored as 9,999.

    `_clamp` reads like it bounds a value and it does not -- it returns None
    above the threshold. That distinction is the whole customer-facing
    question: a substituted boundary value would put a fabricated 9,999.00
    into a sort column, indistinguishable from a company whose ratio really is
    9,999.

    The threshold is NOT an overflow guard on this column. p_fcf_ratio is
    NUMERIC(10,2) and holds 99,999,999.99; 9,999 is the editorial threshold
    every NUMERIC(10,2) valuation ratio in this producer already uses, and
    p_fcf matches them deliberately. Asserted here so that changing the
    threshold for this column alone has to be a decision, not an edit.
    """
    from compute.engine.yearly_compute import _clamp
    assert _clamp(9_999.0) == 9_999.0
    assert _clamp(10_000.0) is None, (
        "_clamp substituted a boundary value instead of withholding")

    # price 4.00 x 100m shares / 1e6 = 400.0 against fcf 0.02 -> 20,000
    assert _ratio(0.02, currency=BASE_CURRENCY, idx=col_index) is None, (
        "a ratio of 20,000 published; the threshold the sibling ratios use "
        "is not being applied to this one")


def test_the_pair_disagrees_at_the_extreme_and_that_is_recorded():
    """The _clamp threshold is not symmetric across the two presentations.

    A ratio above 9,999 is a yield below 0.0001, which rounds to 0.0000 in
    NUMERIC(8,4) and publishes. So the reciprocal pair disagrees at the
    extreme: no ratio, a near-zero yield. This is a consequence of two column
    types, not of a policy, and it is pinned here so it is a known property
    rather than a surprise found in production.
    """
    cols = _insert_columns()
    rows = build_yearly_rows("TST", _financials(0.02), _prices(),
                             current_shares=100_000_000.0,
                             reporting_currency=BASE_CURRENCY)
    row = rows[0]
    assert row[cols.index("p_fcf_ratio")] is None
    assert row[cols.index("fcf_yield")] is not None, (
        "fcf_yield was also withheld, so the asymmetry this test records no "
        "longer exists -- delete the test and the comment that explains it")


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
    """PINS AN OPEN DECISION. It does not justify one.

    This test records what the producer does today -- an unstated currency
    publishes -- and the earlier version of this docstring argued that was
    correct. It is not established. The source contract is explicit that
    silence is NOT AUD (backend/migrations/add_reporting_currency.sql), so
    publishing here rests on "an unknown currency is not evidence of a
    mismatch" rather than on any evidence of coherence, and roughly 8% of ASX
    reporters state a foreign currency.

    What keeps it permissive for now is consistency, not proof:
    applicability.unit_gate makes the identical choice for all eight ratios it
    covers, so a strict rule here alone withholds Price/FCF on rows where P/E
    publishes for the same reason, and unit_gate cannot change while
    FACTOR_MODEL_V3 is frozen.

    Both options leave an inconsistency, so the decision needs the cost.
    scripts/diagnostics/measure_p_fcf_populations.py reports P7: the rows that
    publish ONLY because the currency is unstated. If this test's expectation
    flips, that measurement is why.
    """
    assert _ratio(40.0, currency=None, idx=col_index) is not None, (
        "an unstated reporting currency withheld the ratio. If that is now "
        "deliberate, this test is the record of the old rule -- replace it "
        "with the strict one and cite the P7 measurement that decided it.")


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


if __name__ == "__main__":
    # THE RELEASE GATE RUNS THIS FILE AS A SCRIPT, NOT UNDER PYTEST.
    #
    # `gate_full_suite.sh` executes `python tests/<file>.py` and requires the
    # "N/M passed" line below as positive evidence of execution. Without this
    # block the file defines its functions, runs nothing, and exits 0 -- which
    # the gate reports as INCONCLUSIVE, and which an earlier gate would have
    # counted as a pass.
    #
    # That is exactly what happened to the FIRST candidate of this release.
    # All 21 tests passed locally under pytest and NONE of them ran in the
    # gate: the suite written to certify the restoration could not certify
    # anything, and the gate said so. The contract is only a contract where
    # it executes.
    #
    # This runner expands @pytest.mark.parametrize itself and injects the
    # col_index fixture by name, then CHECKS ITS OWN COVERAGE: the number of
    # invocations must equal the number the marks imply, and a test whose
    # signature asks for something this runner cannot supply is an ERROR, not
    # a skip. A runner that silently skipped such a test would reproduce the
    # defect one level up -- a count that looks complete while a case never
    # ran.
    import inspect
    import sys as _sys

    def _cases(fn):
        """(kwargs, label) per invocation, from the function's own marks."""
        marks = [m for m in getattr(fn, "pytestmark", [])
                 if m.name == "parametrize"]
        cases = [({}, "")]
        for m in marks:
            names = [n.strip() for n in m.args[0].split(",")]
            expanded = []
            for base, label in cases:
                for value in m.args[1]:
                    values = value if len(names) > 1 else (value,)
                    kw = dict(base, **dict(zip(names, values)))
                    expanded.append((kw, f"{label}[{value!r}]"))
            cases = expanded
        return cases

    FIXTURES = {"col_index": _col_index()}

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    expected = sum(len(_cases(f)) for _, f in tests)
    ran = 0
    failures: list[str] = []

    for name, fn in tests:
        wanted = set(inspect.signature(fn).parameters)
        for kwargs, label in _cases(fn):
            missing = wanted - set(kwargs) - set(FIXTURES)
            if missing:
                failures.append(name)
                ran += 1
                print(f"  ERROR {name}{label}  - this runner cannot supply "
                      f"{sorted(missing)}; add it to FIXTURES rather than "
                      f"letting the case go unrun")
                continue
            call = dict(kwargs)
            for f_name in wanted & set(FIXTURES):
                call[f_name] = FIXTURES[f_name]
            try:
                fn(**call)
                ran += 1
                print(f"  PASS  {name}{label}")
            except AssertionError as e:
                ran += 1
                failures.append(name)
                print(f"  FAIL  {name}{label}  - {e}")
            except Exception as e:                            # noqa: BLE001
                ran += 1
                failures.append(name)
                print(f"  ERROR {name}{label}  - {type(e).__name__}: {e}")

    if ran != expected:
        print(f"\n  ** COVERAGE: ran {ran} of {expected} expected cases. The "
              f"count below is not a verdict on this contract.")
        failures.append("runner-coverage")

    print(f"\n{ran - len(failures)}/{expected} passed")
    _sys.exit(1 if failures else 0)
