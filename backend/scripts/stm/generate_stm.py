"""
The source-to-target mapping documents
======================================
Deliverable #1: for every column of every target table in the Bronze ->
Silver -> Gold -> Universe lineage, where the value comes from and what was
done to it on the way.

Every row has two halves, and they are not the same kind of claim.

STRUCTURE is evidence. Target table, target column, data type, precision,
nullability, key membership, the values a CHECK admits, the default, a
generated column's expression -- all of it read from a dated snapshot of a
real database (``snapshot_schema.py``), never from the migrations. The writer
job, the tables it reads and the join conditions it uses come from a static
parse of the code that runs (``extract_lineage.py``). Nobody types these, so
nobody can mistype them, and when the database changes the row changes with it.

DERIVATION is authored. "ROE is net profit after tax over average
shareholders' equity, and it is withheld for banks" is not extractable from
a column definition. That prose lives in a YAML sidecar under
``database/stm/mappings/``, keyed by ``schema.table.column``, written and
reviewed by a person, and joined in here. It survives regeneration because it
is not generated.

The coverage report is the point
--------------------------------
A mapping document's characteristic failure is not being wrong; it is being
incomplete in a way that looks complete. A column added last month has no row,
and a reader cannot tell the difference between "this column is undocumented"
and "this column does not exist".

So every run prints coverage per layer and per table, and ``--fail-on-unmapped``
exits non-zero when a target column has no authored derivation. The document
and the database are then checkable against each other rather than merely
adjacent.

Usage:
    cd backend && python scripts/stm/generate_stm.py \
        --snapshot ../database/stm/schema_snapshot.json \
        --lineage  ../database/stm/lineage.json \
        --mappings ../database/stm/mappings \
        --out-dir  ../database/stm

    ... --layer bronze_to_silver     one layer only
    ... --fail-on-unmapped           CI gate: unmapped target column fails

Exit codes:  0 written (and, with --fail-on-unmapped, fully mapped)
             1 unmapped target columns, with --fail-on-unmapped
             2 could not run -- missing snapshot or lineage, never silent
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

#: The layers, and which target tables belong to each. Targets come from the
#: lineage graph's own classification so the two documents cannot disagree
#: about what Silver means.
LAYERS = {
    "bronze_to_silver": ("Bronze", "Silver"),
    "silver_to_gold":   ("Silver", "Gold"),
    "gold_to_universe": (("Silver", "Gold"), "Universe"),
}

STM_COLUMNS = [
    # Identity
    "layer", "target_table", "target_column", "ordinal",
    # Source
    "source_system", "source_table", "source_column", "source_filter",
    # Structure — evidence, from the snapshot
    "data_type", "length_precision", "is_key", "is_nullable",
    "valid_values", "default_value", "generated_expression",
    # Semantics — authored, from the sidecar
    "transformation_rule", "business_rule", "derivation_formula",
    "tables_involved", "join_condition", "grain", "unit",
    # Process
    "writer_job", "load_strategy", "exposed_as", "applicability",
    # Provenance
    "column_comment", "status", "evidence",
]


# ── Snapshot helpers ─────────────────────────────────────────────────────────

def load_snapshot(path: Path) -> dict:
    """Read a snapshot in either encoding, returning the full form.

    A compact snapshot carries its own ``column_fields`` order, and the
    expansion uses THAT, never a copy held here. A reader with its own idea
    of the field order decodes a differently-ordered payload into a document
    where every row is wrong and nothing looks wrong -- precision read as
    scale, a comment read as a default.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not raw.get("compact"):
        return raw

    fields = raw.get("column_fields")
    if not fields:
        raise SystemExit(
            f"2  {path.name} is marked compact but carries no column_fields; "
            f"it cannot be decoded without guessing the field order, and a "
            f"wrong guess produces a document that is wrong in every row")

    columns = []
    for key, rows in raw["columns"].items():
        schema, _, table = key.partition(".")
        for row in rows:
            padded = list(row) + [None] * (len(fields) - len(row))
            record = dict(zip(fields, padded))
            record["table_schema"], record["table_name"] = schema, table
            columns.append(record)

    return {
        **raw["meta"],
        "columns": columns,
        "tables": [dict(zip(("table_schema", "table_name", "kind",
                             "estimated_rows", "table_comment"), t))
                   for t in raw["tables"]],
        "constraints": [dict(zip(("table_schema", "table_name",
                                  "constraint_name", "constraint_type",
                                  "definition", "columns", "references_table",
                                  "references_columns"), c))
                        for c in raw["constraints"]],
        "indexes": [dict(zip(("table_schema", "table_name", "index_name",
                              "is_unique", "is_primary", "definition"), i))
                    for i in raw["indexes"]],
    }


