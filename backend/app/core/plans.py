"""
ASX Screener — Plan definitions & feature limits
=================================================
Single source of truth for all plan tiers, limits, and pricing.
Import PLAN_LIMITS in any route that enforces quotas.
"""
from typing import TypedDict

# ── Plan rank (higher = more features) ────────────────────────────────────────
PLAN_RANK: dict[str, int] = {
    "free":               0,
    "pro":                1,
    "premium":            2,
    "enterprise_pro":     3,
    "enterprise_premium": 4,
}


class PlanLimits(TypedDict):
    portfolios:       int
    watchlists:       int
    stocks_per_wl:    int
    alerts:           int
    nl_screener:      bool
    csv_export:       bool
    seat_limit:       int   # max team seats (1 = individual)


PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": {
        "portfolios":    1,
        "watchlists":    1,
        "stocks_per_wl": 50,
        "alerts":        3,
        "nl_screener":   False,
        "csv_export":    False,
        "seat_limit":    1,
    },
    "pro": {
        "portfolios":    10,
        "watchlists":    20,
        "stocks_per_wl": 500,
        "alerts":        50,
        "nl_screener":   True,
        "csv_export":    True,
        "seat_limit":    1,
    },
    "premium": {
        "portfolios":    50,
        "watchlists":    50,
        "stocks_per_wl": 500,
        "alerts":        100,
        "nl_screener":   True,
        "csv_export":    True,
        "seat_limit":    1,
    },
    "enterprise_pro": {
        "portfolios":    10,
        "watchlists":    20,
        "stocks_per_wl": 500,
        "alerts":        50,
        "nl_screener":   True,
        "csv_export":    True,
        "seat_limit":    10,  # up to 10 seats
    },
    "enterprise_premium": {
        "portfolios":    50,
        "watchlists":    50,
        "stocks_per_wl": 500,
        "alerts":        100,
        "nl_screener":   True,
        "csv_export":    True,
        "seat_limit":    10,
    },
}


def get_limits(plan: str) -> PlanLimits:
    """Return limits for the given plan, falling back to free if unknown."""
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
