"""
An upsert must not read as an append
====================================
The lineage extractor classified 25 of 42 tables as "insert-only (append)"
while they were upserting on every run -- market.short_positions and
market.period_metrics among them.

Two independent causes, and fixing either alone left the other:

  1. INSERT ... ON CONFLICT DO UPDATE contains no `UPDATE <table>`
     statement, so it matched none of the UPDATE write-patterns.

  2. An f-string is an ast.JoinedStr of Constant fragments. Walking for
     Constants alone shredded one statement into pieces, so the INSERT and
     the ON CONFLICT landed in different strings and could never be seen
     together. technical_compute.py builds its entire upsert that way.

A mapping document that says a table only ever appends, when every run
rewrites the same keys, is wrong about the one property that decides
whether history exists.

The reconciliation tests at the end exist because the JoinedStr change could
plausibly DOUBLE-COUNT: a fragment yielded both inside its JoinedStr and
again on its own would inflate every operation set. Table, parse-error and
dynamic-target counts are asserted against the committed artifact.

Run under pytest, or standalone:
    cd backend && python tests/test_lineage_write_strategy.py
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_spec = importlib.util.spec_from_file_location(
    "stm_extract_lineage", BACKEND / "scripts" / "stm" / "extract_lineage.py")
lineage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lineage)

_gspec = importlib.util.spec_from_file_location(
    "stm_generate_stm", BACKEND / "scripts" / "stm" / "generate_stm.py")
generate = importlib.util.module_from_spec(_gspec)
_gspec.loader.exec_module(generate)

LINEAGE_JSON = BACKEND.parent / "database" / "stm" / "lineage.json"


def _ops(source: str, table: str = "market.t") -> set:
    """Operations the extractor finds for `table` in a module of `source`."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.py"
        path.write_text(source, encoding="utf-8")
        result = lineage.analyse_module(path)
    assert "error" not in result, result.get("error")
    # Normalised to a set here: analyse_module returns whatever container it
    # built, and a test that assumed one would pass or fail on the container
    # type rather than on the operations found.
    return set(result["writes"].get(table, ()))


# ── ON CONFLICT in an ordinary string literal ────────────────────────────────

PLAIN_UPSERT = '''
SQL = """
    INSERT INTO market.t (a, b)
    VALUES %s
    ON CONFLICT (a) DO UPDATE SET
        b = EXCLUDED.b
"""
'''

PLAIN_DO_NOTHING = '''
SQL = """
    INSERT INTO market.t (a, b)
    VALUES %s
    ON CONFLICT (a) DO NOTHING
"""
'''

PLAIN_INSERT = '''
SQL = """
    INSERT INTO market.t (a, b) VALUES %s
"""
'''


def test_on_conflict_do_update_is_an_upsert():
    ops = _ops(PLAIN_UPSERT)
    assert "upsert" in ops, (
        f"ON CONFLICT DO UPDATE read as {sorted(ops)}; an upsert that reads "
        f"as an append misstates whether the table keeps history")


def test_on_conflict_do_nothing_is_not_an_upsert():
    """DO NOTHING and DO UPDATE are different load strategies.

    Under DO NOTHING the first write stands and a correction never lands.
    Collapsing the two would hide that.
    """
    ops = _ops(PLAIN_DO_NOTHING)
    assert "insert-or-ignore" in ops, sorted(ops)
    assert "upsert" not in ops, (
        "DO NOTHING was classified as an upsert, so a table that silently "
        "refuses corrections would be documented as rewriting them")


def test_a_plain_insert_stays_a_plain_insert():
    """The control. Without it, a rule that marked every INSERT an upsert
    would pass both tests above."""
    ops = _ops(PLAIN_INSERT)
    assert ops == {"insert"}, sorted(ops)


# ── ON CONFLICT split across f-string fragments ──────────────────────────────

FSTRING_UPSERT = '''
COLS = ["a", "b"]
SQL = f"""
    INSERT INTO market.t ({", ".join(COLS)})
    VALUES %s
    ON CONFLICT (a) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in COLS if c != "a")}
"""
'''


def test_an_fstring_upsert_is_seen_whole():
    """The shape technical_compute.py actually uses.

    The INSERT and the ON CONFLICT are in different Constant fragments of
    one JoinedStr. Reading fragments separately can never see them together,
    which is why fixing the ON CONFLICT pattern alone left
    market.computed_metrics, market.daily_metrics and
    market.halfyearly_metrics still reading as append-only against run logs
    that say "rows upserted".
    """
    ops = _ops(FSTRING_UPSERT)
    assert "insert" in ops, (
        f"the f-string INSERT target was lost entirely: {sorted(ops)}")
    assert "upsert" in ops, (
        f"f-string upsert read as {sorted(ops)}; the ON CONFLICT sits in a "
        f"different JoinedStr fragment from the INSERT")


