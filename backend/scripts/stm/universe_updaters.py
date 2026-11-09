"""Which universe column does each UPDATE-in-place writer set?

The builder's INSERT covers 341 of 376 columns. The other 35 exist only
because a later job updates the row, so "who writes this column" is not
answerable from the INSERT alone -- and a column whose only writer is an
optional stage is NULL whenever that stage does not run.

Approach: for each module the lineage names as a writer of screener.universe,
find every `UPDATE screener.universe ... SET` in its string literals and
record the assigned column names. Reconciliation: every one of the 376 must
be claimed by the INSERT, by a module here, or be reported unclaimed.
"""
import ast
import json
import re
import sys
from pathlib import Path

EV = Path("database/stm/evidence")
EV.mkdir(parents=True, exist_ok=True)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else EV / "universe_updaters.json"
PAIRS = Path(sys.argv[2]) if len(sys.argv) > 2 else EV / "universe_pairs.json"

MODULES = [
    "backend/compute/engine/asx_indices.py",
    "backend/compute/engine/composite_score.py",
    "backend/compute/engine/dilution_metrics.py",
    "backend/compute/engine/metric_states.py",
    "backend/compute/engine/pros_cons.py",
    "backend/compute/engine/short_positions.py",
    "backend/compute/engine/universe_writer.py",
    "backend/scripts/eodhd/v2/build_screener_universe.py",
    "backend/scripts/eodhd/v2/jobs/incremental_daily.py",
]

UPDATE = re.compile(r"UPDATE\s+screener\.universe\b", re.I)


def literals(path):
    """Every string constant in the file, f-strings reassembled.

    A JoinedStr holds the SQL in fragments; joining only the Constant parts
    keeps the column names and drops the interpolations, which is what the
    column list needs.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append(" {?} ")
            out.append((node.lineno, "".join(parts)))
    return out


def set_columns(sql):
    """Column names assigned by the SET clause of an UPDATE statement."""
    m = re.search(r"\bSET\b(.*?)(?=\bWHERE\b|\bFROM\b|\bRETURNING\b|$)",
                  sql, re.I | re.S)
    if not m:
        return []
    body = re.sub(r"--[^\n]*", "", m.group(1))
    cols, depth, token = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            cols.append(token)
            token = ""
            continue
        token += ch
    cols.append(token)
    names = []
    for c in cols:
        mm = re.match(r"\s*([a-z_][a-z0-9_]*)\s*=", c)
        if mm:
            names.append(mm.group(1))
    return names


by_module, statements = {}, 0
for rel in MODULES:
    path = Path(rel)
    if not path.exists():
        raise SystemExit(f"2  {rel} not found")
    found = {}
    for lineno, text in literals(path):
        if not UPDATE.search(text):
            continue
        statements += 1
        for col in set_columns(text):
            found.setdefault(col, []).append(lineno)
    if found:
        by_module[rel] = {k: sorted(set(v)) for k, v in sorted(found.items())}

pairs = json.loads(PAIRS.read_text(encoding="utf-8"))
inserted = {c["column"] for c in pairs["columns"]}
updated = {c for cols in by_module.values() for c in cols}

OUT.write_text(json.dumps({
    "update_statements_found": statements,
    "inserted": sorted(inserted),
    "by_module": by_module,
    "updated_only": sorted(updated - inserted),
}, indent=1), encoding="utf-8")

print(f"{statements} UPDATE screener.universe statements across "
      f"{len(by_module)} modules")
print(f"inserted {len(inserted)}  updated {len(updated)}  "
      f"update-only {len(updated - inserted)}")
for rel, cols in by_module.items():
    print(f"  {Path(rel).name:30} {len(cols):4} columns")
