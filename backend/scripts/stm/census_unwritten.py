#!/usr/bin/env python
"""
Which unwritten columns are dead, and which are frozen
=====================================================
A column absent from its producer's INSERT is one of two things: never
populated (dead schema, honest NULLs) or holding values from a retired code
path (frozen, and restamped as current by every later run). The mapping
documents must say which, and only the database knows.

WHY THIS IS A SCRIPT AND NOT A .sql FILE
----------------------------------------
It replaces three generated .sql files, one of which killed production.

On 9 November 2026 a census of market.daily_metrics ran seventeen
count(column) aggregates in a single statement. The table is a TimescaleDB
hypertable of several million rows on a 4 GB host; the backend reached
3.5 GB resident and the kernel OOM-killed PostgreSQL:

    Out of memory: Killed process 3218641 (postgres)
    total-vm:5287312kB  anon-rss:3532396kB

The earlier censuses were safe only because their tables were small --
market.yearly_metrics has 39,454 rows -- and the pattern was reused without
checking. This project already had the rule: an instrument must not consume
the resources of the system it observes. A .sql file sitting in the
repository is a loaded gun for whoever runs it next, so the files are gone
and the protections live in code.

WHY NOT A ROW-COUNT GUARD
-------------------------
The obvious guard -- refuse above N rows -- would have been BLIND here.
pg_class.reltuples is -1 for both market.daily_metrics and
market.computed_metrics, because a hypertable's parent relation holds no
rows and its data lives in chunks. The statistic says nothing for exactly
the tables that matter.

So the size check walks the inheritance tree (chunks included) and the
execution is bounded independently of it:

    * one column per statement, never N aggregates in one
    * statement_timeout, so a runaway scan is cancelled rather than allowed
      to accumulate
    * a size ceiling, refused by default and overridable only deliberately

Usage:
    python scripts/stm/census_unwritten.py --table market.yearly_metrics \\
        --columns peg_ratio,quick_ratio,croic
    python scripts/stm/census_unwritten.py --table market.foo --columns a,b \\
        --env-file /opt/asx-screener/backend/.env

Exit codes: 0 census taken · 2 refused or could not run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
BACKEND = _HERE.parents[2] if len(_HERE.parents) > 2 else _HERE.parent
if (BACKEND / "app").is_dir():
    sys.path.insert(0, str(BACKEND))

#: Total relation size, chunks included, above which a full-scan census is
#: refused. 2 GB against a 4 GB host leaves no room for the rest of the
#: system, and the census is never worth an outage: a mapping document that
#: says "population unmeasured" is accurate, while a dead database is not.
MAX_BYTES_DEFAULT = 2 * 1024 ** 3

#: Per-statement ceiling. A census is a diagnostic; if one column cannot be
#: counted in this long, the table is too big for this tool and the answer
#: belongs on a dump or a replica.
STATEMENT_TIMEOUT_MS = 30_000

IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

#: Size of a relation INCLUDING its inheritance children, which is what a
#: hypertable's data actually is. pg_total_relation_size on the parent alone
#: reports a few kilobytes for a table holding millions of rows.
SIZE_SQL = """
WITH RECURSIVE tree(oid) AS (
    SELECT %s::regclass::oid
    UNION ALL
    SELECT i.inhrelid FROM pg_inherits i JOIN tree t ON i.inhparent = t.oid
)
SELECT COALESCE(SUM(pg_total_relation_size(oid)), 0) FROM tree
"""


def _safe_ident(name: str, what: str) -> str:
    if not IDENT.match(name):
        raise SystemExit(f"2  refusing to build SQL from {what} {name!r}")
    return name


def _dsn(env_file: str | None) -> str:
    if env_file:
        path = Path(env_file)
        if not path.exists():
            raise SystemExit(f"2  --env-file {path} does not exist")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL_SYNC=") or line.startswith("DATABASE_URL="):
                key, _, value = line.partition("=")
                os.environ.setdefault(key, value.strip().strip("\"'"))
    from app.core.db import get_database_url_sync
    return get_database_url_sync()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True, help="schema.table")
    ap.add_argument("--columns", required=True,
                    help="comma-separated column names")
    ap.add_argument("--env-file",
                    help="path to the .env holding the credential, for when "
                         "this runs from outside the checkout")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES_DEFAULT)
    ap.add_argument("--force", action="store_true",
                    help="scan a table over the size ceiling anyway. Only "
                         "with a maintenance window: this is the flag whose "
                         "absence stops a repeat of the 9 Nov OOM.")
    args = ap.parse_args()

    if "." not in args.table:
        raise SystemExit("2  --table must be schema.table")
    schema, table = args.table.split(".", 1)
    _safe_ident(schema, "schema")
    _safe_ident(table, "table")
    columns = [_safe_ident(c.strip(), "column")
               for c in args.columns.split(",") if c.strip()]
    if not columns:
        raise SystemExit("2  no columns requested")

    try:
        import psycopg2
        conn = psycopg2.connect(_dsn(args.env_file))
    except Exception as exc:                                   # noqa: BLE001
        raise SystemExit(f"2  cannot reach the database: {exc}")

    try:
        with conn.cursor() as cur:
            cur.execute(SIZE_SQL, (args.table,))
            size = int(cur.fetchone()[0])

        gib = size / 1024 ** 3
        print(f"census: {args.table}  {gib:.2f} GiB including chunks")

        if size > args.max_bytes and not args.force:
            ceiling = args.max_bytes / 1024 ** 3
            print(f"\n2  REFUSED: {gib:.2f} GiB exceeds the {ceiling:.2f} GiB "
                  f"ceiling.\n"
                  f"   A full-scan census of this table is what OOM-killed "
                  f"PostgreSQL on 9 November 2026.\n"
                  f"   Take it on a dump or a replica, or pass --force "
                  f"inside a maintenance window.\n"
                  f"   A mapping that records 'population unmeasured' is "
                  f"accurate; an outage is not.")
            return 2

        print(f"census: {len(columns)} column(s), one statement each, "
              f"{STATEMENT_TIMEOUT_MS} ms timeout\n")
        results: list[tuple[str, int | None]] = []
        for col in columns:
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
                try:
                    # One column, one statement. Never N aggregates in one:
                    # that is the shape that went to 3.5 GB resident.
                    cur.execute(
                        f'SELECT count("{col}") FROM {schema}.{table}')
                    results.append((col, int(cur.fetchone()[0])))
                except Exception as exc:                       # noqa: BLE001
                    conn.rollback()
                    print(f"  {col:34s} UNMEASURED ({type(exc).__name__})")
                    results.append((col, None))
                    continue
            conn.rollback()
            populated = results[-1][1]
            print(f"  {col:34s} {populated:>12,}")

        dead = [c for c, n in results if n == 0]
        frozen = [(c, n) for c, n in results if n]
        unmeasured = [c for c, n in results if n is None]
        print(f"\n  dead (zero rows)   {len(dead)}")
        print(f"  frozen (populated) {len(frozen)}")
        if unmeasured:
            print(f"  UNMEASURED         {len(unmeasured)}  "
                  f"-- not the same as zero")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
