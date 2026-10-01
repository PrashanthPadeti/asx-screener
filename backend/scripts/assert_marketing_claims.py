#!/usr/bin/env python3
"""
The site advertises floors; this proves the product still clears them.

frontend/lib/claims.ts declares what the website promises:

    UNIVERSE_FLOOR         2000    "screen 2,000+ ASX stocks"
    SCREENER_FIELDS_FLOOR   300    "300+ filterable fields"

Those are claims made to prospective customers. Nothing else in the system
knows they exist, so if the served universe fell to 1,800 the site would go on
advertising 2,000+ indefinitely and no check anywhere would fail.

This reads the floors out of the TypeScript (so the source of truth stays the
module the pages import, not a second copy here) and compares each against the
live value. A floor that no longer holds is an exit 1.

Read-only by construction: it opens one database connection, runs COUNT and
metadata queries, and writes nothing. Per the instrument-isolation rule, it
must not be able to alter what it measures.

    cd /opt/asx-screener/backend
    ../asx-venv/bin/python scripts/assert_marketing_claims.py

Exit codes:
    0  every advertised floor holds
    1  at least one claim is now overstated
    2  could not establish the facts (unreadable claims, DB unreachable)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CLAIMS_TS = BACKEND.parent / "frontend/lib/claims.ts"


def declared_floors() -> dict[str, int]:
    """Parse the floors out of claims.ts.

    Reading the TypeScript keeps one source of truth. Restating the numbers
    here would create exactly the duplication this whole change removes --
    the check would then verify its own copy and pass while the site drifted.
    """
    if not CLAIMS_TS.is_file():
        raise FileNotFoundError(f"{CLAIMS_TS} not found")
    src = CLAIMS_TS.read_text(encoding="utf-8")
    # Strip comments so a number quoted in the prose ("Live: 2,121") is never
    # read as a declaration. This repo has read prose as code repeatedly.
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)

    floors: dict[str, int] = {}
    for name, value in re.findall(
            r"export\s+const\s+([A-Z_]+)\s*=\s*(\d+)\b", src):
        floors[name] = int(value)
    return floors


def live_values() -> dict[str, int]:
    """Measure the product. One connection, read-only statements."""
    import psycopg2                                     # noqa: PLC0415

    dsn = os.environ.get("DATABASE_URL") or os.environ.get("ASX_DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")

    out: dict[str, int] = {}
    with psycopg2.connect(dsn) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM screener.universe "
                        "WHERE status = 'active' AND price IS NOT NULL")
            out["UNIVERSE_FLOOR"] = cur.fetchone()[0]

    # The filterable-field count is owned by the API, not the database: it is
    # len(ALLOWED_FIELDS), which is exactly what GET /api/v1/screener/fields
    # reports as total_fields, and so exactly what a customer can filter on.
    #
    # Read by AST rather than imported. Importing the route drags in the app's
    # database dependencies, and an instrument must not need the system it
    # measures to be healthy in order to report. This mirrors _literal() in
    # tests/test_screener_fields.py.
    out["SCREENER_FIELDS_FLOOR"] = len(_route_literal("ALLOWED_FIELDS"))
    return out


def _route_literal(name: str):
    import ast                                            # noqa: PLC0415
    route = BACKEND / "app/api/v1/routes/screener.py"
    tree = ast.parse(route.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else node.targets if isinstance(node, ast.Assign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {route}")


def main() -> int:
    try:
        floors = declared_floors()
    except Exception as exc:                                   # noqa: BLE001
        print(f"UNVERIFIED  cannot read declared claims: {exc}")
        return 2

    if not floors:
        print("UNVERIFIED  no floors declared in claims.ts -- "
              "either the module changed shape or the parser is wrong")
        return 2

    try:
        live = live_values()
    except Exception as exc:                                   # noqa: BLE001
        print(f"UNVERIFIED  cannot measure the product: "
              f"{type(exc).__name__}: {exc}")
        return 2

    width = max(len(k) for k in floors)
    failures = []
    for name, floor in sorted(floors.items()):
        actual = live.get(name)
        if actual is None:
            print(f"  {name:<{width}}  advertised {floor:>6}   NOT MEASURED")
            failures.append(f"{name}: no live value")
            continue
        ok = actual >= floor
        print(f"  {name:<{width}}  advertised {floor:>6}   "
              f"actual {actual:>6}   {'ok' if ok else 'OVERSTATED'}")
        if not ok:
            failures.append(
                f"{name}: site advertises {floor}, product has {actual}")

    if failures:
        print("\nFAIL  the website is advertising more than the product "
              "delivers:")
        for f in failures:
            print(f"    {f}")
        print("\nLower the floor in frontend/lib/claims.ts, or restore the "
              "product. Do not leave the claim standing.")
        return 1

    print("\nPASS  every advertised floor holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
