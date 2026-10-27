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
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import limiter

from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    refresh_token_expires_at,
    verify_password,
)
from app.core.config import settings
from app.core.verification_policy import verification_required_for
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from app.services.email import (
    send_login_failure_alert,
    send_password_reset_email,
    send_verification_reminder_email,
    send_welcome_email,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _verification_required_for(created_at) -> bool:
    """See app/core/verification_policy — the rule lives there so it can be
    tested without importing the application."""
    return verification_required_for(created_at)


async def _issue_verification_email(db: AsyncSession, user_id: str,
                                    email: str, name: str | None,
                                    welcome: bool = False) -> bool:
    """Mint a verification token, store it, and send the email.

    Best-effort on the SEND, deliberate on the TOKEN: the row is updated
    first, so a mail failure leaves an account that can be resent to rather
    than one with no token at all. Returns whether the email went out.
    """
    tok = secrets.token_urlsafe(48)
    await db.execute(text("""
        UPDATE users.users
           SET email_verification_token   = :tok,
               email_verification_sent_at = NOW()
         WHERE id = :uid
    """), {"tok": tok, "uid": user_id})
    await db.commit()

    frontend_url = getattr(settings, "FRONTEND_URL", "https://asxscreener.com.au")
    verify_url = f"{frontend_url}/auth/verify-email?token={tok}"
    try:
        if welcome:
            # ONE email for a new signup. Two arriving seconds apart
            # contradicted each other: the welcome said "start screening"
            # while the account could not be used until the link was
            # clicked. The combined mail leads with the verification step
            # and keeps the product description underneath.
            send_welcome_email(email, name, verify_url=verify_url)
        else:
            send_verification_reminder_email(email, verify_url, name)
        return True
    except Exception as exc:                                   # noqa: BLE001
        log.warning("Could not send verification email to %s: %s", email, exc)
        return False


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

@limiter.limit("3/minute")
@router.post("/register", status_code=status.HTTP_201_CREATED)
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
            RETURNING id, plan, subscription_status, created_at
        """),
        {"email": body.email.lower(), "name": body.name, "pw": hashed},
    )
    row = result.fetchone()
    await db.commit()

    user_id             = str(row.id)
    plan                = row.plan
    subscription_status = row.subscription_status or "inactive"
    created_at          = row.created_at

    log.info(f"New user registered: {body.email}")

    # ── Mandatory verification ────────────────────────────────────────────
    # Until 26 Oct 2026 registration sent a welcome email and no verification
    # email at all; the only way an account ever got one was an admin
    # triggering it by hand. So the verification mail is sent HERE, and the
    # login gate added alongside it is only honest because of this line.
    #
    # No tokens are returned when verification is required. Returning them
    # would hand the new user a working session and make the login gate
    # decorative — they would simply never hit it.
    if _verification_required_for(created_at):
        # welcome=True: one email, verification-led, with the welcome content
        # underneath. The support-inbox copy rides along with it as before.
        sent = await _issue_verification_email(
            db, user_id, body.email.lower(), body.name, welcome=True)
        return {
            "verification_required": True,
            "email": body.email.lower(),
            "email_sent": sent,
            "message": (
                "Account created. Check your email for a verification link "
                "to activate your account — it can take a minute to arrive, "
                "and it sometimes lands in the spam or junk folder."
                if sent else
                "Account created, but the verification email could not be "
                "sent just now. Use 'Resend verification email' on the "
                "sign-in page, or contact support."
            ),
        }

    # Exempt account: no verification needed, so the plain welcome stands on
    # its own and "start screening" is true advice.
    try:
        send_welcome_email(body.email.lower(), body.name)
    except Exception as exc:
        log.warning(f"Could not send welcome email to {body.email}: {exc}")

    token_resp, refresh = _token_response(user_id, body.email.lower(), plan, subscription_status)
    await _store_session(db, user_id, refresh, request)
    return token_resp


# ── Login ─────────────────────────────────────────────────────────────────────

@limiter.limit("5/minute")
@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email + password. Returns access + refresh tokens."""
    email_lc = body.email.lower()

    try:
        result = await db.execute(
            text("""
                SELECT id, email, password_hash, plan, email_verified,
                       subscription_status, name, created_at
                FROM users.users
                WHERE email = :email
            """),
            {"email": email_lc},
        )
        user = result.fetchone()
    except Exception as exc:
        # Login is broken rather than refused — e.g. the database is down, which
        # is what users saw as "Request failed". Alert, then surface a 503 so the
        # cause isn't mistaken for bad credentials.
        log.error(f"Login failed with a system error for {email_lc}: {exc}")
        try:
            send_login_failure_alert(email_lc, f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is temporarily unavailable. Please try again shortly.",
        )

    # Wrong email or password is the user's own credential problem, not a site
    # fault — no alert, by design.
    if user is None or not verify_password(body.password, user.password_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # ── Mandatory email verification ──────────────────────────────────────
    # Credentials are correct; the account simply is not activated yet.
    #
    # Checked AFTER the password so an attacker cannot learn which addresses
    # exist by watching which ones answer 403 instead of 401.
    #
    # Only applies to accounts created on or after the cutoff. Everyone who
    # registered before it is exempt permanently — until 26 Oct 2026
    # registration never sent a verification email, so existing unverified
    # accounts, paying subscribers among them, are unverified because nobody
    # ever asked them.
    if not user.email_verified and _verification_required_for(user.created_at):
        log.info("Login refused — email not verified: %s", email_lc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                # A code the frontend can branch on, so the sign-in page can
                # offer "resend" instead of showing a credentials error.
                "code": "email_not_verified",
                "email": email_lc,
                "message": (
                    "Your email address hasn't been verified yet. We sent a "
                    "verification link when you signed up — please click it "
                    "to activate your account. It can take a minute to "
                    "arrive, and it often lands in the spam or junk folder, "
                    "so check there too. If you can't find it, use 'Resend "
                    "verification email' below."
                ),
            },
        )

    # Credentials are valid from here on, so anything that fails below is a site
    # fault keeping a legitimate user out — alert on it.
    try:
        await db.execute(
            text("UPDATE users.users SET last_login_at = NOW() WHERE id = :id"),
            {"id": user.id},
        )
        await db.commit()

        user_id             = str(user.id)
        subscription_status = user.subscription_status or "inactive"
        token_resp, refresh = _token_response(user_id, user.email, user.plan, subscription_status)
        await _store_session(db, user_id, refresh, request)
    except Exception as exc:
        log.error(f"Login failed after valid credentials for {email_lc}: {exc}")
        try:
            send_login_failure_alert(email_lc, f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is temporarily unavailable. Please try again shortly.",
        )

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


# ── Forgot Password ───────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@limiter.limit("3/minute")
@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a password-reset email. Always returns 200 to prevent email enumeration."""
    result = await db.execute(
        text("SELECT id, name FROM users.users WHERE email = :email"),
        {"email": body.email.lower()},
    )
    user = result.fetchone()

    if user:
        token   = secrets.token_urlsafe(48)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.execute(
            text("""
                UPDATE users.users
                SET password_reset_token = :tok, password_reset_expires_at = :exp
                WHERE id = :id
            """),
            {"tok": token, "exp": expires, "id": str(user.id)},
        )
        await db.commit()

        frontend_url = getattr(settings, "FRONTEND_URL", "https://asxscreener.com.au")
        reset_url = f"{frontend_url}/auth/reset-password?token={token}"
        send_password_reset_email(body.email.lower(), reset_url, user.name)
        log.info(f"Password reset requested for {body.email}")

    return {"message": "If that email is registered, a reset link has been sent."}


# ── Reset Password ────────────────────────────────────────────────────────────

class ResetPasswordRequest(BaseModel):
    token:        str
    new_password: str = Field(..., min_length=8)


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify reset token and update password."""
    result = await db.execute(
        text("""
            SELECT id, password_reset_expires_at
            FROM users.users
            WHERE password_reset_token = :tok
        """),
        {"tok": body.token},
    )
    user = result.fetchone()

    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    expires = user.password_reset_expires_at
    if expires is None or expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset link has expired — please request a new one")

    new_hash = hash_password(body.new_password)
    await db.execute(
        text("""
            UPDATE users.users
            SET password_hash             = :pw,
                password_reset_token      = NULL,
                password_reset_expires_at = NULL,
                updated_at                = NOW()
            WHERE id = :id
        """),
        {"pw": new_hash, "id": str(user.id)},
    )
    # Revoke all existing sessions so old devices must re-login
    await db.execute(
        text("UPDATE users.sessions SET revoked = TRUE, revoked_at = NOW() WHERE user_id = :id AND NOT revoked"),
        {"id": str(user.id)},
    )
    await db.commit()
    log.info(f"Password reset completed for user {user.id}")
    return {"message": "Password updated successfully. You can now sign in."}


# ── Verify Email ─────────────────────────────────────────────────────────────

class ResendVerificationRequest(BaseModel):
    email: EmailStr


@limiter.limit("3/minute")
@router.post("/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send the verification email again.

    Mandatory verification without this would be a trap: an email that went
    to spam and was deleted, or a mistyped-but-valid address, would lock the
    account permanently with no way back except support.

    ALWAYS answers 200 with the same message, whether or not the address
    exists or is already verified. Anything else turns this into an account
    enumeration oracle — a 404 here would let anyone test which emails are
    registered, and this endpoint needs no authentication by definition.

    Rate limited to 3/minute, and a 2-minute cooldown per address, so it
    cannot be used to mailbomb someone.
    """
    email_lc = body.email.lower()
    same_answer = {
        "message": (
            "If that address has an unverified account, we've sent the "
            "verification link again. It can take a minute to arrive, and it "
            "often lands in the spam or junk folder — please check there too."
        )
    }

    row = (await db.execute(text("""
        SELECT id, email, name, email_verified, email_verification_sent_at
          FROM users.users WHERE email = :email
    """), {"email": email_lc})).fetchone()

    if row is None or row.email_verified:
        return same_answer

    last = row.email_verification_sent_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last < timedelta(minutes=2):
            # Silently honoured: telling the caller they are too early would
            # confirm the account exists, which is the thing being protected.
            log.info("resend-verification within cooldown for %s", email_lc)
            return same_answer

    await _issue_verification_email(db, str(row.id), row.email, row.name)
    return same_answer


@router.get("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    One-click email verification.  Called when the user clicks the link in their
    verification reminder email.  Marks email_verified = TRUE and clears the token.
    """
    if not token:
        raise HTTPException(status_code=400, detail="Verification token is required")

    result = await db.execute(
        text("""
            SELECT id, email, email_verified, email_verification_sent_at
            FROM users.users
            WHERE email_verification_token = :tok
        """),
        {"tok": token},
    )
    user = result.fetchone()

    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or already-used verification link")

    if user.email_verified:
        return {"message": "Email already verified. You're all set!"}

    # Token expires after 48 hours
    if user.email_verification_sent_at:
        cutoff = user.email_verification_sent_at.replace(tzinfo=timezone.utc) + timedelta(hours=48)
        if datetime.now(timezone.utc) > cutoff:
            raise HTTPException(status_code=400, detail="Verification link has expired — please request a new one")

    await db.execute(
        text("""
            UPDATE users.users
            SET email_verified              = TRUE,
                email_verification_token    = NULL,
                email_verification_sent_at  = NULL,
                updated_at                  = NOW()
            WHERE id = :uid
        """),
        {"uid": str(user.id)},
    )
    await db.commit()

    log.info(f"Email verified for user {user.email}")
    return {"message": "Email verified successfully! You can now close this page."}


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
                   subscription_status, subscription_ends_at, created_at,
                   email_alerts_enabled, marketing_emails_enabled, push_alerts_enabled
            FROM users.users
            WHERE id = :id
        """),
        {"id": current_user["id"]},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    admin_list = [e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()]
    return UserProfile(
        id=str(row.id),
        email=row.email,
        name=row.name,
        plan=row.plan,
        subscription_status=row.subscription_status or "inactive",
        subscription_ends_at=row.subscription_ends_at.isoformat() if row.subscription_ends_at else None,
        email_verified=row.email_verified or False,
        created_at=row.created_at.isoformat() if row.created_at else None,
        is_admin=row.email.lower() in admin_list,
        email_alerts_enabled=row.email_alerts_enabled if row.email_alerts_enabled is not None else True,
        marketing_emails_enabled=row.marketing_emails_enabled if row.marketing_emails_enabled is not None else False,
        push_alerts_enabled=row.push_alerts_enabled if row.push_alerts_enabled is not None else True,
    )
