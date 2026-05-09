'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import Link from 'next/link'
import {
  Users, TrendingUp, DollarSign, LifeBuoy,
  Bell, Star, PieChart, Monitor, Activity,
  ArrowRight, RefreshCw, Layers, AlertTriangle,
} from 'lucide-react'

interface Stats {
  users: {
    total: number
    by_plan: Record<string, number>
    paying: number
    active_subscriptions: number
    new_1d: number
    new_7d: number
    new_30d: number
    active_7d: number
    active_30d: number
    conversion_rate: number
  }
  support: { open_tickets: number; total_tickets: number }
  platform: {
    active_alerts: number
    watchlists: number
    portfolios: number
    saved_screens: number
    public_screens: number
    universe_stocks: number
    active_anomalies: number
  }
}

const PLAN_COLORS: Record<string, string> = {
  free:              'bg-slate-100 text-slate-700',
  pro:               'bg-blue-100 text-blue-700',
  premium:           'bg-purple-100 text-purple-700',
  enterprise_pro:    'bg-amber-100 text-amber-700',
  enterprise_premium:'bg-orange-100 text-orange-700',
}

const PLAN_LABEL: Record<string, string> = {
  free: 'Free', pro: 'Pro', premium: 'Premium',
  enterprise_pro: 'Ent. Pro', enterprise_premium: 'Ent. Premium',
}

