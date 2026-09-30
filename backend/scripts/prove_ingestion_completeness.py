#!/usr/bin/env python
"""
Prove the ingestion guards bite — against the real driver, on scratch
=====================================================================
Layer 3 of the evidence for the three Phase 6 blockers in
`docs/canonical_rehearsal_record.md`. Layers 1 and 2 (pure behaviour for
StageResult, AST for the loader's ordering) live in
`tests/test_ingestion_completeness.py` and need no database.

This one needs psycopg2 and a real connection, because the defects it guards
against are transactional, and a guard that has only ever been reasoned about
has not been shown to work. Each proof INDUCES the exact failure it claims to
catch, and a proof that cannot be made to fail is reported as no proof at all.

    A  induced per-file failure  — a bad file must not take its batch with it
    B  induced within-file omission — a stated period that never lands must
       fail the load, not shrink the domain downstream stages prove against
    C  induced outer-commit failure — a file admitted but not committed must
       never appear in `written`

C is the subtle one, and it is the defect class already found elsewhere in
this codebase: evidence recorded before the transaction that would have made
it true. Releasing a savepoint is not durability — a rollback of the enclosing
transaction erases released savepoints too.

Refuses to run against production.

Usage:
    cd /opt/asx-screener/backend   (or the scratch checkout)
    DATABASE_URL_SYNC=...asx_screener_scratch ../asx-venv/bin/python \
        scripts/prove_ingestion_completeness.py
"""

import json
import gzip
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import psycopg2                                                    # noqa: E402

