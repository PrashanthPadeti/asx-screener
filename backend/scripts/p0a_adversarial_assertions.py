#!/usr/bin/env python
"""
The adversarial assertion bundle
================================
What the rehearsal proves after each exercise, asked of the real scratch
database and anchored to EXPLICIT run ids.

Never "the latest run", never "the most recent finalisation", never a
table-wide count. Those pass for the wrong reason: an unrelated run existing,
or a population that drifted between the exercise and the assertions, and the
report then proves correct behaviour about the wrong lifecycle.

    run_a   FULL_FUNDAMENTALS_CANONICAL   the canonical baseline
    run_b   DAILY_CANONICAL               reuse proved, published
    run_c   DAILY_CANONICAL + fault       provisional, unattributed, closed
    run_d   DAILY_CANONICAL               recovery, a NEW run

Every assertion runs; the report lists them all and the process exits non-zero
if any failed. Stopping at the first would hide the shape of a failure, and
the shape is what says whether the temporal contract broke in the way we were
testing for or in some other way.

Usage:
    p0a_adversarial_assertions.py --case B --run-b 43
    p0a_adversarial_assertions.py --case C --run-b 43 --run-c 44 \\
        --driver-exit 1 --driver-log /var/backups/p0a/discovery/c.log
    p0a_adversarial_assertions.py --case D --run-c 44 --run-d 45
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2  # noqa: E402

from app.core.db import get_database_url_sync  # noqa: E402
from compute.engine.metric_states import GOVERNED_METRICS, LATEST_MODEL_VERSION  # noqa: E402
from compute.engine.run_resolution import validated_run_ids  # noqa: E402
from compute.engine.run_stages import set_hash  # noqa: E402
from compute.engine.runtime_envelope import SCRATCH_MARKER  # noqa: E402


class Report:
    """Every assertion, with its verdict. Nothing stops early."""

    def __init__(self):
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, bool(ok), detail))
        return bool(ok)

    def failed(self) -> list:
        return [r for r in self.rows if not r[1]]

    def render(self, title: str) -> int:
        width = max(len(r[0]) for r in self.rows)
        print(f"\n=== {title} ===")
        for name, ok, detail in self.rows:
            mark = "PASS" if ok else "FAIL"
            print(f"  {mark}  {name.ljust(width)}  {detail}")
        bad = self.failed()
        print(f"\n{len(self.rows) - len(bad)}/{len(self.rows)} assertions passed")
        if bad:
            print("FAILED: " + "; ".join(n for n, _, _ in bad))
        return 1 if bad else 0


# ── The population, anchored to the run's own evidence ───────────────────────

def anchored_population(cur, run_id: int, report: Report):
    """The codes universe_build was responsible for under THIS run.

    Captured now, then verified against the expected_set_hash that run
    actually recorded. Re-deriving it without that check would let the
    population drift between the exercise and the assertions -- and every
    "every row in the rebuilt population" claim below would then be about a
    different set than the one the run rebuilt.
    """
    cur.execute("""
        SELECT c.asx_code FROM market.companies_current c
         WHERE c.asx_code IN (SELECT asx_code FROM screener.universe);""")
    population = {r[0] for r in cur.fetchall()}

    cur.execute("""
        SELECT expected_set_hash, expected_count
          FROM screener.compute_run_stages
         WHERE run_id = %s AND stage_name = 'universe_build';""", (run_id,))
    row = cur.fetchone()
    if not row:
        report.check("population anchored to run evidence", False,
                     f"run {run_id} has no universe_build stage row")
        return population

    recorded_hash, recorded_count = row
    ours = set_hash(population)
    report.check(
        "population anchored to run evidence", ours == recorded_hash,
        f"{len(population):,} codes, hash {ours[:12]} vs recorded "
        f"{str(recorded_hash)[:12]} ({recorded_count:,} expected)")
    return population


# ── Case C: the injected post-rebuild failure ────────────────────────────────

def case_c(cur, args, report: Report) -> None:
    run_b, run_c = args.run_b, args.run_c

    # 1. The driver stopped, and stopped for the reason we injected.
    report.check("1  driver exited non-zero", args.driver_exit != 0,
                 f"exit {args.driver_exit}")
    # A missing log is an unmet assertion, not a crash. Pointed at a path that
    # does not exist this raised FileNotFoundError and took the whole bundle
    # down, so a mistyped --driver-log read as a broken instrument rather than
    # as evidence that could not be found.
    classified, detail = False, args.driver_log or "no --driver-log given"
    if args.driver_log:
        log_path = Path(args.driver_log)
        if not log_path.exists():
            detail = f"{args.driver_log} does not exist"
        else:
            text = log_path.read_text(encoding="utf-8", errors="ignore")
            classified = ("INJECTED FAULT" in text
                          and "after_provisional_rebuild" in text)
            if not classified:
                # rc=127 produced a FAIL with no fault injected at all. The
                # distinction matters: a run that stopped for some other
                # reason proves nothing about the boundary being tested.
                detail = ("no INJECTED FAULT line — the run failed for some "
                          "other reason and proves nothing about this boundary")
    report.check("1b classified as InjectedFault", classified, detail)

    # 2. The failure is about the lifecycle we think it is.
    cur.execute("SELECT plan_name FROM screener.compute_runs WHERE id = %s;",
                (run_c,))
    row = cur.fetchone()
    report.check("2  run_c plan_name", bool(row) and row[0] == args.expect_plan,
                 f"{row[0] if row else 'run missing'} (expected {args.expect_plan})")

    # 3. universe_build completed and its evidence stands.
    cur.execute("""
        SELECT status, written_count FROM screener.compute_run_stages
         WHERE run_id = %s AND stage_name = 'universe_build';""", (run_c,))
    row = cur.fetchone()
    report.check("3  universe_build SUCCESS", bool(row) and row[0] == "success",
                 f"{row[0]}, {row[1]:,} written" if row else "no stage row")

    # 4. Nothing was published.
    cur.execute("SELECT 1 FROM screener.compute_run_finalizations WHERE run_id = %s;",
                (run_c,))
    report.check("4  run_c has no finalisation", cur.fetchone() is None)

    # 5. No row claims the failed run.
    cur.execute("SELECT count(*) FROM screener.universe WHERE compute_run_id = %s;",
                (run_c,))
    n = cur.fetchone()[0]
    report.check("5  zero rows carry run_c", n == 0, f"{n:,} rows")

    population = anchored_population(cur, run_c, report)

    # 6-7. The authority was revoked across the whole rebuilt population, and
    # no stale sidecar survived to claim an assessment nobody performed.
    cur.execute("""
        SELECT count(*) FILTER (WHERE compute_run_id IS NOT NULL),
               count(*) FILTER (WHERE metric_states IS NOT NULL),
               count(*)
          FROM screener.universe WHERE asx_code = ANY(%s);""",
        (list(population),))
    attributed, sidecars, total = cur.fetchone()
    report.check("6  rebuilt population compute_run_id IS NULL", attributed == 0,
                 f"{attributed:,} of {total:,} still attributed")
    report.check("7  no stale canonical metric_states", sidecars == 0,
                 f"{sidecars:,} of {total:,} still carry a sidecar")

    # 8. The governed surface fails closed through the normal path.
    report.check(*_projection_withheld(cur, population))

    # 9. The previous finalised run is untouched historical evidence.
    cur.execute("""
        SELECT r.plan_name, f.rows_written, f.persistence_violations
          FROM screener.compute_runs r
          JOIN screener.compute_run_finalizations f ON f.run_id = r.id
         WHERE r.id = %s;""", (run_b,))
    row = cur.fetchone()
    report.check("9  run_b finalisation retained", bool(row),
                 f"{row[0]}, {row[1]:,} rows, {row[2]} violations" if row
                 else "run_b has no finalisation")

    # 10. The resolver does not fall back to run_b for rows that no longer
    #     belong to it. run_b may still be servable in principle; what must not
    #     happen is the REBUILT rows being served under it.
    servable = validated_run_ids(cur)
    report.check("10 resolver excludes run_c", run_c not in servable,
                 f"servable: {servable}")
    cur.execute("""
        SELECT count(*) FROM screener.universe
         WHERE asx_code = ANY(%s) AND compute_run_id = ANY(%s);""",
        (list(population), servable or [-1]))
    served = cur.fetchone()[0]
    report.check("10b rebuilt rows match no servable run", served == 0,
                 f"{served:,} rebuilt rows carry a servable run id")

    # 12. The clone still attests to being a clone while we assert about it.
    _marker_consistent(cur, report)

    # 13. The failed run is immutable.
    _run_immutable(cur, run_c, report)


def _projection_withheld(cur, population):
    """Every governed value withheld, with OUTSIDE_SNAPSHOT as the cause.

    Run through app/core/row_projection.py -- the same code a request uses --
    rather than by re-reading the columns. A bespoke check here would prove
    that the columns look revoked, not that the API refuses to serve them.
    """
    from app.core.row_projection import OUTSIDE_SNAPSHOT, project_row
    from compute.engine.universe_writer import column_for

    columns = {m: column_for(m) for m in GOVERNED_METRICS[LATEST_MODEL_VERSION]}
    sample = sorted(population)[:5]
    if not sample:
        return "8  projection withholds governed values", False, "empty population"

    cols = ", ".join(sorted(set(columns.values())))
    cur.execute(f"""
        SELECT asx_code, metric_states, compute_run_id, {cols}
          FROM screener.universe WHERE asx_code = ANY(%s);""", (sample,))
    names = [d[0] for d in cur.description]

    servable = validated_run_ids(cur)
    bad = []
    for row in cur.fetchall():
        values, states = project_row(
            dict(zip(names, row)), model_version=LATEST_MODEL_VERSION,
            expected=columns, run_ids=servable)
        for metric, column in columns.items():
            if values.get(column) is not None:
                bad.append(f"{row[0]}.{metric} served")
            elif states.get(metric, {}).get("reason") != OUTSIDE_SNAPSHOT:
                bad.append(f"{row[0]}.{metric} withheld for "
                           f"{states.get(metric, {}).get('reason')!r}")
    return ("8  projection withholds as OUTSIDE_SNAPSHOT", not bad,
            f"{len(sample)} rows x {len(columns)} metrics"
            + ("" if not bad else f" — {bad[:3]}"))


def _marker_consistent(cur, report: Report) -> None:
    cur.execute("SELECT to_regclass(%s);", (SCRATCH_MARKER,))
    present = cur.fetchone()[0] is not None
    if not present:
        report.check("12 scratch marker self-consistent", False,
                     "the marker is gone; these assertions may be about "
                     "production")
        return
    cur.execute(f"SELECT database, current_database() FROM {SCRATCH_MARKER} LIMIT 1;")
    row = cur.fetchone()
    report.check("12 scratch marker self-consistent",
                 bool(row) and row[0] == row[1],
                 f"marker names {row[0] if row else None}, connected to "
                 f"{row[1] if row else None}")


def _run_immutable(cur, run_id: int, report: Report) -> None:
    """The trigger refuses to edit a run. Proved by attempting it.

    A claim that evidence is immutable, checked by reading it, proves only
    that nobody happened to change it.
    """
    try:
        cur.execute("SAVEPOINT immutability_probe;")
        cur.execute("UPDATE screener.compute_runs SET engine = engine || '_x' "
                    "WHERE id = %s;", (run_id,))
        cur.execute("ROLLBACK TO SAVEPOINT immutability_probe;")
        report.check("13 failed run is immutable", False,
                     "an UPDATE to the run row succeeded")
    except psycopg2.errors.RaiseException as exc:
        cur.execute("ROLLBACK TO SAVEPOINT immutability_probe;")
        report.check("13 failed run is immutable", True,
                     str(exc).splitlines()[0][:70])


# ── Case B: the daily path is genuinely the daily path ───────────────────────

def case_b(cur, args, report: Report) -> None:
    run_b = args.run_b

    cur.execute("SELECT plan_name FROM screener.compute_runs WHERE id = %s;",
                (run_b,))
    row = cur.fetchone()
    report.check("B1 run_b plan_name is DAILY_CANONICAL",
                 bool(row) and row[0] == "DAILY_CANONICAL",
                 row[0] if row else "run missing")

    # The assertion that separates a daily run from a full cycle that happened
    # to pass: yearly_compute must not have executed under this run at all.
    cur.execute("""
        SELECT count(*) FROM screener.compute_run_stages
         WHERE run_id = %s AND stage_name = 'yearly_compute';""", (run_b,))
    n = cur.fetchone()[0]
    report.check("B2 yearly_compute did not run under run_b", n == 0,
                 f"{n} yearly_compute stage rows")

    # The fingerprint admitted at plan-open, the one the reused output proved,
    # and the one re-checked at publication must all be the same value.
    cur.execute("""
        SELECT details -> 'yearly_source_fingerprint'
          FROM screener.compute_run_finalizations WHERE run_id = %s;""", (run_b,))
    row = cur.fetchone()
    published = row[0] if row else None

    from compute.engine import source_fingerprint as sfp
    source_run, proven = sfp.proven_by_latest_yearly(cur)
    report.check("B3 reused yearly output has a proven fingerprint",
                 proven is not None, f"proven by run {source_run}")
    report.check(
        "B4 publication fingerprint equals the reused one",
        bool(published) and proven is not None
        and published == proven.aggregate,
        f"published {str(published)[:12]}, reused {proven.aggregate[:12]}"
        if proven else "no reused fingerprint")

    cur.execute("SELECT 1 FROM screener.compute_run_finalizations WHERE run_id = %s;",
                (run_b,))
    report.check("B5 run_b finalised", cur.fetchone() is not None)
    report.check("B6 resolver serves run_b", run_b in validated_run_ids(cur))
    _marker_consistent(cur, report)


# ── Case D: recovery is a new run, never a resumed one ───────────────────────

def case_d(cur, args, report: Report) -> None:
    run_c, run_d = args.run_c, args.run_d

    report.check("D1 run_d is a different run", run_c != run_d,
                 f"run_c={run_c}, run_d={run_d}")

    # Ordering by creation time, not by arithmetic adjacency: the id sequence
    # can be consumed by anything, and "d == c + 1" would be an assertion about
    # the allocator rather than about the lifecycle.
    cur.execute("""
        SELECT (SELECT run_at FROM screener.compute_runs WHERE id = %s),
               (SELECT run_at FROM screener.compute_runs WHERE id = %s);""",
        (run_c, run_d))
    c_at, d_at = cur.fetchone()
    report.check("D2 run_d created after run_c",
                 bool(c_at and d_at) and d_at > c_at, f"{c_at} -> {d_at}")

    cur.execute("SELECT 1 FROM screener.compute_run_finalizations WHERE run_id = %s;",
                (run_c,))
    report.check("D3 run_c still unfinalised", cur.fetchone() is None)

    cur.execute("""
        SELECT status FROM screener.compute_run_stages
         WHERE run_id = %s AND stage_name = 'universe_build';""", (run_c,))
    row = cur.fetchone()
    report.check("D4 run_c evidence unchanged", bool(row) and row[0] == "success",
                 row[0] if row else "missing")

    cur.execute("""
        SELECT rows_written, persistence_violations
          FROM screener.compute_run_finalizations WHERE run_id = %s;""", (run_d,))
    row = cur.fetchone()
    report.check("D5 run_d finalised", bool(row),
                 f"{row[0]:,} rows, {row[1]} violations" if row else "not finalised")
    report.check("D6 run_d read-back clean", bool(row) and row[1] == 0)

    servable = validated_run_ids(cur)
    report.check("D7 resolver selects run_d", run_d in servable, f"{servable}")
    report.check("D8 resolver still excludes run_c", run_c not in servable)

    population = anchored_population(cur, run_d, report)
    cur.execute("""
        SELECT count(*) FROM screener.universe
         WHERE asx_code = ANY(%s) AND compute_run_id IS DISTINCT FROM %s;""",
        (list(population), run_d))
    stragglers = cur.fetchone()[0]
    report.check("D9 whole population attributed to run_d", stragglers == 0,
                 f"{stragglers:,} rows not carrying run_d")

    _run_immutable(cur, run_c, report)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", required=True, choices=("B", "C", "D"))
    p.add_argument("--run-a", type=int)
    p.add_argument("--run-b", type=int)
    p.add_argument("--run-c", type=int)
    p.add_argument("--run-d", type=int)
    p.add_argument("--driver-exit", type=int, default=0)
    p.add_argument("--driver-log")
    p.add_argument("--expect-plan", default="DAILY_CANONICAL")
    args = p.parse_args()

    required = {"B": ["run_b"], "C": ["run_b", "run_c"], "D": ["run_c", "run_d"]}
    missing = [f"--{n.replace('_', '-')}" for n in required[args.case]
               if getattr(args, n) is None]
    if missing:
        print(f"case {args.case} needs {', '.join(missing)}: every assertion is "
              f"anchored to an explicit run id, never to the latest run.",
              file=sys.stderr)
        return 2

    conn = psycopg2.connect(get_database_url_sync())
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT current_database()")
    print(f"asserting against: {cur.fetchone()[0]}")

    report = Report()
    try:
        {"B": case_b, "C": case_c, "D": case_d}[args.case](cur, args, report)
    finally:
        conn.rollback()          # read-only: nothing here may change the target
        cur.close()
        conn.close()

    return report.render(f"case {args.case}")


if __name__ == "__main__":
    sys.exit(main())
