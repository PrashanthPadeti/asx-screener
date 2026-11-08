"""
A fresh frontier is not a complete series
=========================================
market.daily_prices held NO rows for 2, 3 and 4 November 2026. The freshness
check reported:

    OK  daily_prices  market.daily_prices.time = 2026-11-06
                      (0 weekdays behind, limit 1)
    FRESH — 4 observable output(s) current

Every word of that was true. max() was current because 5 and 6 November had
arrived; the three trading days behind them were missing, and a maximum is
structurally incapable of seeing a hole behind itself. Every window metric
computed that week — returns, moving averages, the 252-row lookbacks — ran
across the gap and was published under a run that passed its own read-back.

These tests assert the PROPERTY (every weekday in the window carries a row),
not the three dates that happened to be missing.

Run under pytest, or standalone:
    cd backend && python tests/test_freshness_continuity.py
"""

import ast
import sys
from datetime import date, datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.output_freshness import (  # noqa: E402
    ANCHORS, ALLOWED_DATE_EXPRS, Anchor, DAYS_UNAVAILABLE, classify,
    expected_weekdays, missing_weekdays, observed_days_sql,
)

CONSUMERS = (
    BACKEND / "scripts" / "assert_output_freshness.py",
    BACKEND / "app" / "api" / "v1" / "routes" / "admin.py",
)

PRICES = next(a for a in ANCHORS if a.job == "daily_prices")


def _whole_window(latest: date, span: int) -> set:
    return set(expected_weekdays(latest, span))


# ── The window itself ────────────────────────────────────────────────────────

def test_the_window_is_weekdays_ending_at_the_newest_observed_row():
    """Anchored at `latest`, never at today.

    A window ending today would report every morning before ingestion as a
    one-day gap. An instrument that fires daily is one an operator stops
    reading, which is how the September 2026 hole survived four days.
    """
    # Friday 6 Nov 2026 backwards: 6,5,4,3,2 Nov then 30,29,28,27,26 Oct.
    got = expected_weekdays(date(2026, 11, 6), 10)
    assert got[-1] == date(2026, 11, 6)
    assert got[0] == date(2026, 10, 26)
    assert len(got) == 10
    assert all(d.weekday() < 5 for d in got), "a weekend day entered the window"


def test_a_weekend_frontier_still_yields_weekdays():
    got = expected_weekdays(date(2026, 11, 8), 5)      # a Sunday
    assert all(d.weekday() < 5 for d in got)
    assert len(got) == 5


# ── The defect, as a property ────────────────────────────────────────────────

def test_a_hole_behind_a_current_frontier_is_stale():
    """The exact November shape: newest row current, three days absent."""
    latest = date(2026, 11, 6)
    present = _whole_window(latest, PRICES.continuity_weekdays)
    for gone in (date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)):
        present.discard(gone)

    # Evaluated on the Saturday, when lag alone was genuinely healthy.
    now = datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc)
    f = classify(PRICES, True, latest, now=now, observed_days=present)

    assert f.weekdays_behind == 0, (
        "lag must still read healthy — otherwise this test proves the lag "
        "check, not the continuity check")
    assert f.state == "stale", "a three-day hole was reported as current"
    assert f.faulty, "the gate would exit 0 over a three-day hole"
    assert f.missing_days == ["2026-11-02", "2026-11-03", "2026-11-04"]
    for d in ("2026-11-02", "2026-11-03", "2026-11-04"):
        assert d in f.reason, f"{d} is missing but is not named in the reason"


def test_a_whole_window_is_current_and_says_so():
    latest = date(2026, 11, 6)
    f = classify(PRICES, True, latest,
                 now=datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc),
                 observed_days=_whole_window(latest,
                                             PRICES.continuity_weekdays))
    assert f.state == "current"
    assert f.missing_days == [], (
        "an empty list means the window was checked and was whole; None "
        "would mean nobody looked, and the two must stay distinguishable")


def test_one_public_holiday_is_tolerated():
    """Weekday arithmetic, not an exchange calendar — stated, not hidden."""
    latest = date(2026, 11, 6)
    present = _whole_window(latest, PRICES.continuity_weekdays)
    present.discard(date(2026, 10, 27))
    f = classify(PRICES, True, latest,
                 now=datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc),
                 observed_days=present)
    assert f.state == "current", "a single closure day fired the alarm"
    assert f.missing_days == ["2026-10-27"], (
        "a tolerated absence must still be REPORTED; silence here would hide "
        "the first day of a growing gap")


def test_the_tolerance_cannot_absorb_the_defect():
    """A limit of 2 would have let the November gap through: three missing
    days minus two tolerated leaves one, which is under the limit."""
    assert PRICES.max_missing_weekdays < 3, (
        f"max_missing_weekdays={PRICES.max_missing_weekdays} would report "
        f"the three-day November hole as current")


# ── The check cannot be skipped by accident ──────────────────────────────────

def test_omitting_observed_days_raises_rather_than_passing():
    """Declared is not enforced.

    If a consumer forgets the parameter, the anchor must not quietly report
    `current` on a property nobody evaluated.
    """
    try:
        classify(PRICES, True, date(2026, 11, 6),
                 now=datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc))
    except ValueError as e:
        assert "continuity" in str(e) and "observed_days" in str(e)
    else:
        raise AssertionError(
            "an anchor declaring continuity was classified without its days")


