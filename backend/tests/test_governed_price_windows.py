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

def test_v3_is_not_live_until_its_producer_exists():
    """The order of operations, as a test rather than as a note.

    Flipping LATEST_MODEL_VERSION to V3 before technical_compute emits
    assessments would make every absent return a contract violation on the
    next canonical run: violations() would flag all 608, the read-back would
    fail, and the publish would refuse. The daily pipeline would stop.

    So governance lands LAST. This test is the guard against landing it
    first, and it is expected to be rewritten -- not deleted -- in the commit
    that flips the constant, to assert the producer instead.
    """
    assert LATEST_MODEL_VERSION == V2, (
        "LATEST_MODEL_VERSION moved to V3. That is only safe once "
        "technical_compute produces an Assessment for every metric in "
        "PRICE_WINDOWS | PRICE_EXTREMES and the states reach "
        "screener.universe.metric_states. Rewrite this test to assert that, "
        "do not just delete it.")


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
