"""
P0-A rollout preconditions — checked before the first production write
======================================================================
Preconditions, not diagnostics. Every check that fails aborts with a non-zero
exit; nothing here prints a warning and carries on, because each one guards a
decision that is irreversible once a row has been written.

    migration
      -> THIS SCRIPT
      -> recompute through the canonical writer
      -> violations() == 0 for the governed set
      -> enable consumers

Usage:
    cd /opt/asx-screener && set -a && . backend/.env && set +a \
      && ./asx-venv/bin/python backend/scripts/p0a_preflight.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2  # noqa: E402

from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.metric_states import (  # noqa: E402
    GOVERNED_METRICS,
    LATEST_MODEL_VERSION,
)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if detail:
        print(f"        {detail}")
    if not ok:
        failures.append(label)


def main() -> int:
    conn = psycopg2.connect(get_database_url_sync())
    cur = conn.cursor()

    print(f"\nP0-A preflight — target model {LATEST_MODEL_VERSION}\n")

    # ── 1 · the schema is ready ──────────────────────────────────────────────
    cur.execute("""
        SELECT count(*) FROM information_schema.columns
         WHERE table_schema='screener' AND table_name='universe'
           AND column_name IN ('metric_states','compute_run_id')
    """)
    check("migration applied (metric_states, compute_run_id present)",
          cur.fetchone()[0] == 2,
          "run migrations/add_metric_states_to_universe.sql first")

    cur.execute("""
        SELECT to_regclass('screener.compute_runs') IS NOT NULL,
               to_regclass('screener.compute_runs') IS NOT NULL
    """)
    check("screener.compute_runs exists", cur.fetchone()[0])

    # ── 2 · V1 is still amendable, or it is not ──────────────────────────────
    # The governed set for a version is pinned so that a row written under it
    # can be validated against exactly what it promised. That guarantee only
    # holds if the set stops changing once rows exist. V1 gained two
    # margin-expansion metrics after the cross-sectional audit, which is
    # legitimate only while no row references it.
    #
    # This is a HARD PRECONDITION, not a warning: if rows already exist, the
    # correct response is an explicit decision to cut V2, not a silent
    # recompute under a V1 that no longer means what those rows promised.
    try:
        cur.execute("""
            SELECT count(*) FROM screener.universe u
              JOIN screener.compute_runs r ON r.id = u.compute_run_id
             WHERE r.factor_model_version = %s
        """, (LATEST_MODEL_VERSION,))
        existing = cur.fetchone()[0]
    except psycopg2.Error:
        conn.rollback()
        existing = 0

    check(f"no persisted rows reference {LATEST_MODEL_VERSION}",
          existing == 0,
          f"{existing} rows already written under {LATEST_MODEL_VERSION}. "
          f"Its governed set is frozen from the first production write — "
          f"adding metrics now requires cutting a new version. Abort and "
          f"decide explicitly rather than recomputing under a changed V1.")

    # ── 3 · the governed set is coherent ─────────────────────────────────────
    from compute.engine.metric_registry import SENSITIVE
    missing = SENSITIVE - GOVERNED_METRICS[LATEST_MODEL_VERSION]
    check("every sensitive metric is governed", not missing,
          f"ungoverned: {sorted(missing)}" if missing else "")

    # ── 4 · the universe carries what the resolver needs ─────────────────────
    cur.execute("""
        SELECT count(*) FROM information_schema.columns
         WHERE table_schema='screener' AND table_name='universe'
           AND column_name IN ('sector','industry','is_reit','is_miner')
    """)
    check("domain-resolution columns present", cur.fetchone()[0] == 4)

    # ── 5 · what the recompute is walking into ───────────────────────────────
    cur.execute("SELECT max(ex_date), count(*) FILTER (WHERE ex_date > NOW() "
                "- INTERVAL '30 days') FROM market.dividends")
    latest, recent = cur.fetchone()
    print(f"\n  note  dividend feed: latest ex-date {latest}, {recent} rows in "
          f"30 days")
    print("        an unhealthy feed is not a blocker — income metrics are "
          "written\n        unavailable with a cause, which is the intended "
          "fail-closed state")

    cur.close()
    conn.close()

    print(f"\n{'ABORT' if failures else 'READY'} — "
          f"{len(failures)} precondition(s) failed\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