def test_an_unreadable_window_is_an_instrument_defect_not_a_gap():
    """Failed-to-obtain is not cannot-exist.

    If the continuity query errors, an empty set would manufacture a ten-day
    gap out of a connection problem, and a whole set would hide a real one.
    Neither is an answer the check is entitled to give.
    """
    f = classify(PRICES, True, date(2026, 11, 6),
                 now=datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc),
                 observed_days=DAYS_UNAVAILABLE)
    assert f.state == "broken", (
        "an unreadable window was rendered as a verdict about the data")
    assert f.missing_days is None, (
        "missing_days must stay None when nothing was observed; a list would "
        "claim the window was examined")
    assert "unknown" in f.reason.lower()


def test_the_admin_consumer_does_not_fabricate_an_empty_window():
    """_scalar returns None on failure by design. The days helper must NOT
    follow that pattern — an empty set is a real and alarming answer, and
    handing it to the classifier on a query error would invent a gap."""
    src = (BACKEND / "app" / "api" / "v1" / "routes" / "admin.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_days")
    handlers = [h for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler)]
    assert handlers, "_days swallows nothing; a failure would abort the panel"
    returned = {ast.unparse(n.value) for h in handlers
                for n in ast.walk(h) if isinstance(n, ast.Return) and n.value}
    assert returned == {"DAYS_UNAVAILABLE"}, (
        f"_days returns {returned} on failure; only the sentinel keeps "
        f"'the query did not run' distinguishable from 'the window is empty'")
    assert "begin_nested" in ast.unparse(fn), (
        "_days runs without a SAVEPOINT; one failed query would abort the "
        "transaction and take the rest of /system-health with it")


def test_both_consumers_pass_observed_days():
    """Structural, not textual: the call site is read from the AST.

    Two surfaces evaluate this registry — the cron gate and /system-health.
    A refactor that drops the argument from one of them would leave a green
    panel over a gapped series, and the runtime guard above only fires for
    anchors that declare continuity today.
    """
    for path in CONSUMERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") == "classify"]
        assert calls, f"{path.name} no longer calls classify()"
        for call in calls:
            kwargs = {k.arg for k in call.keywords}
            assert "observed_days" in kwargs, (
                f"{path.name}:{call.lineno} calls classify() without "
                f"observed_days; anchors declaring continuity would raise, "
                f"and ones that do not would go unchecked")


def test_the_price_anchor_actually_declares_continuity():
    """The population check. A perfect mechanism watching nothing is the
    failure mode this project keeps rediscovering."""
    assert PRICES.continuity_weekdays, (
        "market.daily_prices declares no continuity window, so none of the "
        "machinery above runs against the table it was built for")
    assert PRICES.continuity_weekdays >= 5


# ── SQL construction ─────────────────────────────────────────────────────────

def test_the_date_expression_must_be_allowlisted():
    rogue = Anchor("x", "market.daily_prices", "time", 24,
                   "test", continuity_weekdays=5,
                   date_expr="(time AT TIME ZONE 'Australia/Sydney')::date")
    try:
        observed_days_sql(rogue)
    except ValueError as e:
        assert "ALLOWED_DATE_EXPRS" in str(e)
    else:
        raise AssertionError("an anchor introduced arbitrary SQL")


def test_the_price_anchor_recovers_the_staging_date_at_a_fixed_offset():
    """The same expression transform_prices wrote the rows with.

    'Australia/Sydney' would shift by an hour across a DST boundary and can
    move a row's calendar date at the edges, which would read as a gap.
    """
    assert PRICES.date_expr in ALLOWED_DATE_EXPRS
    assert "+10:00" in PRICES.date_expr
    assert "Sydney" not in PRICES.date_expr
    sql = observed_days_sql(PRICES)
    assert "DISTINCT" in sql and "market.daily_prices" in sql


def test_the_lookback_covers_the_whole_window():
    """Calendar days must contain the requested weekdays with slack at both
    ends, or the query returns less than the window asks about and absent
    days would be invented."""
    sql = observed_days_sql(PRICES)
    days = int(sql.split("interval '")[1].split(" days")[0])
    span = expected_weekdays(date(2026, 11, 6), PRICES.continuity_weekdays)
    assert days >= (span[-1] - span[0]).days + 2, (
        f"lookback of {days} days cannot cover "
        f"{(span[-1] - span[0]).days} calendar days of window")


def test_missing_weekdays_is_membership_not_counts():
    """One row makes a day present. Row-count thresholds are a different
    check and would make this one argue about partial days."""
    latest = date(2026, 11, 6)
    present = _whole_window(latest, 5)
    assert missing_weekdays(present, latest, 5) == []


if __name__ == "__main__":
    # Prints "N/M passed" at line start, which is what the full-suite gate
    # reads as EVIDENCE OF EXECUTION. The first version of this block printed
    # "0 failed" instead; the gate correctly reported the whole file
    # INCONCLUSIVE, because a file that defines its functions and calls none
    # also exits 0 and says nothing. A suite certifying a release must be
    # able to prove it ran.
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
        except Exception as e:                                     # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
