"""
ASX Screener — Alert Worker
=============================
Runs every 15 minutes via APScheduler.
Checks active price / pct-change alerts against screener.universe
and fires email notifications when triggered.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.services.email import send_alert_email

log = logging.getLogger(__name__)


async def check_alerts() -> None:
    """Main alert-check job — called by APScheduler."""
    async with AsyncSessionLocal() as db:
        try:
            await _run_checks(db)
        except Exception as e:
            log.error(f"Alert worker error: {e}", exc_info=True)


async def _run_checks(db: AsyncSession) -> None:
    # Fetch all active alerts with current price data
    result = await db.execute(text("""
        SELECT
            a.id              AS alert_id,
            a.user_id,
            a.asx_code,
            a.alert_type,
            a.threshold_value,
            a.via_email,
            a.repeat_mode,
            a.last_triggered_at,
            u.email,
            u.name,
            u.plan,
            -- current price metrics from screener.universe
            s.price,
            s.return_1w       AS pct_change_1d,   -- best proxy available
            c.company_name
        FROM users.alerts a
        JOIN users.users u         ON u.id   = a.user_id
        LEFT JOIN screener.universe s ON s.asx_code = a.asx_code
        LEFT JOIN market.companies c  ON c.asx_code = a.asx_code
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

        # Revoke once-only alerts
        if alert.repeat_mode == "once":
            await db.execute(text(
                "UPDATE users.alerts SET is_active = FALSE WHERE id = :aid"
            ), {"aid": alert.alert_id})

        # Send email
        if alert.via_email and alert.email:
            sent = send_alert_email(
                to_email=alert.email,
                asx_code=alert.asx_code,
                alert_type=alert.alert_type,
                threshold=float(alert.threshold_value),
                current_value=current_value,
                company_name=alert.company_name,
            )
            if sent:
                # Mark notification sent on the trigger row (best-effort)
                await db.execute(text("""
                    UPDATE users.alert_triggers
                    SET notification_sent = TRUE, notification_sent_at = NOW()
                    WHERE alert_id = :aid
                    ORDER BY triggered_at DESC
                    LIMIT 1
                """), {"aid": alert.alert_id})

        triggered += 1

    await db.commit()
    log.info(f"Alert worker complete — {triggered}/{len(alerts)} fired")


def _get_current_value(alert) -> float | None:
    """Return the metric value to compare against the threshold."""
    if "pct_change" in alert.alert_type:
        return alert.pct_change_1d   # can be None
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
