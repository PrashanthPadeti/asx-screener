"""
Admin Routes
============
Admin-only endpoints for platform management.
All endpoints require require_admin dependency (email in ADMIN_EMAILS list).

Endpoints:
  GET  /pipeline-status          – job health for all daily pipelines (heartbeat-based)
  POST /run-job/{job_id}         – trigger a pipeline job in the background
  GET  /pipeline/runs            – pipeline run history (last 30 days)
  GET  /pipeline/runs/{run_date} – step-level detail for a specific pipeline run
  GET  /pipeline/scheduler       – APScheduler job run history
  GET  /stats                    – platform-level summary stats
  GET  /users                    – paginated user list (search / filter)
  GET  /users/{user_id}          – full user profile + activity
  PATCH /users/{user_id}         – update plan or subscription_status
"""
import logging
import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import require_admin
from app.core.config import settings

log = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _scalar(db: AsyncSession, sql, params=None):
    """Return first column of first row, or None.

    Uses a SAVEPOINT so a query failure doesn't abort the outer transaction
    (PostgreSQL marks a transaction as aborted after any error, causing all
    subsequent statements to fail with 'InFailedSQLTransaction' until rolled
    back).  begin_nested() creates a SAVEPOINT and auto-rolls back on error,
    leaving the parent transaction intact.
    """
    try:
        async with db.begin_nested():
            result = await db.execute(text(sql), params or {})
            row = result.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _iso(val):
    """Convert datetime to ISO string, or None."""
    return val.isoformat() if val else None


# ── Pipeline Status ───────────────────────────────────────────────────────────

