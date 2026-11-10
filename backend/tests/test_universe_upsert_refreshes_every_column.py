"""An inserted column must also be reassigned on conflict.

screener.universe is upserted every run and rows are never deleted except
for excluded security types, so a column present in the INSERT list and
absent from ON CONFLICT DO UPDATE SET is written exactly once per row, on
the first insert, and never again. It then sits frozen beside columns that
refresh daily, and nothing in the row says which is which.

price_to_52w_high was in NEITHER list. Migration 052 added six columns and
backfilled none; the other five were wired into the statement and this one
was not. Measured in production on 10 Nov 2026, before the fix:

    2,566  rows
    2,290  held a stored value
    1,837  could be recomputed from their own row's price and high_52w
    1,674  (91.1%) differed by more than 0.01
    0.10   median absolute error, on a ratio whose useful range is 0-1
    0.93   worst

It was live on three surfaces the whole time: a registered filter field, a
sort column and a response field. A filter over it returned rows selected on
a stale ratio and reported no error. Empty would have been visible; stale
was not.

The test below is deliberately NOT about that one column. A guard written
for the column that was found tests the column that was found. The property
is the general one, and asserting it over all 342 surfaces the next
omission before it reaches production.
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
BUILDER = BACKEND / "scripts" / "eodhd" / "v2" / "build_screener_universe.py"

#: Population sizes, so a parse that stops matching fails loudly instead of
#: reporting a clean statement over an empty set.
EXPECT_INSERT_COLUMNS = 342
EXPECT_SET_COLUMNS = 343

#: Columns the upsert assigns and the INSERT does not list. Both are set to
#: an explicit NULL: the builder revokes canonical state it is not entitled
#: to make, having assessed nothing. The canonical writer re-establishes
#: them, and until it commits row_projection fails the row closed.
DELIBERATE_SET_ONLY = {"metric_states", "compute_run_id"}

#: Columns whose conflict assignment is deliberately NOT EXCLUDED.<col>,
#: with the expression each one must have. Declared per column rather than
#: waived as a pattern: "anything calling a function is fine" would admit
#: exactly the COALESCE this file exists to forbid.
DELIBERATE_EXPRESSIONS = {
    # The build stamp records when THIS upsert ran. Taking it from EXCLUDED
    # would carry the value the SELECT computed, which is the same instant
    # for every row in the statement and says nothing a run id does not.
    "universe_built_at": "NOW()",
}


def _lines() -> list[str]:
    return BUILDER.read_text(encoding="utf-8").splitlines()


def _strip(line: str) -> str:
    return re.sub(r"--.*$", "", line)


def insert_columns() -> list[str]:
    lines = _lines()
    start = next(i for i, ln in enumerate(lines)
                 if "INSERT INTO screener.universe (" in ln)
    end = next(i for i in range(start + 1, len(lines))
               if _strip(lines[i]).strip() == ")")
    body = " ".join(_strip(ln).strip() for ln in lines[start + 1:end])
    return [c.strip() for c in body.split(",") if c.strip()]


def conflict_assignment_list() -> list[tuple[str, str]]:
    """(column, right-hand side) in statement order, duplicates kept.

    A list rather than a dict, because a dict silently keeps the last of a
    repeated assignment. Postgres rejects a duplicate in SET, so the defect
    is a statement that fails at run time -- which, for this statement, is
    the one that publishes the universe.
    """
    lines = _lines()
    at = next(i for i, ln in enumerate(lines)
              if "ON CONFLICT" in ln and "screener.universe" not in ln)
    out = []
    for i in range(at + 1, len(lines)):
        raw = lines[i].strip()
        if raw.startswith('"""') or raw.endswith('"""'):
            break
        m = re.match(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*(.+?),?\s*$",
                     _strip(lines[i]))
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


def conflict_assignments() -> dict[str, str]:
    """column -> the right-hand side it is assigned on conflict."""
    return dict(conflict_assignment_list())


def select_expressions() -> dict[str, str]:
    """output alias -> its SELECT expression, paired by POSITION."""
    lines = _lines()
    start = next(i for i, ln in enumerate(lines)
                 if "INSERT INTO screener.universe (" in ln)
    select = next(i for i in range(start, len(lines))
                  if _strip(lines[i]).strip() == "SELECT")
    depth, exprs, cur = 0, [], []
    for i in range(select + 1, len(lines)):
        s = _strip(lines[i])
        if depth == 0 and re.match(r"^FROM\b", s.strip()):
            break
        buf = ""
        for ch in s:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                cur.append(buf)
                exprs.append(" ".join(x.strip() for x in cur if x.strip()))
                cur, buf = [], ""
                continue
            buf += ch
        cur.append(buf)
    if cur:
        exprs.append(" ".join(x.strip() for x in cur if x.strip()))
    return dict(zip(insert_columns(), exprs))


# ── Populations before properties ───────────────────────────────────────────

def test_the_parsed_populations_are_the_real_ones():
    cols, sets = insert_columns(), conflict_assignments()
    assert len(cols) == EXPECT_INSERT_COLUMNS, (
        f"{len(cols)} insert columns, expected {EXPECT_INSERT_COLUMNS}")
    assert len(sets) == EXPECT_SET_COLUMNS, (
        f"{len(sets)} conflict assignments, expected {EXPECT_SET_COLUMNS}")
    assert len(set(cols)) == len(cols), "a column is inserted twice"


def test_no_column_is_assigned_twice_on_conflict():
    """Postgres rejects a repeated column in SET; this catches it first.

    Found by a mutant that was meant to test something else. The dict-based
    reading of the SET list silently kept the last of a pair, so a duplicate
    was invisible to every other check in this file -- and the statement it
    would break is the one that publishes the universe.
    """
    seen, dupes = set(), []
    for column, _rhs in conflict_assignment_list():
        if column in seen:
            dupes.append(column)
        seen.add(column)
    assert not dupes, (
        f"{dupes} appear more than once in ON CONFLICT DO UPDATE SET. "
        f"Postgres rejects the statement, so the universe build fails at the "
        f"moment it would publish.")


def test_the_select_pairs_one_to_one_with_the_column_list():
    paired = select_expressions()
    assert len(paired) == len(insert_columns()), (
        "the SELECT and the column list did not pair one to one; the "
        "positional alignment this file reads is not trustworthy")


# ── The property ────────────────────────────────────────────────────────────

def test_every_inserted_column_is_reassigned_on_conflict():
    """The general form of the price_to_52w_high defect."""
    inserted = set(insert_columns())
    refreshed = set(conflict_assignments())
    frozen = sorted(inserted - refreshed - {"asx_code"})
    assert not frozen, (
        f"{frozen} are inserted and never reassigned on conflict. The row is "
        f"upserted every run and is not deleted between runs, so each of "
        f"these is written once on first insert and then frozen for the life "
        f"of the row, beside columns that refresh daily. Add them to the ON "
        f"CONFLICT DO UPDATE SET list.")


def test_the_only_unlisted_assignments_are_the_deliberate_two():
    """Assigning a column the INSERT omits sets it from the column default.

    For metric_states and compute_run_id that is the intent, and both are
    assigned an explicit NULL rather than EXCLUDED. Any other column in this
    position would be silently nulled on every conflict.
    """
    inserted = set(insert_columns())
    extra = {c: rhs for c, rhs in conflict_assignments().items()
             if c not in inserted}
    unexpected = sorted(set(extra) - DELIBERATE_SET_ONLY)
    assert not unexpected, (
        f"{unexpected} are assigned on conflict and not inserted. Unless the "
        f"assignment is an explicit literal, EXCLUDED.<col> for an omitted "
        f"column is that column's DEFAULT, so this nulls the value on every "
        f"upsert.")
    for column in sorted(DELIBERATE_SET_ONLY & set(extra)):
        assert extra[column].upper().startswith("NULL"), (
            f"{column} is assigned {extra[column]!r}. It is deliberately "
            f"absent from the INSERT, so it must be set to an explicit NULL "
            f"-- EXCLUDED here would read as a value rather than a revocation.")


def test_a_refreshed_column_takes_its_new_value_not_its_old_one():
    """`col = EXCLUDED.col`, never `col = u.col` or COALESCE of the two.

    A COALESCE(EXCLUDED.col, col) keeps the previous value whenever the new
    computation is unavailable, which is the same defect in a form that
    looks like care: the row then serves a stale number with no way to tell.
    Where a value cannot be computed this run, NULL must replace it.
    """
    wrong = []
    for column, rhs in conflict_assignments().items():
        if column in DELIBERATE_SET_ONLY:
            continue
        if column in DELIBERATE_EXPRESSIONS:
            expected = DELIBERATE_EXPRESSIONS[column]
            assert rhs.upper() == expected.upper(), (
                f"{column} is declared as {expected!r} and is now {rhs!r}. "
                f"Update the declaration together with the statement, or the "
                f"exception stops describing what the code does.")
            continue
        if not re.fullmatch(rf"EXCLUDED\.{re.escape(column)}", rhs):
            wrong.append((column, rhs))
    assert not wrong, (
        f"these conflict assignments do not take the incoming value plainly: "
        f"{wrong}. A COALESCE with the existing value preserves a stale "
        f"number whenever the new one is unavailable.")


def test_every_ratio_guards_its_denominator():
    """A ratio must yield NULL on an absent or non-positive denominator.

    Not division-by-zero protection -- Postgres raises on that and a raise
    is visible. The point is that an unavailable ratio must be NULL, so the
    conflict assignment overwrites a previous value with NULL rather than
    leaving it in place.
    """
    paired = select_expressions()
    unguarded = []
    for column in ("price_to_52w_high", "price_to_52w_low",
                   "ocf_per_share", "fcf_per_share", "revenue_per_share"):
        expr = paired.get(column)
        if expr is None:
            unguarded.append((column, "NOT IN THE STATEMENT"))
        elif not re.search(r"\bCASE\s+WHEN\b", expr, re.IGNORECASE):
            unguarded.append((column, expr[:70]))
    assert not unguarded, (
        f"{unguarded} compute a ratio without a CASE guarding the "
        f"denominator, so an absent denominator cannot produce NULL and the "
        f"previous value survives the upsert.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
