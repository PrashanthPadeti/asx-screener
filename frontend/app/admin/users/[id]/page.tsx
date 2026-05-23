'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'
import {
  ChevronLeft, CheckCircle, XCircle, Clock, AlertCircle,
  User, Bell, Star, PieChart, Monitor, LifeBuoy, Mail,
  Globe, Shield, Save, Loader2, ShieldAlert, History,
} from 'lucide-react'

interface Session {
  ip_address: string | null
  user_agent: string | null
  created_at: string | null
  expires_at: string | null
  revoked: boolean
}

interface Ticket {
  id: string
  subject: string
  status: string
  category: string | null
  created_at: string | null
  updated_at: string | null
}

interface Notification {
  type: string
  channel: string
  sent_at: string | null
}

interface AdminOverride {
  old_plan: string
  new_plan: string
  admin_email: string
  status_change: string | null
  changed_at: string | null
}

interface UserDetail {
  id: string
  email: string
  name: string | null
  plan: string
  subscription_status: string
  email_verified: boolean
  created_at: string | null
  last_login_at: string | null
  subscription_ends_at: string | null
  activity: {
    watchlist_count: number
    alert_count: number
    total_alerts: number
    portfolio_count: number
    ticket_count: number
    screen_count: number
    public_screen_count: number
    notification_count: number
  }
  sessions: Session[]
  tickets: Ticket[]
  notifications: Notification[]
  admin_overrides: AdminOverride[]
  is_admin_override: boolean
}

const PLAN_BADGE: Record<string, string> = {
  free:               'bg-slate-100 text-slate-700',
  pro:                'bg-blue-100 text-blue-700',
  pro_monthly:        'bg-blue-100 text-blue-700',
  pro_annual:         'bg-blue-100 text-blue-800',
  premium:            'bg-purple-100 text-purple-700',
  premium_monthly:    'bg-purple-100 text-purple-700',
  premium_annual:     'bg-purple-100 text-purple-800',
  enterprise_pro:     'bg-amber-100 text-amber-700',
  enterprise_premium: 'bg-orange-100 text-orange-700',
}

const PLAN_LABEL: Record<string, string> = {
  free: 'Free', pro: 'Pro', pro_monthly: 'Pro Monthly', pro_annual: 'Pro Annual',
  premium: 'Premium', premium_monthly: 'Premium Monthly', premium_annual: 'Premium Annual',
  enterprise_pro: 'Enterprise Pro', enterprise_premium: 'Enterprise Premium',
}

const STATUS_CONFIG: Record<string, { cls: string; icon: React.ElementType; label: string }> = {
  active:   { cls: 'text-emerald-600 bg-emerald-50', icon: CheckCircle,  label: 'Active' },
  inactive: { cls: 'text-slate-500 bg-slate-100',   icon: Clock,        label: 'Inactive' },
  past_due: { cls: 'text-amber-600 bg-amber-50',    icon: AlertCircle,  label: 'Past Due' },
  cancelled:{ cls: 'text-red-500 bg-red-50',        icon: XCircle,      label: 'Cancelled' },
  trialing: { cls: 'text-blue-600 bg-blue-50',      icon: Clock,        label: 'Trialing' },
  suspended:{ cls: 'text-red-700 bg-red-100',       icon: XCircle,      label: 'Suspended' },
}

const TICKET_STATUS: Record<string, string> = {
  open:     'bg-blue-100 text-blue-700',
  pending:  'bg-amber-100 text-amber-700',
  resolved: 'bg-emerald-100 text-emerald-700',
  closed:   'bg-slate-100 text-slate-600',
}

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-AU', { dateStyle: 'medium', timeStyle: 'short' })
}

function fmtDateShort(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' })
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-5 py-3 border-b border-slate-100 bg-slate-50">
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 py-2 border-b border-slate-50 last:border-0">
      <span className="text-xs text-slate-400 w-36 shrink-0 pt-0.5">{label}</span>
      <span className="text-sm text-slate-700 flex-1">{value}</span>
    </div>
  )
}

function ActivityPill({ icon: Icon, label, value, color = 'slate' }: {
  icon: React.ElementType; label: string; value: number; color?: string
}) {
  const colors: Record<string, string> = {
    blue:   'bg-blue-50 text-blue-700 border-blue-100',
    green:  'bg-emerald-50 text-emerald-700 border-emerald-100',
    purple: 'bg-purple-50 text-purple-700 border-purple-100',
    amber:  'bg-amber-50 text-amber-700 border-amber-100',
    slate:  'bg-slate-50 text-slate-700 border-slate-100',
  }
  return (
    <div className={`flex flex-col items-center p-3 rounded-xl border ${colors[color]}`}>
      <Icon className="w-4 h-4 mb-1 opacity-70" />
      <span className="text-xl font-bold">{value}</span>
      <span className="text-[10px] font-medium opacity-60 mt-0.5">{label}</span>
    </div>
  )
}

