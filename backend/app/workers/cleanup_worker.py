"""
Cleanup Worker
==============
Scheduled maintenance tasks that run nightly:

  1. purge_expired_sessions  — delete expired/revoked rows from users.sessions
                               (prevents unbounded table growth)

  2. run_data_deletion       — call users.delete_expired_premium_data() for any
                               cancelled users whose 12-month retention window
                               has passed
"""
import logging

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

log = logging.getLogger(__name__)


async def purge_expired_sessions() -> None:
    """Delete sessions that have expired or been revoked."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                DELETE FROM users.sessions
                WHERE expires_at < NOW()
                   OR revoked = TRUE
            """))
            await db.commit()
            deleted = result.rowcount
            if deleted:
                log.info("Session cleanup: removed %d expired/revoked session(s)", deleted)
    except Exception as exc:
        log.error("Session cleanup error: %s", exc, exc_info=True)


async def run_data_deletion() -> None:
    """
    Call users.delete_expired_premium_data() for all users whose
    data_deletion_scheduled_at has passed.
    Runs nightly — safe to call repeatedly (idempotent).
    """
    try:
        async with AsyncSessionLocal() as db:
            # Find users whose deletion window has expired
            result = await db.execute(text("""
                SELECT id FROM users.users
                WHERE data_deletion_scheduled_at IS NOT NULL
                  AND data_deletion_scheduled_at <= NOW()
                  AND subscription_status IN ('cancelled', 'inactive')
            """))
            user_ids = [row[0] for row in result.fetchall()]

            if not user_ids:
                log.debug("Data deletion: no users due for cleanup")
                return

            for user_id in user_ids:
                try:
                    await db.execute(
                        text("SELECT users.delete_expired_premium_data(:uid)"),
                        {"uid": user_id},
                    )
                    log.info("Data deletion: cleaned up user %s", user_id)
                except Exception as user_exc:
                    log.error("Data deletion failed for user %s: %s", user_id, user_exc)
                    await db.rollback()
                    continue

            await db.commit()
            log.info("Data deletion complete: %d user(s) processed", len(user_ids))

    except Exception as exc:
        log.error("Data deletion worker error: %s", exc, exc_info=True)
