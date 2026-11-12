"""Every non-key column is written on conflict: refreshed, or emptied.

Finding 6b/6d. `market.yearly_metrics` has 188 columns and
`yearly_compute.INSERT_SQL` named 124 of them. The `DO UPDATE SET` listed
only those 124, so on a re-run the other 64 were never touched -- while
`computed_at` on the same row WAS refreshed.

A reader had no way to date those values. The row's own timestamp asserted
they were current.

Measured 9 Nov 2026 over 33,864 rows: 27 of the 64 were never populated at
all, and 37 held values on 2.9% to 22.6% of rows. Of the 6,261 rows
carrying a `quick_ratio`, `min(computed_at)` equalled `max(computed_at)`
equalled that day's run -- there was no population of untouched old rows to
explain them.

THE VALUES WERE PRODUCED BY A REJECTED METHOD
---------------------------------------------
Three window pairs are inverted:

    avg_roe_10y    6,429  >  avg_roe_7y    6,424
    avg_roce_10y   6,405  >  avg_roce_7y   6,404
    avg_ebit_10y   6,504  >  avg_ebit_5y   6,502

`average_over` -- the exactly-n-named-fiscal-years contract the WRITTEN
`avg_*` columns use -- cannot produce that ordering, because a longer
window is strictly harder to satisfy. Only the superseded `_avg` helper
can, and its own docstring records that it could label a single year's ROE
as a three-year average.

CUSTOMER EXPOSURE
-----------------
One of the 64 reaches a customer. `ym.p_fcf_ratio` is read by
`build_screener_universe.py` as `screener.universe.price_to_fcf`, which is
a registered screener filter, a sort column, a field in three response
SELECTs, a CSV column labelled "P/FCF" and a company-detail field. The
builder's comment calls it "reliable, already guards against negative/zero
FCF" -- a reliability claim about a column no current run produces.

`beta_1y` is also read there, and is one of the 27 never populated; it was
already withdrawn from screening in v11.2.81.

WHAT THIS FILE ASSERTS
----------------------
The statement, not the data: every non-key column is assigned on conflict,
no column twice, no assignment preserves the prior value, and the emptied
set is exactly the set the schema says is unwritten -- so a column added to
the table later cannot silently become the 65th frozen one.

The behavioural half -- that a valid value actually becomes NULL in
PostgreSQL -- needs a database and lives in
`tests/fixtures/prove_retired_columns_are_emptied.py`.
"""

import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
ENGINE = BACKEND / "compute" / "engine" / "yearly_compute.py"
SNAP_DIR = ROOT / "database" / "stm"

TABLE = "market.yearly_metrics"

#: The upsert key. Not assigned on conflict, by definition.
KEY = ("asx_code", "fiscal_year")

#: Measured 9 Nov 2026. Reconciliation, not configuration.
EXPECT_TABLE_COLUMNS = 188
EXPECT_INSERT_COLUMNS = 124
EXPECT_RETIRED = 64

#: The one retired column that reaches a customer, named so that removing
#: its exposure is a deliberate act rather than a side effect.
SERVED_RETIRED = "p_fcf_ratio"


def statement() -> str:
    src = ENGINE.read_text(encoding="utf-8")
    assert 'INSERT_SQL = """' in src, "INSERT_SQL is not where this test looks"
    return src.split('INSERT_SQL = """')[1].split('"""')[0]


def insert_columns() -> list[str]:
    body = statement().split(f"INSERT INTO {TABLE} (")[1].split(") VALUES")[0]
    # Strip comments before splitting: a column name inside prose is not a
    # column, and the retirement block below is full of them.
    body = re.sub(r"--[^\n]*", "", body)
    return [c.strip() for c in body.replace("\n", " ").split(",") if c.strip()]


def set_clause() -> str:
    return statement().split("DO UPDATE SET")[1]


def refreshed() -> list[str]:
    return re.findall(r"^\s*([a-z_0-9]+)\s*=\s*EXCLUDED\.", set_clause(),
                      re.M)


def emptied() -> list[str]:
    return re.findall(r"^\s*([a-z_0-9]+)\s*=\s*NULL\s*,?\s*$", set_clause(),
                      re.M)


def table_columns() -> list[str]:
    for path in sorted(SNAP_DIR.glob("snap_*.json")):
        snap = json.loads(path.read_text(encoding="utf-8"))
        rows = (snap.get("columns") or {}).get(TABLE)
        if rows:
            return [r[0] for r in rows]
    raise AssertionError(
        f"no snapshot in {SNAP_DIR} describes {TABLE}; every assertion "
        f"below would be comparing against an empty list")


# ── Populations first ───────────────────────────────────────────────────────

