"""Every screener.universe column must have a writer.

test_universe_insert_alignment checks that the builder's INSERT column list
and its SELECT list have the same arity. That catches a positional shift, and
it is blind to the defect this file exists for: a column that is in the TABLE
and in no statement at all.

Ten columns were in exactly that state. Each had a written sibling beside it,
which is why none of them looked wrong:

    analyst_upside              beside analyst_upside_pct
    dps_fy0, dps_fy1            beside eps_fy0, eps_fy1
    franking_credit_per_share   beside franking_pct, grossed_up_yield
    shares_float                beside shares_outstanding
    pay_date                    beside ex_div_date
    adl                         beside obv, cmf_20
    short_name                  beside company_name

A tenth, price_to_52w_high, was the same defect with a worse ending. It
was a registered screener filter, a sort column and a response field, and
it was NOT empty: measured at 2,290 of 2,566 rows populated and frozen,
because it was in neither the INSERT list nor the ON CONFLICT SET list, so
no run ever touched an existing row's value. Of the 1,837 rows that could
be recomputed from their own price and high_52w, 1,674 (91.1%) were wrong
by more than 0.01, median error 0.10 on a ratio whose useful range is 0-1.
Fixed on 10 Nov 2026 and removed from KNOWN_UNWRITTEN below. Empty is
visible; stale is not.

Nothing in the suite could see any of this, because nothing in the suite
asked the question this file asks.

Three writer populations, reconciled
------------------------------------
A column is written if it appears in any of:

  1. the builder's INSERT column list                     (position-paired)
  2. a `UPDATE screener.universe ... SET` in any engine module's literals
  3. the canonical writer's governed registry             (resolved at runtime)

The counts of all three are asserted, not just their union. A refactor that
moves the builder's SQL out of a literal would silently shrink population 1
to zero -- and a coverage check whose population has gone to zero passes.
That is the defect this project has already shipped once, so the population
is checked before the property is.
"""

import ast
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
BUILDER = BACKEND / "scripts" / "eodhd" / "v2" / "build_screener_universe.py"
SNAPSHOT = ROOT / "database" / "stm" / "snap_universe.json"

#: Modules the lineage graph names as writers of screener.universe by UPDATE.
#: Listed rather than globbed: a module that stops writing must fail here and
#: be removed deliberately, not disappear from the population in silence.
UPDATER_MODULES = [
    BACKEND / "compute" / "engine" / "asx_indices.py",
    BACKEND / "compute" / "engine" / "composite_score.py",
    BACKEND / "compute" / "engine" / "dilution_metrics.py",
    BACKEND / "compute" / "engine" / "metric_states.py",
    BACKEND / "compute" / "engine" / "pros_cons.py",
    BACKEND / "compute" / "engine" / "short_positions.py",
    BUILDER,
]

#: Columns with no writer as of 9 Nov 2026, each measured NULL for every row.
#: This list is a declaration of a known defect, NOT a waiver: it may only
#: shrink. An entry removed from it is a column that acquired a writer; a
#: column added to it needs its own finding, because adding one here is
#: shipping a column the product cannot populate.
KNOWN_UNWRITTEN = {
    "adl",
    "analyst_upside",
    "dps_fy0",
    "dps_fy1",
    "franking_credit_per_share",
    "listing_date",
    "pay_date",
    "shares_float",
    "short_name",
}

#: Population sizes at the time this guard was written. These are
#: reconciliation checks: if an extraction returns materially less than this,
#: the extraction broke and its silence is not evidence of coverage.
EXPECT_TARGET_COLUMNS = 376
EXPECT_INSERT_COLUMNS = 342
EXPECT_CONFLICT_SET = 343
EXPECT_UPDATE_ONLY_MIN = 20
EXPECT_GOVERNED_MIN = 70


def _strip(line: str) -> str:
    return re.sub(r"--.*$", "", line)


# ── Population 0: the target columns, from a dated snapshot ─────────────────

def target_columns() -> list[str]:
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = snap["columns"]["screener.universe"]
    declared = snap["meta"]["counts"]["columns"]
    assert len(rows) == declared, (
        f"snapshot declares {declared} columns and carries {len(rows)}; "
        f"it was truncated, and a truncated population under-reports")
    return [r[0] for r in rows]


# ── Population 1: the builder's INSERT ──────────────────────────────────────

def insert_columns() -> list[str]:
    lines = BUILDER.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines)
                 if "INSERT INTO screener.universe (" in ln)
    end = next(i for i in range(start + 1, len(lines))
               if _strip(lines[i]).strip() == ")")
    body = " ".join(_strip(ln).strip() for ln in lines[start + 1:end])
    return [c.strip() for c in body.split(",") if c.strip()]


