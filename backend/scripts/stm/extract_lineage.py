"""
Which job writes which table, read off the jobs
===============================================
A source-to-target mapping needs a third fact beyond source and target: the
process that moves one to the other. That fact is routinely the stalest thing
in a mapping document, because it is the part a human types from memory.

This reads it instead. Every module under the pipeline and compute trees is
parsed, every SQL string literal in it is examined, and each statement is
classified by what it does to which table:

    writes   INSERT INTO x / UPDATE x / DELETE FROM x / TRUNCATE x /
             COPY x FROM / CREATE TABLE x AS / MERGE INTO x
    reads    FROM x / JOIN x / USING x

The result is a table-level lineage graph: for each target table, the modules
that write it and the tables those modules read. That is enough to populate
the "Transformation job", "Tables involved" and "Join condition" columns of
the mapping documents without anybody retyping them, and enough to draw the
dependency edges the run sheet needs.

What this is and is not
-----------------------
It is a STATIC read. A module that builds SQL by concatenation, or routes a
table name through a variable, is reported as `dynamic` rather than guessed
at -- those are listed explicitly so the gap is visible instead of absent.
Silence would be the dangerous outcome: a lineage graph missing an edge looks
exactly like a lineage graph that has no such edge.

It also does not claim to be semantics. Knowing that `yearly_compute.py`
writes `market.yearly_metrics` and reads `financials.annual_pnl` is lineage;
knowing that `roe = net_profit / shareholders_equity` is derivation, and that
is authored, reviewed prose that lives in the YAML sidecar.

Usage:
    cd backend && python scripts/stm/extract_lineage.py \
        --out ../database/stm/lineage.json
    ... --print     human-readable summary to stdout

Exit codes:  0 lineage extracted
             2 nothing to parse -- never a silent empty graph
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

#: Where the pipeline lives. Anything outside these trees is not part of the
#: Bronze -> Silver -> Gold -> Universe lineage and would only add noise.
#: Widened on 6 November 2026. The first version scanned only scripts/eodhd
#: and compute, and missed backend/scripts/*.py entirely -- which is where
#: load_fmp_financials.py lives, the ONLY writer of
#: financials.annual_cashflow.equity_raised, a column yearly_compute consumes
#: as a governed input. A lineage graph that silently omits a directory
#: reports "no writer" for columns that have one, which is the same sentence
#: a genuinely dead column produces. Scan the tree and exclude by name, so a
#: new directory is included by default rather than forgotten.
SOURCE_TREES = (
    BACKEND / "scripts",
    BACKEND / "compute",
)

#: Directories under the scanned trees that are not pipeline code. Excluded
#: by name and listed in the output, so the exclusions are visible.
EXCLUDED_DIRS = frozenset({"__pycache__", "stm"})

#: The layers. A table in none of these is out of scope for the mapping
#: documents -- users, ai, meta, support and strategy are the product's own
#: state, not the data pipeline.
LAYER_OF_SCHEMA = {
    "staging_au": "Bronze",
    "financials": "Silver",
    "market":     "Silver/Gold",     # split per-table by TABLE_LAYER below
    "screener":   "Universe",
}

#: market.* holds both conformed entities and computed measures. The split is
#: by table, not by schema, and it is declared rather than guessed: a name
#: heuristic ("anything ending in _metrics is Gold") would silently
#: misclassify the next table somebody adds.
TABLE_LAYER = {
    # Silver — conformed entities, one row per real-world thing
    "market.companies":          "Silver",
    "market.companies_current":  "Silver",
    "market.daily_prices":       "Silver",
    "market.dividends":          "Silver",
    "market.splits":             "Silver",
    "market.shares_history":     "Silver",
    "market.exchange_list":      "Silver",
    "market.funds":              "Silver",
    "market.fund_prices":        "Silver",
    "market.index_prices":       "Silver",
    "market.global_index_prices": "Silver",
    "market.commodity_prices":   "Silver",
    "market.fx_rates":           "Silver",
    "market.short_positions":    "Silver",
    "market.asx_announcements":  "Silver",
    "market.analyst_ratings":    "Silver",
    "market.earnings_quarterly": "Silver",
    "market.capital_raises":     "Silver",
    # Added 9 Nov 2026. Both were absent, so both fell through to the old
    # "market.* not named here is Gold" default and were classified Gold
    # while being written by Bronze->Silver transforms. The Bronze->Silver
    # mapping took its population from this classification and reported
    # "366/366 mapped, gate passes" over a layer missing two of its tables.
    "market.short_interest":     "Silver",
    "market.valuation_snapshot": "Silver",
}

#: Gold — computed measures, derived from Silver rather than landed from a
#: source. Declared for the same reason the Silver list is: an inferred
#: classification is only as good as its proxy, and every proxy available
#: here is a fact about the CODE rather than about the DATA.
#:
#: A writer-location heuristic was tried and discarded on 9 Nov 2026:
#: compute/engine/fund_prices.py writes market.fund_prices, a conformed
#: Silver entity, so "lives in compute/engine" implied Gold for seven Silver
#: tables. Seven false alarms on a line that exists to carry real ones is
#: worse than no line at all.
TABLE_LAYER_GOLD = {
    "market.anomalies", "market.computed_metrics", "market.daily_metrics",
    "market.exdiv_snapshots", "market.global_indices",
    "market.halfyearly_metrics", "market.heatmap_cache",
    "market.heatmap_labels", "market.index_snapshots",
    "market.mining_metrics", "market.monthly_metrics",
    "market.mover_snapshots", "market.period_metrics",
    "market.price_predictions", "market.quarterly_metrics",
    "market.reit_metrics", "market.sector_benchmarks",
    "market.sector_snapshots", "market.weekly_metrics",
    "market.yearly_metrics",
}

#: Neither Silver nor Gold: pipeline control and telemetry. Named rather than
#: omitted, so "not a data layer" is a decision on the record instead of a
#: table nobody classified.
TABLE_LAYER_CONTROL = {
    "market.pipeline_runs": "run-level telemetry written by the daily "
                            "pipeline; carries no business data",
    "market.pipeline_step_runs": "per-step telemetry written by the daily "
                                 "pipeline; carries no business data",
}


def classify(table: str, modules: list) -> dict:
    """Layer, and how it was decided — never a silent default.

    Every market.* table must appear in exactly one declaration. One that
    appears in none is UNCLASSIFIED and says so; it is not quietly assigned.

    The previous version returned "Gold" for any unnamed market.* table, and
    that default was indistinguishable from a decision. It is how
    market.short_interest and market.valuation_snapshot — both written by
    Bronze->Silver transforms — came to sit in the Gold layer, and how the
    Bronze->Silver mapping came to report itself complete over a layer that
    was missing two of its twenty-two tables.
    """
    if table in TABLE_LAYER:
        return {"layer": TABLE_LAYER[table], "layer_source": "declared"}
    if table in TABLE_LAYER_GOLD:
        return {"layer": "Gold", "layer_source": "declared"}
    if table in TABLE_LAYER_CONTROL:
        return {"layer": "control", "layer_source": "declared",
                "layer_note": TABLE_LAYER_CONTROL[table]}

    schema = table.split(".", 1)[0]
    base = LAYER_OF_SCHEMA.get(schema)
    if base is None:
        return {"layer": "out-of-scope", "layer_source": "schema"}
    if base != "Silver/Gold":
        return {"layer": base, "layer_source": "schema"}

    return {"layer": "UNCLASSIFIED", "layer_source": "none",
            "layer_conflict": (
                f"{table} is written by "
                f"{', '.join(m.rsplit('/', 1)[-1] for m in modules) or 'nothing'} "
                f"but appears in no layer declaration. Add it to TABLE_LAYER, "
                f"TABLE_LAYER_GOLD or TABLE_LAYER_CONTROL deliberately — a "
                f"table that defaults into a layer is a table nobody placed.")}

WRITE_PATTERNS = [
    ("insert",   re.compile(r"\bINSERT\s+INTO\s+([a-z_]+\.[a-z_]+)", re.I)),
    ("update",   re.compile(r"\bUPDATE\s+(?:ONLY\s+)?([a-z_]+\.[a-z_]+)", re.I)),
    ("delete",   re.compile(r"\bDELETE\s+FROM\s+(?:ONLY\s+)?([a-z_]+\.[a-z_]+)", re.I)),
    ("truncate", re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?([a-z_]+\.[a-z_]+)", re.I)),
    ("copy",     re.compile(r"\bCOPY\s+([a-z_]+\.[a-z_]+)\s*(?:\([^)]*\))?\s*FROM", re.I)),
    ("ctas",     re.compile(r"\bCREATE\s+(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)?TABLE\s+"
                            r"(?:IF\s+NOT\s+EXISTS\s+)?([a-z_]+\.[a-z_]+)\s+AS", re.I)),
    ("merge",    re.compile(r"\bMERGE\s+INTO\s+([a-z_]+\.[a-z_]+)", re.I)),
]

#: ON CONFLICT turns an INSERT into an upsert (DO UPDATE) or a skip
#: (DO NOTHING). The two are different load strategies and must not collapse:
#: DO UPDATE rewrites an existing row, DO NOTHING leaves the first write
#: standing, so under DO NOTHING a correction never lands.
ON_CONFLICT = re.compile(r"\bON\s+CONFLICT\b", re.I)
ON_CONFLICT_DO_UPDATE = re.compile(r"\bON\s+CONFLICT\b.*?\bDO\s+UPDATE\b", re.I | re.S)

READ_PATTERNS = [
    re.compile(r"\bFROM\s+(?:ONLY\s+)?([a-z_]+\.[a-z_]+)", re.I),
    re.compile(r"\bJOIN\s+([a-z_]+\.[a-z_]+)", re.I),
    re.compile(r"\bUSING\s+([a-z_]+\.[a-z_]+)", re.I),
]

#: ON <condition> following a JOIN. The join condition is a column the user
#: explicitly asked for, and it is knowable from the text.
JOIN_ON = re.compile(
    r"\bJOIN\s+([a-z_]+\.[a-z_]+)(?:\s+(?:AS\s+)?([a-z_][a-z_0-9]*))?\s+ON\s+(.+?)"
    r"(?=\s+(?:LEFT|RIGHT|INNER|FULL|CROSS|JOIN|WHERE|GROUP|ORDER|LIMIT|UNION|\)|$))",
    re.I | re.S)

#: A statement whose target is interpolated rather than literal. Reported, not
#: silently dropped: an edge nobody can see is indistinguishable from an edge
#: that does not exist.
DYNAMIC_TARGET = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?|MERGE\s+INTO)\s+"
    r"(\{[a-z_]+\}|%s|\$\{)", re.I)

#: Only strings long enough and shaped like SQL. Parsing every literal in the
#: tree would match docstrings that discuss SQL -- which is how a guard ends
#: up reading its own explanation.
SQL_SHAPED = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|TRUNCATE|COPY|MERGE|CREATE\s+TABLE)\b", re.I)


def layer_of(table: str) -> str:
    """Declared layer only, with no writer evidence and no default.

    Retained for callers that have a table name and nothing else. It cannot
    classify an undeclared market.* table and says so rather than guessing;
    `classify(table, modules)` is what the graph build uses.
    """
    if table in TABLE_LAYER:
        return TABLE_LAYER[table]
    schema = table.split(".", 1)[0]
    layer = LAYER_OF_SCHEMA.get(schema)
    if layer == "Silver/Gold":
        return "UNCLASSIFIED"
    return layer or "out-of-scope"


def _joined_str_text(node: ast.JoinedStr) -> str:
    """An f-string reassembled, with each interpolation as a placeholder.

    An f-string is a JoinedStr of Constant fragments and FormattedValue
    holes, so walking for Constants alone shreds one statement into pieces.
    That is not cosmetic: technical_compute.py builds

        INSERT INTO market.daily_metrics ({", ".join(INSERT_COLS)})
        VALUES %s
        ON CONFLICT (asx_code, date) DO UPDATE SET ...

    as ONE f-string, and the INSERT and the ON CONFLICT land in different
    fragments. A test asking whether an INSERT carries ON CONFLICT then
    always fails, and the table reads as append-only while every run
    rewrites the same keys.

    The interpolations become a marker rather than being dropped, so a
    column list computed at runtime cannot be mistaken for absent SQL.
    """
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append(" {...} ")
    return "".join(parts)


def _sql_literals(tree: ast.AST):
    """Every string in the module that looks like SQL, f-strings reassembled.

    JoinedStr is yielded whole and its fragments are NOT yielded again:
    emitting both would double-count operations on the same statement.
    """
    seen_fragments = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant):
                    seen_fragments.add(id(value))
            text = _joined_str_text(node)
            if len(text) >= 20 and SQL_SHAPED.search(text):
                yield node.lineno, text

    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in seen_fragments):
            if len(node.value) >= 20 and SQL_SHAPED.search(node.value):
                yield node.lineno, node.value


def _normalise(sql: str) -> str:
    """Strip SQL comments so a table named in a comment is not read as used.

    A percent sign in a SQL comment once broke a statement in this codebase;
    a table name in one would break this graph the same quiet way.
    """
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return sql


def analyse_module(path: Path) -> dict:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}

    writes  = defaultdict(set)      # table -> {operations}
    reads   = set()
    joins   = []
    dynamic = []

    for lineno, raw in _sql_literals(tree):
        sql = _normalise(raw)
        for op, pattern in WRITE_PATTERNS:
            for m in pattern.finditer(sql):
                table = m.group(1).lower()
                writes[table].add(op)
                # An INSERT carrying ON CONFLICT ... DO UPDATE is an UPSERT,
                # and it matches none of the UPDATE patterns: there is no
                # `UPDATE <table>` statement anywhere in it.
                #
                # Without this, 25 of 42 tables were reported as
                # "insert-only (append)" -- including market.short_positions
                # and market.period_metrics, which plainly upsert. A mapping
                # document that tells a reader a table only ever appends,
                # when every run rewrites the same keys, is wrong about the
                # one property that decides whether history exists.
                if op == "insert" and ON_CONFLICT.search(sql):
                    writes[table].add(
                        "upsert" if ON_CONFLICT_DO_UPDATE.search(sql)
                        else "insert-or-ignore")
        for pattern in READ_PATTERNS:
            for m in pattern.finditer(sql):
                reads.add(m.group(1).lower())
        for m in JOIN_ON.finditer(sql):
            table, alias, cond = m.group(1).lower(), m.group(2), m.group(3)
            joins.append({"table": table, "alias": alias,
                          "on": " ".join(cond.split())[:400], "line": lineno})
        if DYNAMIC_TARGET.search(sql):
            dynamic.append({"line": lineno,
                            "excerpt": " ".join(sql.split())[:160]})

    # A table it writes is not also a source for the mapping document, even
    # though UPDATE ... FROM makes it appear on both sides.
    sources = sorted(reads - set(writes))

    return {
        "writes":  {t: sorted(ops) for t, ops in sorted(writes.items())},
        "reads":   sources,
        "joins":   joins,
        "dynamic": dynamic,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--print", action="store_true", dest="show")
    args = ap.parse_args()

    files = sorted({p for tree in SOURCE_TREES if tree.exists()
                    for p in tree.rglob("*.py")
                    if not EXCLUDED_DIRS & set(p.parts)})
    if not files:
        print(f"2  no modules found under {[str(t) for t in SOURCE_TREES]} — "
              f"the lineage graph would be empty, and an empty graph reads "
              f"exactly like a pipeline with no dependencies")
        return 2

    modules, errors = {}, []
    for path in files:
        result = analyse_module(path)
        if "error" in result:
            errors.append({"module": str(path.relative_to(BACKEND)),
                           "error": result["error"]})
            continue
        if not result["writes"] and not result["reads"]:
            continue                      # touches no table; not a pipeline step
        modules[str(path.relative_to(BACKEND)).replace("\\", "/")] = result

    # Invert: target table -> who writes it. This is the column the mapping
    # documents need, and the direction the run sheet's edges point.
    # Two passes, deliberately. Classification depends on the writers, so it
    # cannot happen while they are still being collected: the old single pass
    # classified a table from the FIRST module that wrote it and never
    # revisited the answer when a second writer appeared.
    by_table = defaultdict(lambda: {"written_by": [], "layer": None})
    for module, result in modules.items():
        for table, ops in result["writes"].items():
            by_table[table]["written_by"].append({"module": module,
                                                  "operations": ops})

    for table, info in by_table.items():
        info.update(classify(table, [w["module"] for w in info["written_by"]]))

    unwritten = sorted({t for m in modules.values() for t in m["reads"]}
                       - set(by_table))

    conflicts = {t: i["layer_conflict"] for t, i in sorted(by_table.items())
                 if i.get("layer_conflict")}

    graph = {
        "modules_scanned": len(files),
        "modules_touching_tables": len(modules),
        "tables_written": len(by_table),
        # Carried in the artifact, not only printed. A consumer reading this
        # file must be able to see that a layer is disputed without having
        # watched the run that produced it.
        "layer_conflicts": conflicts,
        "by_table": {k: by_table[k] for k in sorted(by_table)},
        "by_module": modules,
        "read_but_never_written": unwritten,
        "parse_errors": errors,
    }

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        print(f"lineage written: {out}")

    print(f"modules scanned      {len(files)}")
    print(f"modules touching DB  {len(modules)}")
    print(f"tables written       {len(by_table)}")
    dyn = sum(len(m["dynamic"]) for m in modules.values())
    print(f"dynamic targets      {dyn}  (target not a literal: listed, not guessed)")
    if errors:
        print(f"parse errors         {len(errors)}")
        for e in errors[:5]:
            print(f"    {e['module']}: {e['error']}")

    # Printed every run, including clean ones, so "every table is placed" and
    # "nobody looked" never render the same way.
    print(f"unclassified tables  {len(conflicts)}"
          + ("" if conflicts else "  (every table is declared)"))
    for table, why in conflicts.items():
        print(f"    {table}: {why}")

    if args.show:
        per_layer = defaultdict(list)
        for table, info in sorted(by_table.items()):
            per_layer[info["layer"]].append((table, info["written_by"]))
        for layer in ("Bronze", "Silver", "Gold", "Universe", "out-of-scope"):
            rows = per_layer.get(layer, [])
            if not rows:
                continue
            print(f"\n== {layer}  ({len(rows)} tables) " + "=" * 30)
            for table, writers in rows:
                names = ", ".join(Path(w["module"]).name for w in writers)
                print(f"  {table:40} <- {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