def test_the_populations_are_what_was_measured():
    cols, ins = table_columns(), insert_columns()
    assert len(cols) == EXPECT_TABLE_COLUMNS, (
        f"{TABLE} has {len(cols)} columns, expected "
        f"{EXPECT_TABLE_COLUMNS}. A column was added or dropped; decide "
        f"whether it is written or retired before updating this number.")
    assert len(ins) == EXPECT_INSERT_COLUMNS, (
        f"the INSERT names {len(ins)} columns, expected "
        f"{EXPECT_INSERT_COLUMNS}")


def test_the_retired_set_is_exactly_what_the_schema_says_is_unwritten():
    """The reconciliation that stops a 65th frozen column appearing.

    Derived from the table and the INSERT rather than listed, so a column
    added to market.yearly_metrics and not added to the write shows up here
    as a failure instead of silently inheriting the old behaviour.
    """
    unwritten = set(table_columns()) - set(insert_columns())
    assert len(unwritten) == EXPECT_RETIRED, (
        f"{len(unwritten)} columns are absent from the INSERT, expected "
        f"{EXPECT_RETIRED}")
    missing = sorted(unwritten - set(emptied()))
    assert not missing, (
        f"{missing} are absent from the INSERT and are NOT emptied on "
        f"conflict, so an existing row keeps whatever last wrote them while "
        f"computed_at is refreshed on the same row. That is the defect this "
        f"file exists to prevent, in a new column.")


# ── The statement ───────────────────────────────────────────────────────────

def test_every_non_key_column_is_assigned_on_conflict():
    assigned = set(refreshed()) | set(emptied())
    expected = set(table_columns()) - set(KEY)
    missing = sorted(expected - assigned)
    assert not missing, (
        f"{missing} are columns of {TABLE} that the conflict path never "
        f"touches. On a re-run they keep their previous value beside a "
        f"refreshed computed_at.")


def test_no_column_is_both_refreshed_and_emptied():
    both = sorted(set(refreshed()) & set(emptied()))
    assert not both, (
        f"{both} are assigned twice in one SET clause. PostgreSQL rejects "
        f"that, so the statement would fail at run time rather than here.")


def test_no_column_is_assigned_twice():
    for name, values in (("= EXCLUDED", refreshed()), ("= NULL", emptied())):
        seen, dupes = set(), []
        for col in values:
            if col in seen:
                dupes.append(col)
            seen.add(col)
        assert not dupes, f"{dupes} appear more than once as {name}"


def test_every_inserted_column_is_refreshed_from_its_own_excluded():
    """`a = EXCLUDED.b` would publish one column's value under another name."""
    clause = set_clause()
    crossed = [(a, b) for a, b in
               re.findall(r"^\s*([a-z_0-9]+)\s*=\s*EXCLUDED\.([a-z_0-9]+)",
                          clause, re.M)
               if a != b]
    assert not crossed, f"these assignments cross columns: {crossed}"

    inserted = set(insert_columns()) - set(KEY)
    not_refreshed = sorted(inserted - set(refreshed()))
    assert not not_refreshed, (
        f"{not_refreshed} are inserted but not refreshed on conflict")


def test_no_assignment_preserves_the_prior_value():
    """A COALESCE here keeps the stale number whenever the new one is absent.

    The same defect in a form that looks like care -- and the exact thing
    the price_to_52w_high repair had to avoid. It applies doubly to the
    retired columns: `COALESCE(yearly_metrics.p_fcf_ratio, NULL)` would
    empty nothing at all while reading as a retirement.
    """
    clause = set_clause()
    offenders = re.findall(
        r"^\s*([a-z_0-9]+)\s*=\s*(COALESCE|GREATEST|LEAST)\b", clause, re.M)
    assert not offenders, (
        f"{offenders} do not take EXCLUDED or NULL plainly. An assignment "
        f"that falls back to the stored value cannot replace a valid value "
        f"with an unavailable one, which is the transition this repair "
        f"exists to make.")


def test_the_served_retired_column_is_emptied():
    """Named explicitly because emptying it removes data a customer sees.

    p_fcf_ratio reaches screener.universe.price_to_fcf -- a registered
    filter, a sort column, a CSV column and a company-detail field. Its
    coverage falls to zero when this runs, and that is the intent: the
    values were produced by a code path that no longer exists and cannot be
    dated. Serving an undatable number beside a current timestamp is worse
    than serving none.
    """
    assert SERVED_RETIRED in emptied(), (
        f"{SERVED_RETIRED} is not emptied. It is the one retired column "
        f"with customer exposure, so leaving it would keep the defect "
        f"exactly where it is visible.")


def test_computed_at_is_still_refreshed():
    """The repair must not fix the timestamp instead of the values.

    Freezing computed_at would make the row self-consistent and useless:
    the fix is that the VALUES go, not that the clock stops.
    """
    assert "computed_at" in refreshed(), (
        "computed_at is no longer refreshed on conflict. The defect was "
        "values surviving a refreshed timestamp, not the timestamp itself.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:                           # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
