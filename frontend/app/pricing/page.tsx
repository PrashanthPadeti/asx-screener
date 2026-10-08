'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Check, X, Zap, Shield, Building2, ArrowRight, Star, Users } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { createCheckoutSession, api } from '@/lib/api'
import { cn } from '@/lib/utils'
import FAQSchema from '@/components/FAQSchema'
import { PLAN_LIMITS as L } from '@/lib/plans'

const PRICING_FAQ = [
  {
    question: 'Can I cancel anytime?',
    answer: 'Yes. Cancel at any time from your account page — you keep access until the end of your billing period.',
  },
  {
    question: 'Is there a free trial?',
    answer: 'The Free plan is free forever. Pro and Premium have no trial, but you can start on Free and upgrade any time.',
  },
  {
    question: 'What payment methods are accepted?',
    answer: 'Visa, Mastercard, and American Express via Stripe\'s secure checkout. All prices are in AUD.',
  },
  {
    question: 'What happens to my data if I downgrade?',
    answer: 'Your data is preserved for 12 months after downgrading. You can upgrade again to regain access.',
  },
]

// ── Static plan data (matches backend plans.py) ───────────────────────────────

const PLANS = [
  {
    id:          'free',
    name:        'Free',
    icon:        Shield,
    monthlyAUD:  0,
    yearlyAUD:   0,
    color:       'slate',
    highlight:   false,
    badge:       null,
    description: 'Everything you need to get started with ASX investing.',
    features: L.free,
  },
  {
    id:          'pro',
    name:        'Pro',
    icon:        Zap,
    monthlyAUD:  19.99,
    yearlyAUD:   199.90,
    color:       'blue',
    highlight:   true,
    badge:       'Most Popular',
    description: 'For active investors who want deeper data and automation.',
    features: L.pro,
  },
  {
    id:          'premium',
    name:        'Premium',
    icon:        Star,
    monthlyAUD:  29.99,
    yearlyAUD:   299.90,
    color:       'purple',
    highlight:   false,
    badge:       null,
    description: 'Unlimited data, priority access, and full feature set.',
    features: L.premium,
  },
]

/**
 * The comparison table.
 *
 * Quota rows read PLAN_LIMITS, which mirrors the backend. Access rows are
 * declared here because "which pages a plan can open" has no representation
 * in PLAN_LIMITS — it lives in PlanGate and require_plan — so the honest
 * thing is to state it rather than derive it from something that does not
 * know.
 *
 * Two rows were wrong before v11.2.13 and are corrected here. AI Screener
 * showed a tick for Pro; it is Premium (`nl_screener`), and Pro keeps Query
 * Mode. Community screens showed a tick for Free; `saved_screens.py` returns
 * 403 below Premium, so both Free and Pro see nothing.
 */
type Cell = string | boolean

