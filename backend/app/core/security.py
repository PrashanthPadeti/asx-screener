"""
ASX Screener — Security Utilities
===================================
JWT access tokens  (15 min, stateless, signed HS256)
Refresh tokens     (30 days, opaque UUID stored in users.sessions)
Password hashing   (bcrypt via passlib)
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── Password hashing ─────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain*."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return _pwd_context.verify(plain, hashed)


# ── JWT access tokens ────────────────────────────────────────────────────────

def create_access_token(
    user_id: str,
    email: str,
    plan: str,
    *,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.

    Payload:
        sub   — user UUID (string)
        email — user email
        plan  — free | pro | premium | enterprise
        exp   — expiry (UTC)
        iat   — issued-at (UTC)
        type  — "access"
    """
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    now   = datetime.now(timezone.utc)
    payload = {
        "sub":   user_id,
        "email": email,
        "plan":  plan,
        "iat":   now,
        "exp":   now + delta,
        "type":  "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT access token.

    Raises jose.JWTError on invalid / expired tokens.
    Raises ValueError if token type is not "access".
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    return payload


# ── Opaque refresh tokens ────────────────────────────────────────────────────

def generate_refresh_token() -> str:
    """Return a cryptographically random opaque token (UUID4 hex, no hyphens)."""
    return uuid.uuid4().hex + uuid.uuid4().hex   # 64 hex chars


def refresh_token_expires_at() -> datetime:
    """Return the absolute expiry for a new refresh token."""
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
