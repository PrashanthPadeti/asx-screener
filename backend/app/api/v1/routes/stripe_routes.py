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


# ── Applying a subscription to an account ─────────────────────────────────────
#
# Entitlement used to exist in exactly one place: the webhook handler. That
# made webhook delivery a single point of failure for something the customer
# has already paid for -- and when it failed there was no path back. The
# account stayed on free, /checkout saw a NULL stripe_subscription_id, took the
# "new subscriber" branch, and created a SECOND subscription. Observed in
# production on 15 Sep 2026: one customer, two live subscriptions, two charges
# 23 minutes apart, still on free.
#
# So the logic lives here instead, and two callers use it: the webhook (fast
# path) and /billing/sync (repair path). Not a copy each -- a copy each is how
# the repair path drifts from the thing it is repairing.


def _read_subscription(sub: dict) -> dict:
    """Resolve a Stripe subscription object into the fields we store.

    ``plan`` is None when the price ID is not in our map -- almost always a
    missing or stale STRIPE_* price ID in .env. The caller must then leave the
    plan tier alone: never downgrade a paying customer over a config gap.
    """
    sub_status = sub["status"]
    price_id   = sub["items"]["data"][0]["price"]["id"] if sub.get("items") else ""
    plan_info  = _build_price_plan_map().get(price_id)
    is_active  = sub_status in ("active", "trialing")

    if is_active and plan_info:
        plan, seat_limit, billing_period = plan_info
    elif is_active:
        plan = seat_limit = billing_period = None
        log.error(
            f"Stripe price_id '{price_id}' not found in price map — leaving plan "
            f"unchanged for customer {sub.get('customer')}. Check STRIPE_* price "
            f"IDs in .env."
        )
    else:
        plan, seat_limit, billing_period = "free", 1, "monthly"

    return {
        "sub_id":         sub["id"],
        "sub_status":     sub_status,
        "cid":            sub["customer"],
        "ends":           sub.get("current_period_end"),
        "plan":           plan,
        "seat_limit":     seat_limit,
        "billing_period": billing_period,
        "price_id":       price_id,
    }


async def _plan_is_locked(db: AsyncSession, cid: str) -> bool:
    """Whether a manual grant currently outranks Stripe for this customer.

    Fails OPEN on a missing column: if migration 065 has not been applied the
    answer is "not locked", which is the behaviour that existed before. A
    billing webhook must not start returning 500 because a migration is
    outstanding -- that is the shape of the outage this whole change set
    exists to clean up.
    """
    try:
        row = await db.execute(
            text("""SELECT 1 FROM users.users
                     WHERE stripe_customer_id = :cid
                       AND plan_locked_until IS NOT NULL
                       AND plan_locked_until > NOW()"""),
            {"cid": cid},
        )
        return row.fetchone() is not None
    except Exception as e:
        log.warning(f"plan lock check unavailable ({e}); treating as unlocked")
        await db.rollback()
        return False


