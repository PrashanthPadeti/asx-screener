"""
ASX Screener — Plan definitions & feature limits
=================================================
Single source of truth for all plan tiers, limits, and pricing.
Import PLAN_LIMITS in any route that enforces quotas.
"""
import logging
from typing import TypedDict

_log = logging.getLogger(__name__)

# ── Two orderings, deliberately ───────────────────────────────────────────────
#
# A plan has a COMMERCIAL position (what it costs, what counts as an upgrade)
# and a FEATURE LEVEL (what it can reach). For the individual tiers these agree,
# which is why one ladder served for both. For the enterprise tiers they do not:
# Enterprise Pro costs more than Premium and is an upgrade from Pro, but its
# feature set is Pro's -- the difference is seats.
#
# Conflating them had a measurable consequence. `require_plan("premium")` and
# `PlanGate required="premium"` both compare ranks, and Enterprise Pro ranked 3
# against Premium's 2, so every Premium-gated surface admitted it: Indices,
# ETFs & Funds, Commodities, Global Markets, the Heatmap and Top 5 -- none of
# which its PLAN_LIMITS entitle it to. Meanwhile `portfolio_insights: False`
# correctly withheld AI insights, so the same plan was Pro-level under one
# mechanism and above-Premium under another.

#: COMMERCIAL ordering. Upgrade/downgrade arithmetic only. Never use this to
#: decide access -- that is what produced the defect above.
PLAN_RANK: dict[str, int] = {
    "free":               0,
    "pro":                1,
    "premium":            2,
    "enterprise_pro":     3,
    "enterprise_premium": 4,
}

#: FEATURE level. Every entitlement check compares these. Ties are intended:
#: Enterprise Pro reaches exactly what Pro reaches, and Enterprise Premium
#: exactly what Premium reaches. Seats are expressed in `seat_limit`, not here.
FEATURE_LEVEL: dict[str, int] = {
    "free":               0,
    "pro":                1,
    "enterprise_pro":     1,
    "premium":            2,
    "enterprise_premium": 2,
}


def feature_level(plan: str) -> int:
    """Access level for `plan`; unknown plans get free's level.

    Unknown falls to 0 rather than raising: an unrecognised plan string must
    narrow access, never widen it. But it is LOGGED, because falling back
    silently is how a paying customer stayed on free entitlements unnoticed --
    `pro_monthly` was found in production on 8 Oct 2026, an active Pro
    subscriber resolving to free limits with nothing reporting it.
    """
    if plan not in FEATURE_LEVEL:
        _log.warning(
            "unknown plan %r resolved to free access. A paying subscriber "
            "may be on free entitlements; check users.users.plan.", plan)
    return FEATURE_LEVEL.get(plan, 0)


class PlanLimits(TypedDict):
    portfolios:          int
    watchlists:          int
    stocks_per_wl:       int
    alerts:              int
    nl_screener:         bool
    csv_export:          bool
    portfolio_insights:  bool   # AI portfolio analysis (Premium+)
    seat_limit:          int    # max team seats (1 = individual)


PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": {
        "portfolios":         1,
        "watchlists":         1,
        "stocks_per_wl":      50,
        "alerts":             3,
        "nl_screener":        False,
        "csv_export":         False,
        "portfolio_insights": False,
        "seat_limit":         1,
    },
    "pro": {
        "portfolios":         10,
        "watchlists":         10,
        "stocks_per_wl":      200,
        "alerts":             50,
        # AI natural-language screening is Premium. Pro keeps Query Mode,
        # which is the structured query builder, not the AI path.
        "nl_screener":        False,
        "csv_export":         False,     # CSV export is Premium
        "portfolio_insights": False,
        "seat_limit":         1,
    },
    "premium": {
        "portfolios":         20,
        "watchlists":         20,
        "stocks_per_wl":      500,
        "alerts":             100,
        "nl_screener":        True,
        "csv_export":         True,
        "portfolio_insights": True,
        "seat_limit":         1,
    },
    "enterprise_pro": {
        "portfolios":         10,
        "watchlists":         10,
        "stocks_per_wl":      200,
        "alerts":             50,
        "nl_screener":        False,      # Pro's feature set, 5 or 10 seats
        "csv_export":         False,
        "portfolio_insights": False,
        "seat_limit":         10,
    },
    "enterprise_premium": {
        "portfolios":         20,
        "watchlists":         20,
        "stocks_per_wl":      500,
        "alerts":             100,
        "nl_screener":        True,
        "csv_export":         True,
        "portfolio_insights": True,
        "seat_limit":         10,
    },
}


