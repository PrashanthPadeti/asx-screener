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

#: Measured 9 Nov 2026, revised 13 Nov when p_fcf_ratio was restored.
#: Reconciliation, not configuration.
EXPECT_TABLE_COLUMNS = 188
EXPECT_INSERT_COLUMNS = 125
EXPECT_RETIRED = 63

#: The column that WAS the one retired column reaching a customer. v11.2.86
#: restored it: build_yearly_rows computes it again, under an explicit
#: contract, so it is written rather than emptied.
#:
#: Kept as a named constant rather than deleted. The assertion below flipped
#: from "must be emptied" to "must be written", and a future reader needs to
#: see that the move was deliberate -- a silent disappearance from this file
#: would look like the column had simply stopped being watched.
RESTORED_FORMERLY_RETIRED = "p_fcf_ratio"

#: ── 6a: DEAD. Never populated by anything, on any row. ──────────────────
#:
#: A consumer reads NULL everywhere, so no wrong answer is served. Listed
#: anyway: the split between dead and frozen is what makes the 64 two
#: findings rather than one, and a column moving between these lists
#: without anyone noticing would hide the move.
DEAD_6A = (
    "alpha_1y", "alpha_3y", "avg_eps_growth_10y", "beta_1y", "beta_3y",
    "beta_5y", "calmar_ratio", "cash_conversion_cycle", "dps_grossed_up",
    "eps_cagr_10y", "eps_cagr_7y", "ev_fcf", "fcf_per_share",
    "max_drawdown_3y", "ncavps", "net_debt_per_share", "ocf_per_share",
    "payables_days", "pcf_ratio", "pe_5y_avg", "peg_ratio",
    "pretax_margin", "revenue_per_employee", "revenue_per_share",
    "sortino_1y", "tax_rate_effective", "tbvps",
)

#: ── 6b: FROZEN. Values on 2.9%-22.6% of rows, no current writer. ────────
#:
#: These are the ones that serve a wrong answer rather than no answer, and
#: the reason the repair is urgent: each sits beside a computed_at
#: refreshed by the run that did not produce it.
FROZEN_6B = (
    "avg_current_ratio_3y", "avg_ebit_10y", "avg_ebit_5y",
    "avg_fcf_margin_3y", "avg_fcf_margin_5y", "avg_net_margin_10y",
    "avg_operating_margin_10y", "avg_roce_10y", "avg_roce_7y",
    "avg_roe_10y", "avg_roe_7y", "beneish_m_score", "cash_ratio", "croic",
    "debt_to_ebitda", "ebit_growth_1y", "ebitda_cagr_10y",
    "ebitda_cagr_7y", "equity_multiplier", "inventory_days",
    "inventory_turnover", "net_debt_to_equity", "net_income_cagr_10y",
    "net_income_cagr_7y", "price_cagr_10y", "price_cagr_1y",
    "price_cagr_3y", "price_cagr_5y", "price_cagr_7y", "quick_ratio",
    "revenue_growth_median_10y", "revenue_growth_median_5y", "roaa",
    "roae", "sharpe_3y", "volatility_3y",
)

#: ── 6d: the subset PROVEN to come from the superseded `_avg` helper. ────
#:
#: `average_over` -- the exactly-n-named-fiscal-years contract the WRITTEN
#: avg_* columns use -- cannot produce a longer window with a higher count
#: than its shorter sibling, because a longer window is strictly harder to
#: satisfy. These three pairs invert, so their values were produced by the
#: helper that took the last n list entries and dropped Nones.
#:
#: Measured 9 Nov 2026 and re-measured 13 Nov 2026:
#:     avg_roe_7y   6,424  <  avg_roe_10y   6,429
#:     avg_roce_7y  6,404  <  avg_roce_10y  6,405
#:     avg_ebit_5y  6,502  <  avg_ebit_10y  6,504
#:
#: The wider `avg_*` family is frozen too and is covered by FROZEN_6B;
#: this names the ones where the PROVENANCE is established rather than
#: merely the staleness.
INVERTED_PAIRS_6D = (
    ("avg_roe_7y", "avg_roe_10y"),
    ("avg_roce_7y", "avg_roce_10y"),
    ("avg_ebit_5y", "avg_ebit_10y"),
)


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