const FEATURE_ROWS: { label: string; free: Cell; pro: Cell; premium: Cell }[] = [
  // ── Limits (from PLAN_LIMITS) ──────────────────────────────────────────
  { label: 'Portfolios',               free: `${L.free.portfolios}`,  pro: `${L.pro.portfolios}`,  premium: `${L.premium.portfolios}`  },
  { label: 'Watchlists',               free: `${L.free.watchlists}`,  pro: `${L.pro.watchlists}`,  premium: `${L.premium.watchlists}`  },
  { label: 'Stocks per watchlist',     free: `${L.free.stocksPerWl}`, pro: `${L.pro.stocksPerWl}`, premium: `${L.premium.stocksPerWl}` },
  { label: 'Price alerts',             free: `${L.free.alerts}`,      pro: `${L.pro.alerts}`,      premium: `${L.premium.alerts}`      },

  // ── Screener ───────────────────────────────────────────────────────────
  { label: 'Screener — filters',       free: true,  pro: true,  premium: true  },
  { label: 'Screener — Query Mode',    free: false, pro: true,  premium: true  },
  { label: 'Screener — AI natural language', free: false, pro: L.pro.nlScreener, premium: L.premium.nlScreener },
  { label: 'CSV export',               free: L.free.csvExport, pro: L.pro.csvExport, premium: L.premium.csvExport },
  { label: 'AI portfolio insights',    free: L.free.portfolioInsights, pro: L.pro.portfolioInsights, premium: L.premium.portfolioInsights },

  // ── Screens ────────────────────────────────────────────────────────────
  { label: 'Quick screens',            free: true,  pro: true,  premium: true  },
  { label: 'Sector screens',           free: false, pro: true,  premium: true  },
  { label: 'Pro screens',              free: false, pro: true,  premium: true  },
  { label: 'Premium screens',          free: false, pro: false, premium: true  },
  { label: 'Community screens',        free: false, pro: false, premium: true  },
  { label: 'Saved screens',            free: true,  pro: true,  premium: true  },

  // ── Market data ────────────────────────────────────────────────────────
  { label: 'ASX market overview',      free: true,  pro: true,  premium: true  },
  { label: 'News',                     free: true,  pro: true,  premium: true  },
  { label: 'Market signals',           free: true,  pro: true,  premium: true  },
  { label: 'Short interest data',      free: true,  pro: true,  premium: true  },
  { label: 'Metrics glossary',         free: false, pro: true,  premium: true  },
  { label: 'Broker compare',           free: false, pro: true,  premium: true  },
  { label: 'ASX indices',              free: false, pro: false, premium: true  },
  { label: 'ETFs & funds',             free: false, pro: false, premium: true  },
  { label: 'Commodities',              free: false, pro: false, premium: true  },
  { label: 'Global markets',           free: false, pro: false, premium: true  },
  { label: 'Performance heatmap',      free: false, pro: false, premium: true  },
  { label: 'Alpha 5 weekly picks',     free: false, pro: false, premium: true  },
  { label: 'Education hub',            free: true,  pro: true,  premium: true  },
]

// ── Component ──────────────────────────────────────────────────────────────────

interface FoundingStatus {
  enabled:   boolean
  limit:     number
  claimed:   number
  remaining: number
  available: boolean
}

