#!/usr/bin/env python
"""
Behavioural proof: a valid value becomes an unavailable one
===========================================================
Runs against a SCRATCH or GATE database only. Refuses production.

The source guard in tests/test_yearly_upsert_empties_retired_columns.py
proves the SET clause says `= NULL` for all 64 retired columns. It does NOT
prove that PostgreSQL, running the real statement through the real
execute_values path, replaces an existing value with NULL.

That distinction is the whole finding. 6b was never "a column is missing
from a list" -- it was "a stored value survives a run that restamps the
row as current". A test that reads the SQL cannot tell those apart, because
the defective statement and the repaired one differ only in what the
database does with an EXISTING row.

THE TRANSITION ON TRIAL

    before   p_fcf_ratio = 12.34      computed_at = an old date
    upsert   the real INSERT_SQL, same (asx_code, fiscal_year)
    after    p_fcf_ratio IS NULL      computed_at = the new date

A `COALESCE(yearly_metrics.p_fcf_ratio, EXCLUDED.p_fcf_ratio)` would pass
every source assertion and fail here, which is why this exists.

Three columns are watched together, because they fail differently:

    p_fcf_ratio    RETIRED and SERVED -- reaches screener.universe as
                   price_to_fcf. Must go to NULL.
    quick_ratio    RETIRED, not served. The largest frozen population
                   after p_fcf_ratio. Must go to NULL.
    pe_ratio       WRITTEN. Must take the new value, proving the statement
                   still refreshes what it is supposed to refresh. A
                   repair that emptied everything would pass a
                   NULL-only check.

Usage (from a worktree, against scratch or a gate database):
    python tests/fixtures/prove_retired_columns_are_emptied.py

Exit codes: 0 proven · 1 the property does not hold · 2 refused
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.core.db import get_database_url_sync                      # noqa: E402

# psycopg2 and the compute engine are imported INSIDE main(), not here.
#
# tests/test_fixture_scratch_guard.py loads every mutating fixture to check
# that its _connect refuses production, and it does so hermetically -- on a
# machine with no driver, which is exactly where someone is most likely to
# run a fixture by hand. Importing the engine at module scope pulled in
# psycopg2.extensions.new_type and a chain of others, and the guard began
# failing on the stub rather than checking the guard.
#
# A fixture whose production check cannot be inspected without loading the
# world is a fixture whose production check will eventually go unchecked.

RETIRED_SERVED = "p_fcf_ratio"
RETIRED_UNSERVED = "quick_ratio"
WRITTEN = "pe_ratio"

#: Databases this fixture may mutate.
#:
#: An exact name, or the gate's per-run database by its FULL declared
#: shape. The gate creates `asx_gate_$$`, so an allowlist of literals
#: cannot cover it -- but a substring test must not be the answer either.
#: The sibling fixture records why: `"scratch" in url` admitted two of
#: three URLs that resolved to PRODUCTION, because the word appeared in a
#: username and in a connection parameter.
#:
#: So the resolved database NAME is matched against anchored patterns. The
#: anchors are what make this identity rather than substring matching:
#: `asx_screener` cannot match either one.
APPROVED_EXACT = frozenset({"asx_screener_scratch"})
APPROVED_PATTERN = re.compile(r"^asx_gate_\d+$")


def _target_database(url: str) -> str:
    """The database this URL resolves to, by parsing -- not by eye."""
    return urlsplit(url).path.lstrip("/").split("?")[0]


def _may_mutate(database: str) -> bool:
    """May this fixture destroy the named database?

    The gate builds a per-run database called `asx_gate_<pid>`, so a list
    of literals cannot cover it. The pattern is ANCHORED at both ends,
    which is what makes this identity matching rather than the substring
    test that once admitted production three different ways.
    """
    return (database in APPROVED_EXACT
            or bool(APPROVED_PATTERN.match(database)))


def _connect():
    url = get_database_url_sync()
    target = _target_database(url)
    if not _may_mutate(target):
        raise SystemExit(
            f"2  REFUSING: this fixture mutates data and {target!r} is not "
            f"an approved target.\n"
            f"  resolved database : {target!r}\n"
            f"  approved          : {', '.join(sorted(APPROVED_EXACT))} "
            f"or asx_gate_<digits>\n"
            f"Point DATABASE_URL_SYNC at a scratch or gate database.")
    import psycopg2
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def _pick_row(cur):
    """An existing (asx_code, fiscal_year) to exercise the conflict path.

    The conflict path is the only one on trial: a fresh INSERT writes NULL
    for these columns anyway, because they are nullable with no default.
    Proving the INSERT path would prove nothing about the defect.
    """
    cur.execute("""
        SELECT asx_code, fiscal_year
          FROM market.yearly_metrics
         ORDER BY asx_code, fiscal_year
         LIMIT 1
    """)
    row = cur.fetchone()
    if row is None:
        raise SystemExit(
            "2  market.yearly_metrics is empty in this database, so the "
            "conflict path cannot be exercised. This is not a pass.")
    return row


def main() -> int:
    from psycopg2.extras import execute_values
    from compute.engine.yearly_compute import INSERT_SQL, _insert_columns

    conn = _connect()
    cur = conn.cursor()
    code, fy = _pick_row(cur)
    columns = _insert_columns()
    old_stamp = datetime(2020, 1, 1, tzinfo=timezone.utc)

    # ── Arrange: a valid value in each retired column, and an old stamp ──
    cur.execute(f"""
        UPDATE market.yearly_metrics
           SET {RETIRED_SERVED} = 12.34,
               {RETIRED_UNSERVED} = 56.78,
               {WRITTEN} = 1.0,
               computed_at = %s
         WHERE asx_code = %s AND fiscal_year = %s
    """, (old_stamp, code, fy))

    cur.execute(f"""
        SELECT {RETIRED_SERVED}, {RETIRED_UNSERVED}, {WRITTEN}, computed_at
          FROM market.yearly_metrics
         WHERE asx_code = %s AND fiscal_year = %s
    """, (code, fy))
    before = cur.fetchone()
    if before[0] is None or before[1] is None:
        raise SystemExit("2  could not seed the retired columns; aborting")
    print(f"before   {code} FY{fy}: {RETIRED_SERVED}={before[0]} "
          f"{RETIRED_UNSERVED}={before[1]} {WRITTEN}={before[2]} "
          f"computed_at={before[3]}")

    # ── Act: the REAL statement, through the REAL executor ──────────────
    #
    # The row is built from the existing row's own values so every column
    # stays internally consistent; only pe_ratio and computed_at change.
    # Inventing a row would test a row nobody writes.
    cur.execute(f"SELECT {', '.join(columns)} "
                f"FROM market.yearly_metrics "
                f"WHERE asx_code = %s AND fiscal_year = %s", (code, fy))
    values = list(cur.fetchone())
    new_stamp = datetime.now(timezone.utc)
    values[columns.index(WRITTEN)] = 2.0
    values[columns.index("computed_at")] = new_stamp

    execute_values(cur, INSERT_SQL, [tuple(values)], page_size=1)

    cur.execute(f"""
        SELECT {RETIRED_SERVED}, {RETIRED_UNSERVED}, {WRITTEN}, computed_at
          FROM market.yearly_metrics
         WHERE asx_code = %s AND fiscal_year = %s
    """, (code, fy))
    after = cur.fetchone()
    print(f"after    {code} FY{fy}: {RETIRED_SERVED}={after[0]} "
          f"{RETIRED_UNSERVED}={after[1]} {WRITTEN}={after[2]} "
          f"computed_at={after[3]}")

    # ── Assert ──────────────────────────────────────────────────────────
    failures = []
    if after[0] is not None:
        failures.append(
            f"{RETIRED_SERVED} is {after[0]!r}, not NULL. A valid value "
            f"survived a run that restamped the row -- the defect is "
            f"intact, and this column reaches customers as price_to_fcf.")
    if after[1] is not None:
        failures.append(
            f"{RETIRED_UNSERVED} is {after[1]!r}, not NULL.")
    if after[2] != 2.0:
        failures.append(
            f"{WRITTEN} is {after[2]!r}, expected 2.0. The statement no "
            f"longer refreshes a written column, so the repair emptied "
            f"more than it should have.")
    if after[3] == before[3]:
        failures.append(
            "computed_at did not move. The repair must empty the values, "
            "not stop the clock.")

    # Never commit. The proof is in what the statement DID, and leaving it
    # behind would corrupt a shared scratch database for the next reader.
    conn.rollback()
    conn.close()

    for line in failures:
        print(f"FAIL  {line}")
    if failures:
        print(f"\n{len(failures)} assertion(s) failed; rolled back")
        return 1
    print("\nPROVEN: a valid value became unavailable, a written column was "
          "refreshed, and the timestamp moved. Rolled back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
