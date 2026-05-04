"""
ASX Screener — Alert Routes
==============================
GET    /alerts           — list user's alerts
POST   /alerts           — create alert
PATCH  /alerts/{id}      — toggle active/inactive
DELETE /alerts/{id}      — delete alert
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.plans import get_limits
from app.db.session import get_db
from app.schemas.alert import AlertCreate, AlertOut, AlertsResponse

log = logging.getLogger(__name__)
router = APIRouter()


# ── List alerts ───────────────────────────────────────────────────────────────

@router.get("", response_model=AlertsResponse)
async def list_alerts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT id, asx_code, alert_type, threshold_value, via_email,
                   is_active, repeat_mode, trigger_count, last_triggered_at, created_at
            FROM users.alerts
            WHERE user_id = :uid
            ORDER BY created_at DESC
        """),
        {"uid": current_user["id"]},
    )
    rows = result.fetchall()
    return AlertsResponse(alerts=[
        AlertOut(
            id=str(r.id),
            asx_code=r.asx_code,
            alert_type=r.alert_type,
            threshold_value=float(r.threshold_value),
            via_email=r.via_email,
            is_active=r.is_active,
            repeat_mode=r.repeat_mode,
            trigger_count=r.trigger_count or 0,
            last_triggered_at=r.last_triggered_at,
            created_at=r.created_at,
        )
        for r in rows
    ])


# ── Create alert ──────────────────────────────────────────────────────────────

@router.post("", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    limit = get_limits(current_user.get("plan", "free"))["alerts"]

    count_result = await db.execute(
        text("SELECT COUNT(*) FROM users.alerts WHERE user_id = :uid AND is_active = TRUE"),
        {"uid": current_user["id"]},
    )
    if (count_result.scalar() or 0) >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your plan allows a maximum of {limit} active alerts.",
        )

    result = await db.execute(
        text("""
            INSERT INTO users.alerts
                (user_id, alert_type, asx_code, threshold_value, via_email, repeat_mode)
            VALUES (:uid, :type, :code, :threshold, :email, :repeat)
            RETURNING id, asx_code, alert_type, threshold_value, via_email,
                      is_active, repeat_mode, trigger_count, last_triggered_at, created_at
        """),
        {
            "uid":       current_user["id"],
            "type":      body.alert_type,
            "code":      body.asx_code,
            "threshold": body.threshold_value,
            "email":     body.via_email,
            "repeat":    body.repeat_mode,
        },
    )
    row = result.fetchone()
    await db.commit()
    return AlertOut(
        id=str(row.id),
        asx_code=row.asx_code,
        alert_type=row.alert_type,
        threshold_value=float(row.threshold_value),
        via_email=row.via_email,
        is_active=row.is_active,
        repeat_mode=row.repeat_mode,
        trigger_count=0,
        created_at=row.created_at,
    )


# ── Toggle alert ──────────────────────────────────────────────────────────────

@router.patch("/{alert_id}", response_model=AlertOut)
async def toggle_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            UPDATE users.alerts
            SET is_active = NOT is_active
            WHERE id = :aid AND user_id = :uid
            RETURNING id, asx_code, alert_type, threshold_value, via_email,
                      is_active, repeat_mode, trigger_count, last_triggered_at, created_at
        """),
        {"aid": alert_id, "uid": current_user["id"]},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.commit()
    return AlertOut(
        id=str(row.id), asx_code=row.asx_code, alert_type=row.alert_type,
        threshold_value=float(row.threshold_value), via_email=row.via_email,
        is_active=row.is_active, repeat_mode=row.repeat_mode,
        trigger_count=row.trigger_count or 0, last_triggered_at=row.last_triggered_at,
        created_at=row.created_at,
    )


# ── Delete alert ──────────────────────────────────────────────────────────────

@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("DELETE FROM users.alerts WHERE id = :aid AND user_id = :uid RETURNING id"),
        {"aid": alert_id, "uid": current_user["id"]},
    )
    if result.fetchone() is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.commit()
