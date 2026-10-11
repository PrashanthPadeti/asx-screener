#!/usr/bin/env python
"""
Stale data must not be presentable as current
=============================================
`ASX100` last published **2026-05-29** while every other index was current to
2026-10-09, and the API served it with no qualification at all:

    ASX100  close=7304.8  r1y=0.0336  date=2026-05-29  status=None

A Premium subscriber saw a four-month-old price and a one-year return
computed from it, with nothing marking either. Nine of ten indices succeed on
every run, so `ProducerTally.verify()` -- which raises only when
`usable == 0` -- reported success throughout. The same tolerance that hid
`DIV` and `PMC`.

Two things this is careful about
--------------------------------
**Staleness is measured, not declared.** Unlike `UNVERIFIED_SERIES`, there is
no hand-maintained list: any series that falls behind is caught, including
the next one to go quiet. A list would only ever contain the problems
somebody already found.

**Freshness is counted in trading sessions, not calendar days.** A calendar
threshold either fires every weekend or gets loosened until it catches
nothing. On Saturday 10 Oct, a Friday 9 Oct close is perfectly current.

Run:  python tests/test_stale_series_cannot_appear_current.py
"""

import sys
from datetime import date, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.series_provenance import (                        # noqa: E402
    DELAYED, NO_DATA, PUBLICATION_CUTOFF_HOUR, STALE,
    STALE_AFTER_SESSIONS,
    STALE_SUPPRESSED_FIELDS, containment_version, freshness_status,
    is_stale, last_expected_session, sessions_behind, suppress_if_stale,
    suppress_if_unverified)

#: Market-local datetimes. Freshness depends on the HOUR, not just the day:
#: before the publication cutoff today's close is not yet expected, after it
#: it is. A date alone cannot express that.
SAT = datetime(2026, 10, 10, 12, 0)          # Saturday midday
MON_AM = datetime(2026, 10, 12, 9, 0)        # Monday, before the close
MON_PM = datetime(2026, 10, 12, 20, 0)       # Monday evening, after cutoff
TUE_AM = datetime(2026, 10, 13, 9, 0)


def _row(code, price_date, **over):
    v = dict(index_code=code, display_name=code, price_date=price_date,
             close_price=7304.8, return_1d=0.001, return_1w=0.01,
             return_1m=0.02, return_3m=0.03, return_6m=0.04, return_1y=0.0336,
             return_ytd=0.05, high_52w=7800.0, low_52w=6900.0)
    v.update(over)
    return v


# ── Weekends must not raise false alarms ────────────────────────────────────

def test_a_friday_close_is_current_on_the_weekend():
    """The live case: ASX200 at 2026-10-09, checked on Saturday."""
    assert last_expected_session(SAT) == date(2026, 10, 9)
    assert not is_stale(date(2026, 10, 9), SAT)


def test_a_friday_close_is_still_current_on_monday_morning():
    """Before the cutoff, Monday's close is not yet published."""
    assert last_expected_session(MON_AM) == date(2026, 10, 9)
    assert sessions_behind(date(2026, 10, 9), MON_AM) == 0


def test_monday_evening_expects_mondays_close():
    """The bug in the first version of this rule.

    It never returned today, so on Monday evening -- hours after Monday's
    close was published -- it still expected Friday. Every index would read
    current while a full session behind, permanently.
    """
    assert last_expected_session(MON_PM) == date(2026, 10, 12), (
        "after the publication cutoff, today's close must be expected")
    assert sessions_behind(date(2026, 10, 9), MON_PM) == 1, (
        "Friday's data on Monday evening is one session behind, not current")


def test_the_cutoff_is_the_hinge():
    """Same calendar day, different expectation, decided only by the hour."""
    before = datetime(2026, 10, 12, PUBLICATION_CUTOFF_HOUR - 1, 59)
    after = datetime(2026, 10, 12, PUBLICATION_CUTOFF_HOUR, 0)
    assert last_expected_session(before) == date(2026, 10, 9)
    assert last_expected_session(after) == date(2026, 10, 12)


def test_todays_close_is_not_expected_before_the_cutoff():
    """Otherwise every index reads stale each morning, and an alarm that
    fires daily is one nobody reads."""
    assert last_expected_session(TUE_AM) == date(2026, 10, 12)