def test_fstring_fragments_are_not_counted_twice():
    """A JoinedStr must be yielded whole OR in pieces, never both.

    Double-yielding would not change this set (operations are a set), but it
    would inflate read/join collection and make every downstream count
    unreliable. Asserted on the literal stream itself.
    """
    import ast
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.py"
        path.write_text(FSTRING_UPSERT, encoding="utf-8")
        tree = ast.parse(path.read_text(encoding="utf-8"))
    literals = list(lineage._sql_literals(tree))
    assert len(literals) == 1, (
        f"{len(literals)} SQL literals from one f-string statement; "
        f"fragments are being emitted alongside the reassembled string")
    assert "INSERT INTO market.t" in literals[0][1]
    assert "ON CONFLICT" in literals[0][1]


def test_interpolations_are_marked_not_dropped():
    """A runtime-computed column list must not read as absent SQL."""
    import ast
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.py"
        path.write_text(FSTRING_UPSERT, encoding="utf-8")
        tree = ast.parse(path.read_text(encoding="utf-8"))
    text = list(lineage._sql_literals(tree))[0][1]
    assert "{...}" in text, (
        "interpolations vanished, so a dynamically built column list is "
        "indistinguishable from SQL that never had one")


# ── The strategy names the document actually prints ──────────────────────────

def _strategy(ops: set, table: str = "market.t") -> str:
    fake = {"by_table": {table: {"written_by": [{"module": "m.py",
                                                 "operations": sorted(ops)}]}}}
    return generate.load_strategy_of(fake, table)


def test_upsert_is_named_as_an_upsert():
    assert "upsert" in _strategy({"insert", "upsert"}).lower()
    assert "append" not in _strategy({"insert", "upsert"}).lower()


def test_do_nothing_says_corrections_do_not_land():
    s = _strategy({"insert", "insert-or-ignore"})
    assert "NOT corrected" in s, (
        f"{s!r} does not warn that an existing row is left alone; that is "
        f"the whole difference between DO NOTHING and DO UPDATE")


def test_truncate_plus_upsert_reports_both_paths():
    s = _strategy({"insert", "upsert", "truncate"})
    assert "upsert" in s and "TRUNCATE" in s, s


def test_a_real_append_only_table_is_still_called_append_only():
    """The control for the strategy namer."""
    assert _strategy({"insert"}) == "insert-only (append)"


# ── Reconciliation against the committed artifact ────────────────────────────

def _lineage() -> dict:
    if not LINEAGE_JSON.exists():
        raise AssertionError(f"{LINEAGE_JSON} is missing; regenerate it")
    return json.loads(LINEAGE_JSON.read_text(encoding="utf-8"))


#: Write targets the lineage scan sees. Moved once, deliberately.
#:
#:   66  scripts/ and compute/ only
#:   85  after app/ joined SOURCE_TREES on 10 Nov 2026
#:
#: The 19 added are written by request handlers and scheduled workers under
#: app/. They were always there; the scan was not looking. That omission
#: undercut every "nothing writes this column" claim made from the graph,
#: because an absence proved nothing about a population that excluded a
#: whole tree -- so the number moving was the point of the change, not a
#: side effect of it.
#:
#: Finding 11 was re-checked against the wider population and still holds:
#: screener.universe has exactly nine writers and none is under app/.
EXPECT_TABLES_WRITTEN = 85


def test_the_artifact_still_covers_the_same_table_population():
    """Reassembling f-strings must not add or lose write targets.

    The number above is a reconciliation check, not a setting. Update it
    only together with the reason it moved; a number edited to match
    whatever the scan happened to produce is not a check of anything.
    """
    assert _lineage()["tables_written"] == EXPECT_TABLES_WRITTEN, (
        f"the write-target population moved to "
        f"{_lineage()['tables_written']}; confirm deliberately and record "
        f"why, rather than updating this number to match")


def test_the_artifact_has_no_parse_errors_or_dynamic_targets():
    lin = _lineage()
    assert lin["parse_errors"] == [], lin["parse_errors"]
    dynamic = sum(len(m.get("dynamic", []))
                  for m in lin["by_module"].values())
    assert dynamic == 0, (
        f"{dynamic} write target(s) are interpolated rather than literal, so "
        f"the lineage cannot name what they write")


def test_every_table_is_classified():
    assert _lineage().get("layer_conflicts") == {}, (
        "a table is in no layer declaration; it would default into a layer "
        "and the mapping for that layer would take a wrong population")


def test_no_table_with_an_on_conflict_writer_reads_as_append_only():
    """The population check, against the real codebase rather than fixtures.

    A fixture proves the rule fires; this proves it fires everywhere it
    should. Every writer module is re-read and any table whose SQL carries
    ON CONFLICT must not be described as append-only.
    """
    lin = _lineage()
    wrong = []
    for table, info in lin["by_table"].items():
        ops = {op for w in info["written_by"] for op in w["operations"]}
        strategy = generate.load_strategy_of(lin, table)
        if "append" in strategy and ("upsert" in ops or "insert-or-ignore" in ops):
            wrong.append(f"{table}: ops={sorted(ops)} -> {strategy}")
    assert not wrong, "\n".join(wrong)


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