@router.get("/pipeline-status")
async def pipeline_status(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Returns last-run time and row count for every daily pipeline job."""

    jobs = []

    # ── Core daily pipeline (cron) ────────────────────────────────────────────

    jobs.append({
        "job": "EOD Price Download",
        "schedule": "Weekdays 6:30pm AEST",
        "type": "cron",
        "job_id": "eod_price_download",
        "last_run": await _scalar(db, "SELECT MAX(time)::date FROM market.daily_prices"),
        "row_count": await _scalar(db, """
            SELECT COUNT(*) FROM market.daily_prices
            WHERE time::date = (SELECT MAX(time)::date FROM market.daily_prices)
        """),
        "table": "market.daily_prices",
        "description": "Download bulk EOD prices from EODHD → staging → market.daily_prices",
    })

    jobs.append({
        "job": "Daily Metrics Compute",
        "schedule": "Weekdays ~6:40pm AEST",
        "type": "cron",
        "job_id": "daily_metrics",
        "last_run": await _scalar(db, "SELECT MAX(computed_at) FROM market.computed_metrics"),
        "row_count": await _scalar(db, """
            SELECT COUNT(*) FROM market.computed_metrics
            WHERE computed_at = (SELECT MAX(computed_at) FROM market.computed_metrics)
        """),
        "table": "market.computed_metrics",
        "description": "P/E, EV, returns, yield + RSI/MACD/MA technical indicators",
    })

    jobs.append({
        "job": "Universe Build",
        "schedule": "Weekdays ~6:50pm AEST",
        "type": "cron",
        "job_id": "universe_build",
        "last_run": await _scalar(db, "SELECT MAX(universe_built_at) FROM screener.universe"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE status = 'active'"),
        "table": "screener.universe",
        "description": "Golden Record rebuild — merges all metrics into screener.universe",
    })

    jobs.append({
        "job": "Weekly Fundamentals",
        "schedule": "Sunday 10pm + Monday 7am AEST",
        "type": "cron",
        "job_id": "weekly_fundamentals",
        "last_run": await _scalar(db, """
            SELECT MAX(universe_built_at) FROM screener.universe
            WHERE pe_ratio IS NOT NULL OR revenue_ttm IS NOT NULL
        """),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE pe_ratio IS NOT NULL"),
        "table": "screener.universe (fundamentals)",
        "description": "Download fundamentals, yearly/half-yearly/weekly metrics + universe rebuild",
    })

    jobs.append({
        "job": "ASX Index Prices",
        "schedule": "Daily 5:30pm AEST",
        "type": "apscheduler",
        "job_id": "index_prices",
        "last_run": await _scalar(db, "SELECT last_run_at FROM meta.job_heartbeat WHERE job_id = 'index_prices'"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.index_prices WHERE price_date = (SELECT MAX(price_date) FROM market.index_prices)"),
        "table": "market.index_prices",
        "description": "ASX 200/300 and sector index OHLCV",
    })

    jobs.append({
        "job": "ETF / Fund Prices",
        "schedule": "Daily 5:35pm AEST",
        "type": "apscheduler",
        "job_id": "fund_prices",
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.fund_prices"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.fund_prices WHERE price_date = (SELECT MAX(price_date) FROM market.fund_prices)"),
        "table": "market.fund_prices",
        "description": "ASX ETF and managed fund daily prices",
    })

    jobs.append({
        "job": "Global Markets",
        "schedule": "Daily 5:40pm AEST",
        "type": "apscheduler",
        "job_id": "global_markets",
        "last_run": await _scalar(db, "SELECT last_run_at FROM meta.job_heartbeat WHERE job_id = 'global_markets'"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.global_index_prices WHERE price_date = (SELECT MAX(price_date) FROM market.global_index_prices)"),
        "table": "market.global_index_prices",
        "description": "S&P500, FTSE, Nikkei etc + AUD FX rates",
    })

    jobs.append({
        "job": "Commodities",
        "schedule": "Daily 5:45pm AEST",
        "type": "apscheduler",
        "job_id": "commodities",
        "last_run": await _scalar(db, "SELECT last_run_at FROM meta.job_heartbeat WHERE job_id = 'commodities'"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.commodity_prices WHERE price_date = (SELECT MAX(price_date) FROM market.commodity_prices)"),
        "table": "market.commodity_prices",
        "description": "Gold, silver, oil, copper commodity prices",
    })

    jobs.append({
        "job": "ASX Index Flags",
        "schedule": "Daily 5:50pm AEST",
        "type": "apscheduler",
        "job_id": "asx_index_flags",
        "last_run": await _scalar(db, "SELECT last_run_at FROM meta.job_heartbeat WHERE job_id = 'asx_index_flags'"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE is_asx200 = TRUE"),
        "table": "screener.universe (is_asx200/300)",
        "description": "Mark ASX 200/300 constituent flags by market cap",
    })

    jobs.append({
        "job": "ASIC Short Positions",
        "schedule": "Daily 6:30pm AEST",
        "type": "apscheduler",
        "job_id": "short_positions",
        "last_run": await _scalar(db, "SELECT last_run_at FROM meta.job_heartbeat WHERE job_id = 'short_positions'"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE short_pct > 0"),
        "table": "market.short_positions",
        "description": "ASIC daily short interest data (JS-rendered — currently 0 rows)",
    })

    jobs.append({
        "job": "Market Snapshot",
        "schedule": "Daily 6:45pm AEST",
        "type": "apscheduler",
        "job_id": "market_snapshot",
        "last_run": await _scalar(db, "SELECT last_run_at FROM meta.job_heartbeat WHERE job_id = 'market_snapshot'"),
        "row_count": await _scalar(db, """
            SELECT COUNT(*) FROM market.mover_snapshots
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM market.mover_snapshots)
        """),
        "table": "market.index_snapshots + mover_snapshots",
        "description": "ASX200/300 stats, top movers, heavy buying/selling, ex-div",
    })

    jobs.append({
        "job": "Anomaly Detection",
        "schedule": "Daily 7:00pm AEST",
        "type": "apscheduler",
        "job_id": "anomaly_detection",
        "last_run": await _scalar(db, "SELECT MAX(detected_at) FROM market.anomalies WHERE is_active = TRUE"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.anomalies WHERE is_active = TRUE"),
        "table": "market.anomalies",
        "description": "7 anomaly flag types across ASX universe",
    })

    jobs.append({
        "job": "ASX Announcements",
        "schedule": "Every 10 minutes",
        "type": "interval",
        "job_id": "asx_announcements",
        "last_run": await _scalar(db, "SELECT last_run_at FROM meta.job_heartbeat WHERE job_id = 'asx_announcements'"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.asx_announcements"),
        "table": "market.asx_announcements",
        "description": "ASX company announcements from EODHD",
    })

    jobs.append({
        "job": "Price Alerts",
        "schedule": "Every 15 minutes",
        "type": "interval",
        "job_id": "price_alerts",
        "last_run": await _scalar(db, """
            SELECT last_run_at FROM meta.job_heartbeat WHERE job_id = 'price_alerts'
        """),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM users.alerts WHERE is_active = TRUE"),
        "table": "users.alerts",
        "description": "Price/pct-change alerts → email + SMS",
    })

    jobs.append({
        "job": "ML Price Predictions",
        "schedule": "Weekdays 9:00pm AEST",
        "type": "cron",
        "job_id": "price_predictions",
        "last_run": await _scalar(db, """
            SELECT MAX(created_at) FROM market.price_predictions
            WHERE model = 'ensemble'
        """),
        "row_count": await _scalar(db, """
            SELECT COUNT(DISTINCT asx_code) FROM market.price_predictions
            WHERE prediction_date = (SELECT MAX(prediction_date) FROM market.price_predictions)
              AND model = 'ensemble'
        """),
        "table": "market.price_predictions",
        "description": "XGBoost · RF · SVM · LSTM ensemble ML forecasts for top 1,000 ASX stocks",
    })

    for j in jobs:
        if j.get("last_run") and hasattr(j["last_run"], "isoformat"):
            j["last_run"] = j["last_run"].isoformat()
        if j.get("row_count") is not None:
            j["row_count"] = int(j["row_count"])

    return {"jobs": jobs, "total": len(jobs)}


# ── Run Job Now ───────────────────────────────────────────────────────────────

# Maps job_id → async callable (import deferred to avoid circular imports)
async def _run_job(job_id: str) -> None:
    """Background task dispatcher — calls the appropriate worker function."""
    from datetime import date
    try:
        if job_id == "index_prices":
            from app.workers.index_prices_worker import compute_index_prices
            await compute_index_prices()

        elif job_id == "fund_prices":
            from compute.engine.fund_prices import run
            await run(target_date=date.today(), backfill_days=3)

        elif job_id == "global_markets":
            from app.workers.global_markets_worker import compute_global_markets
            await compute_global_markets()

        elif job_id == "commodities":
            from app.workers.commodities_worker import compute_commodities
            await compute_commodities()

        elif job_id == "market_snapshot":
            from app.workers.market_snapshot_worker import run_market_snapshot
            await run_market_snapshot()

        elif job_id == "anomaly_detection":
            from app.workers.anomaly_worker import run_anomaly_detect
            await run_anomaly_detect()

        elif job_id == "asx_announcements":
            from app.workers.announcement_worker import fetch_announcements
            await fetch_announcements()

        elif job_id == "price_alerts":
            from app.workers.alert_worker import check_alerts
            await check_alerts()

        elif job_id == "asx_index_flags":
            from app.workers.asx_indices_worker import run_asx_indices
            await run_asx_indices()

        elif job_id == "short_positions":
            from app.workers.short_positions_worker import run_short_positions
            await run_short_positions()

        elif job_id in ("universe_build", "weekly_fundamentals"):
            log.warning(f"Job '{job_id}' is a heavy cron job — trigger via server CLI, not this endpoint.")
            return

        else:
            log.warning(f"run-job: unknown job_id '{job_id}'")
            return

        log.info(f"run-job: '{job_id}' completed successfully")
    except Exception as exc:
        log.error(f"run-job: '{job_id}' failed — {exc}", exc_info=True)


RUNNABLE_JOBS = {
    "index_prices", "fund_prices", "global_markets", "commodities",
    "market_snapshot", "anomaly_detection", "asx_announcements",
    "price_alerts", "asx_index_flags", "short_positions",
}


@router.post("/run-job/{job_id}")
async def trigger_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_admin),
):
    """
    Trigger a pipeline job immediately in the background.
    Returns instantly — check pipeline-status after ~30s to see the result.
    """
    if job_id in ("universe_build", "weekly_fundamentals"):
        raise HTTPException(
            status_code=400,
            detail="Universe Build and Weekly Fundamentals are heavy cron jobs. Run via server CLI: python -m compute.pipeline.daily_pipeline",
        )
    if job_id not in RUNNABLE_JOBS:
        raise HTTPException(status_code=404, detail=f"Unknown job '{job_id}'")

    background_tasks.add_task(_run_job, job_id)
    log.info(f"Admin triggered job: '{job_id}' (by {admin.get('email', 'unknown')})")
    return {"status": "started", "job_id": job_id, "message": f"Job '{job_id}' is running in the background. Refresh pipeline status in ~30 seconds."}


# ── Pipeline Run History ──────────────────────────────────────────────────────

@router.get("/pipeline/runs")
async def pipeline_run_history(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Returns the last N days of daily pipeline run history.
    Each row includes overall status, step counts, duration, and failure info.
    """
    result = await db.execute(text("""
        SELECT
            id, run_date, pipeline_name,
            started_at, completed_at, status,
            total_steps, steps_completed,
            failed_step, failed_step_name, error_message,
            duration_seconds
        FROM market.pipeline_runs
        WHERE run_date >= CURRENT_DATE - :days * INTERVAL '1 day'
        ORDER BY run_date DESC, started_at DESC
    """), {"days": days})

    rows = result.fetchall()
    runs = []
    for r in rows:
        runs.append({
            "id":               r.id,
            "run_date":         r.run_date.isoformat() if r.run_date else None,
            "pipeline_name":    r.pipeline_name,
            "started_at":       _iso(r.started_at),
            "completed_at":     _iso(r.completed_at),
            "status":           r.status,
            "total_steps":      r.total_steps,
            "steps_completed":  r.steps_completed,
            "failed_step":      r.failed_step,
            "failed_step_name": r.failed_step_name,
            "error_message":    r.error_message,
            "duration_seconds": r.duration_seconds,
            "duration_fmt":     _fmt_duration(r.duration_seconds),
        })

    return {"runs": runs, "total": len(runs)}


