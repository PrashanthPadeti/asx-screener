"""
Set equality is the proof; counts are diagnostics
=================================================
The population-proof machinery, at the grains the four producers actually use.

Each producer owes a different identity. technical_compute owes a row per
(code, date); halfyearly_compute owes one per (code, fiscal_year);
period_metrics_compute owes one per (code, computed_date); transform_prices
owes a date-set digest per code. Collapsing them all to "company codes" would
make four different questions look like one, and the three that are really
about time would be answered by a proof that never examined time.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_population_proof.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.run_stages import (  # noqa: E402
    StageResult, render_key, report_population, set_hash,
)


class Log:
    """Collects what a producer would have printed."""

    def __init__(self):
        self.lines = []

    def _add(self, msg, *a):
        self.lines.append(msg % a if a else msg)

    info = error = warning = _add

    def text(self):
        return "\n".join(self.lines)


# ── Keys at any grain ────────────────────────────────────────────────────────

def test_composite_keys_render_unambiguously():
    """Two different keys must never collapse into one string."""
    a = render_key(("BHP", date(2026, 9, 15)))
    b = render_key(("BHP", date(2026, 9, 16)))
    assert a != b
    assert "2026-09-15" in a

    # The classic collision: a separator that can occur inside a part. If the
    # renderer joined on "-", ("AB", "C-D") and ("AB-C", "D") would be one key.
    assert render_key(("AB", "C-D")) != render_key(("AB-C", "D"))


def test_a_date_and_its_datetime_are_the_same_member():
    """Rendering through isoformat() keeps one calendar day one member."""
    from datetime import datetime
    assert render_key(date(2026, 9, 15)) == "2026-09-15"
    assert render_key(datetime(2026, 9, 15).date()) == render_key(date(2026, 9, 15))


def test_the_hash_does_not_depend_on_processing_order():
    keys = [("BHP", date(2026, 9, 15)), ("CBA", date(2026, 9, 15))]
    assert set_hash(keys) == set_hash(reversed(keys))


# ── What the proof must catch ────────────────────────────────────────────────

def test_equal_counts_over_different_members_fails():
    """The failure counts alone cannot see.

    A producer that wrote exactly as many rows as it owed, for a different set
    of companies, is broken. `written_count == expected_count` calls it clean.
    """
    expected = frozenset({("BHP", 2026), ("CBA", 2026)})
    written = frozenset({("BHP", 2026), ("NAB", 2026)})
    result = StageResult("halfyearly_compute", expected, written,
                         grain="asx_code+fiscal_year")

    assert len(expected) == len(written), "the premise of this test"
    assert not result.ok
    assert result.status == "failed"
    assert result.missing == {("CBA", 2026)}
    assert result.extra == {("NAB", 2026)}


def test_the_right_codes_at_the_wrong_date_fails():
    """Every company present, no row written today.

    This is the shape a code-only proof passes: the target still holds
    yesterday's row for everyone, and the consumer takes the latest row with
    no recency bound, so stale values are served as current ones.
    """
    yesterday, today = date(2026, 9, 15), date(2026, 9, 16)
    result = StageResult(
        "period_metrics_compute",
        frozenset({("BHP", today), ("CBA", today)}),
        frozenset({("BHP", yesterday), ("CBA", yesterday)}),
        grain="asx_code+computed_date")

    assert not result.ok
    assert {k[0] for k in result.missing} == {"BHP", "CBA"}

    # And the same data, proved at the grain that hides it:
    collapsed = StageResult(
        "period_metrics_compute",
        frozenset({"BHP", "CBA"}), frozenset({"BHP", "CBA"}))
    assert collapsed.ok, (
        "the point of this test: at code grain the identical run passes, "
        "which is why the date belongs in the key")


def test_extra_members_fail_as_loudly_as_missing_ones():
    """The producer wrote something its own domain does not account for, so
    one of the two is wrong and the run cannot say which."""
    result = StageResult("technical_compute",
                         frozenset({("BHP", date(2026, 9, 16))}),
                         frozenset({("BHP", date(2026, 9, 16)),
                                    ("XYZ", date(2026, 9, 16))}),
                         grain="asx_code+date")
    assert not result.ok
    assert result.extra == {("XYZ", date(2026, 9, 16))}


def test_a_digest_member_detects_a_hole_in_the_middle():
    """transform_prices' grain.

    Same code, same row count, same first and last date — one day swapped.
    A min/max/count comparison passes this; the date-set digest does not.
    """
    def digest(days):
        return set_hash([f"{d}" for d in days])

    src = ["2026-09-14", "2026-09-15", "2026-09-16"]
    tgt = ["2026-09-14", "2026-09-17", "2026-09-16"]
    assert len(src) == len(tgt) and min(src) == min(tgt)

    result = StageResult(
        "transform_prices",
        frozenset({("BHP", 3, digest(src))}),
        frozenset({("BHP", 3, digest(tgt))}),
        grain="asx_code+row_count+date_set_digest")
    assert not result.ok


# ── Reporting and its refusals ───────────────────────────────────────────────

def test_a_producer_cannot_pass_by_having_nothing_to_say():
    """An unscoped call with no result is an inert check, not a pass."""
    try:
        report_population(None, None, None, Log())
    except ValueError as e:
        assert "nothing to say" in str(e)
    else:
        raise AssertionError("a producer with no result was reported as passing")


def test_a_scoped_run_records_nothing_and_does_not_fail():
    log = Log()
    assert report_population(None, 7, None, log,
                             scoped_reason="a scoped run's expected population "
                                           "is not the source domain")
    assert "skipped" in log.text()


def test_the_proof_prints_the_grain_and_both_directions():
    log = Log()
    ok = report_population(
        None, None,
        StageResult("technical_compute",
                    frozenset({("BHP", date(2026, 9, 16)),
                               ("CBA", date(2026, 9, 16))}),
                    frozenset({("BHP", date(2026, 9, 16))}),
                    grain="asx_code+date"),
        log)
    out = log.text()
    assert not ok
    assert "asx_code+date" in out
    assert "POPULATION NOT COVERED" in out
    assert "missing sample" in out and "CBA" in out
    assert "expected, not written" in out and "written, not expected" in out


def test_the_grain_is_persisted_not_inferred():
    """A reader of compute_run_stages cannot tell 2,103 companies from 2,103
    company-days unless the record says which."""
    payload = StageResult("technical_compute", frozenset(), frozenset(),
                          {"errors": 0}, grain="asx_code+date").payload()
    assert payload["grain"] == "asx_code+date"
    assert payload["errors"] == 0


def test_samples_are_bounded_and_say_so_when_truncated():
    from compute.engine.run_stages import SAMPLE_LIMIT
    expected = frozenset((f"C{i:04d}", 2026) for i in range(SAMPLE_LIMIT * 3))
    payload = StageResult("halfyearly_compute", expected, frozenset(),
                          grain="asx_code+fiscal_year").payload()
    assert len(payload["missing_sample"]) == SAMPLE_LIMIT
    assert payload["missing_truncated"] is True


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
