"""
ASX Screener — Watchlist Routes
=================================
All endpoints require authentication.

GET    /watchlist                      — list user's watchlists
POST   /watchlist                      — create watchlist
GET    /watchlist/{id}                 — get watchlist + codes
PATCH  /watchlist/{id}                 — rename / update description
DELETE /watchlist/{id}                 — delete watchlist
POST   /watchlist/{id}/stocks          — add stock to watchlist
DELETE /watchlist/{id}/stocks/{code}   — remove stock from watchlist
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.watchlist import (
    WatchlistAddStock,
    WatchlistCreate,
    WatchlistDetail,
    WatchlistSummary,
    WatchlistUpdate,
    WatchlistsResponse,
)

log = logging.getLogger(__name__)
router = APIRouter()

_FREE_WATCHLIST_LIMIT  = 3
_FREE_STOCK_LIMIT      = 50
_PRO_WATCHLIST_LIMIT   = 20
_PRO_STOCK_LIMIT       = 500


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_watchlist_or_404(
    watchlist_id: str,
    user_id: str,
    db: AsyncSession,
) -> dict:
    """Fetch watchlist row, raising 404 if not found or not owned by user."""
    result = await db.execute(
        text("""
            SELECT id, user_id, name, description, item_count, created_at
            FROM users.watchlists
            WHERE id = :wid AND user_id = :uid
        """),
        {"wid": watchlist_id, "uid": user_id},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return row


async def _refresh_item_count(watchlist_id: str, db: AsyncSession) -> None:
    await db.execute(
        text("""
            UPDATE users.watchlists
            SET item_count = (
                SELECT COUNT(*) FROM users.watchlist_items WHERE watchlist_id = :wid
            ),
            updated_at = NOW()
            WHERE id = :wid
        """),
        {"wid": watchlist_id},
    )


# ── List watchlists ───────────────────────────────────────────────────────────

@router.get("", response_model=WatchlistsResponse)
async def list_watchlists(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all watchlists owned by the authenticated user."""
    result = await db.execute(
        text("""
            SELECT id, name, description, item_count, created_at
            FROM users.watchlists
            WHERE user_id = :uid
            ORDER BY created_at ASC
        """),
        {"uid": current_user["id"]},
    )
    rows = result.fetchall()
    return WatchlistsResponse(
        watchlists=[
            WatchlistSummary(
                id=str(r.id),
                name=r.name,
                description=r.description,
                item_count=r.item_count or 0,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


# ── Create watchlist ──────────────────────────────────────────────────────────

@router.post("", response_model=WatchlistSummary, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    body: WatchlistCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new watchlist. Free plan: max 3 watchlists."""
    plan = current_user.get("plan", "free")
    limit = _PRO_WATCHLIST_LIMIT if plan in ("pro", "premium", "enterprise") else _FREE_WATCHLIST_LIMIT

    count_result = await db.execute(
        text("SELECT COUNT(*) FROM users.watchlists WHERE user_id = :uid"),
        {"uid": current_user["id"]},
    )
    current_count = count_result.scalar() or 0
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your plan allows a maximum of {limit} watchlists.",
        )

    result = await db.execute(
        text("""
            INSERT INTO users.watchlists (user_id, name, description)
            VALUES (:uid, :name, :desc)
            RETURNING id, name, description, item_count, created_at
        """),
        {"uid": current_user["id"], "name": body.name.strip(), "desc": body.description},
    )
    row = result.fetchone()
    await db.commit()

    return WatchlistSummary(
        id=str(row.id),
        name=row.name,
        description=row.description,
        item_count=0,
        created_at=row.created_at,
    )


# ── Get watchlist detail ──────────────────────────────────────────────────────

@router.get("/{watchlist_id}", response_model=WatchlistDetail)
async def get_watchlist(
    watchlist_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return watchlist metadata + ordered list of ASX codes."""
    wl = await _get_watchlist_or_404(watchlist_id, current_user["id"], db)

    items_result = await db.execute(
        text("""
            SELECT asx_code FROM users.watchlist_items
            WHERE watchlist_id = :wid
            ORDER BY sort_order ASC, added_at ASC
        """),
        {"wid": watchlist_id},
    )
    codes = [r.asx_code for r in items_result.fetchall()]

    return WatchlistDetail(
        id=str(wl.id),
        name=wl.name,
        description=wl.description,
        item_count=wl.item_count or 0,
        created_at=wl.created_at,
        codes=codes,
    )


# ── Update watchlist ──────────────────────────────────────────────────────────

@router.patch("/{watchlist_id}", response_model=WatchlistSummary)
async def update_watchlist(
    watchlist_id: str,
    body: WatchlistUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename or update the description of a watchlist."""
    wl = await _get_watchlist_or_404(watchlist_id, current_user["id"], db)

    new_name = body.name.strip() if body.name else wl.name
    new_desc = body.description if body.description is not None else wl.description

    result = await db.execute(
        text("""
            UPDATE users.watchlists
            SET name = :name, description = :desc, updated_at = NOW()
            WHERE id = :wid
            RETURNING id, name, description, item_count, created_at
        """),
        {"wid": watchlist_id, "name": new_name, "desc": new_desc},
    )
    row = result.fetchone()
    await db.commit()

    return WatchlistSummary(
        id=str(row.id),
        name=row.name,
        description=row.description,
        item_count=row.item_count or 0,
        created_at=row.created_at,
    )


# ── Delete watchlist ──────────────────────────────────────────────────────────

@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a watchlist and all its items (CASCADE)."""
    await _get_watchlist_or_404(watchlist_id, current_user["id"], db)
    await db.execute(
        text("DELETE FROM users.watchlists WHERE id = :wid"),
        {"wid": watchlist_id},
    )
    await db.commit()


# ── Add stock ─────────────────────────────────────────────────────────────────

@router.post("/{watchlist_id}/stocks", status_code=status.HTTP_201_CREATED)
async def add_stock(
    watchlist_id: str,
    body: WatchlistAddStock,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a stock to a watchlist. Idempotent (ignores duplicates)."""
    await _get_watchlist_or_404(watchlist_id, current_user["id"], db)

    plan = current_user.get("plan", "free")
    limit = _PRO_STOCK_LIMIT if plan in ("pro", "premium", "enterprise") else _FREE_STOCK_LIMIT

    count_result = await db.execute(
        text("SELECT COUNT(*) FROM users.watchlist_items WHERE watchlist_id = :wid"),
        {"wid": watchlist_id},
    )
    current_count = count_result.scalar() or 0
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Watchlist limit reached ({limit} stocks on your plan).",
        )

    await db.execute(
        text("""
            INSERT INTO users.watchlist_items (watchlist_id, asx_code, notes, target_price)
            VALUES (:wid, :code, :notes, :tp)
            ON CONFLICT (watchlist_id, asx_code) DO NOTHING
        """),
        {
            "wid":   watchlist_id,
            "code":  body.asx_code.upper().strip(),
            "notes": body.notes,
            "tp":    body.target_price,
        },
    )
    await _refresh_item_count(watchlist_id, db)
    await db.commit()
    return {"asx_code": body.asx_code.upper().strip(), "watchlist_id": watchlist_id}


# ── Remove stock ──────────────────────────────────────────────────────────────

@router.delete("/{watchlist_id}/stocks/{asx_code}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_stock(
    watchlist_id: str,
    asx_code: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a stock from a watchlist. Idempotent."""
    await _get_watchlist_or_404(watchlist_id, current_user["id"], db)
    await db.execute(
        text("""
            DELETE FROM users.watchlist_items
            WHERE watchlist_id = :wid AND asx_code = :code
        """),
        {"wid": watchlist_id, "code": asx_code.upper()},
    )
    await _refresh_item_count(watchlist_id, db)
    await db.commit()
