"""
Admin Routes
============
Admin-only endpoints for platform management.
All endpoints require require_admin dependency (email in ADMIN_EMAILS list).

Endpoints:
  GET  /pipeline-status          – job health for all daily pipelines
  POST /run-job/{job_id}         – trigger a pipeline job in the background
  GET  /stats                    – platform-level summary stats
  GET  /users                    – paginated user list (search / filter)
  GET  /users/{user_id}          – full user profile + activity
  PATCH /users/{user_id}         – update plan or subscription_status
"""
import logging
import math
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import require_admin

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
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.daily_prices"),
        "row_count": await _scalar(db, """
            SELECT COUNT(*) FROM market.daily_prices
            WHERE price_date = (SELECT MAX(price_date) FROM market.daily_prices)
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
            SELECT MAX(updated_at) FROM screener.universe
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
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.index_prices"),
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
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.global_index_prices"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.global_index_prices WHERE price_date = (SELECT MAX(price_date) FROM market.global_index_prices)"),
        "table": "market.global_index_prices",
        "description": "S&P500, FTSE, Nikkei etc + AUD FX rates",
    })

    jobs.append({
        "job": "Commodities",
        "schedule": "Daily 5:45pm AEST",
        "type": "apscheduler",
        "job_id": "commodities",
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.commodity_prices"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.commodity_prices WHERE price_date = (SELECT MAX(price_date) FROM market.commodity_prices)"),
        "table": "market.commodity_prices",
        "description": "Gold, silver, oil, copper commodity prices",
    })

    jobs.append({
        "job": "ASX Index Flags",
        "schedule": "Daily 5:50pm AEST",
        "type": "apscheduler",
        "job_id": "asx_index_flags",
        "last_run": await _scalar(db, "SELECT MAX(computed_at) FROM market.asx_index_constituents") or
                    await _scalar(db, "SELECT MAX(universe_built_at) FROM screener.universe WHERE is_asx200 = TRUE"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE is_asx200 = TRUE"),
        "table": "screener.universe (is_asx200/300)",
        "description": "Mark ASX 200/300 constituent flags by market cap",
    })

    jobs.append({
        "job": "ASIC Short Positions",
        "schedule": "Daily 6:30pm AEST",
        "type": "apscheduler",
        "job_id": "short_positions",
        "last_run": await _scalar(db, "SELECT MAX(report_date) FROM market.short_positions"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE short_pct > 0"),
        "table": "market.short_positions",
        "description": "ASIC daily short interest data (JS-rendered — currently 0 rows)",
    })

    jobs.append({
        "job": "Market Snapshot",
        "schedule": "Daily 6:45pm AEST",
        "type": "apscheduler",
        "job_id": "market_snapshot",
        "last_run": await _scalar(db, "SELECT MAX(snapshot_date) FROM market.index_snapshots"),
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
        "last_run": await _scalar(db, "SELECT MAX(released_at) FROM market.asx_announcements"),
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
            SELECT MAX(sent_at) FROM users.notification_history
            WHERE notification_type = 'price_alert'
        """),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM users.alerts WHERE is_active = TRUE"),
        "table": "users.alerts",
        "description": "Price/pct-change alerts → email + SMS",
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
            from compute.engine.index_prices import run
            await run(target_date=date.today(), backfill_days=3)

        elif job_id == "fund_prices":
            from compute.engine.fund_prices import run
            await run(target_date=date.today(), backfill_days=3)

        elif job_id == "global_markets":
            from compute.engine.global_markets import run
            await run(target_date=date.today(), backfill_days=3)

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
    universe_stocks = int(await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE status = 'active'") or 0)
    anomalies_active = int(await _scalar(db, "SELECT COUNT(*) FROM market.anomalies WHERE is_active = TRUE") or 0)

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

    # User rows
    rows_result = await db.execute(text(f"""
        SELECT
            u.id, u.email, u.name, u.plan, u.subscription_status,
            u.email_verified, u.created_at, u.last_login_at,
            u.subscription_ends_at,
            (SELECT COUNT(*) FROM users.watchlists w   WHERE w.user_id = u.id)              AS watchlist_count,
            (SELECT COUNT(*) FROM users.alerts    a    WHERE a.user_id = u.id AND a.is_active) AS alert_count,
            (SELECT COUNT(*) FROM users.portfolios p   WHERE p.user_id = u.id)              AS portfolio_count,
            (SELECT COUNT(*) FROM screener.saved_screens s WHERE s.user_id = u.id)          AS screen_count,
            (SELECT COUNT(*) FROM support.tickets t WHERE t.user_id = u.id)           AS ticket_count,
            (SELECT ip_address FROM users.sessions si
             WHERE si.user_id = u.id ORDER BY si.created_at DESC LIMIT 1)                   AS last_ip
        FROM users.users u
        {where_sql}
        ORDER BY u.{sort_by} {sort_dir} NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params)

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
        "sessions":       sessions,
        "tickets":        tickets,
        "notifications":  notifications,
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
    await db.commit()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id":                  str(row.id),
        "email":               row.email,
        "plan":                row.plan,
        "subscription_status": row.subscription_status,
        "name":                row.name,
    }