@router.get("/pipeline/runs/{run_date}")
async def pipeline_run_detail(
    run_date: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Returns the full step-by-step detail for a specific pipeline run date.
    Includes the overall run record plus all 14 step rows.
    """
    # Overall run
    run_result = await db.execute(text("""
        SELECT
            id, run_date, pipeline_name,
            started_at, completed_at, status,
            total_steps, steps_completed,
            failed_step, failed_step_name, error_message,
            duration_seconds
        FROM market.pipeline_runs
        WHERE run_date = :run_date
          AND pipeline_name = 'daily'
        ORDER BY started_at DESC
        LIMIT 1
    """), {"run_date": run_date})

    run_row = run_result.fetchone()
    if not run_row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No pipeline run found for {run_date}")

    # Steps
    steps_result = await db.execute(text("""
        SELECT
            step_number, step_name,
            started_at, completed_at, status,
            duration_seconds, error_message
        FROM market.pipeline_step_runs
        WHERE run_id = :run_id
        ORDER BY step_number
    """), {"run_id": run_row.id})

    steps = []
    for s in steps_result.fetchall():
        steps.append({
            "step_number":      s.step_number,
            "step_name":        s.step_name,
            "started_at":       _iso(s.started_at),
            "completed_at":     _iso(s.completed_at),
            "status":           s.status,
            "duration_seconds": float(s.duration_seconds) if s.duration_seconds else None,
            "duration_fmt":     _fmt_duration(s.duration_seconds),
            "error_message":    s.error_message,
        })

    return {
        "run": {
            "id":               run_row.id,
            "run_date":         run_row.run_date.isoformat(),
            "pipeline_name":    run_row.pipeline_name,
            "started_at":       _iso(run_row.started_at),
            "completed_at":     _iso(run_row.completed_at),
            "status":           run_row.status,
            "total_steps":      run_row.total_steps,
            "steps_completed":  run_row.steps_completed,
            "failed_step":      run_row.failed_step,
            "failed_step_name": run_row.failed_step_name,
            "error_message":    run_row.error_message,
            "duration_seconds": run_row.duration_seconds,
            "duration_fmt":     _fmt_duration(run_row.duration_seconds),
        },
        "steps": steps,
    }


@router.get("/pipeline/scheduler")
async def scheduler_job_history(
    days: int = Query(14, ge=1, le=60),
    job_id: str = Query("", description="Filter by job_id"),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Returns APScheduler job run history for the last N days.
    Optionally filter by job_id.
    """
    where_parts = ["run_date >= CURRENT_DATE - :days * INTERVAL '1 day'"]
    params: dict = {"days": days}

    if job_id:
        where_parts.append("job_id = :job_id")
        params["job_id"] = job_id

    where_sql = " AND ".join(where_parts)

    result = await db.execute(text(f"""
        SELECT
            id, run_date, job_id, job_name,
            started_at, completed_at, status,
            duration_seconds, skip_reason, error_message
        FROM market.scheduler_job_runs
        WHERE {where_sql}
        ORDER BY started_at DESC
        LIMIT 500
    """), params)

    rows = result.fetchall()
    jobs_out = []
    for r in rows:
        jobs_out.append({
            "id":               r.id,
            "run_date":         r.run_date.isoformat() if r.run_date else None,
            "job_id":           r.job_id,
            "job_name":         r.job_name,
            "started_at":       _iso(r.started_at),
            "completed_at":     _iso(r.completed_at),
            "status":           r.status,
            "duration_seconds": float(r.duration_seconds) if r.duration_seconds else None,
            "duration_fmt":     _fmt_duration(r.duration_seconds),
            "skip_reason":      r.skip_reason,
            "error_message":    r.error_message,
        })

    # Summary counts by job
    summary_result = await db.execute(text(f"""
        SELECT job_id, job_name,
               COUNT(*) FILTER (WHERE status = 'success') AS success_count,
               COUNT(*) FILTER (WHERE status = 'failed')  AS failed_count,
               COUNT(*) FILTER (WHERE status = 'skipped') AS skipped_count,
               MAX(started_at) FILTER (WHERE status = 'success') AS last_success,
               ROUND(AVG(duration_seconds) FILTER (WHERE status = 'success'), 1) AS avg_duration
        FROM market.scheduler_job_runs
        WHERE {where_sql}
        GROUP BY job_id, job_name
        ORDER BY job_name
    """), params)

    summary = []
    for r in summary_result.fetchall():
        summary.append({
            "job_id":        r.job_id,
            "job_name":      r.job_name,
            "success_count": int(r.success_count or 0),
            "failed_count":  int(r.failed_count or 0),
            "skipped_count": int(r.skipped_count or 0),
            "last_success":  _iso(r.last_success),
            "avg_duration":  float(r.avg_duration) if r.avg_duration else None,
        })

    return {
        "runs":    jobs_out,
        "summary": summary,
        "total":   len(jobs_out),
    }


def _fmt_duration(seconds) -> str | None:
    """Format duration in seconds to human-readable string."""
    if seconds is None:
        return None
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


# ── Platform Stats ────────────────────────────────────────────────────────────

@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Platform-level summary statistics."""

    # Users by plan
    result = await db.execute(text("""
        SELECT plan, COUNT(*) AS cnt
        FROM users.users
        GROUP BY plan
        ORDER BY cnt DESC
    """))
    by_plan = {row.plan: int(row.cnt) for row in result.fetchall()}
    total_users = sum(by_plan.values())

    # Subscription stats
    active_subs = int(await _scalar(db, "SELECT COUNT(*) FROM users.users WHERE subscription_status = 'active'") or 0)
    paying = int(await _scalar(db, "SELECT COUNT(*) FROM users.users WHERE plan != 'free'") or 0)

    # New signups
    new_1d  = int(await _scalar(db, "SELECT COUNT(*) FROM users.users WHERE created_at >= NOW() - INTERVAL '1 day'") or 0)
    new_7d  = int(await _scalar(db, "SELECT COUNT(*) FROM users.users WHERE created_at >= NOW() - INTERVAL '7 days'") or 0)
    new_30d = int(await _scalar(db, "SELECT COUNT(*) FROM users.users WHERE created_at >= NOW() - INTERVAL '30 days'") or 0)

    # Active users (logged in)
    active_7d  = int(await _scalar(db, "SELECT COUNT(*) FROM users.users WHERE last_login_at >= NOW() - INTERVAL '7 days'") or 0)
    active_30d = int(await _scalar(db, "SELECT COUNT(*) FROM users.users WHERE last_login_at >= NOW() - INTERVAL '30 days'") or 0)

    # Support tickets
    open_tickets = int(await _scalar(db, """
        SELECT COUNT(*) FROM support.tickets WHERE status IN ('open', 'pending')
    """) or 0)
    total_tickets = int(await _scalar(db, "SELECT COUNT(*) FROM support.tickets") or 0)

    # Platform data
    total_alerts    = int(await _scalar(db, "SELECT COUNT(*) FROM users.alerts WHERE is_active = TRUE") or 0)
    total_watchlists = int(await _scalar(db, "SELECT COUNT(*) FROM users.watchlists") or 0)
    total_portfolios = int(await _scalar(db, "SELECT COUNT(*) FROM users.portfolios") or 0)
    total_screens   = int(await _scalar(db, "SELECT COUNT(*) FROM screener.saved_screens") or 0)
    public_screens  = int(await _scalar(db, "SELECT COUNT(*) FROM screener.saved_screens WHERE is_public = TRUE") or 0)

    # Universe stats
    universe_stocks  = int(await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE status = 'active'") or 0)
    anomalies_active = int(await _scalar(db, "SELECT COUNT(*) FROM market.anomalies WHERE is_active = TRUE") or 0)

    # Comms stats (quick counts for dashboard cards)
    notifs_today    = int(await _scalar(db, "SELECT COUNT(*) FROM users.notification_history WHERE sent_at >= CURRENT_DATE AND status = 'sent'") or 0)
    notifs_7d       = int(await _scalar(db, "SELECT COUNT(*) FROM users.notification_history WHERE sent_at >= NOW() - INTERVAL '7 days' AND status = 'sent'") or 0)
    failed_24h      = int(await _scalar(db, "SELECT COUNT(*) FROM users.notification_history WHERE status = 'failed' AND (sent_at >= NOW() - INTERVAL '24 hours' OR sent_at IS NULL)") or 0)
    triggers_today  = int(await _scalar(db, "SELECT COUNT(*) FROM users.alert_triggers WHERE triggered_at >= CURRENT_DATE") or 0)
    ann_today       = int(await _scalar(db, "SELECT COUNT(*) FROM market.asx_announcements WHERE released_at >= CURRENT_DATE") or 0)
    ann_sensitive7d = int(await _scalar(db, "SELECT COUNT(*) FROM market.asx_announcements WHERE market_sensitive = TRUE AND released_at >= NOW() - INTERVAL '7 days'") or 0)

    return {
        "users": {
            "total": total_users,
            "by_plan": by_plan,
            "paying": paying,
            "active_subscriptions": active_subs,
            "new_1d": new_1d,
            "new_7d": new_7d,
            "new_30d": new_30d,
            "active_7d": active_7d,
            "active_30d": active_30d,
            "conversion_rate": round(paying / total_users * 100, 1) if total_users else 0,
        },
        "support": {
            "open_tickets": open_tickets,
            "total_tickets": total_tickets,
        },
        "platform": {
            "active_alerts": total_alerts,
            "watchlists": total_watchlists,
            "portfolios": total_portfolios,
            "saved_screens": total_screens,
            "public_screens": public_screens,
            "universe_stocks": universe_stocks,
            "active_anomalies": anomalies_active,
        },
        "comms": {
            "notifications_today":        notifs_today,
            "notifications_7d":           notifs_7d,
            "failed_24h":                 failed_24h,
            "alert_triggers_today":       triggers_today,
            "announcements_today":        ann_today,
            "announcements_sensitive_7d": ann_sensitive7d,
        },
    }


# ── Communications Centre ─────────────────────────────────────────────────────

@router.get("/comms")
async def comms_overview(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Full communications visibility:
    - Notification volume + breakdown by type/channel
    - Recent 50 outbound notifications with user info
    - Recent 50 alert trigger firings
    - Recent 30 ASX announcements (newest first, market-sensitive flagged)
    """

    # ── Volume stats ──────────────────────────────────────────────
    sent_today   = int(await _scalar(db, "SELECT COUNT(*) FROM users.notification_history WHERE sent_at >= CURRENT_DATE AND status = 'sent'") or 0)
    sent_7d      = int(await _scalar(db, "SELECT COUNT(*) FROM users.notification_history WHERE sent_at >= NOW() - INTERVAL '7 days' AND status = 'sent'") or 0)
    sent_30d     = int(await _scalar(db, "SELECT COUNT(*) FROM users.notification_history WHERE sent_at >= NOW() - INTERVAL '30 days' AND status = 'sent'") or 0)
    failed_24h   = int(await _scalar(db, "SELECT COUNT(*) FROM users.notification_history WHERE status = 'failed'") or 0)
    triggers_today = int(await _scalar(db, "SELECT COUNT(*) FROM users.alert_triggers WHERE triggered_at >= CURRENT_DATE") or 0)
    triggers_7d    = int(await _scalar(db, "SELECT COUNT(*) FROM users.alert_triggers WHERE triggered_at >= NOW() - INTERVAL '7 days'") or 0)
    ann_today      = int(await _scalar(db, "SELECT COUNT(*) FROM market.asx_announcements WHERE released_at >= CURRENT_DATE") or 0)
    ann_sensitive7d = int(await _scalar(db, "SELECT COUNT(*) FROM market.asx_announcements WHERE market_sensitive = TRUE AND released_at >= NOW() - INTERVAL '7 days'") or 0)

    # ── Breakdown by type (30d) ───────────────────────────────────
    type_rows = (await db.execute(text("""
        SELECT notification_type, COUNT(*) AS cnt
        FROM users.notification_history
        WHERE sent_at >= NOW() - INTERVAL '30 days' AND status = 'sent'
        GROUP BY notification_type ORDER BY cnt DESC
    """))).fetchall()
    by_type = {r.notification_type: int(r.cnt) for r in type_rows}

    # ── Breakdown by channel (30d) ────────────────────────────────
    chan_rows = (await db.execute(text("""
        SELECT channel, COUNT(*) AS cnt
        FROM users.notification_history
        WHERE sent_at >= NOW() - INTERVAL '30 days' AND status = 'sent'
        GROUP BY channel
    """))).fetchall()
    by_channel = {r.channel: int(r.cnt) for r in chan_rows}

    # ── Recent notifications (last 100) ──────────────────────────
    notif_rows = (await db.execute(text("""
        SELECT
            nh.notification_type, nh.channel, nh.subject,
            nh.recipient, nh.status, nh.error_message,
            nh.attempt_count, nh.sent_at,
            u.email AS user_email, u.name AS user_name, u.plan AS user_plan
        FROM users.notification_history nh
        LEFT JOIN users.users u ON u.id = nh.user_id
        ORDER BY nh.sent_at DESC NULLS LAST
        LIMIT 100
    """))).fetchall()

    notifications = [
        {
            "notification_type": r.notification_type,
            "channel":           r.channel,
            "subject":           r.subject,
            "recipient":         r.recipient,
            "status":            r.status,
            "error_message":     r.error_message,
            "attempt_count":     int(r.attempt_count or 1),
            "sent_at":           _iso(r.sent_at),
            "user_email":        r.user_email,
            "user_name":         r.user_name,
            "user_plan":         r.user_plan,
        }
        for r in notif_rows
    ]

    # ── Alert triggers (last 100) ─────────────────────────────────
    trig_rows = (await db.execute(text("""
        SELECT
            at.triggered_at, at.trigger_value, at.notification_sent,
            a.asx_code, a.alert_type, a.threshold_value, a.repeat_mode,
            u.email AS user_email, u.name AS user_name, u.plan AS user_plan,
            s.company_name
        FROM users.alert_triggers at
        JOIN  users.alerts a   ON at.alert_id = a.id
        JOIN  users.users  u   ON u.id = a.user_id
        LEFT JOIN screener.universe s ON s.asx_code = a.asx_code
        ORDER BY at.triggered_at DESC
        LIMIT 100
    """))).fetchall()

    triggers = [
        {
            "triggered_at":      _iso(r.triggered_at),
            "trigger_value":     float(r.trigger_value),
            "notification_sent": bool(r.notification_sent),
            "asx_code":          r.asx_code,
            "company_name":      r.company_name,
            "alert_type":        r.alert_type,
            "threshold_value":   float(r.threshold_value),
            "repeat_mode":       r.repeat_mode,
            "user_email":        r.user_email,
            "user_name":         r.user_name,
            "user_plan":         r.user_plan,
        }
        for r in trig_rows
    ]

    # ── Recent announcements (last 50) ────────────────────────────
    ann_rows = (await db.execute(text("""
        SELECT
            aa.asx_code, aa.title, aa.document_type,
            aa.url, aa.market_sensitive, aa.released_at,
            aa.source_type, aa.source_label,
            s.company_name,
            (
                SELECT COUNT(*) FROM users.notification_history nh
                WHERE nh.notification_type = 'announcement'
                  AND nh.status = 'sent'
                  AND nh.metadata::jsonb ->> 'asx_code' = aa.asx_code
                  AND nh.sent_at >= aa.released_at
                  AND nh.sent_at <= aa.released_at + INTERVAL '30 minutes'
            ) AS notif_sent_count
        FROM market.asx_announcements aa
        LEFT JOIN screener.universe s ON s.asx_code = aa.asx_code
        ORDER BY aa.released_at DESC
        LIMIT 50
    """))).fetchall()

    announcements = [
        {
            "asx_code":          r.asx_code,
            "company_name":      r.company_name,
            "title":             r.title,
            "document_type":     r.document_type,
            "url":               r.url,
            "market_sensitive":  bool(r.market_sensitive),
            "released_at":       _iso(r.released_at),
            "source_type":       r.source_type,
            "source_label":      r.source_label,
            "notif_sent_count":  int(r.notif_sent_count or 0),
        }
        for r in ann_rows
    ]

    return {
        "summary": {
            "notifications_today":        sent_today,
            "notifications_7d":           sent_7d,
            "notifications_30d":          sent_30d,
            "failed_24h":                 failed_24h,
            "alert_triggers_today":       triggers_today,
            "alert_triggers_7d":          triggers_7d,
            "announcements_today":        ann_today,
            "announcements_sensitive_7d": ann_sensitive7d,
        },
        "by_type":        by_type,
        "by_channel":     by_channel,
        "notifications":  notifications,
        "triggers":       triggers,
        "announcements":  announcements,
    }


# ── User Management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: str = Query(""),
    plan: str = Query(""),
    subscription_status: str = Query(""),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Paginated, searchable, filterable user list."""
    offset = (page - 1) * limit

    # Validate sort
    allowed_sort = {"created_at", "last_login_at", "email", "plan", "name"}
    if sort_by not in allowed_sort:
        sort_by = "created_at"
    sort_dir = "DESC" if sort_dir.lower() == "desc" else "ASC"

    where_parts = []
    params: dict = {"limit": limit, "offset": offset}

    if search:
        where_parts.append("(u.email ILIKE :search OR u.name ILIKE :search)")
        params["search"] = f"%{search}%"
    if plan:
        where_parts.append("u.plan = :plan")
        params["plan"] = plan
    if subscription_status:
        where_parts.append("u.subscription_status = :sub_status")
        params["sub_status"] = subscription_status

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # Total count
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM users.users u {where_sql}"),
        params,
    )
    total = int(count_result.scalar() or 0)

    # User rows (without override flag — fetched separately to be safe)
    rows_result = await db.execute(text(f"""
        SELECT
            u.id, u.email, u.name, u.plan, u.subscription_status,
            u.email_verified, u.created_at, u.last_login_at,
            u.subscription_ends_at,
            (SELECT COUNT(*) FROM users.watchlists w   WHERE w.user_id = u.id)              AS watchlist_count,
            (SELECT COUNT(*) FROM users.alerts    a    WHERE a.user_id = u.id AND a.is_active) AS alert_count,
            (SELECT COUNT(*) FROM users.portfolios p   WHERE p.user_id = u.id)              AS portfolio_count,
            (SELECT COUNT(*) FROM screener.saved_screens s WHERE s.user_id = u.id)          AS screen_count,
            (SELECT COUNT(*) FROM support.tickets t WHERE t.user_id = u.id)                 AS ticket_count,
            (SELECT ip_address FROM users.sessions si
             WHERE si.user_id = u.id ORDER BY si.created_at DESC LIMIT 1)                   AS last_ip
        FROM users.users u
        {where_sql}
        ORDER BY u.{sort_by} {sort_dir} NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params)

    # Safely fetch which users have admin overrides
    override_ids: set = set()
    try:
        tbl_check = (await db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'users' AND table_name = 'subscription_events'
            )
        """))).scalar()
        if tbl_check:
            ov_result = await db.execute(text("""
                SELECT DISTINCT user_id FROM users.subscription_events
                WHERE event_type = 'admin_override'
            """))
            override_ids = {str(r.user_id) for r in ov_result.fetchall()}
    except Exception as e:
        log.warning(f"list_users: failed to fetch override_ids: {e!r}")

    users = []
    for r in rows_result.fetchall():
        users.append({
            "id":                    str(r.id),
            "email":                 r.email,
            "name":                  r.name,
            "plan":                  r.plan,
            "subscription_status":   r.subscription_status,
            "email_verified":        r.email_verified or False,
            "created_at":            _iso(r.created_at),
            "last_login_at":         _iso(r.last_login_at),
            "subscription_ends_at":  _iso(r.subscription_ends_at),
            "watchlist_count":       int(r.watchlist_count or 0),
            "alert_count":           int(r.alert_count or 0),
            "portfolio_count":       int(r.portfolio_count or 0),
            "screen_count":          int(r.screen_count or 0),
            "ticket_count":          int(r.ticket_count or 0),
            "last_ip":               r.last_ip,
            "is_admin_override":     str(r.id) in override_ids,
        })

    return {
        "users": users,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if total else 1,
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Full user profile: activity counts, recent sessions, recent tickets."""

    result = await db.execute(text("""
        SELECT
            u.id, u.email, u.name, u.plan, u.subscription_status,
            u.email_verified, u.created_at, u.last_login_at,
            u.subscription_ends_at,
            (SELECT COUNT(*) FROM users.watchlists w    WHERE w.user_id = u.id)              AS watchlist_count,
            (SELECT COUNT(*) FROM users.alerts    a     WHERE a.user_id = u.id AND a.is_active) AS alert_count,
            (SELECT COUNT(*) FROM users.alerts    a2    WHERE a2.user_id = u.id)              AS total_alerts,
            (SELECT COUNT(*) FROM users.portfolios p    WHERE p.user_id = u.id)              AS portfolio_count,
            (SELECT COUNT(*) FROM support.tickets t WHERE t.user_id = u.id)           AS ticket_count,
            (SELECT COUNT(*) FROM screener.saved_screens s WHERE s.user_id = u.id)          AS screen_count,
            (SELECT COUNT(*) FROM screener.saved_screens s WHERE s.user_id = u.id AND s.is_public) AS public_screen_count,
            (SELECT COUNT(*) FROM users.notification_history n WHERE n.user_id = u.id)      AS notification_count
        FROM users.users u
        WHERE u.id = :uid
    """), {"uid": user_id})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    # Recent sessions (last 10)
    sessions_result = await db.execute(text("""
        SELECT ip_address, user_agent, created_at, expires_at, revoked
        FROM users.sessions
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT 10
    """), {"uid": user_id})

    sessions = [
        {
            "ip_address":  s.ip_address,
            "user_agent":  s.user_agent,
            "created_at":  _iso(s.created_at),
            "expires_at":  _iso(s.expires_at),
            "revoked":     s.revoked or False,
        }
        for s in sessions_result.fetchall()
    ]

    # Recent support tickets (last 5)
    tickets_result = await db.execute(text("""
        SELECT id, subject, status, category, created_at, updated_at
        FROM support.tickets
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT 5
    """), {"uid": user_id})

    tickets = [
        {
            "id":         str(t.id),
            "subject":    t.subject,
            "status":     t.status,
            "category":   t.category,
            "created_at": _iso(t.created_at),
            "updated_at": _iso(t.updated_at),
        }
        for t in tickets_result.fetchall()
    ]

    # Recent notification history (last 10)
    notif_result = await db.execute(text("""
        SELECT notification_type, channel, sent_at, metadata
        FROM users.notification_history
        WHERE user_id = :uid
        ORDER BY sent_at DESC
        LIMIT 10
    """), {"uid": user_id})

    notifications = [
        {
            "type":    n.notification_type,
            "channel": n.channel,
            "sent_at": _iso(n.sent_at),
        }
        for n in notif_result.fetchall()
    ]

    # Admin override history
    admin_overrides = []
    try:
        tbl_check = (await db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'users' AND table_name = 'subscription_events'
            )
        """))).scalar()
        log.info(f"get_user: subscription_events table exists={tbl_check}")
        if tbl_check:
            override_result = await db.execute(text("""
                SELECT old_plan, new_plan, stripe_event_id, created_at
                FROM users.subscription_events
                WHERE user_id = :uid AND event_type = 'admin_override'
                ORDER BY created_at DESC
                LIMIT 20
            """), {"uid": user_id})
            rows = override_result.fetchall()
            log.info(f"get_user: found {len(rows)} admin_override rows for user {user_id}")
            for o in rows:
                # stripe_event_id format: "admin:{email}|{old_status}→{new_status}"
                ref = o.stripe_event_id or ""
                admin_email   = ref.split("|")[0].replace("admin:", "") if ref.startswith("admin:") else ref
                status_change = ref.split("|")[1] if "|" in ref else None
                admin_overrides.append({
                    "old_plan":      o.old_plan,
                    "new_plan":      o.new_plan,
                    "admin_email":   admin_email,
                    "status_change": status_change,
                    "changed_at":    _iso(o.created_at),
                })
    except Exception as e:
        log.warning(f"get_user: failed to fetch admin_overrides for {user_id}: {e!r}")

    is_admin_override = len(admin_overrides) > 0

    return {
        "id":                    str(row.id),
        "email":                 row.email,
        "name":                  row.name,
        "plan":                  row.plan,
        "subscription_status":   row.subscription_status,
        "email_verified":        row.email_verified or False,
        "created_at":            _iso(row.created_at),
        "last_login_at":         _iso(row.last_login_at),
        "subscription_ends_at":  _iso(row.subscription_ends_at),
        "activity": {
            "watchlist_count":       int(row.watchlist_count or 0),
            "alert_count":           int(row.alert_count or 0),
            "total_alerts":          int(row.total_alerts or 0),
            "portfolio_count":       int(row.portfolio_count or 0),
            "ticket_count":          int(row.ticket_count or 0),
            "screen_count":          int(row.screen_count or 0),
            "public_screen_count":   int(row.public_screen_count or 0),
            "notification_count":    int(row.notification_count or 0),
        },
        "sessions":         sessions,
        "tickets":          tickets,
        "notifications":    notifications,
        "admin_overrides":  admin_overrides,
        "is_admin_override": is_admin_override,
    }


# ── Update User ───────────────────────────────────────────────────────────────

VALID_PLANS   = {"free", "pro", "premium", "enterprise_pro", "enterprise_premium"}
VALID_STATUSES = {"active", "inactive", "past_due", "cancelled", "trialing", "suspended"}


class UserUpdateBody(BaseModel):
    plan: Optional[str]                = None
    subscription_status: Optional[str] = None
    name: Optional[str]                = None


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateBody,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Update a user's plan, subscription status, or name."""

    if body.plan and body.plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Valid: {VALID_PLANS}")
    if body.subscription_status and body.subscription_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {VALID_STATUSES}")

    # Fetch current values before update so we can log what changed
    before = (await db.execute(
        text("SELECT plan, subscription_status FROM users.users WHERE id = :uid"),
        {"uid": user_id},
    )).fetchone()
    if not before:
        raise HTTPException(status_code=404, detail="User not found")

    set_parts = []
    params: dict = {"uid": user_id}

    if body.plan is not None:
        set_parts.append("plan = :plan")
        params["plan"] = body.plan
    if body.subscription_status is not None:
        set_parts.append("subscription_status = :sub_status")
        params["sub_status"] = body.subscription_status
    if body.name is not None:
        set_parts.append("name = :name")
        params["name"] = body.name

    if not set_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await db.execute(text(f"""
        UPDATE users.users
        SET {', '.join(set_parts)}
        WHERE id = :uid
        RETURNING id, email, plan, subscription_status, name
    """), params)
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    # ── Audit log ─────────────────────────────────────────────────────────────
    # Write to subscription_events whenever plan or status is manually changed
    plan_changed   = body.plan is not None and body.plan != before.plan
    status_changed = body.subscription_status is not None and body.subscription_status != before.subscription_status

    if plan_changed or status_changed:
        old_plan   = before.plan or "free"
        new_plan   = body.plan if body.plan is not None else old_plan
        old_status = before.subscription_status or "inactive"
        new_status = body.subscription_status if body.subscription_status is not None else old_status
        log.info(
            f"Admin override detected: user={user_id} "
            f"plan={old_plan}→{new_plan} status={old_status}→{new_status} by={admin['email']}"
        )
        try:
            # Use begin_nested() (SAVEPOINT) so a failure here doesn't abort
            # the outer transaction that holds the plan/status UPDATE.
            async with db.begin_nested():
                await db.execute(text("""
                    CREATE TABLE IF NOT EXISTS users.subscription_events (
                        id              BIGSERIAL PRIMARY KEY,
                        user_id         UUID        NOT NULL REFERENCES users.users(id) ON DELETE CASCADE,
                        event_type      TEXT        NOT NULL,
                        old_plan        TEXT,
                        new_plan        TEXT,
                        stripe_event_id TEXT,
                        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """))
                await db.execute(text("""
                    INSERT INTO users.subscription_events
                        (user_id, event_type, old_plan, new_plan, stripe_event_id)
                    VALUES (:uid, 'admin_override', :old_plan, :new_plan, :admin_ref)
                """), {
                    "uid":       user_id,
                    "old_plan":  old_plan,
                    "new_plan":  new_plan,
                    "admin_ref": f"admin:{admin['email']}|{old_status}→{new_status}",
                })
            log.info(
                f"Admin override audit written: user={user_id} plan={old_plan}→{new_plan} "
                f"status={old_status}→{new_status} by={admin['email']}"
            )
        except Exception as e:
            log.warning(f"Failed to write admin_override audit event: {e!r}")

    await db.commit()

    return {
        "id":                  str(row.id),
        "email":               row.email,
        "plan":                row.plan,
        "subscription_status": row.subscription_status,
        "name":                row.name,
    }


