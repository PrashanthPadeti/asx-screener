"""
An n-year average is n years, or it is nothing
==============================================
_avg(values, n) took values[-n:] — the last n LIST ENTRIES — then dropped
every None among them and averaged what was left. Two independent defects:

    window     a company reporting 2016, 2019, 2022 had its "3-year average"
               computed across seven years
    coverage   avg_roe_3y could be one year's ROE labelled as three, with
               nothing distinguishing it from a genuine one

Measured on production, the window half is small (one company of 1,595 on a
3-year window; eight of 1,528 on 5-year) because an average reaches back n-1
years where a CAGR reaches n. The coverage half is about 1% for roe, roa and
roce — and 537 of 1,594 for roic, which is that metric's own sparsity showing
through rather than the rule creating a problem.

That last case is why the rule matters: the system must not manufacture an
apparently robust three-year average from one observation because the
underlying metric is thin.

Run under pytest, or standalone:
    cd /opt/asx-screener/backend && ../asx-venv/bin/python tests/test_average_window.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compute.engine.periods import average_over  # noqa: E402


# ── The three fixtures ───────────────────────────────────────────────────────

def test_a_gap_in_the_window_yields_nothing():
    """Years 2022, 2024, 2025 for a 3-year average ending 2025. The last three
    ROWS exist, and they span four years. 2023 is required and absent."""
    series = {2022: 0.10, 2024: 0.12, 2025: 0.14}

    assert average_over(series, 2025, 3) is None


def test_a_missing_observation_inside_a_complete_window_yields_nothing():
    """Years 2023, 2024, 2025 all present, middle observation NULL.

    Not a history problem — every required period exists. One observation is
    missing, and the distinction matters most for roic, whose sparsity would
    otherwise be mislabelled as insufficient history.
    """
    series = {2023: 0.10, 2024: None, 2025: 0.14}

    assert average_over(series, 2025, 3) is None


def test_a_complete_contiguous_window_is_the_exact_mean():
    series = {2023: 0.10, 2024: 0.20, 2025: 0.30}

    assert average_over(series, 2025, 3) == 0.2


# ── The edges the old helper got wrong quietly ───────────────────────────────

def test_a_single_observation_is_never_an_n_year_average():
    """The headline coverage defect. One year of ROIC is not a three-year
    average of it, however arithmetically true the mean of one number is."""
    assert average_over({2025: 0.15}, 2025, 3) is None

def test_the_window_is_anchored_to_the_year_asked_for_not_the_latest():
    """Averaging as at 2024 must not reach forward into 2025."""
    series = {2022: 0.10, 2023: 0.20, 2024: 0.30, 2025: 0.99}

    assert average_over(series, 2024, 3) == 0.2


def test_extra_history_beyond_the_window_is_ignored():
    series = {y: 1.0 for y in range(2010, 2026)}
    series[2025] = 0.4
    series[2024] = 0.2
    series[2023] = 0.6

    assert average_over(series, 2025, 3) == 0.4


def test_zero_is_an_observation():
    """A truthiness check would drop it and average two, which is the same
    class of error as the compaction in daily_compute's growth series."""
    assert average_over({2023: 0.0, 2024: 0.3, 2025: 0.3}, 2025, 3) == 0.2


def test_a_negative_observation_is_an_observation():
    assert average_over({2023: -0.2, 2024: 0.1, 2025: 0.4}, 2025, 3) == 0.1


def test_a_five_year_window_needs_all_five():
    series = {2021: 0.1, 2022: 0.1, 2023: 0.1, 2025: 0.1}

    assert average_over(series, 2025, 5) is None
    assert average_over({**series, 2024: 0.1}, 2025, 5) == 0.1


def test_an_empty_series_yields_nothing_rather_than_raising():
    assert average_over({}, 2025, 3) is None


# ── Standalone runner ─────────────────────────────────────────────────────────

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
