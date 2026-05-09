'use client'
import { useEffect, useState, useCallback } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'
import {
  Search, ChevronLeft, ChevronRight, ChevronUp, ChevronDown,
  CheckCircle, XCircle, Clock, AlertCircle, ArrowRight,
} from 'lucide-react'

interface AdminUser {
  id: string
  email: string
  name: string | null
  plan: string
  subscription_status: string
  email_verified: boolean
  created_at: string | null
  last_login_at: string | null
  subscription_ends_at: string | null
  watchlist_count: number
  alert_count: number
  portfolio_count: number
  screen_count: number
  ticket_count: number
  last_ip: string | null
}

interface UserListResponse {
  users: AdminUser[]
  total: number
  page: number
  limit: number
  pages: number
}

const PLAN_BADGE: Record<string, string> = {
  free:               'bg-slate-100 text-slate-700',
  pro:                'bg-blue-100 text-blue-700',
  premium:            'bg-purple-100 text-purple-700',
  enterprise_pro:     'bg-amber-100 text-amber-700',
  enterprise_premium: 'bg-orange-100 text-orange-700',
}

const PLAN_LABEL: Record<string, string> = {
  free: 'Free', pro: 'Pro', premium: 'Premium',
  enterprise_pro: 'Ent Pro', enterprise_premium: 'Ent Premium',
}

const STATUS_CONFIG: Record<string, { cls: string; icon: React.ElementType; label: string }> = {
  active:   { cls: 'text-emerald-600', icon: CheckCircle,  label: 'Active' },
  inactive: { cls: 'text-slate-400',   icon: Clock,        label: 'Inactive' },
  past_due: { cls: 'text-amber-600',   icon: AlertCircle,  label: 'Past Due' },
  cancelled:{ cls: 'text-red-500',     icon: XCircle,      label: 'Cancelled' },
  trialing: { cls: 'text-blue-500',    icon: Clock,        label: 'Trial' },
  suspended:{ cls: 'text-red-700',     icon: XCircle,      label: 'Suspended' },
}

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' })
}

function fmtAge(iso: string | null) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3600000)
  const d = Math.floor(h / 24)
  if (d > 30) return `${Math.floor(d / 30)}mo ago`
  if (d >= 1) return `${d}d ago`
  if (h >= 1) return `${h}h ago`
  return 'Just now'
}