export default function UserDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [user, setUser]       = useState<UserDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  // Edit state
  const [editPlan,   setEditPlan]   = useState('')
  const [editStatus, setEditStatus] = useState('')
  const [editName,   setEditName]   = useState('')
  const [saving, setSaving]         = useState(false)
  const [saveMsg, setSaveMsg]       = useState<string | null>(null)

  const [activeTab, setActiveTab] = useState<'overview' | 'sessions' | 'tickets' | 'notifications' | 'history'>('overview')

  useEffect(() => {
    const load = async () => {
      setLoading(true); setError(null)
      try {
        const { data } = await api.get(`/api/v1/admin/users/${id}`)
        setUser(data)
        setEditPlan(data.plan)
        setEditStatus(data.subscription_status)
        setEditName(data.name || '')
      } catch (e: any) {
        setError(e?.response?.data?.detail || 'Failed to load user')
      } finally {
        setLoading(false)
      }
    }
    if (id) load()
  }, [id])

  const handleSave = async () => {
    if (!user) return
    setSaving(true); setSaveMsg(null)
    try {
      const body: Record<string, string> = {}
      if (editPlan   !== user.plan)                body.plan = editPlan
      if (editStatus !== user.subscription_status) body.subscription_status = editStatus
      if (editName   !== (user.name || ''))        body.name = editName

      if (Object.keys(body).length === 0) {
        setSaveMsg('No changes to save.')
        setSaving(false)
        return
      }

      const { data } = await api.patch(`/api/v1/admin/users/${id}`, body)
      setUser(prev => prev ? { ...prev, plan: data.plan, subscription_status: data.subscription_status, name: data.name } : prev)
      setSaveMsg('Changes saved.')
    } catch (e: any) {
      setSaveMsg(e?.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="space-y-4 animate-pulse">
          <div className="h-8 bg-slate-100 rounded w-48" />
          <div className="h-32 bg-slate-100 rounded-xl" />
          <div className="h-48 bg-slate-100 rounded-xl" />
        </div>
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700">{error || 'User not found'}</div>
      </div>
    )
  }

  const statusCfg = STATUS_CONFIG[user.subscription_status] ?? { cls: 'text-slate-500 bg-slate-100', icon: Clock, label: user.subscription_status }
  const StatusIcon = statusCfg.icon

  const tabs = [
    { key: 'overview' as const,       label: 'Overview' },
    { key: 'sessions' as const,       label: `Sessions (${user.sessions.length})` },
    { key: 'tickets' as const,        label: `Tickets (${user.tickets.length})` },
    { key: 'notifications' as const,  label: `Notifications (${user.notifications.length})` },
    { key: 'history' as const,        label: `Override History (${user.admin_overrides?.length ?? 0})`, highlight: user.is_admin_override },
  ]

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">

      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Link href="/admin/users" className="flex items-center gap-1 hover:text-slate-700">
          <ChevronLeft className="w-4 h-4" />Users
        </Link>
        <span>/</span>
        <span className="text-slate-700 font-medium truncate max-w-[300px]">{user.email}</span>
      </div>

      {/* Header card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex flex-wrap items-start gap-4 justify-between">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-blue-600 text-white flex items-center justify-center text-2xl font-bold">
              {(user.name || user.email)[0].toUpperCase()}
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl font-bold text-slate-900">{user.name || '—'}</h1>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PLAN_BADGE[user.plan] ?? 'bg-slate-100 text-slate-600'}`}>
                  {PLAN_LABEL[user.plan] ?? user.plan}
                </span>
                <span className={`flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${statusCfg.cls}`}>
                  <StatusIcon className="w-3 h-3" />{statusCfg.label}
                </span>
                {user.email_verified
                  ? <span className="flex items-center gap-1 text-xs text-emerald-600"><CheckCircle className="w-3 h-3" />Verified</span>
                  : <span className="flex items-center gap-1 text-xs text-amber-500"><AlertCircle className="w-3 h-3" />Unverified</span>}
                {user.is_admin_override && (
                  <span className="flex items-center gap-1 text-xs font-semibold text-orange-600 bg-orange-50 border border-orange-200 px-2 py-0.5 rounded-full">
                    <ShieldAlert className="w-3 h-3" /> Admin Override
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-500 mt-1">{user.email}</p>
              <p className="text-xs text-slate-400 mt-0.5">
                Joined {fmtDateShort(user.created_at)} · Last login {user.last_login_at ? fmtDate(user.last_login_at) : 'Never'}
              </p>
            </div>
          </div>

          {/* Edit Panel */}
          <div className="flex flex-col gap-2 min-w-[220px]">
            <div className="flex gap-2">
              <select
                value={editPlan}
                onChange={e => setEditPlan(e.target.value)}
                className="flex-1 text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="free">Free</option>
                <option value="pro">Pro</option>
                <option value="premium">Premium</option>
                <option value="enterprise_pro">Enterprise Pro</option>
                <option value="enterprise_premium">Enterprise Premium</option>
              </select>
              <select
                value={editStatus}
                onChange={e => setEditStatus(e.target.value)}
                className="flex-1 text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="trialing">Trialing</option>
                <option value="past_due">Past Due</option>
                <option value="cancelled">Cancelled</option>
                <option value="suspended">Suspended</option>
              </select>
            </div>
            <input
              value={editName}
              onChange={e => setEditName(e.target.value)}
              placeholder="Name…"
              className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50"
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              Save Changes
            </button>
            {saveMsg && <p className="text-xs text-center text-slate-500">{saveMsg}</p>}
            <p className="text-[10px] text-center text-slate-400">Plan/status changes are audit-logged</p>
          </div>
        </div>
      </div>

      {/* Activity summary */}
      <div className="grid grid-cols-4 sm:grid-cols-8 gap-3">
        <ActivityPill icon={Star}     label="Watchlists" value={user.activity.watchlist_count}     color="amber"  />
        <ActivityPill icon={Bell}     label="Alerts"     value={user.activity.alert_count}         color="blue"   />
        <ActivityPill icon={PieChart} label="Portfolios" value={user.activity.portfolio_count}     color="green"  />
        <ActivityPill icon={Monitor}  label="Screens"    value={user.activity.screen_count}        color="purple" />
        <ActivityPill icon={Globe}    label="Public"     value={user.activity.public_screen_count} color="slate"  />
        <ActivityPill icon={LifeBuoy} label="Tickets"    value={user.activity.ticket_count}        color={user.activity.ticket_count > 0 ? 'amber' : 'slate'} />
        <ActivityPill icon={Mail}     label="Notifs"     value={user.activity.notification_count}  color="slate"  />
        <ActivityPill icon={Bell}     label="All Alerts" value={user.activity.total_alerts}        color="slate"  />
      </div>

      {/* Tabs */}
      <div>
        <div className="flex gap-0 border-b border-slate-200 flex-wrap">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                activeTab === t.key
                  ? (t.highlight ? 'border-orange-500 text-orange-600' : 'border-blue-600 text-blue-600')
                  : (t.highlight ? 'border-transparent text-orange-500 hover:text-orange-600' : 'border-transparent text-slate-500 hover:text-slate-700')
              }`}
            >
              {t.highlight && <ShieldAlert className="w-3.5 h-3.5" />}
              {t.label}
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-4">

          {/* ── Overview Tab ──────────────────────────────── */}
          {activeTab === 'overview' && (
            <>
              <Section title="Profile">
                <InfoRow label="User ID"              value={<span className="font-mono text-xs">{user.id}</span>} />
                <InfoRow label="Email"                value={user.email} />
                <InfoRow label="Name"                 value={user.name || <span className="text-slate-300">Not set</span>} />
                <InfoRow label="Email Verified"       value={user.email_verified ? '✅ Verified' : '⚠️ Not verified'} />
                <InfoRow label="Joined"               value={fmtDate(user.created_at)} />
                <InfoRow label="Last Login"           value={user.last_login_at ? fmtDate(user.last_login_at) : 'Never'} />
              </Section>

              <Section title="Subscription">
                <InfoRow label="Plan"                 value={
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PLAN_BADGE[user.plan] ?? 'bg-slate-100 text-slate-600'}`}>
                      {PLAN_LABEL[user.plan] ?? user.plan}
                    </span>
                    {user.is_admin_override && (
                      <span className="flex items-center gap-1 text-[10px] font-semibold text-orange-600 bg-orange-50 border border-orange-200 px-1.5 py-0.5 rounded">
                        <ShieldAlert className="w-2.5 h-2.5" /> Admin Override
                      </span>
                    )}
                  </div>
                } />
                <InfoRow label="Status"               value={
                  <span className={`flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${statusCfg.cls}`}>
                    <StatusIcon className="w-3 h-3" />{statusCfg.label}
                  </span>
                } />
                <InfoRow label="Subscription Ends"    value={user.subscription_ends_at ? fmtDate(user.subscription_ends_at) : '—'} />
                {user.is_admin_override && (
                  <div className="mt-3 flex items-start gap-2 p-3 bg-orange-50 border border-orange-200 rounded-lg">
                    <ShieldAlert className="w-4 h-4 text-orange-500 shrink-0 mt-0.5" />
                    <div className="text-xs text-orange-700">
                      <p className="font-semibold">Manually set by admin — no Stripe subscription</p>
                      <p className="mt-0.5 text-orange-600">This account has no billing record. There is no automatic expiry. See Override History tab for full audit log.</p>
                    </div>
                  </div>
                )}
              </Section>
            </>
          )}

          {/* ── Sessions Tab ─────────────────────────────── */}
          {activeTab === 'sessions' && (
            <Section title="Login Sessions (Last 10)">
              {user.sessions.length === 0 ? (
                <p className="text-sm text-slate-400">No sessions found</p>
              ) : (
                <div className="space-y-2">
                  {user.sessions.map((s, i) => (
                    <div key={i} className={`flex flex-wrap items-start gap-3 p-3 rounded-lg border ${s.revoked ? 'border-red-100 bg-red-50/30' : 'border-slate-100 bg-slate-50'}`}>
                      <div className="flex items-center gap-2">
                        <Globe className={`w-4 h-4 ${s.revoked ? 'text-red-400' : 'text-slate-400'}`} />
                        <span className="font-mono text-xs text-slate-700">{s.ip_address || '—'}</span>
                        {s.revoked && <span className="text-[10px] text-red-500 font-semibold">REVOKED</span>}
                      </div>
                      <div className="flex-1 text-xs text-slate-400 truncate">{s.user_agent || '—'}</div>
                      <div className="text-xs text-slate-400 whitespace-nowrap">{fmtDate(s.created_at)}</div>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          )}

          {/* ── Tickets Tab ──────────────────────────────── */}
          {activeTab === 'tickets' && (
            <Section title="Support Tickets (Last 5)">
              {user.tickets.length === 0 ? (
                <p className="text-sm text-slate-400">No support tickets</p>
              ) : (
                <div className="space-y-2">
                  {user.tickets.map(t => (
                    <div key={t.id} className="flex items-start gap-3 p-3 rounded-lg border border-slate-100 bg-slate-50">
                      <LifeBuoy className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-700 truncate">{t.subject}</p>
                        {t.category && <p className="text-xs text-slate-400">{t.category}</p>}
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${TICKET_STATUS[t.status] ?? 'bg-slate-100 text-slate-600'}`}>
                          {t.status}
                        </span>
                        <span className="text-[10px] text-slate-400">{fmtDateShort(t.created_at)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          )}

          {/* ── Notifications Tab ────────────────────────── */}
          {activeTab === 'notifications' && (
            <Section title="Notification History (Last 10)">
              {user.notifications.length === 0 ? (
                <p className="text-sm text-slate-400">No notifications sent</p>
              ) : (
                <div className="space-y-2">
                  {user.notifications.map((n, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 rounded-lg border border-slate-100 bg-slate-50">
                      <Bell className="w-4 h-4 text-slate-400 shrink-0" />
                      <div className="flex-1">
                        <span className="text-sm font-medium text-slate-700">{n.type}</span>
                      </div>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 font-medium">{n.channel}</span>
                      <span className="text-xs text-slate-400 whitespace-nowrap">{fmtDate(n.sent_at)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          )}

          {/* ── Override History Tab ─────────────────────── */}
          {activeTab === 'history' && (
            <Section title="Admin Override History">
              {!user.admin_overrides || user.admin_overrides.length === 0 ? (
                <div className="flex items-center gap-3 py-4 text-slate-400">
                  <History className="w-5 h-5" />
                  <p className="text-sm">No admin overrides on record. All plan changes have gone through Stripe.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs text-slate-500 mb-3">
                    {user.admin_overrides.length} manual override{user.admin_overrides.length !== 1 ? 's' : ''} recorded.
                    These changes bypassed Stripe — there is no associated billing record.
                  </p>
                  {user.admin_overrides.map((o, i) => (
                    <div key={i} className="flex items-start gap-3 p-4 rounded-xl border border-orange-200 bg-orange-50">
                      <ShieldAlert className="w-4 h-4 text-orange-500 shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-semibold text-slate-800">Plan:</span>
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PLAN_BADGE[o.old_plan] ?? 'bg-slate-100 text-slate-600'}`}>
                            {PLAN_LABEL[o.old_plan] ?? o.old_plan}
                          </span>
                          <span className="text-slate-400">→</span>
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PLAN_BADGE[o.new_plan] ?? 'bg-slate-100 text-slate-600'}`}>
                            {PLAN_LABEL[o.new_plan] ?? o.new_plan}
                          </span>
                        </div>
                        {o.status_change && (
                          <div className="mt-1 text-xs text-orange-700">
                            <span className="font-medium">Status:</span> {o.status_change}
                          </div>
                        )}
                        <div className="mt-1 text-xs text-slate-500">
                          By <span className="font-medium text-slate-700">{o.admin_email}</span>
                          {' · '}{fmtDate(o.changed_at)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          )}
        </div>
      </div>
    </div>
  )
}
