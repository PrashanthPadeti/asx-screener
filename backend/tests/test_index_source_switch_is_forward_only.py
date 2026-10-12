#!/usr/bin/env python
"""
A source switch must not rewrite another provider's history
===========================================================
ASX100 stopped publishing on 2026-05-29 while every other index stayed
current. EODHD's `ATOI.INDX` carries the series and is current, so the source
switches -- but switching provider must not silently replace 778 rows that a
different provider produced.

The boundary is an explicit effective date. Rows dated before it are never
written. The fetch still reaches 400 days further back, because a one-year
return needs a year of context, but that context is for COMPUTATION only.
Persisting it would be the gap backfill, which is a separate decision.

What the identity evidence does and does not support
----------------------------------------------------
Every stored ASX100 date since 2026-01-01 exists in `ATOI.INDX` (103/103),
96 of those closes agree to within 0.01, and the `AXJO` control differs by
~1,427 points. That supports identity **for the tested period**.

It does not validate all 778 stored rows: 675 predate 2026 and were never
compared. And seven of the 103 differ by up to 38.2 points (~0.5%), scattered
across January-March, in both directions. Cause unresolved.

Run:  python tests/test_index_source_switch_is_forward_only.py
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SRC = (BACKEND / "compute" / "engine" / "index_prices.py").read_text(
    encoding="utf-8")


def _load():
    """Load just the source model, without importing the producer.

    The module pulls in pandas and the DB session at import; the rules under
    test are pure and must be exercisable without either.
    """
    import ast
    tree = ast.parse(SRC)
    wanted = []
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == "IndexSource":
            wanted.append(n)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            t = ast.unparse(n)
            if t.startswith(("SOURCES", "ASX100_SWITCH_DATE", "TICKER_MAP")):
                wanted.append(n)
    ns = {}
    exec("from dataclasses import dataclass\nfrom datetime import date\n", ns)
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "<m>", "exec"), ns)
    return ns


NS = _load()
SOURCES = NS["SOURCES"]
SWITCH = NS["ASX100_SWITCH_DATE"]


# ── Only ASX100 moves ───────────────────────────────────────────────────────

def test_only_asx100_changes_provider():
    """An isolated switch. Every other index keeps Yahoo.

    A general migration is the separate sourcing-track design and must not
    arrive under a one-index repair.
    """
    moved = [c for c, s in SOURCES.items() if s.provider != "yahoo"]
    assert moved == ["ASX100"], f"unexpected providers changed: {moved}"
    assert SOURCES["ASX100"].symbol == "ATOI.INDX"
    assert SOURCES["ASX100"].provider == "eodhd"


def test_every_other_index_keeps_its_yahoo_symbol():
    expected = {"ASX20": "^ATLI", "ASX50": "^AFLI", "ASX200": "^AXJO",
                "ASX300": "^AXKO", "AXFJ": "^AXFJ", "AXMJ": "^AXMJ",
                "AXEJ": "^AXEJ", "AXHJ": "^AXHJ"}
    actual = {c: s.symbol for c, s in SOURCES.items() if s.provider == "yahoo"}
    assert actual == expected, f"Yahoo mapping changed: {actual}"


def test_axjo_is_still_absent():
    """The v11.2.18 containment must survive this refactor."""
    assert "AXJO" not in SOURCES


def test_the_ticker_map_is_derived_not_duplicated():
    """Two hand-maintained populations drift. One is authoritative."""
    assert "code: src.symbol for code, src in SOURCES.items()" in SRC, (
        "TICKER_MAP is no longer derived from SOURCES, so the two can drift")
    assert NS["TICKER_MAP"] == {c: s.symbol for c, s in SOURCES.items()
                                if s.provider == "yahoo"}


# ── Forward-only ────────────────────────────────────────────────────────────

def test_the_switch_date_is_explicit():
    """Not "today", not implied by the window. One reviewable value."""
    assert isinstance(SWITCH, date)
    assert SOURCES["ASX100"].effective_from == SWITCH


def test_nothing_before_the_effective_date_is_writable():
    """The whole point. 778 rows produced by Yahoo stay untouched."""
    s = SOURCES["ASX100"]
    for start in (date(2023, 5, 5), date(2026, 1, 1), date(2026, 5, 29),
                  SWITCH - timedelta(days=1)):
        assert s.first_writable(start) == SWITCH, (
            f"a run starting {start} would write rows before {SWITCH}")


def test_a_later_start_is_not_dragged_backwards():
    """first_writable clamps forward only; it must never widen a window."""
    later = SWITCH + timedelta(days=20)
    assert SOURCES["ASX100"].first_writable(later) == later


def test_an_unswitched_index_is_unconstrained():
    """Yahoo indices have always been the source, so nothing is withheld."""
    for code in ("ASX200", "AXHJ"):
        assert SOURCES[code].effective_from is None
        assert SOURCES[code].first_writable(date(2023, 1, 1)) == date(2023, 1, 1)


def test_the_gap_is_not_backfilled():
    """2026-05-30 .. the switch date stays empty by construction.

    Those ~95 sessions are real missing data and EODHD has them, but writing
    them is a separate decision. If this test fails, the switch has silently
    become a backfill.
    """
    s = SOURCES["ASX100"]
    gap_day = date(2026, 6, 15)
    assert gap_day < SWITCH
    assert s.first_writable(date(2026, 1, 1)) > gap_day, (
        "a run would write rows inside the May-October gap")


def test_the_loop_filters_on_first_writable_not_start_date():
    """The rule has to be applied, not merely available.

    A `first_writable` nobody calls is a comment.
    """
    body = SRC[SRC.index("async def run("):]
    assert "writable_from = source.first_writable(start_date)" in body
    assert "if writable_from <= r[\"price_date\"] <= target_date" in body, (
        "rows are still filtered from start_date, so the effective date is "
        "declared but not enforced")


def test_withheld_rows_are_reported():
    """Silently dropping rows is how a boundary becomes invisible."""
    body = SRC[SRC.index("async def run("):]
    assert "withheld" in body and "forward-only" in body


# ── Provenance and partial-failure reporting ────────────────────────────────

def test_the_run_logs_provider_and_symbol():
    """A source change should be visible in the run that first used it."""
    body = SRC[SRC.index("async def run("):]
    assert "source.provider" in body and "source.effective_from" in body, (
        "the run does not record which provider served each index")


def test_partial_failure_reporting_survives():
    """The tally must still count refusals and empties per index."""
    body = SRC[SRC.index("async def run("):]
    for call in ("tally.refusal(", "tally.nothing_available(",
                 "tally.obtained(", "tally.verify()"):
        assert call in body, f"{call} disappeared in the switch"
    assert "expected=len(SOURCES)" in SRC, (
        "expected is no longer the full population")


def test_the_eodhd_fetcher_honours_the_producer_contract():
    """Refused and empty are different events and must stay distinguishable."""
    fn = SRC[SRC.index("def fetch_eodhd_index("):]
    fn = fn[:fn.index("def fetch_for(")]
    assert "raise SourceRefused(" in fn, "a refusal is not distinguishable"
    assert "return None" in fn, "an empty result has no path"
    assert "429" in fn, "rate limiting is not treated as a refusal"


def test_the_eodhd_fetcher_does_not_log_the_url():
    """An exception's text can carry the request URL, and the URL carries the
    api_token. v11.2.17 redacts at the sink; this avoids the problem at the
    source as well."""
    fn = SRC[SRC.index("def fetch_eodhd_index("):]
    fn = fn[:fn.index("def fetch_for(")]
    assert "type(exc).__name__" in fn
    assert re.search(r"log\.\w+\([^)]*\{exc\}", fn) is None, (
        "an exception is interpolated into a log line")


# ── Late publication must not lose the first session ────────────────────────
#
# The job fires ~06:30 UTC, about 17:30 Sydney, and the ASX closes at 16:00.
# If the provider has not published that day's close yet, the run writes
# nothing for it. The session must then be picked up by a later run rather
# than silently skipped -- and still without admitting pre-switch rows.

BACKFILL_DAYS_DEFAULT = 1


def _window(target, backfill_days=BACKFILL_DAYS_DEFAULT):
    """Reproduces run(): start_date = target_date - backfill_days."""
    return target - timedelta(days=backfill_days), target


def _writable_dates(target, backfill_days=BACKFILL_DAYS_DEFAULT):
    start, end = _window(target, backfill_days)
    wf = SOURCES["ASX100"].first_writable(start)
    out, day = [], wf
    while day <= end:
        out.append(day)
        day += timedelta(days=1)
    return out


def test_a_late_first_session_is_ingested_on_the_following_run():
    """Publication misses the switch-date run; the next run still gets it."""
    missed = SWITCH
    next_run = SWITCH + timedelta(days=1)
    assert missed in _writable_dates(next_run), (
        "a session unpublished at its own run becomes unwritable on the next "
        "one, so it is lost rather than delayed")


def test_a_late_session_never_admits_pre_switch_rows():
    """Recovery must not widen the window backwards past the boundary."""
    for days_late in range(0, 6):
        dates = _writable_dates(SWITCH + timedelta(days=days_late))
        assert all(d >= SWITCH for d in dates), (
            f"a run {days_late} day(s) after the switch would write rows "
            f"before {SWITCH}")


def test_recovery_is_bounded_by_backfill_days():
    """A known limit, asserted so it is a decision rather than a surprise.

    With backfill_days=1 the window is [target-1, target], so a session is
    recoverable for exactly one extra run. Two runs late and it falls out of
    the window -- a pre-existing property of every index here, not something
    the source switch introduces. Raising backfill_days widens recovery for
    all of them.
    """
    assert SWITCH not in _writable_dates(SWITCH + timedelta(days=2)), (
        "the recovery horizon has changed; update this test and say so")
    assert SWITCH in _writable_dates(SWITCH + timedelta(days=5),
                                     backfill_days=5), (
        "a wider backfill window does not extend recovery as expected")


# ── Where returns come from ─────────────────────────────────────────────────

def test_returns_are_computed_from_the_fetched_frame_only():
    """Single-source per row, which is why the gap rows must be fetched.

    Computing a 1-year return from stored history would span the 95-session
    hole. Computing it from the fetched EODHD frame does not.
    """
    body = SRC[SRC.index("def compute_rows("):]
    body = body[:body.index("\ndef ", 1)]
    assert 'closes = df["close"]' in body
    assert "SELECT" not in body.upper(), (
        "compute_rows reads the database, so returns could mix stored and "
        "fetched sources within one figure")
    assert "_pct_return(closes" in body


def test_the_lookback_is_wide_enough_for_a_one_year_return():
    """252 trading days needs ~365 calendar days; the fetch asks for 400."""
    fn = SRC[SRC.index("def fetch_eodhd_index("):]
    fn = fn[:fn.index("def fetch_for(")]
    assert "timedelta(days=400)" in fn, (
        "the EODHD lookback no longer covers a 252-session return window")


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
            except Exception as exc:                           # noqa: BLE001
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
                failures.append(name)
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
