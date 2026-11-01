"""Two debt measures with similar names, and the rule that keeps them apart
=========================================================================
EODHD's balance sheet carries ``longTermDebt`` (borrowings) and
``longTermDebtTotal`` (wider -- lease and similar non-current obligations).
The loader read the first and ignored the second, which left Piotroski F5
unassessable for most of the universe: measured over all 1,886 cached
payloads, ``longTermDebt`` is present on the latest consecutive year pair for
648 companies and ``longTermDebtTotal`` for 1,624.

The dangerous repair is the obvious one. Falling back from one key to the
other -- in Python, or as a SQL COALESCE -- makes F5 compare borrowings in
year t-1 against borrowings-plus-leases in year t and report a leverage change
that is entirely an artefact of which key the provider populated. Where both
are reported they DISAGREE on 4,067 of 6,558 years, systematically and by
roughly 2x (MP1: 6.7m vs 13.4m, 3.8m vs 8.7m, 7.1m vs 14.2m). So the measures
get one column each and the scorer picks ONE definition for every company.

These tests assert the parse and write side. Whether the column is actually
populated is an acceptance query after the backfill, because a test cannot
prove that somebody else's API filled a field.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_long_term_debt_total_ingestion.py
"""

import ast
import sys
from pathlib import Path

BACKEND   = Path(__file__).resolve().parents[1]
LOADER    = BACKEND / "scripts/eodhd/load_fundamentals.py"
MIGRATION = (BACKEND / "migrations"
             / "add_long_term_debt_total_to_annual_balance_sheet.sql")

NARROW = "longTermDebt"
WIDE   = "longTermDebtTotal"

sys.path.insert(0, str(BACKEND))


def _fn(name: str) -> ast.FunctionDef:
    tree = ast.parse(LOADER.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == name), None)
    assert fn is not None, f"{name} is gone from load_fundamentals"
    return fn


def _body(node):
    """The function's statements with its docstring removed.

    A docstring that explains a defect names the very strings a matcher looks
    for. Three guards were fooled that way on 30 Oct 2026.
    """
    body = node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return body


def _strings(node) -> set:
    return {n.value for stmt in _body(node) for n in ast.walk(stmt)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _strings_under(node) -> set:
    return {n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


# ── Both measures are read ───────────────────────────────────────────────────

def test_the_wider_measure_is_read():
    assert WIDE in _strings(_fn("parse_annual_bs")), (
        f"parse_annual_bs does not read {WIDE}. It is present on the latest "
        f"consecutive year pair for 1,624 companies against 648 for "
        f"{NARROW}, and without it Piotroski F5 is unassessable for most of "
        f"the universe")


def test_the_narrow_measure_is_still_read():
    """Population control. If the repair were done by RENAMING the key rather
    than adding one, every metric derived from long_term_debt would silently
    change definition and this file would still pass."""
    assert NARROW in _strings(_fn("parse_annual_bs")), (
        f"parse_annual_bs no longer reads {NARROW}; the wider measure was "
        f"substituted for it rather than added beside it, which redefines "
        f"long_term_debt and everything derived from it")


# ── And never substituted for one another ────────────────────────────────────

def test_the_two_measures_are_not_coalesced_in_python():
    """The defect this whole column exists to prevent.

    ``r.get("longTermDebt") or r.get("longTermDebtTotal")`` would make F5
    compare borrowings in one year against borrowings-plus-leases in the next.
    Any boolean fallback mentioning both keys is that bug.
    """
    for node in ast.walk(_fn("parse_annual_bs")):
        if isinstance(node, ast.BoolOp):
            seen = _strings_under(node)
            assert not (NARROW in seen and WIDE in seen), (
                f"parse_annual_bs falls back between {NARROW} and {WIDE} in a "
                f"single expression. They are different quantities -- they "
                f"disagree on 4,067 of the 6,558 years carrying both -- and "
                f"mixing them inside one company's series reports a change of "
                f"definition as a change in leverage")


def test_the_two_measures_are_not_coalesced_in_sql():
    """Same defect, moved one layer down. A COALESCE in the upsert, or in any
    view the scorer reads, has exactly the effect the Python check forbids."""
    sql = " ".join(_strings(_fn("upsert_annual_bs"))).lower()
    assert "coalesce" not in sql or not (
        "long_term_debt_total" in sql and "coalesce(long_term_debt" in sql), (
        "the balance-sheet upsert COALESCEs the two long-term debt columns "
        "together; they must be written independently")


def test_the_columns_hold_distinct_values():
    """Both keys read, both columns written, but from the SAME variable is a
    mistake no string matcher above would catch."""
    src = LOADER.read_text(encoding="utf-8")
    block = src[src.index('"long_term_debt":'):]
    block = block[:block.index('"total_liabilities":')]
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    values = [ln.split(":", 1)[1].strip().rstrip(",") for ln in lines]
    assert len(values) == 2, (
        f"expected long_term_debt and long_term_debt_total adjacent in the "
        f"parsed row, found {len(values)} entries")
    assert values[0] != values[1], (
        f"long_term_debt and long_term_debt_total are both assigned "
        f"{values[0]}; one of the two columns is a copy of the other and the "
        f"F5 definition choice is meaningless")


# ── It reaches the table ─────────────────────────────────────────────────────

def test_the_parsed_row_carries_the_column():
    assert "long_term_debt_total" in _strings(_fn("parse_annual_bs")), (
        "the parsed row has no long_term_debt_total key, so the value is read "
        "and discarded")


def test_the_upsert_writes_and_updates_it():
    """A column in the INSERT list but not the DO UPDATE SET is written once
    and then frozen: every later load leaves the first value in place."""
    sql = " ".join(_strings(_fn("upsert_annual_bs")))
    assert "long_term_debt_total" in sql, (
        "the balance-sheet upsert does not mention long_term_debt_total")
    assert "long_term_debt_total = EXCLUDED.long_term_debt_total" in sql, (
        "long_term_debt_total is inserted but never updated on conflict, so "
        "it would freeze at whatever the first load wrote")


# ── The column exists to receive it ──────────────────────────────────────────

def test_the_migration_exists_and_is_idempotent():
    assert MIGRATION.exists(), (
        "no migration adds long_term_debt_total; the loader's INSERT names a "
        "column that does not exist and every fundamentals load would fail")
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS long_term_debt_total" in sql, (
        "the migration is not idempotent; deploy.sh does not track "
        "migrations, so re-running one must be harmless")


def test_the_migration_names_both_keys_and_forbids_substitution():
    """The column's own documentation has to carry the rule. The next reader
    meets two similarly named columns and a COALESCE is the obvious move."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert NARROW in sql and WIDE in sql, (
        "the migration does not name both payload keys, so nothing records "
        "which quantity this column holds")
    low = sql.lower()
    assert "never substitute" in low or "must never be substituted" in low, (
        "the column carries no statement forbidding substitution between the "
        "two measures, which is the one error that silently corrupts F5")


def test_the_migration_says_absence_is_not_zero():
    """EODHD states a genuine zero as "0.00" -- 5,444 years of it. A NULL is a
    different claim and the distinction is what makes F5 assessable or not."""
    low = MIGRATION.read_text(encoding="utf-8").lower()
    assert "null" in low and "zero" in low, (
        "the column carries no statement about what a NULL means; the next "
        "reader is free to treat absence as zero, which would award F5 "
        "-- leverage decreased -- to companies that simply did not report")


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
