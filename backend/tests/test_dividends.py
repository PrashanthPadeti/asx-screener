"""
TTM dividend window and gross-up — permanent regression tests
=============================================================
These ship with the fix and stay in the suite. Two of them are named in the
correctness roadmap as required fixtures:

  * CBA dividend window — asserts window membership, cash DPS, gross-up and
    final yield *separately*, not a displayed percentage.
  * Anomaly predicate — a semi-annual payer whose corrected grossed-up yield is
    below 12% must not fire HIGH_GROSSED_UP_YIELD, and the same fixture shows
    the old four-payment calculation would have fired it.

Run under pytest, or standalone the way the multibagger tests are run:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_dividends.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.dividends import (  # noqa: E402
    CORP_TAX_RATE,
    DividendState,
    GrossUpPolicy,
    Payment,
    dividend_metrics,
    franking_credit,
    gross_up,
    implied_franking_pct,
    in_window,
    normalise,
    reconciles,
    ttm_dividends,
    ttm_window,
)

FULLY_FRANKED = 1.0 + 0.30 / 0.70          # 1.428571…
AS_OF = date(2026, 9, 9)


def row(ex_date: str, amount: float, franking=100.0, grossed_up=None) -> dict:
    """A row shaped like fetch_dividends returns."""
    return {"ex_date": date.fromisoformat(ex_date), "amount": amount,
            "franking_pct": franking, "grossed_up": grossed_up}


# CBA's payments as they actually stand in market.dividends, newest first,
# with the stored grossed_up_amount alongside. Every row reconciles exactly to
# cash x 1.428571, and franking is 100% throughout.
#
# CBA's financial year ends 30 June: the interim goes ex around February and
# the final around August. The series below therefore spans two and a half
# years, and divs[:4] summed 2024-08 through 2026-02 — the $9.70 that produced
# the 8.73% on the company page.
CBA_ROWS = [
    row("2026-02-18", 2.35, grossed_up=3.357143),
    row("2025-08-20", 2.60, grossed_up=3.714286),
    row("2025-02-19", 2.25, grossed_up=3.214286),
    row("2024-08-21", 2.50, grossed_up=3.571429),
    row("2024-02-21", 2.15, grossed_up=3.071429),
    row("2023-08-16", 2.40, grossed_up=3.428571),
]

#: A date on which CBA's interim and the preceding final both sit inside the
#: trailing year — the ordinary semi-annual shape the window is built for.
CBA_TWO_PAYMENT_DATE = date(2026, 3, 1)


# ── The window is period-based ────────────────────────────────────────────────

def test_window_is_twelve_months_not_four_payments():
    kept = in_window(normalise(CBA_ROWS), CBA_TWO_PAYMENT_DATE)
    assert [p.ex_date for p in kept] == [date(2026, 2, 18), date(2025, 8, 20)]
    assert len(kept) == 2, "a semi-annual payer has two payments in a year"


def test_window_bounds_are_inclusive_and_exclude_the_year_ago_day():
    start, end = ttm_window(date(2026, 9, 9))
    assert (start, end) == (date(2025, 9, 10), date(2026, 9, 9))


def test_window_survives_leap_years():
    assert ttm_window(date(2025, 2, 28))[0] == date(2024, 2, 29)
    assert ttm_window(date(2024, 2, 29))[0] == date(2023, 3, 1)


def test_quarterly_payer_keeps_four_payments():
    rows = [row(f"2026-{m:02d}-15", 0.25) for m in (8, 5, 2)] + [row("2025-11-15", 0.25)]
    assert len(in_window(normalise(rows), AS_OF)) == 4


def test_as_of_is_the_snapshot_date_not_today():
    """A metric computed for a past date selects the window that date saw."""
    kept = in_window(normalise(CBA_ROWS), date(2025, 9, 1))
    assert [p.ex_date for p in kept] == [date(2025, 8, 20), date(2025, 2, 19)]


# ── Fixture · CBA dividend window ─────────────────────────────────────────────

def test_cba_window_membership_cash_gross_and_yield_separately():
    res = ttm_dividends(CBA_ROWS, as_of=CBA_TWO_PAYMENT_DATE)

    assert res.state is DividendState.APPLICABLE
    assert res.payment_count == 2
    assert res.cash_dps == 4.95, "2.35 + 2.60, shown as DPS (TTM) $4.950"
    assert res.provenance == "stored", "the per-payment column is used"
    # Stored gross-ups are held to six decimals, so summing them lands a
    # fraction of a cent off the exact ratio. That difference is the price of
    # preferring the recorded value over recomputing it, and is immaterial at
    # any display precision.
    assert abs(res.gross_dps - 4.95 * FULLY_FRANKED) < 1e-5
    assert abs(res.franking_pct - 100.0) < 1e-4

    m = dividend_metrics(CBA_ROWS, close=158.690, as_of=CBA_TWO_PAYMENT_DATE)
    assert abs(m["grossed_up_yield"] - 0.044561) < 5e-6


def test_cba_no_longer_reports_the_two_and_a_half_year_figure():
    """The old arithmetic, asserted so the regression is visible, not implied."""
    old_cash = sum(r["amount"] for r in CBA_ROWS[:4])
    old_yield = old_cash * FULLY_FRANKED / 158.690

    assert abs(old_cash - 9.70) < 1e-9, "2024-08 through 2026-02"
    assert abs(old_yield - 0.08732) < 5e-6, "the 8.73% the company page displayed"

    new = dividend_metrics(CBA_ROWS, close=158.690, as_of=CBA_TWO_PAYMENT_DATE)
    assert new["grossed_up_yield"] < old_yield / 1.9, "roughly halved, not adjusted"


def test_a_stale_feed_shows_up_as_a_one_payment_window():
    """A period window reports what the data contains, and that is the point.

    As of September 2026 the trailing year holds only CBA's February interim:
    the August 2026 final is absent from market.dividends. A payment-count
    heuristic hides that by reaching further back until it has four rows; a
    period window states it, which is the behaviour to keep. The yield is
    genuinely understated until the feed catches up — a data-completeness
    problem, surfaced rather than papered over.
    """
    res = ttm_dividends(CBA_ROWS, as_of=AS_OF)

    assert res.payment_count == 1
    assert res.cash_dps == 2.35, "the February interim, alone"
    assert res.window_start == date(2025, 9, 10)


# ── Fixture · anomaly predicate ───────────────────────────────────────────────

ANOMALY_THRESHOLD = 0.12          # anomaly_detect.py:129, HIGH_GROSSED_UP_YIELD

# An ordinary fully-franked semi-annual payer: 35c twice a year, $10 share.
ORDINARY_PAYER = [
    row("2026-08-15", 0.35), row("2026-02-15", 0.35),
    row("2025-08-15", 0.35), row("2025-02-15", 0.35),
]


def test_ordinary_semi_annual_payer_must_not_fire_the_yield_anomaly():
    m = dividend_metrics(ORDINARY_PAYER, close=10.0, as_of=AS_OF)

    assert abs(m["grossed_up_yield"] - 0.10) < 1e-6, "10% — high, but real"
    assert m["grossed_up_yield"] <= ANOMALY_THRESHOLD, \
        "corrected yield is below the anomaly threshold"


def test_the_old_calculation_would_have_fired_it():
    """Same fixture, both halves: proves the bug and proves the correction."""
    old_cash = sum(r["amount"] for r in ORDINARY_PAYER[:4])
    old_yield = old_cash * FULLY_FRANKED / 10.0

    assert old_yield > ANOMALY_THRESHOLD, "20% — the doubled figure fires"
    assert dividend_metrics(ORDINARY_PAYER, close=10.0,
                            as_of=AS_OF)["grossed_up_yield"] <= ANOMALY_THRESHOLD


# ── Gross up per payment, not per aggregate ───────────────────────────────────

def test_franking_changed_between_payments_is_grossed_up_per_payment():
    """The second defect in the same function: 100% then 0% is not 'avg 50%'."""
    rows = [row("2026-08-15", 1.00, franking=0.0),
            row("2026-02-15", 1.00, franking=100.0)]
    res = ttm_dividends(rows, as_of=AS_OF)

    assert res.cash_dps == 2.00
    assert abs(res.gross_dps - (1.00 + 1.00 * FULLY_FRANKED)) < 1e-9

    aggregate = 2.00 * (1 + 0.50 * CORP_TAX_RATE / (1 - CORP_TAX_RATE))
    assert abs(res.gross_dps - aggregate) < 1e-9, \
        "for two equal payments the two happen to agree — see the unequal case"


def test_unequal_payments_expose_the_aggregate_error():
    rows = [row("2026-08-15", 0.20, franking=0.0),
            row("2026-02-15", 2.00, franking=100.0)]
    res = ttm_dividends(rows, as_of=AS_OF)

    correct = 0.20 + 2.00 * FULLY_FRANKED
    aggregate = 2.20 * (1 + 0.50 * CORP_TAX_RATE / (1 - CORP_TAX_RATE))

    assert abs(res.gross_dps - correct) < 1e-9
    assert abs(res.gross_dps - aggregate) > 0.10, "the averaged version is materially wrong"


def test_unfranked_gross_equals_cash():
    res = ttm_dividends([row("2026-08-15", 1.00, franking=0.0)], as_of=AS_OF)
    assert res.gross_dps == res.cash_dps
    assert res.franking_pct == 0.0


def test_franking_credit_is_capped_at_full_franking():
    assert franking_credit(1.0, 150.0) == franking_credit(1.0, 100.0)
    assert franking_credit(1.0, -20.0) == 0.0


# ── Stored per-payment value wins where usable ────────────────────────────────

def test_stored_grossed_up_amount_is_used_not_recomputed():
    """The column fetch_dividends already selected and nothing ever read."""
    rows = [row("2026-08-15", 1.00, franking=100.0, grossed_up=1.40)]
    res = ttm_dividends(rows, as_of=AS_OF)

    assert res.provenance == "stored"
    assert res.gross_dps == 1.40, "stored 1.40 preserved, not replaced by 1.4286"


def test_missing_stored_value_is_reconstructed_and_the_mix_is_declared():
    rows = [row("2026-08-15", 1.00, franking=100.0, grossed_up=1.40),
            row("2026-02-15", 1.00, franking=100.0, grossed_up=None)]
    res = ttm_dividends(rows, as_of=AS_OF)

    assert res.provenance == "mixed", "never silent about a mixed series"
    assert abs(res.gross_dps - (1.40 + FULLY_FRANKED)) < 1e-9


def test_implausible_stored_value_is_rejected():
    """A gross-up below its cash, or far above the franked ceiling, is not one."""
    below = gross_up(Payment(date(2026, 8, 15), 1.00, 100.0, stored_gross=0.50))
    assert below.provenance == "reconstructed"

    above = gross_up(Payment(date(2026, 8, 15), 1.00, 100.0, stored_gross=14.0))
    assert above.provenance == "reconstructed", "10x is a different quantity"


def test_strict_stored_refuses_rather_than_partially_summing():
    rows = [row("2026-08-15", 1.00, grossed_up=1.40),
            row("2026-02-15", 1.00, grossed_up=None)]
    res = ttm_dividends(rows, as_of=AS_OF, policy=GrossUpPolicy.STRICT_STORED)
    assert res.state is DividendState.UNAVAILABLE
    assert res.gross_dps is None


def test_compute_only_ignores_stored_values():
    rows = [row("2026-08-15", 1.00, franking=100.0, grossed_up=1.40)]
    res = ttm_dividends(rows, as_of=AS_OF, policy=GrossUpPolicy.COMPUTE_ONLY)
    assert abs(res.gross_dps - FULLY_FRANKED) < 1e-9


def test_reconciliation_flag_records_whether_stored_matches_the_formula():
    matches = gross_up(Payment(date(2026, 8, 15), 1.00, 100.0, stored_gross=1.428571))
    differs = gross_up(Payment(date(2026, 8, 15), 1.00, 100.0, stored_gross=1.40))
    assert matches.reconciles is True
    assert differs.reconciles is False


# ── States, not silent nulls ──────────────────────────────────────────────────

def test_no_history_and_lapsed_payer_are_different_states():
    assert ttm_dividends([], as_of=AS_OF).state is DividendState.NO_DIVIDEND_HISTORY

    lapsed = ttm_dividends([row("2023-06-01", 1.00)], as_of=AS_OF)
    assert lapsed.state is DividendState.NO_PAYMENTS_IN_WINDOW
    assert lapsed.window_start == date(2025, 9, 10)


def test_franking_without_a_dividend_yields_nothing():
    """SFR showed 100% franking against no dividend. That must not survive."""
    res = ttm_dividends([row("2026-08-15", 0.0, franking=100.0)], as_of=AS_OF)
    assert res.state is DividendState.UNAVAILABLE
    assert res.franking_pct is None


def test_rows_missing_a_date_or_amount_are_dropped():
    rows = [row("2026-08-15", 1.00), {"ex_date": None, "amount": 5.0},
            {"ex_date": date(2026, 7, 1), "amount": None}]
    assert len(normalise(rows)) == 1


def test_decimal_and_string_inputs_normalise():
    from decimal import Decimal
    rows = [{"ex_date": "2026-08-15", "amount": Decimal("1.25"),
             "franking_pct": Decimal("100"), "grossed_up_amount": Decimal("1.7857")}]
    res = ttm_dividends(rows, as_of=AS_OF)
    assert res.cash_dps == 1.25 and res.provenance == "stored"


# ── The five fields are written together or not at all ────────────────────────

FIELDS = ("dividend_per_share", "dividend_yield", "franking_pct",
          "grossed_up_dividend", "grossed_up_yield")


def test_every_field_is_present_on_every_path():
    """Omitting a key leaves the previous run's value in place — the OEL bug."""
    for rows, close in (([], 10.0), (CBA_ROWS, None), (CBA_ROWS, 0.0),
                        ([row("2020-01-01", 1.0)], 10.0), (CBA_ROWS, 158.69)):
        m = dividend_metrics(rows, close=close, as_of=AS_OF)
        assert set(m) == set(FIELDS), f"missing keys for close={close}"


