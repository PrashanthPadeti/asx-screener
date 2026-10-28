"""
340 columns, by position
========================
build_screener_universe issues one INSERT ... SELECT into screener.universe
with 340 columns. The insert list and the select list are matched by POSITION
and by nothing else: PostgreSQL checks the counts and the types, and a
type-compatible pair swapped anywhere in the middle is accepted silently.

Almost every column in that statement is a nullable number, so almost every
mistake is type-compatible. Insert one column into the select without
inserting it in the same place in the column list and every value after it
lands in its neighbour's column -- return_3y into return_5y, and so on down
the statement. Nothing fails. The screener simply serves the wrong numbers.

v11.2.63 moves ten multi-year returns into this statement, which is exactly
the edit that can do it. This test counts both sides.

It reads the file rather than importing it, because the module resolves a
database URL at import time.
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
BUILDER = BACKEND / "scripts" / "eodhd" / "v2" / "build_screener_universe.py"

EXPECTED_RETURNS = [
    "return_1w", "return_1m", "return_3m", "return_6m", "return_1y",
    "return_ytd",
    "return_2y", "return_3y", "return_4y", "return_5y", "return_6y",
    "return_7y", "return_8y", "return_9y", "return_10y", "return_15y",
]


def _lines() -> list[str]:
    return BUILDER.read_text(encoding="utf-8").splitlines()


def _strip(line: str) -> str:
    return re.sub(r"--.*$", "", line)


def _insert_columns() -> list[str]:
    """The column list between 'INSERT INTO screener.universe (' and ')'."""
    lines = _lines()
    start = next(i for i, ln in enumerate(lines)
                 if "INSERT INTO screener.universe (" in ln)
    end = next(i for i in range(start + 1, len(lines))
               if _strip(lines[i]).strip() == ")")
    body = " ".join(_strip(ln).strip() for ln in lines[start + 1:end])
    return [c.strip() for c in body.split(",") if c.strip()]


def _select_expression_count() -> int:
    """Top-level expressions in the matching SELECT.

    Depth-aware: COALESCE(a, b) is one expression, not two, and counting
    commas naively would make this test pass for the wrong reason.
    """
    lines = _lines()
    start = next(i for i, ln in enumerate(lines)
                 if "INSERT INTO screener.universe (" in ln)
    select = next(i for i in range(start, len(lines))
                  if _strip(lines[i]).strip() == "SELECT")

    depth, exprs = 0, 1
    for i in range(select + 1, len(lines)):
        stripped = _strip(lines[i])
        if depth == 0 and re.match(r"^FROM\b", stripped.strip()):
            return exprs
        for ch in stripped:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                exprs += 1
    raise AssertionError("no top-level FROM found; the statement did not end")


# ── Alignment ───────────────────────────────────────────────────────────────

def test_the_insert_and_select_have_the_same_arity():
    columns = _insert_columns()
    exprs = _select_expression_count()
    assert len(columns) == exprs, (
        f"{len(columns)} insert columns against {exprs} select expressions; "
        f"every value past the mismatch lands in the wrong column")


def test_no_column_is_listed_twice():
    """A duplicate shifts everything after it by one and is accepted by
    PostgreSQL only if the types happen to line up -- which, for a table of
    nullable numerics, they usually do."""
    columns = _insert_columns()
    dupes = sorted({c for c in columns if columns.count(c) > 1})
    assert not dupes, f"duplicated insert columns: {dupes}"


def test_the_parser_sees_a_plausible_statement():
    """The control. If the extraction silently matched nothing, both counts
    would be trivially equal and this file would assert that 0 == 0 forever.
    """
    columns = _insert_columns()
    assert len(columns) > 300, (
        f"only {len(columns)} columns extracted; the parser is not reading "
        f"the statement it thinks it is")
    assert columns[-1] == "universe_built_at", (
        f"the column list ends at {columns[-1]!r}, so the closing paren was "
        f"found in the wrong place")


# ── The returns specifically ────────────────────────────────────────────────

def test_every_served_return_is_written():
    """return_2y/4y/6y/8y/9y were absent from this statement entirely. The
    table is upserted, so they kept whatever a long-gone producer left."""
    columns = _insert_columns()
    missing = [r for r in EXPECTED_RETURNS if r not in columns]
    assert not missing, f"served return columns not written: {missing}"


def test_every_return_is_also_updated_on_conflict():
    """Being in the insert list is not enough. A column missing from the
    ON CONFLICT SET list is written once, on first insert, and never again --
    which is the same stale-forever behaviour by a different route."""
    text = BUILDER.read_text(encoding="utf-8")
    conflict = text[text.index("ON CONFLICT (asx_code) DO UPDATE SET"):]
    for name in EXPECTED_RETURNS:
        assert re.search(rf"\b{name}\s*=\s*EXCLUDED\.{name}\b", conflict), (
            f"{name} is inserted but never updated, so it freezes at its "
            f"first written value")


def test_the_multi_year_returns_come_from_daily_metrics():
    """Not from yearly_metrics. That producer anchored without a grace
    bound, ended at the fiscal period end rather than today, and had no
    corporate-action withholding -- it published return_3y = 1449.0 for JNS.
    """
    text = BUILDER.read_text(encoding="utf-8")
    sql = "\n".join(_strip(ln) for ln in text.splitlines())
    for n in (2, 3, 4, 5, 6, 7, 8, 9, 10, 15):
        name = f"return_{n}y"
        assert re.search(rf"\bdm\.{name}\b", sql), (
            f"{name} is not selected from daily_metrics")
        assert not re.search(rf"\bym\.{name}\b", sql), (
            f"{name} is still read from yearly_metrics")


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
