'use client'
import { useState, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { User, CreditCard, Bell, Shield, CheckCircle2, Loader2, LogIn } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const PLAN_COLORS: Record<string, string> = {
  free:       'bg-gray-100 text-gray-700',
  pro:        'bg-blue-100 text-blue-700',
  premium:    'bg-purple-100 text-purple-700',
  enterprise: 'bg-amber-100 text-amber-700',
}

const PRO_FEATURES = [
  'CSV export (up to 5,000 rows)',
  '20 watchlists (500 stocks each)',
  '50 price alerts',
  'Priority data refresh',
  'Email support',
]

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

  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [portalLoading,   setPortalLoading]   = useState(false)

  async function handleUpgrade() {
    setCheckoutLoading(true)
    try {
      const { data } = await api.post('/api/v1/billing/checkout')
      window.location.href = data.url
    } catch {
      alert('Billing is not configured yet. Check back soon!')
    } finally { setCheckoutLoading(false) }
  }

  async function handlePortal() {
    setPortalLoading(true)
    try {
      const { data } = await api.post('/api/v1/billing/portal')
      window.location.href = data.url
    } catch {
      alert('No billing account found.')
    } finally { setPortalLoading(false) }
  }

  if (loading) {
    return (
      <div className="space-y-4 max-w-2xl">
        {[1,2,3].map(i => <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }

  if (!user) {
    return (
      <div className="max-w-lg mx-auto text-center py-20">
        <User className="w-12 h-12 text-gray-200 mx-auto mb-4" />
        <h1 className="text-xl font-bold text-gray-900 mb-2">Account Settings</h1>
        <p className="text-gray-500 mb-6">Sign in to manage your account and billing.</p>
        <Link href="/auth/login"
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700">
          <LogIn className="w-4 h-4" />
          Sign in
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
        <User className="w-5 h-5" />
        Account Settings
      </h1>

      {/* Upgrade success banner */}
      {upgradeStatus === 'success' && (
        <div className="flex items-center gap-2 px-4 py-3 bg-green-50 border border-green-200 rounded-xl text-sm text-green-700">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          Your subscription is now active. Welcome to Pro!
        </div>
      )}

      {/* Profile card */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-sm">
            {(user.name || user.email)[0].toUpperCase()}
          </div>
          <div>
            <p className="font-medium text-gray-900">{user.name || '—'}</p>
            <p className="text-sm text-gray-500">{user.email}</p>
          </div>
          <span className={cn('ml-auto text-xs px-2.5 py-1 rounded-full font-semibold capitalize',
            PLAN_COLORS[user.plan] ?? PLAN_COLORS.free)}>
            {user.plan}
          </span>
        </div>
        <div className="border-t border-gray-100 pt-3 grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-gray-500 mb-0.5">Email verified</p>
            <p className={user.email_verified ? 'text-green-600 font-medium' : 'text-amber-600'}>
              {user.email_verified ? '✓ Verified' : 'Not verified'}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-0.5">Plan</p>
            <p className="font-medium text-gray-900 capitalize">{user.plan}</p>
          </div>
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

      {/* Billing card */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <CreditCard className="w-4 h-4 text-gray-600" />
          <h2 className="font-semibold text-gray-900">Billing</h2>
        </div>

        {user.plan === 'free' ? (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
              <p className="text-sm font-semibold text-blue-900 mb-1">Upgrade to Pro — A$29/month</p>
              <ul className="space-y-1.5 mt-2">
                {PRO_FEATURES.map(f => (
                  <li key={f} className="flex items-start gap-2 text-sm text-blue-800">
                    <CheckCircle2 className="w-3.5 h-3.5 text-blue-500 mt-0.5 shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
            <button onClick={handleUpgrade} disabled={checkoutLoading}
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 hover:bg-blue-700
                         disabled:bg-blue-400 text-white font-medium rounded-lg transition-colors">
              {checkoutLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              Upgrade to Pro
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-700">
              You&apos;re on the <strong className="capitalize">{user.plan}</strong> plan.
            </p>
            <button onClick={handlePortal} disabled={portalLoading}
              className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm
                         text-gray-700 hover:bg-gray-50 transition-colors">
              {portalLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Manage subscription
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