def test_a_company_that_stopped_paying_writes_nulls():
    m = dividend_metrics([row("2023-06-01", 1.00)], close=10.0, as_of=AS_OF)
    assert all(m[f] is None for f in FIELDS)


# ── The invariant the screener row must satisfy ───────────────────────────────

def test_franking_is_never_manufactured_from_gross_alone():
    """A meaningless denominator must fail closed, not divide through.

    The derivation reads cash and gross together. If cash is zero, absent or
    negative there is no basis to imply a franking percentage from — and
    returning one would recreate the defect being fixed, in a new place.
    """
    for cash in (0.0, -1.0):
        assert implied_franking_pct(cash, 1.40) is None, \
            f"cash={cash} must not yield a franking percentage"


def test_a_gross_only_series_produces_no_franking_field():
    """SFR: 100% franking recorded against no dividend."""
    m = dividend_metrics([row("2026-08-15", 0.0, franking=100.0, grossed_up=1.40)],
                         close=10.0, as_of=AS_OF)
    assert m["franking_pct"] is None
    assert m["grossed_up_yield"] is None
    assert reconciles(m), "all-null is the correct fail-closed outcome"


def test_reconcile_fails_closed_on_a_zero_cash_yield():
    """Not a divide-by-zero, and not a pass either."""
    assert not reconciles({"dividend_yield": 0.0, "grossed_up_yield": 0.02,
                           "franking_pct": 100.0})


