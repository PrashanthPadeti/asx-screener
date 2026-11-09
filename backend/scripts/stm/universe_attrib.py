"""Per-column writer attribution for all 376 screener.universe columns.

Three independent extractions are reconciled here, and the reconciliation is
the point: a column every extraction misses is a column nothing writes, and
that is not visible from any one of them.

  builder INSERT      341  position-paired with its SELECT expression
  builder DO UPDATE    342 refreshed on conflict (asx_code excluded)
  engine UPDATEs        25 update-only, from string literals, 6 modules
  canonical writer      80 governed columns, from the registry at runtime

Precedence, which is ordering not opinion: the builder inserts or refreshes
the row, the engine updaters overwrite their own columns, and the canonical
writer last -- so for a governed column the canonical writer's value is what
a customer reads, and the builder's is provisional.
"""
import json
import sys
from pathlib import Path

EV = Path("database/stm/evidence")
EV.mkdir(parents=True, exist_ok=True)
SP = Path(sys.argv[1]) if len(sys.argv) > 1 else EV
ROOT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")

pairs = json.loads((SP / "universe_pairs.json").read_text(encoding="utf-8"))
upd = json.loads((SP / "universe_updaters.json").read_text(encoding="utf-8"))
# The governed registry is resolved here rather than read from a file:
# a hand-made intermediate is a second declaration of what is governed,
# free to go stale against the registry it claims to describe.
sys.path.insert(0, "backend")
from compute.engine.metric_states import LATEST_MODEL_VERSION   # noqa: E402
from compute.engine.universe_writer import persisted_governed    # noqa: E402

gov = {"version": LATEST_MODEL_VERSION,
       "mapping": persisted_governed(LATEST_MODEL_VERSION)}
snap = json.loads((ROOT / "database/stm/snap_universe.json").read_text(encoding="utf-8"))

cols = snap["columns"]["screener.universe"]
expr = {c["column"]: c["expr"] for c in pairs["columns"]}
refreshed = set(pairs["do_update_set"])
governed_cols = set(gov["mapping"].values())
by_col_module = {}
for mod, cmap in upd["by_module"].items():
    for col, lines in cmap.items():
        by_col_module.setdefault(col, []).append(
            {"module": mod, "lines": lines})

out = []
for row in cols:
    name, ordinal = row[0], row[1]
    writers = []
    if name in expr:
        writers.append("build_screener_universe.py (INSERT)")
    for w in by_col_module.get(name, []):
        writers.append(f"{Path(w['module']).name} (UPDATE @{w['lines'][0]})")
    if name in governed_cols:
        writers.append("universe_writer.py (canonical UPDATE, governed)")
    out.append({
        "ordinal": ordinal,
        "column": name,
        "insert_expr": expr.get(name),
        "refreshed_on_conflict": name in refreshed,
        "governed": name in governed_cols,
        "writers": writers,
        "unclaimed": not writers,
    })

unclaimed = [r["column"] for r in out if r["unclaimed"]]
(SP / "universe_attrib.json").write_text(
    json.dumps({"columns": out, "unclaimed": unclaimed}, indent=1),
    encoding="utf-8")

print(f"{len(out)} columns attributed")
print(f"  INSERT only            "
      f"{sum(1 for r in out if r['insert_expr'] and len(r['writers']) == 1)}")
print(f"  INSERT + canonical     "
      f"{sum(1 for r in out if r['insert_expr'] and r['governed'])}")
print(f"  update-only            "
      f"{sum(1 for r in out if not r['insert_expr'] and r['writers'])}")
print(f"  governed               {sum(1 for r in out if r['governed'])}")
print(f"  UNCLAIMED              {len(unclaimed)}: {', '.join(unclaimed)}")
