"""
Support Tickets
================
POST /api/v1/support/tickets           — create ticket (public)
GET  /api/v1/support/tickets           — list all tickets (admin)
GET  /api/v1/support/tickets/{id}      — ticket detail (admin)
PUT  /api/v1/support/tickets/{id}      — update status/notes (admin)
GET  /api/v1/support/uploads/{tid}/{f} — serve attachment (admin)
"""
import json
import logging
import os
import uuid
from typing import Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_optional_user, require_admin
from app.db.session import get_db
from app.services.email import send_support_confirmation, send_support_notification

log = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = "/opt/asx-screener/uploads/support"
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _ticket_row_to_dict(row) -> dict:
    attachments = row.attachments
    if isinstance(attachments, str):
        attachments = json.loads(attachments or "[]")
    return {
        "id":               str(row.id),
        "ticket_number":    row.ticket_number,
        "user_id":          str(row.user_id) if row.user_id else None,
        "name":             row.name,
        "email":            row.email,
        "phone":            row.phone,
        "category":         row.category,
        "subject":          row.subject,
        "description":      row.description,
        "attachments":      attachments,
        "status":           row.status,
        "priority":         row.priority,
        "resolution_notes": row.resolution_notes,
        "resolved_by":      row.resolved_by,
        "created_at":       row.created_at.isoformat() if row.created_at else None,
        "updated_at":       row.updated_at.isoformat() if row.updated_at else None,
        "resolved_at":      row.resolved_at.isoformat() if row.resolved_at else None,
    }


# ── Create ticket (public) ────────────────────────────────────────────────────

@router.post("/tickets", status_code=status.HTTP_201_CREATED)
async def create_ticket(
    name:               str            = Form(...),
    email:              str            = Form(...),
    phone:              Optional[str]  = Form(None),
    category:           str            = Form("general"),
    subject:            str            = Form(...),
    description:        str            = Form(...),
    # Browser / device context (sent by frontend, never shown to user)
    context_url:        Optional[str]  = Form(None),
    context_user_agent: Optional[str]  = Form(None),
    context_viewport:   Optional[str]  = Form(None),
    context_timestamp:  Optional[str]  = Form(None),
    subscription_tier:  Optional[str]  = Form(None),
    files:              list[UploadFile] = File(default=[]),
    current_user: Optional[dict]  = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"] if current_user else None
    # Prefer subscription tier from auth token over form field
    if current_user and not subscription_tier:
        subscription_tier = current_user.get("subscription_tier") or current_user.get("tier")

    # Save attachments
    attachment_paths: list[str] = []
    ticket_id = str(uuid.uuid4())
    if files:
        upload_path = os.path.join(UPLOAD_DIR, ticket_id)
        os.makedirs(upload_path, exist_ok=True)
        for f in files:
            if not f.filename:
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in ALLOWED_EXTS:
                continue
            content = await f.read()
            if len(content) > MAX_FILE_SIZE:
                continue
            safe_name = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(upload_path, safe_name)
            async with aiofiles.open(file_path, "wb") as out:
                await out.write(content)
            attachment_paths.append(f"{ticket_id}/{safe_name}")

    result = await db.execute(text("""
        INSERT INTO support.tickets
            (id, user_id, name, email, phone, category, subject, description, attachments)
        VALUES
            (:id, :uid, :name, :email, :phone, :cat, :subj, :desc, CAST(:att AS jsonb))
        RETURNING id, ticket_number, user_id, name, email, phone, category, subject,
                  description, attachments, status, priority, resolution_notes,
                  resolved_by, created_at, updated_at, resolved_at
    """), {
        "id":    ticket_id,
        "uid":   user_id,
        "name":  name,
        "email": email.lower(),
        "phone": phone,
        "cat":   category,
        "subj":  subject,
        "desc":  description,
        "att":   json.dumps(attachment_paths),
    })
    await db.commit()
    row = result.fetchone()

    send_support_notification(
        ticket_number=row.ticket_number,
        name=name,
        email=email,
        phone=phone,
        category=category,
        subject=subject,
        description=description,
        user_id=user_id,
        context_url=context_url,
        context_user_agent=context_user_agent,
        context_viewport=context_viewport,
        context_timestamp=context_timestamp,
        subscription_tier=subscription_tier,
    )

    # Confirmation email to the user (best-effort — don't fail the request)
    try:
        send_support_confirmation(
            ticket_number=row.ticket_number,
            name=name,
            email=email,
            category=category,
            subject=subject,
        )
    except Exception as exc:
        log.warning(f"Could not send support confirmation to {email}: {exc}")

    log.info(f"Support ticket #{row.ticket_number} created by {email}")
    return {"ticket": _ticket_row_to_dict(row)}


# ── List tickets (admin) ──────────────────────────────────────────────────────

@router.get("/tickets")
async def list_tickets(
    status_filter: Optional[str] = None,
    category:      Optional[str] = None,
    limit:         int = 100,
    offset:        int = 0,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    conditions = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}
    if status_filter and status_filter != "all":
        conditions.append("status = :status")
        params["status"] = status_filter
    if category and category != "all":
        conditions.append("category = :category")
        params["category"] = category

    where = " AND ".join(conditions)
    result = await db.execute(text(f"""
        SELECT id, ticket_number, user_id, name, email, phone, category, subject,
               description, attachments, status, priority, resolution_notes,
               resolved_by, created_at, updated_at, resolved_at
        FROM support.tickets
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """), params)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM support.tickets WHERE {where}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )
    total = count_result.scalar()

    return {
        "tickets": [_ticket_row_to_dict(r) for r in result.fetchall()],
        "total":   total,
    }