def test_the_tolerance_governs_withholding_and_is_not_a_holiday_calendar():
    """What the threshold actually does, stated without overclaiming.

    It decides when figures are WITHHELD. There is no operational alerting
    on freshness in this system, so nothing here should be described as an
    alert delay. Holidays are not modelled, so a closure consumes part of the
    tolerance, and three sessions is not a judgement that three sessions of
    silence is fine -- the defect this catches ran to roughly 94.
    """
    assert STALE_AFTER_SESSIONS == 3
    assert sessions_behind(date(2026, 10, 7), SAT) == 2
    assert not is_stale(date(2026, 10, 7), SAT)


def test_the_boundary_is_in_sessions_not_days():
    assert sessions_behind(date(2026, 10, 6), SAT) == STALE_AFTER_SESSIONS
    assert not is_stale(date(2026, 10, 6), SAT)
    assert is_stale(date(2026, 10, 5), SAT)


# ── The defect ──────────────────────────────────────────────────────────────

def test_the_asx100_figures_are_withheld():
    out = suppress_if_stale(_row("ASX100", "2026-05-29"), SAT)
    assert out["data_status"] == STALE
    leaked = [f for f in STALE_SUPPRESSED_FIELDS if out.get(f) is not None]
    assert not leaked, f"a stale series still publishes: {leaked}"


def test_the_last_close_and_date_are_kept_as_history():
    """Withholding them would destroy true information.

    The close IS what the index was on 29 May. Only the figures that imply
    "as of now" are wrong -- the returns, and the 52-week extremes, which
    mean "52 weeks to today" and were last computed in May.
    """
    out = suppress_if_stale(_row("ASX100", "2026-05-29"), SAT)
    assert out["close_price"] == 7304.8
    assert out["price_date"] == "2026-05-29"


def test_how_far_behind_is_published():
    out = suppress_if_stale(_row("ASX100", "2026-05-29"), SAT)
    assert out["sessions_behind"] > 90, (
        "a consumer should not have to subtract dates and guess at weekends")


def test_a_current_series_is_untouched():
    row = _row("ASX200", "2026-10-09")
    assert suppress_if_stale(row, SAT) == row
    assert "data_status" not in suppress_if_stale(row, SAT)


def test_staleness_is_measured_not_declared():
    """No allow-list. The NEXT series to go quiet is caught too.

    A hand-maintained list can only contain problems already found, which is
    how ASX100 went unnoticed for four months.
    """
    unknown = suppress_if_stale(_row("NEVERSEEN", "2026-01-02"), SAT)
    assert unknown["data_status"] == STALE, (
        "only known-bad codes are checked, so a new stale series is invisible")


def test_a_series_with_no_prices_reports_no_data():
    """This test previously asserted the opposite of its own name.

    It was called "a missing date is not treated as fresh" and asserted the
    row passed through UNTOUCHED -- which leaves data_status unset, i.e.
    exactly "fresh". The name described the property; the assertion verified
    its negation.

    Never-published and stopped-publishing are different facts with
    different causes -- a dead identifier versus a source gone quiet -- so
    they get different statuses.
    """
    out = suppress_if_stale(_row("X", None), SAT)
    assert out["data_status"] == NO_DATA
    assert out.get("sessions_behind") is None, (
        "there is no date to count back from, and 0 would read as up to date")
    assert freshness_status(None, SAT) == NO_DATA
    assert NO_DATA != STALE, "never-published collapsed into stopped"


# ── Provenance outranks staleness ───────────────────────────────────────────

def test_an_unverified_series_is_not_relabelled_stale():
    """AXJO is current and wrong; ASX100 is right and old.

    Calling the first "stale" would understate it -- stale implies the
    figures were correct when fresh, and AXJO's never were.
    """
    out = suppress_if_stale(
        suppress_if_unverified("AXJO", _row("AXJO", "2026-10-09")), SAT)
    assert out["data_status"] == "series_provenance_unverified"
    assert out["close_price"] is None, "provenance suppression was undone"


def test_an_unverified_and_old_series_keeps_the_stronger_label():
    out = suppress_if_stale(
        suppress_if_unverified("AXJO", _row("AXJO", "2025-01-02")), SAT)
    assert out["data_status"] == "series_provenance_unverified"


# ── Wiring ──────────────────────────────────────────────────────────────────

ROUTE = BACKEND / "app" / "api" / "v1" / "routes" / "indices_funds.py"


