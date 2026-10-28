"""
A blank that says nothing
=========================
On 28 Oct 2026, immediately after canonical run 30 published cleanly with
"state/value contradictions: 0", the served universe carried:

    608 of 2,113 stocks with return_1y NULL and no state entry
    190                    return_6m
     87                    return_3m

metric_states.py states the contract plainly -- "a NULL numeric column must
never be the only signal" -- and violations() enforces it. It reported zero
because it only inspects GOVERNED_METRICS, and the price windows were not in
it. The guarantee was real, the population it covered was not.

v11.2.62 is what made this visible: anchoring the windows on the calendar
rather than on row counts turned ~221 wrong numbers into honest absences, and
every one of them arrived at the customer as an unexplained dash.

These tests pin the V3 contract. They do not test that the states are
produced -- that is the producer's own suite -- they test that the contract
covers the right metrics and that every one of them can actually be stored.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine.metric_states import (                       # noqa: E402
    GOVERNED_METRICS, LATEST_MODEL_VERSION, PRICE_WINDOWS, PRICE_EXTREMES,
)
from compute.engine.universe_writer import (                     # noqa: E402
    column_for, persisted_governed, NOT_PERSISTED,
)

V2 = "FACTOR_MODEL_V2"
V3 = "FACTOR_MODEL_V3"


# ── The contract ────────────────────────────────────────────────────────────

def test_v3_keeps_everything_v2_governed():
    """A version bump may add meaning. It may never quietly drop a metric
    that a published run promised to govern."""
    missing = GOVERNED_METRICS[V2] - GOVERNED_METRICS[V3]
    assert not missing, f"V3 drops metrics V2 governed: {sorted(missing)}"


def test_the_price_windows_are_governed_in_v3():
    for metric in PRICE_WINDOWS | PRICE_EXTREMES:
        assert metric in GOVERNED_METRICS[V3], f"{metric} is not governed"


def test_they_were_not_governed_in_v2():
    """The premise. If V2 already governed these, the 608 blanks had some
    other cause and this whole change is aimed at the wrong thing."""
    for metric in PRICE_WINDOWS | PRICE_EXTREMES:
        assert metric not in GOVERNED_METRICS[V2], (
            f"{metric} was already governed in V2, so an unexplained NULL "
            f"would have been a violations() failure, not a gap")


def test_the_one_day_return_is_deliberately_excluded():
    """return_1d has no window: the previous close is the previous close.
    Excluded by decision, and this records it so a later reader does not
    'fix' the omission."""
    assert "return_1d" not in GOVERNED_METRICS[V3]


# ── Storage: where governance silently fails ────────────────────────────────

def test_the_52_week_extremes_map_to_their_real_columns():
    """The ev_to_ebitda failure, pre-empted.

    The registry names these week_52_high / week_52_low; the universe stores
    them as high_52w / low_52w, and nothing aliases one to the other. Without
    an explicit STORAGE_COLUMN entry, column_for() returns the registry
    spelling, no such column exists, and the metric resolves as
    governed-with-no-column -- withholding universally while looking entirely
    correct from every direction except the customer's.
    """
    assert column_for("week_52_high") == "high_52w"
    assert column_for("week_52_low") == "low_52w"


def test_the_return_windows_store_under_their_own_names():
    """The opposite risk: adding an alias that is not needed would point a
    governed metric at a column answering a different question."""
    for metric in PRICE_WINDOWS:
        assert column_for(metric) == metric, (
            f"{metric} acquired a storage alias; if that is intended the "
            f"column must answer the same question the metric asks")


def test_every_governed_price_metric_resolves_to_a_column():
    """persisted_governed() raises on a collision and skips NOT_PERSISTED.
    Neither may apply here: a price window silently dropped from the SET list
    leaves yesterday's value in place rather than failing."""
    mapping = persisted_governed(V3)
    for metric in PRICE_WINDOWS | PRICE_EXTREMES:
        assert metric not in NOT_PERSISTED, (
            f"{metric} is governed but declared as having no column")
        assert metric in mapping, (
            f"{metric} is governed by V3 but absent from the persisted "
            f"mapping, so no UPDATE would ever write it")


def test_no_two_price_metrics_claim_one_column():
    """persisted_governed() aborts on a duplicate claim. Calling it is the
    assertion; this names what it protects."""
    mapping = persisted_governed(V3)
    columns = [mapping[m] for m in sorted(PRICE_WINDOWS | PRICE_EXTREMES)]
    assert len(columns) == len(set(columns)), f"duplicate columns: {columns}"


# ── Sequencing ──────────────────────────────────────────────────────────────

def test_v3_is_live_and_its_producer_exists():
    """The order of operations, as a test rather than as a note.

    This asserted the opposite until step 5: that LATEST_MODEL_VERSION was
    still V2, because flipping it before technical_compute emitted
    assessments would make every absent return a contract violation on the
    next canonical run -- violations() flags them, the read-back fails, the
    publish refuses, and the daily pipeline stops.

    Rewritten rather than deleted, per its own instruction. The guard is now
    the other half of the same rule: V3 is live, so every governed price
    metric must have a producer that can assess it.
    """
    assert LATEST_MODEL_VERSION == V3

    from compute.engine.window_states import (
        EXTREME_COLUMNS, window_assessment)
    from compute.engine.return_windows import ALL_WINDOWS

    # return_ytd has no fixed window and so is not in ALL_WINDOWS, but it is
    # governed and window_states assesses it with its own branch.
    producible = set(ALL_WINDOWS) | set(EXTREME_COLUMNS) | {"return_ytd"}
    ungoverned = (PRICE_WINDOWS | PRICE_EXTREMES) - producible
    assert not ungoverned, (
        f"governed under the live contract with no producer: "
        f"{sorted(ungoverned)} — these would be written as NULL with no "
        f"sidecar entry, which is the defect V3 exists to close")

    # And the rebuild path the canonical writer depends on actually works,
    # rather than merely existing.
    a = window_assessment("return_1y", None, {
        "return_1y": {"state": "insufficient_data",
                      "cause": "insufficient_history",
                      "reason": "no close within 7 days of 2025-10-27"}})
    assert not a.ok and a.value is None


def test_the_live_contract_can_store_every_metric_it_governs():
    """Every governed metric resolves to a real column under the version
    that is actually running. persisted_governed() raises on a collision;
    this names what it protects, now that the version it checks is live."""
    mapping = persisted_governed(LATEST_MODEL_VERSION)
    for metric in PRICE_WINDOWS | PRICE_EXTREMES:
        assert metric in mapping, (
            f"{metric} is governed by the live contract but has no storage "
            f"column, so no UPDATE would ever write it")


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
