"""
Daily Pipeline — ASX Screener
==============================
Runs after ASX market close each weekday (08:30 UTC = 18:30 AEST).

Shape (rule 3 of docs/canonical_orchestration.md):

    INGESTION PREFIX
      1.  Download today's EOD prices (per-stock, from yesterday) -> Raw Zone
      2.  Download ASIC short positions                           -> Raw Zone
      3.  Load prices -> staging_au.eod_prices                    (UPSERT)
      4.  Load short positions -> staging_au.short_positions
      6.  Transform short positions -> market.short_positions

    ══ INGESTION BARRIER ══  acquire the canonical execution lease

    CANONICAL DRIVER  p0a_canonical_run.py --plan DAILY_CANONICAL
      admission (incl. the yearly reuse fingerprint), then transform_prices,
      daily_compute, technical_compute, halfyearly_compute,
      period_metrics_compute, universe_build, and the canonical tail:
      publication-time fingerprint recheck, canonical commit, full-population
      read-back, finalisation.

    POST-PUBLICATION SUFFIX  (inside the lease, only if finalisation succeeded)
      14. Heatmap cache -> market.heatmap_cache / heatmap_labels

      11, 12, 15 remain handled by APScheduler.

Why the compute steps are not here any more
-------------------------------------------
They used to be: six separate commands running transform_prices,
daily_compute, technical_compute, halfyearly_compute,
period_metrics_compute and build_screener_universe. build_screener_universe
invalidates the canonical contract atomically -- by design -- and nothing
here re-established it, so every run revoked the published snapshot and the
governed surface failed closed until a human repaired it. Production ran that
way until the cron was disabled on 23 Sep 2026.

Those six steps ARE the DAILY_CANONICAL plan. They now run once, through the
driver, which owns admission before the first derived mutation: a refused
fingerprint leaves yesterday's validated snapshot intact rather than creating
today's unattributed universe.

Usage:
    python scripts/eodhd/v2/jobs/daily_pipeline.py
    python scripts/eodhd/v2/jobs/daily_pipeline.py --skip-download

Crontab (08:30 UTC Mon-Fri — ~2.5 hours after ASX close):
    30 8 * * 1-5 cd /opt/asx-screener && /opt/asx-screener/asx-venv/bin/python scripts/eodhd/v2/jobs/daily_pipeline.py >> /opt/asx-screener/logs/daily_pipeline.log 2>&1

Note: Steps 11-12-14 are skipped; APScheduler handles those (index prices, ETF prices, snapshots)
      at 5:30-6:45 PM. This pipeline focuses on core screener.universe data (Steps 1-10, 13).
"""

import argparse
import logging
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

#: The MAINTAINED backend tree, and only that one.
#:
#: parents[4] of backend/scripts/eodhd/v2/jobs/ is `backend`, not
#: /opt/asx-screener as the comment here claimed for a long time. Nothing
#: depended on the comment being right until the compute path below did.
BASE_DIR  = Path(__file__).resolve().parents[4]   # <repo>/backend
SCRIPTS   = BASE_DIR / "scripts" / "eodhd" / "v2"
ASIC      = BASE_DIR / "scripts" / "asic"
# Prefer backend/compute/engine (canonical source); fall back to root-level compute/engine
# if the server uses a symlink or flat deployment without the backend/ prefix.
#: One engine tree. No fallback.
#:
#: This resolved two candidates and took whichever existed:
#:
#:     _compute_canonical = BASE_DIR / "backend" / "compute" / "engine"
#:     _compute_fallback  = BASE_DIR / "compute" / "engine"
#:
#: BASE_DIR is `backend`, so the "canonical" candidate was
#: backend/backend/compute/engine and could never exist, and the "fallback"
#: was backend/compute/engine — the maintained tree. It worked, by accident,
#: with the two names meaning the opposite of what they said.
#:
#: The trap was that correcting BASE_DIR to the repo root — the obvious
#: reading of the old comment — would have flipped the fallback to
#: <repo>/compute/engine: the stale April copies the deployment contract
#: records as a live hazard, correct code in git and something else
#: executing. A pipeline that silently selects a second engine tree is worse
#: than one that cannot start.
COMPUTE   = BASE_DIR / "compute" / "engine"
if not COMPUTE.is_dir():
    raise SystemExit(
        f"FATAL: compute engine tree not found at {COMPUTE}. There is no "
        f"fallback and there must not be one: a second tree is how April's "
        f"code ends up running against today's database. Fix the deployment.")
