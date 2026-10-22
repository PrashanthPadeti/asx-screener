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
            if t.startswith(("SOURCES", "ASX100_SWITCH_DATE", "INDEX_EODHD_SWITCH", "TICKER_MAP", "EXCLUDED_SOURCES")):
                wanted.append(n)
    ns = {}
    exec("from dataclasses import dataclass\nfrom datetime import date\n", ns)
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "<m>", "exec"), ns)
    return ns


NS = _load()
SOURCES = NS["SOURCES"]
SWITCH = NS["ASX100_SWITCH_DATE"]


# ── Only ASX100 moves ───────────────────────────────────────────────────────

#: The mappings evidence supports, and ONLY those. Each was measured at
#: median level 0.00000%, median daily-return 0.00000pp and 0 outliers over
#: 1,351 stored sessions, against the symbol whose name names the index.
EVIDENCED = {
    "ASX50":  "AFLI.INDX",
    "ASX100": "ATOI.INDX",
    "ASX200": "AXJO.INDX",
    "ASX300": "AXKO.INDX",
    "AXEJ":   "AXEJ.INDX",
    "AXHJ":   "AXHJ.INDX",
}

#: Deliberately NOT switched. Their own stored history holds the wrong
#: series from 2025-05 to 2026-05, so each failed the outlier cap at ~19.6%
#: against its OWN code. The question "does this symbol continue what we
#: publish" has no answer while what we publish is not one series.
AWAITING_REPAIR = {"ASX20": "^ATLI", "AXFJ": "^AXFJ", "AXMJ": "^AXMJ"}


def test_only_evidenced_indices_changed_provider():
    """Every EODHD source is one the discovery run actually supported.

    Not "the ones that would be convenient". A symbol added here without a
    measured match is the AXJO defect again -- a mapping that works and is
    wrong.
    """
    moved = {c: s.symbol for c, s in SOURCES.items() if s.provider == "eodhd"}
    assert moved == EVIDENCED, (
        f"EODHD mappings are not exactly the evidenced set.\n"
        f"  configured: {moved}\n  evidenced:  {EVIDENCED}")


def test_the_three_contaminated_indices_are_not_switched():
    """They fail the rule on their own history, and that is the right answer.

    Switching them anyway would build on data known to be wrong -- the whole
    reason the repair was sequenced first.
    """
    for code, symbol in AWAITING_REPAIR.items():
        assert SOURCES[code].provider == "yahoo", (
            f"{code} was switched while its stored history is still "
            f"contaminated; see the 13-month finding")
        assert SOURCES[code].symbol == symbol
        assert SOURCES[code].effective_from is None


def test_every_remaining_yahoo_symbol_is_accounted_for():
    """No index drifts onto Yahoo unnoticed."""
    actual = {c: s.symbol for c, s in SOURCES.items() if s.provider == "yahoo"}
    assert actual == AWAITING_REPAIR, f"unexpected Yahoo mapping: {actual}"


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
    for code in AWAITING_REPAIR:
        assert SOURCES[code].effective_from is None
        assert SOURCES[code].first_writable(date(2023, 1, 1)) == date(2023, 1, 1)


def test_every_switched_index_withholds_everything_before_its_date():
    """The property, across all six, not just the one this release added.

    A new source with effective_from=None would silently rewrite years of
    another provider's rows on its first run.
    """
    for code in EVIDENCED:
        s = SOURCES[code]
        assert s.effective_from is not None, (
            f"{code} switched provider with no effective date — its first "
            f"run would write over the whole stored history")
        for start in (date(2021, 5, 10), date(2024, 1, 1),
                      s.effective_from - timedelta(days=1)):
            assert s.first_writable(start) == s.effective_from, (
                f"a run starting {start} would write {code} rows before "
                f"{s.effective_from}")


def test_every_switched_index_declares_its_source_change():
    """A population check, not a spot check.

    Derived from SOURCES, so adding a seventh switched index without
    declaring it fails here rather than shipping an undeclared substitution.
    The numbers are identical across both providers, which is precisely why
    this is easy to forget: nothing on the page would look wrong.
    """
    from app.core.series_provenance import SOURCE_CHANGES
    switched = {c for c, s in SOURCES.items() if s.effective_from is not None}
    undeclared = switched - set(SOURCE_CHANGES)
    assert not undeclared, (
        f"these indices changed source and say so nowhere: "
        f"{sorted(undeclared)}")

    for code in switched:
        rec = SOURCE_CHANGES[code]
        assert rec["changed_on"] == SOURCES[code].effective_from.isoformat(), (
            f"{code} declares {rec['changed_on']} but switches on "
            f"{SOURCES[code].effective_from} — the declaration is wrong, "
            f"which is worse than absent")
        assert SOURCES[code].symbol in rec["to_source"], (
            f"{code} declares {rec['to_source']} but fetches "
            f"{SOURCES[code].symbol}")


