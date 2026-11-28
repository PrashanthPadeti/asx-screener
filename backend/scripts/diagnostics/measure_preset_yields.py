#!/usr/bin/env python
"""
How many stocks does each preset screen actually return?
========================================================
`assert_presets_satisfiable.py` answers a narrower question than it looks:
it finds columns that are empty for the whole population and flags presets
filtering on them. "Satisfiable" there means *no criterion sits on an empty
column*. It does not mean the screen returns a row -- a preset can clear that
check and still match nothing because its thresholds are strict.

That distinction matters for the 27 November 2026 removal of the Piotroski
filter from nine Pro/Premium presets. The satisfiability check going from
"10 cannot return a row" to "all satisfiable" establishes that no paid screen
is blocked by an empty column any more. It does NOT establish that those nine
now show a customer anything. This measures that directly.

WHY IT USES THE PRODUCT'S OWN QUERY BUILDER

`build_screener_sql` is the function the route calls. Re-deriving the SQL here
-- mapping fields to columns, applying each operator, honouring the registry's
`scale` -- would produce a second implementation of the product's semantics,
and a count from a second implementation that disagrees with the first tells
you nothing about which is right. Every comparator bug in this project's
recent history has had that shape. So the preset's filter list is handed to
the real builder and only its COUNT query is executed.

READ-ONLY: the COUNT query only, inside a transaction that is rolled back.
The DATA query is never run -- row bodies are not needed to count rows, and an
instrument must not consume the resources of the system it observes.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

ROUTE = BACKEND / "app/api/v1/routes/screener.py"


def _dsn() -> str:
    """Resolved at the execution boundary, like the satisfiability check.

    Reads the project's .env rather than trusting the caller's shell: three
    jobs once died in 1ms because DATABASE_URL arrived only via another
    module's import-time load_dotenv.
    """
    for candidate in (BACKEND / ".env", BACKEND.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    url = (os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL", ""))
    if not url:
        raise RuntimeError("neither DATABASE_URL_SYNC nor DATABASE_URL is set")
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            url = "postgresql://" + url[len(prefix):]
    return url


def _presets() -> list:
    tree = ast.parse(ROUTE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.AsyncFunctionDef)
                and node.name == "get_screener_presets"):
            for ret in ast.walk(node):
                if isinstance(ret, ast.Return):
                    return ast.literal_eval(ret.value).get("presets", [])
    raise SystemExit("get_screener_presets no longer returns a literal")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="comma-separated preset ids")
    ap.add_argument("--paid-only", action="store_true",
                    help="only presets whose min_plan is not free")
    args = ap.parse_args()

    import psycopg2
    from app.api.v1.routes.screener import build_screener_sql
    from app.schemas.screener import ScreenerRequest

    presets = _presets()
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        presets = [p for p in presets if p.get("id") in wanted]
    if args.paid_only:
        presets = [p for p in presets
                   if (p.get("min_plan") or "free") != "free"]
    if not presets:
        print("2  no presets selected — measuring nothing")
        return 2

    from compute.engine.screen_sql import resolve_run_scope

    conn = psycopg2.connect(_dsn())
    try:
        cur = conn.cursor()

        # The builder refuses to compile a governed read without a validated
        # run scope, and it is right to: outside a known contract an absent
        # sidecar entry cannot be read as APPLICABLE. The scope is resolved
        # through the server's own service call rather than reconstructed
        # here, for the same reason the SQL is -- "validated" means a
        # supported model version, a completed recompute and a contract-key
        # check, and an instrument that approximates that measures a
        # population the product would not serve.
        scope = resolve_run_scope(cur)
        print(f"run scope: {scope}\n")

        print(f"{'min_plan':9} {'preset':30} {'rows':>6}  filters")
        print("-" * 78)
        empty = []
        for p in presets:
            req = ScreenerRequest(filters=p.get("filters", []),
                                  sort_by=p.get("sort_by") or "market_cap",
                                  sort_dir=p.get("sort_dir") or "desc")
            count_sql, _data_sql, params = build_screener_sql(req, scope=scope)
            cur.execute(count_sql, params)
            n = cur.fetchone()[0]
            plan = p.get("min_plan") or "free"
            nf = len(p.get("filters", []))
            flag = "   <-- EMPTY" if n == 0 else ""
            print(f"{plan:9} {p.get('id'):30} {n:6}  {nf}{flag}")
            if n == 0:
                empty.append((plan, p.get("id")))

        conn.rollback()
        print("\nread-only, rolled back")
        if empty:
            print(f"\n{len(empty)} preset(s) return no rows:")
            for plan, pid in empty:
                print(f"  [{plan}] {pid}")
        else:
            print("\nevery selected preset returns at least one row")
        # A paid screen showing nothing is the condition this exists to catch.
        return 1 if any(plan != "free" for plan, _ in empty) else 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