def test_implied_franking_round_trips():
    assert abs(implied_franking_pct(1.0, FULLY_FRANKED) - 100.0) < 1e-9
    assert implied_franking_pct(1.0, 1.0) == 0.0
    assert abs(implied_franking_pct(1.0, 1.0 + 0.5 * 0.30 / 0.70) - 50.0) < 1e-9


def test_metrics_reconcile_by_construction():
    for rows, close in ((CBA_ROWS, 158.690), (CBA_ROWS, 155.25),
                        (ORDINARY_PAYER, 10.0)):
        assert reconciles(dividend_metrics(rows, close=close, as_of=AS_OF))


def test_mixed_franking_still_reconciles():
    rows = [row("2026-08-15", 0.20, franking=0.0), row("2026-02-15", 2.00, franking=100.0)]
    assert reconciles(dividend_metrics(rows, close=40.0, as_of=AS_OF))


def test_reconcile_rejects_the_shapes_seen_in_production():
    # WES: 0.00% cash against 7.50% grossed-up.
    assert not reconciles({"dividend_yield": 0.0, "grossed_up_yield": 0.075,
                           "franking_pct": 100.0})
    # A grossed-up yield below its own cash yield.
    assert not reconciles({"dividend_yield": 0.05, "grossed_up_yield": 0.04,
                           "franking_pct": 100.0})
    # Fully franked, but the ratio says otherwise.
    assert not reconciles({"dividend_yield": 0.05, "grossed_up_yield": 0.055,
                           "franking_pct": 100.0})
    # All-null is legitimate.
    assert reconciles({"dividend_yield": None, "grossed_up_yield": None,
                       "franking_pct": None})


# ── Standalone runner, matching the existing tests' convention ────────────────

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
        except Exception as e:
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")

    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
