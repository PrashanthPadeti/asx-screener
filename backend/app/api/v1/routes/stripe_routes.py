"""
ASX Screener — Stripe Billing Routes
========================================
POST /billing/checkout    — create Stripe Checkout session (or upgrade existing sub)
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


def _build_price_plan_map() -> dict[str, tuple[str, int, str]]:
    """Map Stripe price_id → (plan_code, seat_limit, billing_period)."""
    ids = _price_ids()
    return {k: v for k, v in {
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

@router.get("/founding-member-status")
async def founding_member_status(db: AsyncSession = Depends(get_db)):
    """
    Public endpoint — no auth required.
    Returns how many founding-member slots have been claimed and how many remain.
    """
    limit = settings.FOUNDING_MEMBER_LIMIT
    if limit <= 0:
        return {"enabled": False, "limit": 0, "claimed": 0, "remaining": 0, "available": False}

    result = await db.execute(
        text("SELECT COUNT(*) FROM users.users WHERE is_founding_member = TRUE")
    )
    claimed = result.scalar() or 0
    remaining = max(0, limit - claimed)
    return {
        "enabled":   True,
        "limit":     limit,
        "claimed":   claimed,
        "remaining": remaining,
        "available": remaining > 0,
    }


@router.get("/plans")
async def get_plans():
    """Return full plan catalogue with resolved Stripe price IDs."""
    ids = _price_ids()
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
    plan: str              # e.g. "pro" | "premium"
    interval: str = "monthly"  # "monthly" | "yearly"
    seats: int = 1         # 1, 5, or 10


# Map (plan, interval) → price key name in _price_ids()
_PLAN_INTERVAL_TO_KEY: dict[tuple[str, str], str] = {
    ("pro",               "monthly"): "STRIPE_PRO_MONTHLY",
    ("pro",               "yearly"):  "STRIPE_PRO_YEARLY",
    ("premium",           "monthly"): "STRIPE_PREMIUM_MONTHLY",
    ("premium",           "yearly"):  "STRIPE_PREMIUM_YEARLY",
    ("enterprise_pro",    "monthly"): "STRIPE_ENT_PRO_5_MONTHLY",
    ("enterprise_pro",    "yearly"):  "STRIPE_ENT_PRO_5_YEARLY",
    ("enterprise_premium","monthly"): "STRIPE_ENT_PREM_5_MONTHLY",
    ("enterprise_premium","yearly"):  "STRIPE_ENT_PREM_5_YEARLY",
}

# Statuses that mean an existing subscription can be modified (upgraded/downgraded)
_UPGRADEABLE_STATUSES = {"active", "trialing", "past_due"}


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    For new subscribers: create a Stripe Checkout session (redirect to Stripe).
    For existing subscribers: modify the current subscription in-place (no redirect needed).
    This prevents duplicate subscriptions when upgrading or changing billing interval.
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")

    # Resolve plan + interval → Stripe price ID
    price_key = _PLAN_INTERVAL_TO_KEY.get((body.plan, body.interval))
    if not price_key:
        raise HTTPException(status_code=400, detail="Invalid plan or interval")
    price_id = _price_ids().get(price_key, "")
    if not price_id:
        raise HTTPException(status_code=400, detail="Price not configured for this plan")

    import stripe as _stripe
    _stripe.api_key = settings.STRIPE_SECRET_KEY

    result = await db.execute(
        text("""
            SELECT email, name, stripe_customer_id, stripe_subscription_id, subscription_status
            FROM users.users WHERE id = :id
        """),
        {"id": current_user["id"]},
    )
    user = result.fetchone()

    base_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")

    # ── Existing subscriber: modify in-place ──────────────────────────────────
    sub_id = getattr(user, "stripe_subscription_id", None)
    if sub_id and getattr(user, "subscription_status", None) in _UPGRADEABLE_STATUSES:
        try:
            sub = _stripe.Subscription.retrieve(sub_id)
            if sub.status in _UPGRADEABLE_STATUSES:
                item_id = sub["items"]["data"][0]["id"]
                _stripe.Subscription.modify(
                    sub_id,
                    items=[{"id": item_id, "price": price_id}],
                    proration_behavior="create_prorations",
                    metadata={"user_id": str(current_user["id"]), "seats": str(body.seats)},
                )
                log.info(
                    f"Subscription {sub_id} modified to price {price_id} "
                    f"(plan={body.plan} interval={body.interval}) for user {current_user['id']}"
                )
                # Webhook (customer.subscription.updated) will update the DB plan automatically.
                return {"url": f"{base_url}/account?upgrade=success"}
        except Exception as e:
            # Subscription gone or invalid — fall through to new checkout session
            log.warning(f"Could not modify subscription {sub_id}: {e}. Creating new checkout session.")

    # ── New subscriber (or subscription lapsed): create Checkout session ──────
    customer_id = getattr(user, "stripe_customer_id", None)
    if not customer_id:
        customer = _stripe.Customer.create(
            email=user.email,
            name=user.name or user.email,
            metadata={"user_id": str(current_user["id"])},
        )
        customer_id = customer.id
        await db.execute(
            text("UPDATE users.users SET stripe_customer_id = :cid WHERE id = :uid"),
            {"cid": customer_id, "uid": current_user["id"]},
        )
        await db.commit()

    try:
        session = _stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{base_url}/account?upgrade=success",
            cancel_url=f"{base_url}/pricing?upgrade=cancelled",
            metadata={"user_id": str(current_user["id"]), "seats": str(body.seats)},
        )
    except _stripe.error.AuthenticationError:
        log.error("Stripe AuthenticationError — check STRIPE_SECRET_KEY")
        raise HTTPException(status_code=503, detail="Payment provider authentication failed — contact support")
    except _stripe.error.InvalidRequestError as e:
        log.error(f"Stripe InvalidRequestError: {e}")
        raise HTTPException(status_code=400, detail=f"Payment configuration error: {e.user_message or str(e)}")
    except _stripe.error.StripeError as e:
        log.error(f"Stripe error during checkout: {e}")
        raise HTTPException(status_code=502, detail=f"Payment provider error: {e.user_message or 'Please try again shortly'}")
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

    base_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
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

    async def _log_event(user_id: str, ev_type: str, old_plan: str, new_plan: str, stripe_event_id: str):
        """Write to subscription_events audit table if it exists."""
        try:
            await db.execute(text("""
                INSERT INTO users.subscription_events
                    (user_id, event_type, old_plan, new_plan, stripe_event_id)
                VALUES (:uid, :et, :op, :np, :eid)
            """), {"uid": user_id, "et": ev_type, "op": old_plan, "np": new_plan, "eid": stripe_event_id})
        except Exception:
            pass  # table may not exist yet

    # ── Subscription created / updated ────────────────────────────────────────
    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        sub        = event["data"]["object"]
        sub_id     = sub["id"]
        sub_status = sub["status"]
        cid        = sub["customer"]
        ends       = sub.get("current_period_end")
        metadata   = sub.get("metadata", {})
        seats      = int(metadata.get("seats", 1))

        price_id  = sub["items"]["data"][0]["price"]["id"] if sub.get("items") else ""
        price_map = _build_price_plan_map()
        plan_info = price_map.get(price_id)

        if sub_status in ("active", "trialing") and plan_info:
            plan, seat_limit, billing_period = plan_info
        else:
            plan, seat_limit, billing_period = "free", 1, "monthly"

        result = await db.execute(
            text("SELECT id, plan, is_founding_member FROM users.users WHERE stripe_customer_id = :cid"),
            {"cid": cid},
        )
        user_row = result.fetchone()

        await db.execute(
            text("""
                UPDATE users.users
                SET plan                      = :plan,
                    subscription_status       = :status,
                    subscription_ends_at      = to_timestamp(:ends),
                    billing_period            = :bp,
                    seat_limit                = :seats,
                    stripe_subscription_id    = :sub_id,
                    subscription_inactive_since = CASE WHEN :plan = 'free' THEN NOW() ELSE NULL END,
                    data_deletion_scheduled_at  = CASE WHEN :plan = 'free' THEN NOW() + INTERVAL '12 months' ELSE NULL END
                WHERE stripe_customer_id = :cid
            """),
            {"plan": plan, "status": sub_status, "ends": ends,
             "bp": billing_period, "seats": seat_limit, "sub_id": sub_id, "cid": cid},
        )
        await db.commit()
        if user_row:
            await _log_event(str(user_row.id), event_type, user_row.plan, plan, event["id"])
            await db.commit()
        log.info(
            f"Subscription {sub_id} updated: plan='{plan}' status='{sub_status}' "
            f"interval='{billing_period}' for customer {cid}"
        )

        # ── Founding Member bonus (new subscriptions only, active plan only) ──
        founding_limit = getattr(settings, "FOUNDING_MEMBER_LIMIT", 100)
        is_new_sub     = event_type == "customer.subscription.created"
        is_paid_plan   = plan not in ("free",)
        already_member = getattr(user_row, "is_founding_member", False) if user_row else False

        if (founding_limit > 0 and is_new_sub and is_paid_plan
                and sub_status in ("active", "trialing") and user_row and not already_member):
            try:
                # Atomically claim the next founding-member slot (if any remain)
                claim_result = await db.execute(text("""
                    WITH next_slot AS (
                        SELECT COALESCE(MAX(founding_member_number), 0) + 1 AS slot_num
                        FROM users.users
                        WHERE is_founding_member = TRUE
                    )
                    UPDATE users.users
                    SET is_founding_member     = TRUE,
                        founding_member_number = (SELECT slot_num FROM next_slot),
                        subscription_ends_at   = CASE
                            WHEN :billing_period = 'monthly'
                                THEN NOW() + INTERVAL '6 months'
                            ELSE
                                NOW() + INTERVAL '3 years'
                        END
                    WHERE id = :uid
                      AND (SELECT slot_num FROM next_slot) <= :limit
                    RETURNING founding_member_number
                """), {
                    "billing_period": billing_period,
                    "uid":   user_row.id,
                    "limit": founding_limit,
                })
                await db.commit()
                slot = claim_result.scalar()
                if slot:
                    log.info(
                        f"Founding member #{slot} granted to user {user_row.id} "
                        f"(plan={plan} interval={billing_period})"
                    )
                else:
                    log.info(
                        f"Founding member limit ({founding_limit}) already reached — "
                        f"no bonus for user {user_row.id}"
                    )
            except Exception as fm_err:
                log.warning(f"Founding member bonus failed (non-fatal): {fm_err}")
                await db.rollback()

    # ── Subscription cancelled ────────────────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        sub = event["data"]["object"]
        cid = sub["customer"]
        sub_id = sub["id"]

        result = await db.execute(
            text("SELECT id, plan FROM users.users WHERE stripe_customer_id = :cid"),
            {"cid": cid},
        )
        user_row = result.fetchone()

        await db.execute(
            text("""
                UPDATE users.users
                SET plan                      = 'free',
                    subscription_status       = 'cancelled',
                    subscription_ends_at      = NULL,
                    seat_limit                = 1,
                    stripe_subscription_id    = NULL,
                    subscription_inactive_since     = NOW(),
                    data_deletion_scheduled_at      = NOW() + INTERVAL '12 months',
                    deletion_reminder_30d_sent      = FALSE,
                    deletion_reminder_7d_sent       = FALSE,
                    deletion_reminder_1d_sent       = FALSE
                WHERE stripe_customer_id = :cid
                  AND (stripe_subscription_id = :sub_id OR stripe_subscription_id IS NULL)
            """),
            {"cid": cid, "sub_id": sub_id},
        )
        await db.commit()
        if user_row:
            await _log_event(str(user_row.id), "cancelled", user_row.plan, "free", event["id"])
            await db.commit()
        log.info(f"Subscription {sub_id} cancelled for customer {cid} — downgraded to free")

    # ── Payment failed ────────────────────────────────────────────────────────
    elif event_type == "invoice.payment_failed":
        cid = event["data"]["object"]["customer"]
        await db.execute(
            text("UPDATE users.users SET subscription_status = 'past_due' WHERE stripe_customer_id = :cid"),
            {"cid": cid},
        )
        await db.commit()
        log.warning(f"Payment failed for customer {cid} — marked past_due")

    # ── Payment succeeded ─────────────────────────────────────────────────────
    elif event_type == "invoice.payment_succeeded":
        cid = event["data"]["object"]["customer"]
        await db.execute(
            text("""
                UPDATE users.users
                SET subscription_inactive_since = NULL,
                    data_deletion_scheduled_at  = NULL,
                    deletion_reminder_30d_sent  = FALSE,
                    deletion_reminder_7d_sent   = FALSE,
                    deletion_reminder_1d_sent   = FALSE
                WHERE stripe_customer_id = :cid
            """),
            {"cid": cid},
        )
        await db.commit()

    # ── Checkout completed: store customer ID and subscription ID ─────────────
    elif event_type == "checkout.session.completed":
        session    = event["data"]["object"]
        user_id    = session.get("metadata", {}).get("user_id")
        cid        = session.get("customer")
        sub_id     = session.get("subscription")  # present for mode=subscription
        if user_id and cid:
            await db.execute(
                text("""
                    UPDATE users.users
                    SET stripe_customer_id     = :cid,
                        stripe_subscription_id = COALESCE(:sub_id, stripe_subscription_id)
                    WHERE id = :uid
                """),
                {"cid": cid, "sub_id": sub_id, "uid": user_id},
            )
            await db.commit()
            log.info(f"Checkout completed: customer={cid} subscription={sub_id} user={user_id}")

    return {"status": "ok"}
