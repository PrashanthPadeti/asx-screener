"""
One gate, every anchor-dependent column
=======================================
`price_at` is "last close on or before the fiscal period end" with no floor,
so a company whose price feed stops anchors every later fiscal year to the
same final close. Measured over 33,864 production rows: median 0 days, p95
2, **max 6,644** -- FDR's FY2021 metrics were computed from a close struck in
October 2003. That is finding 18.

v11.2.86 bounded Price/FCF alone at 7 calendar days. v11.2.87 moves the bound
to the single point where `px` is derived, so every column reached through it
obeys the same rule.

WHY THIS FILE EXISTS SEPARATELY FROM THE PRICE/FCF CONTRACT

A per-column test proves a per-column fix. The defect here is a CLASS -- the
anchor reaches fifteen published columns, and eleven of them were missed by
reading the source, because `market_cap` feeds `enterprise_value` feeds
`ev_revenue`, and `dividend_yield` feeds `franked_yield`. A test that
enumerated the columns it already knew about would pass while the next
derivation joined the class unguarded.

So this asserts the PROPERTY: the set of columns that move when the anchor is
withheld is exactly the declared set, and every member of it declines. Adding
a sixteenth derivation fails this test, which is the point -- the judgement
gets made rather than inherited.

THE ONE EXCEPTION, AND WHY IT IS AN EXCEPTION

`altman_z_score` is not withheld. Its X4 term falls back from market value to
BOOK equity when the market cap is absent, so a stale anchor silently
re-bases it instead of removing it. That fallback predates this change, and
whether a column should quietly change basis is a separate question recorded
in finding 18. It is pinned here as a known, deliberate asymmetry rather than
left to be rediscovered.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# yearly_compute resolves DATABASE_URL_SYNC at module scope. setdefault, never
# an assignment: a real URL on the gate must win. Nothing here connects.
os.environ.setdefault("DATABASE_URL_SYNC",
                      "postgresql://unused@127.0.0.1:1/unused")

from compute.engine.applicability import BASE_CURRENCY        # noqa: E402
from compute.engine.yearly_compute import (                   # noqa: E402
    INSERT_SQL, MAX_PRICE_AGE_DAYS, build_yearly_rows,
)

#: Every published column that moves when the price anchor is withheld.
#:
#: DERIVED, not hand-written: produced by running the real producer twice per
#: company -- once normally, once with `_price_observation` returning
#: (None, None) -- over production data, and diffing the rows. See
#: scripts/diagnostics/measure_price_anchor_staleness.py.
#:
#: Reading the source gave eleven. The differential gave fifteen.
ANCHOR_DEPENDENT = {
    "price_at_compute",
    "market_cap",
    "enterprise_value",
    "pe_ratio",
    "pb_ratio",
    "ps_ratio",
    "ev_ebitda",
    "ev_ebit",
    "ev_revenue",
    "earnings_yield",
    "dividend_yield",
    "franked_yield",
    "fcf_yield",
    "p_fcf_ratio",
    "altman_z_score",
}

#: Nothing. Every anchor-dependent column declines on a REJECTED anchor.
#:
#: altman_z_score was briefly in here. Its X4 term falls back from market
#: value to book equity when the market cap is absent, so the anchor gate
#: made it re-base rather than decline -- publishing a different model basis
#: under the same field name, on 275 rows, 4 of them served, with nothing to
#: say so. A pre-existing fallback is not a licence to activate it as a side
#: effect of an unrelated repair. Decided 18 Nov 2026: a rejected anchor
#: withholds it.
#:
#: The fallback itself is untouched for the case it was written for -- no
#: price history at all -- which test_the_fallback_survives_an_absent_anchor
#: pins, so this release does not quietly also change that.
REBASED_NOT_WITHHELD: set[str] = set()

PERIOD_END = pd.Timestamp("2025-06-30")


def _insert_columns() -> list[str]:
    head = INSERT_SQL.split("VALUES", 1)[0]
    inner = head[head.index("(") + 1: head.rindex(")")]
    return [c.strip() for c in inner.replace("\n", " ").split(",") if c.strip()]


def _financials() -> pd.DataFrame:
    """One fiscal year rich enough to populate the whole anchor-dependent set.

    Deliberately complete: dividends and franking so `dividend_yield` and
    `franked_yield` exist, balance-sheet items so `altman_z_score` computes,
    debt so `enterprise_value` differs from `market_cap`. A thinner fixture
    would leave columns NULL in both runs and the test would silently cover
    fewer of them than it claims.
    """
    return pd.DataFrame([{
        "fiscal_year": 2025,
        "period_end_date": PERIOD_END,
        "revenue": 500.0, "gross_profit": 200.0, "ebitda": 90.0,
        "ebit": 70.0, "interest_expense": 5.0,
        "net_profit": 50.0, "eps": 0.50, "eps_diluted": 0.48,
        "dps": 0.20, "dps_franking_pct": 100.0,
        "gpm": None, "opm": None, "npm": None, "ebitda_margin": None,
        # total_equity must NOT equal the market capitalisation. At 400.0 it
        # did -- px 4.00 x 100m shares / 1e6 is also 400.0 -- so Altman's X4
        # was mc/td and te/td with the same numerator, the re-base produced
        # an identical number, and the test reported the mechanism as absent.
        # A fixture coincidence reads exactly like a missing behaviour.
        "total_assets": 900.0, "total_equity": 250.0,
        "total_current_assets": 300.0, "total_current_liab": 150.0,
        "total_debt": 200.0, "net_debt": 150.0,
        "cash_equivalents": 50.0, "long_term_debt": 120.0,
        "retained_earnings": 100.0, "working_capital": 150.0,
        "book_value_per_share": 4.00, "shares_outstanding": 100_000_000.0,
        "trade_receivables": 60.0, "inventory": 40.0,
        "cfo": 110.0, "capex": -30.0, "fcf": 40.0,
        "equity_raised": 0.0, "cfi": -30.0, "dividends_paid": -10.0,
        "derived_dps": 0.20, "derived_franking_pct": 100.0,
    }])


def _prices(last_day: str) -> pd.Series:
    idx = pd.date_range("2024-01-01", last_day, freq="D")
    return pd.Series(np.full(len(idx), 4.0), index=idx)


def _row(last_day: str) -> tuple:
    rows = build_yearly_rows("TST", _financials(), _prices(last_day),
                             current_shares=100_000_000.0,
                             reporting_currency=BASE_CURRENCY)
    assert rows, f"no row produced for a series ending {last_day}"
    return rows[0]


def _fresh_and_stale():
    """Anchors 0 days and 8 days before the period end."""
    return _row("2025-06-30"), _row("2025-06-22")


# ── The property ─────────────────────────────────────────────────────────

def test_the_moving_set_is_exactly_the_declared_set():
    """Adding a sixteenth derivation must fail here, not ship unguarded.

    This is the whole reason the fix is one gate rather than fifteen guards.
    If some future column starts reading `px` or `mc`, it joins the class
    automatically in the producer -- and this test makes someone confirm that
    was intended.
    WHAT THIS DOES NOT ESTABLISH. It proves dependency coverage for the
    columns THIS FIXTURE exercises. A derivation on an unexercised branch,
    or one whose two values coincide, is invisible to it -- which is not
    hypothetical: altman_z_score read as basis-stable here until the fixture
    stopped setting total_equity to the same number as the market cap. So
    this is a ratchet against silent additions, not a proof of completeness,
    and the production differential in
    scripts/diagnostics/measure_price_anchor_staleness.py is what measures
    the real set.
    """
    cols = _insert_columns()
    fresh, stale = _fresh_and_stale()
    moving = {name for i, name in enumerate(cols)
              if name != "computed_at" and fresh[i] != stale[i]}

    assert moving, (
        "nothing moved when the anchor went stale, so this fixture is not "
        "exercising the gate at all and every assertion below is vacuous")
    assert moving == ANCHOR_DEPENDENT, (
        f"the anchor-dependent set changed.\n"
        f"  newly moving (unguarded until now): "
        f"{sorted(moving - ANCHOR_DEPENDENT)}\n"
        f"  no longer moving: {sorted(ANCHOR_DEPENDENT - moving)}\n"
        f"If a column was added, decide whether it should be withheld or "
        f"re-based and update ANCHOR_DEPENDENT / REBASED_NOT_WITHHELD. Do "
        f"not widen the set without that decision.")


def test_every_anchor_dependent_column_declines():
    """A stale anchor withholds, it does not substitute."""
    cols = _insert_columns()
    fresh, stale = _fresh_and_stale()

    for name in sorted(ANCHOR_DEPENDENT - REBASED_NOT_WITHHELD):
        i = cols.index(name)
        assert fresh[i] is not None, (
            f"{name} is NULL even with a fresh anchor, so this fixture does "
            f"not cover it and its inclusion above is unproven")
        assert stale[i] is None, (
            f"{name} published {stale[i]!r} from a close "
            f"{MAX_PRICE_AGE_DAYS + 1} days before the period end. mc is "
            f"px * shares, so this divides an old market quantity into "
            f"current statements.")


def test_altman_is_withheld_on_a_rejected_anchor():
    """A rejected anchor must not silently switch the model basis.

    Altman's X4 is a MARKET value of equity over total liabilities, with a
    fallback to BOOK equity when the market cap is absent. The anchor gate
    makes the market cap absent for 402 rows, so without this the fallback
    would fire there and publish a different basis under the same field --
    275 rows, 4 of them served, none of them saying so.

    A pre-existing fallback is not a licence to activate it as a side effect
    of an unrelated repair.
    """
    cols = _insert_columns()
    i = cols.index("altman_z_score")
    fresh, stale = _fresh_and_stale()
    assert fresh[i] is not None, (
        "altman_z_score is NULL even with a fresh anchor, so this fixture "
        "does not cover it")
    assert stale[i] is None, (
        f"altman_z_score published {stale[i]!r} on a rejected anchor. Its X4 "
        f"term has silently moved from market value to book equity.")


def test_the_fallback_survives_an_absent_anchor():
    """REJECTED is not ABSENT, and only this distinction keeps the fallback.

    No price history at all is the case the book-equity fallback was written
    for, and this release must not change it. So an empty series still
    publishes a score, while a series whose only observation is too old does
    not. If these two ever agree, one of the two decisions has been lost.
    """
    cols = _insert_columns()
    i = cols.index("altman_z_score")

    empty = build_yearly_rows("TST", _financials(),
                              pd.Series(dtype=float,
                                        index=pd.DatetimeIndex([])),
                              current_shares=100_000_000.0,
                              reporting_currency=BASE_CURRENCY)
    assert empty, "no row produced for an empty price series"
    assert empty[0][i] is not None, (
        "altman_z_score was withheld with NO price observation at all. That "
        "is the pre-existing missing-price case its book-equity fallback "
        "exists for, and this release was not supposed to touch it.")

    assert _row("2025-06-22")[i] is None, (
        "a rejected anchor published a score, so the two cases now agree "
        "and the distinction between rejected and absent has been lost")


def test_the_boundary_is_the_same_seven_days():
    """One bound, shared. Not a second threshold for a second set of columns."""
    cols = _insert_columns()
    i = cols.index("market_cap")
    assert MAX_PRICE_AGE_DAYS == 7
    assert _row("2025-06-23")[i] is not None, "7 days must publish"
    assert _row("2025-06-22")[i] is None, "8 days must withhold"


def test_a_series_that_reaches_nothing_withholds():
    """No observation at all is not freshness."""
    cols = _insert_columns()
    rows = build_yearly_rows("TST", _financials(),
                             pd.Series(dtype=float,
                                       index=pd.DatetimeIndex([])),
                             current_shares=100_000_000.0,
                             reporting_currency=BASE_CURRENCY)
    assert rows
    # altman_z_score is excluded HERE and only here. An empty series is the
    # ABSENT case, where its book-equity fallback is deliberately preserved;
    # test_the_fallback_survives_an_absent_anchor asserts that side, and
    # test_altman_is_withheld_on_a_rejected_anchor asserts the other. Every
    # other column has one rule for both cases.
    for name in sorted(ANCHOR_DEPENDENT - {"altman_z_score"}):
        assert rows[0][cols.index(name)] is None, (
            f"{name} published with no price observation at all")


def test_window_metrics_are_not_withheld_by_the_anchor():
    """The gate must not reach past the class it is for.

    `sharpe_1y`, `volatility_1y` and `max_drawdown_1y` read the price SERIES,
    not the anchor. An early version of the measuring instrument truncated
    the series and wrongly reported them as anchor-dependent; withholding
    them here would be the same mistake in the producer, costing real
    coverage for no reason.
    """
    cols = _insert_columns()
    fresh, stale = _fresh_and_stale()
    for name in ("sharpe_1y", "volatility_1y", "max_drawdown_1y"):
        if name not in cols:
            continue
        i = cols.index(name)
        assert fresh[i] == stale[i], (
            f"{name} changed when only the anchor was withheld, so the gate "
            f"is reaching series-based metrics it has no business touching")


if __name__ == "__main__":
    # The release gate runs suites as `python tests/<file>.py` and requires
    # the "N/M passed" line as positive evidence of execution. Without this
    # block the file defines its functions, runs nothing, and exits 0 --
    # which is how test_price_to_fcf_contract.py certified nothing while
    # passing 21/21 locally.
    import sys as _sys

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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    _sys.exit(1 if failures else 0)