def test_no_bad_window_is_declared_now_the_rows_are_repaired():
    """The notice comes off because the data was fixed, not to tidy up.

    796 rows were repaired on 21 Oct 2026 and the reconciliation confirms 0
    of 275 rows differ inside the window on all three indices. Leaving the
    warning up would train readers to ignore it; taking it down while the
    rows were still wrong would have been worse. Order matters, and it was:
    repair, verify, then remove.
    """
    from app.core.series_provenance import KNOWN_BAD_WINDOWS
    assert KNOWN_BAD_WINDOWS == {}, (
        f"a bad-window warning is still declared for "
        f"{sorted(KNOWN_BAD_WINDOWS)} — either the repair did not cover it "
        f"or the notice outlived the defect")


def test_the_repair_is_declared_for_exactly_those_three():
    """A correction nobody is told about looks like instability.

    Someone who read one of these charts last week saw different numbers.
    Removing the warning and saying nothing leaves them with a series that
    silently changed. The declaration is the other half of the repair.
    """
    from app.core.series_provenance import HISTORY_REPAIRS
    assert set(HISTORY_REPAIRS) == set(AWAITING_REPAIR), (
        f"declared repairs {sorted(HISTORY_REPAIRS)} do not match the three "
        f"indices that were repaired {sorted(AWAITING_REPAIR)}")
    total = 0
    for code, r in HISTORY_REPAIRS.items():
        assert r["from"] == "2025-05-01" and r["to"] == "2026-05-31", (
            f"{code} declares a window other than the one repaired")
        assert r["repaired_on"] == "2026-10-21", (
            f"{code} declares the wrong repair date")
        assert r["note"].strip(), f"{code} declares a repair with no note"
        total += r["rows"]
    assert total == 796, (
        f"the declared row counts total {total}; the repair updated 796 "
        f"(266 + 265 + 265) in one transaction")


def test_the_window_reaches_the_api_and_the_chart():
    """Declaring it in Python changes nothing a customer can see.

    The backend must serve it and the chart must render it. This is the
    paired-contract rule: a declaration and its consumer are one feature,
    and either half alone is worth nothing.
    """
    route = (BACKEND / "app" / "api" / "v1" / "routes"
             / "indices_funds.py").read_text(encoding="utf-8")
    assert '"known_bad_window": KNOWN_BAD_WINDOWS.get(code_u)' in route, (
        "the window is declared but never served")

    chart = (BACKEND.parent / "frontend" / "app" / "indices" / "[code]"
             / "IndexDetailContent.tsx").read_text(encoding="utf-8")
    statements = [l for l in chart.splitlines()
                  if l.strip() and not l.strip().startswith(("//", "*", "/*"))]
    body = "\n".join(statements)
    assert "known_bad_window" in body, "the chart never reads the field"
    assert "badWindow?.note" in body, "the chart never renders the note"


def test_the_repair_note_reaches_the_api_and_the_chart():
    """Same paired-contract rule as the warning it replaces.

    Declaring the repair in Python changes nothing a reader can see unless
    the route serves it and the chart renders it.
    """
    route = (BACKEND / "app" / "api" / "v1" / "routes"
             / "indices_funds.py").read_text(encoding="utf-8")
    assert '"history_repair": HISTORY_REPAIRS.get(code_u)' in route, (
        "the repair is declared but never served")

    chart = (BACKEND.parent / "frontend" / "app" / "indices" / "[code]"
             / "IndexDetailContent.tsx").read_text(encoding="utf-8")
    statements = [l for l in chart.splitlines()
                  if l.strip() and not l.strip().startswith(("//", "*", "/*"))]
    body = "\n".join(statements)
    assert "history_repair" in body, "the chart never reads the field"
    assert "repair?.note" in body, "the chart never renders the note"
    # Amber means "do not trust this line". A completed correction is not
    # that, and dressing it as one teaches readers to ignore the warnings.
    repair_block = body[body.index("repair?.note"):][:400]
    assert "amber" not in repair_block, (
        "the repair note renders as a warning; it is an explanation")