from scripts.eodhd.v2 import load_to_staging_fundamentals as L     # noqa: E402

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, claim: str, detail: str = "") -> None:
    RESULTS.append((bool(ok), claim, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {claim}")
    if detail:
        print(f"        {detail}")


def guard_target(dsn: str) -> str:
    db = dsn.rsplit("/", 1)[-1].split("?")[0]
    if db != "asx_screener_scratch":
        sys.exit(f"REFUSING: target is {db!r}, not asx_screener_scratch. "
                 "This writes to staging tables and is a rehearsal tool.")
    return db


def sample_files(n: int = 3) -> list[Path]:
    """Real files, so the happy path is genuinely exercised."""
    files = sorted(L.FUND_DIR.glob("*.json.gz"))
    if len(files) < n:
        sys.exit(f"need at least {n} fundamentals files, found {len(files)}")
    # Spread out, so the chosen files are not all one company's snapshots.
    step = max(1, len(files) // n)
    return [files[i * step] for i in range(n)]


# ── A: one bad file must not take its batch with it ─────────────────────────

def prove_isolation(conn, files) -> None:
    """The 30 Sep defect: conn.rollback() discarded up to 49 other companies'
    rows, and those files had already been counted as loaded."""
    victim = files[1].name
    real = L.load_file

    def failing(cur, path):
        if path.name == victim:
            raise RuntimeError("induced failure")
        return real(cur, path)

    L.load_file = failing
    try:
        cur = conn.cursor()
        # One batch, so all three share a transaction: if isolation is broken,
        # the survivors are rolled back with the victim.
        expected, written, empty, skipped, failed = L.load_files(
            conn, cur, files, batch_commit=len(files))
        cur.close()
    finally:
        L.load_file = real

    survivors = {f.name for f in files} - {victim}
    landed = survivors & (written | empty)
    check(victim in failed,
          "an induced per-file failure is recorded as failed",
          f"failed={sorted(failed)}")
    check(landed == survivors,
          "the other files in the same batch still survive",
          f"survivors={sorted(survivors)} landed={sorted(landed)}")
    check(victim not in written,
          "the failed file is not counted as written")


# ── B: a stated period that never lands must fail the load ──────────────────

def prove_within_file_omission(conn, files) -> None:
    """A file-grain proof passes while periods vanish inside the file.

    Induced by corrupting one period's record so `period_key` refuses it --
    exactly what a bare `continue` used to swallow.
    """
    src = files[0]
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / src.name
        with gzip.open(src, "rt", encoding="utf-8") as f:
            raw = json.load(f)

        fin = (raw.get("Financials") or {}).get("Income_Statement") or {}
        periods = fin.get("yearly") or {}
        if not periods:
            check(False, "the sample file states at least one yearly period",
                  f"{src.name} has none; pick a different sample")
            return
        doomed = sorted(periods)[0]
        periods[doomed] = "not a record"          # stated, unfileable

        with gzip.open(target, "wt", encoding="utf-8") as f:
            json.dump(raw, f)

        cur = conn.cursor()
        expected, written, empty, skipped, failed = L.load_files(
            conn, cur, [target], batch_commit=1)
        cur.close()

    proof = L.population_proof(expected, written, empty, skipped, failed)
    key = f"{src.name}|income|yearly|{doomed}"
    check(key in expected,
          "the corrupted period is still part of the expected population",
          f"key={key}")
    check(key in proof["unaccounted"],
          "a stated period that never landed is unaccounted, not silently dropped",
          f"unaccounted={len(proof['unaccounted'])}")
    check(bool(proof["unaccounted"]),
          "the load therefore does not report success")


# ── C: released is not durable ──────────────────────────────────────────────

class _CommitFails:
    """An outer transaction that dies after files were admitted."""

    def __init__(self):
        self.cur = _RecordingCursor()

    def cursor(self):
        return self.cur

    def commit(self):
        raise psycopg2.OperationalError("induced outer commit failure")


class _RecordingCursor:
    def execute(self, *a, **k):
        pass

    def close(self):
        pass


def prove_pending_is_not_written(files) -> None:
    """Admit a file, then fail the enclosing commit. `written` must not claim it.

    No real connection: the point is the promotion rule, and a stub makes the
    failure deterministic instead of hoping the database misbehaves.
    """
    real = L.load_file
    L.load_file = lambda cur, path: ({"fundamentals": 1}, set(), set())
    conn = _CommitFails()
    try:
        L.load_files(conn, conn.cursor(), files[:1], batch_commit=1)
    except psycopg2.OperationalError:
        check(True, "a failed outer commit propagates rather than being swallowed")
    except Exception as exc:                                       # noqa: BLE001
        check(False, "a failed outer commit propagates rather than being swallowed",
              f"raised {type(exc).__name__}: {exc}")
    else:
        check(False, "a failed outer commit propagates rather than being swallowed",
              "load_files returned normally")
    finally:
        L.load_file = real

    # The positive control: the same file, with a commit that works, IS
    # written. Without this, a rule that never promotes anything would pass
    # the test above.
    class _CommitWorks(_CommitFails):
        def commit(self):
            pass

    L.load_file = lambda cur, path: ({"fundamentals": 1}, set(), set())
    try:
        conn2 = _CommitWorks()
        _, written, _, _, _ = L.load_files(conn2, conn2.cursor(), files[:1],
                                           batch_commit=1)
        check(files[0].name in written,
              "the same file IS written when the commit succeeds",
              f"written={sorted(written)}")
    finally:
        L.load_file = real


def main() -> int:
    dsn = L.DB_URL
    db = guard_target(dsn)
    print(f"target database: {db}\n")

    files = sample_files()
    print("sample:", ", ".join(f.name for f in files), "\n")

    conn = psycopg2.connect(dsn)
    try:
        print("A  induced per-file failure")
        prove_isolation(conn, files)
        print("\nB  induced within-file omission")
        prove_within_file_omission(conn, files)
    finally:
        conn.rollback()
        conn.close()

    print("\nC  released is not durable")
    prove_pending_is_not_written(files)

    failed = [c for ok, c, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} proofs passed")
    if failed:
        print("INGESTION PROOF FAILED — the guards do not bite:")
        for c in failed:
            print(f"  - {c}")
        return 1
    print("INGESTION PROOF PASSED — each guard was induced to fire, and the "
          "controls show it is not firing unconditionally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