def merge_snapshots(paths: list) -> dict:
    """Several snapshots as one picture of the database.

    The schemas are large enough that they are taken in slices and carried
    across by hand. Merging them is only honest if the slices describe the
    same database at compatible times, so that is checked rather than
    assumed: two slices from different databases would produce a mapping
    document that is internally consistent and describes no real system.

    A table appearing in two slices keeps the first; the slices are disjoint
    by construction and an overlap is reported.
    """
    snaps = [load_snapshot(p) for p in paths]
    databases = {s.get("database") for s in snaps}
    if len(databases) > 1:
        raise SystemExit(
            f"2  snapshots come from different databases {sorted(databases)}; "
            f"merging them would describe a system that does not exist")

    merged = dict(snaps[0])
    seen_tables, overlaps = set(), []
    merged["tables"], merged["columns"] = [], []
    merged["constraints"], merged["indexes"] = [], []

    for snap in snaps:
        for t in snap["tables"]:
            fq = f"{t['table_schema']}.{t['table_name']}"
            if fq in seen_tables:
                overlaps.append(fq)
                continue
            seen_tables.add(fq)
            merged["tables"].append(t)
        for key in ("columns", "constraints", "indexes"):
            merged[key].extend(
                r for r in snap[key]
                if f"{r['table_schema']}.{r['table_name']}" not in
                   {o for o in overlaps})

    merged["taken_at_utc"] = " + ".join(sorted(s["taken_at_utc"] for s in snaps))
    merged["slices"] = [{"taken_at_utc": s["taken_at_utc"],
                         "schemas": s.get("schemas_requested"),
                         "tables": len(s["tables"])} for s in snaps]
    if overlaps:
        merged["overlapping_tables"] = sorted(set(overlaps))
    return merged


def index_snapshot(snap: dict) -> dict:
    """Reshape the snapshot into lookups keyed by schema.table[.column]."""
    tables, columns = {}, defaultdict(list)
    for t in snap["tables"]:
        tables[f"{t['table_schema']}.{t['table_name']}"] = t
    for c in snap["columns"]:
        columns[f"{c['table_schema']}.{c['table_name']}"].append(c)

    keys, checks, uniques = defaultdict(set), defaultdict(list), defaultdict(list)
    for con in snap["constraints"]:
        table = f"{con['table_schema']}.{con['table_name']}"
        cols = con.get("columns") or []
        if con["constraint_type"] == "p":
            keys[table].update(cols)
        elif con["constraint_type"] == "u":
            uniques[table].append(cols)
        elif con["constraint_type"] == "c":
            checks[table].append(con)

    # A unique INDEX with no backing constraint still expresses a business
    # key. Reporting only pg_constraint would call those columns non-key.
    for idx in snap.get("indexes", []):
        if not idx.get("is_unique") or idx.get("is_primary"):
            continue
        table = f"{idx['table_schema']}.{idx['table_name']}"
        inner = re.search(r"\(([^)]*)\)", idx.get("definition") or "")
        if inner:
            cols = [c.strip().split()[0].strip('"')
                    for c in inner.group(1).split(",")]
            uniques[table].append(cols)

    return {"tables": tables, "columns": columns, "keys": keys,
            "checks": checks, "uniques": uniques}


