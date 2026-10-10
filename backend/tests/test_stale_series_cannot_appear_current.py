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
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.series_provenance import (                        # noqa: E402
    STALE, STALE_AFTER_SESSIONS, STALE_SUPPRESSED_FIELDS, containment_version,
    is_stale, last_expected_session, sessions_behind, suppress_if_stale,
    suppress_if_unverified)

SAT = date(2026, 10, 10)
MON = date(2026, 10, 12)
TUE = date(2026, 10, 13)


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


def test_a_friday_close_is_still_current_on_monday():
    assert last_expected_session(MON) == date(2026, 10, 9)
    assert not is_stale(date(2026, 10, 9), MON)
    assert sessions_behind(date(2026, 10, 9), MON) == 0


def test_today_is_never_expected():
    """A session's data lands after the close.

    Expecting today's close would mark every index stale each morning, and an
    alarm that fires daily is one nobody reads.
    """
    assert last_expected_session(TUE) < TUE


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


def test_a_missing_date_is_not_treated_as_fresh():
    row = _row("X", None)
    assert suppress_if_stale(row, SAT) == row, (
        "a null date must pass through untouched rather than being scored")
    assert sessions_behind(None, SAT) > 1000


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
    assert 'is_stale(' in hist, "the history endpoint never evaluates staleness"
    assert '"data_status": "stale" if stale else None' in hist
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
