# Decision pending — what happens to over-quota data on downgrade

**Status:** open. Not a defect; no implementation until the semantics are chosen.
**Raised:** 8 Oct 2026, during the v11.2.16 pricing-correctness work.
**Explicitly out of scope for v11.2.16.**

## The finding

All four published quotas are enforced, correctly, and before the write:

| Quota | Handler | Scope of the count |
|---|---|---|
| Portfolios | `portfolio.py` `create_portfolio` | per user |
| Watchlists | `watchlist.py` `create_watchlist` | per user |
| Stocks per watchlist | `watchlist.py` `add_stock` | per **watchlist** |
| Price alerts | `alerts.py` `create_alert` | per user, `is_active = TRUE` only |

`test_quota_limits_are_enforced.py` pins all four, including that the 403
precedes the INSERT (asserted by source position) and that the comparison is
`>=` rather than `>`.

**Every one of them is create-time only.** Nothing re-evaluates quotas when a
plan changes. `customer.subscription.deleted` in `stripe_routes.py` does this:

```sql
UPDATE users.users
SET plan = 'free', subscription_status = 'cancelled', seat_limit = 1,
    data_deletion_scheduled_at = NOW() + INTERVAL '12 months', ...
```

It touches no quota-bearing table. So a Premium subscriber who cancels keeps
20 portfolios, 20 watchlists of up to 500 stocks each, and 100 active alerts,
on a Free plan whose published entitlement is 1 / 1 / 50 / 3 — indefinitely.
They cannot create *more*, and they keep using what they have.

## Why this is a policy question and not a bug

The same handler sets `data_deletion_scheduled_at = NOW() + 12 months`, so
*retaining the rows* is clearly deliberate. Retention and quota are different
properties, though, and the deliberate retention does not settle what the
customer is entitled to use in the meantime. Nothing in the code expresses an
intent either way, so there is no "correct" behaviour to restore.

The three candidates are materially different contracts, and the choice is
commercial before it is technical:

| Option | Customer experience | Cost |
|---|---|---|
| **Retain and freeze excess** | Keeps everything; cannot add, edit or refresh beyond the Free quota until they delete down or resubscribe | Needs a per-entity "over quota" state and an ordering rule for *which* 19 of 20 portfolios freeze; most UI surfaces must render it |
| **Retain read-only** | Sees all historical data, can act only within Free limits | Same ordering problem; gentler, but a read-only portfolio still shows live prices, which is most of the paid value |
| **Delete excess** | Loses data | Destructive and irreversible; contradicts the 12-month retention already implemented and almost certainly needs notice and an export path first |

A fourth is legitimate and is the current de facto behaviour:

| **Grandfather indefinitely** | Keeps full use of what they had; only creation is capped | Zero work. A cancelled Premium user retains most of the Premium value, which weakens the upgrade and is a revenue decision |

## What must be decided before any implementation

1. Which of the four.
2. If anything freezes or is deleted: the **ordering rule**. "Keep 1 of 20
   watchlists" needs a deterministic, explainable choice — oldest, most
   recently used, or user-selected. User-selected is the only one that does
   not silently pick for them, and it needs a UI.
3. Whether the 12-month retention window governs this too, or runs separately.
4. Notice: whether a downgrading customer is told, and when.
5. Whether a *downgrade* between paid tiers (Premium → Pro) behaves the same
   as a cancellation to Free. The code path differs
   (`customer.subscription.updated` vs `.deleted`).

## Note for whoever implements it

Enforcement would move from create-time to a lifecycle concern, and the
instinct will be to reconcile inside the Stripe webhook. Resist it. A webhook
that deletes or freezes customer rows makes a payment-provider callback
authoritative over user data, and a replayed or out-of-order event then
mutates it. Per [[engineering-rule-instrument-isolation]], keep the
reconciliation a separate, idempotent, independently runnable job that reads
plan state and converges — so it can be dry-run against production, and so a
bad run is re-runnable rather than destructive.

Any implementation needs behavioural evidence from a real downgraded account,
not a structural guard: a guard proves the reconciliation exists, only a
downgraded user proves they receive the intended contract.
