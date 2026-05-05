"""
ASX Screener — Portfolio Notification Worker
=============================================
Two jobs:
  1. check_portfolio_thresholds()  — every 30 min
     Compares current portfolio value to last-notified value.
     Fires email/SMS if change exceeds user's configured threshold %.

  2. send_weekly_portfolio_summaries() — Monday 8am AEST (cron)
     Sends a full portfolio summary email to all users with weekly email enabled.
"""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.services.notification_service import (
    send_portfolio_threshold_notification,
    send_weekly_portfolio_email,
)

log = logging.getLogger(__name__)


# ── Threshold check ───────────────────────────────────────────────────────────

async def check_portfolio_thresholds() -> None:
    async with AsyncSessionLocal() as db:
        try:
            await _run_threshold_checks(db)
        except Exception as e:
            log.error(f"Portfolio threshold worker error: {e}", exc_info=True)


async def _run_threshold_checks(db) -> None:
    # Fetch all portfolios with current value + user preferences
    result = await db.execute(text("""
        SELECT
            p.id            AS portfolio_id,
            p.name          AS portfolio_name,
            p.user_id,
            u.email,
            u.name          AS user_name,
            u.plan,
            -- Current portfolio value from holdings
            COALESCE(SUM(h.quantity * s.price), 0)  AS current_value,
            -- Notification state
            pns.last_value,
            pns.last_notified_at,
            -- Preferences
            np.portfolio_threshold_email,
            np.portfolio_threshold_sms,
            np.portfolio_threshold_pct,
            np.phone_number
        FROM users.portfolios p
        JOIN users.users u            ON u.id = p.user_id
        LEFT JOIN users.holdings h    ON h.portfolio_id = p.id
        LEFT JOIN screener.universe s ON s.asx_code = h.asx_code
        LEFT JOIN users.portfolio_notification_state pns ON pns.portfolio_id = p.id
        LEFT JOIN users.notification_preferences np      ON np.user_id = p.user_id
        WHERE u.subscription_status = 'active'
          AND (np.portfolio_threshold_email = TRUE OR np.portfolio_threshold_sms = TRUE)
          -- Don't re-notify within 4 hours
          AND (pns.last_notified_at IS NULL OR pns.last_notified_at < NOW() - INTERVAL '4 hours')
        GROUP BY p.id, p.name, p.user_id, u.email, u.name, u.plan,
                 pns.last_value, pns.last_notified_at,
                 np.portfolio_threshold_email, np.portfolio_threshold_sms,
                 np.portfolio_threshold_pct, np.phone_number
    """))
    portfolios = result.fetchall()

    if not portfolios:
        return

    log.info(f"Checking thresholds for {len(portfolios)} portfolios")
    fired = 0

    for p in portfolios:
        current = float(p.current_value or 0)
        previous = float(p.last_value or current)

        if previous == 0:
            # No previous value — just record current
            await _upsert_state(db, str(p.portfolio_id), current, record_notify=False)
            continue

        threshold_pct = float(p.portfolio_threshold_pct or 5.0)
        change_pct    = ((current - previous) / previous) * 100

        if abs(change_pct) < threshold_pct:
            continue

        await send_portfolio_threshold_notification(
            db=db,
            user_id=str(p.user_id),
            email=p.email if p.portfolio_threshold_email else None,
            phone=p.phone_number if p.portfolio_threshold_sms else None,
            portfolio_name=p.portfolio_name,
            current_value=current,
            previous_value=previous,
            change_pct=change_pct,
            via_email=bool(p.portfolio_threshold_email),
            via_sms=bool(p.portfolio_threshold_sms),
        )
        await _upsert_state(db, str(p.portfolio_id), current, record_notify=True)
        fired += 1

    await db.commit()
    log.info(f"Portfolio threshold check done — {fired}/{len(portfolios)} fired")


async def _upsert_state(db, portfolio_id: str, value: float, record_notify: bool) -> None:
    await db.execute(text("""
        INSERT INTO users.portfolio_notification_state (portfolio_id, last_value, last_notified_at)
        VALUES (:pid, :val, :notified)
        ON CONFLICT (portfolio_id) DO UPDATE
          SET last_value       = :val,
              last_notified_at = CASE WHEN :notified THEN NOW()
                                      ELSE users.portfolio_notification_state.last_notified_at END
    """), {"pid": portfolio_id, "val": value, "notified": record_notify})


