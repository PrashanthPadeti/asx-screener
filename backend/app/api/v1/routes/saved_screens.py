"""
Saved Screens — CRUD + community listing
GET    /api/v1/screens/community      — all public screens (no auth)
GET    /api/v1/screens/mine           — current user's screens (auth)
POST   /api/v1/screens                — create screen (auth)
PUT    /api/v1/screens/{id}           — update screen (auth, owner only)
DELETE /api/v1/screens/{id}           — delete screen (auth, owner only)
POST   /api/v1/screens/{id}/use       — increment use_count (no auth)
"""
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional

from app.core.deps import get_current_user
from app.core.config import settings
from app.core.plans import PLAN_RANK as _PLAN_RANK
from app.db.session import get_db

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class SaveScreenRequest(BaseModel):
    name:        str         = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    filters:     list        = Field(default_factory=list)
    sort_by:     str         = "market_cap"
    sort_dir:    str         = "desc"
    is_public:   bool        = False
    query_text:  Optional[str] = None


class UpdateScreenRequest(BaseModel):
    name:        Optional[str]  = Field(None, min_length=1, max_length=120)
    description: Optional[str]  = None
    filters:     Optional[list] = None
    sort_by:     Optional[str]  = None
    sort_dir:    Optional[str]  = None
    is_public:   Optional[bool] = None
    query_text:  Optional[str]  = None


def _row_to_dict(row) -> dict:
    return {
        "id":           str(row.id),
        "user_id":      str(row.user_id),
        "user_name":    row.user_name or "Anonymous",
        "name":         row.name,
        "description":  row.description,
        "filters":      row.filters if isinstance(row.filters, list) else json.loads(row.filters or "[]"),
        "sort_by":      row.sort_by,
        "sort_dir":     row.sort_dir,
        "is_public":    row.is_public,
        "use_count":    row.use_count,
        "query_text":   row.query_text if hasattr(row, "query_text") else None,
        "creator_plan": row.creator_plan if hasattr(row, "creator_plan") else "free",
        "created_at":   row.created_at.isoformat() if row.created_at else None,
        "updated_at":   row.updated_at.isoformat() if row.updated_at else None,
    }


def _is_admin(email: str) -> bool:
    admin_list = [e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()]
    return email.lower() in admin_list


# ── Community screens ─────────────────────────────────────────────────────────

@router.get("/community")
async def community_screens(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return public screens the requesting user is allowed to see:
    - Admin: all public screens
    - Premium (rank 2+): all public screens
    - Pro (rank 1): screens created by free or pro users only
    - Free (rank 0): 403
    """
    user_rank = _PLAN_RANK.get(current_user["plan"], 0)

    if not _is_admin(current_user["email"]) and user_rank < 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Community screens are available to Pro and Premium subscribers.",
        )

    # Admins and Premium users (rank >= 2) see everything.
    # Pro users (rank 1) see screens where creator_plan rank <= 1 (free/pro).
    if _is_admin(current_user["email"]) or user_rank >= 2:
        rank_filter = 999  # no upper cap
    else:
        rank_filter = 1  # pro cap: exclude premium-created screens

    result = await db.execute(text("""
        SELECT s.id, s.user_id, u.name AS user_name, s.name, s.description,
               s.filters, s.sort_by, s.sort_dir, s.is_public, s.use_count,
               s.query_text, s.creator_plan, s.created_at, s.updated_at
        FROM screener.saved_screens s
        JOIN users.users u ON u.id = s.user_id
        WHERE s.is_public = TRUE
          AND CASE s.creator_plan
                WHEN 'free'               THEN 0
                WHEN 'pro'                THEN 1
                WHEN 'enterprise_pro'     THEN 1
                WHEN 'premium'            THEN 2
                WHEN 'enterprise_premium' THEN 2
                ELSE 0
              END <= :rank_filter
        ORDER BY s.use_count DESC, s.created_at DESC
        LIMIT 100
    """), {"rank_filter": rank_filter})
    return {"screens": [_row_to_dict(r) for r in result.fetchall()]}


# ── My screens ────────────────────────────────────────────────────────────────

@router.get("/mine")
async def my_screens(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        SELECT s.id, s.user_id, u.name AS user_name, s.name, s.description,
               s.filters, s.sort_by, s.sort_dir, s.is_public, s.use_count,
               s.query_text, s.creator_plan, s.created_at, s.updated_at
        FROM screener.saved_screens s
        JOIN users.users u ON u.id = s.user_id
        WHERE s.user_id = :uid
        ORDER BY s.updated_at DESC
    """), {"uid": current_user["id"]})
    return {"screens": [_row_to_dict(r) for r in result.fetchall()]}


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_screen(
    body: SaveScreenRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("""
        INSERT INTO screener.saved_screens
            (user_id, name, description, filters, sort_by, sort_dir, is_public, query_text, creator_plan)
        VALUES (:uid, :name, :desc, CAST(:filters AS jsonb), :sort_by, :sort_dir, :is_public, :query_text, :creator_plan)
        RETURNING id, user_id, name, description, filters, sort_by, sort_dir,
                  is_public, use_count, query_text, creator_plan, created_at, updated_at
    """), {
        "uid":          current_user["id"],
        "name":         body.name,
        "desc":         body.description,
        "filters":      json.dumps(body.filters),
        "sort_by":      body.sort_by,
        "sort_dir":     body.sort_dir,
        "is_public":    body.is_public,
        "query_text":   body.query_text,
        "creator_plan": current_user["plan"],
    })
    await db.commit()
    row = result.fetchone()
    # Fetch with user name
    result2 = await db.execute(text("""
        SELECT s.id, s.user_id, u.name AS user_name, s.name, s.description,
               s.filters, s.sort_by, s.sort_dir, s.is_public, s.use_count,
               s.query_text, s.creator_plan, s.created_at, s.updated_at
        FROM screener.saved_screens s
        JOIN users.users u ON u.id = s.user_id
        WHERE s.id = :id
    """), {"id": row.id})
    return _row_to_dict(result2.fetchone())


