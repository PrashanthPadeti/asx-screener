'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Check, X, Zap, Shield, Building2, ArrowRight, Star } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { createCheckoutSession } from '@/lib/api'
import { cn } from '@/lib/utils'
import Link from 'next/link'

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
    features: {
      portfolios:   1,
      watchlists:   1,
      stocksPerWl:  50,
      alerts:       3,
      nlScreener:   false,
      csvExport:    false,
    },
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
    features: {
      portfolios:   10,
      watchlists:   20,
      stocksPerWl:  500,
      alerts:       50,
      nlScreener:   true,
      csvExport:    true,
    },
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
    features: {
      portfolios:   50,
      watchlists:   50,
      stocksPerWl:  500,
      alerts:       100,
      nlScreener:   true,
      csvExport:    true,
    },
  },
]

const FEATURE_ROWS: { label: string; key: keyof typeof PLANS[0]['features'] | null; free: string; pro: string; premium: string }[] = [
  { label: 'Portfolios',         key: null, free: '1',    pro: '10',   premium: '50'  },
  { label: 'Watchlists',         key: null, free: '1',    pro: '20',   premium: '50'  },
  { label: 'Stocks per watchlist',key: null,free: '50',   pro: '500',  premium: '500' },
  { label: 'Price alerts',       key: null, free: '3',    pro: '50',   premium: '100' },
  { label: 'AI Screener',        key: 'nlScreener',  free: '', pro: '', premium: '' },
  { label: 'CSV export',         key: 'csvExport',   free: '', pro: '', premium: '' },
  { label: 'Saved screens',      key: null, free: '✓',   pro: '✓',    premium: '✓'   },
  { label: 'Community screens',  key: null, free: '✓',   pro: '✓',    premium: '✓'   },
  { label: 'Market signals',     key: null, free: '✓',   pro: '✓',    premium: '✓'   },
  { label: 'Short interest data',key: null, free: '✓',   pro: '✓',    premium: '✓'   },
]

// ── Component ──────────────────────────────────────────────────────────────────

export default function PricingPage() {
  const { user } = useAuth()
  const router   = useRouter()
  const [yearly, setYearly]   = useState(true)
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError]     = useState<string | null>(null)

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

      {/* Plan cards */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10">

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
                    <ComparisonCell value={row.key ? PLANS[0].features[row.key as keyof typeof PLANS[0]['features']] : row.free} />
                    <ComparisonCell value={row.key ? PLANS[1].features[row.key as keyof typeof PLANS[1]['features']] : row.pro} highlight />
                    <ComparisonCell value={row.key ? PLANS[2].features[row.key as keyof typeof PLANS[2]['features']] : row.premium} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