# ── Get single ticket (admin) ─────────────────────────────────────────────────

@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: UUID,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        SELECT id, ticket_number, user_id, name, email, phone, category, subject,
               description, attachments, status, priority, resolution_notes,
               resolved_by, created_at, updated_at, resolved_at
        FROM support.tickets WHERE id = :id
    """), {"id": str(ticket_id)})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_row_to_dict(row)


# ── Update ticket (admin) ─────────────────────────────────────────────────────

class UpdateTicketRequest(BaseModel):
    status:           Optional[str] = None
    priority:         Optional[str] = None
    resolution_notes: Optional[str] = None


@router.put("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: UUID,
    body: UpdateTicketRequest,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    updates: dict = {}
    if body.status           is not None: updates["status"]           = body.status
    if body.priority         is not None: updates["priority"]         = body.priority
    if body.resolution_notes is not None: updates["resolution_notes"] = body.resolution_notes

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    # Auto-set resolved_at and resolved_by
    extra_sql = ""
    if body.status in ("resolved", "closed"):
        extra_sql = ", resolved_at = NOW(), resolved_by = :resolver"
        updates["resolver"] = admin["email"]

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates if k != "resolver")
    updates["id"] = str(ticket_id)
    await db.execute(
        text(f"UPDATE support.tickets SET {set_clauses}{extra_sql}, updated_at = NOW() WHERE id = :id"),
        updates,
    )
    await db.commit()

    result = await db.execute(text("""
        SELECT id, ticket_number, user_id, name, email, phone, category, subject,
               description, attachments, status, priority, resolution_notes,
               resolved_by, created_at, updated_at, resolved_at
        FROM support.tickets WHERE id = :id
    """), {"id": str(ticket_id)})
    return _ticket_row_to_dict(result.fetchone())


# ── Serve attachment (admin) ──────────────────────────────────────────────────

@router.get("/uploads/{ticket_id}/{filename}")
async def serve_upload(
    ticket_id: str,
    filename:  str,
    admin: dict = Depends(require_admin),
):
    safe_ticket = ticket_id.replace("..", "").replace("/", "")
    safe_file   = filename.replace("..", "").replace("/", "")
    path = os.path.join(UPLOAD_DIR, safe_ticket, safe_file)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
