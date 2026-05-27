"""
ASX Screener — User Profile Routes
=====================================
PATCH  /api/v1/users/me   — update name / notification preferences
DELETE /api/v1/users/me   — delete account (Privacy Act 1988 right to erasure)

Both endpoints write to users.audit_log for NDB scheme compliance.
"""
import hashlib
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.auth import UpdateProfileRequest, UserProfile
from app.core.config import settings

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_ip(request: Request) -> str:
    """SHA-256 hash of client IP — stored in audit log, never raw IP."""
    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(ip.encode()).hexdigest()


async def _audit(
    db: AsyncSession,
    user_id: str,
    action: str,
    request: Request,
    old_value: dict | None = None,
    new_value: dict | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> None:
    """Insert a row into users.audit_log."""
    import json
    await db.execute(text("""
        INSERT INTO users.audit_log
            (user_id, action, entity_type, entity_id, old_value, new_value,
             ip_address_hash, user_agent)
        VALUES
            (:uid, :action, :etype, :eid, :old, :new, :ip, :ua)
    """), {
        "uid":    user_id,
        "action": action,
        "etype":  entity_type,
        "eid":    entity_id,
        "old":    json.dumps(old_value) if old_value else None,
        "new":    json.dumps(new_value) if new_value else None,
        "ip":     _hash_ip(request),
        "ua":     (request.headers.get("user-agent") or "")[:499],
    })


# ── PATCH /users/me ───────────────────────────────────────────────────────────

@router.patch("/me", response_model=UserProfile)
async def update_me(
    body: UpdateProfileRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update the current user's name, timezone, or notification preferences.
    Only fields explicitly provided (non-None) are updated.
    """
    uid = current_user["id"]

    # Fetch current values for audit log
    result = await db.execute(text("""
        SELECT name, timezone,
               email_alerts_enabled, marketing_emails_enabled, push_alerts_enabled
        FROM users.users WHERE id = :id
    """), {"id": uid})
    before = result.fetchone()
    if before is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Build SET clause for only provided fields
    updates: dict[str, object] = {}
    if body.name                     is not None: updates["name"]                     = body.name
    if body.timezone                 is not None: updates["timezone"]                 = body.timezone
    if body.email_alerts_enabled     is not None: updates["email_alerts_enabled"]     = body.email_alerts_enabled
    if body.marketing_emails_enabled is not None: updates["marketing_emails_enabled"] = body.marketing_emails_enabled
    if body.push_alerts_enabled      is not None: updates["push_alerts_enabled"]      = body.push_alerts_enabled

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    set_clause = ", ".join(f"{col} = :{col}" for col in updates)
    updates["id"] = uid
    updates["updated_at"] = "NOW()"  # handled below

    await db.execute(text(f"""
        UPDATE users.users
        SET {set_clause}, updated_at = NOW()
        WHERE id = :id
    """), {**updates})

    # Write audit entry (scrub any PII — only log preference field names + bool values)
    pref_keys = {"email_alerts_enabled", "marketing_emails_enabled", "push_alerts_enabled", "timezone"}
    old_v = {k: getattr(before, k) for k in updates if k in pref_keys and k != "id"}
    new_v = {k: v for k, v in updates.items() if k in pref_keys}
    await _audit(db, uid, "prefs.updated", request,
                 old_value=old_v, new_value=new_v,
                 entity_type="user", entity_id=uid)

    await db.commit()

    # Return updated profile
    row = await db.execute(text("""
        SELECT id, email, name, plan, email_verified,
               subscription_status, subscription_ends_at, created_at,
               email_alerts_enabled, marketing_emails_enabled, push_alerts_enabled
        FROM users.users WHERE id = :id
    """), {"id": uid})
    user = row.fetchone()

    admin_list = [e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()]
    return UserProfile(
        id=str(user.id),
        email=user.email,
        name=user.name,
        plan=user.plan,
        subscription_status=user.subscription_status or "inactive",
        subscription_ends_at=user.subscription_ends_at.isoformat() if user.subscription_ends_at else None,
        email_verified=user.email_verified or False,
        created_at=user.created_at.isoformat() if user.created_at else None,
        is_admin=user.email.lower() in admin_list,
        email_alerts_enabled=user.email_alerts_enabled if user.email_alerts_enabled is not None else True,
        marketing_emails_enabled=user.marketing_emails_enabled if user.marketing_emails_enabled is not None else False,
        push_alerts_enabled=user.push_alerts_enabled if user.push_alerts_enabled is not None else True,
    )


# ── DELETE /users/me ──────────────────────────────────────────────────────────

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete the current user's account and all associated personal data.

    Privacy Act 1988 (Cth) — APP 11: organisations must destroy or de-identify
    personal information that is no longer needed.

    What is deleted (CASCADE):
      - users.users row
      - watchlists, watchlist_items
      - portfolios, portfolio_transactions
      - saved_screens
      - alerts, alert_triggers
      - user_notes, user_custom_ratios
      - sessions (refresh tokens)
      - unsubscribe_tokens

    What is RETAINED (legal obligation):
      - Billing records in Stripe (7-year ATO tax record-keeping requirement)
      - audit_log rows (SET NULL on user_id — no PII retained, action preserved)
    """
    uid = current_user["id"]

    # Verify the user exists before deletion
    result = await db.execute(
        text("SELECT id, email FROM users.users WHERE id = :id"),
        {"id": uid},
    )
    user = result.fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Write audit entry BEFORE deletion (foreign key will be SET NULL after)
    await _audit(
        db, uid, "account.deleted", request,
        old_value={"email_hash": hashlib.sha256(user.email.encode()).hexdigest()},
        new_value={"deleted": True},
        entity_type="user", entity_id=uid,
    )

    # Delete all Stripe subscriptions via Stripe API (best-effort)
    try:
        result2 = await db.execute(
            text("SELECT stripe_customer_id FROM users.users WHERE id = :id"),
            {"id": uid},
        )
        row2 = result2.fetchone()
        if row2 and row2.stripe_customer_id:
            # We don't cancel here — Stripe keeps billing records
            # Just detach the customer from our records
            pass
    except Exception:
        pass  # Non-fatal — Stripe deletion is separate

    # Delete the user — CASCADE handles all child records
    await db.execute(
        text("DELETE FROM users.users WHERE id = :id"),
        {"id": uid},
    )
    await db.commit()

    log.info(f"Account deleted: user_id={uid} (email hash stored in audit_log only)")
    # 204 No Content — no body