async def _write_subscription(db: AsyncSession, f: dict) -> None:
    """Persist the resolved subscription against the Stripe customer.

    Three branches, in priority order: an unrecognised price never touches the
    plan tier; a manual grant outranks Stripe until it expires; otherwise
    Stripe is authoritative.
    """
    if f["plan"] is None:
        # Unrecognised price ID: refresh the subscription bookkeeping but never
        # touch the plan tier, billing_period or seat_limit.
        await db.execute(
            text("""
                UPDATE users.users
                SET subscription_status       = :status,
                    subscription_ends_at      = to_timestamp(:ends),
                    stripe_subscription_id    = :sub_id,
                    subscription_inactive_since = NULL,
                    data_deletion_scheduled_at  = NULL
                WHERE stripe_customer_id = :cid
            """),
            {"status": f["sub_status"], "ends": f["ends"],
             "sub_id": f["sub_id"], "cid": f["cid"]},
        )
    elif await _plan_is_locked(db, f["cid"]):
        # A human granted this plan and said until when. Record everything
        # factual about the subscription -- it is still true, and billing needs
        # it -- but do not recompute the entitlement from the price map, and
        # never shorten the granted end date.
        #
        # GREATEST, not assignment: if Stripe's period runs past the grant
        # (they kept paying beyond it) the later date is the honest one.
        # subscription_status is NOT copied from Stripe here, and that is
        # deliberate. It is not a billing field -- require_plan() gates access
        # on it, so writing Stripe's 'canceled' or 'past_due' onto a granted
        # account would revoke the grant through the back door while plan
        # still read 'premium'. The grant is a promise about access, so while
        # it holds, access is active.
        await db.execute(
            text("""
                UPDATE users.users
                SET subscription_status    = 'active',
                    stripe_subscription_id = :sub_id,
                    subscription_ends_at   = GREATEST(
                        subscription_ends_at, to_timestamp(:ends)),
                    subscription_inactive_since = NULL,
                    data_deletion_scheduled_at  = NULL
                WHERE stripe_customer_id = :cid
            """),
            {"ends": f["ends"], "sub_id": f["sub_id"], "cid": f["cid"]},
        )
        log.info(
            f"Plan locked for customer {f['cid']} — Stripe says "
            f"'{f['plan']}' but a manual grant is in force; entitlement "
            f"left as granted, subscription bookkeeping updated."
        )
    else:
        # :is_free is computed here rather than asked of the database as
        # `:plan = 'free'`.
        #
        # That comparison is what took subscription upgrades down completely.
        # Binding :plan twice — once assigned to a VARCHAR(20) column, once
        # compared against a bare literal — made PostgreSQL deduce two types
        # for one placeholder:
        #
        #   asyncpg.exceptions.AmbiguousParameterError:
        #     inconsistent types deduced for parameter $1
        #     DETAIL: text versus character varying
        #
        # The statement could not even be prepared, so every
        # customer.subscription.created and .updated event returned 500 while
        # the other webhook branches returned 200. No account could be
        # upgraded by any route, and because a failed upgrade leaves
        # stripe_subscription_id NULL, /checkout then treated each retry as a
        # new subscriber and started another paid subscription.
        #
        # A bound boolean removes the deduction entirely. The rule this
        # follows: never bind one parameter into both an assignment and a
        # predicate in the same statement — compute the predicate in Python
        # and bind its result.
        await db.execute(
            text("""
                UPDATE users.users
                SET plan                      = :plan,
                    subscription_status       = :status,
                    subscription_ends_at      = to_timestamp(:ends),
                    billing_period            = :bp,
                    seat_limit                = :seats,
                    stripe_subscription_id    = :sub_id,
                    subscription_inactive_since = CASE WHEN :is_free THEN NOW() ELSE NULL END,
                    data_deletion_scheduled_at  = CASE WHEN :is_free THEN NOW() + INTERVAL '12 months' ELSE NULL END
                WHERE stripe_customer_id = :cid
            """),
            {"plan": f["plan"], "status": f["sub_status"], "ends": f["ends"],
             "bp": f["billing_period"], "seats": f["seat_limit"],
             "sub_id": f["sub_id"], "cid": f["cid"],
             "is_free": f["plan"] == "free"},
        )
    await db.commit()


