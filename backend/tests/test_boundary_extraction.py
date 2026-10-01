"""
Extraction discovers; classification decides
=============================================
`canonical_boundary` derives canonical ownership from the stages' SQL. Until
1 Oct 2026 it derived it from a hand-maintained tuple of four schema names,
and the table pattern was built from that tuple — so `users` (201 SQL
references), `meta`, `support` and `strategy` were not merely unclassified,
they were INVISIBLE. `tables_touched(top5_strategy.py)` returned no writes for
a job that INSERTs, UPDATEs and DELETEs `strategy.monthly_picks`, and its
launch-authority finding therefore described it as read-only.

The rule this file enforces:

    Extraction must not decide visibility. Classification decides relevance.

An enumeration that controls what can be SEEN hides things by omission, and
omission is invisible by construction — which is why this went unnoticed for
as long as the module has existed.

The fictional-schema fixture is the load-bearing test. Anyone can widen a list
from four schemas to five; only a genuinely generic extractor sees a schema
that appears nowhere in this repository.

Run under pytest, or standalone:
    cd backend && ../asx-venv/bin/python tests/test_boundary_extraction.py
"""

import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from compute.engine import canonical_boundary as cb                # noqa: E402

#: A schema name that appears nowhere else in the codebase. Verified by
#: `grep -ri zarquon` returning nothing. If the extractor can see this, it is
#: generic; if it can only see a wider enumeration, it cannot.
FICTIONAL = "zarquon"


def _file(sql: str, suffix=".py") -> Path:
    """A throwaway module whose only content is one SQL string."""
    tmp = Path(tempfile.mkdtemp()) / f"probe{suffix}"
    body = f'QUERY = """\n{sql}\n"""\n' if suffix == ".py" else sql
    tmp.write_text(body, encoding="utf-8")
    return tmp


# ── The criterion that cannot be satisfied by widening a list ────────────────

def test_a_schema_that_exists_nowhere_is_still_discovered():
    t, u = cb.relations(_file(
        f"SELECT * FROM {FICTIONAL}.ledger JOIN {FICTIONAL}.entries ON TRUE"))
    assert f"{FICTIONAL}.ledger" in t and f"{FICTIONAL}.entries" in t
    assert t[f"{FICTIONAL}.ledger"] == {"r"}
    assert not u


def test_writes_to_an_unknown_schema_are_writes():
    t, _ = cb.relations(_file(f"INSERT INTO {FICTIONAL}.ledger (a) VALUES (1)"))
    assert t[f"{FICTIONAL}.ledger"] == {"w"}


def test_extraction_does_not_consult_the_canonical_schema_list():
    """The structural guarantee. If CANONICAL_SCHEMAS appeared in the
    patterns again, the enumeration would be back in control of visibility."""
    src = (BACKEND / "compute/engine/canonical_boundary.py").read_text(
        encoding="utf-8")
    patterns = src[src.index("_IDENT ="):src.index("def _executable_source")]
    assert "CANONICAL_SCHEMAS" not in patterns
    assert "SCHEMAS" not in patterns


# ── Every write form, and aliased DML ────────────────────────────────────────

def test_each_write_form_is_captured():
    forms = {
        f"INSERT INTO {FICTIONAL}.t (a) VALUES (1)": "w",
        f"DELETE FROM {FICTIONAL}.t WHERE a = 1": "w",
        f"UPDATE {FICTIONAL}.t SET a = 1": "w",
        f"TRUNCATE TABLE {FICTIONAL}.t": "w",
        f"MERGE INTO {FICTIONAL}.t USING src ON TRUE": "w",
        f"COPY {FICTIONAL}.t FROM STDIN": "w",
        f"SELECT * FROM {FICTIONAL}.t": "r",
        f"SELECT * FROM a JOIN {FICTIONAL}.t ON TRUE": "r",
    }
    for sql, direction in forms.items():
        t, _ = cb.relations(_file(sql))
        assert f"{FICTIONAL}.t" in t, f"missed: {sql}"
        assert direction in t[f"{FICTIONAL}.t"], f"wrong direction: {sql}"


def test_aliased_dml_stays_visible():
    """`UPDATE schema.table alias SET ...` is the shape short_positions uses.
    A pattern demanding SET immediately after the name reports no write."""
    t, _ = cb.relations(_file(
        f"UPDATE {FICTIONAL}.t AS x SET a = 1 FROM other o WHERE x.id = o.id"))
    assert t[f"{FICTIONAL}.t"] == {"w"}
    cols = cb.columns_written(_file(f"UPDATE {FICTIONAL}.t x SET a=1, b=2"),
                              f"{FICTIONAL}.t")
    assert cols == {"a", "b"}


def test_nested_sql_is_reached():
    t, _ = cb.relations(_file(f"""
        INSERT INTO {FICTIONAL}.dest (a)
        SELECT a FROM {FICTIONAL}.src WHERE a IN (
            SELECT a FROM {FICTIONAL}.inner_src)
    """))
    assert t[f"{FICTIONAL}.dest"] == {"w"}
    assert t[f"{FICTIONAL}.src"] == {"r"}
    assert t[f"{FICTIONAL}.inner_src"] == {"r"}


# ── What must NOT be mistaken for a relation ─────────────────────────────────