def conflict_set_columns() -> list[str]:
    """Columns the upsert path reassigns in ON CONFLICT DO UPDATE SET.

    The terminator is the closing triple quote. A blank or comment-only line
    does NOT end the list -- treating `-- Identity` as the end truncated an
    earlier version of this parse to zero columns, which passed.
    """
    lines = BUILDER.read_text(encoding="utf-8").splitlines()
    at = next(i for i, ln in enumerate(lines)
              if "ON CONFLICT" in ln and "screener.universe" not in ln)
    out = []
    for i in range(at + 1, len(lines)):
        raw = lines[i].strip()
        if raw.startswith('"""') or raw.endswith('"""'):
            break
        m = re.match(r"^\s*([a-z_][a-z0-9_]*)\s*=", _strip(lines[i]))
        if m:
            out.append(m.group(1))
    return out


# ── Population 2: UPDATE statements in engine modules ───────────────────────

def _literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield "".join(
                v.value if isinstance(v, ast.Constant)
                and isinstance(v.value, str) else " {?} "
                for v in node.values)


def _set_columns(sql: str) -> list[str]:
    m = re.search(r"\bSET\b(.*?)(?=\bWHERE\b|\bFROM\b|\bRETURNING\b|$)",
                  sql, re.I | re.S)
    if not m:
        return []
    body = re.sub(r"--[^\n]*", "", m.group(1))
    parts, depth, token = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(token)
            token = ""
            continue
        token += ch
    parts.append(token)
    return [m.group(1) for m in
            (re.match(r"\s*([a-z_][a-z0-9_]*)\s*=", p) for p in parts) if m]


def updated_columns() -> dict[str, set[str]]:
    pattern = re.compile(r"UPDATE\s+screener\.universe\b", re.I)
    out: dict[str, set[str]] = {}
    for path in UPDATER_MODULES:
        assert path.exists(), f"{path} is named as a writer and is not there"
        cols: set[str] = set()
        for text in _literals(path):
            if pattern.search(text):
                cols.update(_set_columns(text))
        out[path.name] = cols
    return out


# ── Population 3: the canonical writer's governed registry ──────────────────

def governed_columns() -> set[str]:
    sys.path.insert(0, str(BACKEND))
    from compute.engine.metric_states import LATEST_MODEL_VERSION
    from compute.engine.universe_writer import persisted_governed
    return set(persisted_governed(LATEST_MODEL_VERSION).values())


# ── Populations are checked before the property ─────────────────────────────

def test_the_target_population_is_the_whole_table():
    cols = target_columns()
    assert len(cols) == EXPECT_TARGET_COLUMNS, (
        f"{len(cols)} target columns, expected {EXPECT_TARGET_COLUMNS}. "
        f"If the table really changed, update the constant in the same commit "
        f"as the snapshot -- a guard measuring a population it cannot name is "
        f"not measuring anything.")
    assert len(set(cols)) == len(cols), "duplicate column names in snapshot"


def test_the_insert_population_did_not_collapse():
    cols = insert_columns()
    assert len(cols) == EXPECT_INSERT_COLUMNS, (
        f"the builder's INSERT names {len(cols)} columns, expected "
        f"{EXPECT_INSERT_COLUMNS}")
    assert len(set(cols)) == len(cols), "a column is inserted twice"


def test_the_conflict_set_population_did_not_collapse():
    cols = conflict_set_columns()
    assert len(cols) == EXPECT_CONFLICT_SET, (
        f"ON CONFLICT DO UPDATE SET names {len(cols)} columns, expected "
        f"{EXPECT_CONFLICT_SET}")
    assert len(set(cols)) == len(cols), "a column is reassigned twice"


def test_the_updater_population_did_not_collapse():
    by_module = updated_columns()
    silent = sorted(m for m, c in by_module.items() if not c)
    assert not silent, (
        f"{silent} are named as UPDATE writers of screener.universe and no "
        f"UPDATE statement was found in them. Either they stopped writing and "
        f"belong out of UPDATER_MODULES, or the parse broke -- and a parse "
        f"that finds nothing reports full coverage.")
    total = {c for cols in by_module.values() for c in cols}
    assert len(total) >= EXPECT_UPDATE_ONLY_MIN, (
        f"only {len(total)} updated columns found across "
        f"{len(by_module)} modules")


def test_the_governed_population_did_not_collapse():
    cols = governed_columns()
    assert len(cols) >= EXPECT_GOVERNED_MIN, (
        f"the governed registry resolves {len(cols)} storage columns, "
        f"expected at least {EXPECT_GOVERNED_MIN}")


# ── The property ────────────────────────────────────────────────────────────