# ── Email Verification Reminders ──────────────────────────────────────────────

class VerificationReminderBody(BaseModel):
    user_ids: Optional[List[str]] = None   # None = send to ALL unverified users
    resend_cooldown_hours: int = 24         # skip users reminded within this window


@router.get("/unverified-users")
async def list_unverified_users(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Return all users whose email is not yet verified, with last-reminder timestamp.
    Used to populate the admin verification panel.
    """
    result = await db.execute(text("""
        SELECT id, email, name, plan, created_at,
               email_verification_sent_at
        FROM users.users
        WHERE email_verified = FALSE OR email_verified IS NULL
        ORDER BY created_at DESC
    """))
    users = []
    for r in result.fetchall():
        users.append({
            "id":                          str(r.id),
            "email":                       r.email,
            "name":                        r.name,
            "plan":                        r.plan,
            "created_at":                  _iso(r.created_at),
            "last_reminder_sent_at":       _iso(r.email_verification_sent_at),
        })
    return {"users": users, "total": len(users)}


@router.post("/send-verification-reminders")
async def send_verification_reminders(
    body: VerificationReminderBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Send (or re-send) email-verification reminders.
    - If body.user_ids is provided: only those users.
    - If body.user_ids is None/empty: all unverified users.
    - Skips users who already received a reminder within resend_cooldown_hours.
    Returns immediately; emails are sent in a background task.
    """
    from app.services.email import send_verification_reminder_email

    # Build the WHERE clause
    params: dict = {}
    where_parts = ["(email_verified = FALSE OR email_verified IS NULL)"]

    if body.user_ids:
        # PostgreSQL ANY with array — cast each to uuid
        where_parts.append("id = ANY(:uid_list)")
        params["uid_list"] = body.user_ids

    where_sql = " AND ".join(where_parts)

    result = await db.execute(text(f"""
        SELECT id, email, name, email_verification_sent_at
        FROM users.users
        WHERE {where_sql}
        ORDER BY created_at DESC
    """), params)
    candidates = result.fetchall()

    if not candidates:
        return {"sent": 0, "skipped": 0, "failed": 0, "message": "No unverified users found"}

    # Separate into "should send" vs "recently reminded (skip)"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=body.resend_cooldown_hours)
    to_send = []
    skipped  = 0
    for u in candidates:
        last_sent = u.email_verification_sent_at
        if last_sent:
            last_sent_aware = last_sent.replace(tzinfo=timezone.utc) if last_sent.tzinfo is None else last_sent
            if last_sent_aware > cutoff:
                skipped += 1
                continue
        to_send.append(u)

    if not to_send:
        return {
            "sent": 0, "skipped": skipped, "failed": 0,
            "message": f"All {skipped} user(s) were reminded within the last {body.resend_cooldown_hours}h — no emails sent",
        }

    # Generate tokens + update DB for all, then send in background
    frontend_url = getattr(settings, "FRONTEND_URL", "https://asxscreener.com.au")
    now = datetime.now(timezone.utc)
    user_data = []
    for u in to_send:
        tok = secrets.token_urlsafe(48)
        await db.execute(text("""
            UPDATE users.users
            SET email_verification_token   = :tok,
                email_verification_sent_at = :now
            WHERE id = :uid
        """), {"tok": tok, "uid": str(u.id), "now": now})
        verify_url = f"{frontend_url}/auth/verify-email?token={tok}"
        user_data.append((u.email, u.name, verify_url))

    await db.commit()

    log.info(
        f"Admin {admin['email']} queued {len(user_data)} verification reminder(s) "
        f"(skipped {skipped} recently reminded)"
    )

    # Send emails in background so the HTTP response is instant
    async def _send_all():
        sent = failed = 0
        for email, name, url in user_data:
            ok = send_verification_reminder_email(email, url, name)
            if ok:
                sent += 1
            else:
                failed += 1
        log.info(f"Verification reminders: sent={sent} failed={failed}")

    background_tasks.add_task(_send_all)

    return {
        "sent":    len(user_data),
        "skipped": skipped,
        "failed":  0,   # actual send results are async — check server logs
        "message": f"Sending {len(user_data)} reminder(s) in background. {skipped} skipped (recently reminded).",
    }