export default function PricingPage() {
  const { user } = useAuth()
  const router   = useRouter()
  const [yearly, setYearly]   = useState(true)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError]     = useState<string | null>(null)
  const [founding, setFounding] = useState<FoundingStatus | null>(null)

  // Fetch founding-member availability on mount
  useEffect(() => {
    api.get<FoundingStatus>('/api/v1/billing/founding-member-status')
      .then(r => setFounding(r.data))
      .catch(() => {/* non-critical — hide banner on error */})
  }, [])

  const currentPlan = user?.plan ?? 'free'
  const isPro       = ['pro', 'premium', 'enterprise_pro', 'enterprise_premium'].includes(currentPlan)

  async function handleUpgrade(plan: typeof PLANS[0]) {
    if (plan.id === 'free') return
    if (!user) { router.push(`/auth/login?next=/pricing`); return }
    if (currentPlan === plan.id) return

    setLoading(plan.id)
    setError(null)
    try {
      const interval = yearly ? 'yearly' : 'monthly'
      const { url } = await createCheckoutSession(plan.id, interval)
      window.location.href = url
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Unable to start checkout. Please try again.')
      setLoading(null)
    }
  }

  function ctaLabel(plan: typeof PLANS[0]) {
    if (plan.id === 'free') return 'Get Started Free'
    if (currentPlan === plan.id) return 'Current Plan'
    if (!user) return `Upgrade to ${plan.name}`
    return `Upgrade to ${plan.name}`
  }

  function ctaDisabled(plan: typeof PLANS[0]) {
    return currentPlan === plan.id || loading === plan.id
  }

  const yearlyDiscount = (mo: number) => {
    const yr = mo * 10  // 10 months for price of 12
    return Math.round((1 - yr / (mo * 12)) * 100)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <FAQSchema url="https://asxscreener.com.au/pricing" items={PRICING_FAQ} />

      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-12 text-center">
          <h1 className="text-3xl font-bold text-gray-900 mb-3">Simple, transparent pricing</h1>
          <p className="text-gray-500 max-w-xl mx-auto">
            Professional ASX research tools for every investor. Start free, upgrade when you're ready.
          </p>

          {/* Monthly / Yearly toggle */}
          <div className="inline-flex items-center gap-3 mt-6 bg-gray-100 rounded-xl p-1">
            <button
              onClick={() => setYearly(false)}
              className={cn('px-4 py-2 rounded-lg text-sm font-semibold transition-all',
                !yearly ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              )}
            >
              Monthly
            </button>
            <button
              onClick={() => setYearly(true)}
              className={cn('px-4 py-2 rounded-lg text-sm font-semibold transition-all flex items-center gap-2',
                yearly ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              )}
            >
              Yearly
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                SAVE {yearlyDiscount(PLANS[1].monthlyAUD)}%
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Main layout: plan cards + sticky sidebar */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10">
        <div className="flex flex-col lg:flex-row gap-8 items-start">

          {/* ── Left: all plan content ── */}
          <div className="flex-1 min-w-0">

            {/* Mobile founding banner (hidden on lg where sidebar shows) */}
            {founding?.enabled && (
              <div className={cn(
                'lg:hidden rounded-2xl px-5 py-4 flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-6',
                founding.available
                  ? 'bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200'
                  : 'bg-gray-50 border border-gray-200'
              )}>
                <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center shrink-0', founding.available ? 'bg-amber-100' : 'bg-gray-200')}>
                  <Users className={cn('w-5 h-5', founding.available ? 'text-amber-600' : 'text-gray-400')} />
                </div>
                <div className="flex-1 min-w-0">
                  {founding.available ? (
                    <>
                      <p className="font-bold text-amber-900 text-sm">Founding Members</p>
                      <p className="text-amber-700 text-xs mt-0.5">Monthly → 6 months &nbsp;·&nbsp; Annual → 3 years. No extra charge.</p>
                    </>
                  ) : (
                    <p className="font-bold text-gray-600 text-sm">Founding Members — offer has ended. Standard pricing applies.</p>
                  )}
                </div>
              </div>
            )}

            {error && (
              <div className="mb-6 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
                {error}
              </div>
            )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map(plan => {
            const Icon       = plan.icon
            const price      = yearly ? plan.yearlyAUD / 12 : plan.monthlyAUD
            const isCurrent  = currentPlan === plan.id
            const isLoadingThis = loading === plan.id

            return (
              <div key={plan.id} className={cn(
                'relative flex flex-col rounded-2xl border bg-white p-6',
                plan.highlight
                  ? 'border-blue-500 shadow-lg shadow-blue-100 ring-1 ring-blue-500'
                  : 'border-gray-200'
              )}>
                {plan.badge && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="bg-blue-600 text-white text-xs font-bold px-3 py-1 rounded-full">
                      {plan.badge}
                    </span>
                  </div>
                )}
                {isCurrent && (
                  <div className="absolute -top-3 right-4">
                    <span className="bg-emerald-600 text-white text-xs font-bold px-3 py-1 rounded-full">
                      Your Plan
                    </span>
                  </div>
                )}

                {/* Icon + name */}
                <div className="flex items-center gap-3 mb-4">
                  <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center',
                    plan.color === 'blue'   ? 'bg-blue-50'   :
                    plan.color === 'purple' ? 'bg-purple-50' : 'bg-slate-100'
                  )}>
                    <Icon className={cn('w-5 h-5',
                      plan.color === 'blue'   ? 'text-blue-600'   :
                      plan.color === 'purple' ? 'text-purple-600' : 'text-slate-500'
                    )} />
                  </div>
                  <div>
                    <h3 className="font-bold text-gray-900">{plan.name}</h3>
                    <p className="text-xs text-gray-400">{plan.description}</p>
                  </div>
                </div>

                {/* Price */}
                <div className="mb-5">
                  {plan.monthlyAUD === 0 ? (
                    <div className="text-3xl font-bold text-gray-900">Free</div>
                  ) : (
                    <>
                      <div className="flex items-baseline gap-1">
                        <span className="text-3xl font-bold text-gray-900">
                          ${price.toFixed(2)}
                        </span>
                        <span className="text-gray-400 text-sm">/mo AUD</span>
                      </div>
                      {yearly && (
                        <p className="text-xs text-gray-400 mt-0.5">
                          ${plan.yearlyAUD.toFixed(0)} billed yearly
                        </p>
                      )}
                    </>
                  )}
                </div>

                {/* Features */}
                <ul className="space-y-2.5 mb-6 flex-1">
                  <FeatureItem label={`${plan.features.portfolios} portfolio${plan.features.portfolios > 1 ? 's' : ''}`} ok />
                  <FeatureItem label={`${plan.features.watchlists} watchlist${plan.features.watchlists > 1 ? 's' : ''} (${plan.features.stocksPerWl} stocks)`} ok />
                  <FeatureItem label={`${plan.features.alerts} price alert${plan.features.alerts > 1 ? 's' : ''}`} ok />
                  <FeatureItem label="Saved & community screens" ok />
                  <FeatureItem label="AI-powered screener" ok={plan.features.nlScreener} />
                  <FeatureItem label="CSV export" ok={plan.features.csvExport} />
                </ul>

                {/* CTA */}
                {plan.id === 'free' ? (
                  <Link
                    href={user ? '/screener' : '/auth/register'}
                    className="block text-center py-2.5 px-4 rounded-xl border border-gray-300 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    {user ? 'Go to Screener' : 'Get Started Free'}
                  </Link>
                ) : (
                  <div className="space-y-2">
                    <button
                      onClick={() => handleUpgrade(plan)}
                      disabled={ctaDisabled(plan)}
                      className={cn(
                        'w-full py-2.5 px-4 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2',
                        isCurrent
                          ? 'bg-gray-100 text-gray-500 cursor-default'
                          : plan.highlight
                          ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                          : 'bg-gray-900 text-white hover:bg-gray-800'
                      )}
                    >
                      {isLoadingThis ? (
                        <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <>
                          {ctaLabel(plan)}
                          {!isCurrent && <ArrowRight className="w-3.5 h-3.5" />}
                        </>
                      )}
                    </button>
                    {!isCurrent && (
                      <p className="text-[10px] text-center text-gray-400 leading-snug">
                        {founding?.enabled && founding.available && (
                          <span className="block text-amber-600 font-semibold mb-0.5">
                            🎉 Founding member offer applies
                          </span>
                        )}
                        By upgrading you agree to our{' '}
                        <Link href="/terms" className="underline hover:text-gray-600">Terms of Service</Link>
                        {' '}and{' '}
                        <Link href="/privacy" className="underline hover:text-gray-600">Privacy Policy</Link>.
                        Cancel anytime.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Enterprise banner */}
        <div className="mt-8 bg-gradient-to-r from-slate-800 to-slate-900 rounded-2xl p-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center shrink-0">
              <Building2 className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-bold text-white">Enterprise</h3>
              <p className="text-slate-300 text-sm">Team seats, API access, and custom onboarding. From $49.99/mo for 5 seats.</p>
            </div>
          </div>
          <a
            href="mailto:hello@asxscreener.com.au?subject=Enterprise%20Pricing"
            className="shrink-0 px-5 py-2.5 bg-white text-slate-900 text-sm font-bold rounded-xl hover:bg-slate-100 transition-colors"
          >
            Contact Sales
          </a>
        </div>

        {/* Feature comparison table */}
        <div className="mt-12">
          <h2 className="text-lg font-bold text-gray-900 mb-4">Full feature comparison</h2>
          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="py-3 px-4 text-left font-semibold text-gray-600 w-1/2">Feature</th>
                  <th className="py-3 px-4 text-center font-semibold text-gray-600">Free</th>
                  <th className="py-3 px-4 text-center font-semibold text-blue-600">Pro</th>
                  <th className="py-3 px-4 text-center font-semibold text-gray-600">Premium</th>
                </tr>
              </thead>
              <tbody>
                {FEATURE_ROWS.map((row, i) => (
                  <tr key={row.label} className={cn('border-t border-gray-100', i % 2 === 0 ? '' : 'bg-gray-50/50')}>
                    <td className="py-3 px-4 text-gray-700">{row.label}</td>
                    <ComparisonCell value={row.free} />
                    <ComparisonCell value={row.pro} highlight />
                    <ComparisonCell value={row.premium} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-gray-500">
            Enterprise Pro and Enterprise Premium include everything in Pro and
            Premium respectively, for 5 or 10 team members.
          </p>
        </div>

        {/* FAQ */}
        <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-6">
          <FaqItem q="Can I cancel anytime?">
            Yes. Cancel at any time from your account page — you keep access until the end of your billing period.
          </FaqItem>
          <FaqItem q="Is there a free trial?">
            The Free plan is free forever. Pro and Premium have no trial, but you can start on Free and upgrade any time.
          </FaqItem>
          <FaqItem q="What payment methods are accepted?">
            Visa, Mastercard, and American Express via Stripe's secure checkout. All prices are in AUD.
          </FaqItem>
          <FaqItem q="What happens to my data if I downgrade?">
            Your data is preserved for 12 months after downgrading. You can upgrade again to regain access.
          </FaqItem>
        </div>

          </div>{/* end left column */}

          {/* ── Right: Option C sticky founding widget (desktop only) ── */}
          {founding?.enabled && (
            <div className="hidden lg:block w-56 flex-shrink-0 sticky top-24 self-start">
              <div className="bg-[#0f172a] rounded-2xl p-4 border border-amber-500/30">

                {/* Header */}
                <div className="flex items-center gap-2 mb-4">
                  <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
                  <span className="text-amber-400 text-xs font-semibold">Founding Member Offer</span>
                </div>

                {/* Deals */}
                <div className="space-y-2 mb-4">
                  <div className="flex items-start gap-2 py-2 border-b border-white/[0.07]">
                    <Check className="w-3.5 h-3.5 text-emerald-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-slate-200 text-xs">Monthly</span>
                      <span className="text-slate-400 text-xs"> — pay 1, get </span>
                      <span className="text-amber-400 text-xs font-semibold">6 months</span>
                    </div>
                  </div>
                  <div className="flex items-start gap-2 py-2">
                    <Check className="w-3.5 h-3.5 text-emerald-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <span className="text-slate-200 text-xs">Annual</span>
                      <span className="text-slate-400 text-xs"> — pay 1yr, get </span>
                      <span className="text-amber-400 text-xs font-semibold">3 years</span>
                    </div>
                  </div>
                </div>

                {/* Availability notice — no deadline is advertised. */}
                <div className="mb-4">
                  {!founding.available && (
                    <p className="text-[10px] text-slate-500">Offer has ended</p>
                  )}
                </div>

                {/* CTA */}
                {founding.available ? (
                  <Link
                    href="/auth/register"
                    className="block text-center bg-amber-500 hover:bg-amber-400 text-slate-900 text-xs font-semibold py-2.5 rounded-lg transition-colors"
                  >
                    Claim my spot
                  </Link>
                ) : (
                  <div className="text-center text-[10px] text-slate-500 py-2">
                    Standard pricing applies
                  </div>
                )}

                <p className="text-[10px] text-slate-600 text-center mt-3 leading-relaxed">
                  Founding member offer. No extra charge.
                </p>
              </div>
            </div>
          )}

        </div>{/* end flex row */}
      </div>
    </div>
  )
}

// ── Small components ──────────────────────────────────────────────────────────

function FeatureItem({ label, ok }: { label: string; ok: boolean }) {
  return (
    <li className="flex items-center gap-2.5 text-sm">
      {ok
        ? <Check className="w-4 h-4 text-emerald-500 shrink-0" />
        : <X     className="w-4 h-4 text-gray-300 shrink-0" />}
      <span className={ok ? 'text-gray-700' : 'text-gray-400'}>{label}</span>
    </li>
  )
}

function ComparisonCell({ value, highlight }: { value: string | number | boolean; highlight?: boolean }) {
  if (typeof value === 'boolean') {
    return (
      <td className={cn('py-3 px-4 text-center', highlight && 'bg-blue-50/30')}>
        {value
          ? <Check className="w-4 h-4 text-emerald-500 mx-auto" />
          : <X     className="w-4 h-4 text-gray-300 mx-auto" />}
      </td>
    )
  }
  return (
    <td className={cn('py-3 px-4 text-center text-gray-700', highlight && 'bg-blue-50/30 font-medium text-blue-700')}>
      {value}
    </td>
  )
}

function FaqItem({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h3 className="font-semibold text-gray-900 mb-1.5 text-sm">{q}</h3>
      <p className="text-gray-500 text-sm leading-relaxed">{children}</p>
    </div>
  )
}