PYTHON    = sys.executable
TODAY     = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()

# Shared alert utility — path: backend/scripts/utils/alert.py (as weekly_pipeline)
sys.path.insert(0, str(BASE_DIR / "scripts"))
from utils.alert import send_failure_alert  # noqa: E402


# ── Pipeline Tracker ──────────────────────────────────────────────────────────

class PipelineTracker:
    """
    Records pipeline and step-level run status to market.pipeline_runs /
    market.pipeline_step_runs for admin monitoring and APScheduler dependency checks.

    All methods are best-effort — DB failures are logged but never propagate
    to the pipeline itself, so monitoring can never break data processing.
    """

    def __init__(self):
        self.run_id: int | None = None
        self._conn = None

    def connect(self) -> None:
        """Open a sync psycopg2 connection using DATABASE_URL_SYNC (or DATABASE_URL)."""
        try:
            import os
            import psycopg2
            # Load .env if present (same multi-path search as market_snapshot.py)
            try:
                from dotenv import load_dotenv
                _here = Path(__file__).resolve()
                for _candidate in [
                    _here.parents[4] / "backend" / ".env",   # /opt/asx-screener/backend/.env ← primary
                    _here.parents[3] / "backend" / ".env",
                    _here.parents[4] / ".env",
                    _here.parents[3] / ".env",
                ]:
                    if _candidate.exists():
                        load_dotenv(_candidate)
                        break
            except ImportError:
                pass

            db_url = os.environ.get("DATABASE_URL_SYNC", "")
            if not db_url:
                # Fall back: strip asyncpg prefix from DATABASE_URL
                async_url = os.environ.get("DATABASE_URL", "")
                db_url = async_url.replace("postgresql+asyncpg://", "postgresql://")
            if not db_url:
                log.warning("PipelineTracker: no DATABASE_URL — run tracking disabled")
                return
            self._conn = psycopg2.connect(db_url)
            self._conn.autocommit = True
            log.info("PipelineTracker: DB connected")
        except Exception as exc:
            log.warning(f"PipelineTracker: connect failed — {exc}")

    def _exec(self, sql: str, params=()):
        """Execute SQL; return cursor on success, None on failure."""
        if not self._conn:
            return None
        try:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur
        except Exception as exc:
            log.warning(f"PipelineTracker: SQL error — {exc}")
            return None

    def start_pipeline(self, run_date: str, total_steps: int = 14) -> None:
        cur = self._exec("""
            INSERT INTO market.pipeline_runs
                (run_date, pipeline_name, started_at, status, total_steps, steps_completed)
            VALUES (%s, 'daily', NOW(), 'running', %s, 0)
            ON CONFLICT (run_date, pipeline_name) DO UPDATE
              SET started_at    = NOW(),
                  status        = 'running',
                  steps_completed = 0,
                  failed_step   = NULL,
                  failed_step_name = NULL,
                  error_message = NULL,
                  completed_at  = NULL,
                  duration_seconds = NULL
            RETURNING id
        """, (run_date, total_steps))
        if cur:
            row = cur.fetchone()
            if row:
                self.run_id = row[0]
                log.info(f"PipelineTracker: pipeline_run id={self.run_id}")

    def start_step(self, step_number: int, step_name: str) -> None:
        if not self.run_id:
            return
        self._exec("""
            INSERT INTO market.pipeline_step_runs
                (run_id, run_date, step_number, step_name, started_at, status)
            VALUES (%s, CURRENT_DATE, %s, %s, NOW(), 'running')
            ON CONFLICT (run_id, step_number) DO UPDATE
              SET started_at = NOW(), status = 'running',
                  completed_at = NULL, error_message = NULL, duration_seconds = NULL
        """, (self.run_id, step_number, step_name))

    def finish_step(self, step_number: int, success: bool = True,
                    error_msg: str = None) -> None:
        if not self.run_id:
            return
        status = "success" if success else "failed"
        self._exec("""
            UPDATE market.pipeline_step_runs
               SET completed_at     = NOW(),
                   status           = %s,
                   duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::numeric(10,2),
                   error_message    = %s
             WHERE run_id = %s AND step_number = %s
        """, (status, error_msg, self.run_id, step_number))
        if success:
            self._exec("""
                UPDATE market.pipeline_runs
                   SET steps_completed = steps_completed + 1
                 WHERE id = %s
            """, (self.run_id,))

    def skip_step(self, step_number: int, step_name: str) -> None:
        if not self.run_id:
            return
        self._exec("""
            INSERT INTO market.pipeline_step_runs
                (run_id, run_date, step_number, step_name,
                 started_at, completed_at, status, duration_seconds)
            VALUES (%s, CURRENT_DATE, %s, %s, NOW(), NOW(), 'skipped', 0)
            ON CONFLICT (run_id, step_number) DO NOTHING
        """, (self.run_id, step_number, step_name))
        # Skipped steps still count toward completed (they were intentionally bypassed)
        self._exec("""
            UPDATE market.pipeline_runs
               SET steps_completed = steps_completed + 1
             WHERE id = %s
        """, (self.run_id,))

    def finish_pipeline(self, success: bool, failed_step: int = None,
                        failed_step_name: str = None, error_msg: str = None) -> None:
        if not self.run_id:
            return
        status = "success" if success else "failed"
        self._exec("""
            UPDATE market.pipeline_runs
               SET completed_at     = NOW(),
                   status           = %s,
                   failed_step      = %s,
                   failed_step_name = %s,
                   error_message    = %s,
                   duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::integer
             WHERE id = %s
        """, (status, failed_step, failed_step_name, error_msg, self.run_id))

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass


# ── Step runners ──────────────────────────────────────────────────────────────

def run(label: str, cmd: list[str],
        tracker: PipelineTracker = None, step: int = None) -> None:
    """Run a required step. Exits the pipeline on failure."""
    if tracker and step:
        tracker.start_step(step, label)
    log.info(f"▶  {label}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=BASE_DIR)
    elapsed = time.time() - t0
    if result.returncode != 0:
        log.error(f"✗  {label} failed (exit {result.returncode}) after {elapsed:.1f}s")
        if tracker and step:
            tracker.finish_step(step, success=False,
                                error_msg=f"exit code {result.returncode}")
            tracker.finish_pipeline(
                success=False,
                failed_step=step,
                failed_step_name=label,
                error_msg=f"Step {step} '{label}' failed with exit code {result.returncode}",
            )
            tracker.close()
        # Email the failure.  The tracker only records it in the database, which
        # nobody sees unless they open the Pipeline Monitor — step 13 failed six
        # nights running (19-25 Aug 2026) and went unnoticed for that reason.
        try:
            send_failure_alert(
                pipeline="daily",
                step=label,
                target_date=TODAY,
                exit_code=result.returncode,
            )
        except Exception as exc:                       # never mask the real failure
            log.error(f"Could not send failure alert: {exc}")
        sys.exit(result.returncode)
    log.info(f"✓  {label} done in {elapsed:.1f}s")
    if tracker and step:
        tracker.finish_step(step, success=True)


def run_optional(label: str, cmd: list[str],
                 tracker: PipelineTracker = None, step: int = None) -> None:
    """Run an optional step. Logs a warning on failure but continues."""
    if tracker and step:
        tracker.start_step(step, label)
    log.info(f"▶  {label}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=BASE_DIR)
    elapsed = time.time() - t0
    if result.returncode != 0:
        log.warning(f"⚠  {label} failed (exit {result.returncode}) after {elapsed:.1f}s — continuing")
        if tracker and step:
            tracker.finish_step(step, success=False,
                                error_msg=f"exit code {result.returncode} (optional — pipeline continues)")
    else:
        log.info(f"✓  {label} done in {elapsed:.1f}s")
        if tracker and step:
            tracker.finish_step(step, success=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def _sync_db_url() -> str:
    """The synchronous DSN, resolved the same way PipelineTracker resolves it.

    Deliberately not app.core.db.get_database_url_sync: importing the
    application from a pipeline pulls in its settings, its routes and its
    lifespan, and this process has no business constructing any of that.
    """
    import os

    url = os.environ.get("DATABASE_URL_SYNC", "")
    if not url:
        url = os.environ.get("DATABASE_URL", "").replace(
            "postgresql+asyncpg://", "postgresql://")
    if not url:
        raise SystemExit(
            "FATAL: neither DATABASE_URL_SYNC nor DATABASE_URL is set, so the "
            "canonical execution lease cannot be taken. Refusing to run the "
            "canonical driver unserialized.")
    return url


@contextmanager
def canonical_execution(tracker):
    """Hold the lease, run the canonical driver, then yield to the suffix.

    The wrapper owns the lease rather than the driver, because the driver
    exits at finalisation and the suffix reads `screener.universe` after it.
    Releasing at finalisation would let a later run's provisional rebuild
    revoke attribution while a suffix consumer was still reading — so the
    lease spans admission through the last consumer of live canonical state.

    Yields True when a publication happened. A refused or failed driver
    yields False and the suffix does not run: those consumers read the
    published universe, and there is nothing newly published to read.

    Failure semantics, per docs/canonical_orchestration.md:

        lease timeout        prior run keeps serving, freshness may degrade
        admission refused    no run created, nothing rebuilt, prior serves
        producer failure     prior run keeps serving
        tail failure         new rows unattributed, governed surface fails closed
        finalisation         new run is authoritative
    """
    import psycopg2

    import os

    from compute.engine.canonical_lease import (
        LEASE_HELD_ENV, SCHEDULED_WAIT_SECONDS, LeaseUnavailable,
        canonical_lease,
    )

    conn = psycopg2.connect(_sync_db_url())
    conn.autocommit = True
    try:
        with canonical_lease(conn, wait_seconds=SCHEDULED_WAIT_SECONDS,
                             why="daily_pipeline"):
            log.info("── canonical execution: DAILY_CANONICAL ──")
            result = subprocess.run([
                PYTHON, str(BASE_DIR / "scripts" / "p0a_canonical_run.py"),
                "--plan", "DAILY_CANONICAL", "--execute", "--allow-production",
            ])
            published = result.returncode == 0
            if published:
                tracker.finish_step(5, success=True)
            else:
                # Not a pipeline crash. The driver's own failure semantics
                # decide what state the database is in, and every one of them
                # leaves something coherent serving. The wrapper records the
                # outcome and lets the suffix be skipped.
                log.error("canonical driver exited %d — no publication this "
                          "cycle; see its log for which boundary it stopped "
                          "at", result.returncode)
                tracker.finish_step(5, success=False,
                                    error=f"canonical driver exit "
                                          f"{result.returncode}")
            # The suffix runs inside this lease. Tell it so, or its own
            # auxiliary_lease would block on the lock this process holds.
            os.environ[LEASE_HELD_ENV] = "daily_pipeline"
            try:
                yield published
            finally:
                os.environ.pop(LEASE_HELD_ENV, None)
    except LeaseUnavailable as exc:
        # Another canonical execution is in flight. The previously finalised
        # output keeps serving; this cycle simply does not publish.
        log.error("%s", exc)
        tracker.finish_step(5, success=False, error=str(exc)[:400])
        yield False
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip steps 1-2 (raw downloads) — use existing files")
    args = parser.parse_args()

    DIVIDER = "─" * 60
    log.info(DIVIDER)
    log.info(f"ASX Screener — Daily Pipeline — {TODAY}")
    log.info(DIVIDER)
    t_start = time.time()

    # ── Initialise pipeline tracker ───────────────────────────────────────────
    tracker = PipelineTracker()
    tracker.connect()
    tracker.start_pipeline(TODAY, total_steps=15)

    # ── Step 1: Download EOD prices (per-stock from yesterday) ────────────────
    # Uses historical per-stock endpoint — bulk endpoint not available on this tier.
    # --from-date yesterday covers Mon (gets Fri+Mon) and all weekdays correctly.
    if not args.skip_download:
        run("Step 1: Download EOD prices", [
            PYTHON, str(SCRIPTS / "download_eod_prices.py"),
            "--mode", "historical",
            "--from-date", YESTERDAY,
        ], tracker=tracker, step=1)
    else:
        log.info("Step 1: Skipped (--skip-download)")
        tracker.skip_step(1, "Step 1: Download EOD prices")

    # ── Step 2: Download ASIC short positions (non-fatal — page is JS-rendered) ─
    # ASIC publishes with ~2-3 business day lag; idempotent if already cached.
    # Step is optional: a scraping failure must not block prices/compute/universe.
    if not args.skip_download:
        run_optional("Step 2: Download ASIC short positions", [
            PYTHON, str(ASIC / "download_short_positions.py"),
        ], tracker=tracker, step=2)
    else:
        log.info("Step 2: Skipped (--skip-download)")
        tracker.skip_step(2, "Step 2: Download ASIC short positions")

    # ── Step 3: Load today's price files → staging_au (UPSERT, no truncate) ──
    run("Step 3: Load prices → staging_au", [
        PYTHON, str(SCRIPTS / "load_to_staging_prices.py"),
        "--mode", "historical",
        "--date", TODAY,
    ], tracker=tracker, step=3)

    # ── Step 4: Load + transform short positions (non-fatal) ─────────────────
    run_optional("Step 4: Load short positions → staging_au", [
        PYTHON, str(ASIC / "load_to_staging_short.py"),
    ], tracker=tracker, step=4)

    # ── Step 6: Transform short positions (non-fatal) ────────────────────────
    #
    # Moved ahead of the canonical block, where it belongs. It writes
    # market.short_positions, a canonical INPUT, so it is PRE_INGESTION and
    # must complete before admission — not run between two compute stages
    # while the driver is reading the table it is writing.
    run_optional("Step 6: Transform short positions → market.short_positions", [
        PYTHON, str(ASIC / "transforms" / "transform_short.py"),
    ], tracker=tracker, step=6)

    # ═══ INGESTION BARRIER ═══════════════════════════════════════════════════
    #
    # Everything above fills source and staging state. Everything below can
    # determine one of the 72 governed values, and belongs to the canonical
    # driver under the execution lease.
    #
    # Steps 5, 7, 8, 9, 10 and 13 used to run here as six separate commands
    # and are now ONE driver invocation, because they are exactly
    # DAILY_CANONICAL's stages: transform_prices, daily_compute,
    # technical_compute, halfyearly_compute, period_metrics_compute,
    # universe_build, then the canonical tail. Running them here AND in the
    # driver would compute everything twice; running them only here is what
    # left the contract revoked every morning with nothing to re-establish it.
    #
    # The driver owns admission. Its plan preconditions — including the yearly
    # reuse fingerprint — are evaluated AFTER the lease is acquired and BEFORE
    # any derived mutation, so a refusal leaves yesterday's validated snapshot
    # intact rather than creating today's unattributed universe.
    for step, name in ((5, "Step 5: Transform prices"),
                       (7, "Step 7: Daily compute"),
                       (8, "Step 8: Technical compute"),
                       (9, "Step 9: Half-yearly compute"),
                       (10, "Step 10: Period metrics"),
                       (13, "Step 13: Build screener.universe")):
        tracker.skip_step(step, f"{name} — executed by the canonical driver")

    # ── Step 11: ASX index prices (Yahoo Finance) ─────────────────────────────
    # Skipped — APScheduler handles this at 5:30 PM (non-core screener data)
    log.info("Step 11: Skipped (handled by APScheduler at 5:30 PM)")
    tracker.skip_step(11, "Step 11: ASX index prices")

    # ── Step 12: ETF & fund prices (Yahoo Finance) ────────────────────────────
    # Skipped — APScheduler handles this at 5:35 PM (non-core screener data)
    log.info("Step 12: Skipped (handled by APScheduler at 5:35 PM)")
    tracker.skip_step(12, "Step 12: ETF & fund prices")

    with canonical_execution(tracker) as published:
        # ── Step 14: Heatmap cache — POST_PUBLICATION suffix ─────────────────
        #
        # Inside the lease and conditional on finalisation. It reads
        # screener.universe, so releasing the lease at finalisation would let
        # a later run's provisional rebuild revoke attribution underneath it
        # and leave this reading un-attributed state.
        #
        # Non-fatal by design: once finalisation succeeds the publication is
        # authoritative, and a downstream consumer failing must not
        # retroactively invalidate it. It reports its own health instead.
        if published:
            run_optional("Step 14: Heatmap cache → market.heatmap_cache", [
                PYTHON, str(COMPUTE / "heatmap_compute.py"),
            ], tracker=tracker, step=14)
        else:
            tracker.skip_step(14, "Step 14: Heatmap cache — no publication")

    # ── Step 15: Market snapshots (runs after universe rebuild) ───────────────
    # Skipped — APScheduler handles this at 6:45 PM (admin dashboard only, non-core)
    log.info("Step 15: Skipped (handled by APScheduler at 6:45 PM)")
    tracker.skip_step(15, "Step 15: Market snapshots")

    # ── Mark pipeline as successful ───────────────────────────────────────────
    tracker.finish_pipeline(success=True)
    tracker.close()

    elapsed = time.time() - t_start
    log.info(DIVIDER)
    log.info(f"Daily pipeline complete in {elapsed / 60:.1f} min")
    log.info(DIVIDER)


if __name__ == "__main__":
    main()