def test_ctes_aliases_and_derived_tables_are_not_relations():
    t, _ = cb.relations(_file(f"""
        WITH recent AS (SELECT * FROM {FICTIONAL}.t),
             ranked AS (SELECT * FROM recent)
        SELECT * FROM ranked r
        JOIN (SELECT 1) derived ON TRUE
        JOIN recent ON TRUE
    """))
    assert set(t) == {f"{FICTIONAL}.t"}, t


def test_python_imports_are_not_relations():
    """The false positive the old enumeration was concealing. `from
    compute.engine.run_plans import PLANS` matches FROM <qualified> exactly;
    it only stayed hidden because `compute` was not a listed schema."""
    tmp = Path(tempfile.mkdtemp()) / "mod.py"
    tmp.write_text("from compute.engine.run_plans import PLANS\n"
                   "import os.path\n", encoding="utf-8")
    t, _ = cb.relations(tmp)
    assert t == {}, t


def test_a_docstring_mentioning_a_table_is_not_a_reference():
    tmp = Path(tempfile.mkdtemp()) / "mod.py"
    tmp.write_text(f'"""This module never reads FROM {FICTIONAL}.t."""\n'
                   "X = 1\n", encoding="utf-8")
    assert cb.relations(tmp)[0] == {}


def test_commented_sql_is_not_a_reference():
    t, _ = cb.relations(_file(
        f"-- SELECT * FROM {FICTIONAL}.commented\n"
        f"/* FROM {FICTIONAL}.blocked */\n"
        f"SELECT * FROM {FICTIONAL}.real_one"))
    assert set(t) == {f"{FICTIONAL}.real_one"}, t


# ── Unresolvable is a state, not a silence ───────────────────────────────────

def test_dynamic_sql_becomes_unresolved_not_nothing():
    """A producer whose target is computed at runtime is the one most worth
    knowing about. Reporting it as 'no tables' is the failure mode."""
    t, u = cb.relations(_file('SELECT * FROM {table} WHERE a = 1'))
    assert t == {}
    assert u and "FROM" in u[0]


def test_parameterised_relation_position_is_unresolved():
    _, u = cb.relations(_file("INSERT INTO %(target)s (a) VALUES (1)"))
    assert u, "a %-format relation must be reported, not dropped"


def test_the_real_dynamic_case_in_this_repo_is_reported():
    """transform_prices builds `FROM {table}` in _digest_sql. Before this,
    that reference did not exist as far as the boundary was concerned."""
    u = cb.unresolved_relations(
        BACKEND / "scripts/eodhd/v2/transforms/transform_prices.py")
    assert u, "the digest query's computed relation is still invisible"


# ── Mutation controls ────────────────────────────────────────────────────────

def test_the_extractor_is_not_simply_finding_everything():
    """If it matched any dotted token it would 'pass' every test above while
    reporting nonsense."""
    t, _ = cb.relations(_file("SELECT a.b FROM x WHERE c.d = e.f"))
    assert t == {}, t


def test_direction_is_not_uniform():
    """A reader recorded as a writer would make every stage look dangerous;
    a writer recorded as a reader makes one look harmless. Both are failures,
    so the two directions must actually differ."""
    r, _ = cb.relations(_file(f"SELECT * FROM {FICTIONAL}.t"))
    w, _ = cb.relations(_file(f"DELETE FROM {FICTIONAL}.t"))
    assert r[f"{FICTIONAL}.t"] == {"r"}
    assert w[f"{FICTIONAL}.t"] == {"w"}


def test_a_python_import_inside_a_string_is_not_a_relation():
    """budget_audit.py builds a subprocess command containing
    "import asyncio; from app.workers.announcement_worker import ..." and
    `FROM app.workers` matched it perfectly once extraction stopped
    enumerating schemas -- the old allow-list had been hiding it.

    The discriminator is the `import` that follows: `from X.Y import Z` is
    not a shape SQL has.
    """
    t, _ = cb.relations(_file(
        "import asyncio; from app.workers.announcement_worker import run"))
    assert t == {}, t


def test_the_import_exclusion_does_not_swallow_real_sql():
    """The control. A rule that stripped anything containing the word
    `import` would hide real relations alongside the false positive."""
    t, _ = cb.relations(_file(
        f"SELECT * FROM {FICTIONAL}.import_log WHERE imported = TRUE"))
    assert t == {f"{FICTIONAL}.import_log": {"r"}}, t


def test_a_docstring_with_an_escape_is_still_stripped():
    """ast.get_docstring returns the PARSED value, so a docstring holding a
    line continuation never matches its own source text and stripping it by
    string replacement silently removes nothing.

    Tested against the real file rather than a fixture, because the real
    file is what exposed it: incremental_daily.py says
    "- Does NOT update screener.universe", that line survived stripping, the
    extractor recorded a WRITE from a sentence asserting the opposite, and
    the file was quarantined as a latent canonical writer on that basis.
    Ten docstrings in this tree have the same shape.
    """
    import ast as _ast
    p = BACKEND / "scripts/eodhd/v2/jobs/incremental_daily.py"
    src = p.read_text(encoding="utf-8")
    doc = _ast.get_docstring(_ast.parse(src), clean=False)

    assert doc and doc not in src, (
        "this file no longer reproduces the escape case; pick another")
    assert "screener.universe" in doc, (
        "the docstring no longer names the table, so this proves nothing")

    assert cb.relations(p)[0] == {}, (
        "docstring prose leaked into the executable source and was read as SQL")


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
        except Exception as e:                                     # noqa: BLE001
            failures.append(name)
            print(f"  ERROR {name}  - {type(e).__name__}: {e}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