def test_list_and_detail_both_apply_it():
    src = ROUTE.read_text(encoding="utf-8")
    assert src.count("present_index(") >= 3, (
        "the helper is defined but not used at both endpoints")
    helper = src[src.index("def present_index"):]
    helper = helper[:helper.index("INDEX_META")]
    assert "suppress_if_unverified" in helper and "suppress_if_stale" in helper
    assert helper.index("suppress_if_unverified") > helper.index("suppress_if_stale"), (
        "staleness must wrap provenance, so provenance is applied first")


def test_history_is_labelled_not_emptied():
    """Stale history is real data. Emptying the chart would destroy it.

    This differs from an unverified series, whose points are withheld because
    they measure something other than what they claim.
    """
    src = ROUTE.read_text(encoding="utf-8")
    hist = src[src.index("async def get_index_history"):]
    assert "freshness_status(" in hist, (
        "the history endpoint never evaluates freshness")
    assert '"data_status": status' in hist
    assert '"history": [' in hist, "the history payload was removed entirely"


def test_the_cache_key_covers_the_staleness_rules():
    """Otherwise a cached pre-containment response serves for an hour."""
    import app.core.series_provenance as sp
    before = containment_version()
    original = sp.STALE_AFTER_SESSIONS
    sp.STALE_AFTER_SESSIONS = original + 1
    try:
        assert containment_version() != before, (
            "changing the staleness threshold does not change the cache key, "
            "so stale figures would keep being served from cache")
    finally:
        sp.STALE_AFTER_SESSIONS = original


# ── The UI tells the two apart ──────────────────────────────────────────────

FRONTEND = BACKEND.parent / "frontend"
LIST_PAGE = FRONTEND / "app" / "indices" / "page.tsx"
DETAIL_PAGE = FRONTEND / "app" / "indices" / "[code]" / "IndexDetailContent.tsx"


def _code_only(src: str) -> str:
    import re
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def test_stale_and_unverified_render_differently():
    """One shared message would understate the unverified case.

    A stale series was right when published and stopped updating. An
    unverified one was never measuring what it claimed. Telling a subscriber
    the second is merely "not updating" would be false.
    """
    for page in (LIST_PAGE, DETAIL_PAGE):
        src = _code_only(page.read_text(encoding="utf-8"))
        assert "'stale'" in src, f"{page.name} never checks for stale"
        assert "'series_provenance_unverified'" in src, (
            f"{page.name} never checks for unverified")
        assert "data_status &&" not in src, (
            f"{page.name} still has a catch-all data_status branch, which "
            f"would give both defects the same message")


def test_the_stale_chart_keeps_its_history():
    """Emptying it would destroy real data.

    Only the unverified case empties the chart, because those points measure
    something other than what they claim.
    """
    src = _code_only(DETAIL_PAGE.read_text(encoding="utf-8"))
    assert "unavailable={p?.data_status === 'series_provenance_unverified'}" in src, (
        "the chart is emptied for any data_status, so a stale series would "
        "lose its genuine history")
    assert "stale={p?.data_status === 'stale'}" in src
    assert "it is not current" in src, (
        "the stale chart renders with no notice, so it reads as current")


# ── Freshness and alert tolerance are separate ──────────────────────────────

def test_zero_sessions_behind_is_the_only_current():
    """Anything that has missed an expected session is marked.

    An earlier version used one threshold for both jobs, so a series 1-3
    sessions behind reported data_status None -- i.e. "current". The clock
    was right and the label was still wrong.
    """
    assert freshness_status(date(2026, 10, 9), SAT) is None
    for behind, d in ((1, date(2026, 10, 8)), (2, date(2026, 10, 7)),
                      (3, date(2026, 10, 6))):
        assert sessions_behind(d, SAT) == behind
        assert freshness_status(d, SAT) == DELAYED, (
            f"{behind} session(s) behind still reports as current")


def test_mondays_missing_close_shows_delayed_after_the_cutoff():
    """The case that prompted this split."""
    assert freshness_status(date(2026, 10, 9), MON_PM) == DELAYED
    out = suppress_if_stale(_row("ASX200", "2026-10-09"), MON_PM)
    assert out["data_status"] == DELAYED
    assert out["sessions_behind"] == 1