# ── Weekly summary ────────────────────────────────────────────────────────────

async def send_weekly_portfolio_summaries() -> None:
    async with AsyncSessionLocal() as db:
        try:
            await _run_weekly_summaries(db)
        except Exception as e:
            log.error(f"Weekly portfolio summary worker error: {e}", exc_info=True)


async def _run_weekly_summaries(db) -> None:
    # Get users due for weekly email (not sent in last 6 days)
    result = await db.execute(text("""
        SELECT DISTINCT
            u.id        AS user_id,
            u.email,
            u.name,
            u.plan,
            np.portfolio_threshold_pct
        FROM users.users u
        JOIN users.notification_preferences np ON np.user_id = u.id
        WHERE np.portfolio_weekly_email = TRUE
          AND u.subscription_status = 'active'
          AND (
            NOT EXISTS (
                SELECT 1 FROM users.portfolio_notification_state pns2
                JOIN users.portfolios p2 ON p2.id = pns2.portfolio_id
                WHERE p2.user_id = u.id
                  AND pns2.weekly_sent_at > NOW() - INTERVAL '6 days'
            )
          )
    """))
    users = result.fetchall()

    if not users:
        log.info("Weekly summaries: no users due")
        return

    log.info(f"Sending weekly summaries to {len(users)} users")

    for user in users:
        portfolios = await _get_user_portfolios(db, str(user.user_id))
        if not portfolios:
            continue

        await send_weekly_portfolio_email(
            db=db,
            user_id=str(user.user_id),
            email=user.email,
            name=user.name,
            portfolios=portfolios,
        )

        # Mark weekly_sent_at on all portfolios for this user
        await db.execute(text("""
            INSERT INTO users.portfolio_notification_state (portfolio_id, last_value, weekly_sent_at)
            SELECT p.id, COALESCE(SUM(h.quantity * s.price), 0), NOW()
            FROM users.portfolios p
            LEFT JOIN users.holdings h    ON h.portfolio_id = p.id
            LEFT JOIN screener.universe s ON s.asx_code = h.asx_code
            WHERE p.user_id = :uid
            GROUP BY p.id
            ON CONFLICT (portfolio_id) DO UPDATE
              SET weekly_sent_at = NOW()
        """), {"uid": str(user.user_id)})

    await db.commit()
    log.info(f"Weekly summaries done — {len(users)} sent")


async def _get_user_portfolios(db, user_id: str) -> list[dict]:
    result = await db.execute(text("""
        SELECT
            p.id            AS portfolio_id,
            p.name,
            COALESCE(SUM(h.quantity * s.price), 0)                         AS total_value,
            COALESCE(SUM(h.quantity * h.avg_cost), 0)                      AS total_cost,
            COALESCE(SUM(h.quantity * (s.price - h.avg_cost)), 0)          AS total_gain_loss,
            JSON_AGG(JSON_BUILD_OBJECT(
                'asx_code', h.asx_code,
                'quantity', h.quantity,
                'current_price', s.price,
                'avg_cost', h.avg_cost,
                'gain_pct', CASE WHEN h.avg_cost > 0
                                 THEN ((s.price - h.avg_cost) / h.avg_cost) * 100
                                 ELSE 0 END
            )) FILTER (WHERE h.id IS NOT NULL) AS holdings
        FROM users.portfolios p
        LEFT JOIN users.holdings h    ON h.portfolio_id = p.id
        LEFT JOIN screener.universe s ON s.asx_code = h.asx_code
        WHERE p.user_id = :uid
        GROUP BY p.id, p.name
    """), {"uid": user_id})
    rows = result.fetchall()

    portfolios = []
    for r in rows:
        cost  = float(r.total_cost or 0)
        value = float(r.total_value or 0)
        gl    = float(r.total_gain_loss or 0)
        portfolios.append({
            "name":             r.name,
            "total_value":      value,
            "total_cost":       cost,
            "total_gain_loss":  gl,
            "total_return_pct": (gl / cost * 100) if cost > 0 else 0,
            "holdings":         r.holdings or [],
        })
    return portfolios
