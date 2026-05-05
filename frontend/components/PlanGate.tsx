'use client'

/**
 * PlanGate — inline plan-level feature gating.
 *
 * Usage:
 *   <PlanGate required="premium" feature="ASX Indices">
 *     <IndicesContent />
 *   </PlanGate>
 *
 * When the user's plan is below `required`, renders an upgrade prompt instead.
 * When not authenticated at all, renders nothing (ClientGuard handles redirect).
 */

import Link from 'next/link'
import { Lock, Zap } from 'lucide-react'
import { useAuth } from '@/lib/auth'

const PLAN_RANK: Record<string, number> = {
  free:                0,
  pro:                 1,
  premium:             2,
  enterprise_pro:      3,
  enterprise_premium:  4,
}

const PLAN_PRICE: Record<string, { monthly: string; yearly: string }> = {
  pro:     { monthly: '$19.99', yearly: '$199.90' },
  premium: { monthly: '$29.99', yearly: '$299.90' },
}

const PLAN_FEATURES: Record<string, string[]> = {
  pro: [
    '10 portfolios, 20 watchlists',
    '50 price alerts',
    'Natural language screener',
    'CSV export',
    'Advanced financials',
  ],
  premium: [
    'Everything in Pro',
    'ASX Indices tracker',
    'ETF & Managed Funds',
    'AI Deep Analysis per stock',
    'AI Portfolio Insights',
    '50 portfolios, 50 watchlists',
    '100 price alerts',
  ],
}

interface Props {
  required: 'pro' | 'premium'
  feature?: string
  children: React.ReactNode
}

export function PlanGate({ required, feature, children }: Props) {
  const { user } = useAuth()

  if (!user) return null

  const userRank = PLAN_RANK[user.plan] ?? 0
  const reqRank  = PLAN_RANK[required]  ?? 0

  if (userRank >= reqRank) return <>{children}</>

  const planLabel = required === 'premium' ? 'Premium' : 'Pro'
  const price     = PLAN_PRICE[required]
  const features  = PLAN_FEATURES[required]

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 py-16">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8 max-w-md w-full text-center">
        {/* Icon */}
        <div className={`w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4 ${required === 'premium' ? 'bg-amber-50' : 'bg-blue-50'}`}>
          <Lock className={`w-7 h-7 ${required === 'premium' ? 'text-amber-500' : 'text-blue-500'}`} />
        </div>

        {/* Heading */}
        <h2 className="text-xl font-bold text-slate-900 mb-1">
          {planLabel} Plan Required
        </h2>
        <p className="text-sm text-slate-500 mb-6">
          {feature ? `${feature} is` : 'This feature is'} available on the{' '}
          <span className="font-semibold text-slate-700">{planLabel}</span> plan.
        </p>

        {/* Features */}
        <ul className="text-left space-y-2 mb-6">
          {features.map(f => (
            <li key={f} className="flex items-start gap-2 text-sm text-slate-600">
              <Zap className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
              {f}
            </li>
          ))}
        </ul>

        {/* Pricing */}
        <p className="text-xs text-slate-400 mb-4">
          From {price.monthly}/mo · {price.yearly}/yr (save ~17%)
        </p>

        {/* CTA */}
        <Link
          href={`/account?upgrade=${required}`}
          className="block w-full py-3 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-colors"
        >
          Upgrade to {planLabel}
        </Link>
        <p className="mt-3 text-xs text-slate-400">
          Cancel anytime · Instant access after payment
        </p>
      </div>
    </div>
  )
}
