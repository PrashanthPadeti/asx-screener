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
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.dividends import (  # noqa: E402
    CORP_TAX_RATE,
    DividendState,
    FeedHealth,
    MIN_RECENT_ISSUERS,
    MIN_RECENT_ROWS,
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


# ── Feed staleness · the window is only as honest as the feed ─────────────────

def test_a_stale_feed_refuses_rather_than_halving_the_yield():
    """Measured Sep 2026: market.dividends held 0 rows in the preceding 30 days
    and every ASX20 payer was 6-10 months past its last recorded dividend. A
    correct window over that feed captures one of two semi-annual payments."""
    res = ttm_dividends(CBA_ROWS, as_of=AS_OF, feed_as_of=date(2026, 8, 3))

    assert res.state is DividendState.FEED_INCOMPLETE
    assert res.cash_dps is None and res.gross_dps is None


def test_a_current_feed_computes_normally():
    res = ttm_dividends(CBA_ROWS, as_of=CBA_TWO_PAYMENT_DATE,
                        feed_as_of=date(2026, 2, 25))
    assert res.state is DividendState.APPLICABLE
    assert res.cash_dps == 4.95


def test_a_quiet_month_does_not_trip_the_guard():
    """January and July have troughs; the tolerance clears one, not a break."""
    res = ttm_dividends(CBA_ROWS, as_of=CBA_TWO_PAYMENT_DATE,
                        feed_as_of=date(2026, 3, 1) - timedelta(days=34))
    assert res.state is DividendState.APPLICABLE


def test_the_guard_is_opt_in():
    """Callers that cannot supply a feed date keep the previous behaviour."""
    assert ttm_dividends(CBA_ROWS, as_of=AS_OF).state is DividendState.APPLICABLE


def test_feed_incomplete_writes_nulls_not_a_halved_number():
    m = dividend_metrics(CBA_ROWS, close=158.690, as_of=AS_OF,
                         feed_as_of=date(2026, 8, 3))
    assert all(m[f] is None for f in FIELDS)


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


def test_a_company_that_stopped_paying_writes_an_observed_zero():
    """Superseded by the observed-vs-unobserved distinction, and it was this
    test that encoded the conflation.

    It asserted all-NULL for a company that stopped paying. The protection it
    was really carrying -- the OEL bug, where an omitted key left a stale 480%
    grossed-up yield in place -- is test_every_field_is_present_on_every_path,
    which is unaffected. What this one additionally asserted was that "paid
    nothing" and "could not observe" should look identical, and they must not:

        No dividend paid in a healthy, fully observed period is EVIDENCE.
        Failure to observe the period is MISSING evidence.

    The old shape cost every non-payer its Income score and then its composite,
    because an UNAVAILABLE constituent may not be reweighted.
    """
    m = dividend_metrics([row("2023-06-01", 1.00)], close=10.0, as_of=AS_OF)

    assert m["dividend_per_share"] == 0.0
    assert m["dividend_yield"] == 0.0
    assert m["grossed_up_dividend"] == 0.0
    assert m["grossed_up_yield"] == 0.0
    # Nothing was paid, so there is nothing to frank. Zero would be a claim
    # about a distribution that did not happen.
    assert m["franking_pct"] is None
    assert set(m) == set(FIELDS), "every field still written, OEL protection"


def test_an_unobservable_window_still_writes_nothing():
    """The other side of the distinction. Without a valid price the yield is
    genuinely uncomputable and stays absent rather than being called zero --
    while the payment facts, which need no price, are still stated."""
    m = dividend_metrics([], close=None, as_of=AS_OF)

    assert m["dividend_yield"] is None
    assert m["grossed_up_yield"] is None
    assert m["dividend_per_share"] == 0.0, "no price needed to know it paid none"


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

# ── An announcement is not an observation ────────────────────────────────────

def test_future_announcements_do_not_make_a_stale_feed_healthy():
    """The defect the September 2026 reload exposed.

    MAX(ex_date) and the breadth counters were both unbounded above, and the
    table legitimately holds announced future ex-dates -- out to 2026-12-16
    after the reload. Unbounded, the watermark was that December date, the lag
    came out at -94 days, and -94 <= 35 reported healthy.

    Strictly worse than the original defect: a feed that had recorded nothing
    since May would have passed on the strength of dividends that have not
    happened yet.
    """
    h = FeedHealth(latest_ex_date=date(2026, 8, 3), as_of=date(2026, 9, 13),
                   recent_rows=0, recent_issuers=0, future_announced=412)

    assert not h.healthy
    assert h.lag_days == 41
    assert "41 days behind" in h.reason
    assert "412 future announcements" in h.reason


def test_a_table_of_only_future_announcements_is_unhealthy():
    """No ex-date has occurred, so nothing has been observed. Healthy would
    mean the feed is current on the strength of records about the future."""
    h = FeedHealth(latest_ex_date=None, as_of=date(2026, 9, 13),
                   recent_rows=0, recent_issuers=0, future_announced=412)

    assert not h.healthy
    assert "no ex-date that has occurred" in h.reason


def test_an_empty_table_is_a_source_failure_not_universal_non_payment():
    """2,500 companies do not all stop paying dividends at once. An empty
    table is unequivocally unhealthy -- and the transform now refuses to
    commit one, so both ends of that hold."""
    h = FeedHealth(latest_ex_date=None, as_of=date(2026, 9, 13),
                   recent_rows=0, recent_issuers=0, future_announced=0)

    assert not h.healthy
    assert "holds no ex-dates" in h.reason


def test_a_repaired_feed_is_healthy_on_occurred_evidence():
    h = FeedHealth(latest_ex_date=date(2026, 9, 3), as_of=date(2026, 9, 13),
                   recent_rows=96, recent_issuers=93, future_announced=412)

    assert h.healthy
    assert h.lag_days == 10


def test_a_negative_lag_is_never_healthy():
    """Defensive rather than reachable: the query bounds latest_ex_date to
    today, so a negative lag would mean the clock disagrees with the database.
    Reporting healthy on that basis is precisely what was wrong before."""
    h = FeedHealth(latest_ex_date=date(2026, 12, 16), as_of=date(2026, 9, 13))

    assert h.lag_days < 0
    assert not h.healthy


# ── Breadth: a floor calibrated from evidence ────────────────────────────────

def test_the_quietest_real_window_is_still_healthy():
    """The case a badly-chosen floor breaks. Across 136 rolling 35-day windows
    of the repaired feed the worst held 68 rows / 66 issuers. A floor that
    rejects that would fire every winter and teach an operator to ignore it."""
    h = FeedHealth(latest_ex_date=date(2026, 9, 11), as_of=date(2026, 9, 13),
                   recent_rows=68, recent_issuers=66)

    assert h.healthy, h.failure


def test_fresh_but_thin_is_not_healthy():
    """Freshness alone was always weak: one stray fresh row makes the
    watermark current while coverage stays broken. Breadth is the second hard
    condition, not a corroborating nicety."""
    h = FeedHealth(latest_ex_date=date(2026, 9, 11), as_of=date(2026, 9, 13),
                   recent_rows=4, recent_issuers=3)

    assert not h.healthy
    assert "4 ex-dates" in h.failure


def test_rows_without_issuers_is_its_own_failure():
    """100 rows across three issuers is broken in a way a row count cannot
    see, so both conditions are required rather than either."""
    h = FeedHealth(latest_ex_date=date(2026, 9, 11), as_of=date(2026, 9, 13),
                   recent_rows=100, recent_issuers=3)

    assert not h.healthy
    assert "issuers" in h.failure


def test_the_floor_sits_well_below_observed_healthy_and_above_the_outage():
    """The calibration itself, asserted so a future edit cannot quietly move
    the floor into either failure mode.

    worst healthy window  68 rows / 66 issuers
    observed outage        0 rows in 35 days
    """
    assert MIN_RECENT_ROWS < 68 / 2, "must clear the quietest healthy window"
    assert MIN_RECENT_ISSUERS < 66 / 2
    assert MIN_RECENT_ROWS > 1, "must still reject the outage we measured"
    assert MIN_RECENT_ISSUERS > 1


def test_freshness_is_checked_before_breadth():
    """A stale feed reports staleness, not thinness. Both are true of a dead
    feed, and only the first tells an operator what happened."""
    h = FeedHealth(latest_ex_date=date(2026, 8, 3), as_of=date(2026, 9, 13),
                   recent_rows=0, recent_issuers=0)

    assert "days behind" in h.failure


# ── The ingestion chain is actually scheduled ────────────────────────────────

def _weekly_pipeline_source() -> str:
    from pathlib import Path as _P
    return (_P(__file__).resolve().parents[1] / "scripts" / "eodhd" / "v2"
            / "jobs" / "weekly_pipeline.py").read_text(encoding="utf-8")


def test_the_dividend_chain_is_in_the_weekly_pipeline():
    """The outage cause, as an assertion.

    download_dividends ran every Sunday and filled the raw zone.
    load_to_staging_dividends and transform_dividends existed only in
    pipeline_runner.py, which is in no cron entry -- so market.dividends
    advanced solely when someone ran that path by hand, and decayed from May
    2026 when nobody did. The provider never stopped working.
    """
    src = _weekly_pipeline_source()

    assert "load_to_staging_dividends.py" in src
    assert "transform_dividends.py" in src
    assert "assert_feed_health.py" in src


def test_dividends_are_materialised_before_anything_computes_over_them():
    """yearly_compute derives DPS from market.dividends and daily_compute
    reads it for every yield metric. Loading after them would compute a week
    behind the feed, every week, and look entirely normal doing it."""
    src = _weekly_pipeline_source()

    transform = src.index("transform_dividends.py")
    assert_health = src.index("assert_feed_health.py")
    yearly = src.index("yearly_compute.py")
    staging = src.index("load_to_staging_dividends.py")

    assert staging < transform, "staging load precedes the transform"
    assert transform < assert_health, "health is asserted on the loaded table"
    assert assert_health < yearly, "nothing computes over an unasserted feed"


def test_the_scheduler_does_not_reimplement_the_health_thresholds():
    """An operational definition of healthy living beside the financial one
    drifts from it, silently: the scheduler would report success while the
    engine withheld every dividend metric, and neither would be wrong by its
    own lights."""
    src = _weekly_pipeline_source()

    # Usage, not mention: the pipeline's comments may name the function it
    # delegates to, and this test failing on its own explanatory comment
    # would be a guard that punishes documentation.
    assert "fetch_feed_health(" not in src, "the pipeline must not classify"
    assert "import fetch_feed_health" not in src
    assert "FEED_STALENESS_DAYS" not in src
    assert "MIN_RECENT_ROWS" not in src
    assert "MIN_RECENT_ISSUERS" not in src


# ── The same rule, one layer up, where the factor engine reads it ────────────
#
# DividendSource.assessments already concludes that a non-payer's franking_pct
# is NOT_MEANINGFUL / OBSERVATION. But it can only reach that conclusion where
# it holds the raw payment rows, and the factor engine does not: it reads a
# universe row. So a NULL franking_pct arrived at ranking as UNAVAILABLE /
# SOURCE_MISSING.
#
# That is not a cosmetic mislabel. An UNAVAILABLE constituent may not be
# reweighted out of a factor, so it withheld Income for every non-payer and
# the composite with it -- 321 and 252 of 2,103 in discovery-7, against 1,888
# in production -- while dividend_yield and dividend_per_share were by then
# correctly populated on 1,597 rows. The dividend data was right and the score
# was still refused.
#
# dps_ttm == 0 carries the evidence, and the observation gate now reads it.

def _assess_franking(value, observed):
    from compute.engine.applicability import Domain, Observation, assess
    return assess("franking_pct", value, Domain.GENERAL_CORPORATE,
                  Observation(dividends_observed=observed))


def test_a_non_payer_has_nothing_to_frank():
    """The case that was withholding Income across the universe."""
    from compute.engine.applicability import Applicability, Cause
    a = _assess_franking(None, 0.0)

    assert a.state is Applicability.NOT_MEANINGFUL
    assert a.cause is Cause.OBSERVATION
    assert not a.ok


def test_an_unobserved_dividend_is_still_source_missing():
    """The distinction the whole change rests on. A zero says we looked and
    found nothing; None says we could not look. Collapsing them would trade
    one wrong answer for another, and this one would be worse -- it would
    manufacture a factor score out of absent data."""
    from compute.engine.applicability import Applicability, Cause
    a = _assess_franking(None, None)

    assert a.state is Applicability.UNAVAILABLE
    assert a.cause is Cause.SOURCE_MISSING


def test_a_payer_missing_franking_is_still_source_missing():
    """A company that demonstrably paid, with no franking figure, is a real
    gap in the feed and must keep saying so."""
    from compute.engine.applicability import Applicability, Cause
    a = _assess_franking(None, 0.45)

    assert a.state is Applicability.UNAVAILABLE
    assert a.cause is Cause.SOURCE_MISSING


def test_a_franking_value_is_never_overridden_by_the_rule():
    """The gate withholds; it must not reach a value that exists."""
    from compute.engine.applicability import Applicability
    a = _assess_franking(100.0, 0.0)

    assert a.state is Applicability.APPLICABLE
    assert a.value == 100.0


def _assess_div(metric, value, observed, years):
    from compute.engine.applicability import Domain, Observation, assess
    return assess(metric, value, Domain.GENERAL_CORPORATE,
                  Observation(dividends_observed=observed,
                              dividend_years=years))


def test_a_non_payer_has_no_dividend_growth_rate():
    """discovery-10: dividend_cagr_3y was NULL on 1,735 of the 1,738 rows with
    no Income score — the third constituent in this family to withhold the
    whole factor by claiming a source failure."""
    from compute.engine.applicability import Applicability, Cause
    a = _assess_div("dividend_cagr_3y", None, 0.0, 0)

    assert a.state is Applicability.NOT_MEANINGFUL
    assert a.cause is Cause.OBSERVATION


def test_a_short_paying_history_says_wait_not_missing():
    """The distinction PERIOD_REQUIREMENT cannot make. It counts consecutive
    annual REPORTING periods, so a company that has reported for ten years and
    paid for two passes it and lands on SOURCE_MISSING — sending an operator
    to check a feed that is working. A dividend window is measured in paying
    years."""
    from compute.engine.applicability import Applicability, Cause
    a = _assess_div("dividend_cagr_3y", None, 0.30, 2)

    assert a.state is Applicability.INSUFFICIENT_DATA
    assert a.cause is Cause.INSUFFICIENT_HISTORY


def test_a_long_payer_with_no_value_is_still_a_real_gap():
    """Five years of dividends and no CAGR is our problem, and must keep
    saying so. Neither new rule may swallow it."""
    from compute.engine.applicability import Applicability, Cause
    a = _assess_div("dividend_cagr_3y", None, 0.30, 5)

    assert a.state is Applicability.UNAVAILABLE
    assert a.cause is Cause.SOURCE_MISSING


def test_the_non_payer_answer_outranks_the_short_history_answer():
    """Both rules match a non-payer: dps is 0 and paying years is 0. The
    meaningful answer wins, because 'wait for more dividend history' is
    advice about a dividend the company does not pay."""
    from compute.engine.applicability import Applicability
    a = _assess_div("dividend_cagr_3y", None, 0.0, 0)

    assert a.state is Applicability.NOT_MEANINGFUL


def test_every_dividend_window_is_measured_in_paying_years():
    """A hand-written entry claiming a 3-year window on a _5y column would
    withhold two fewer years than the name promises, and nothing else would
    notice — the same guard the rolling averages already carry."""
    from compute.engine.applicability import DIVIDEND_PERIOD_REQUIREMENT

    for metric, required in DIVIDEND_PERIOD_REQUIREMENT.items():
        assert metric.endswith(f"_{required}y"), (
            f"{metric} requires {required} paying years")


def test_the_factor_engine_actually_loads_the_observation():
    """The rule is inert unless dps_ttm reaches the frame. OBSERVATION_COLS is
    what puts it there -- composite_score appends its values to select_cols --
    so an entry missing here means the gate silently never fires."""
    from compute.engine.factor_applicability import OBSERVATION_COLS

    assert OBSERVATION_COLS.get("dividends_observed") == "dps_ttm", (
        "franking_pct's observation gate reads Observation.dividends_observed; "
        "without this mapping it is always None and the gate never fires")
    assert OBSERVATION_COLS.get("dividend_years") == "dividend_consecutive_yrs", (
        "the dividend CAGR window is measured in paying years; without this "
        "mapping the gate is inert and every short payer reads SOURCE_MISSING")


# ── The contract has to reach the column, not just the function ──────────────
#
# dividend_metrics was correct and its output was persisted, and the served
# numbers still came from somewhere else. build_screener_universe took
# dividend_yield and dps_ttm from market.valuation_snapshot, franking_pct from
# a single latest row of market.dividends, and grossed_up_yield from
# computed_metrics with a fallback to ym.franked_yield. Four of the five
# governed fields never touched this module.
#
# Nothing counted it. Every coverage number looked plausible on its own; the
# defect was only visible as an asymmetry between two fields that this module
# always writes together -- 1,597 against 464 in discovery-6.
#
# These guards are textual because the thing being asserted is textual: which
# relation a column is selected from. A test that computed values would pass
# against the wrong source, which is exactly what happened.

_BUILDER = (Path(__file__).resolve().parents[1]
            / "scripts" / "eodhd" / "v2" / "build_screener_universe.py")

#: The fields dividend_metrics returns as a set, under the names they carry in
#: market.computed_metrics. Kept here rather than imported so that renaming a
#: key in the module cannot silently empty this list.
GOVERNED_DIVIDEND_FIELDS = (
    "dividend_yield", "dividend_per_share", "franking_pct",
    "grossed_up_dividend", "grossed_up_yield",
)


def _builder_sql() -> str:
    """The builder's source with comment lines removed.

    Comments discuss the rejected sources by name -- correctly, that is what
    they are for -- and an earlier guard of mine matched its own explanation
    instead of the code. Strip them before asserting on SQL text.
    """
    lines = []
    for line in _BUILDER.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_no_governed_dividend_field_is_read_from_an_ungoverned_relation():
    """valuation_snapshot, yearly_metrics and a raw latest dividend row are
    all real tables with plausible values. None of them applied the TTM
    window, the gross-up policy, or the feed-health refusal."""
    sql = _builder_sql()
    forbidden = [
        "vs.dividend_yield", "vs.dividend_per_share", "vs.franking_pct",
        "vs.grossed_up_yield", "ym.franked_yield", "div_latest.franking_pct",
    ]
    found = [f for f in forbidden if f in sql]

    assert not found, (
        f"build_screener_universe reads a governed dividend field from an "
        f"ungoverned source: {found}. These must come from cm.* -- the one "
        f"writer that went through compute.engine.dividends.")


def test_the_builder_reads_the_dividend_fields_it_needs_from_computed_metrics():
    """The inverse, and the half that actually failed: the values were
    computed and persisted, and then simply not selected."""
    sql = _builder_sql()
    missing = [f for f in ("dividend_yield", "dividend_per_share",
                           "franking_pct", "grossed_up_yield")
               if f"cm.{f}" not in sql]

    assert not missing, (
        f"governed dividend fields not read from computed_metrics: {missing}")


def test_dividend_metrics_still_returns_exactly_the_governed_field_set():
    """If a sixth field appears here, the guard above stops covering it. The
    two lists are only useful while they describe the same set."""
    keys = set(dividend_metrics([], 10.0))

    assert keys == set(GOVERNED_DIVIDEND_FIELDS), (
        f"dividend_metrics returns {sorted(keys)}, guard covers "
        f"{sorted(GOVERNED_DIVIDEND_FIELDS)}")


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
