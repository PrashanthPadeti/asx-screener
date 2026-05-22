"""
ASX Screener — Alert Routes
==============================
GET    /alerts           — list user's alerts (with company_name)
GET    /alerts/search    — ASX code autocomplete (must be before /{id})
GET    /alerts/history   — triggered history    (must be before /{id})
POST   /alerts           — create alert
PATCH  /alerts/{id}      — toggle active/inactive
PUT    /alerts/{id}      — update alert fields
DELETE /alerts/{id}      — delete alert
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.plans import get_limits, PLAN_RANK
from app.db.session import get_db
from app.schemas.alert import (
    AlertCreate, AlertUpdate, AlertOut, AlertsResponse,
    AlertHistoryItem, AlertHistoryResponse, ALERT_TYPE_MIN_PLAN,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_alert_out(row, company_name: str | None = None) -> AlertOut:
    return AlertOut(
        id=str(row.id),
        asx_code=row.asx_code,
        company_name=company_name,
        alert_type=row.alert_type,
        threshold_value=float(row.threshold_value),
        via_email=row.via_email,
        is_active=row.is_active,
        repeat_mode=row.repeat_mode,
        trigger_count=row.trigger_count or 0,
        last_triggered_at=row.last_triggered_at,
        created_at=row.created_at,
    )


async def _get_company_name(db: AsyncSession, asx_code: str) -> str | None:
    r = (await db.execute(
        text("SELECT company_name FROM screener.universe WHERE asx_code = :code"),
        {"code": asx_code},
    )).fetchone()
    return r.company_name if r else None


# ── List alerts ───────────────────────────────────────────────────────────────

@router.get("", response_model=AlertsResponse)
async def list_alerts(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT a.id, a.asx_code, u.company_name,
                   a.alert_type, a.threshold_value, a.via_email,
                   a.is_active, a.repeat_mode, a.trigger_count,
                   a.last_triggered_at, a.created_at
            FROM users.alerts a
            LEFT JOIN screener.universe u ON u.asx_code = a.asx_code
            WHERE a.user_id = :uid
            ORDER BY a.created_at DESC
        """),
        {"uid": current_user["id"]},
    )
    rows = result.fetchall()
    return AlertsResponse(alerts=[
        AlertOut(
            id=str(r.id),
            asx_code=r.asx_code,
            company_name=r.company_name,
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


# ── Autocomplete search ───────────────────────────────────────────────────────
# NOTE: must be defined BEFORE /{alert_id} to avoid path conflict

@router.get("/search")
async def search_stocks(
    q: str = Query(default="", min_length=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = q.strip()
    if len(q) < 1:
        return {"results": []}
    result = await db.execute(
        text("""
            SELECT asx_code, company_name
            FROM screener.universe
            WHERE asx_code ILIKE :prefix OR company_name ILIKE :contains
            ORDER BY
                CASE WHEN asx_code ILIKE :prefix THEN 0 ELSE 1 END,
                asx_code
            LIMIT 10
        """),
        {"prefix": f"{q.upper()}%", "contains": f"%{q}%"},
    )
    rows = result.fetchall()
    return {"results": [{"asx_code": r.asx_code, "company_name": r.company_name} for r in rows]}


# ── Triggered history ─────────────────────────────────────────────────────────
# NOTE: must be defined BEFORE /{alert_id} to avoid path conflict

@router.get("/history", response_model=AlertHistoryResponse)
async def alert_history(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT
                at.alert_id,
                a.asx_code,
                u.company_name,
                a.alert_type,
                a.threshold_value,
                at.trigger_value,
                at.triggered_at,
                at.notification_sent
            FROM users.alert_triggers at
            JOIN  users.alerts a    ON at.alert_id = a.id
            LEFT JOIN screener.universe u ON u.asx_code = a.asx_code
            WHERE a.user_id = :uid
            ORDER BY at.triggered_at DESC
            LIMIT 200
        """),
        {"uid": current_user["id"]},
    )
    rows = result.fetchall()
    return AlertHistoryResponse(history=[
        AlertHistoryItem(
            alert_id=str(r.alert_id),
            asx_code=r.asx_code,
            company_name=r.company_name,
            alert_type=r.alert_type,
            threshold_value=float(r.threshold_value),
            triggered_value=float(r.trigger_value),
            triggered_at=r.triggered_at,
            notification_sent=bool(r.notification_sent),
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
    plan  = current_user.get("plan", "free")
    limit = get_limits(plan)["alerts"]

    # Enforce active-alert quota
    count = (await db.execute(
        text("SELECT COUNT(*) FROM users.alerts WHERE user_id = :uid AND is_active = TRUE"),
        {"uid": current_user["id"]},
    )).scalar() or 0
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your plan allows a maximum of {limit} active alerts.",
        )

    # Enforce alert-type plan gating
    required = ALERT_TYPE_MIN_PLAN.get(body.alert_type, "free")
    if PLAN_RANK.get(plan, 0) < PLAN_RANK.get(required, 0):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This alert type requires a {required.title()} plan or higher.",
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
    cn = await _get_company_name(db, row.asx_code)
    return _build_alert_out(row, cn)


# ── Toggle alert (pause / resume) ─────────────────────────────────────────────

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
    cn = await _get_company_name(db, row.asx_code)
    return _build_alert_out(row, cn)


# ── Update alert fields ───────────────────────────────────────────────────────

@router.put("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: str,
    body: AlertUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fields: dict = {}
    if body.asx_code        is not None: fields["asx_code"]        = body.asx_code
    if body.alert_type      is not None: fields["alert_type"]      = body.alert_type
    if body.threshold_value is not None: fields["threshold_value"] = body.threshold_value
    if body.via_email       is not None: fields["via_email"]       = body.via_email
    if body.repeat_mode     is not None: fields["repeat_mode"]     = body.repeat_mode
    if body.is_active       is not None: fields["is_active"]       = body.is_active

    if not fields:
        raise HTTPException(status_code=422, detail="No fields provided to update")

    # Plan-gate alert type changes
    if body.alert_type is not None:
        plan     = current_user.get("plan", "free")
        required = ALERT_TYPE_MIN_PLAN.get(body.alert_type, "free")
        if PLAN_RANK.get(plan, 0) < PLAN_RANK.get(required, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This alert type requires a {required.title()} plan or higher.",
            )

    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    params     = {**fields, "aid": alert_id, "uid": current_user["id"]}

    result = await db.execute(
        text(f"""
            UPDATE users.alerts
            SET {set_clause}
            WHERE id = :aid AND user_id = :uid
            RETURNING id, asx_code, alert_type, threshold_value, via_email,
                      is_active, repeat_mode, trigger_count, last_triggered_at, created_at
        """),
        params,
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.commit()
    cn = await _get_company_name(db, row.asx_code)
    return _build_alert_out(row, cn)


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
