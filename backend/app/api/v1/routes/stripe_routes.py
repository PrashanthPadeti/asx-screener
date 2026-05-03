"""
ASX Screener — Stripe Billing Routes
========================================
POST /billing/checkout    — create Stripe Checkout session (upgrade to Pro)
POST /billing/portal      — create Stripe Customer Portal session
POST /billing/webhook     — Stripe webhook handler (updates plan in DB)
GET  /billing/plans       — list available plans + pricing
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db

log = logging.getLogger(__name__)
router = APIRouter()

# ── Plan definitions ──────────────────────────────────────────────────────────

PLANS = [
    {
        "id":          "free",
        "name":        "Free",
        "price_aud":   0,
        "price_id":    None,
        "features": [
            "Screen all ~1,800 ASX stocks",
            "3 watchlists (50 stocks each)",
            "3 price alerts",
            "ASX announcements feed",
            "Composite quality scores",
        ],
    },
    {
        "id":          "pro",
        "name":        "Pro",
        "price_aud":   29,
        "price_id":    settings.STRIPE_PRO_PRICE_ID if hasattr(settings, "STRIPE_PRO_PRICE_ID") else "",
        "features": [
            "Everything in Free",
            "CSV export (up to 5,000 rows)",
            "20 watchlists (500 stocks each)",
            "50 price alerts",
            "Priority data refresh",
            "Email support",
        ],
    },
]


@router.get("/plans")
async def get_plans():
    """Return available plans. No auth required."""
    return {"plans": PLANS}


# ── Checkout ──────────────────────────────────────────────────────────────────

@router.post("/checkout")
async def create_checkout(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout session to upgrade to Pro."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")

    import stripe as _stripe
    _stripe.api_key = settings.STRIPE_SECRET_KEY

    price_id = getattr(settings, "STRIPE_PRO_PRICE_ID", "")
    if not price_id:
        raise HTTPException(status_code=503, detail="Stripe price ID not configured")

    # Get or create Stripe customer
    result = await db.execute(
        text("SELECT email, name, stripe_customer_id FROM users.users WHERE id = :id"),
        {"id": current_user["id"]},
    )
    user = result.fetchone()

    customer_id = user.stripe_customer_id
    if not customer_id:
        customer = _stripe.Customer.create(
            email=user.email,
            name=user.name or user.email,
            metadata={"user_id": current_user["id"]},
        )
        customer_id = customer.id
        await db.execute(
            text("UPDATE users.users SET stripe_customer_id = :cid WHERE id = :uid"),
            {"cid": customer_id, "uid": current_user["id"]},
        )
        await db.commit()

    session = _stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url="http://209.38.84.102:3000/account?upgrade=success",
        cancel_url="http://209.38.84.102:3000/account?upgrade=cancelled",
        metadata={"user_id": current_user["id"]},
    )
    return {"url": session.url}


# ── Customer Portal ───────────────────────────────────────────────────────────

@router.post("/portal")
async def create_portal(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Customer Portal session to manage subscription."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")

    import stripe as _stripe
    _stripe.api_key = settings.STRIPE_SECRET_KEY

    result = await db.execute(
        text("SELECT stripe_customer_id FROM users.users WHERE id = :id"),
        {"id": current_user["id"]},
    )
    user = result.fetchone()
    if not user or not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found")

    session = _stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url="http://209.38.84.102:3000/account",
    )
    return {"url": session.url}


# ── Webhook ───────────────────────────────────────────────────────────────────

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle Stripe webhook events.
    Verifies signature and updates user plan/subscription status.
    """
    if not settings.STRIPE_SECRET_KEY:
        return {"status": "ok"}

    import stripe as _stripe
    _stripe.api_key = settings.STRIPE_SECRET_KEY

    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")

    try:
        event = _stripe.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        log.warning(f"Stripe webhook signature error: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    log.info(f"Stripe event: {event_type}")

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        sub    = event["data"]["object"]
        status_str = sub["status"]
        plan   = "pro" if status_str in ("active", "trialing") else "free"
        cid    = sub["customer"]
        ends   = sub.get("current_period_end")

        await db.execute(
            text("""
                UPDATE users.users
                SET plan = :plan,
                    subscription_status = :status,
                    subscription_ends_at = to_timestamp(:ends)
                WHERE stripe_customer_id = :cid
            """),
            {"plan": plan, "status": status_str, "ends": ends, "cid": cid},
        )
        await db.commit()
        log.info(f"Updated plan to '{plan}' for Stripe customer {cid}")

    elif event_type == "customer.subscription.deleted":
        cid = event["data"]["object"]["customer"]
        await db.execute(
            text("""
                UPDATE users.users
                SET plan = 'free', subscription_status = 'cancelled',
                    subscription_ends_at = NULL
                WHERE stripe_customer_id = :cid
            """),
            {"cid": cid},
        )
        await db.commit()

    elif event_type == "checkout.session.completed":
        session    = event["data"]["object"]
        user_id    = session.get("metadata", {}).get("user_id")
        cid        = session.get("customer")
        if user_id and cid:
            await db.execute(
                text("UPDATE users.users SET stripe_customer_id = :cid WHERE id = :uid"),
                {"cid": cid, "uid": user_id},
            )
            await db.commit()

    return {"status": "ok"}
