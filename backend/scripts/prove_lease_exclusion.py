#!/usr/bin/env python
"""
Two real canonical invocations; the second must not enter the plan
===================================================================
The Phase 6 blocker, tested by induction rather than by convention.

On 30 Sep 2026 one command pasted twice started two
FULL_FUNDAMENTALS_CANONICAL executions 22 seconds apart against the same
database:

    id 6  14:02:14  FULL_FUNDAMENTALS_CANONICAL  rows_written NULL
    id 5  14:01:52  FULL_FUNDAMENTALS_CANONICAL  rows_written NULL

Neither reached finalisation, so nothing published. That was a watchful
terminal and a pkill, not an invariant.

This starts TWO production-shaped invocations against scratch -- real driver
processes with --execute --allow-production, not stubs -- and proves the
second refuses BEFORE create_run. The decisive evidence is not the exit code
but the run table: exactly one new run row, because a refusal that still
opened a run would have entered the plan.

Four proofs, and the controls matter as much as the assertions:

    A  the second invocation exits non-zero
    B  the second invocation creates NO run row
    C  a forged ASX_CANONICAL_LEASE_HELD does not get past the lock
    D  with the lease free, an invocation DOES enter the plan
       -- without which a driver that refused everything would pass A-C

Refuses to run against production.

Usage:
    cd /tmp/p0a-gate/backend
    DATABASE_URL_SYNC=...asx_screener_scratch \
        ../asx-venv/bin/python scripts/prove_lease_exclusion.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2                                                    # noqa: E402

from app.core.db import get_database_url_sync                      # noqa: E402
from compute.engine.canonical_lease import (                       # noqa: E402
    CANONICAL_LEASE_KEY, LEASE_HELD_ENV, lease_is_held,
)

DRIVER = BACKEND / "scripts" / "p0a_canonical_run.py"
PLAN = "FULL_FUNDAMENTALS_CANONICAL"
RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, claim: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), claim, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {claim}")
    if detail:
        print(f"        {detail}")


def guard_target(dsn: str) -> str:
    db = dsn.rsplit("/", 1)[-1].split("?")[0]
    if db != "asx_screener_scratch":
        sys.exit(f"REFUSING: target is {db!r}, not asx_screener_scratch.")
    return db


def max_run_id(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(max(id), 0) FROM screener.compute_runs")
        return cur.fetchone()[0]


def invoke(env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(DRIVER), "--plan", PLAN, "--execute",
         "--allow-production"],
        capture_output=True, text=True, env=env, timeout=300)


def main() -> int:
    dsn = get_database_url_sync()
    print(f"target database: {guard_target(dsn)}\n")

    conn = psycopg2.connect(dsn)
    conn.autocommit = True

    if lease_is_held(conn):
        sys.exit("REFUSING: the canonical lease is already held. Another run "
                 "is in flight; this test needs to control contention itself.")

    # ── A + B: a second real invocation, while the first holds the lease ────
    print("A/B  two production-shaped invocations")
    before = max_run_id(conn)

    first = subprocess.Popen(
        [sys.executable, str(DRIVER), "--plan", PLAN, "--execute",
         "--allow-production"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        # Wait for the first to actually hold the lock rather than sleeping a
        # guessed interval: a race here would prove nothing either way.
        deadline = time.time() + 120
        while time.time() < deadline and not lease_is_held(conn):
            if first.poll() is not None:
                out = first.stdout.read() if first.stdout else ""
                sys.exit(f"the first invocation exited early:\n{out[-2000:]}")
            time.sleep(0.5)

        if not lease_is_held(conn):
            sys.exit("the first invocation never took the lease — nothing to "
                     "contend with, so this proves nothing")

        after_first = max_run_id(conn)
        second = invoke()
        after_second = max_run_id(conn)

        check(second.returncode != 0,
              "the second invocation refuses",
              f"exit={second.returncode}")
        check("REFUSING" in (second.stdout + second.stderr),
              "and says why, rather than crashing")
        check(after_second == after_first,
              "the second invocation creates NO run row — it never entered "
              "the plan",
              f"max(run_id) {before} -> {after_first} (first) -> "
              f"{after_second} (after second)")

        # ── C: a forged inheritance claim must not get past the lock ────────
        # The first invocation still holds the lease here, so a forged claim
        # would ALSO have to beat the lock. Tested separately below with the
        # lease free, which is the case that actually matters.
        print("\nC  a forged inheritance claim, with the lease free")
    finally:
        first.terminate()
        try:
            first.wait(timeout=30)
        except subprocess.TimeoutExpired:
            first.kill()

    # Let the terminated process's session drop its advisory lock.
    deadline = time.time() + 30
    while time.time() < deadline and lease_is_held(conn):
        time.sleep(0.5)
    if lease_is_held(conn):
        sys.exit("the lease did not clear after terminating the first run")

    before_forged = max_run_id(conn)
    forged = invoke({LEASE_HELD_ENV: "not_a_real_wrapper"})
    after_forged = max_run_id(conn)
    check(forged.returncode != 0,
          "a forged inheritance claim is refused",
          f"exit={forged.returncode}")
    check("no session holds" in (forged.stdout + forged.stderr),
          "and the refusal names the claim as unbacked")
    check(after_forged == before_forged,
          "the forged claim creates NO run row",
          f"max(run_id) {before_forged} -> {after_forged}")

    # ── D: the control ─────────────────────────────────────────────────────
    print("\nD  control: with the lease free, a run DOES enter the plan")
    before_ctl = max_run_id(conn)
    ctl = subprocess.Popen(
        [sys.executable, str(DRIVER), "--plan", PLAN, "--execute",
         "--allow-production"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 180
        while time.time() < deadline and max_run_id(conn) == before_ctl:
            if ctl.poll() is not None:
                break
            time.sleep(1)
        entered = max_run_id(conn) > before_ctl
        check(entered,
              "an uncontended invocation enters the plan and opens a run",
              f"max(run_id) {before_ctl} -> {max_run_id(conn)}")
    finally:
        ctl.terminate()
        try:
            ctl.wait(timeout=30)
        except subprocess.TimeoutExpired:
            ctl.kill()

    conn.close()

    failed = [c for ok, c, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} proofs passed")
    if failed:
        print("LEASE EXCLUSION NOT PROVEN:")
        for c in failed:
            print(f"  - {c}")
        return 1
    print("LEASE EXCLUSION PROVEN — a second canonical execution cannot enter "
          "the plan, a forged inheritance claim cannot either, and an "
          "uncontended one still can.")
    print("\nNote: this leaves abandoned run rows with no finalisation, which "
          "is the lifecycle behaving correctly. The resolver will not select "
          "them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
