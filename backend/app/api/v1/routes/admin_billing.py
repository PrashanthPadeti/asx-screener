"""
Admin: the paying customers, as Stripe sees them
================================================
Why this exists, concretely:

On 26 Oct 2026 a Premium subscriber had turned off auto-renewal. His
subscription was set to end on 22 November. Every local record said
`subscription_status = active`, `subscription_ends_at = NULL` -- a perfectly
healthy subscriber -- because Stripe does not fire
`customer.subscription.deleted` until the period actually ends. The
cancellation was invisible here until the day it took effect, and was only
found by reading Stripe directly.

So this page does not trust one source. It reads BOTH and shows where they
disagree:

    Stripe    is the truth for BILLING  -- what is charged, when, and whether
                                           it will renew
    database  is the truth for ACCESS   -- what the application lets them do

A row where those disagree is not a cosmetic problem. `plan` drives
entitlement; `cancel_at_period_end` drives revenue. A customer can be paying
while the app denies them features, or have access while nothing is being
charged, and neither shows up anywhere else.

Unknown is displayed as unknown
-------------------------------
If Stripe cannot be reached, rows still render with their database state and
the Stripe fields are explicitly `null` with `stripe_error` set. They are
never shown as zero, inactive or "no subscription" -- a failure to OBTAIN
the billing state is a different fact from a customer HAVING no billing
state, and a dashboard that conflates them tells you the business shrank.

Cost
----
One `Subscription.list` for the whole page rather than one call per row, so
the list view is 1-2 Stripe calls regardless of customer count. Invoice
history is fetched per customer, only when one is opened.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import require_admin
from app.db.session import get_db

log = logging.getLogger(__name__)
router = APIRouter()

#: Plans that represent money. `free` is not a customer for this page's
#: purposes; admin/users already lists everyone.
PAID_PLANS = ("pro", "premium", "enterprise")


def _stripe_client():
    """The Stripe SDK, configured. None when no key is set.

    Returning None rather than raising lets the endpoint answer with
    database state and an explicit `stripe_error`, which is more useful than
    a 500 that tells the admin nothing about their customers.
    """
    if not settings.STRIPE_SECRET_KEY:
        return None
    import stripe as _stripe
    _stripe.api_key = settings.STRIPE_SECRET_KEY
    return _stripe


def _ts(epoch) -> str | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _fetch_all_subscriptions() -> dict:
    """{customer_id: subscription} for every subscription Stripe knows.

    SYNCHRONOUS -- the Stripe SDK blocks. Always called through
    asyncio.to_thread: this module is imported by the API process, and a
    blocking network call on the event loop stops the whole site answering,
    which is the exact failure this codebase has a test suite devoted to.

    `status="all"` deliberately. Filtering to active would hide the
    cancelled and past_due customers, who are the ones an admin most needs
    to see.
    """
    stripe = _stripe_client()
    if stripe is None:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")

    grouped: dict[str, list] = {}
    subs = stripe.Subscription.list(status="all", limit=100)
    for s in subs.auto_paging_iter():
        grouped.setdefault(s.get("customer"), []).append(s)

    # The count travels with the representative. A customer holding several
    # subscription objects is worth seeing -- it is how a double-charge, a
    # stranded checkout or a comped trial beside a cancelled original shows
    # up -- and showing only one of them silently hides the rest.
    return {cid: (_pick_representative(items), len(items))
            for cid, items in grouped.items()}


#: Which subscription represents a customer who holds several, most live
#: first. A duplicate checkout, a comped year implemented as a trial, or a
#: plan change all leave more than one object behind.
#:
#: "active" alone is not enough, and the gap was not theoretical: a customer
#: who had been granted a year of Premium as a TRIAL (running to Sep 2027)
#: alongside the CANCELLED duplicate from his double-charge was displayed as
#: "Ended" on 26 Oct 2026, with the cancelled subscription's price and a
#: billing date in the past. A kept promise rendered as churn.
_LIVENESS = {
    "active": 0, "trialing": 1, "past_due": 2, "unpaid": 3,
    "incomplete": 4, "paused": 5, "canceled": 6, "incomplete_expired": 7,
}


def _pick_representative(items: list) -> dict:
    """Most-live first; among equals, most recently created."""
    return sorted(
        items,
        key=lambda s: (_LIVENESS.get(s.get("status"), 9),
                       -(s.get("created") or 0)),
    )[0]


def _shape_subscription(s: dict) -> dict:
    """The billing facts, flattened. Amounts stay in minor units."""
    item = (s.get("items", {}).get("data") or [{}])[0]
    price = item.get("price") or {}
    rec = price.get("recurring") or {}
    discount = s.get("discount") or {}
    coupon = discount.get("coupon") or {}

    return {
        "subscription_id":     s.get("id"),
        "status":              s.get("status"),
        "amount_minor":        price.get("unit_amount"),
        "currency":            (price.get("currency") or "").upper(),
        "interval":            rec.get("interval"),
        "interval_count":      rec.get("interval_count", 1),
        "current_period_start": _ts(s.get("current_period_start")),
        "next_billing_date":   _ts(s.get("current_period_end")),
        "cancel_at_period_end": bool(s.get("cancel_at_period_end")),
        "canceled_at":         _ts(s.get("canceled_at")),
        "trial_end":           _ts(s.get("trial_end")),
        "started_at":          _ts(s.get("start_date") or s.get("created")),
        "discount":            coupon.get("name") or coupon.get("id"),
        "price_id":            price.get("id"),
    }


def _lifecycle(db_row: dict, sub: dict | None) -> str:
    """One word for what is actually happening to this customer.

    `status` alone is not enough: Stripe reports a subscription as "active"
    right up to the moment it ends, so a customer who has turned off
    auto-renewal is indistinguishable from a continuing one by status. That
    is precisely how a pending cancellation stayed invisible.
    """
    if sub is None:
        return "no_subscription"
    status = sub.get("status")
    if status == "active" and sub.get("cancel_at_period_end"):
        return "cancelling"          # paying now, will not renew
    if status == "trialing":
        return "trialing"
    if status in ("past_due", "unpaid", "incomplete"):
        return "payment_failing"
    if status in ("canceled", "incomplete_expired"):
        return "ended"
    return status or "unknown"


def _mrr_minor(sub: dict | None) -> int:
    """Monthly recurring revenue in minor units, annuals divided down.

    Counted as zero once cancellation is scheduled: that revenue is leaving,
    and an MRR figure that includes it overstates the business by exactly
    the amount you would most want to know about.
    """
    # Trials are excluded: no cash arrives until they convert, and the ones
    # in this account are comped years granted as trials -- counting them
    # would book goodwill as revenue.
    if not sub or sub.get("status") != "active":
        return 0
    if sub.get("cancel_at_period_end"):
        return 0
    amount = sub.get("amount_minor") or 0
    count = sub.get("interval_count") or 1
    interval = sub.get("interval")
    if interval == "month":
        return int(amount / count)
    if interval == "year":
        return int(amount / (12 * count))
    if interval == "week":
        return int(amount * 52 / 12 / count)
    return 0


def _drift(db_row: dict, sub: dict | None) -> list[str]:
    """Where the application and Stripe disagree.

    Each entry is a sentence an admin can act on, not a field name.
    """
    out: list[str] = []
    db_plan = (db_row.get("plan") or "free").lower()
    db_status = (db_row.get("subscription_status") or "").lower()

    if sub is None:
        if db_plan in PAID_PLANS and not db_row.get("plan_locked_until"):
            out.append(
                f"app grants {db_plan} but Stripe has no subscription — "
                f"unpaid access")
        return out

    paying = sub.get("status") in ("active", "trialing")

    if sub.get("cancel_at_period_end") and db_status == "active":
        out.append(
            f"cancelling on {(sub.get('next_billing_date') or '')[:10]} — the "
            f"app still shows 'active' and will until that date")

    if not paying and db_plan in PAID_PLANS and not db_row.get("plan_locked_until"):
        out.append(
            f"Stripe subscription is {sub.get('status')} but the app still "
            f"grants {db_plan}")

    if paying and db_plan not in PAID_PLANS:
        out.append(
            f"paying for a subscription but the app grants '{db_plan}' — "
            f"entitlement is being denied to a paying customer")

    if sub.get("status") in ("past_due", "unpaid"):
        out.append("payment is failing — card likely expired or declined")

    return out


@router.get("/subscribers")
async def list_subscribers(
    include_lapsed: bool = Query(
        True, description="Include customers whose subscription has ended"),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Every customer who has ever had a Stripe customer record or a paid plan."""
    rows = (await db.execute(text("""
        SELECT u.id, u.email, u.name, u.plan, u.subscription_status,
               u.billing_period, u.created_at, u.last_login_at,
               u.stripe_customer_id, u.stripe_subscription_id,
               u.subscription_ends_at, u.subscription_inactive_since,
               u.plan_locked_until, u.plan_locked_reason,
               u.is_founding_member, u.founding_member_number,
               u.default_currency, u.email_verified
          FROM users.users u
         WHERE u.stripe_customer_id IS NOT NULL
            OR lower(coalesce(u.plan, 'free')) IN ('pro', 'premium', 'enterprise')
         ORDER BY u.created_at DESC
    """))).mappings().all()

    # One Stripe round trip for the whole page. Failure is reported, not
    # swallowed: the rows still render from the database with the billing
    # fields explicitly absent.
    subs_by_customer: dict = {}
    stripe_error: str | None = None
    try:
        subs_by_customer = await asyncio.to_thread(_fetch_all_subscriptions)
    except Exception as exc:                                   # noqa: BLE001
        stripe_error = f"{type(exc).__name__}: {exc}"
        log.warning("admin/billing: could not read Stripe: %s", stripe_error)

    out = []
    mrr_total = 0
    for r in rows:
        entry = subs_by_customer.get(r["stripe_customer_id"])
        raw, held = entry if entry else (None, 0)
        sub = _shape_subscription(raw) if raw else None
        if sub is not None:
            sub["subscriptions_held"] = held
        lifecycle = _lifecycle(dict(r), sub) if stripe_error is None else "unknown"
        mrr = _mrr_minor(sub)
        mrr_total += mrr

        if not include_lapsed and lifecycle in ("ended", "no_subscription"):
            continue

        out.append({
            "user_id":          str(r["id"]),
            "email":            r["email"],
            "name":             r["name"],
            "joined":           _iso(r["created_at"]),
            "last_login":       _iso(r["last_login_at"]),
            "email_verified":   r["email_verified"],

            # What the application grants right now.
            "app_plan":            r["plan"],
            "app_status":          r["subscription_status"],
            "app_billing_period":  r["billing_period"],
            "app_access_until":    _iso(r["subscription_ends_at"]),
            "plan_locked_until":   _iso(r["plan_locked_until"]),
            "plan_locked_reason":  r["plan_locked_reason"],
            "is_founding_member":  r["is_founding_member"],
            "founding_number":     r["founding_member_number"],

            # What Stripe is actually doing. null when unobtainable.
            "stripe_customer_id":  r["stripe_customer_id"],
            "stripe":              sub,
            "stripe_error":        stripe_error,

            "lifecycle":        lifecycle,
            "mrr_minor":        mrr,
            "drift":            _drift(dict(r), sub) if stripe_error is None else [],
        })

    counts: dict = {}
    for row in out:
        counts[row["lifecycle"]] = counts.get(row["lifecycle"], 0) + 1

    return {
        "subscribers": out,
        "summary": {
            "customers":      len(out),
            "mrr_minor":      mrr_total,
            "arr_minor":      mrr_total * 12,
            "by_lifecycle":   counts,
            "with_drift":     sum(1 for r in out if r["drift"]),
            # Stated, not implied. A dashboard whose numbers came from a
            # failed call must say so where the numbers are read.
            "stripe_error":   stripe_error,
            "generated_at":   datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/transactions")
async def all_transactions(
    limit: int = Query(100, ge=1, le=100),
    starting_after: str | None = Query(
        None, description="Stripe invoice id to page from"),
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Every invoice across every customer — the ledger.

    Stripe is the source: an invoice that exists there but whose webhook
    never landed would be missing from any local table, and a payment this
    business received must not depend on our own ingestion having worked.

    Customer emails come from the database because Stripe's customer object
    may carry a different one; the local record is what the account is.
    """
    def _pull(after: str | None) -> dict:
        stripe = _stripe_client()
        if stripe is None:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured")
        kwargs = {"limit": limit}
        if after:
            kwargs["starting_after"] = after
        page = stripe.Invoice.list(**kwargs)
        return {"data": list(page.data), "has_more": page.has_more}

    try:
        page = await asyncio.to_thread(_pull, starting_after)
    except Exception as exc:                                   # noqa: BLE001
        log.warning("admin/billing: ledger unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Could not read Stripe: {type(exc).__name__}. The "
                   f"transactions exist; they could not be retrieved.")

    rows = (await db.execute(text("""
        SELECT stripe_customer_id, email, name
          FROM users.users WHERE stripe_customer_id IS NOT NULL
    """))).mappings().all()
    who = {r["stripe_customer_id"]: (r["email"], r["name"]) for r in rows}

    out, gross, refunded = [], 0, 0
    for inv in page["data"]:
        cid = inv.get("customer")
        email, name = who.get(cid, (None, None))
        paid = inv.get("amount_paid") or 0
        gross += paid
        lines = (inv.get("lines", {}).get("data") or [{}])
        out.append({
            "invoice_id":   inv.get("id"),
            "number":       inv.get("number"),
            "created":      _ts(inv.get("created")),
            "status":       inv.get("status"),
            # Named explicitly when the customer is not one of ours: a blank
            # here would read as a missing value rather than as a Stripe
            # customer with no local account.
            "email":        email or f"(no local account: {cid})",
            "name":         name,
            "description":  lines[0].get("description") if lines else None,
            "amount_due":   inv.get("amount_due"),
            "amount_paid":  paid,
            "currency":     (inv.get("currency") or "").upper(),
            "hosted_url":   inv.get("hosted_invoice_url"),
            "pdf_url":      inv.get("invoice_pdf"),
        })

    return {
        "transactions": out,
        "has_more":     page["has_more"],
        "next_cursor":  out[-1]["invoice_id"] if out and page["has_more"] else None,
        # Scoped to THIS page, and said so. A total labelled without its
        # scope gets read as the lifetime figure.
        "page_total_minor": gross,
        "page_size": len(out),
    }


@router.get("/subscribers/{user_id}/transactions")
async def subscriber_transactions(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Full payment history for one customer, from Stripe.

    Invoices rather than charges as the spine: an invoice carries what the
    customer was billed FOR, the period it covered, and whether it was
    actually paid. Refunds are attached to their charge so a refunded
    payment never reads as revenue.
    """
    row = (await db.execute(text("""
        SELECT id, email, name, plan, stripe_customer_id
          FROM users.users WHERE id = :uid
    """), {"uid": user_id})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    if not row["stripe_customer_id"]:
        return {"user": {"email": row["email"], "name": row["name"]},
                "transactions": [],
                "note": "This user has no Stripe customer record — they have "
                        "never started a paid subscription."}

    def _pull(cid: str) -> dict:
        stripe = _stripe_client()
        if stripe is None:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured")

        invoices = stripe.Invoice.list(customer=cid, limit=100)
        out = []
        refunded_total = 0
        paid_total = 0
        for inv in invoices.auto_paging_iter():
            amount_paid = inv.get("amount_paid") or 0
            # Refunds live on the charge, not the invoice.
            refunded = 0
            charge_id = inv.get("charge")
            if charge_id:
                try:
                    ch = stripe.Charge.retrieve(charge_id)
                    refunded = ch.get("amount_refunded") or 0
                except Exception:                              # noqa: BLE001
                    refunded = 0
            paid_total += amount_paid
            refunded_total += refunded
            lines = inv.get("lines", {}).get("data") or [{}]
            out.append({
                "invoice_id":     inv.get("id"),
                "number":         inv.get("number"),
                "created":        _ts(inv.get("created")),
                "status":         inv.get("status"),
                "description":    (lines[0].get("description")
                                   if lines else None),
                "period_start":   _ts((lines[0].get("period") or {}).get("start")
                                      if lines else None),
                "period_end":     _ts((lines[0].get("period") or {}).get("end")
                                      if lines else None),
                "amount_due":     inv.get("amount_due"),
                "amount_paid":    amount_paid,
                "amount_refunded": refunded,
                "currency":       (inv.get("currency") or "").upper(),
                "hosted_url":     inv.get("hosted_invoice_url"),
                "pdf_url":        inv.get("invoice_pdf"),
            })

        cust = stripe.Customer.retrieve(cid)
        return {
            "transactions":    out,
            "net_paid_minor":  paid_total - refunded_total,
            "gross_paid_minor": paid_total,
            "refunded_minor":  refunded_total,
            # Negative is a credit Stripe will apply to the next invoice.
            "credit_balance_minor": cust.get("balance", 0),
        }

    try:
        data = await asyncio.to_thread(_pull, row["stripe_customer_id"])
    except Exception as exc:                                   # noqa: BLE001
        log.warning("admin/billing: transactions unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Could not read Stripe: {type(exc).__name__}. The history "
                   f"exists; it could not be retrieved. Nothing here means "
                   f"'no transactions'.")

    return {"user": {"user_id": str(row["id"]), "email": row["email"],
                     "name": row["name"], "plan": row["plan"],
                     "stripe_customer_id": row["stripe_customer_id"]},
            **data}
