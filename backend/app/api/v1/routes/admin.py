"""
Admin — Pipeline Status
=======================
Returns last-run timestamps for every daily job by querying
the actual data tables. No separate job_runs table needed.
Admin-only endpoint (checks for superuser plan).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db
from app.core.deps import require_admin

router = APIRouter()


async def _scalar(db, sql, params=None):
    """Return first column of first row, or None."""
    try:
        result = await db.execute(text(sql), params or {})
        row = result.fetchone()
        return row[0] if row else None
    except Exception:
        return None


@router.get("/pipeline-status")
async def pipeline_status(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Returns last-run time and row count for every daily pipeline job.
    Restricted to admin users via require_admin dependency.
    """

    jobs = []

    # ── Universe Build (daily pipeline) ──────────────────────────
    jobs.append({
        "job": "Universe Build",
        "schedule": "Weekdays 6:30pm AEST",
        "type": "cron",
        "last_run": await _scalar(db, "SELECT MAX(universe_built_at) FROM screener.universe"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE status = 'active'"),
        "table": "screener.universe",
        "description": "Daily EOD prices → metrics → screener.universe rebuild",
    })

    # ── Weekly Fundamentals ───────────────────────────────────────
    jobs.append({
        "job": "Weekly Fundamentals",
        "schedule": "Sunday 10pm AEST",
        "type": "cron",
        "last_run": await _scalar(db, """
            SELECT MAX(updated_at) FROM screener.universe
            WHERE pe_ratio IS NOT NULL OR revenue_ttm IS NOT NULL
        """),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE pe_ratio IS NOT NULL"),
        "table": "screener.universe (fundamentals)",
        "description": "Download + load fundamentals, rebuild full universe",
    })

    # ── ASX Index Prices (5:30pm) ─────────────────────────────────
    jobs.append({
        "job": "ASX Index Prices",
        "schedule": "Daily 5:30pm AEST",
        "type": "apscheduler",
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.indices"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.indices"),
        "table": "market.indices",
        "description": "ASX 200/300 and sector index OHLCV",
    })

    # ── ETF / Fund Prices (5:35pm) ────────────────────────────────
    jobs.append({
        "job": "ETF / Fund Prices",
        "schedule": "Daily 5:35pm AEST",
        "type": "apscheduler",
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.fund_prices"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.fund_prices WHERE price_date = (SELECT MAX(price_date) FROM market.fund_prices)"),
        "table": "market.fund_prices",
        "description": "ASX ETF and managed fund daily prices",
    })

    # ── Global Markets (5:40pm) ───────────────────────────────────
    jobs.append({
        "job": "Global Markets",
        "schedule": "Daily 5:40pm AEST",
        "type": "apscheduler",
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.global_indices"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.global_indices WHERE price_date = (SELECT MAX(price_date) FROM market.global_indices)"),
        "table": "market.global_indices",
        "description": "S&P500, FTSE, Nikkei etc + AUD FX rates",
    })

    # ── Commodities (5:45pm) ──────────────────────────────────────
    jobs.append({
        "job": "Commodities",
        "schedule": "Daily 5:45pm AEST",
        "type": "apscheduler",
        "last_run": await _scalar(db, "SELECT MAX(price_date) FROM market.commodity_prices"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.commodity_prices WHERE price_date = (SELECT MAX(price_date) FROM market.commodity_prices)"),
        "table": "market.commodity_prices",
        "description": "Gold, silver, oil, copper commodity prices",
    })

    # ── ASX Index Flags (5:50pm) ──────────────────────────────────
    jobs.append({
        "job": "ASX Index Flags",
        "schedule": "Daily 5:50pm AEST",
        "type": "apscheduler",
        "last_run": await _scalar(db, "SELECT MAX(computed_at) FROM market.asx_index_constituents") or
                    await _scalar(db, "SELECT MAX(universe_built_at) FROM screener.universe WHERE is_asx200 = TRUE"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE is_asx200 = TRUE"),
        "table": "screener.universe (is_asx200/300)",
        "description": "Mark ASX 200/300 constituent flags by market cap",
    })

    # ── ASIC Short Positions (6:30pm) ─────────────────────────────
    jobs.append({
        "job": "ASIC Short Positions",
        "schedule": "Daily 6:30pm AEST",
        "type": "apscheduler",
        "last_run": await _scalar(db, "SELECT MAX(report_date) FROM market.short_positions"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM screener.universe WHERE short_pct > 0"),
        "table": "market.short_positions",
        "description": "ASIC daily short interest data (JS-rendered — currently 0 rows)",
    })

    # ── Market Snapshot (6:45pm) ──────────────────────────────────
    jobs.append({
        "job": "Market Snapshot",
        "schedule": "Daily 6:45pm AEST",
        "type": "apscheduler",
        "last_run": await _scalar(db, "SELECT MAX(snapshot_date) FROM market.index_snapshots"),
        "row_count": await _scalar(db, """
            SELECT COUNT(*) FROM market.mover_snapshots
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM market.mover_snapshots)
        """),
        "table": "market.index_snapshots + mover_snapshots",
        "description": "ASX200/300 stats, top movers, heavy buying/selling, ex-div",
    })

    # ── Anomaly Detection (7:00pm) ────────────────────────────────
    jobs.append({
        "job": "Anomaly Detection",
        "schedule": "Daily 7:00pm AEST",
        "type": "apscheduler",
        "last_run": await _scalar(db, "SELECT MAX(detected_at) FROM market.anomalies WHERE is_active = TRUE"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.anomalies WHERE is_active = TRUE"),
        "table": "market.anomalies",
        "description": "7 anomaly flag types across ASX universe",
    })

    # ── Announcements (every 10 min) ──────────────────────────────
    jobs.append({
        "job": "ASX Announcements",
        "schedule": "Every 10 minutes",
        "type": "interval",
        "last_run": await _scalar(db, "SELECT MAX(released_at) FROM market.asx_announcements"),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM market.asx_announcements"),
        "table": "market.asx_announcements",
        "description": "ASX company announcements from EODHD",
    })

    # ── Notifications / Alerts ─────────────────────────────────────
    jobs.append({
        "job": "Price Alerts",
        "schedule": "Every 15 minutes",
        "type": "interval",
        "last_run": await _scalar(db, """
            SELECT MAX(sent_at) FROM users.notification_history
            WHERE notification_type = 'price_alert'
        """),
        "row_count": await _scalar(db, "SELECT COUNT(*) FROM users.alerts WHERE is_active = TRUE"),
        "table": "users.alerts",
        "description": "Price/pct-change alerts → email + SMS",
    })

    # Serialize datetimes
    for j in jobs:
        if j.get("last_run") and hasattr(j["last_run"], "isoformat"):
            j["last_run"] = j["last_run"].isoformat()
        if j.get("row_count") is not None:
            j["row_count"] = int(j["row_count"])

    return {"jobs": jobs, "total": len(jobs)}