def get_limits(plan: str) -> PlanLimits:
    """Return limits for the given plan, falling back to free if unknown.

    The fallback is deliberate -- an unrecognised plan must not widen access --
    but it is logged for the same reason as `feature_level`: a silent
    downgrade of a paying customer is indistinguishable from a free user.
    """
    if plan not in PLAN_LIMITS:
        _log.warning("unknown plan %r resolved to free limits", plan)
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


# ── Pricing catalogue ──────────────────────────────────────────────────────────
# price_id fields are populated from settings (env vars) at runtime

PLANS_CATALOGUE = [
    {
        "id":           "free",
        "name":         "Free",
        "monthly_aud":  0,
        "yearly_aud":   0,
        "price_id_monthly": None,
        "price_id_yearly":  None,
        "seats":        1,
        "features":     PLAN_LIMITS["free"],
        "highlight":    False,
    },
    {
        "id":           "pro",
        "name":         "Pro",
        "monthly_aud":  19.99,
        "yearly_aud":   199.90,
        "price_id_monthly": "STRIPE_PRO_MONTHLY",
        "price_id_yearly":  "STRIPE_PRO_YEARLY",
        "seats":        1,
        "features":     PLAN_LIMITS["pro"],
        "highlight":    True,
    },
    {
        "id":           "premium",
        "name":         "Premium",
        "monthly_aud":  29.99,
        "yearly_aud":   299.90,
        "price_id_monthly": "STRIPE_PREMIUM_MONTHLY",
        "price_id_yearly":  "STRIPE_PREMIUM_YEARLY",
        "seats":        1,
        "features":     PLAN_LIMITS["premium"],
        "highlight":    False,
    },
    {
        "id":           "enterprise_pro",
        "name":         "Enterprise Pro",
        "monthly_aud":  None,   # varies by seats
        "yearly_aud":   None,
        "seats_options": [
            {"seats": 5,  "monthly_aud": 49.99,  "yearly_aud": 499.90,
             "price_id_monthly": "STRIPE_ENT_PRO_5_MONTHLY",
             "price_id_yearly":  "STRIPE_ENT_PRO_5_YEARLY"},
            {"seats": 10, "monthly_aud": 99.99,  "yearly_aud": 999.90,
             "price_id_monthly": "STRIPE_ENT_PRO_10_MONTHLY",
             "price_id_yearly":  "STRIPE_ENT_PRO_10_YEARLY"},
        ],
        "features":     PLAN_LIMITS["enterprise_pro"],
        "highlight":    False,
    },
    {
        "id":           "enterprise_premium",
        "name":         "Enterprise Premium",
        "monthly_aud":  None,
        "yearly_aud":   None,
        "seats_options": [
            {"seats": 5,  "monthly_aud": 79.99,  "yearly_aud": 799.90,
             "price_id_monthly": "STRIPE_ENT_PREM_5_MONTHLY",
             "price_id_yearly":  "STRIPE_ENT_PREM_5_YEARLY"},
            {"seats": 10, "monthly_aud": 159.99, "yearly_aud": 1599.90,
             "price_id_monthly": "STRIPE_ENT_PREM_10_MONTHLY",
             "price_id_yearly":  "STRIPE_ENT_PREM_10_YEARLY"},
        ],
        "features":     PLAN_LIMITS["enterprise_premium"],
        "highlight":    False,
    },
]