export default function AdminUsersPage() {
  const searchParams  = useSearchParams()
  const router        = useRouter()

  const [data, setData]       = useState<UserListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  // Filters
  const [search,  setSearch]  = useState(searchParams.get('search') || '')
  const [plan,    setPlan]    = useState(searchParams.get('plan') || '')
  const [status,  setStatus]  = useState(searchParams.get('status') || '')
  const [page,    setPage]    = useState(Number(searchParams.get('page') || 1))
  const [sortBy,  setSortBy]  = useState('created_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const params = new URLSearchParams({
        page: String(page), limit: '50',
        search, plan, subscription_status: status,
        sort_by: sortBy, sort_dir: sortDir,
      })
      const { data: res } = await api.get(`/api/v1/admin/users?${params}`)
      setData(res)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }, [page, search, plan, status, sortBy, sortDir])

  useEffect(() => { load() }, [load])

  function toggleSort(col: string) {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortDir('desc') }
    setPage(1)
  }

  function SortIcon({ col }: { col: string }) {
    if (sortBy !== col) return <ChevronUp className="w-3 h-3 text-slate-300" />
    return sortDir === 'asc'
      ? <ChevronUp className="w-3 h-3 text-blue-500" />
      : <ChevronDown className="w-3 h-3 text-blue-500" />
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setPage(1)
    load()
  }

  const StatusBadge = ({ s }: { s: string }) => {
    const cfg = STATUS_CONFIG[s] ?? { cls: 'text-slate-500', icon: Clock, label: s }
    const Icon = cfg.icon
    return (
      <span className={`flex items-center gap-1 text-xs font-medium ${cfg.cls}`}>
        <Icon className="w-3 h-3" />{cfg.label}
      </span>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">User Management</h1>
        {data && <p className="text-sm text-slate-400 mt-0.5">{data.total.toLocaleString()} users found</p>}
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <form onSubmit={handleSearch} className="flex flex-wrap gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search email or name…"
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Plan filter */}
          <select
            value={plan}
            onChange={e => { setPlan(e.target.value); setPage(1) }}
            className="px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Plans</option>
            <option value="free">Free</option>
            <option value="pro">Pro</option>
            <option value="premium">Premium</option>
            <option value="enterprise_pro">Enterprise Pro</option>
            <option value="enterprise_premium">Enterprise Premium</option>
          </select>

          {/* Status filter */}
          <select
            value={status}
            onChange={e => { setStatus(e.target.value); setPage(1) }}
            className="px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="trialing">Trialing</option>
            <option value="past_due">Past Due</option>
            <option value="cancelled">Cancelled</option>
            <option value="suspended">Suspended</option>
          </select>

          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            Search
          </button>
        </form>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error}</div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 bg-slate-50 border-b border-slate-100">
                <th className="py-3 px-4 text-left font-semibold">
                  <button onClick={() => toggleSort('email')} className="flex items-center gap-1 hover:text-slate-700">
                    User <SortIcon col="email" />
                  </button>
                </th>
                <th className="py-3 px-4 text-left font-semibold">Plan</th>
                <th className="py-3 px-4 text-left font-semibold">Status</th>
                <th className="py-3 px-4 text-right font-semibold hidden md:table-cell">
                  <button onClick={() => toggleSort('created_at')} className="flex items-center gap-1 ml-auto hover:text-slate-700">
                    Joined <SortIcon col="created_at" />
                  </button>
                </th>
                <th className="py-3 px-4 text-right font-semibold hidden lg:table-cell">
                  <button onClick={() => toggleSort('last_login_at')} className="flex items-center gap-1 ml-auto hover:text-slate-700">
                    Last Login <SortIcon col="last_login_at" />
                  </button>
                </th>
                <th className="py-3 px-4 text-center font-semibold hidden lg:table-cell">Activity</th>
                <th className="py-3 px-4 text-center font-semibold">Verified</th>
                <th className="py-3 px-4" />
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      {Array.from({ length: 8 }).map((_, j) => (
                        <td key={j} className="py-3 px-4">
                          <div className="h-4 bg-slate-100 rounded animate-pulse w-3/4" />
                        </td>
                      ))}
                    </tr>
                  ))
                : data?.users.map(u => (
                    <tr key={u.id} className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
                      {/* User */}
                      <td className="py-3 px-4">
                        <div className="font-medium text-slate-800">{u.email}</div>
                        {u.name && <div className="text-xs text-slate-400">{u.name}</div>}
                        {u.last_ip && <div className="text-[10px] text-slate-300 font-mono">{u.last_ip}</div>}
                      </td>

                      {/* Plan */}
                      <td className="py-3 px-4">
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PLAN_BADGE[u.plan] ?? 'bg-slate-100 text-slate-600'}`}>
                          {PLAN_LABEL[u.plan] ?? u.plan}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="py-3 px-4">
                        <StatusBadge s={u.subscription_status} />
                      </td>

                      {/* Joined */}
                      <td className="py-3 px-4 text-right text-xs text-slate-500 hidden md:table-cell whitespace-nowrap">
                        {fmtDate(u.created_at)}
                      </td>

                      {/* Last login */}
                      <td className="py-3 px-4 text-right text-xs text-slate-500 hidden lg:table-cell whitespace-nowrap">
                        {fmtAge(u.last_login_at)}
                      </td>

                      {/* Activity */}
                      <td className="py-3 px-4 hidden lg:table-cell">
                        <div className="flex items-center justify-center gap-3 text-[11px] text-slate-500">
                          {u.watchlist_count > 0 && <span title="Watchlists">⭐ {u.watchlist_count}</span>}
                          {u.alert_count > 0     && <span title="Alerts">🔔 {u.alert_count}</span>}
                          {u.portfolio_count > 0 && <span title="Portfolios">📊 {u.portfolio_count}</span>}
                          {u.screen_count > 0    && <span title="Saved screens">🔍 {u.screen_count}</span>}
                          {u.ticket_count > 0    && <span title="Support tickets">🎫 {u.ticket_count}</span>}
                          {u.watchlist_count === 0 && u.alert_count === 0 && u.portfolio_count === 0 && u.screen_count === 0 && (
                            <span className="text-slate-300">None</span>
                          )}
                        </div>
                      </td>

                      {/* Verified */}
                      <td className="py-3 px-4 text-center">
                        {u.email_verified
                          ? <CheckCircle className="w-4 h-4 text-emerald-500 mx-auto" />
                          : <Clock className="w-4 h-4 text-slate-300 mx-auto" />}
                      </td>

                      {/* Action */}
                      <td className="py-3 px-4">
                        <Link
                          href={`/admin/users/${u.id}`}
                          className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors whitespace-nowrap"
                        >
                          View <ArrowRight className="w-3 h-3" />
                        </Link>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>

        {!loading && data?.users.length === 0 && (
          <div className="py-12 text-center text-slate-400 text-sm">No users found</div>
        )}
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            Showing {((page - 1) * 50) + 1}–{Math.min(page * 50, data.total)} of {data.total.toLocaleString()} users
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-slate-600 px-2">Page {page} of {data.pages}</span>
            <button
              onClick={() => setPage(p => Math.min(data.pages, p + 1))}
              disabled={page === data.pages}
              className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
