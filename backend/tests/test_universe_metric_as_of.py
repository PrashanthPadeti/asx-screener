#!/usr/bin/env python
"""
A derived row may only serve the source state it summarises
===========================================================
`screener.universe` draws its technical columns from `market.daily_metrics`
through a LATERAL join. That join used to be:

    FROM market.daily_metrics WHERE asx_code = c.asx_code
    ORDER BY date DESC LIMIT 1

-- the latest row EVER WRITTEN for the code, with no relationship to the
prices it claims to describe.

Observed 3 Oct 2026. ALPH had exactly two rows in `market.daily_metrics`:

    2026-06-19   sma_200 11.0564   dma200_ratio 1.0175
    2026-10-01   sma_200 NULL      dma200_ratio NULL     <- written by run 6

Until run 6 wrote the second one, the unbounded lateral served the June row.
The site showed a 200-day moving average ratio of 1.0175 for an instrument
whose prices ran to 1 October -- three and a half months of a stale number
presented as current. 33 codes were still in that state after run 6, so the
condition recurs whenever a technical run skips a code.

Why not an age threshold
------------------------
"Metric must be less than N days old" is the tempting fix and it is wrong.
A suspended instrument has an old latest price AND an old latest metric, and
those agreeing is CORRECT -- there is nothing newer to compute from. An age
rule would suppress a legitimately quiet code and still admit a stale row
inside its window.

The honest question is not "how old is this row" but "does this row describe
the source state being served". That is `dm.date = dp.price_date`.

Run:  python tests/test_universe_metric_as_of.py
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
BUILDER = BACKEND / "scripts" / "eodhd" / "v2" / "build_screener_universe.py"


def _daily_metrics_lateral(source: str) -> str:
    """The LATERAL block that feeds the technical columns, comments stripped.

    Stripped because the block below documents the defect it forbids, and a
    scan that reads its own explanation reports the bug it just fixed. That
    has happened three times in this codebase already.
    """
    start = source.index("FROM market.daily_metrics")
    end = source.index(") dm ON TRUE", start)
    block = source[start:end]
    return "\n".join(line for line in block.splitlines()
                     if not line.strip().startswith("--"))


def test_the_metric_row_must_be_as_of_the_price_it_summarises():
    body = _daily_metrics_lateral(BUILDER.read_text(encoding="utf-8"))
    assert "dp.price_date" in body, (
        "the daily_metrics lateral does not correlate with the code's latest "
        "price date, so a row written months ago will be served as current")
    assert re.search(r"\bdate\s*=\s*dp\.price_date\b", body), (
        "the correspondence must be equality on the as-of date; anything "
        "looser re-admits the stale row")


def test_the_bound_is_not_an_age_threshold():
    """An interval against now() would suppress quiet codes and still admit
    a stale row inside the window. The bound is source-relative."""
    body = _daily_metrics_lateral(BUILDER.read_text(encoding="utf-8"))
    for forbidden in ("now()", "CURRENT_DATE", "current_date", "interval"):
        assert forbidden not in body, (
            f"the lateral bounds staleness with {forbidden!r}. Elapsed time "
            "is not the property: a suspended instrument correctly has an old "
            "price and an old metric, and those agreeing is not staleness")


def test_no_lateral_on_daily_metrics_is_left_unbounded():
    """The guard is about the table, not about one join written once."""
    source = BUILDER.read_text(encoding="utf-8")
    for match in re.finditer(r"FROM market\.daily_metrics", source):
        tail = source[match.start():match.start() + 2000]
        stop = tail.find(") ")
        segment = "\n".join(
            line for line in tail[:stop if stop > 0 else len(tail)].splitlines()
            if not line.strip().startswith("--"))
        assert "price_date" in segment, (
            "a lateral reads market.daily_metrics without tying the row to "
            "the price date it summarises")


def test_every_technical_source_is_bounded_not_just_the_daily_one():
    """The served columns COALESCE across three laterals.

        COALESCE(dm.return_3m, mm.return_3m) AS return_3m
        COALESCE(dm.rsi_14,    mm.rsi_14)    AS rsi_14
        COALESCE(dm.sma_200,   wm.sma_40w)   AS sma_200

    So bounding only `daily_metrics` made things WORSE: suppressing a stale
    daily row promotes whatever the weekly or monthly lateral holds, and those
    had no bound at all. The scratch fixture caught it -- the stale daily row
    was correctly rejected and the universe served sma_200 = 54.6245 from the
    weekly source instead. Four source guards passed while the behaviour was
    wrong, which is why this one exists.
    """
    # Comments are stripped BEFORE the boundary is located, not after.
    # Locating "LIMIT 1" in the raw text found it inside this file's own
    # explanatory comment -- "This was ORDER BY date DESC LIMIT 1 with no
    # bound at all" -- which truncated the block before the predicate and
    # reported the bug the comment describes. Fourth time in this codebase.
    raw = BUILDER.read_text(encoding="utf-8")
    source = "\n".join(line for line in raw.splitlines()
                       if not line.strip().startswith("--"))
    for table in ("market.daily_metrics", "market.weekly_metrics",
                  "market.monthly_metrics"):
        start = source.index(f"FROM {table}")
        block = source[start:source.index("LIMIT 1", start)]
        assert "dp.price_date" in block, (
            f"the {table} lateral is unbounded. It feeds columns that are "
            f"COALESCEd into the served technical values, so an unbounded row "
            f"here is a second path for stale evidence")


def test_the_check_can_actually_fail():
    """Mutation control, against the exact text this replaced.

    Without it, a refactor that drops the predicate leaves three green tests
    whose scan simply finds nothing to object to.
    """
    unbounded = ("FROM market.daily_metrics\n"
                 "    WHERE asx_code = c.asx_code\n"
                 "    ORDER BY date DESC\n"
                 "    LIMIT 1\n) dm ON TRUE")
    body = _daily_metrics_lateral(unbounded)
    assert "dp.price_date" not in body, (
        "the extractor cannot see the predicate's absence, so the guards "
        "above prove nothing")


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
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - len(failures)}/{total} passed")
    sys.exit(1 if failures else 0)
