'use client'
import { useState, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import {
  User, CreditCard, Bell, Shield, CheckCircle2, Loader2, LogIn,
  AlertTriangle, Crown, Zap, Lock, ExternalLink,
} from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Plan config ───────────────────────────────────────────────────────────────

const PLAN_RANK: Record<string, number> = {
  free: 0, pro: 1, premium: 2, enterprise_pro: 3, enterprise_premium: 4,
}

const PLANS = [
  {
    id: 'free' as const,
    label: 'Free',
    monthly: null,
    yearly: null,
    color: 'border-gray-200',
    badge: 'bg-gray-100 text-gray-600',
    icon: <Shield className="w-5 h-5 text-gray-400" />,
    features: [
      '1 portfolio (10 holdings)',
      '3 watchlists (50 stocks each)',
      '5 price alerts',
      'Basic screener (50 filters)',
      'ASX announcements feed',
    ],
  },
  {
    id: 'pro' as const,
    label: 'Pro',
    monthly: 19.99,
    yearly: 199.90,
    color: 'border-blue-400',
    badge: 'bg-blue-100 text-blue-700',
    icon: <Zap className="w-5 h-5 text-blue-500" />,
    features: [
      '10 portfolios (20 holdings each)',
      '20 watchlists (500 stocks each)',
      '50 price alerts',
      'Natural language screener',
      'CSV export (5,000 rows)',
      'Advanced financials & ratios',
    ],
  },
  {
    id: 'premium' as const,
    label: 'Premium',
    monthly: 29.99,
    yearly: 299.90,
    color: 'border-purple-400',
    badge: 'bg-purple-100 text-purple-700',
    icon: <Crown className="w-5 h-5 text-purple-500" />,
    features: [
      'Everything in Pro',
      'ASX Indices tracker',
      'ETF & Managed Funds',
      'AI Deep Analysis per stock',
      'AI Portfolio Insights',
      '50 portfolios & watchlists',
      '100 price alerts',
    ],
  },
]

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  active:    { label: 'Active',    color: 'text-green-600' },
  trialing:  { label: 'Trial',     color: 'text-blue-600' },
  past_due:  { label: 'Past Due',  color: 'text-amber-600' },
  cancelled: { label: 'Cancelled', color: 'text-red-500' },
  inactive:  { label: 'Inactive',  color: 'text-gray-400' },
}

// ── Account page ──────────────────────────────────────────────────────────────

export default function AccountPage() {
  return (
    <Suspense>
      <AccountPageInner />
    </Suspense>
  )
}

