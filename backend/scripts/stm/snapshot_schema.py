"""
What the database actually holds, as a dated artifact
=====================================================
The source-to-target mapping documents describe columns: their type, their
nullability, which ones are keys, what values a CHECK constraint admits. Every
one of those facts has to come from somewhere, and there are two candidates.

The migrations are the obvious one and the wrong one. ``013_staging_schema.sql``
creates ``staging.eod_prices``; the code reads ``staging_au.eod_prices``, and
only migration 053 reconciles them by renaming the schema. Reading the DDL text
tells you about a schema that existed for forty migrations and does not exist
now. An ordered replay would get the right answer, but a replay is a
derivation, and a derivation can disagree with the system it claims to describe
without anybody finding out.

So the mapping documents are built from this: a snapshot of
``information_schema`` and the catalogs, taken from a real database, carrying
the host, the database name and the timestamp it was taken at. A mapping row
then cites evidence rather than inference, and a snapshot that no longer
matches production is a detectable condition rather than a silent lie.

Side effects: none
------------------
Catalog reads only. No temp tables, no ANALYZE, no row counts -- a COUNT(*)
over market.daily_prices is 6.4 million rows and this must never be the reason
production slows down. Row counts come from ``pg_class.reltuples``, which is
the planner's existing estimate and costs nothing. They are labelled as
estimates wherever they appear.

Usage:
    cd backend && ../asx-venv/bin/python scripts/stm/snapshot_schema.py \
        --out ../database/stm/schema_snapshot.json

    ... --schemas market,financials,staging_au,screener   restrict the scope

Exit codes:  0 snapshot written
             2 could not run (no DB, no schemas matched) -- never silent
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Where the checkout is, when this file is still inside one. It is run from
#: /tmp on the server -- deliberately, so the production checkout never has to
#: move -- and there parents[2] does not exist. Computing it unguarded raised
#: IndexError at import, before argparse could offer the --env-file that
#: exists precisely for that case: the fallback has to be in the line that
#: runs first, not only in the flag that handles the consequence.
_HERE = Path(__file__).resolve()
BACKEND = _HERE.parents[2] if len(_HERE.parents) > 2 else _HERE.parent
if (BACKEND / "app").is_dir():
    sys.path.insert(0, str(BACKEND))

#: The layers the mapping documents describe. Schemas outside this set exist
#: (users, ai, meta, support, strategy) and are deliberately not part of the
#: Bronze -> Silver -> Gold -> Universe lineage.
DEFAULT_SCHEMAS = ("staging_au", "financials", "market", "screener")

SNAPSHOT_VERSION = 1


def _dsn(env_file: str | None = None) -> str:
    """A psycopg2 DSN resolved at the execution boundary.

    Reads the project's .env directly rather than depending on the caller's
    shell: three jobs once died in 1ms because DATABASE_URL arrived only via
    another module's import-time load_dotenv.

    ``--env-file`` exists because this script is deliberately run from outside
    the checkout. Switching the production checkout to a feature branch to
    make a path resolve would put unreleased code where systemd and every cron
    job will load it; copying the one file out and pointing it at the .env is
    the version that changes nothing.
    """
    candidates = ([Path(env_file)] if env_file
                  else [BACKEND / ".env", BACKEND.parent / ".env"])
    if env_file and not Path(env_file).exists():
        raise RuntimeError(f"--env-file {env_file} does not exist")
    for candidate in candidates:
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))

    url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "neither DATABASE_URL_SYNC nor DATABASE_URL is set, and there is "
            "no built-in default: the credential must not live in source code")
    return (url.replace("postgresql+asyncpg://", "postgresql://", 1)
               .replace("postgresql+psycopg2://", "postgresql://", 1))


# ── Catalog queries ──────────────────────────────────────────────────────────
# Each is a single statement over the catalogs. No joins against user tables.

COLUMNS_SQL = """
SELECT c.table_schema,
       c.table_name,
       c.column_name,
       c.ordinal_position,
       c.data_type,
       c.udt_name,
       c.character_maximum_length,
       c.numeric_precision,
       c.numeric_scale,
       c.datetime_precision,
       c.is_nullable = 'YES'                        AS is_nullable,
       c.column_default,
       c.is_generated <> 'NEVER'                    AS is_generated,
       c.generation_expression,
       col_description(fc.oid, c.ordinal_position)  AS column_comment
  FROM information_schema.columns c
  JOIN pg_class     fc ON fc.relname = c.table_name
  JOIN pg_namespace fn ON fn.oid = fc.relnamespace
                      AND fn.nspname = c.table_schema
 WHERE c.table_schema = ANY(%s)
 ORDER BY c.table_schema, c.table_name, c.ordinal_position