async def _claim_founding_member(db: AsyncSession, user_row, f: dict) -> int | None:
    """Claim the next founding-member slot, if the offer still has room.

    Returns the slot number granted, or None. Safe to call more than once for
    the same user: the caller checks is_founding_member first, and the claim
    itself is a single atomic statement bounded by the limit.
    """
    founding_limit = getattr(settings, "FOUNDING_MEMBER_LIMIT", 100)
    if not (founding_limit > 0 and user_row
            and f["plan"] not in (None, "free")
            and f["sub_status"] in ("active", "trialing")
            and not getattr(user_row, "is_founding_member", False)):
        return None
    try:
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
            "billing_period": f["billing_period"],
            "uid":   user_row.id,
            "limit": founding_limit,
        })
        await db.commit()
        slot = claim_result.scalar()
        if slot:
            log.info(f"Founding member #{slot} granted to user {user_row.id} "
                     f"(plan={f['plan']} interval={f['billing_period']})")
        else:
            log.info(f"Founding member limit ({founding_limit}) already reached — "
                     f"no bonus for user {user_row.id}")
        return slot
    except Exception as fm_err:
        log.warning(f"Founding member bonus failed (non-fatal): {fm_err}")
        await db.rollback()
        return None


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

    # ── Last guard before creating a second subscription ─────────────────────
    #
    # Everything above decided "new subscriber" from OUR row. If that row is
    # stale -- which is precisely what a lost webhook leaves behind -- the
    # decision is wrong and the cost lands on the customer: a second live
    # subscription and a second monthly charge, for a plan they already bought.
    # That happened on 15 Sep 2026: two subscriptions 23 minutes apart, while
    # the account showed free.
    #
    # So ask Stripe, which knows, rather than trusting the cache we already
    # know can be stale. A subscription found here is adopted into our row and
    # modified in place, never duplicated.
    try:
        existing = _stripe.Subscription.list(
            customer=customer_id, status="active", limit=10)
        live = list(existing.data) or []
    except Exception as e:
        # Do not block a legitimate purchase because the check failed; log it
        # and fall through. This guard prevents a duplicate, it is not the
        # authority on whether checkout may proceed.
        log.warning(f"Pre-checkout subscription check failed for {customer_id}: {e}")
        live = []

    if live:
        adopted = sorted(live, key=lambda s: s["created"])[0]
        log.warning(
            f"Pre-checkout guard: customer {customer_id} already has "
            f"{len(live)} active subscription(s) {[s['id'] for s in live]} "
            f"while our row had stripe_subscription_id={sub_id!r}. Modifying "
            f"{adopted['id']} in place instead of creating another."
        )
        try:
            item_id = adopted["items"]["data"][0]["id"]
            _stripe.Subscription.modify(
                adopted["id"],
                items=[{"id": item_id, "price": price_id}],
                proration_behavior="create_prorations",
                metadata={"user_id": str(current_user["id"]), "seats": str(body.seats)},
            )
            await db.execute(
                text("""UPDATE users.users SET stripe_subscription_id = :sid
                        WHERE id = :uid"""),
                {"sid": adopted["id"], "uid": current_user["id"]},
            )
            await db.commit()
            return {"url": f"{base_url}/account?upgrade=success"}
        except Exception as e:
            log.error(
                f"Could not modify adopted subscription {adopted['id']}: {e}. "
                f"Refusing to create a duplicate — sending the customer to the "
                f"billing portal instead."
            )
            # Deliberately not falling through to Checkout. Failing to change a
            # subscription is recoverable; charging twice is not.
            raise HTTPException(
                status_code=409,
                detail="You already have an active subscription. Please use "
                       "Manage Billing to change your plan, or contact support.",
            )

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


# ── Sync: repair an account from Stripe ───────────────────────────────────────


