'use client'
import { useEffect, useState, useRef } from 'react'
import { api } from '@/lib/api'
import {
  Mail, Zap, Megaphone, XCircle, RefreshCw,
  CheckCircle, AlertCircle, Phone, ExternalLink,
  ChevronDown, ChevronUp,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface CommsSummary {
  notifications_today: number
  notifications_7d: number
  notifications_30d: number
  failed_24h: number
  alert_triggers_today: number
  alert_triggers_7d: number
  announcements_today: number
  announcements_sensitive_7d: number
}

interface NotifRow {
  notification_type: string
  channel: string
  subject: string | null
  recipient: string | null
  status: string
  error_message: string | null
  attempt_count: number
  sent_at: string | null
  user_email: string | null
  user_name: string | null
  user_plan: string | null
}

interface TriggerRow {
  triggered_at: string
  trigger_value: number
  notification_sent: boolean
  asx_code: string
  company_name: string | null
  alert_type: string
  threshold_value: number
  repeat_mode: string
  user_email: string | null
  user_name: string | null
  user_plan: string | null
}

interface AnnouncementRow {
  asx_code: string
  company_name: string | null
  title: string
  document_type: string
  url: string | null
  market_sensitive: boolean
  released_at: string
  source_type: string
  source_label: string
  notif_sent_count: number
}

interface CommsData {
  summary: CommsSummary
  by_type: Record<string, number>
  by_channel: Record<string, number>
  notifications: NotifRow[]
  triggers: TriggerRow[]
  announcements: AnnouncementRow[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-AU', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

function fmtAlertType(t: string): string {
  const map: Record<string, string> = {
    price_above: 'Price ↑', price_below: 'Price ↓',
    pct_1d_above: '1d Move ↑', pct_1w_above: '1w Move ↑',
    pct_change_above: 'Pct ↑', pct_change_below: 'Pct ↓',
    div_yield_above: 'Yield ↑', pe_below: 'P/E ↓',
    rsi_below_30: 'RSI<30', rsi_above_70: 'RSI>70',
    announcement: 'Announcement',
  }
  return map[t] ?? t
}

const PLAN_PILL: Record<string, string> = {
  free:    'bg-slate-100 text-slate-600',
  pro:     'bg-blue-100 text-blue-700',
  premium: 'bg-purple-100 text-purple-700',
  enterprise_pro:    'bg-amber-100 text-amber-700',
  enterprise_premium:'bg-orange-100 text-orange-700',
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function SummaryCard({
  label, value, sub, icon: Icon, color = 'blue',
}: {
  label: string; value: string | number; sub?: string
  icon: React.ElementType; color?: string
}) {
  const colors: Record<string, string> = {
    blue:   'bg-blue-50 text-blue-600',
    green:  'bg-emerald-50 text-emerald-600',
    purple: 'bg-purple-50 text-purple-600',
    amber:  'bg-amber-50 text-amber-600',
    red:    'bg-red-50 text-red-600',
    slate:  'bg-slate-100 text-slate-600',
  }
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-start gap-3">
      <div className={`p-2 rounded-lg ${colors[color]}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-slate-500">{label}</p>
        <p className="text-xl font-bold text-slate-800">{value}</p>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'sent') return (
    <span className="inline-flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
      <CheckCircle className="w-3 h-3" /> sent
    </span>
  )
  return (
    <span className="inline-flex items-center gap-1 text-xs text-red-700 bg-red-50 px-2 py-0.5 rounded-full">
      <AlertCircle className="w-3 h-3" /> failed
    </span>
  )
}

function ChannelBadge({ channel }: { channel: string }) {
  if (channel === 'sms') return (
    <span className="inline-flex items-center gap-1 text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full">
      <Phone className="w-3 h-3" /> SMS
    </span>
  )
  return (
    <span className="inline-flex items-center gap-1 text-xs text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full">
      <Mail className="w-3 h-3" /> Email
    </span>
  )
}

function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 w-48"
    />
  )
}

// ── Notifications Tab ─────────────────────────────────────────────────────────

function NotificationsTab({ rows }: { rows: NotifRow[] }) {
  const [search, setSearch]   = useState('')
  const [filter, setFilter]   = useState<'all' | 'sent' | 'failed'>('all')
  const [expanded, setExpanded] = useState<number | null>(null)

  const filtered = rows.filter(r => {
    if (filter === 'sent'   && r.status !== 'sent')   return false
    if (filter === 'failed' && r.status !== 'failed') return false
    if (search) {
      const q = search.toLowerCase()
      return (
        (r.recipient || '').toLowerCase().includes(q) ||
        (r.user_email || '').toLowerCase().includes(q) ||
        (r.subject || '').toLowerCase().includes(q) ||
        r.notification_type.toLowerCase().includes(q)
      )
    }
    return true
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <SearchInput value={search} onChange={setSearch} placeholder="Search email / subject…" />
        <div className="flex gap-1">
          {(['all', 'sent', 'failed'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs rounded-lg font-medium transition-colors ${
                filter === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-400 ml-auto">{filtered.length} records</span>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Type</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Channel</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Recipient</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Subject</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Plan</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Sent At</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400 text-sm">No notifications found</td></tr>
            )}
            {filtered.map((r, i) => (
              <>
                <tr
                  key={i}
                  className={`hover:bg-slate-50 cursor-pointer ${r.status === 'failed' ? 'bg-red-50/30' : ''}`}
                  onClick={() => setExpanded(expanded === i ? null : i)}
                >
                  <td className="px-4 py-3">
                    <span className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-mono">
                      {r.notification_type}
                    </span>
                  </td>
                  <td className="px-4 py-3"><ChannelBadge channel={r.channel} /></td>
                  <td className="px-4 py-3 text-slate-700 max-w-[180px] truncate">{r.recipient || r.user_email || '—'}</td>
                  <td className="px-4 py-3 text-slate-600 max-w-[200px] truncate">{r.subject || '—'}</td>
                  <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                  <td className="px-4 py-3">
                    {r.user_plan ? (
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${PLAN_PILL[r.user_plan] ?? 'bg-slate-100 text-slate-600'}`}>
                        {r.user_plan}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{fmtDate(r.sent_at)}</td>
                  <td className="px-4 py-3 text-slate-400">
                    {expanded === i ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </td>
                </tr>
                {expanded === i && (
                  <tr key={`${i}-detail`} className="bg-slate-50">
                    <td colSpan={8} className="px-6 py-3">
                      <div className="text-xs space-y-1 text-slate-600">
                        <div><span className="font-medium text-slate-700">User:</span> {r.user_name || '—'} · {r.user_email || '—'}</div>
                        <div><span className="font-medium text-slate-700">Recipient:</span> {r.recipient || '—'}</div>
                        <div><span className="font-medium text-slate-700">Attempts:</span> {r.attempt_count}</div>
                        {r.error_message && (
                          <div className="text-red-600"><span className="font-medium">Error:</span> {r.error_message}</div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Alert Triggers Tab ────────────────────────────────────────────────────────

function TriggersTab({ rows }: { rows: TriggerRow[] }) {
  const [search, setSearch] = useState('')

  const filtered = rows.filter(r => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      r.asx_code.toLowerCase().includes(q) ||
      (r.company_name || '').toLowerCase().includes(q) ||
      (r.user_email || '').toLowerCase().includes(q) ||
      r.alert_type.toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <SearchInput value={search} onChange={setSearch} placeholder="Search code / user…" />
        <span className="text-xs text-slate-400 ml-auto">{filtered.length} records</span>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Code</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Company</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Alert Type</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Threshold</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Triggered @</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Notified</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">User</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Plan</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Triggered At</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-slate-400 text-sm">No alert triggers found</td></tr>
            )}
            {filtered.map((r, i) => (
              <tr key={i} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-semibold text-blue-700">{r.asx_code}</td>
                <td className="px-4 py-3 text-slate-600 max-w-[140px] truncate">{r.company_name || '—'}</td>
                <td className="px-4 py-3">
                  <span className="text-xs bg-amber-50 text-amber-700 px-2 py-0.5 rounded">
                    {fmtAlertType(r.alert_type)}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-700">
                  {r.alert_type.includes('pct') || r.alert_type.includes('change')
                    ? `${r.threshold_value.toFixed(2)}%`
                    : `$${r.threshold_value.toFixed(2)}`
                  }
                </td>
                <td className="px-4 py-3 text-slate-700 font-medium">
                  {r.alert_type.includes('pct') || r.alert_type.includes('change')
                    ? `${r.trigger_value.toFixed(2)}%`
                    : `$${r.trigger_value.toFixed(2)}`
                  }
                </td>
                <td className="px-4 py-3">
                  {r.notification_sent
                    ? <CheckCircle className="w-4 h-4 text-emerald-500" />
                    : <XCircle className="w-4 h-4 text-slate-300" />
                  }
                </td>
                <td className="px-4 py-3 text-slate-600 text-xs max-w-[160px] truncate">
                  {r.user_name || r.user_email || '—'}
                </td>
                <td className="px-4 py-3">
                  {r.user_plan ? (
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${PLAN_PILL[r.user_plan] ?? 'bg-slate-100 text-slate-600'}`}>
                      {r.user_plan}
                    </span>
                  ) : '—'}
                </td>
                <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{fmtDate(r.triggered_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Announcements Tab ─────────────────────────────────────────────────────────

function AnnouncementsTab({ rows }: { rows: AnnouncementRow[] }) {
  const [search, setSearch]     = useState('')
  const [sensitiveOnly, setSensitiveOnly] = useState(false)

  const filtered = rows.filter(r => {
    if (sensitiveOnly && !r.market_sensitive) return false
    if (search) {
      const q = search.toLowerCase()
      return (
        r.asx_code.toLowerCase().includes(q) ||
        (r.company_name || '').toLowerCase().includes(q) ||
        r.title.toLowerCase().includes(q)
      )
    }
    return true
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <SearchInput value={search} onChange={setSearch} placeholder="Search code / title…" />
        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={sensitiveOnly}
            onChange={e => setSensitiveOnly(e.target.checked)}
            className="rounded"
          />
          Market-sensitive only
        </label>
        <span className="text-xs text-slate-400 ml-auto">{filtered.length} records</span>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Code</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Company</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Title</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Type</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Source</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Sensitive</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Notifs Sent</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Released At</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-slate-400 text-sm">No announcements found</td></tr>
            )}
            {filtered.map((r, i) => (
              <tr key={i} className={`hover:bg-slate-50 ${r.market_sensitive ? 'bg-amber-50/20' : ''}`}>
                <td className="px-4 py-3 font-semibold text-blue-700">{r.asx_code}</td>
                <td className="px-4 py-3 text-slate-600 text-xs max-w-[120px] truncate">{r.company_name || '—'}</td>
                <td className="px-4 py-3 text-slate-700 max-w-[260px]">
                  <span className="line-clamp-2 text-xs leading-relaxed">{r.title}</span>
                </td>
                <td className="px-4 py-3 text-xs text-slate-500 max-w-[120px] truncate">{r.document_type}</td>
                <td className="px-4 py-3">
                  <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                    {r.source_label}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {r.market_sensitive
                    ? <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">⚡ Sensitive</span>
                    : <span className="text-xs text-slate-400">—</span>
                  }
                </td>
                <td className="px-4 py-3">
                  {r.notif_sent_count > 0
                    ? <span className="text-xs font-semibold text-emerald-700">{r.notif_sent_count}</span>
                    : <span className="text-xs text-slate-400">0</span>
                  }
                </td>
                <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">{fmtDate(r.released_at)}</td>
                <td className="px-4 py-3">
                  {r.url && (
                    <a href={r.url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>
                      <ExternalLink className="w-3.5 h-3.5 text-slate-400 hover:text-blue-600" />
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type TabId = 'notifications' | 'triggers' | 'announcements'

export default function CommsPage() {
  const [data, setData]       = useState<CommsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [tab, setTab]         = useState<TabId>('notifications')
  const [refreshed, setRefreshed] = useState<Date | null>(null)

  const load = async () => {
    setLoading(true); setError(null)
    try {
      const { data: d } = await api.get('/api/v1/admin/comms')
      setData(d)
      setRefreshed(new Date())
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load communications data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: 'notifications', label: 'Notifications',   count: data?.notifications.length },
    { id: 'triggers',      label: 'Alert Triggers',  count: data?.triggers.length },
    { id: 'announcements', label: 'Announcements',   count: data?.announcements.length },
  ]

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Communications Centre</h1>
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

      {/* Summary cards */}
      {loading && !data ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 h-20 animate-pulse">
              <div className="w-8 h-8 bg-slate-100 rounded-lg mb-2" />
              <div className="h-3 bg-slate-100 rounded w-2/3" />
            </div>
          ))}
        </div>
      ) : data ? (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <SummaryCard label="Emails Sent Today"   value={data.summary.notifications_today}   sub={`${data.summary.notifications_7d} this week`}                  icon={Mail}      color="blue"   />
            <SummaryCard label="Emails Sent (30d)"   value={data.summary.notifications_30d}     sub="All channels"                                                   icon={Mail}      color="slate"  />
            <SummaryCard label="Failed (24h)"        value={data.summary.failed_24h}            sub={data.summary.failed_24h > 0 ? 'Needs attention' : 'All clear'} icon={XCircle}   color={data.summary.failed_24h > 0 ? 'red' : 'slate'} />
            <SummaryCard label="Alert Triggers Today" value={data.summary.alert_triggers_today} sub={`${data.summary.alert_triggers_7d} this week`}                 icon={Zap}       color="amber"  />
            <SummaryCard label="Announcements Today" value={data.summary.announcements_today}                                                                        icon={Megaphone} color="purple" />
            <SummaryCard label="Sensitive (7d)"      value={data.summary.announcements_sensitive_7d} sub="Market-sensitive filings"                                  icon={AlertCircle} color="amber" />
            {Object.entries(data.by_channel).map(([ch, cnt]) => (
              <SummaryCard key={ch} label={`Channel: ${ch.charAt(0).toUpperCase() + ch.slice(1)}`} value={cnt.toLocaleString()} sub="Last 30 days" icon={ch === 'sms' ? Phone : Mail} color="green" />
            ))}
          </div>

          {/* By-type breakdown */}
          {Object.keys(data.by_type).length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <h3 className="text-sm font-semibold text-slate-700 mb-3">Notification Types (30d)</h3>
              <div className="flex flex-wrap gap-3">
                {Object.entries(data.by_type).sort((a, b) => b[1] - a[1]).map(([type, cnt]) => (
                  <div key={type} className="flex items-center gap-2 px-3 py-2 bg-slate-50 rounded-lg border border-slate-100">
                    <span className="text-xs font-mono text-slate-600">{type}</span>
                    <span className="text-sm font-bold text-slate-800">{cnt.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tabs */}
          <div>
            <div className="flex gap-1 border-b border-slate-200 mb-4">
              {tabs.map(t => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                    tab === t.id
                      ? 'border-blue-600 text-blue-700'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {t.label}
                  {t.count !== undefined && (
                    <span className="text-xs bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded-full">
                      {t.count}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {tab === 'notifications'  && <NotificationsTab  rows={data.notifications}  />}
            {tab === 'triggers'       && <TriggersTab        rows={data.triggers}        />}
            {tab === 'announcements'  && <AnnouncementsTab   rows={data.announcements}   />}
          </div>
        </>
      ) : null}
    </div>
  )
}