"""

#: Constraints, with the constraint body rendered by Postgres itself.
#: pg_get_constraintdef is the authority on what a CHECK admits -- reproducing
#: it from catalog columns would be a second implementation of the same rule.
CONSTRAINTS_SQL = """
SELECT n.nspname                                    AS table_schema,
       t.relname                                    AS table_name,
       con.conname                                  AS constraint_name,
       con.contype                                  AS constraint_type,
       pg_get_constraintdef(con.oid)                AS definition,
       ARRAY(SELECT a.attname
               FROM unnest(con.conkey) k
               JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k)
                                                    AS columns,
       CASE WHEN con.confrelid <> 0
            THEN fn.nspname || '.' || ft.relname END AS references_table,
       ARRAY(SELECT a.attname
               FROM unnest(con.confkey) k
               JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k)
                                                    AS references_columns
  FROM pg_constraint con
  JOIN pg_class      t  ON t.oid = con.conrelid
  JOIN pg_namespace  n  ON n.oid = t.relnamespace
  LEFT JOIN pg_class     ft ON ft.oid = con.confrelid
  LEFT JOIN pg_namespace fn ON fn.oid = ft.relnamespace
 WHERE n.nspname = ANY(%s)
 ORDER BY 1, 2, 3
"""

#: Unique indexes that are not backed by a constraint still express a business
#: key. A mapping document that reported only pg_constraint would call those
#: columns non-key.
INDEXES_SQL = """
SELECT n.nspname        AS table_schema,
       t.relname        AS table_name,
       i.relname        AS index_name,
       ix.indisunique   AS is_unique,
       ix.indisprimary  AS is_primary,
       pg_get_indexdef(i.oid) AS definition
  FROM pg_index ix
  JOIN pg_class     i ON i.oid = ix.indexrelid
  JOIN pg_class     t ON t.oid = ix.indrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace
 WHERE n.nspname = ANY(%s)
 ORDER BY 1, 2, 3
"""

#: reltuples is the planner's estimate and costs nothing. relkind filters out
#: TimescaleDB chunks, which would otherwise swamp the inventory: the gate
#: clone reports 5,800 tables, almost all of them chunks of daily_prices.
TABLES_SQL = """
SELECT n.nspname                        AS table_schema,
       t.relname                        AS table_name,
       t.relkind                        AS kind,
       t.reltuples::bigint              AS estimated_rows,
       obj_description(t.oid, 'pg_class') AS table_comment
  FROM pg_class t
  JOIN pg_namespace n ON n.oid = t.relnamespace
 WHERE n.nspname = ANY(%s)
   AND t.relkind IN ('r', 'p', 'v', 'm')
   AND t.relispartition IS NOT TRUE
   AND t.relname NOT LIKE '\\_hyper\\_%%'
   AND t.relname NOT LIKE '\\_compressed\\_hyper\\_%%'
 ORDER BY 1, 2