@router.post("/sync")
async def sync_subscription(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reconcile this account against Stripe, and apply whatever Stripe says.

    Stripe is the record of what the customer paid for; our row is a cache of
    it. Until now that cache could only ever be written by an inbound webhook,
    so a webhook that was never delivered -- a wrong STRIPE_WEBHOOK_SECRET, an
    endpoint registered in test mode only, an outage -- left a paying customer
    on free with no way back except a manual database edit.

    Safe to call repeatedly: it reads the live subscription and applies the
    same mapping the webhook applies, so calling it when nothing is wrong
    writes the values that are already there.

    It will not invent a subscription. If Stripe has no active subscription
    for this customer, the account is left exactly as it is -- this endpoint
    repairs a missed source, it does not grant entitlement.
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")

    import stripe as _stripe
    _stripe.api_key = settings.STRIPE_SECRET_KEY

    result = await db.execute(
        text("""SELECT id, email, plan, is_founding_member, stripe_customer_id
                FROM users.users WHERE id = :id"""),
        {"id": current_user["id"]},
    )
    user_row = result.fetchone()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")

    cid = user_row.stripe_customer_id
    if not cid:
        # The customer row is created by /checkout before the session, so a
        # missing one normally means they never started checkout. Look them up
        # by email anyway: a customer created through a payment link or the
        # Stripe dashboard has no user_id metadata and would otherwise be
        # invisible to us forever.
        try:
            found = _stripe.Customer.list(email=user_row.email, limit=1)
            cid = found.data[0].id if found.data else None
        except Exception as e:
            log.warning(f"Stripe customer lookup failed for {user_row.email}: {e}")
            cid = None
        if not cid:
            return {"synced": False, "reason": "no_stripe_customer",
                    "plan": user_row.plan}
        await db.execute(
            text("UPDATE users.users SET stripe_customer_id = :cid WHERE id = :uid"),
            {"cid": cid, "uid": user_row.id},
        )
        await db.commit()
        log.info(f"Sync linked Stripe customer {cid} to user {user_row.id} by email")

    try:
        subs = _stripe.Subscription.list(customer=cid, status="all", limit=100)
    except Exception as e:
        log.error(f"Stripe subscription list failed for customer {cid}: {e}")
        raise HTTPException(status_code=502, detail="Could not reach payment provider")

    live = [s for s in subs.data if s["status"] in ("active", "trialing")]
    if not live:
        return {"synced": False, "reason": "no_active_subscription",
                "plan": user_row.plan}

    # More than one live subscription means the customer is being billed twice
    # -- the exact damage a lost webhook causes, because /checkout reads a NULL
    # stripe_subscription_id and starts a second one. We cannot cancel or
    # refund from here; that is a decision with money attached. Report it
    # loudly, apply the earliest (the one they meant to buy), and let an
    # operator resolve the duplicate.
    if len(live) > 1:
        log.error(
            f"DUPLICATE SUBSCRIPTIONS: customer {cid} (user {user_row.id}, "
            f"{user_row.email}) has {len(live)} active subscriptions: "
            f"{[s['id'] for s in live]}. The customer is being charged more "
            f"than once. Needs manual cancellation and refund in Stripe."
        )

    chosen = sorted(live, key=lambda s: s["created"])[0]
    f = _read_subscription(chosen)
    await _write_subscription(db, f)
    await _claim_founding_member(db, user_row, f)

    log.info(
        f"Sync applied subscription {f['sub_id']} to user {user_row.id}: "
        f"plan='{f['plan']}' status='{f['sub_status']}' "
        f"interval='{f['billing_period']}'"
    )
    return {
        "synced": True,
        "plan": f["plan"] if f["plan"] is not None else user_row.plan,
        "status": f["sub_status"],
        "billing_period": f["billing_period"],
        "duplicate_subscriptions": len(live) if len(live) > 1 else 0,
        # Same caveat as the admin grant: access is decided by the signed JWT,
        # so the caller must refresh before the new plan is visible.
        "takes_effect": (
            "on the next token refresh (within "
            f"{settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes), or immediately "
            "on sign out and back in"
        ),
    }


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
        sub = event["data"]["object"]
        f   = _read_subscription(sub)

        result = await db.execute(
            text("SELECT id, plan, is_founding_member FROM users.users WHERE stripe_customer_id = :cid"),
            {"cid": f["cid"]},
        )
        user_row = result.fetchone()

        if not user_row:
            log.error(
                f"Stripe {event_type}: no user found with stripe_customer_id={f['cid']} — "
                f"subscription {f['sub_id']} not applied to any account."
            )

        await _write_subscription(db, f)

        effective_plan = f["plan"] if f["plan"] is not None else (user_row.plan if user_row else None)
        if user_row:
            await _log_event(str(user_row.id), event_type, user_row.plan, effective_plan, event["id"])
            await db.commit()
        log.info(
            f"Subscription {f['sub_id']} updated: plan='{effective_plan}'"
            f"{' (unchanged — unknown price)' if f['plan'] is None else ''} "
            f"status='{f['sub_status']}' interval='{f['billing_period']}' for customer {f['cid']}"
        )

        # ── Founding Member bonus (new subscriptions only, active plan only) ──
        if event_type == "customer.subscription.created":
            await _claim_founding_member(db, user_row, f)

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

        # A courtesy grant must outlive the subscription that occasioned it.
        # Someone compensated for an outage with three years of Premium does
        # not lose it by cancelling the paid plan they were unhappy with --
        # that would revoke the apology along with the subscription.
        if await _plan_is_locked(db, cid):
            await db.execute(
                text("""
                    UPDATE users.users
                    SET subscription_status         = 'active',
                        stripe_subscription_id      = NULL,
                        subscription_inactive_since = NULL,
                        data_deletion_scheduled_at  = NULL
                    WHERE stripe_customer_id = :cid
                """),
                {"cid": cid},
            )
            await db.commit()
            log.info(
                f"Subscription {sub_id} cancelled for customer {cid} — plan "
                f"retained under a manual grant, not downgraded to free. "
                f"stripe_subscription_id cleared so a future purchase starts "
                f"a fresh subscription."
            )
            return {"status": "ok"}

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