function AccountPageInner() {
  const { user, loading } = useAuth()
  const searchParams      = useSearchParams()
  const upgradeStatus     = searchParams.get('upgrade')
  const upgradeTarget     = searchParams.get('upgrade') // also used as target plan hint

  const [billing, setBilling]   = useState<'monthly' | 'yearly'>('monthly')
  const [checkoutPlan, setCheckoutPlan] = useState<string | null>(null)
  const [portalLoading, setPortalLoading] = useState(false)

  async function handleCheckout(planId: 'pro' | 'premium') {
    setCheckoutPlan(planId)
    try {
      const { data } = await api.post('/api/v1/billing/checkout', {
        plan: planId,
        interval: billing,
        success_url: `${window.location.origin}/account?upgrade=success`,
        cancel_url:  `${window.location.origin}/account?upgrade=cancelled`,
      })
      window.location.href = data.url
    } catch {
      alert('Billing is not configured yet. Check back soon!')
    } finally {
      setCheckoutPlan(null)
    }
  }

  async function handlePortal() {
    setPortalLoading(true)
    try {
      const { data } = await api.post('/api/v1/billing/portal')
      window.location.href = data.url
    } catch {
      alert('No billing account found.')
    } finally {
      setPortalLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 max-w-3xl">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  if (!user) {
    return (
      <div className="max-w-lg mx-auto text-center py-20">
        <User className="w-12 h-12 text-gray-200 mx-auto mb-4" />
        <h1 className="text-xl font-bold text-gray-900 mb-2">Account Settings</h1>
        <p className="text-gray-500 mb-6">Sign in to manage your account and billing.</p>
        <Link
          href="/auth/login?redirect=/account"
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700"
        >
          <LogIn className="w-4 h-4" />
          Sign in
        </Link>
      </div>
    )
  }

  const userRank   = PLAN_RANK[user.plan] ?? 0
  const isPaid     = userRank > 0
  const statusInfo = STATUS_LABELS[user.subscription_status] ?? STATUS_LABELS.inactive
  const isPastDue  = user.subscription_status === 'past_due'
  const isCancelled = user.subscription_status === 'cancelled'

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
        <User className="w-5 h-5" />
        Account Settings
      </h1>

      {/* Success banner */}
      {upgradeStatus === 'success' && (
        <div className="flex items-center gap-2 px-4 py-3 bg-green-50 border border-green-200 rounded-xl text-sm text-green-700">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          Your subscription is now active. Welcome to {user.plan === 'premium' ? 'Premium' : 'Pro'}!
        </div>
      )}

      {/* Cancelled banner */}
      {upgradeStatus === 'cancelled' && (
        <div className="flex items-center gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-700">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          Checkout was cancelled — you haven&apos;t been charged.
        </div>
      )}

      {/* Past-due warning */}
      {isPastDue && (
        <div className="flex items-start gap-3 px-4 py-3 bg-amber-50 border border-amber-300 rounded-xl text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Payment failed</p>
            <p className="text-xs mt-0.5">
              Your last payment didn&apos;t go through. Update your payment method to keep your subscription active.
            </p>
            <button
              onClick={handlePortal}
              disabled={portalLoading}
              className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 hover:text-amber-900 underline"
            >
              {portalLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ExternalLink className="w-3 h-3" />}
              Update payment method
            </button>
          </div>
        </div>
      )}

      {/* Profile card */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-sm shrink-0">
            {(user.name || user.email)[0].toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-medium text-gray-900 truncate">{user.name || '—'}</p>
            <p className="text-sm text-gray-500 truncate">{user.email}</p>
          </div>
          <div className="text-right shrink-0">
            <span className={cn('text-xs px-2.5 py-1 rounded-full font-semibold capitalize', {
              'bg-gray-100 text-gray-600':   user.plan === 'free',
              'bg-blue-100 text-blue-700':   user.plan === 'pro',
              'bg-purple-100 text-purple-700': user.plan === 'premium',
              'bg-amber-100 text-amber-700': user.plan.startsWith('enterprise'),
            })}>
              {user.plan}
            </span>
            {isPaid && (
              <p className={cn('text-xs mt-1 font-medium', statusInfo.color)}>
                {statusInfo.label}
              </p>
            )}
          </div>
        </div>

        <div className="border-t border-gray-100 mt-4 pt-4 grid grid-cols-3 gap-3 text-sm">
          <div>
            <p className="text-xs text-gray-500 mb-0.5">Email verified</p>
            <p className={user.email_verified ? 'text-green-600 font-medium' : 'text-amber-600'}>
              {user.email_verified ? '✓ Verified' : 'Not verified'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-0.5">Current plan</p>
            <p className="font-medium text-gray-900 capitalize">{user.plan}</p>
          </div>
          {user.subscription_ends_at && (
            <div>
              <p className="text-xs text-gray-500 mb-0.5">
                {isCancelled ? 'Access until' : 'Renews'}
              </p>
              <p className="font-medium text-gray-900 text-xs">
                {new Date(user.subscription_ends_at).toLocaleDateString('en-AU', {
                  day: 'numeric', month: 'short', year: 'numeric'
                })}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-2 gap-3">
        <Link href="/watchlist"
          className="flex items-center gap-3 px-4 py-3 bg-white border border-gray-200 rounded-xl hover:border-blue-200 hover:bg-blue-50 transition-colors">
          <Shield className="w-4 h-4 text-blue-600" />
          <div>
            <p className="text-sm font-medium text-gray-900">Watchlists</p>
            <p className="text-xs text-gray-500">Manage saved stocks</p>
          </div>
        </Link>
        <Link href="/alerts"
          className="flex items-center gap-3 px-4 py-3 bg-white border border-gray-200 rounded-xl hover:border-blue-200 hover:bg-blue-50 transition-colors">
          <Bell className="w-4 h-4 text-blue-600" />
          <div>
            <p className="text-sm font-medium text-gray-900">Alerts</p>
            <p className="text-xs text-gray-500">Price notifications</p>
          </div>
        </Link>
      </div>

      {/* Billing section */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <CreditCard className="w-4 h-4 text-gray-600" />
            <h2 className="font-semibold text-gray-900">Plans &amp; Billing</h2>
          </div>

          {/* Billing interval toggle */}
          {!isPaid && (
            <div className="flex items-center gap-1 p-0.5 bg-gray-100 rounded-lg text-xs">
              <button
                onClick={() => setBilling('monthly')}
                className={cn('px-3 py-1 rounded-md font-medium transition-colors', {
                  'bg-white shadow text-gray-900': billing === 'monthly',
                  'text-gray-500 hover:text-gray-700': billing === 'yearly',
                })}
              >
                Monthly
              </button>
              <button
                onClick={() => setBilling('yearly')}
                className={cn('px-3 py-1 rounded-md font-medium transition-colors', {
                  'bg-white shadow text-gray-900': billing === 'yearly',
                  'text-gray-500 hover:text-gray-700': billing === 'monthly',
                })}
              >
                Yearly
                <span className="ml-1 text-green-600">−17%</span>
              </button>
            </div>
          )}
        </div>

        {/* Manage subscription for paid users */}
        {isPaid && (
          <div className="mb-5 flex items-center justify-between p-4 bg-gray-50 rounded-xl">
            <div>
              <p className="text-sm font-medium text-gray-900">
                You&apos;re on the <span className="capitalize font-bold">{user.plan}</span> plan
              </p>
              <p className={cn('text-xs mt-0.5', statusInfo.color)}>
                Status: {statusInfo.label}
                {user.subscription_ends_at && (
                  <span className="text-gray-400 ml-1">
                    · {isCancelled ? 'Access until' : 'Renews'}{' '}
                    {new Date(user.subscription_ends_at).toLocaleDateString('en-AU', {
                      day: 'numeric', month: 'short', year: 'numeric',
                    })}
                  </span>
                )}
              </p>
            </div>
            <button
              onClick={handlePortal}
              disabled={portalLoading}
              className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm
                         text-gray-700 hover:bg-white hover:border-gray-300 transition-colors"
            >
              {portalLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ExternalLink className="w-3.5 h-3.5" />}
              Manage subscription
            </button>
          </div>
        )}

        {/* Plan cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {PLANS.map(plan => {
            const isCurrentPlan = user.plan === plan.id || (plan.id === 'free' && userRank === 0)
            const isUpgrade     = PLAN_RANK[plan.id] > userRank
            const isDowngrade   = PLAN_RANK[plan.id] < userRank
            const price         = billing === 'yearly' ? plan.yearly : plan.monthly

            return (
              <div
                key={plan.id}
                className={cn(
                  'border-2 rounded-xl p-4 relative transition-all',
                  plan.color,
                  isCurrentPlan ? 'bg-gray-50' : 'bg-white',
                  plan.id === 'premium' && 'ring-2 ring-purple-200',
                )}
              >
                {plan.id === 'premium' && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-purple-600 text-white text-[10px] font-bold px-3 py-0.5 rounded-full">
                    MOST POPULAR
                  </div>
                )}

                <div className="flex items-center gap-2 mb-3">
                  {plan.icon}
                  <span className={cn('text-xs font-bold px-2 py-0.5 rounded-full capitalize', plan.badge)}>
                    {plan.label}
                  </span>
                  {isCurrentPlan && (
                    <span className="ml-auto text-[10px] text-gray-500 font-medium">Current</span>
                  )}
                </div>

                {price ? (
                  <div className="mb-3">
                    <span className="text-2xl font-bold text-gray-900">${price.toFixed(2)}</span>
                    <span className="text-xs text-gray-500 ml-1">/{billing === 'yearly' ? 'yr' : 'mo'}</span>
                    {billing === 'yearly' && (
                      <p className="text-xs text-green-600 mt-0.5">
                        ≈ ${(price / 12).toFixed(2)}/mo
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="mb-3">
                    <span className="text-2xl font-bold text-gray-900">Free</span>
                    <span className="text-xs text-gray-500 ml-1">forever</span>
                  </div>
                )}

                <ul className="space-y-1.5 mb-4">
                  {plan.features.map(f => (
                    <li key={f} className="flex items-start gap-1.5 text-xs text-gray-600">
                      {isCurrentPlan || isDowngrade
                        ? <CheckCircle2 className="w-3.5 h-3.5 text-gray-400 shrink-0 mt-0.5" />
                        : <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0 mt-0.5" />
                      }
                      {f}
                    </li>
                  ))}
                </ul>

                {isCurrentPlan ? (
                  <div className="w-full py-2 text-center text-xs font-medium text-gray-400 border border-gray-200 rounded-lg">
                    Current plan
                  </div>
                ) : isUpgrade && plan.id !== 'free' ? (
                  <button
                    onClick={() => handleCheckout(plan.id as 'pro' | 'premium')}
                    disabled={checkoutPlan !== null}
                    className={cn(
                      'w-full py-2 text-white text-xs font-semibold rounded-lg transition-colors flex items-center justify-center gap-1.5',
                      plan.id === 'premium'
                        ? 'bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400'
                        : 'bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400',
                    )}
                  >
                    {checkoutPlan === plan.id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Lock className="w-3 h-3" />
                    )}
                    Upgrade to {plan.label}
                  </button>
                ) : isDowngrade && isPaid ? (
                  <button
                    onClick={handlePortal}
                    className="w-full py-2 text-gray-600 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Downgrade
                  </button>
                ) : null}
              </div>
            )
          })}
        </div>

        <p className="mt-4 text-xs text-gray-400 text-center">
          Prices in AUD · Cancel anytime · Instant access after payment · Secure checkout via Stripe
        </p>
      </div>
    </div>
  )
}
