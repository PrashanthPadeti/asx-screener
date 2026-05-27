"""
ASX Screener — Notification Routes
=====================================
GET  /notifications/preferences        — get user's notification preferences
PUT  /notifications/preferences        — update preferences
GET  /notifications/history            — get notification history (paginated)
POST /notifications/test               — send a test notification
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.deps import get_current_user
from app.db.session import get_db

log = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class NotificationPreferences(BaseModel):
    portfolio_weekly_email:    bool    = True
    portfolio_threshold_email: bool    = True
    portfolio_threshold_sms:   bool    = False
    portfolio_threshold_pct:   float   = 5.0
    alerts_email:              bool    = True
    alerts_sms:                bool    = False
    announcements_email:       bool    = False
    announcements_sms:         bool    = False
    phone_number:              Optional[str] = None
    weekly_report_day:         int     = 1
    weekly_report_hour:        int     = 8
    timezone:                  str     = "Australia/Sydney"


class NotificationHistoryItem(BaseModel):
    id:                int
    channel:           str
    notification_type: str
    subject:           Optional[str]
    recipient:         Optional[str]
    status:            str
    error_message:     Optional[str]
    attempt_count:     int
    sent_at:           Optional[str]
    created_at:        str


# ── Preferences ───────────────────────────────────────────────────────────────

@router.get("/preferences", response_model=NotificationPreferences)
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        SELECT * FROM users.notification_preferences
        WHERE user_id = :uid
    """), {"uid": current_user["id"]})
    row = result.fetchone()

    if row is None:
        return NotificationPreferences()

    return NotificationPreferences(
        portfolio_weekly_email    = row.portfolio_weekly_email,
        portfolio_threshold_email = row.portfolio_threshold_email,
        portfolio_threshold_sms   = row.portfolio_threshold_sms,
        portfolio_threshold_pct   = float(row.portfolio_threshold_pct or 5.0),
        alerts_email              = row.alerts_email,
        alerts_sms                = row.alerts_sms,
        announcements_email       = row.announcements_email,
        announcements_sms         = row.announcements_sms,
        phone_number              = row.phone_number,
        weekly_report_day         = row.weekly_report_day or 1,
        weekly_report_hour        = row.weekly_report_hour or 8,
        timezone                  = row.timezone or "Australia/Sydney",
    )


