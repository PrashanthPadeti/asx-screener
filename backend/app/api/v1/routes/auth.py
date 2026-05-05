"""
ASX Screener — Auth Routes
============================
POST /api/v1/auth/register  — create account
POST /api/v1/auth/login     — get access + refresh tokens
POST /api/v1/auth/refresh   — exchange refresh token for new pair
POST /api/v1/auth/logout    — revoke refresh token
GET  /api/v1/auth/me        — return current user profile
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    refresh_token_expires_at,
    verify_password,
)
from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _token_response(
    user_id: str,
    email: str,
    plan: str,
    subscription_status: str = "inactive",
) -> tuple:
    """Build a full TokenResponse (access + refresh) for a user."""
    access  = create_access_token(user_id, email, plan, subscription_status)
    refresh = generate_refresh_token()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ), refresh


async def _store_session(
    db: AsyncSession,
    user_id: str,
    refresh_token: str,
    request: Request,
) -> None:
    """Persist a new refresh-token session row."""
    expires = refresh_token_expires_at()
    ua  = request.headers.get("user-agent", "")[:499]
    ip  = request.client.host if request.client else None
    await db.execute(
        text("""
            INSERT INTO users.sessions (user_id, refresh_token, user_agent, ip_address, expires_at)
            VALUES (:uid, :tok, :ua, :ip, :exp)
        """),
        {"uid": user_id, "tok": refresh_token, "ua": ua, "ip": ip, "exp": expires},
    )
    await db.commit()


# ── Register ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account and return tokens."""
    row = await db.execute(
        text("SELECT id FROM users.users WHERE email = :email"),
        {"email": body.email.lower()},
    )
    if row.fetchone():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    hashed = hash_password(body.password)

    result = await db.execute(
        text("""
            INSERT INTO users.users (email, name, password_hash)
            VALUES (:email, :name, :pw)
            RETURNING id, plan, subscription_status
        """),
        {"email": body.email.lower(), "name": body.name, "pw": hashed},
    )
    row = result.fetchone()
    await db.commit()

    user_id             = str(row.id)
    plan                = row.plan
    subscription_status = row.subscription_status or "inactive"

    token_resp, refresh = _token_response(user_id, body.email.lower(), plan, subscription_status)
    await _store_session(db, user_id, refresh, request)

    log.info(f"New user registered: {body.email}")
    return token_resp


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email + password. Returns access + refresh tokens."""
    result = await db.execute(
        text("""
            SELECT id, email, password_hash, plan, email_verified, subscription_status
            FROM users.users
            WHERE email = :email
        """),
        {"email": body.email.lower()},
    )
    user = result.fetchone()

    if user is None or not verify_password(body.password, user.password_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    await db.execute(
        text("UPDATE users.users SET last_login_at = NOW() WHERE id = :id"),
        {"id": user.id},
    )
    await db.commit()

    user_id             = str(user.id)
    subscription_status = user.subscription_status or "inactive"
    token_resp, refresh = _token_response(user_id, user.email, user.plan, subscription_status)
    await _store_session(db, user_id, refresh, request)

    log.info(f"User logged in: {user.email}")
    return token_resp


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    result = await db.execute(
        text("""
            SELECT s.id AS session_id, s.user_id, s.expires_at, s.revoked,
                   u.email, u.plan, u.subscription_status
            FROM users.sessions s
            JOIN users.users u ON u.id = s.user_id
            WHERE s.refresh_token = :tok
        """),
        {"tok": body.refresh_token},
    )
    row = result.fetchone()

    if row is None or row.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token",
        )

    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired — please log in again",
        )

    await db.execute(
        text("""
            UPDATE users.sessions
            SET revoked = TRUE, revoked_at = NOW()
            WHERE id = :sid
        """),
        {"sid": row.session_id},
    )
    await db.commit()

    user_id             = str(row.user_id)
    subscription_status = row.subscription_status or "inactive"
    token_resp, new_refresh = _token_response(user_id, row.email, row.plan, subscription_status)
    await _store_session(db, user_id, new_refresh, request)

    return token_resp


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Revoke the given refresh token. Idempotent — no error if token unknown."""
    await db.execute(
        text("""
            UPDATE users.sessions
            SET revoked = TRUE, revoked_at = NOW()
            WHERE refresh_token = :tok AND NOT revoked
        """),
        {"tok": body.refresh_token},
    )
    await db.commit()


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserProfile)
async def me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's full profile (requires valid access token)."""
    result = await db.execute(
        text("""
            SELECT id, email, name, plan, email_verified,
                   subscription_status, subscription_ends_at, created_at
            FROM users.users
            WHERE id = :id
        """),
        {"id": current_user["id"]},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfile(
        id=str(row.id),
        email=row.email,
        name=row.name,
        plan=row.plan,
        subscription_status=row.subscription_status or "inactive",
        subscription_ends_at=row.subscription_ends_at.isoformat() if row.subscription_ends_at else None,
        email_verified=row.email_verified or False,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )
