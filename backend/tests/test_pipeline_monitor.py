"""
The pipeline monitor counts what the producer wrote
===================================================
Daily Metrics Compute reported ``Rows: 1`` every day while the producer wrote
~1,524. Not a job-invocation count, and not a display bug — an accident of
precision:

    WHERE computed_at = (SELECT MAX(computed_at) FROM market.computed_metrics)

``computed_at`` is set per row at insert time, so ``MAX(computed_at)`` is a
single microsecond and the equality matched exactly one row: the last one
written. Two entries above, EOD Price Download already counted correctly, by
``time::date``, and reported 1,577.

This page is the coverage surface an operator reads to decide whether a
producer ran properly, and P0-A's central discipline is that a producer must
prove its population against an independently derived expectation. A monitor
that understates one by three orders of magnitude does not merely mislead —
it trains people to ignore the instrument, which is worse than having none.

The rule these tests enforce: a row count over a time-series table is counted
by DATA date, never by exact equality against a MAX() of a per-row timestamp.
Equality against a truncated date is fine; equality against a raw timestamp is
the defect.

Textual, because the assertion is about the shape of SQL that only a populated
production database would otherwise expose — and it would expose it as a
plausible-looking small number, which is exactly what went unnoticed.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_pipeline_monitor.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ADMIN = (Path(__file__).resolve().parents[1]
         / "app" / "api" / "v1" / "routes" / "admin.py")

#: Timestamp columns written per row. Comparing one for exact equality against
#: its own MAX() selects a single row, whatever the producer actually wrote.
PER_ROW_TIMESTAMPS = ("computed_at", "created_at", "loaded_at", "updated_at",
                      "fetched_at", "detected_at", "built_at",
                      "universe_built_at")


def _pipeline_status_source() -> str:
    """Just the pipeline_status endpoint, comments stripped.

    Comments here quote the broken predicate deliberately, and a guard that
    matches its own explanation proves nothing — a mistake this repo has made
    more than once.
    """
    src = ADMIN.read_text(encoding="utf-8")
    start = src.index("async def pipeline_status(")
    end = src.index("@router.get", start + 10)
    body = src[start:end]
    return "\n".join(ln for ln in body.splitlines()
                     if not ln.strip().startswith("#"))


def test_no_row_count_compares_a_raw_timestamp_to_its_own_max():
    """The defect itself, stated as a rule rather than as one column."""
    src = _pipeline_status_source()

    offenders = []
    for col in PER_ROW_TIMESTAMPS:
        # `col = (SELECT MAX(col)` with no ::date on either side.
        pattern = rf"{col}\s*=\s*\(\s*SELECT\s+MAX\(\s*{col}\s*\)(?!\s*::\s*date)"
        if re.search(pattern, src, re.I):
            offenders.append(col)

    assert not offenders, (
        f"a row count compares {offenders} for exact equality against its own "
        f"MAX(); a per-row timestamp makes that select exactly one row. Count "
        f"by data date, as EOD Price Download does.")


def test_the_daily_metrics_count_is_by_data_date():
    """Specifically that the repair is the one described, not a cast bolted
    onto the same predicate."""
    src = _pipeline_status_source()
    i = src.index("market.computed_metrics\n            WHERE")
    window = src[i:i + 200]

    assert "time::date" in window, (
        "Daily Metrics Compute no longer counts by data date")
    assert "MAX(time)::date" in window, (
        "the subquery must also truncate, or the comparison never matches")


def test_it_counts_the_same_way_its_sibling_does():
    """EOD Price Download and Daily Metrics Compute describe the same run over
    the same trading day. Counting them by different grains is how one of them
    stayed wrong for so long — there was nothing to compare it against."""
    src = _pipeline_status_source()

    prices = re.search(r"market\.daily_prices\s+WHERE\s+(\S+)", src)
    metrics = re.search(r"market\.computed_metrics\s+WHERE\s+(\S+)", src)

    assert prices and metrics, "could not locate both row-count queries"
    assert prices.group(1) == metrics.group(1) == "time::date", (
        f"the two daily producers count by different grains: "
        f"{prices.group(1)!r} vs {metrics.group(1)!r}")


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
