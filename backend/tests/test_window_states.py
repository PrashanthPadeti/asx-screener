"""
Four causes, one blank
======================
A price window can be empty for four reasons, and before v11.2.63 all four
reached the customer as the same dash:

    no close near the window's start      about the company's trading
    not enough history                    about the company's trading
    an unreconciled corporate action      about OUR data -- go reconcile it
    past the column's ceiling             about OUR schema -- go widen it

After canonical run 30 published cleanly on 28 Oct 2026 -- "state/value
contradictions: 0" -- 608 of 2,113 served stocks carried a NULL return_1y
with no entry at all, 190 a NULL return_6m, 87 a NULL return_3m.

These tests cover the producer side: that each cause is distinguished, and
that the explanation is built from the same anchor rule as the number it
explains.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.applicability import Applicability, Cause   # noqa: E402
from compute.engine.return_windows import (                     # noqa: E402
    ALL_WINDOWS, anchor_positions,
)
from compute.engine.window_states import (                      # noqa: E402
    EXTREME_COLUMNS, anchor_for, assess_row, presence, window_assessment,
)

START = date(2020, 1, 1)
METRICS = list(ALL_WINDOWS) + ["return_ytd"] + list(EXTREME_COLUMNS)


def _dates(n: int, start: date = START) -> pd.Series:
    return pd.Series([pd.Timestamp(start + timedelta(days=i)) for i in range(n)])


def _all(value: bool) -> dict:
    return {m: value for m in METRICS}


# ── The explanation must match the producer ─────────────────────────────────

def test_the_explanation_matches_the_producer():
    """anchor_for() recomputes for one row what anchor_positions() computes
    for all of them. If they ever disagree, the sidecar explains a value the
    producer did not compute -- an explanation worse than none, because it
    reads as authoritative.

    Checked over every window and a deliberately gappy series.
    """
    days = list(range(400)) + list(range(700, 1400))
    dates = pd.Series([pd.Timestamp(START + timedelta(days=d)) for d in days])

    for metric, (offset, grace) in ALL_WINDOWS.items():
        pos = anchor_positions(dates, offset, grace)
        for row in (0, 5, 399, 400, 700, len(dates) - 1):
            _, anchor = anchor_for(dates, row, offset, grace)
            if pos[row] < 0:
                assert anchor is None, (
                    f"{metric} row {row}: the producer found no anchor, the "
                    f"explanation found {anchor}")
            else:
                assert anchor == dates[pos[row]], (
                    f"{metric} row {row}: producer anchored at "
                    f"{dates[pos[row]]}, explanation at {anchor}")


# ── The four causes ─────────────────────────────────────────────────────────

def test_an_applicable_window_gets_no_entry():
    """Absence of an entry IS the applicable signal. An entry beside a
    populated value is as much a contract violation as a NULL without one."""
    dates = _dates(4000)
    out = assess_row(dates, len(dates) - 1, _all(True), _all(True), _all(True))
    assert out == {}


def test_too_little_history_says_so_and_names_the_date():
    dates = _dates(200)
    out = assess_row(dates, len(dates) - 1, _all(False), _all(False), _all(False))

    entry = out["return_1y"]
    assert entry["state"] == Applicability.INSUFFICIENT_DATA.value
    assert entry["cause"] == Cause.INSUFFICIENT_HISTORY.value
    target = (dates.iloc[-1] - ALL_WINDOWS["return_1y"][0]).date().isoformat()
    assert target in entry["reason"], (
        f"the reason does not name the date it looked for: {entry['reason']}")


def test_a_withheld_window_blames_the_corporate_action_not_the_company():
    """Computed, then removed by withholding. SOURCE_MISSING because what is
    missing is the split record -- not the price, and not the company's
    trading."""
    dates = _dates(4000)
    out = assess_row(dates, len(dates) - 1,
                     computed=_all(True),
                     after_withholding=_all(False),
                     final=_all(False))

    entry = out["return_1y"]
    assert entry["state"] == Applicability.UNAVAILABLE.value
    assert entry["cause"] == Cause.SOURCE_MISSING.value
    assert "corporate action" in entry["reason"]


def test_a_value_the_column_cannot_hold_blames_the_schema():
    """Survived withholding, removed by the column limit. It clears by
    widening a column and never by waiting, so INSUFFICIENT_HISTORY would
    blame the company for our ceiling."""
    dates = _dates(4000)
    out = assess_row(dates, len(dates) - 1,
                     computed=_all(True),
                     after_withholding=_all(True),
                     final=_all(False))

    entry = out["return_1y"]
    assert entry["state"] == Applicability.UNAVAILABLE.value
    assert entry["cause"] == Cause.COMPUTATION_UNSUPPORTED.value


def test_the_four_causes_are_actually_different():
    """The point of the whole module. If any two collapse to one payload,
    the sidecar has reproduced the blank it replaced."""
    dates = _dates(4000)
    short = _dates(200)

    payloads = {
        "no_history": assess_row(short, len(short) - 1,
                                 _all(False), _all(False), _all(False)),
        "withheld": assess_row(dates, len(dates) - 1,
                               _all(True), _all(False), _all(False)),
        "unstorable": assess_row(dates, len(dates) - 1,
                                 _all(True), _all(True), _all(False)),
    }
    seen = {name: (p["return_1y"]["state"], p["return_1y"]["cause"])
            for name, p in payloads.items()}
    assert len(set(seen.values())) == 3, f"causes collapsed: {seen}"


# ── return_ytd, which has no fixed window ───────────────────────────────────

def test_a_series_starting_this_year_explains_its_missing_ytd():
    """return_ytd runs from the last close of the PREVIOUS calendar year, so
    a series that begins inside the current one has no anchor at all.

    This metric is governed and is not in ALL_WINDOWS, so it needs its own
    branch. It was missed on the first pass and caught by the test comparing
    the governed set against what the producer can assess -- under the live
    contract it would have been written as NULL with no entry.
    """
    dates = pd.Series([pd.Timestamp(date(2026, 3, 1) + timedelta(days=i))
                       for i in range(60)])
    out = assess_row(dates, len(dates) - 1, _all(False), _all(False), _all(False))

    entry = out["return_ytd"]
    assert entry["state"] == Applicability.INSUFFICIENT_DATA.value
    assert entry["cause"] == Cause.INSUFFICIENT_HISTORY.value
    assert "2026-01-01" in entry["reason"], entry["reason"]


def test_a_ytd_spanning_a_corporate_action_says_so():
    dates = pd.Series([pd.Timestamp(date(2025, 1, 1) + timedelta(days=i))
                       for i in range(500)])
    out = assess_row(dates, len(dates) - 1,
                     computed=_all(True),
                     after_withholding=_all(False),
                     final=_all(False))

    entry = out["return_ytd"]
    assert entry["cause"] == Cause.SOURCE_MISSING.value
    assert "year to date" in entry["reason"]


def test_an_applicable_ytd_gets_no_entry():
    dates = _dates(4000)
    out = assess_row(dates, len(dates) - 1, _all(True), _all(True), _all(True))
    assert "return_ytd" not in out


# ── The 52-week extremes ────────────────────────────────────────────────────

def test_a_short_series_explains_its_missing_52_week_extreme():
    dates = _dates(100)
    out = assess_row(dates, len(dates) - 1, _all(False), _all(False), _all(False))
    for metric in EXTREME_COLUMNS:
        entry = out[metric]
        assert entry["cause"] == Cause.INSUFFICIENT_HISTORY.value
        assert "99 days" in entry["reason"], entry["reason"]


def test_presence_reads_the_storage_column_for_the_extremes():
    """week_52_high is stored as high_52w. Keying presence by the canonical
    name against the frame would report both extremes absent on every row,
    and every one of them would acquire a false explanation."""
    dates = _dates(5)
    df = pd.DataFrame({"date": dates,
                       "high_52w": np.full(5, 2.0),
                       "low_52w": np.full(5, 1.0)})
    got = presence(df, 4)
    assert got["week_52_high"] is True
    assert got["week_52_low"] is True


# ── Round trip, for the canonical writer ────────────────────────────────────

def test_an_entry_rebuilds_as_a_suppressed_assessment():
    payload = {"return_1y": {"state": "insufficient_data",
                             "cause": "insufficient_history",
                             "reason": "no close within 7 days of 2025-10-27"}}
    a = window_assessment("return_1y", None, payload)
    assert a.state is Applicability.INSUFFICIENT_DATA
    assert a.cause is Cause.INSUFFICIENT_HISTORY
    assert a.value is None
    assert not a.ok


def test_a_value_with_no_entry_rebuilds_as_applicable():
    a = window_assessment("return_1y", 7.6, {})
    assert a.ok and a.value == 7.6


def test_an_unassessed_absence_is_not_called_applicable():
    """A row written before this contract existed has no entry and no value.
    Calling that applicable would publish a NULL as though it were a
    considered answer."""
    a = window_assessment("return_1y", None, None)
    assert not a.ok
    assert a.state is Applicability.UNAVAILABLE
    assert "no recorded reason" in a.reason


def test_every_governed_price_metric_is_covered():
    """Population check. A governed metric this module never assesses would
    reach the writer with no entry and no value, and be published as an
    unexplained null by the statement written to prevent them."""
    dates = _dates(100)
    out = assess_row(dates, len(dates) - 1, _all(False), _all(False), _all(False))
    missing = [m for m in METRICS if m not in out]
    assert not missing, f"absent but unexplained: {missing}"


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
        except Exception as e:                                # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
