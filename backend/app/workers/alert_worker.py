"""
ASX Screener — Alert Worker
=============================
Runs every 15 minutes via APScheduler.
Checks active price / pct-change alerts against screener.universe
and fires email + SMS notifications when triggered.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.services.notification_service import send_alert_notification

log = logging.getLogger(__name__)


async def check_alerts() -> None:
    """Main alert-check job — called by APScheduler."""
    async with AsyncSessionLocal() as db:
        try:
            await _run_checks(db)
        except Exception as e:
            log.error(f"Alert worker error: {e}", exc_info=True)


async def _run_checks(db: AsyncSession) -> None:
    result = await db.execute(text("""
        SELECT
            a.id              AS alert_id,
            a.user_id,
            a.asx_code,
            a.alert_type,
            a.threshold_value,
            a.via_email,
            COALESCE(a.via_sms, FALSE)  AS via_sms,
            a.repeat_mode,
            a.last_triggered_at,
            u.email,
            u.name,
            u.plan,
            -- Prefer user prefs phone; alerts table doesn't store phone
            np.phone_number,
            s.price,
            s.return_1w       AS pct_change_1d,
            c.company_name
        FROM users.alerts a
        JOIN users.users u             ON u.id   = a.user_id
        LEFT JOIN screener.universe s  ON s.asx_code = a.asx_code
        LEFT JOIN market.companies c   ON c.asx_code = a.asx_code
        LEFT JOIN users.notification_preferences np ON np.user_id = a.user_id
        WHERE a.is_active = TRUE
          AND (a.repeat_mode = 'every_time'
               OR a.last_triggered_at IS NULL
               OR a.last_triggered_at < NOW() - INTERVAL '23 hours')
    """))
    alerts = result.fetchall()

    if not alerts:
        return

    log.info(f"Checking {len(alerts)} active alerts")
    triggered = 0

    for alert in alerts:
        current_value = _get_current_value(alert)
        if current_value is None:
            continue

        fired = _should_fire(
            alert_type=alert.alert_type,
            threshold=float(alert.threshold_value),
            current=current_value,
        )
        if not fired:
            continue

        # Record trigger
        await db.execute(text("""
            INSERT INTO users.alert_triggers
                (alert_id, triggered_at, trigger_value, notification_sent)
            VALUES (:aid, NOW(), :val, FALSE)
        """), {"aid": alert.alert_id, "val": current_value})

        await db.execute(text("""
            UPDATE users.alerts
            SET last_triggered_at = NOW(),
                trigger_count = trigger_count + 1
            WHERE id = :aid
        """), {"aid": alert.alert_id})

        if alert.repeat_mode == "once":
            await db.execute(text(
                "UPDATE users.alerts SET is_active = FALSE WHERE id = :aid"
            ), {"aid": alert.alert_id})

        # Send notifications (email + SMS) via unified service
        await send_alert_notification(
            db=db,
            user_id=str(alert.user_id),
            email=alert.email,
            phone=alert.phone_number,
            asx_code=alert.asx_code,
            alert_type=alert.alert_type,
            threshold=float(alert.threshold_value),
            current_value=current_value,
            company_name=alert.company_name,
            via_email=bool(alert.via_email),
            via_sms=bool(alert.via_sms),
        )

        triggered += 1

    await db.commit()
    log.info(f"Alert worker complete — {triggered}/{len(alerts)} fired")


def _get_current_value(alert) -> float | None:
    if "pct_change" in alert.alert_type:
        return alert.pct_change_1d
    return alert.price


def _should_fire(alert_type: str, threshold: float, current: float) -> bool:
    if alert_type == "price_above":
        return current >= threshold
    if alert_type == "price_below":
        return current <= threshold
    if alert_type == "pct_change_above":
        return current >= threshold
    if alert_type == "pct_change_below":
        return current <= threshold
    return False
