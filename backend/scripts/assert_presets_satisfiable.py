"""
Every preset screen must be able to return a row
================================================
On 30 October 2026, ten of the thirty-one preset screens could not return a
result under any market conditions. They filtered on ``piotroski_f_score``,
which is computed for none of the 2,113 companies in the universe, or on
``beta_1y``, which is NULL for all of them.

    piotroski_strong          quality_undervalued       ai_top5
    mining_value              franking_optimiser        multi_factor_qm
    quality_elite_compounder  altman_safety_screen      low_beta_income_shield
    small_cap_hidden_gems

Each rendered "0 stocks matched" -- indistinguishable, to a paying customer,
from a screen that was merely strict. They had been empty since they shipped.

Why this is a SCRIPT and not a test
-----------------------------------
The property is about data, and the full-suite gate runs against a clone that
has the schema and a seeded compute run but no universe rows. Every column
would read as empty there, so a gate-time version of this check would either
fail on all 31 presets or be written loose enough to pass on anything -- and
the second is what usually happens. A guard whose population is absent
reports on nothing while printing PASS.

So this runs where the data is. The companion unit test
(test_preset_satisfiability.py) asserts the part that IS static: that every
preset names fields the registry actually knows.

Exit codes:  0 every preset is satisfiable
             1 at least one cannot return a row
             2 could not run (no DB, no presets) -- never silent success

Usage:
    cd backend && ../asx-venv/bin/python scripts/assert_presets_satisfiable.py
    ... --json   machine-readable, for a scheduled check
"""

import argparse
import ast
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

ROUTE = BACKEND / "app/api/v1/routes/screener.py"

#: The population a customer screens over. Must match DIAGNOSIS_POPULATION in
#: the route: a check run over a different population than the product uses
#: answers a question nobody asked.
POPULATION = "u.price IS NOT NULL AND u.status = 'active'"


def _literal(name: str):
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name:
                return ast.literal_eval(node.value)
    raise SystemExit(f"2  {name} not found in {ROUTE}")


def _presets() -> list:
    """Preset definitions, read from the route's own returned literal."""
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.AsyncFunctionDef)
                and node.name == "get_screener_presets"):
            continue
        for ret in ast.walk(node):
            if isinstance(ret, ast.Return):
                return ast.literal_eval(ret.value).get("presets", [])
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    presets = _presets()
    if not presets:
        print("2  no presets found — this check is guarding nothing")
        return 2

    allowed = _literal("ALLOWED_FIELDS")

    try:
        import psycopg2
        from app.core.db import get_database_url_sync
        conn = psycopg2.connect(get_database_url_sync())
    except Exception as exc:                                   # noqa: BLE001
        print(f"2  cannot reach the database: {exc}")
        return 2

    # Which referenced columns hold nothing for the whole population. One
    # query, no joins: an instrument must not consume the resources of the
    # system it observes.
    referenced = sorted({f["field"] for p in presets for f in p.get("filters", [])}
                        | {p["sort_by"] for p in presets if p.get("sort_by")})
    known = [f for f in referenced if f in allowed]
    unknown = [f for f in referenced if f not in allowed]

    cols = {f: allowed[f]["col"] for f in known}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), "
            + ", ".join(f"count({c})" for c in cols.values())
            + f" FROM screener.universe u WHERE {POPULATION}")
        row = cur.fetchone()
    population, counts = row[0], row[1:]
    if not population:
        print("2  the universe is empty — nothing can be judged satisfiable")
        return 2

    barren = {f for f, n in zip(cols, counts) if not n}

    broken = []
    for p in presets:
        used = {f["field"] for f in p.get("filters", [])}
        if p.get("sort_by"):
            used.add(p["sort_by"])
        offending = sorted(used & (barren | set(unknown)))
        if offending:
            broken.append({"id": p.get("id"), "name": p.get("name"),
                           "premium": bool(p.get("premium")),
                           "unsatisfiable_on": offending})

    if args.json:
        print(json.dumps({"population": population,
                          "presets": len(presets),
                          "empty_columns": sorted(barren),
                          "unknown_fields": unknown,
                          "broken": broken}, indent=2))
    else:
        print(f"population: {population} active companies")
        print(f"presets:    {len(presets)}")
        if barren:
            print(f"columns empty for the whole population: {sorted(barren)}")
        if unknown:
            print(f"fields unknown to ALLOWED_FIELDS:       {unknown}")
        if broken:
            print(f"\n{len(broken)} preset(s) cannot return a row:")
            for b in broken:
                tag = "PREMIUM" if b["premium"] else "free"
                print(f"  [{tag:7}] {b['id']:28} {b['unsatisfiable_on']}")
        else:
            print("\nall presets are satisfiable")

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
