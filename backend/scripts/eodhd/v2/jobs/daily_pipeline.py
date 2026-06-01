"""
Daily Pipeline — ASX Screener
==============================
Runs after ASX market close each weekday (08:30 UTC = 18:30 AEST).

Steps:
  1.  Download today's EOD prices (per-stock, from yesterday) → Raw Zone
  2.  Download ASIC short positions                           → Raw Zone
  3.  Load prices → staging_au.eod_prices                    (today's files, UPSERT)
  4.  Load short positions → staging_au.short_positions
  5.  Transform prices → market.daily_prices                  (from yesterday)
  6.  Transform short positions → market.short_positions
  7.  Daily compute engine → market.computed_metrics
  8.  Technical compute engine → market.daily_metrics
  9.  Half-yearly compute engine → market.halfyearly_metrics
  10. Period metrics compute engine → market.period_metrics
  11. [SKIPPED] ASX index prices → market.index_prices        (APScheduler handles at 5:30 PM)
  12. [SKIPPED] ETF & fund prices → market.fund_prices        (APScheduler handles at 5:35 PM)
  13. Build screener.universe → Golden Record
  14. [SKIPPED] Market snapshots → snapshots                  (APScheduler handles at 6:45 PM)

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
from datetime import date, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_DIR  = Path(__file__).resolve().parents[4]   # /opt/asx-screener
SCRIPTS   = BASE_DIR / "scripts" / "eodhd" / "v2"
ASIC      = BASE_DIR / "scripts" / "asic"
# Prefer backend/compute/engine (canonical source); fall back to root-level compute/engine
# if the server uses a symlink or flat deployment without the backend/ prefix.
_compute_canonical = BASE_DIR / "backend" / "compute" / "engine"
_compute_fallback  = BASE_DIR / "compute" / "engine"
COMPUTE   = _compute_canonical if _compute_canonical.exists() else _compute_fallback
PYTHON    = sys.executable
TODAY     = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


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
    tracker.start_pipeline(TODAY, total_steps=14)

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
        "--run-date", TODAY,
    ], tracker=tracker, step=3)

    # ── Step 4: Load + transform short positions (non-fatal) ─────────────────
    run_optional("Step 4: Load short positions → staging_au", [
        PYTHON, str(ASIC / "load_to_staging_short.py"),
    ], tracker=tracker, step=4)

    # ── Step 5: Transform prices → market.daily_prices ───────────────────────
    run("Step 5: Transform prices → market.daily_prices", [
        PYTHON, str(SCRIPTS / "transforms" / "transform_prices.py"),
        "--from-date", YESTERDAY,
    ], tracker=tracker, step=5)

    # ── Step 6: Transform short positions (non-fatal) ────────────────────────
    run_optional("Step 6: Transform short positions → market.short_positions", [
        PYTHON, str(ASIC / "transforms" / "transform_short.py"),
    ], tracker=tracker, step=6)

    # ── Step 7: Daily compute engine ──────────────────────────────────────────
    run("Step 7: Daily compute → market.computed_metrics", [
        PYTHON, str(COMPUTE / "daily_compute.py"),
    ], tracker=tracker, step=7)

    # ── Step 8: Technical compute engine ──────────────────────────────────────
    run("Step 8: Technical compute → market.daily_metrics", [
        PYTHON, str(COMPUTE / "technical_compute.py"),
    ], tracker=tracker, step=8)

    # ── Step 9: Half-yearly compute ───────────────────────────────────────────
    run("Step 9: Half-yearly compute → market.halfyearly_metrics", [
        PYTHON, str(COMPUTE / "halfyearly_compute.py"),
    ], tracker=tracker, step=9)

    # ── Step 10: Period metrics ────────────────────────────────────────────────
    run("Step 10: Period metrics → market.period_metrics", [
        PYTHON, str(COMPUTE / "period_metrics_compute.py"),
    ], tracker=tracker, step=10)

    # ── Step 11: ASX index prices (Yahoo Finance) ─────────────────────────────
    # Skipped — APScheduler handles this at 5:30 PM (non-core screener data)
    log.info("Step 11: Skipped (handled by APScheduler at 5:30 PM)")
    tracker.skip_step(11, "Step 11: ASX index prices")

    # ── Step 12: ETF & fund prices (Yahoo Finance) ────────────────────────────
    # Skipped — APScheduler handles this at 5:35 PM (non-core screener data)
    log.info("Step 12: Skipped (handled by APScheduler at 5:35 PM)")
    tracker.skip_step(12, "Step 12: ETF & fund prices")

    # ── Step 13: Build screener.universe ──────────────────────────────────────
    run("Step 13: Build screener.universe", [
        PYTHON, str(SCRIPTS / "build_screener_universe.py"),
    ], tracker=tracker, step=13)

    # ── Step 14: Market snapshots (runs after universe rebuild) ───────────────
    # Skipped — APScheduler handles this at 6:45 PM (admin dashboard only, non-core)
    log.info("Step 14: Skipped (handled by APScheduler at 6:45 PM)")
    tracker.skip_step(14, "Step 14: Market snapshots")

    # ── Mark pipeline as successful ───────────────────────────────────────────
    tracker.finish_pipeline(success=True)
    tracker.close()

    elapsed = time.time() - t_start
    log.info(DIVIDER)
    log.info(f"Daily pipeline complete in {elapsed / 60:.1f} min")
    log.info(DIVIDER)


if __name__ == "__main__":
    main()