def test_a_declaration_changes_the_cache_key():
    """Otherwise a response cached before the switch omits the declaration.

    The digest exists so that changing what we publish about a series
    changes the key. A source change is such a change.
    """
    import app.core.series_provenance as sp
    before = sp.containment_version()
    original = dict(sp.SOURCE_CHANGES)
    try:
        sp.SOURCE_CHANGES["ZZZZ"] = {"changed_on": "2026-01-01",
                                     "from_source": "a", "to_source": "b",
                                     "note": "x"}
        assert sp.containment_version() != before, (
            "declaring a source change does not change the containment "
            "digest, so cached responses would omit it")
    finally:
        sp.SOURCE_CHANGES.clear()
        sp.SOURCE_CHANGES.update(original)
    assert sp.containment_version() == before, "the control did not restore"


def test_the_new_switch_date_is_one_explicit_shared_value():
    """Five indices, one reviewable date — not five dates to keep in step."""
    new = NS["INDEX_EODHD_SWITCH"]
    assert isinstance(new, date)
    moved_now = {c for c in EVIDENCED if c != "ASX100"}
    for code in moved_now:
        assert SOURCES[code].effective_from == new, (
            f"{code} has its own switch date; five dates drift, one does not")
    assert SOURCES["ASX100"].effective_from == SWITCH, (
        "the earlier ASX100 switch date moved — tags and dates never move")


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


# ── The chart must not imply continuity across missing sessions ─────────────

FRONTEND = BACKEND.parent / "frontend"
CHART = FRONTEND / "app" / "indices" / "[code]" / "IndexDetailContent.tsx"
ROUTE = BACKEND / "app" / "api" / "v1" / "routes" / "indices_funds.py"


def test_the_chart_breaks_the_line_at_a_gap():
    """Missing sessions are absent from the data, not null in it.

    Without an inserted null, Recharts plots 2026-05-29 adjacent to the next
    available date and joins them -- an unbroken line across 95 sessions that
    were never recorded. A gap in the data should look like a gap.
    """
    src = CHART.read_text(encoding="utf-8")
    # The logic lives in lib/chartGaps.ts, shared with the fund chart --
    # the same defect was fixed here first and then found unfixed there.
    assert "insertGaps(" in src, "the chart does not break at gaps"
    helper = (BACKEND.parent / "frontend" / "lib" / "chartGaps.ts").read_text(
        encoding="utf-8")
    assert "MAX_GAP_DAYS" in helper
    assert "gaps.push(" in helper, (
        "the helper does not record the gaps it finds")


def test_the_gap_is_described_in_words():
    """A break in a line reads as a rendering artefact unless it is labelled."""
    src = CHART.read_text(encoding="utf-8")
    assert "describeGaps(" in src, "the chart does not caption its gaps"
    helper = (BACKEND.parent / "frontend" / "lib" / "chartGaps.ts").read_text(
        encoding="utf-8")
    assert "no data recorded" in helper


def test_the_source_change_is_exposed():
    """A series spanning a provider change must say so."""
    prov = (BACKEND / "app" / "core" / "series_provenance.py").read_text(
        encoding="utf-8")
    assert "SOURCE_CHANGES" in prov
    assert '"ASX100"' in prov[prov.index("SOURCE_CHANGES"):]
    route = ROUTE.read_text(encoding="utf-8")
    assert '"source_change": SOURCE_CHANGES.get(code_u)' in route, (
        "the history endpoint does not surface the recorded source change")
    assert "sourceChange" in CHART.read_text(encoding="utf-8"), (
        "the chart never renders the source change")


def test_the_recorded_change_matches_the_switch_date():
    """The note and the producer must not drift apart."""
    prov = (BACKEND / "app" / "core" / "series_provenance.py").read_text(
        encoding="utf-8")
    block = prov[prov.index("SOURCE_CHANGES"):]
    block = block[:block.index("\n}\n")]
    assert str(SWITCH) in block, (
        f"SOURCE_CHANGES does not name the switch date {SWITCH}")
    assert "ATOI.INDX" in block and "AXTO" in block, (
        "the note does not name both the old and new symbols")


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
