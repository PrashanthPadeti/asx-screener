"""
ASX Screener — Alert Worker
=============================
Runs every 15 minutes via APScheduler.
Checks active price / pct-change alerts against screener.universe
and fires email + SMS notifications when triggered.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.services.notification_service import send_alert_notification

log = logging.getLogger(__name__)


#: How long a delivered alert suppresses the next one, however many times the
#: threshold is crossed in between.
DAILY_CAP = timedelta(hours=23)


def decide(met: bool, was_met: bool, last_triggered_at, now,
           cap=DAILY_CAP) -> str:
    """What to do with one alert this cycle. Pure, so it can be tested.

        FIRE          the threshold was just crossed and nothing suppresses it
        SUPPRESS_EDGE the condition is met but was ALREADY met -- the crossing
                      has been reported; this is the same state, not a new event
        SUPPRESS_CAP  a genuine new crossing, but one was delivered within the
                      cap, so it is recorded and not sent
        REARM         the condition has gone false; the next crossing fires
        IDLE          not met, and was not met

    The distinction between SUPPRESS_EDGE and FIRE is the whole defect. A
    level-triggered alert answers "is CBA below $150?" every fifteen minutes.
    An edge-triggered one answers "has CBA just fallen below $150?", which is
    the question the user actually asked.
    """
    if not met:
        return "REARM" if was_met else "IDLE"
    if was_met:
        return "SUPPRESS_EDGE"
    if last_triggered_at is not None and last_triggered_at > now - cap:
        return "SUPPRESS_CAP"
    return "FIRE"


async def check_alerts() -> None:
    """Main alert-check job — called by APScheduler."""
    async with AsyncSessionLocal() as db:
        try:
            await _run_checks(db)
        except Exception as e:
            log.error(f"Alert worker error: {e}", exc_info=True)
            raise          # telemetry must observe the failure
        finally:
            # Always record execution time so Pipeline Monitor shows true last-run
            try:
                await db.execute(text("""
                    INSERT INTO meta.job_heartbeat (job_id, last_run_at, run_count)
                    VALUES ('price_alerts', NOW(), 1)
                    ON CONFLICT (job_id) DO UPDATE SET
                        last_run_at = NOW(),
                        run_count   = meta.job_heartbeat.run_count + 1
                """))
                await db.commit()
            except Exception as hb_err:
                log.debug(f"Heartbeat write failed: {hb_err}")


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
            a.condition_met,
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
        LEFT JOIN market.companies_current c ON c.asx_code = a.asx_code
        LEFT JOIN users.notification_preferences np ON np.user_id = a.user_id
        WHERE a.is_active = TRUE
    """))
    alerts = result.fetchall()

    if not alerts:
        return

    log.info(f"Evaluating {len(alerts)} active alerts")
    fired = rearmed = suppressed = 0
    now = datetime.now(timezone.utc)

    for alert in alerts:
        current_value = _get_current_value(alert)
        if current_value is None:
            # No observation. This is NOT "the condition is false": treating a
            # missing price as not-met would re-arm the alert, and the next
            # price that arrives would fire a duplicate for a crossing that
            # never happened. Leave the armed state exactly as it was.
            continue

        met = _should_fire(
            alert_type=alert.alert_type,
            threshold=float(alert.threshold_value),
            current=current_value,
        )

        action = decide(met, bool(alert.condition_met),
                        alert.last_triggered_at, now)

        if action in ("IDLE", "REARM"):
            # Re-arm. The next time the threshold is crossed, it fires again.
            if action == "REARM":
                await db.execute(text(
                    "UPDATE users.alerts SET condition_met = FALSE "
                    "WHERE id = :aid"), {"aid": alert.alert_id})
                await db.commit()
                rearmed += 1
            continue

        # ── The condition is met ──────────────────────────────────────────
        # EDGE, not level. An alert is a statement about a crossing, not about
        # a state: "tell me when CBA falls below $150" is answered once when it
        # falls. Level-triggering is what sent one user 52 emails on 1 Oct 2026
        # and 29 more on 2 Oct -- one per check cycle, for fourteen hours,
        # while the price simply stayed where it was.
        if action == "SUPPRESS_EDGE":
            suppressed += 1
            continue

        # Record the crossing and COMMIT before anything leaves the building.
        #
        # The previous version sent every email inside one transaction and
        # committed after the loop, so a single failing notification rolled
        # back the throttle for every alert already processed -- while their
        # emails had already been sent. An email cannot be un-sent, so the
        # state that suppresses the next one must be durable first.
        await db.execute(text(
            "UPDATE users.alerts SET condition_met = TRUE WHERE id = :aid"),
            {"aid": alert.alert_id})
        await db.commit()

        # Daily cap, on top of the edge. Two crossings in one day send one
        # email; the second crossing is recorded but not delivered.
        if action == "SUPPRESS_CAP":
            log.info(
                f"  {alert.asx_code} {alert.alert_type} crossed again but was "
                f"last sent {alert.last_triggered_at:%Y-%m-%d %H:%M} — within "
                f"the 23h cap, not sending")
            suppressed += 1
            continue

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

        await db.commit()

        # Only now, with the suppression state durable, send.
        #
        # A failure here costs one undelivered notification. The alternative --
        # sending first -- costs an email every fifteen minutes until the price
        # moves, which is the defect being fixed.
        try:
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
        except Exception as exc:                                # noqa: BLE001
            log.error(
                f"  {alert.asx_code}: crossing recorded but notification "
                f"failed: {exc}", exc_info=True)

        fired += 1

    log.info(
        f"Alert worker complete — {fired} fired, {suppressed} suppressed, "
        f"{rearmed} re-armed, of {len(alerts)} evaluated")


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
