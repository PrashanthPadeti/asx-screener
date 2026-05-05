"""
ASX Screener — FastAPI Auth Dependencies
==========================================
get_current_user    — requires valid Bearer token (401 if missing/invalid)
get_optional_user   — returns None if no token / invalid
require_plan()      — factory that raises 403 if user's plan is below minimum
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.core.plans import PLAN_RANK as _PLAN_RANK
from app.db.session import get_db

# ── Bearer scheme (auto_error=False so optional use works) ───────────────────

_bearer = HTTPBearer(auto_error=False)


# ── Internal helper ──────────────────────────────────────────────────────────

async def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: AsyncSession,
) -> Optional[dict]:
    """
    Decode the Bearer token and return a dict with:
        id, email, plan, name, email_verified
    Returns None if credentials are absent or the token is invalid.
    Does NOT hit the DB — trusts the signed JWT payload.
    """
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        return None

    return {
        "id":                  payload["sub"],
        "email":               payload["email"],
        "plan":                payload.get("plan", "free"),
        "subscription_status": payload.get("status", "inactive"),
    }


# ── Public dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Require a valid access token.  Raises HTTP 401 if absent or invalid.
    Returns user dict: {id, email, plan}.
    """
    user = await _resolve_user(credentials, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[dict]:
    """
    Return user dict if a valid token is present, otherwise None.
    Never raises — suitable for endpoints that work for both
    authenticated and anonymous users.
    """
    return await _resolve_user(credentials, db)


def require_plan(minimum: str):
    """
    Dependency factory: raise HTTP 403 if the authenticated user's plan
    is below *minimum*.

    Usage::

        @router.get("/premium-data")
        async def premium(user = Depends(require_plan("pro"))):
            ...
    """
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        user_rank = _PLAN_RANK.get(user["plan"], 0)
        min_rank  = _PLAN_RANK.get(minimum, 0)
        if user_rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires the '{minimum}' plan or higher.",
            )
        return user
    return _check