def key_role(table: str, column: str, idx: dict) -> str:
    if column in idx["keys"].get(table, ()):
        return "PK"
    for cols in idx["uniques"].get(table, ()):
        if column in cols:
            return "BK" if len(cols) > 1 else "UK"
    return ""


def valid_values(table: str, column: str, idx: dict) -> str:
    """What a CHECK on this column admits, as Postgres renders it.

    pg_get_constraintdef is the authority. Reproducing the rule from catalog
    columns would be a second implementation of it, free to disagree.
    """
    out = []
    for con in idx["checks"].get(table, ()):
        definition = con.get("definition") or ""
        if column in (con.get("columns") or []) or \
                re.search(rf"\b{re.escape(column)}\b", definition):
            out.append(definition.replace("CHECK ", "", 1).strip())
    return " AND ".join(out)


def precision(col: dict) -> str:
    if col.get("character_maximum_length"):
        return str(col["character_maximum_length"])
    if col.get("numeric_precision") is not None:
        scale = col.get("numeric_scale")
        return (f"{col['numeric_precision']},{scale}" if scale is not None
                else str(col["numeric_precision"]))
    return ""


# ── Sidecar ──────────────────────────────────────────────────────────────────

def load_mappings(folder: Path) -> dict:
    """Authored prose, keyed schema.table.column.

    Missing is a reportable state, not a default. A sidecar directory that
    does not exist yields nothing and the coverage report says so, rather
    than the generator inventing plausible-sounding derivations.
    """
    if not folder.exists():
        return {}
    try:
        import yaml
    except ImportError:
        print("WARNING pyyaml not installed — authored derivations cannot be "
              "read, and every row will report as unmapped. That is the "
              "correct output for this state, but it is not the document.",
              file=sys.stderr)
        return {}

    merged, seen = {}, {}
    for path in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        # A file-level `defaults:` block applies to every column in the file,
        # and a column's own value wins. Without this the block would sit in
        # the document looking authoritative while changing nothing -- which
        # is the same defect as a declared entitlement nothing enforces.
        defaults = dict(doc.get("defaults") or {})

        for table, cols in (doc.get("columns") or {}).items():
            for column, body in (cols or {}).items():
                fq = f"{table}.{column}"
                if fq in seen:
                    # Two files claiming the same column is a contradiction,
                    # not a merge: last-write-wins would hide the conflict.
                    raise SystemExit(
                        f"2  {fq} is mapped in both {seen[fq]} and "
                        f"{path.name}; one column, one authored derivation")
                seen[fq] = path.name
                row = {**defaults, **(body or {})}

                # An authored key with no output column is prose that will
                # never reach the document. Silently dropping it means
                # somebody writes a business rule, reviews it, commits it,
                # and it is nowhere in the deliverable.
                stray = sorted(set(row) - set(STM_COLUMNS) - {"_source_file"})
                if stray:
                    raise SystemExit(
                        f"2  {path.name}: {fq} sets {stray}, which is not a "
                        f"mapping-document column. Add it to STM_COLUMNS or "
                        f"correct the key — authored prose that lands nowhere "
                        f"is worse than absent, because it reads as done.")

                merged[fq] = row
                merged[fq]["_source_file"] = path.name
    return merged


# ── Lineage helpers ──────────────────────────────────────────────────────────

def writers_of(lineage: dict, table: str) -> list:
    info = lineage.get("by_table", {}).get(table)
    return [w["module"] for w in info["written_by"]] if info else []


def load_strategy_of(lineage: dict, table: str) -> str:
    """TRUNCATE+INSERT, UPSERT, UPDATE-in-place -- read off the operations."""
    info = lineage.get("by_table", {}).get(table)
    if not info:
        return ""
    ops = {op for w in info["written_by"] for op in w["operations"]}

    # The UNION of operations across every writer, which is not the same as
    # the strategy any single run uses. financials.annual_pnl upserts on the
    # daily path and TRUNCATEs only under --full; reporting just "full reload"
    # would describe a mode that runs rarely as though it were the normal one.
    if "truncate" in ops and ("update" in ops or "insert" in ops):
        both = "upsert" if "update" in ops else "insert"
        return f"{both} on the incremental path; TRUNCATE + INSERT on a full run"
    if "truncate" in ops and "insert" in ops:
        return "full reload (TRUNCATE + INSERT)"
    if "delete" in ops and "insert" in ops:
        return "delete-and-insert (windowed replace)"
    if "insert" in ops and "update" in ops:
        return "upsert (INSERT + UPDATE)"
    if ops == {"update"}:
        return "update-in-place (enriches rows another job inserted)"
    if "insert" in ops:
        return "insert-only (append)"
    return ", ".join(sorted(ops))


def joins_for(lineage: dict, modules: list) -> str:
    seen, out = set(), []
    for module in modules:
        for j in lineage.get("by_module", {}).get(module, {}).get("joins", []):
            text = f"{j['table']}: {j['on']}"
            if text not in seen:
                seen.add(text)
                out.append(text)
    return " | ".join(out[:6])


def sources_for(lineage: dict, modules: list) -> list:
    seen = []
    for module in modules:
        for table in lineage.get("by_module", {}).get(module, {}).get("reads", []):
            if table not in seen:
                seen.append(table)
    return seen


# ── Build ────────────────────────────────────────────────────────────────────

def build_layer(layer: str, snap_idx: dict, lineage: dict, mappings: dict,
                exposed: dict, evidence: str) -> list:
    source_layers, target_layer = LAYERS[layer]
    if isinstance(source_layers, str):
        source_layers = (source_layers,)

    targets = sorted(t for t, info in lineage.get("by_table", {}).items()
                     if info.get("layer") == target_layer)

    rows = []
    for table in targets:
        cols = snap_idx["columns"].get(table)
        if not cols:
            # In the lineage but not in the database: a real contradiction
            # between the code and the system, surfaced as a row rather than
            # dropped. A silently missing table is how a layer goes missing.
            rows.append({c: "" for c in STM_COLUMNS} | {
                "layer": layer, "target_table": table,
                "target_column": "(whole table)",
                "status": "ABSENT FROM SNAPSHOT — code writes it, the "
                          "database does not have it",
                "writer_job": "; ".join(Path(m).name
                                        for m in writers_of(lineage, table)),
                "evidence": evidence})
            continue

        modules  = writers_of(lineage, table)
        strategy = load_strategy_of(lineage, table)
        srcs     = [s for s in sources_for(lineage, modules)
                    if lineage.get("by_table", {}).get(s, {}).get("layer")
                    in source_layers]
        join_txt = joins_for(lineage, modules)

        for col in cols:
            name = col["column_name"]
            fq   = f"{table}.{name}"
            authored = mappings.get(fq, {})

            rows.append({
                "layer":          layer,
                "target_table":   table,
                "target_column":  name,
                "ordinal":        col["ordinal_position"],
                "source_system":  authored.get("source_system",
                                               "EODHD" if target_layer == "Bronze" else ""),
                "source_table":   authored.get("source_table",
                                               "; ".join(srcs[:4])),
                "source_column":  authored.get("source_column", ""),
                "data_type":      col["udt_name"],
                "length_precision": precision(col),
                "is_key":         key_role(table, name, snap_idx),
                "is_nullable":    "Y" if col["is_nullable"] else "N",
                "valid_values":   authored.get("valid_values",
                                               valid_values(table, name, snap_idx)),
                "default_value":  col.get("column_default") or "",
                "generated_expression": col.get("generation_expression") or "",
                "transformation_rule": authored.get("transformation_rule", ""),
                "business_rule":  authored.get("business_rule", ""),
                "derivation_formula": authored.get("derivation_formula", ""),
                "tables_involved": authored.get("tables_involved",
                                                "; ".join(srcs[:6])),
                "join_condition": authored.get("join_condition", join_txt),
                "grain":          authored.get("grain", ""),
                "unit":           authored.get("unit", ""),
                "writer_job":     authored.get("writer_job",
                                               "; ".join(Path(m).name for m in modules)),
                "load_strategy":  strategy,
                "exposed_as":     exposed.get(f"{table}.{name}", ""),
                "applicability":  authored.get("applicability", ""),
                "column_comment": col.get("column_comment") or "",
                "status":         "mapped" if authored else "UNMAPPED",
                "evidence":       evidence,
            })
    return rows


