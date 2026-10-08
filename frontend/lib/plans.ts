/**
 * Plan ordering — two of them, deliberately.
 *
 * A plan has a COMMERCIAL position (what it costs, what counts as an upgrade)
 * and a FEATURE LEVEL (what it can reach). For the individual tiers these
 * agree. For the enterprise tiers they do not: Enterprise Pro costs more than
 * Premium and is an upgrade from Pro, but its feature set is Pro's — the
 * difference is seats.
 *
 * Mirrors backend/app/core/plans.py. Keep the two in step; the backend is
 * authoritative and the server re-checks every gate, so a mismatch here shows
 * a locked feature as available (or the reverse) rather than granting access.
 *
 * This file exists because the map was copy-pasted into three components and
 * drifted: alerts/page.tsx had the feature-level values, PlanGate.tsx had the
 * commercial ones, so the same user was Pro-level in one place and
 * above-Premium in another.
 */

/** COMMERCIAL ordering. Upgrade/downgrade arithmetic only — never access. */
export const PLAN_RANK: Record<string, number> = {
  free:               0,
  pro:                1,
  premium:            2,
  enterprise_pro:     3,
  enterprise_premium: 4,
}

/** FEATURE level. Every entitlement check compares these. Ties are intended. */
export const FEATURE_LEVEL: Record<string, number> = {
  free:               0,
  pro:                1,
  enterprise_pro:     1,
  premium:            2,
  enterprise_premium: 2,
}

/** Access level for a plan. Unknown plans fall to free — narrow, never widen. */
export function featureLevel(plan: string | null | undefined): number {
  return FEATURE_LEVEL[plan ?? 'free'] ?? 0
}

/** Does `plan` reach everything `required` reaches? */
export function hasFeatureAccess(
  plan: string | null | undefined,
  required: string,
): boolean {
  return featureLevel(plan) >= featureLevel(required)
}

/**
 * Quota limits, mirroring PLAN_LIMITS in backend/app/core/plans.py.
 *
 * The backend is authoritative and enforces every one of these; this copy
 * exists only so the pricing table and the alerts page can display them
 * without a round trip. A mismatch shows the wrong number to a visitor — it
 * cannot grant anything.
 *
 * `GET /api/v1/billing/plans` returns the real catalogue including these
 * values, and the pricing page should eventually read from it rather than
 * mirror it. Until then this is one copy instead of the three that existed
 * (pricing/page.tsx, alerts/page.tsx, PlanGate.tsx).
 */
export interface PlanLimits {
  portfolios:        number
  watchlists:        number
  stocksPerWl:       number
  alerts:            number
  nlScreener:        boolean
  csvExport:         boolean
  portfolioInsights: boolean
  seatLimit:         number
}

export const PLAN_LIMITS: Record<string, PlanLimits> = {
  free:               { portfolios: 1,  watchlists: 1,  stocksPerWl: 50,  alerts: 3,   nlScreener: false, csvExport: false, portfolioInsights: false, seatLimit: 1  },
  pro:                { portfolios: 10, watchlists: 20, stocksPerWl: 500, alerts: 50,  nlScreener: false, csvExport: true,  portfolioInsights: false, seatLimit: 1  },
  premium:            { portfolios: 50, watchlists: 50, stocksPerWl: 500, alerts: 100, nlScreener: true,  csvExport: true,  portfolioInsights: true,  seatLimit: 1  },
  enterprise_pro:     { portfolios: 10, watchlists: 20, stocksPerWl: 500, alerts: 50,  nlScreener: false, csvExport: true,  portfolioInsights: false, seatLimit: 10 },
  enterprise_premium: { portfolios: 50, watchlists: 50, stocksPerWl: 500, alerts: 100, nlScreener: true,  csvExport: true,  portfolioInsights: true,  seatLimit: 10 },
}

export function planLimits(plan: string | null | undefined): PlanLimits {
  return PLAN_LIMITS[plan ?? 'free'] ?? PLAN_LIMITS.free
}