"""


#: Field order for the compact column encoding. The reader reconstructs the
#: full records from this, so the two must not drift: it is written once here
#: and carried INSIDE the artifact, rather than duplicated in the reader.
COMPACT_COLUMN_FIELDS = [
    "column_name", "ordinal_position", "data_type", "udt_name",
    "character_maximum_length", "numeric_precision", "numeric_scale",
    "is_nullable", "column_default", "is_generated", "generation_expression",
    "datetime_precision", "column_comment",
]


def _compact(snapshot: dict) -> dict:
    """The same facts, columnar, with empty trailing fields dropped.

    Lossless with respect to everything the mapping documents consume. It
    exists because the only route off a browser-console host is a paste, and
    a 1.2MB artifact is not pasteable. The field order travels with the
    payload so a reader can never decode it against a different schema than
    the writer used -- the failure that encoding would otherwise invite is
    silent column shifting, which produces a document that is wrong in every
    row while looking entirely normal.
    """
    grouped = {}
    for col in snapshot["columns"]:
        key = f"{col['table_schema']}.{col['table_name']}"
        row = [col.get(f) for f in COMPACT_COLUMN_FIELDS]
        while row and row[-1] in (None, ""):
            row.pop()
        grouped.setdefault(key, []).append(row)

    return {
        "compact": 1,
        "column_fields": COMPACT_COLUMN_FIELDS,
        "meta": {k: snapshot[k] for k in
                 ("snapshot_version", "taken_at_utc", "host", "database",
                  "server_version", "schemas_requested", "schemas_found",
                  "schemas_missing", "counts")},
        "tables": [[t["table_schema"], t["table_name"], t["kind"],
                    t["estimated_rows"], t.get("table_comment")]
                   for t in snapshot["tables"]],
        "columns": grouped,
        "constraints": [[c["table_schema"], c["table_name"],
                         c["constraint_name"], c["constraint_type"],
                         c["definition"], c.get("columns"),
                         c.get("references_table"), c.get("references_columns")]
                        for c in snapshot["constraints"]],
        "indexes": [[i["table_schema"], i["table_name"], i["index_name"],
                     i["is_unique"], i["is_primary"], i["definition"]]
                    for i in snapshot["indexes"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True,
                    help="path to write the snapshot JSON to")
    ap.add_argument("--schemas", default=",".join(DEFAULT_SCHEMAS),
                    help="comma-separated schemas to snapshot")
    ap.add_argument("--env-file",
                    help="path to the .env holding DATABASE_URL, for when this "
                         "script is run from outside the checkout")
    ap.add_argument("--compact", action="store_true",
                    help="columnar encoding with empty fields dropped. Same "
                         "facts, roughly a fifth the bytes, for when the only "
                         "way off the host is a terminal paste")
    args = ap.parse_args()

    schemas = [s.strip() for s in args.schemas.split(",") if s.strip()]
    if not schemas:
        print("2  no schemas requested — this would snapshot nothing")
        return 2

    try:
        import psycopg2
        conn = psycopg2.connect(_dsn(args.env_file))
    except Exception as exc:                                   # noqa: BLE001
        print(f"2  cannot reach the database: {exc}")
        return 2

    def fetch(sql):
        with conn.cursor() as cur:
            cur.execute(sql, (schemas,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), version()")
            dbname, server_version = cur.fetchone()

        tables      = fetch(TABLES_SQL)
        columns     = fetch(COLUMNS_SQL)
        constraints = fetch(CONSTRAINTS_SQL)
        indexes     = fetch(INDEXES_SQL)
    finally:
        conn.close()

    if not columns:
        print(f"2  no columns found in {schemas} — the snapshot would describe "
              f"nothing, and an empty mapping document reads as a clean one")
        return 2

    found = sorted({t["table_schema"] for t in tables})
    missing = sorted(set(schemas) - set(found))

    snapshot = {
        "snapshot_version": SNAPSHOT_VERSION,
        "taken_at_utc":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host":             socket.gethostname(),
        "database":         dbname,
        "server_version":   server_version.split(" on ")[0],
        "schemas_requested": schemas,
        "schemas_found":     found,
        "schemas_missing":   missing,
        "counts": {"tables": len(tables), "columns": len(columns),
                   "constraints": len(constraints), "indexes": len(indexes)},
        "tables":      tables,
        "columns":     columns,
        "constraints": constraints,
        "indexes":     indexes,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.compact:
        out.write_text(json.dumps(_compact(snapshot), separators=(",", ":"),
                                  default=str), encoding="utf-8")
    else:
        out.write_text(json.dumps(snapshot, indent=2, default=str),
                       encoding="utf-8")

    print(f"snapshot written: {out}")
    print(f"  taken_at  {snapshot['taken_at_utc']}  on {snapshot['host']}")
    print(f"  database  {dbname}")
    print(f"  tables    {len(tables)}")
    print(f"  columns   {len(columns)}")
    print(f"  constraints {len(constraints)}   indexes {len(indexes)}")
    for schema in found:
        n = sum(1 for c in columns if c["table_schema"] == schema)
        t = sum(1 for x in tables if x["table_schema"] == schema)
        print(f"    {schema:14} {t:4} tables  {n:5} columns")
    if missing:
        # Not fatal, but never silent: a requested schema that does not exist
        # means the mapping document will be missing a layer entirely.
        print(f"  WARNING schemas requested but not present: {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
