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


# ── Full replacement is old-complete or new-complete, never partial ──────────

TRANSFORM_PRICES = (Path(__file__).resolve().parents[1]
                    / "scripts/eodhd/v2/transforms/transform_prices.py")


def _code_lines():
    """Source with comments and blanks removed, so no guard can match its own
    explanation -- a mistake this codebase has made four times."""
    out = []
    for line in TRANSFORM_PRICES.read_text(encoding="utf-8").splitlines():
        body = line.split("#")[0].rstrip()
        if body.strip():
            out.append(body)
    return out


def test_the_truncate_is_not_committed_on_its_own():
    """The original defect.

    TRUNCATE; COMMIT; then rebuild 6.7M rows left market.daily_prices empty
    and DURABLY so for the length of the rebuild. Anything that went wrong in
    that window destroyed the price history with nothing to roll back to, and
    almost every producer downstream reads this table.
    """
    lines = _code_lines()
    trunc = next(i for i, l in enumerate(lines)
                 if "TRUNCATE TABLE market.daily_prices" in l)
    following = " ".join(lines[trunc + 1:trunc + 4])
    assert "conn.commit()" not in following, (
        "the TRUNCATE is committed before the reload replaces what it removed")


def test_no_commit_is_reachable_mid_replacement():
    """Every commit between the TRUNCATE and the guards must be unreachable on
    a full run, or the table can be left in a committed partial state."""
    lines = _code_lines()
    trunc = next(i for i, l in enumerate(lines)
                 if "TRUNCATE TABLE market.daily_prices" in l)
    # Up to the proof, not merely up to the shrink guard: a commit placed
    # between the guards and the proof would still publish a replacement the
    # proof had not yet approved.
    proof = next(i for i, l in enumerate(lines) if "ok = prove_population(" in l)

    for i in range(trunc, proof):
        if "conn.commit()" not in lines[i]:
            continue
        # Walk back to the condition governing this commit.
        indent = len(lines[i]) - len(lines[i].lstrip())
        context = " ".join(
            l for l in lines[max(0, i - 4):i]
            if len(l) - len(l.lstrip()) < indent and l.strip().startswith(("if", "elif")))
        assert "not is_full_run" in context, (
            f"line {i}: {lines[i].strip()!r} can commit part of a replacement")


def test_a_failing_code_aborts_the_full_run_rather_than_skipping_it():
    """Skip-and-continue is how a partial replacement gets committed: the
    rollback restores the TRUNCATE too, so the remaining codes would rebuild
    into a table that was never emptied."""
    lines = _code_lines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "except Exception as e:")
    block = " ".join(lines[start:start + 14])
    assert "is_full_run" in block and "return 1" in block, (
        "a per-code failure during a full run does not abort the run")


def test_every_refusal_restores_the_previous_state():
    """Empty rebuild, sharp shrink, and a failed population proof must each
    roll back — a refusal that leaves the truncate committed is not a refusal.
    """
    src = " ".join(_code_lines())
    for refusal in ("the rebuild produced no rows",
                    "would shrink",
                    "does not match"):
        idx = src.index(refusal)
        # The rollback precedes the message it explains.
        assert "conn.rollback()" in src[max(0, idx - 400):idx], (
            f"the {refusal!r} refusal does not roll back")


def test_the_proof_gates_the_commit_rather_than_describing_it():
    """A proof that runs after the commit can only report the damage."""
    lines = _code_lines()
    proof = next(i for i, l in enumerate(lines) if "ok = prove_population(" in l)
    final = max(i for i, l in enumerate(lines) if "conn.commit()" in l)
    assert proof < final, "the population proof runs after the final commit"


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
