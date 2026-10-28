"""
Three declarations of one fact
==============================
The columns technical_compute writes were a hand-maintained list, the values
it writes were a hand-maintained tuple in the same order, and the windows it
computes were a third declaration elsewhere. Nothing failed when they stopped
agreeing.

That is how return_2y/4y/6y/8y/9y came to be served by a producer that no
longer exists: filterable, sortable, shown on the company page, written by
nothing, holding whatever was last put there because screener.universe is
upserted and a column absent from a SET list keeps its old value.

INSERT_COLS and the value tuple are now both spliced from RETURN_COLS, which
is itself derived from ALL_WINDOWS. These tests assert the splice holds, and
that build_rows() emits exactly one value per declared column -- the
invariant an ordered pair of hand-written lists can violate silently.

psycopg2 is stubbed so this runs without a database driver installed. It
tests declaration and arity, not SQL.
"""

import sys
import types
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

for name in ("psycopg2", "psycopg2.extras", "psycopg2.extensions", "dotenv"):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
_pg = sys.modules["psycopg2"]
_pg.connect = lambda *a, **k: None
_pg.extras = sys.modules["psycopg2.extras"]
_pg.extensions = sys.modules["psycopg2.extensions"]
_pg.extras.execute_values = lambda *a, **k: []
_pg.extras.Json = dict
_pg.extensions.new_type = lambda *a, **k: object()
_pg.extensions.register_type = lambda *a, **k: None
_pg.extensions.DECIMAL = types.SimpleNamespace(values=())
sys.modules["dotenv"].load_dotenv = lambda *a, **k: False

# technical_compute resolves DB_URL at IMPORT time, so the module cannot be
# loaded without one even by a test that never connects. A placeholder, not a
# credential; psycopg2.connect is stubbed above and is never called.
import os                                                         # noqa: E402
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://unused@/unused")

from compute.engine.return_windows import ALL_WINDOWS             # noqa: E402
from compute.engine.technical_compute import (                    # noqa: E402
    INSERT_COLS, RETURN_COLS, COLUMN_MIGRATION, verify_columns,
    compute_indicators, build_rows,
)


def _frame(n: int = 900, start: date = date(2022, 1, 1)) -> pd.DataFrame:
    """A series that actually rises and falls.

    A strictly monotonic close gives RSI no losses, and build_rows() drops
    rows whose rsi_14 is NaN as warm-up -- so a straight line produces no
    rows at all and the arity check silently tests nothing.
    """
    i = np.arange(n)
    close = 1.0 + 0.002 * i + 0.35 * np.sin(i / 17.0)
    return pd.DataFrame({
        "date": pd.to_datetime([start + timedelta(days=k) for k in range(n)]),
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "adj_close": close,
        "volume": 10_000.0 + 500.0 * np.cos(i / 11.0),
    })


class _Cursor:
    """A cursor that answers one information_schema question."""

    def __init__(self, columns):
        self._columns = list(columns)

    def execute(self, sql, *args):
        self._sql = sql

    def fetchall(self):
        return [(c,) for c in self._columns]


# ── The splice ──────────────────────────────────────────────────────────────

def test_every_computed_window_is_written():
    """The population check, in the direction that lost the orphans: a window
    computed and not written is a number that never reaches anybody."""
    missing = set(ALL_WINDOWS) - set(INSERT_COLS)
    assert not missing, f"computed but never written: {sorted(missing)}"


def test_no_return_column_is_written_without_a_window():
    """The other direction: a written column with no producer is exactly the
    orphan condition, and it would be filled with NULL forever."""
    windowed = {c for c in INSERT_COLS if c.startswith("return_")}
    unaccounted = windowed - set(ALL_WINDOWS) - {"return_1d", "return_ytd"}
    assert not unaccounted, f"written with no window: {sorted(unaccounted)}"


def test_return_cols_is_derived_not_restated():
    assert RETURN_COLS == ["return_1d", "return_ytd", *ALL_WINDOWS]