def test_the_6a_and_6b_lists_partition_the_retired_set():
    """The two findings must account for the 64 between them, exactly.

    A column in neither list is one nobody has classified as dead or
    frozen, which is how a wrong answer gets filed as a harmless one. A
    column in both is a contradiction about whether it ever held a value.
    """
    retired = set(table_columns()) - set(insert_columns())
    dead, frozen = set(DEAD_6A), set(FROZEN_6B)

    both = sorted(dead & frozen)
    assert not both, f"{both} are listed as BOTH dead and frozen"

    unclassified = sorted(retired - dead - frozen)
    assert not unclassified, (
        f"{unclassified} are retired and classified as neither dead (6a) "
        f"nor frozen (6b). Measure whether they hold values before filing "
        f"them: the two have different severities and different urgencies.")

    phantom = sorted((dead | frozen) - retired)
    assert not phantom, (
        f"{phantom} are classified as retired but the INSERT writes them. "
        f"Either the write was restored, or the list is stale.")

    # The 9 Nov census measured 27 dead and 37 frozen. 6b is 36 from
    # v11.2.86: p_fcf_ratio left it by being RESTORED, not by being
    # reclassified. "Restored" is the only legitimate way out of either list,
    # and `phantom` above is what proves it -- a name that leaves a list
    # without the INSERT gaining it fails there first.
    assert len(dead) == 27 and len(frozen) == 36, (
        f"the census measured 27 dead and 37 frozen, less p_fcf_ratio "
        f"restored in v11.2.86; these lists hold {len(dead)} and "
        f"{len(frozen)}")


def test_every_6d_column_is_emptied():
    """The columns whose PROVENANCE is proven, not merely their staleness.

    Named separately from 6b because the argument is different: these are
    not just undated, they are known to have been produced by a helper
    this codebase replaced for labelling a single year's ROE as a
    three-year average.
    """
    missing = sorted(
        {c for pair in INVERTED_PAIRS_6D for c in pair} - set(emptied()))
    assert not missing, (
        f"{missing} carry values from the superseded _avg helper and are "
        f"not emptied on conflict.")


def test_the_inverted_pairs_are_all_frozen_columns():
    """Otherwise the inversion argument is about a column someone writes.

    If one of these were in the INSERT, its count would reflect the
    CURRENT implementation and could not evidence the old one.
    """
    written = set(insert_columns())
    offenders = sorted(
        {c for pair in INVERTED_PAIRS_6D for c in pair} & written)
    assert not offenders, (
        f"{offenders} are written by the current implementation, so their "
        f"counts say nothing about the superseded helper and the 6d "
        f"provenance argument does not rest on them.")


def test_the_restored_column_is_written_and_not_emptied():
    """The inverse of what this test asserted in v11.2.85, deliberately.

    p_fcf_ratio reaches screener.universe.price_to_fcf -- a registered
    filter, a sort column, a CSV column and a company-detail field. v11.2.85
    emptied it because every value it held came from a code path that no
    longer existed and could not be dated. v11.2.86 gives it a producer
    again, so the correct assertion is now that it is WRITTEN.

    Both halves are asserted. A column that appeared in neither list would
    silently keep whatever a prior run left in it, which is the exact defect
    finding 6b was -- and emptying and writing are the only two outcomes
    this statement may produce for it.
    """
    assert RESTORED_FORMERLY_RETIRED in refreshed(), (
        f"{RESTORED_FORMERLY_RETIRED} is not written on conflict. It was "
        f"restored in v11.2.86 and a row that keeps its prior value is the "
        f"frozen-column defect returning to the one column where a customer "
        f"can see it.")
    assert RESTORED_FORMERLY_RETIRED not in emptied(), (
        f"{RESTORED_FORMERLY_RETIRED} is still in the NULL list as well as "
        f"the written one. Whichever assignment PostgreSQL applied, one of "
        f"the two intents is not happening.")


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