# ── Update ────────────────────────────────────────────────────────────────────

@router.put("/{screen_id}")
async def update_screen(
    screen_id: UUID,
    body: UpdateScreenRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        text("SELECT user_id FROM screener.saved_screens WHERE id = :id"),
        {"id": str(screen_id)},
    )
    row = existing.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Screen not found")
    if str(row.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your screen")

    updates = {}
    if body.name        is not None: updates["name"]        = body.name
    if body.description is not None: updates["description"] = body.description
    if body.filters     is not None: updates["filters"]     = json.dumps(body.filters)
    if body.sort_by     is not None: updates["sort_by"]     = body.sort_by
    if body.sort_dir    is not None: updates["sort_dir"]    = body.sort_dir
    if body.is_public   is not None: updates["is_public"]   = body.is_public
    if body.query_text  is not None: updates["query_text"]  = body.query_text

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    set_clauses = ", ".join(
        f"{k} = CAST(:{k} AS jsonb)" if k == "filters" else f"{k} = :{k}"
        for k in updates
    )
    updates["id"] = str(screen_id)
    await db.execute(
        text(f"UPDATE screener.saved_screens SET {set_clauses}, updated_at = NOW() WHERE id = :id"),
        updates,
    )
    await db.commit()

    result = await db.execute(text("""
        SELECT s.id, s.user_id, u.name AS user_name, s.name, s.description,
               s.filters, s.sort_by, s.sort_dir, s.is_public, s.use_count,
               s.query_text, s.creator_plan, s.created_at, s.updated_at
        FROM screener.saved_screens s
        JOIN users.users u ON u.id = s.user_id
        WHERE s.id = :id
    """), {"id": str(screen_id)})
    return _row_to_dict(result.fetchone())


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{screen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_screen(
    screen_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        text("SELECT user_id FROM screener.saved_screens WHERE id = :id"),
        {"id": str(screen_id)},
    )
    row = existing.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Screen not found")
    if str(row.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not your screen")

    await db.execute(
        text("DELETE FROM screener.saved_screens WHERE id = :id"),
        {"id": str(screen_id)},
    )
    await db.commit()


# ── Use count ─────────────────────────────────────────────────────────────────

@router.post("/{screen_id}/use", status_code=status.HTTP_204_NO_CONTENT)
async def increment_use(screen_id: UUID, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("UPDATE screener.saved_screens SET use_count = use_count + 1 WHERE id = :id AND is_public = TRUE"),
        {"id": str(screen_id)},
    )
    await db.commit()
