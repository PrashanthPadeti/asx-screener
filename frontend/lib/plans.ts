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
