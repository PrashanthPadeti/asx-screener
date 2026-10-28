"""
One published run, so the gate can test the contract that matters
=================================================================
gate_full_suite builds its isolated database from `pg_dump --schema-only`:
the real schema and no rows. That is right for almost everything, and it
leaves one blind spot.

A governed request is answerable only against a validated compute run. With
no runs at all, every governed query returns 503 -- correctly -- so no
primary-feature test could ever exercise a governed path. The ones that pass
today pass by querying UNGOVERNED fields: market_cap, sector, is_reit.

That stayed invisible while return_1y was ungoverned, because the documented
Query Mode syntax -- "return_1y > 0 AND market_cap > 0 AND is_reit = false"
-- happened to be answerable without a contract. v11.2.63 governs the price
windows, the same query became a governed query, and the gate reported a
primary feature broken. It was right: on a database with no runs, it is.

So the gap is the gate's, not the release's. This seeds exactly one run.

What it does NOT do
-------------------
It does not loosen the publication contract, and it cannot. The run it
writes has to satisfy VALIDATED_RUNS_SQL -- the same statement the API runs,
with the same parameters -- and this script asserts that by asking the
resolver afterwards. If the seed were a shortcut, validated_run_ids() would
return nothing and this exits non-zero.

The required stages are read from plan_requirements(), never listed here. A
hardcoded list would be a second declaration of the plan, and it would go
stale the first time a stage is added -- seeding a run the resolver rejects,
or worse, one it accepts while production's real runs are failing a
requirement this never modelled.

It writes no universe rows. Zero results is a valid screener response and
the shape assertions already accept it; what the tests need is a contract to
answer under, not data to answer with.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2                                              # noqa: E402

from app.core.db import get_database_url_sync                # noqa: E402
from compute.engine.metric_states import LATEST_MODEL_VERSION  # noqa: E402
from compute.engine.run_plans import plan_requirements       # noqa: E402
from compute.engine.run_resolution import validated_run_ids  # noqa: E402

PLAN = "DAILY_CANONICAL"


def main() -> int:
    requirements = plan_requirements()
    if PLAN not in requirements:
        print(f"gate-seed: {PLAN} is not a declared plan; known plans are "
              f"{', '.join(sorted(requirements))}", file=sys.stderr)
        return 2

    required = list(requirements[PLAN])
    if not required:
        print(f"gate-seed: {PLAN} declares no required stages. A run with no "
              f"requirements would validate trivially and the seed would "
              f"prove nothing.", file=sys.stderr)
        return 2

    conn = psycopg2.connect(get_database_url_sync())
    conn.autocommit = False
    cur = conn.cursor()

    # Refuse to touch a database that already has runs. This script exists
    # for the gate's empty clone; pointed anywhere else it must do nothing
    # rather than add a fabricated run to a real history.
    cur.execute("SELECT count(*) FROM screener.compute_runs")
    existing = cur.fetchone()[0]
    if existing:
        print(f"gate-seed: refusing — this database already has {existing} "
              f"compute run(s). The seed is only for an empty clone.",
              file=sys.stderr)
        return 2

    now = datetime.now(tz=timezone.utc)

    cur.execute(
        """INSERT INTO screener.compute_runs
               (run_at, engine, factor_model_version, plan_name, rows_written)
           VALUES (%s, %s, %s, %s, %s)
           RETURNING id""",
        (now, "gate_seed", LATEST_MODEL_VERSION, PLAN, 0))
    run_id = cur.fetchone()[0]

    # Every stage the plan requires, read from the plan itself.
    #
    # The counts and hashes are the stage's own evidence that it covered its
    # source population: status='success' means expected_set_hash equals
    # written_set_hash. An empty clone has an empty source population, so the
    # honest evidence is 0 = 0 over the hash of the empty set -- the same
    # shape a real stage writes, not a filler value chosen to get past a NOT
    # NULL. A seed claiming a non-zero count it did not write would be
    # fabricating the exact proof this table exists to hold.
    empty_set_hash = hashlib.sha256(b"").hexdigest()
    for stage in required:
        cur.execute(
            """INSERT INTO screener.compute_run_stages
                   (run_id, stage_name, status,
                    expected_count, written_count, missing_count, extra_count,
                    expected_set_hash, written_set_hash, details)
               VALUES (%s, %s, 'success', 0, 0, 0, 0, %s, %s, %s)""",
            (run_id, stage, empty_set_hash, empty_set_hash,
             json.dumps({"seeded_by": "gate_seed_run",
                         "note": "empty clone: the source population is empty, "
                                 "so coverage is 0 of 0"})))

    cur.execute(
        """INSERT INTO screener.compute_run_finalizations
               (run_id, rows_written, persistence_violations, details)
           VALUES (%s, 0, 0, %s)""",
        (run_id, json.dumps({"seeded_by": "gate_seed_run"})))

    conn.commit()

    # The seed proves itself against the resolver the API uses. Same
    # statement, same parameters, same answer a governed request would get --
    # which is the only reason seeding a run means anything.
    ids = validated_run_ids(cur)
    if run_id not in ids:
        conn.rollback()
        print(f"gate-seed: run {run_id} was written and the resolver does not "
              f"accept it (validated: {ids}). The seed does not satisfy the "
              f"publication contract, so it must not be reported as one.",
              file=sys.stderr)
        return 1

    print(f"gate: seeded compute run {run_id} under {LATEST_MODEL_VERSION} "
          f"({PLAN}, {len(required)} required stages, resolver accepts it)")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