def exposed_fields() -> dict:
    """screener.universe column -> the API field name a customer screens on.

    Read from ALLOWED_FIELDS so the mapping document can say which of the 542
    screener columns a customer can actually reach.
    """
    import ast
    route = BACKEND / "app/api/v1/routes/screener.py"
    if not route.exists():
        return {}
    tree = ast.parse(route.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "ALLOWED_FIELDS":
                registry = ast.literal_eval(node.value)
                out = {}
                for field, spec in registry.items():
                    col = (spec or {}).get("col")
                    if isinstance(col, str):
                        out[f"screener.universe.{col.split('.')[-1]}"] = field
                return out
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    root = BACKEND.parent / "database/stm"
    ap.add_argument("--snapshot", action="append",
                    help="schema snapshot JSON; repeatable, and the slices "
                         "are merged after checking they describe the same "
                         "database")
    ap.add_argument("--lineage",  default=str(root / "lineage.json"))
    ap.add_argument("--mappings", default=str(root / "mappings"))
    ap.add_argument("--out-dir",  default=str(root))
    ap.add_argument("--layer", choices=sorted(LAYERS), action="append")
    ap.add_argument("--fail-on-unmapped", action="store_true")
    args = ap.parse_args()

    snap_paths = [Path(p) for p in (args.snapshot or
                                    [str(root / "schema_snapshot.json")])]
    lin_path = Path(args.lineage)
    for path, what, how in ([(p, "schema snapshot", "snapshot_schema.py")
                             for p in snap_paths]
                            + [(lin_path, "lineage graph", "extract_lineage.py")]):
        if not path.exists():
            print(f"2  {what} not found at {path}; run {how} first. Building "
                  f"the mapping without it would mean inventing the half that "
                  f"is supposed to be evidence")
            return 2

    snap    = merge_snapshots(snap_paths)
    lineage = json.loads(lin_path.read_text(encoding="utf-8"))
    snap_idx = index_snapshot(snap)
    mappings = load_mappings(Path(args.mappings))
    exposed  = exposed_fields()

    evidence = (f"snapshot {snap['taken_at_utc']} "
                f"{snap['database']}@{snap['host']}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    layers = args.layer or sorted(LAYERS)

    total, unmapped_total = 0, 0
    print(f"evidence: {evidence}")
    print(f"authored derivations loaded: {len(mappings)}")
    print()

    for layer in layers:
        rows = build_layer(layer, snap_idx, lineage, mappings, exposed, evidence)
        path = out_dir / f"stm_{layer}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=STM_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        unmapped = [r for r in rows if r["status"] != "mapped"]
        total += len(rows)
        unmapped_total += len(unmapped)
        pct = 100.0 * (len(rows) - len(unmapped)) / len(rows) if rows else 0.0
        print(f"{layer:18} {len(rows):5} rows   "
              f"{len(rows) - len(unmapped):5} mapped ({pct:5.1f}%)   "
              f"{len(unmapped):5} unmapped   -> {path.name}")

        by_table = defaultdict(lambda: [0, 0])
        for r in rows:
            by_table[r["target_table"]][0] += 1
            if r["status"] == "mapped":
                by_table[r["target_table"]][1] += 1
        for table in sorted(by_table):
            n, m = by_table[table]
            flag = "" if m == n else ("  <- nothing mapped" if m == 0 else "")
            print(f"    {table:42} {m:4}/{n:<4}{flag}")
        print()

    done = total - unmapped_total
    print(f"TOTAL {done}/{total} target columns carry an authored derivation "
          f"({100.0 * done / total if total else 0:.1f}%)")

    if args.fail_on_unmapped and unmapped_total:
        print(f"\n1  {unmapped_total} target column(s) have no authored "
              f"derivation. A mapping document that is silently incomplete "
              f"reads exactly like a complete one.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