@router.put("/preferences", response_model=NotificationPreferences)
async def update_preferences(
    body: NotificationPreferences,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate threshold
    if not (0.1 <= body.portfolio_threshold_pct <= 50):
        raise HTTPException(status_code=400, detail="Threshold must be between 0.1% and 50%")

    # SMS requires phone number
    if (body.alerts_sms or body.portfolio_threshold_sms or body.announcements_sms) and not body.phone_number:
        raise HTTPException(status_code=400, detail="Phone number required to enable SMS notifications")

    await db.execute(text("""
        INSERT INTO users.notification_preferences (
            user_id,
            portfolio_weekly_email, portfolio_threshold_email,
            portfolio_threshold_sms, portfolio_threshold_pct,
            alerts_email, alerts_sms,
            announcements_email, announcements_sms,
            phone_number, weekly_report_day, weekly_report_hour, timezone,
            updated_at
        ) VALUES (
            :uid,
            :weekly_email, :threshold_email,
            :threshold_sms, :threshold_pct,
            :alerts_email, :alerts_sms,
            :ann_email, :ann_sms,
            :phone, :day, :hour, :tz,
            NOW()
        )
        ON CONFLICT (user_id) DO UPDATE SET
            portfolio_weekly_email    = EXCLUDED.portfolio_weekly_email,
            portfolio_threshold_email = EXCLUDED.portfolio_threshold_email,
            portfolio_threshold_sms   = EXCLUDED.portfolio_threshold_sms,
            portfolio_threshold_pct   = EXCLUDED.portfolio_threshold_pct,
            alerts_email              = EXCLUDED.alerts_email,
            alerts_sms                = EXCLUDED.alerts_sms,
            announcements_email       = EXCLUDED.announcements_email,
            announcements_sms         = EXCLUDED.announcements_sms,
            phone_number              = EXCLUDED.phone_number,
            weekly_report_day         = EXCLUDED.weekly_report_day,
            weekly_report_hour        = EXCLUDED.weekly_report_hour,
            timezone                  = EXCLUDED.timezone,
            updated_at                = NOW()
    """), {
        "uid":             current_user["id"],
        "weekly_email":    body.portfolio_weekly_email,
        "threshold_email": body.portfolio_threshold_email,
        "threshold_sms":   body.portfolio_threshold_sms,
        "threshold_pct":   body.portfolio_threshold_pct,
        "alerts_email":    body.alerts_email,
        "alerts_sms":      body.alerts_sms,
        "ann_email":       body.announcements_email,
        "ann_sms":         body.announcements_sms,
        "phone":           body.phone_number,
        "day":             body.weekly_report_day,
        "hour":            body.weekly_report_hour,
        "tz":              body.timezone,
    })
    await db.commit()
    return body


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/history")
async def get_history(
    channel: Optional[str] = Query(None),
    notification_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = ["user_id = :uid"]
    params: dict = {"uid": current_user["id"], "limit": limit, "offset": offset}

    if channel:
        filters.append("channel = :channel")
        params["channel"] = channel
    if notification_type:
        filters.append("notification_type = :ntype")
        params["ntype"] = notification_type

    where = " AND ".join(filters)

    result = await db.execute(text(f"""
        SELECT id, channel, notification_type, subject, recipient,
               status, error_message, attempt_count, sent_at, created_at
        FROM users.notification_history
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """), params)
    rows = result.fetchall()

    count_result = await db.execute(text(f"""
        SELECT COUNT(*) FROM users.notification_history WHERE {where}
    """), {k: v for k, v in params.items() if k not in ("limit", "offset")})
    total = count_result.scalar() or 0

    items = [
        {
            "id":                r.id,
            "channel":           r.channel,
            "notification_type": r.notification_type,
            "subject":           r.subject,
            "recipient":         _mask(r.recipient),
            "status":            r.status,
            "error_message":     r.error_message,
            "attempt_count":     r.attempt_count,
            "sent_at":           r.sent_at.isoformat() if r.sent_at else None,
            "created_at":        r.created_at.isoformat(),
        }
        for r in rows
    ]
    return {"total": total, "items": items}


# ── Test notification ─────────────────────────────────────────────────────────

# ── Unsubscribe (Spam Act 2003) ───────────────────────────────────────────────

class UnsubscribeRequest(BaseModel):
    token: str
    type:  str = "all_marketing"   # all_marketing | alerts | digest


@router.post("/unsubscribe", status_code=status.HTTP_200_OK)
async def process_unsubscribe(
    body: UnsubscribeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    One-click email unsubscribe — Spam Act 2003 (Cth) s.18.

    Processes immediately. Token is single-use (marked used after processing).
    No authentication required — token itself is the credential.
    """
    valid_types = {"all_marketing", "alerts", "digest"}
    if body.type not in valid_types:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(valid_types)}")

    # Look up the token
    result = await db.execute(text("""
        SELECT id, user_id, unsubscribe_type, used, expires_at
        FROM users.unsubscribe_tokens
        WHERE token = :tok
    """), {"tok": body.token})
    row = result.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Invalid unsubscribe link")

    if row.used:
        return {"status": "already_done", "type": row.unsubscribe_type}

    from datetime import datetime, timezone
    if row.expires_at and row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Unsubscribe link has expired — please contact support")

    # Mark token as used
    await db.execute(text("""
        UPDATE users.unsubscribe_tokens
        SET used = TRUE, used_at = NOW()
        WHERE id = :id
    """), {"id": row.id})

    # Update user preference
    col_map = {
        "all_marketing": "marketing_emails_enabled",
        "alerts":        "email_alerts_enabled",
        "digest":        "marketing_emails_enabled",  # digest falls under marketing
    }
    col = col_map[body.type]

    await db.execute(text(f"""
        UPDATE users.users SET {col} = FALSE, updated_at = NOW()
        WHERE id = :uid
    """), {"uid": str(row.user_id)})

    # Audit log
    await db.execute(text("""
        INSERT INTO users.audit_log (user_id, action, entity_type, metadata)
        VALUES (:uid, 'prefs.unsubscribed', 'user', :meta::jsonb)
    """), {
        "uid":  str(row.user_id),
        "meta": f'{{"type": "{body.type}", "channel": "email_link"}}',
    })

    await db.commit()
    log.info(f"Unsubscribe processed: user={row.user_id}, type={body.type}")
    return {"status": "success", "type": body.type}


class TestRequest(BaseModel):
    channel: str  # 'email' or 'sms'


@router.post("/test", status_code=status.HTTP_202_ACCEPTED)
async def send_test(
    body: TestRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.channel not in ("email", "sms"):
        raise HTTPException(status_code=400, detail="channel must be 'email' or 'sms'")

    # Fetch user details
    result = await db.execute(text("""
        SELECT u.email, u.name, np.phone_number
        FROM users.users u
        LEFT JOIN users.notification_preferences np ON np.user_id = u.id
        WHERE u.id = :uid
    """), {"uid": current_user["id"]})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    if body.channel == "sms":
        if not row.phone_number:
            raise HTTPException(status_code=400, detail="No phone number on file. Add one in notification preferences.")
        from app.services.sms import send_sms
        ok = send_sms(row.phone_number, "Test from ASX Screener — your SMS notifications are working! 🇦🇺")
        return {"ok": ok, "channel": "sms", "recipient": _mask(row.phone_number)}
    else:
        from app.services.notification_service import _send_raw_email
        ok = _send_raw_email(
            row.email,
            "Test notification from ASX Screener",
            "<p>Your email notifications are working correctly. 🇦🇺</p>"
        )
        return {"ok": ok, "channel": "email", "recipient": _mask(row.email)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if "@" in value:
        parts = value.split("@")
        return parts[0][:2] + "***@" + parts[1]
    # Phone
    return value[:4] + "***" + value[-2:]