def test_the_column_list_has_no_duplicates():
    """A duplicate would shift every value after it by one, writing each
    column's number into its neighbour."""
    seen, dupes = set(), []
    for c in INSERT_COLS:
        if c in seen:
            dupes.append(c)
        seen.add(c)
    assert not dupes, f"duplicated columns: {dupes}"


# ── Arity: the invariant two parallel lists can break ───────────────────────

def test_every_row_carries_exactly_one_value_per_column():
    """build_rows() must emit len(INSERT_COLS) values. An ordered pair of
    hand-written sequences can disagree here and the only symptom is every
    value landing in the wrong column from the insertion point onward."""
    out = compute_indicators(_frame(), shares=1_000_000.0)
    rows = build_rows("TST", out)

    assert rows, "build_rows produced nothing for a 900-day series"
    for row in rows[:5]:
        assert len(row) == len(INSERT_COLS), (
            f"row has {len(row)} values for {len(INSERT_COLS)} columns")


def test_the_long_horizons_actually_compute():
    """Not merely declared. A fifteen-year window on a three-year series is
    correctly absent; a two-year one is not, and must carry a number."""
    out = compute_indicators(_frame(), shares=1_000_000.0)
    assert out["return_2y"].notna().any(), (
        "return_2y is declared but never produced a value over 900 days")
    assert out["return_15y"].notna().sum() == 0, (
        "a fifteen-year return was produced from under three years of data")


# ── The preflight has two outcomes ──────────────────────────────────────────

def test_it_admits_a_schema_that_can_hold_every_column():
    verify_columns(_Cursor(INSERT_COLS))        # must not raise


def test_it_refuses_and_names_the_migration():
    """A refusal test that never reaches the admitting path proves nothing,
    so both are here. deploy.sh does not apply migrations: code can land
    ahead of its schema, and the first symptom would otherwise be an
    exception partway through a run with some companies committed."""
    partial = [c for c in INSERT_COLS if c not in ("return_4y", "return_10y")]
    try:
        verify_columns(_Cursor(partial))
    except SystemExit as e:
        message = str(e)
    else:
        raise AssertionError("a missing column was written anyway")

    assert "return_4y" in message and "return_10y" in message
    assert COLUMN_MIGRATION["return_4y"] in message, (
        "the refusal does not name the migration that fixes it")


def test_every_missing_column_can_name_its_migration():
    """A column with no recorded migration produces a refusal nobody can
    act on. Only the columns this release introduces need an entry; the rest
    predate the check."""
    introduced = set(ALL_WINDOWS) - {"return_1w", "return_1m", "return_3m",
                                     "return_6m", "return_1y"}
    missing = introduced - set(COLUMN_MIGRATION)
    assert not missing, f"no migration recorded for: {sorted(missing)}"


# ── The retired producer ────────────────────────────────────────────────────

def test_the_old_multi_year_producer_refuses():
    """price_return() is retired, not deleted.

    It is the obvious function for a future reader to reach for, and it was
    wrong in three independent ways: an anchor with no grace bound (a
    three-year return could measure eight), a window ending at the fiscal
    period end rather than today, and no corporate-action withholding -- it
    published return_3y = 1449.0 for JNS. A silent reintroduction of any of
    those is worse than an exception.
    """
    import pandas as pd
    from compute.engine.yearly_compute import (
        price_return, price_at, UnsupportedComputation)

    prices = pd.Series(
        [1.0, 2.0],
        index=pd.to_datetime(["2020-01-01", "2026-01-01"]))

    try:
        price_return(prices, date(2026, 6, 30), 3)
    except UnsupportedComputation as e:
        assert "technical_compute" in str(e), (
            "the refusal does not say where the computation moved to")
    else:
        raise AssertionError("price_return computed a multi-year return")

    # price_at is NOT retired: price_at_compute still asks it "the close at
    # or before the fiscal year end", which claims no window length.
    assert price_at(prices, date(2026, 6, 30)) == 2.0


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