function StatCard({
  label, value, sub, icon: Icon, color = 'blue', href,
}: {
  label: string; value: string | number; sub?: string
  icon: React.ElementType; color?: string; href?: string
}) {
  const colors: Record<string, string> = {
    blue:   'bg-blue-50 text-blue-600',
    green:  'bg-emerald-50 text-emerald-600',
    purple: 'bg-purple-50 text-purple-600',
    amber:  'bg-amber-50 text-amber-600',
    red:    'bg-red-50 text-red-600',
    slate:  'bg-slate-100 text-slate-600',
  }
  const card = (
    <div className="bg-white rounded-xl border border-slate-200 p-5 flex items-start gap-4 hover:border-slate-300 transition-colors">
      <div className={`p-2.5 rounded-lg ${colors[color]}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-500 font-medium">{label}</p>
        <p className="text-2xl font-bold text-slate-800 mt-0.5">{value}</p>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
      </div>
      {href && <ArrowRight className="w-4 h-4 text-slate-300 mt-1 shrink-0" />}
    </div>
  )
  return href ? <Link href={href}>{card}</Link> : card
}

export default function AdminDashboard() {
  const [stats, setStats]     = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [refreshed, setRefreshed] = useState<Date | null>(null)

  const load = async () => {
    setLoading(true); setError(null)
    try {
      const { data } = await api.get('/api/v1/admin/stats')
      setStats(data)
      setRefreshed(new Date())
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load stats')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Admin Dashboard</h1>
          {refreshed && (
            <p className="text-xs text-slate-400 mt-0.5">
              Updated {refreshed.toLocaleTimeString('en-AU')}
            </p>
          )}
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error}</div>
      )}

      {loading && !stats ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 h-28 animate-pulse">
              <div className="w-10 h-10 bg-slate-100 rounded-lg mb-3" />
              <div className="h-3 bg-slate-100 rounded w-2/3 mb-2" />
              <div className="h-6 bg-slate-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : stats ? (
        <>
          {/* ── User Stats ──────────────────────────────────── */}
          <section>
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Users</h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard label="Total Users"        value={stats.users.total.toLocaleString()} icon={Users}      color="blue"   href="/admin/users" />
              <StatCard label="Paying Users"       value={stats.users.paying.toLocaleString()} sub={`${stats.users.conversion_rate}% conversion`} icon={DollarSign} color="green" href="/admin/users?plan=pro" />
              <StatCard label="Active (7d)"        value={stats.users.active_7d.toLocaleString()} sub={`${stats.users.active_30d.toLocaleString()} in 30d`} icon={TrendingUp} color="purple" />
              <StatCard label="New Signups (7d)"   value={stats.users.new_7d.toLocaleString()}  sub={`${stats.users.new_1d} today · ${stats.users.new_30d} this month`} icon={Users} color="amber" />
            </div>
          </section>

          {/* ── Plan Breakdown ──────────────────────────────── */}
          <section>
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Plan Breakdown</h2>
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex flex-wrap gap-3">
                {Object.entries(stats.users.by_plan).map(([plan, count]) => {
                  const pct = stats.users.total > 0 ? (count / stats.users.total * 100).toFixed(1) : '0'
                  return (
                    <Link
                      key={plan}
                      href={`/admin/users?plan=${plan}`}
                      className="flex items-center gap-2 px-4 py-3 rounded-xl border border-slate-100 hover:border-slate-300 transition-colors"
                    >
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PLAN_COLORS[plan] ?? 'bg-slate-100 text-slate-600'}`}>
                        {PLAN_LABEL[plan] ?? plan}
                      </span>
                      <span className="text-xl font-bold text-slate-800">{count.toLocaleString()}</span>
                      <span className="text-xs text-slate-400">{pct}%</span>
                    </Link>
                  )
                })}
              </div>

              {/* Simple bar chart */}
              <div className="mt-4 h-3 bg-slate-100 rounded-full overflow-hidden flex gap-0.5">
                {Object.entries(stats.users.by_plan).map(([plan, count]) => {
                  const pct = stats.users.total > 0 ? (count / stats.users.total * 100) : 0
                  const barColors: Record<string, string> = {
                    free: 'bg-slate-400', pro: 'bg-blue-500',
                    premium: 'bg-purple-500', enterprise_pro: 'bg-amber-500',
                    enterprise_premium: 'bg-orange-500',
                  }
                  return pct > 0 ? (
                    <div
                      key={plan}
                      className={`h-full ${barColors[plan] ?? 'bg-slate-300'}`}
                      style={{ width: `${pct}%` }}
                      title={`${PLAN_LABEL[plan] ?? plan}: ${count}`}
                    />
                  ) : null
                })}
              </div>
            </div>
          </section>

          {/* ── Platform & Support ──────────────────────────── */}
          <section>
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Platform & Support</h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard label="Open Tickets"       value={stats.support.open_tickets}    sub={`${stats.support.total_tickets} total`} icon={LifeBuoy}  color={stats.support.open_tickets > 0 ? 'amber' : 'slate'} href="/admin/support" />
              <StatCard label="Active Alerts"      value={stats.platform.active_alerts.toLocaleString()} icon={Bell}      color="blue" />
              <StatCard label="Watchlists"          value={stats.platform.watchlists.toLocaleString()}    icon={Star}      color="slate" />
              <StatCard label="Portfolios"          value={stats.platform.portfolios.toLocaleString()}    icon={PieChart}  color="slate" />
              <StatCard label="Saved Screens"       value={stats.platform.saved_screens.toLocaleString()} sub={`${stats.platform.public_screens} public`} icon={Monitor}   color="purple" />
              <StatCard label="Active Stocks"       value={stats.platform.universe_stocks.toLocaleString()} icon={Layers}  color="blue" />
              <StatCard label="Active Anomalies"    value={stats.platform.active_anomalies.toLocaleString()} icon={AlertTriangle} color="amber" />
              <StatCard label="Pipeline Jobs"       value="12"  sub="View health status" icon={Activity}  color="green"  href="/admin/pipeline" />
            </div>
          </section>

          {/* ── Quick Links ─────────────────────────────────── */}
          <section>
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Quick Actions</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                { href: '/admin/users',    label: 'Manage Users',    desc: 'Search, filter and update user plans',  icon: Users,     color: 'bg-blue-50 border-blue-200 text-blue-700' },
                { href: '/admin/pipeline', label: 'Pipeline Health', desc: 'Check daily job execution status',     icon: Activity,  color: 'bg-emerald-50 border-emerald-200 text-emerald-700' },
                { href: '/admin/support',  label: 'Support Queue',   desc: `${stats.support.open_tickets} tickets need attention`, icon: LifeBuoy, color: stats.support.open_tickets > 0 ? 'bg-amber-50 border-amber-200 text-amber-700' : 'bg-slate-50 border-slate-200 text-slate-600' },
              ].map(({ href, label, desc, icon: Icon, color }) => (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-start gap-3 p-4 rounded-xl border ${color} hover:opacity-90 transition-opacity`}
                >
                  <Icon className="w-5 h-5 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-semibold text-sm">{label}</p>
                    <p className="text-xs mt-0.5 opacity-75">{desc}</p>
                  </div>
                  <ArrowRight className="w-4 h-4 ml-auto shrink-0 mt-0.5 opacity-50" />
                </Link>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}
