"""
A field read from the wrong section of a payload you already download
=====================================================================
financials.annual_pnl.shares_used is NULL for all 2,113 active companies.
Every year, since the beginning. Not a coverage gap and not a provider gap:

    Balance_Sheet    share fields: ['commonStockSharesOutstanding']
    Income_Statement share fields: ['netIncomeApplicableToCommonShares']

load_fundamentals.parse_annual_pnl asked the Income_Statement row for
``commonStockSharesOutstanding`` and received None every single time. Nothing
consumed the column, so nothing ever failed.

What it cost: Piotroski F7 (no new shares issued) needs two consecutive years
of share counts, and no company in the universe had one. That made the score
unevaluable, which withheld it -- correctly -- which left ten of thirty-one
preset screens, nine of them Premium, returning an empty table since they
shipped. A customer asking "why does this screen find nothing" was three
layers away from a `.get()` on the wrong dictionary.

market.companies.shares_outstanding already existed and is NOT a substitute:
a single current snapshot from SharesStats, no history, useless for a
year-over-year criterion. The near-miss is worth naming -- a column with the
right name and the wrong shape is exactly what gets grabbed in a hurry.

This file asserts the parse side. The data side is an acceptance query after
the backfill (both_yr_shares: 0 -> ~1,570), because a test cannot prove that
a column somebody else's API fills is actually filled.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_annual_shares_ingestion.py
"""

import ast
import sys
from pathlib import Path

BACKEND   = Path(__file__).resolve().parents[1]
LOADER    = BACKEND / "scripts/eodhd/load_fundamentals.py"
MIGRATION = (BACKEND / "migrations"
             / "add_shares_outstanding_to_annual_balance_sheet.sql")

sys.path.insert(0, str(BACKEND))


def _fn(name: str) -> ast.FunctionDef:
    tree = ast.parse(LOADER.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == name), None)
    assert fn is not None, f"{name} is gone from load_fundamentals"
    return fn


def _string_constants(node) -> set:
    """String literals in a function's CODE, docstring excluded.

    Comments never reach the AST, but a docstring does, and a docstring that
    explains a defect names the very strings the test is looking for. Three
    guards were fooled that way on 30 Oct 2026 before this helper existed.
    """
    body = node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return {n.value for stmt in body for n in ast.walk(stmt)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


# ── The field is read from the section that carries it ───────────────────────

def test_the_balance_sheet_parser_reads_the_share_count():
    assert "commonStockSharesOutstanding" in _string_constants(
        _fn("parse_annual_bs")), (
        "the balance-sheet parser does not read commonStockSharesOutstanding, "
        "which is the only section of the EODHD payload that carries it")


def test_the_pnl_parser_no_longer_asks_for_it():
    """It never received it, and a line that looks like it populates a column
    is how the next person concludes the data exists."""
    assert "commonStockSharesOutstanding" not in _string_constants(
        _fn("parse_annual_pnl")), (
        "parse_annual_pnl still reads commonStockSharesOutstanding from the "
        "Income_Statement payload, where EODHD does not put it. It will "
        "silently receive None, exactly as it has all along.")


def test_each_parser_reads_its_own_section():
    """Population control for the two tests above.

    If the parsers stop naming their sections, the checks above are asserting
    things about functions that no longer do what their names say.
    """
    assert "Income_Statement" in _string_constants(_fn("parse_annual_pnl"))
    assert "Balance_Sheet" in _string_constants(
        _fn("parse_annual_bs"))


# ── It reaches the table ─────────────────────────────────────────────────────

def test_the_parsed_row_carries_the_column():
    assert "shares_outstanding" in _string_constants(
        _fn("parse_annual_bs")), (
        "the parsed row has no shares_outstanding key, so the value is read "
        "and discarded")


def test_the_upsert_writes_and_updates_it():
    """Both halves. A column in the INSERT list but not the DO UPDATE SET is
    written once and then frozen: every later load would leave the first
    value in place, and nobody would see a failure."""
    src = _fn("upsert_annual_bs")
    sql = " ".join(_string_constants(src))
    assert "shares_outstanding" in sql, (
        "the balance-sheet upsert does not mention shares_outstanding")
    assert "shares_outstanding   = EXCLUDED.shares_outstanding" in sql \
        or "shares_outstanding = EXCLUDED.shares_outstanding" in sql, (
        "shares_outstanding is inserted but never updated on conflict, so it "
        "would freeze at whatever the first load wrote")


def test_the_value_tuple_matches_the_column_list():
    """The failure this catches is silent and total: a misaligned tuple
    writes every column's value into its neighbour."""
    src = LOADER.read_text(encoding="utf-8")
    block = src[src.index("INSERT INTO financials.annual_balance_sheet"):]
    block = block[:block.index("execute_values")]
    columns = block[block.index("(asx_code"):block.index("VALUES %s")]
    n_cols = columns.count(",") + 1
    tup = block[block.index("vals = ["):]
    tup = tup[:tup.index("for r in rows")]
    n_vals = tup.count('r["') + tup.count("r['")
    assert n_cols == n_vals, (
        f"the balance-sheet upsert names {n_cols} columns but supplies "
        f"{n_vals} values; every column after the mismatch receives its "
        f"neighbour's number")


# ── The column exists to receive it ──────────────────────────────────────────

def test_the_migration_exists_and_is_idempotent():
    assert MIGRATION.exists(), (
        "no migration adds shares_outstanding; the loader's INSERT names a "
        "column that does not exist and every fundamentals load would fail")
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS shares_outstanding" in sql, (
        "the migration is not idempotent; deploy.sh does not track "
        "migrations, so re-running one must be harmless")
    assert "annual_balance_sheet" in sql


def test_the_migration_says_absence_is_not_zero():
    """The distinction the whole F-Score rewrite turns on. A NULL here means
    the period was not reported, never that the company has no shares."""
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "never" in sql and "null" in sql, (
        "the column carries no statement about what a NULL means; the next "
        "reader is free to treat absence as zero, which is precisely the "
        "assumption that made the old F-Score invalid")


def test_the_current_snapshot_is_not_mistaken_for_history():
    """market.companies.shares_outstanding has the right name and the wrong
    shape. Saying so in the migration is cheaper than someone discovering it
    after wiring F7 to it."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "market.companies.shares_outstanding" in sql, (
        "nothing warns that a same-named current-snapshot column exists and "
        "cannot serve a year-over-year criterion")


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
        except Exception as e:                                 # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
