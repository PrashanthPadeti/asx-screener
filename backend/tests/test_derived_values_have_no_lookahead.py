#!/usr/bin/env python
"""
A row's derived values must not depend on anything after that row
=================================================================
The repair recomputes 13 stored columns for ~800 rows dated between May 2025
and May 2026, using the production `compute_rows` on corrected history. That
history now extends to October 2026 -- months of observations that did not
exist when those rows were first written.

If any derived value reads forward, recomputing a May-2025 row on a frame
ending in October 2026 produces a figure that could not have been known on
the day, and the repair would replace wrong numbers with differently wrong
ones. A chart of "what the 1-year return was on this date" would silently
become "what we can work out now".

So the property is asserted before the repair is allowed to use the output,
and it is asserted BEHAVIOURALLY. By inspection the three calculations read
backwards:

    _pct_return    indices [i - lookback, i]
    52-week range  closes.iloc[max(0, i-251) : i+1]
    _ytd_return    dates < year_start, and year_start <= dates[i]

Inspection is not proof. A future refactor using a centred window, a
`bfill`, a `shift(-1)` or a whole-series `max()` would pass a reading and
fail here.

THE TEST: compute each row on a frame TRUNCATED at that row, and on the
full frame. Both see identical history up to the row, so every value must
match exactly. Any difference is information arriving from the future.

Run:  python tests/test_derived_values_have_no_lookahead.py
Requires the real pandas.
"""

import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

DERIVED = ("return_1d", "return_1w", "return_1m", "return_3m", "return_6m",
           "return_1y", "return_ytd", "high_52w", "low_52w")


def _frame(n: int = 420):
    """Deterministic, and deliberately not monotonic.

    A rising series would hide a forward-looking 52-week HIGH, because the
    high is always the latest point. The reversal partway means the maximum
    sits in the middle, so a window that reaches forward reports a different
    number than one that does not. It also crosses a year boundary, which
    `_ytd_return` depends on.
    """
    import numpy as np
    import pandas as pd
    idx = pd.bdate_range("2024-06-03", periods=n)
    t = np.arange(n)
    close = 100 + 30 * np.sin(t / 37.0) + t * 0.02      # rises, falls, rises
    return pd.DataFrame(
        {"open": close - 0.5, "high": close + 1.0,
         "low": close - 1.0, "close": close,
         "volume": np.full(n, 1000)},
        index=idx)


def _rows_by_date(df):
    from compute.engine.index_prices import compute_rows
    return {r["price_date"]: r for r in compute_rows(df)}


def test_truncating_at_a_row_changes_nothing_about_it():
    """The property, across the whole frame rather than one sample point."""
    df = _frame()
    full = _rows_by_date(df)
    dates = sorted(full)

    # Every 17th row, plus the last -- enough to cross the year boundary and
    # both turning points without recomputing 420 frames.
    probes = list(range(20, len(dates), 17)) + [len(dates) - 1]
    offenders = []
    for i in probes:
        d = dates[i]
        truncated = _rows_by_date(df.iloc[: i + 1])
        if d not in truncated:
            offenders.append((d, "row vanished when truncated"))
            continue
        for col in DERIVED:
            a, b = full[d].get(col), truncated[d].get(col)
            if a is None and b is None:
                continue
            if a is None or b is None or abs(a - b) > 1e-12:
                offenders.append((d, f"{col}: full={a} truncated={b}"))

    assert not offenders, (
        "derived values depend on observations AFTER the row's own date, so "
        "recomputing a 2025 row on 2026 history would invent a figure that "
        "could not have been known then:\n  "
        + "\n  ".join(f"{d} {why}" for d, why in offenders[:10]))


def test_the_detector_catches_a_forward_looking_window():
    """Mutation control.

    Without this, a test that passes proves only that it ran. A 52-week high
    taken over the WHOLE series is the most plausible way this breaks, and
    it must be caught.
    """
    df = _frame()
    closes = df["close"]
    dates = df.index
    i = 300
    backward = float(closes.iloc[max(0, i - 251): i + 1].max())
    forward = float(closes.max())
    assert backward != forward, (
        "the fixture's maximum sits inside every backward window, so a "
        "whole-series max would be indistinguishable from a correct one "
        "and the test above proves nothing")


def test_a_row_recomputed_on_longer_history_keeps_its_own_close():
    """Closes are observations, not derivations. They must never move.

    The repair replaces contaminated closes with the provider's; it must not
    also perturb the ones it is using as context.
    """
    df = _frame()
    full = _rows_by_date(df)
    half = _rows_by_date(df.iloc[:260])
    for d, r in half.items():
        assert abs(full[d]["close_price"] - r["close_price"]) < 1e-12, (
            f"{d}: close_price changed with the length of the frame")


def test_the_lookback_is_positional_and_that_is_recorded():
    """NOT a lookahead, but it governs what the repair can claim.

    `return_1y` is 252 ROWS back, not one calendar year. On a frame with
    different leading history the same date resolves to a different prior
    row -- which is why 252 rows at the series start differ between stored
    and recomputed values while their closes agree exactly.

    Asserted so the repair's documentation cannot drift from the code: the
    repaired rows are correct against the provider on the same basis the
    producer uses, and that basis is positional.
    """
    import ast
    src = (BACKEND / "compute" / "engine" / "index_prices.py").read_text(
        encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "_pct_return")
    body = ast.unparse(fn)
    assert "current_idx - lookback" in body, (
        "_pct_return no longer offsets positionally; the repair notes and "
        "the 252-row finding both describe behaviour that has changed")
    assert "iloc" in body, "_pct_return no longer indexes positionally"


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