def test_the_tolerance_governs_withholding_only():
    """Delayed is marked and still shown; stale is marked and withheld.

    Blanking a page because of a public holiday would make the surface
    useless, and a surface people stop reading is the failure mode this
    whole effort is about.
    """
    delayed = suppress_if_stale(_row("X", "2026-10-07"), SAT)
    assert delayed["data_status"] == DELAYED
    assert delayed["return_1y"] == 0.0336, "a delayed series had figures withheld"
    assert delayed["high_52w"] == 7800.0

    stale = suppress_if_stale(_row("X", "2026-10-05"), SAT)
    assert stale["data_status"] == STALE
    assert stale["return_1y"] is None and stale["high_52w"] is None
    assert stale["close_price"] == 7304.8, "the last close must survive"


def test_the_boundary_between_delayed_and_stale_is_the_tolerance():
    assert freshness_status(date(2026, 10, 6), SAT) == DELAYED   # 3 behind
    assert freshness_status(date(2026, 10, 5), SAT) == STALE     # 4 behind
    assert not is_stale(date(2026, 10, 6), SAT)
    assert is_stale(date(2026, 10, 5), SAT)


def test_the_cache_key_changes_at_the_cutoff():
    """A response cached at 17:30 must not assert "current" at 18:30.

    The list key embeds the expected session, so crossing the cutoff changes
    the key and forces re-evaluation rather than serving a stale verdict for
    the remainder of the hour TTL.
    """
    src = ROUTE.read_text(encoding="utf-8")
    block = src[src.index('_key = make_key("indices"'):]
    block = block[:block.index("cached = await cache_get")]
    assert "last_expected_session(market_now())" in block, (
        "the indices cache key does not include the expected session, so a "
        "freshness verdict can outlive the cutoff that re-decides it")
    before = datetime(2026, 10, 12, PUBLICATION_CUTOFF_HOUR - 1, 30)
    after = datetime(2026, 10, 12, PUBLICATION_CUTOFF_HOUR, 30)
    assert last_expected_session(before) != last_expected_session(after), (
        "the key component does not change across the cutoff")


def test_the_history_endpoint_reports_the_same_three_states():
    src = ROUTE.read_text(encoding="utf-8")
    hist = src[src.index("async def get_index_history"):]
    assert "freshness_status(" in hist, (
        "history still uses a two-state stale check, so a delayed series "
        "reports as current there while the list says delayed")
    assert '"data_status": status' in hist


def test_history_status_does_not_depend_on_the_window():
    """Found by the v11.2.19 post-deploy check, and it was my bug.

    The status was derived from the WINDOWED rows, so a series stale enough
    to fall entirely outside the requested window produced no rows and
    therefore no status: ASX100, 95 sessions behind, reported "current" on
    history while the list said "stale".

    Absence of rows in a window is not absence of a freshness problem. It is
    the strongest evidence of one.
    """
    src = ROUTE.read_text(encoding="utf-8")
    hist = src[src.index("async def get_index_history"):]
    hist = hist[:hist.index("# ── ETF")] if "# ── ETF" in hist else hist
    assert "max(price_date)" in hist, (
        "history freshness is not taken from the series' latest price")
    assert "rows[-1]" not in hist, (
        "history freshness is still derived from the windowed rows, so a "
        "sufficiently stale series reports no status at all")
    assert "freshness_status(latest" in hist


def test_an_empty_window_with_an_older_latest_price_still_reports_stale():
    """The v11.2.19 defect, asserted behaviourally rather than structurally.

    Checking that `rows[-1]` is absent from the source proves only that the
    old spelling is gone. The property is: when the requested window
    contains no rows AND the series' latest price is old, the answer is
    still "stale".

    The second assertion reconstructs the old derivation to show it really
    did produce None, so this is a contrast rather than a lone claim.
    """
    windowed_rows = []                      # a 30-day window, ASX100
    latest = date(2026, 5, 29)              # its actual last price

    assert freshness_status(latest, SAT) == STALE, (
        "the series-latest derivation does not report stale")

    old_derivation = (freshness_status(windowed_rows[-1], SAT)
                      if windowed_rows else None)
    assert old_derivation is None, (
        "the control does not reproduce the defect, so this test proves "
        "nothing about the fix")


def test_an_empty_window_on_a_current_series_is_not_stale():
    """A narrow window over a holiday break has no rows either.

    Without this, the fix could have been "no rows means stale", which would
    mislabel a perfectly current series whenever someone asked for a short
    window.
    """
    assert freshness_status(date(2026, 10, 9), SAT) is None


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
            except Exception as exc:                             # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
