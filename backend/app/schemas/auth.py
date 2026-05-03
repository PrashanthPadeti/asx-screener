"""
ASX Screener — Auth Pydantic Schemas
"""
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    """Returned by /login and /refresh."""
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int          # seconds until access token expires


class AccessTokenResponse(BaseModel):
    """Returned by /refresh when only access token is rotated."""
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int


class UserProfile(BaseModel):
    """Returned by GET /me."""
    id:             str
    email:          str
    name:           Optional[str]   = None
    plan:           str             = "free"
    email_verified: bool            = False
    created_at:     Optional[str]   = None

    model_config = {"from_attributes": True}
