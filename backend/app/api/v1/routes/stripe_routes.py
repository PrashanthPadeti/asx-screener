"""
ASX Screener — Stripe Billing Routes
========================================
POST /billing/checkout    — create Stripe Checkout session
POST /billing/portal      — create Stripe Customer Portal session
POST /billing/webhook     — Stripe webhook handler
GET  /billing/plans       — list available plans + pricing
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.plans import PLANS_CATALOGUE
from app.db.session import get_db

log = logging.getLogger(__name__)
router = APIRouter()

# ── Stripe price ID map (populated from env) ──────────────────────────────────
# Keys match the price_id_monthly / price_id_yearly references in PLANS_CATALOGUE

def _price_ids() -> dict[str, str]:
    """Read all Stripe price IDs from settings at call time (not import time)."""
    return {
        "STRIPE_PRO_MONTHLY":          getattr(settings, "STRIPE_PRO_MONTHLY",          ""),
        "STRIPE_PRO_YEARLY":           getattr(settings, "STRIPE_PRO_YEARLY",           ""),
        "STRIPE_PREMIUM_MONTHLY":      getattr(settings, "STRIPE_PREMIUM_MONTHLY",      ""),
        "STRIPE_PREMIUM_YEARLY":       getattr(settings, "STRIPE_PREMIUM_YEARLY",       ""),
        "STRIPE_ENT_PRO_5_MONTHLY":    getattr(settings, "STRIPE_ENT_PRO_5_MONTHLY",    ""),
        "STRIPE_ENT_PRO_5_YEARLY":     getattr(settings, "STRIPE_ENT_PRO_5_YEARLY",     ""),
        "STRIPE_ENT_PRO_10_MONTHLY":   getattr(settings, "STRIPE_ENT_PRO_10_MONTHLY",   ""),
        "STRIPE_ENT_PRO_10_YEARLY":    getattr(settings, "STRIPE_ENT_PRO_10_YEARLY",    ""),
        "STRIPE_ENT_PREM_5_MONTHLY":   getattr(settings, "STRIPE_ENT_PREM_5_MONTHLY",   ""),
        "STRIPE_ENT_PREM_5_YEARLY":    getattr(settings, "STRIPE_ENT_PREM_5_YEARLY",    ""),
        "STRIPE_ENT_PREM_10_MONTHLY":  getattr(settings, "STRIPE_ENT_PREM_10_MONTHLY",  ""),
        "STRIPE_ENT_PREM_10_YEARLY":   getattr(settings, "STRIPE_ENT_PREM_10_YEARLY",   ""),
    }

# Map Stripe price_id → (plan_code, seat_limit, billing_period)
def _build_price_plan_map() -> dict[str, tuple[str, int, str]]:
    ids = _price_ids()
    return {v: k for k, v in {
        ids["STRIPE_PRO_MONTHLY"]:         ("pro",               1,  "monthly"),
        ids["STRIPE_PRO_YEARLY"]:          ("pro",               1,  "yearly"),
        ids["STRIPE_PREMIUM_MONTHLY"]:     ("premium",           1,  "monthly"),
        ids["STRIPE_PREMIUM_YEARLY"]:      ("premium",           1,  "yearly"),
        ids["STRIPE_ENT_PRO_5_MONTHLY"]:   ("enterprise_pro",    5,  "monthly"),
        ids["STRIPE_ENT_PRO_5_YEARLY"]:    ("enterprise_pro",    5,  "yearly"),
        ids["STRIPE_ENT_PRO_10_MONTHLY"]:  ("enterprise_pro",    10, "monthly"),
        ids["STRIPE_ENT_PRO_10_YEARLY"]:   ("enterprise_pro",    10, "yearly"),
        ids["STRIPE_ENT_PREM_5_MONTHLY"]:  ("enterprise_premium", 5, "monthly"),
        ids["STRIPE_ENT_PREM_5_YEARLY"]:   ("enterprise_premium", 5, "yearly"),
        ids["STRIPE_ENT_PREM_10_MONTHLY"]: ("enterprise_premium",10, "monthly"),
        ids["STRIPE_ENT_PREM_10_YEARLY"]:  ("enterprise_premium",10, "yearly"),
    }.items() if k}  # skip empty price IDs


# ── Plans endpoint ────────────────────────────────────────────────────────────

@router.get("/plans")
async def get_plans():
    """Return full plan catalogue with resolved Stripe price IDs."""
    ids = _price_ids()
    # Inject actual price IDs into catalogue copy
    resolved = []
    for plan in PLANS_CATALOGUE:
        p = dict(plan)
        if "price_id_monthly" in p:
            p["price_id_monthly"] = ids.get(p["price_id_monthly"] or "", "") or None
            p["price_id_yearly"]  = ids.get(p["price_id_yearly"]  or "", "") or None
        if "seats_options" in p:
            p["seats_options"] = [
                {**opt,
                 "price_id_monthly": ids.get(opt["price_id_monthly"], "") or None,
                 "price_id_yearly":  ids.get(opt["price_id_yearly"],  "") or None}
                for opt in p["seats_options"]
            ]
        resolved.append(p)
    return {"plans": resolved}


# ── Checkout ──────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    price_id: str          # Stripe price ID chosen by frontend
    seats: int = 1         # 1, 5, or 10


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout session for the selected plan + billing period."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")

    # Validate price_id is one we know about
    known = set(_price_ids().values()) - {""}
    if body.price_id not in known:
        raise HTTPException(status_code=400, detail="Invalid price ID")

    import stripe as _stripe
    _stripe.api_key = settings.STRIPE_SECRET_KEY

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

    base_url = getattr(settings, "FRONTEND_URL", "http://209.38.84.102:3000")
    session = _stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": body.price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{base_url}/account?upgrade=success",
        cancel_url=f"{base_url}/account?upgrade=cancelled",
        metadata={"user_id": current_user["id"], "seats": str(body.seats)},
    )
    return {"url": session.url}


# ── Customer Portal ───────────────────────────────────────────────────────────

@router.post("/portal")
async def create_portal(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

    base_url = getattr(settings, "FRONTEND_URL", "http://209.38.84.102:3000")
    session = _stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{base_url}/account",
    )
    return {"url": session.url}


# ── Webhook ───────────────────────────────────────────────────────────────────

@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
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
        sub        = event["data"]["object"]
        sub_status = sub["status"]
        cid        = sub["customer"]
        ends       = sub.get("current_period_end")
        metadata   = event.get("data", {}).get("object", {}).get("metadata", {})
        seats      = int(metadata.get("seats", 1))

        # Determine plan from price ID
        price_id   = sub["items"]["data"][0]["price"]["id"] if sub.get("items") else ""
        price_map  = _build_price_plan_map()
        plan_info  = price_map.get(price_id)

        if sub_status in ("active", "trialing") and plan_info:
            plan, seat_limit, billing_period = plan_info
        else:
            plan, seat_limit, billing_period = "free", 1, "monthly"

        await db.execute(
            text("""
                UPDATE users.users
                SET plan = :plan,
                    subscription_status  = :status,
                    subscription_ends_at = to_timestamp(:ends),
                    billing_period       = :bp,
                    seat_limit           = :seats
                WHERE stripe_customer_id = :cid
            """),
            {"plan": plan, "status": sub_status, "ends": ends,
             "bp": billing_period, "seats": seat_limit, "cid": cid},
        )
        await db.commit()
        log.info(f"Updated to plan='{plan}' seats={seat_limit} for Stripe customer {cid}")

    elif event_type == "customer.subscription.deleted":
        cid = event["data"]["object"]["customer"]
        await db.execute(
            text("""
                UPDATE users.users
                SET plan = 'free', subscription_status = 'cancelled',
                    subscription_ends_at = NULL, seat_limit = 1
                WHERE stripe_customer_id = :cid
            """),
            {"cid": cid},
        )
        await db.commit()

    elif event_type == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        cid     = session.get("customer")
        if user_id and cid:
            await db.execute(
                text("UPDATE users.users SET stripe_customer_id = :cid WHERE id = :uid"),
                {"cid": cid, "uid": user_id},
            )
            await db.commit()

    return {"status": "ok"}