def _writers_by_column() -> dict[str, list[str]]:
    writers: dict[str, list[str]] = {}
    for col in insert_columns():
        writers.setdefault(col, []).append("build_screener_universe (INSERT)")
    for module, cols in updated_columns().items():
        for col in cols:
            writers.setdefault(col, []).append(f"{module} (UPDATE)")
    for col in governed_columns():
        writers.setdefault(col, []).append("universe_writer (canonical)")
    return writers


def test_every_universe_column_has_a_writer():
    writers = _writers_by_column()
    unwritten = {c for c in target_columns() if c not in writers}

    new = sorted(unwritten - KNOWN_UNWRITTEN)
    assert not new, (
        f"{new} exist in screener.universe and no statement writes them. They "
        f"will be NULL for every company, and a screener filter over such a "
        f"column returns nothing while reporting no error. Wire a writer, or "
        f"drop the column -- do not add it to KNOWN_UNWRITTEN without a "
        f"finding that says why the product ships it unpopulated.")


def test_the_known_unwritten_list_only_shrinks():
    writers = _writers_by_column()
    fixed = sorted(c for c in KNOWN_UNWRITTEN if c in writers)
    assert not fixed, (
        f"{fixed} now have writers and are still listed as unwritten. Remove "
        f"them from KNOWN_UNWRITTEN: a stale exception hides the next real one.")


def test_no_statement_writes_a_column_that_does_not_exist():
    """The other direction: a write to a column the table does not have.

    Postgres rejects it at runtime, so this only fails before deployment --
    which is the point, since the statement that would fail is the one that
    publishes the universe.
    """
    target = set(target_columns())
    stray = sorted(c for c in _writers_by_column() if c not in target)
    assert not stray, (
        f"{stray} are assigned by a statement and are not columns of "
        f"screener.universe")


def test_every_inserted_column_is_refreshed_on_conflict_except_the_key():
    """An inserted column left out of DO UPDATE SET keeps its old value.

    The row is upserted every run, so a column that is not reassigned holds
    whatever the first insert put there -- for as long as the row survives.
    """
    inserted = set(insert_columns())
    refreshed = set(conflict_set_columns())
    stale = sorted(inserted - refreshed - {"asx_code"})
    assert not stale, (
        f"{stale} are inserted and never reassigned on conflict; after the "
        f"first run they are frozen at their original value")


def test_the_stm_tooling_cannot_write_what_it_reads():
    """No mapping tool both connects to the database and carries write SQL.

    canonical_boundary excludes scripts/stm/ from its tree-wide writer scan,
    because these tools carry the pipeline's SQL as DATA -- `INSERT INTO
    screener.universe (` as a literal to find, `UPDATE\\s+screener\\.universe`
    as a pattern to match. Without the exclusion the analyser is reported as
    a writer of the table it analyses, and SECOND PUBLICATION AUTHORITY fires
    on an instrument.

    An exclusion is a hole, so the property that makes it safe is asserted
    here instead of assumed there. Two files connect and carry no write text;
    four carry write text and never connect. A file that did both would be
    excluded from the writer scan while being able to write, which is the one
    combination the exclusion must not cover.

    A read-only instrument has already OOM-killed this production database
    once. "It only reads" is a claim that needs a check, not a comment.
    """
    stm = BACKEND / "scripts" / "stm"
    assert stm.is_dir(), f"{stm} is missing"

    connects = re.compile(r"psycopg|connect\(|DATABASE_URL")
    writes = re.compile(
        r"\b(INSERT\s+INTO|UPDATE\s+(?:ONLY\s+)?[a-z_]+\.|DELETE\s+FROM"
        r"|TRUNCATE|CREATE\s+TABLE|MERGE\s+INTO)", re.IGNORECASE)

    both, seen = [], 0
    for path in sorted(stm.glob("*.py")):
        seen += 1
        src = path.read_text(encoding="utf-8")
        if connects.search(src) and writes.search(src):
            both.append(path.name)

    assert seen >= 8, (
        f"only {seen} files found under {stm}; the scan lost its population "
        f"and an empty scan finds no violation")
    assert not both, (
        f"{both} both open a database connection and contain write-shaped "
        f"SQL. canonical_boundary excludes this directory from its writer "
        f"scan, so such a file could write a canonical output with no "
        f"publication authority and nothing would report it. Split the "
        f"reading from the writing, or remove the exclusion.")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed, failed = 0, []
    for fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed.append((fn.__name__, str(exc)))
        except Exception as exc:  # noqa: BLE001 - a broken parse must report
            failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
    for name, msg in failed:
        print(f"FAIL {name}\n     {msg}\n")
    print(f"{passed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
