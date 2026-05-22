'use client'
import { useState, useEffect, useRef, useCallback } from 'react'
import Link from 'next/link'
import {
  Bell, Plus, Trash2, ToggleLeft, ToggleRight, LogIn, Loader2,
  Pencil, X, History, ChevronDown,
} from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { HelpDrawer } from '@/components/HelpDrawer'
import { ALERTS_SECTIONS } from '@/lib/helpContent'

// ── Types ──────────────────────────────────────────────────────────────────────

interface Alert {
  id:                string
  asx_code:          string
  company_name:      string | null
  alert_type:        string
  threshold_value:   number
  via_email:         boolean
  is_active:         boolean
  repeat_mode:       string
  trigger_count:     number
  last_triggered_at: string | null
  created_at:        string | null
}

interface AlertHistory {
  alert_id:          string
  asx_code:          string
  company_name:      string | null
  alert_type:        string
  threshold_value:   number
  triggered_value:   number
  triggered_at:      string
  notification_sent: boolean
}

interface Suggestion {
  asx_code:     string
  company_name: string | null
}

// ── Alert type definitions ─────────────────────────────────────────────────────

interface AlertTypeDef {
  value:          string
  label:          string
  unit:           string    // '$' | '%' | '' (no unit)
  minPlan:        string    // 'free' | 'pro' | 'premium'
  hasThreshold:   boolean
  autoThreshold?: number   // auto-set for no-threshold types
  comingSoon?:    boolean
}

const ALERT_TYPES: AlertTypeDef[] = [
  // Basic price — Free
  { value: 'price_above',    label: 'Price rises above',              unit: '$',  minPlan: 'free',    hasThreshold: true  },
  { value: 'price_below',    label: 'Price falls below',              unit: '$',  minPlan: 'free',    hasThreshold: true  },
  // % change — Free
  { value: 'pct_1d_above',   label: '1-day move above %',             unit: '%',  minPlan: 'free',    hasThreshold: true  },
  { value: 'pct_1w_above',   label: '1-week move above %',            unit: '%',  minPlan: 'free',    hasThreshold: true  },
  // Fundamental — Pro+
  { value: 'div_yield_above',label: 'Dividend yield above %',         unit: '%',  minPlan: 'pro',     hasThreshold: true  },
  { value: 'pe_below',       label: 'P/E falls below',                unit: '',   minPlan: 'pro',     hasThreshold: true  },
  // Technical — Pro+
  { value: 'rsi_below_30',   label: 'RSI falls below 30',             unit: '',   minPlan: 'pro',     hasThreshold: false, autoThreshold: 30 },
  { value: 'rsi_above_70',   label: 'RSI rises above 70',             unit: '',   minPlan: 'pro',     hasThreshold: false, autoThreshold: 70 },
  // Event — Pro+
  { value: 'announcement',   label: 'Market-sensitive announcement',  unit: '',   minPlan: 'pro',     hasThreshold: false, autoThreshold: 0, comingSoon: true },
  { value: 'watchlist_news', label: 'Watchlist news',                 unit: '',   minPlan: 'pro',     hasThreshold: false, autoThreshold: 0, comingSoon: true },
  // AI/Screener — Premium+
  { value: 'screener_match', label: 'Screener result match',          unit: '',   minPlan: 'premium', hasThreshold: false, autoThreshold: 0, comingSoon: true },
]

const ALERT_TYPE_MAP = Object.fromEntries(ALERT_TYPES.map(t => [t.value, t]))

// Legacy label fallback for older alert types stored in DB
const LEGACY_LABELS: Record<string, string> = {
  pct_change_above: '1W change above %',
  pct_change_below: '1W change below %',
}

// ── Plan config ────────────────────────────────────────────────────────────────

const PLAN_RANK: Record<string, number> = {
  free: 0, pro: 1, premium: 2, enterprise_pro: 1, enterprise_premium: 2,
}

const ALERT_LIMITS: Record<string, number> = {
  free: 3, pro: 50, premium: 100, enterprise_pro: 50, enterprise_premium: 100,
}

const PLAN_LABELS: Record<string, string> = {
  free:               'Free Plan',
  pro:                'Pro Plan',
  premium:            'Premium Plan',
  enterprise_pro:     'Enterprise Pro Plan',
  enterprise_premium: 'Enterprise Premium Plan',
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function getAlertLabel(alertType: string): string {
  return ALERT_TYPE_MAP[alertType]?.label ?? LEGACY_LABELS[alertType] ?? alertType
}

/** Format a threshold or triggered value with the right unit and decimal places */
function fmtValue(value: number, alertType: string): string {
  const def  = ALERT_TYPE_MAP[alertType]
  const unit = def?.unit ?? (alertType.includes('pct') || alertType.includes('change') ? '%' : '$')
  if (unit === '%') return `${value.toFixed(2)}%`
  if (unit === '')  return value.toFixed(2)
  // Price — smart decimal places
  const dec = value >= 1 ? 2 : value >= 0.1 ? 3 : 4
  return `$${value.toFixed(dec)}`
}

function fmtDateShort(s: string | null): string {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' })
}

function fmtDateTime(s: string | null): string {
  if (!s) return '—'
  return new Date(s).toLocaleString('en-AU', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── ASX Code Autocomplete ──────────────────────────────────────────────────────

function CodeAutocomplete({
  value,
  onChange,
  disabled = false,
}: {
  value:    string
  onChange: (code: string) => void
  disabled?: boolean
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [open,        setOpen]        = useState(false)
  const [fetching,    setFetching]    = useState(false)
  const debounceRef                   = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef                  = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node))
        setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const fetchSuggestions = useCallback((q: string) => {
    if (q.length < 1) { setSuggestions([]); setOpen(false); return }
    setFetching(true)
    api.get(`/api/v1/alerts/search?q=${encodeURIComponent(q)}`)
      .then(r => { setSuggestions(r.data.results ?? []); setOpen(true) })
      .catch(() => setSuggestions([]))
      .finally(() => setFetching(false))
  }, [])

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value.toUpperCase()
    onChange(v)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => fetchSuggestions(v), 200)
  }

  const handleSelect = (s: Suggestion) => {
    onChange(s.asx_code)
    setOpen(false)
    setSuggestions([])
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        value={value}
        onChange={handleInput}
        placeholder="e.g. CBA"
        required
        maxLength={10}
        disabled={disabled}
        autoComplete="off"
        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono
                   focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
      />
      {fetching && (
        <Loader2 className="absolute right-2.5 top-2.5 w-4 h-4 animate-spin text-gray-400 pointer-events-none" />
      )}
      {open && suggestions.length > 0 && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden">
          {suggestions.map(s => (
            <button
              key={s.asx_code}
              type="button"
              onMouseDown={() => handleSelect(s)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 flex items-center gap-2 border-b border-gray-50 last:border-0"
            >
              <span className="font-mono font-bold text-blue-600 w-12 shrink-0">{s.asx_code}</span>
              <span className="text-gray-500 truncate text-xs">{s.company_name ?? ''}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Shared Alert Form (create + edit) ──────────────────────────────────────────

interface FormData {
  asx_code:        string
  alert_type:      string
  threshold_value: number
  via_email:       boolean
  repeat_mode:     string
}

function AlertForm({
  initial,
  plan,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  initial?:    Partial<Alert>
  plan:        string
  onSubmit:    (data: FormData) => Promise<void>
  onCancel?:   () => void
  submitLabel: string
}) {
  const [code,       setCode]       = useState(initial?.asx_code      ?? '')
  const [alertType,  setAlertType]  = useState(initial?.alert_type    ?? 'price_above')
  const [threshold,  setThreshold]  = useState(initial?.threshold_value != null ? String(initial.threshold_value) : '')
  const [viaEmail,   setViaEmail]   = useState(initial?.via_email     ?? true)
  const [repeatMode, setRepeatMode] = useState(initial?.repeat_mode   ?? 'every_time')
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState<string | null>(null)

  const userRank    = PLAN_RANK[plan] ?? 0
  const typeDef     = ALERT_TYPE_MAP[alertType]
  const needsThresh = typeDef?.hasThreshold ?? true

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!code.trim()) return
    setLoading(true); setError(null)
    const threshVal = needsThresh
      ? (parseFloat(threshold) || 0)
      : (typeDef?.autoThreshold ?? 0)
    try {
      await onSubmit({
        asx_code:        code.toUpperCase().trim(),
        alert_type:      alertType,
        threshold_value: threshVal,
        via_email:       viaEmail,
        repeat_mode:     repeatMode,
      })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to save alert')
    } finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* ASX Code */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">ASX Code</label>
          <CodeAutocomplete value={code} onChange={setCode} />
        </div>

        {/* Condition */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Condition</label>
          <select
            value={alertType}
            onChange={e => setAlertType(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {ALERT_TYPES.map(t => {
              const isLocked  = PLAN_RANK[t.minPlan] > userRank
              const isCurrent = t.value === alertType
              return (
                <option key={t.value} value={t.value} disabled={isLocked && !isCurrent}>
                  {isLocked && !isCurrent ? '🔒 ' : ''}{t.label}
                  {t.comingSoon ? ' (soon)' : ''}
                  {isLocked && !isCurrent ? ` — ${t.minPlan === 'pro' ? 'Pro' : 'Premium'}+` : ''}
                </option>
              )
            })}
          </select>
        </div>

        {/* Threshold */}
        {needsThresh && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Threshold{typeDef?.unit ? ` (${typeDef.unit})` : ''}
            </label>
            <input
              type="number"
              step="any"
              value={threshold}
              onChange={e => setThreshold(e.target.value)}
              placeholder={typeDef?.unit === '$' ? '0.00' : typeDef?.unit === '%' ? '5.0' : '15'}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        )}

        {/* Repeat */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Repeat</label>
          <select
            value={repeatMode}
            onChange={e => setRepeatMode(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="every_time">Every time</option>
            <option value="once">Once only</option>
            <option value="daily_max">Max once/day</option>
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between pt-1">
        <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
          <input
            type="checkbox"
            checked={viaEmail}
            onChange={e => setViaEmail(e.target.checked)}
            className="rounded border-gray-300 text-blue-600"
          />
          Email notification
        </label>
        <div className="flex gap-2">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 border border-gray-300 text-gray-600 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
          )}
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400
                       text-white text-sm font-medium rounded-lg transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            {submitLabel}
          </button>
        </div>
      </div>
    </form>
  )
}

// ── Edit Alert Modal ───────────────────────────────────────────────────────────

function EditAlertModal({
  alert,
  plan,
  onSave,
  onClose,
}: {
  alert:   Alert
  plan:    string
  onSave:  (updated: Alert) => void
  onClose: () => void
}) {
  const handleSubmit = async (data: FormData) => {
    const { data: updated } = await api.put(`/api/v1/alerts/${alert.id}`, data)
    onSave(updated)
    onClose()
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">Edit Alert</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        <AlertForm
          initial={alert}
          plan={plan}
          onSubmit={handleSubmit}
          onCancel={onClose}
          submitLabel="Save Changes"
        />
      </div>
    </div>
  )
}

// ── Alert Row ──────────────────────────────────────────────────────────────────

function AlertRow({
  alert,
  onToggle,
  onDelete,
  onEdit,
}: {
  alert:    Alert
  onToggle: (id: string) => void
  onDelete: (id: string) => void
  onEdit:   (alert: Alert) => void
}) {
  return (
    <tr className={cn(
      'border-b border-gray-50 transition-colors hover:bg-gray-50/50',
      !alert.is_active && 'opacity-50',
    )}>
      <td className="px-4 py-3">
        <Link href={`/company/${alert.asx_code}`}
          className="font-mono font-bold text-blue-600 hover:underline text-sm">
          {alert.asx_code}
        </Link>
        {alert.company_name && (
          <p className="text-xs text-gray-400 mt-0.5 max-w-[130px] truncate">{alert.company_name}</p>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-gray-700">{getAlertLabel(alert.alert_type)}</td>
      <td className="px-4 py-3 text-sm font-medium text-gray-900 font-mono tabular-nums">
        {ALERT_TYPE_MAP[alert.alert_type]?.hasThreshold === false
          ? '—'
          : fmtValue(alert.threshold_value, alert.alert_type)}
      </td>
      <td className="px-4 py-3">
        <span className={cn(
          'text-xs px-2 py-0.5 rounded-full font-medium',
          alert.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500',
        )}>
          {alert.is_active ? 'Active' : 'Paused'}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 tabular-nums">{alert.trigger_count}×</td>
      <td className="px-4 py-3 text-xs text-gray-400">{fmtDateShort(alert.last_triggered_at)}</td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-0.5">
          <button
            onClick={() => onEdit(alert)}
            title="Edit alert"
            className="p-1.5 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded transition-colors"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onToggle(alert.id)}
            title={alert.is_active ? 'Pause alert' : 'Resume alert'}
            className="p-1.5 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded transition-colors"
          >
            {alert.is_active
              ? <ToggleRight className="w-5 h-5 text-blue-500" />
              : <ToggleLeft  className="w-5 h-5" />}
          </button>
          <button
            onClick={() => onDelete(alert.id)}
            title="Delete alert"
            className="p-1.5 text-gray-300 hover:text-red-400 hover:bg-red-50 rounded transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Triggered History Table ────────────────────────────────────────────────────

function HistoryTable({
  history,
  loading,
}: {
  history: AlertHistory[]
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-12 bg-gray-100 rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  if (history.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400 bg-white border border-gray-200 rounded-xl">
        <History className="w-8 h-8 mx-auto mb-3 text-gray-200" />
        <p className="text-sm font-medium">No alerts triggered yet</p>
        <p className="text-xs mt-1">When an alert fires, it will appear here.</p>
      </div>
    )
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
            <th className="px-4 py-2.5 text-left">Code</th>
            <th className="px-4 py-2.5 text-left">Condition</th>
            <th className="px-4 py-2.5 text-left">Trigger Price</th>
            <th className="px-4 py-2.5 text-left">Triggered At</th>
            <th className="px-4 py-2.5 text-left">Email Sent</th>
          </tr>
        </thead>
        <tbody>
          {history.map((h, i) => (
            <tr
              key={`${h.alert_id}-${h.triggered_at}-${i}`}
              className="border-b border-gray-50 hover:bg-gray-50/50"
            >
              <td className="px-4 py-3">
                <Link href={`/company/${h.asx_code}`}
                  className="font-mono font-bold text-blue-600 hover:underline text-sm">
                  {h.asx_code}
                </Link>
                {h.company_name && (
                  <p className="text-xs text-gray-400 mt-0.5 max-w-[130px] truncate">{h.company_name}</p>
                )}
              </td>
              <td className="px-4 py-3 text-sm text-gray-700">{getAlertLabel(h.alert_type)}</td>
              <td className="px-4 py-3 text-sm font-medium text-gray-900 font-mono tabular-nums">
                {fmtValue(h.triggered_value, h.alert_type)}
              </td>
              <td className="px-4 py-3 text-xs text-gray-500">{fmtDateTime(h.triggered_at)}</td>
              <td className="px-4 py-3">
                <span className={cn(
                  'text-xs px-2 py-0.5 rounded-full font-medium',
                  h.notification_sent ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400',
                )}>
                  {h.notification_sent ? 'Sent' : 'Pending'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const { user, loading: authLoading } = useAuth()

  const [alerts,      setAlerts]      = useState<Alert[]>([])
  const [history,     setHistory]     = useState<AlertHistory[]>([])
  const [loading,     setLoading]     = useState(true)
  const [histLoading, setHistLoading] = useState(false)
  const [activeTab,   setActiveTab]   = useState<'alerts' | 'history'>('alerts')
  const [showForm,    setShowForm]    = useState(true)
  const [editAlert,   setEditAlert]   = useState<Alert | null>(null)

  // Load active alerts
  useEffect(() => {
    if (!user) { setLoading(false); return }
    api.get('/api/v1/alerts')
      .then(r => setAlerts(r.data.alerts ?? []))
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false))
  }, [user])

  // Load history lazily when tab is first opened
  useEffect(() => {
    if (activeTab !== 'history' || !user || history.length > 0) return
    setHistLoading(true)
    api.get('/api/v1/alerts/history')
      .then(r => setHistory(r.data.history ?? []))
      .catch(() => setHistory([]))
      .finally(() => setHistLoading(false))
  }, [activeTab, user, history.length])

  const handleCreate = async (data: FormData) => {
    const { data: created } = await api.post('/api/v1/alerts', data)
    setAlerts(prev => [created, ...prev])
  }

  const handleToggle = async (id: string) => {
    try {
      const { data } = await api.patch(`/api/v1/alerts/${id}`)
      setAlerts(prev => prev.map(a => a.id === id ? data : a))
    } catch { /* ignore */ }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this alert?')) return
    try {
      await api.delete(`/api/v1/alerts/${id}`)
      setAlerts(prev => prev.filter(a => a.id !== id))
    } catch { /* ignore */ }
  }

  const handleSaveEdit = (updated: Alert) => {
    setAlerts(prev => prev.map(a => a.id === updated.id ? updated : a))
  }

  // ── Loading skeleton ───────────────────────────────────────────────────────

  if (authLoading || loading) {
    return (
      <div className="space-y-4 max-w-4xl">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-12 bg-gray-100 rounded-xl animate-pulse" />
        ))}
      </div>
    )
  }

  // ── Not logged in ──────────────────────────────────────────────────────────

  if (!user) {
    return (
      <div className="max-w-lg mx-auto text-center py-20">
        <Bell className="w-12 h-12 text-gray-200 mx-auto mb-4" />
        <h1 className="text-xl font-bold text-gray-900 mb-2">Price Alerts</h1>
        <p className="text-gray-500 mb-6">Sign in to set price alerts and get email notifications.</p>
        <Link
          href="/auth/login"
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700"
        >
          <LogIn className="w-4 h-4" />
          Sign in
        </Link>
      </div>
    )
  }

  const plan        = user.plan ?? 'free'
  const alertLimit  = ALERT_LIMITS[plan] ?? 3
  const planLabel   = PLAN_LABELS[plan]  ?? 'Free Plan'
  const activeCount = alerts.filter(a => a.is_active).length
  const atLimit     = activeCount >= alertLimit

  // ── Page ───────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-4xl">

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Bell className="w-5 h-5 text-blue-600" />
            Price Alerts
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {planLabel} · {activeCount} of {alertLimit} active alerts used
            {atLimit && (plan === 'free' || plan === 'pro') && (
              <Link href="/pricing" className="ml-2 text-blue-600 hover:underline font-medium text-xs">
                Upgrade for more →
              </Link>
            )}
          </p>
        </div>
        <HelpDrawer
          sections={ALERTS_SECTIONS}
          title="Alerts Guide"
          subtitle="Conditions, repeat modes, and limits explained"
        />
      </div>

      {/* ── Tab bar ─────────────────────────────────────────────── */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        <button
          onClick={() => setActiveTab('alerts')}
          className={cn(
            'px-4 py-1.5 text-sm font-medium rounded-md transition-colors',
            activeTab === 'alerts'
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-700',
          )}
        >
          Active Alerts ({alerts.length})
        </button>
        <button
          onClick={() => setActiveTab('history')}
          className={cn(
            'px-4 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1.5',
            activeTab === 'history'
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-700',
          )}
        >
          <History className="w-3.5 h-3.5" />
          Triggered History
        </button>
      </div>

      {/* ══════════════════════════════════════════════════════════ */}
      {/* Active Alerts tab                                         */}
      {/* ══════════════════════════════════════════════════════════ */}
      {activeTab === 'alerts' && (
        <>
          {/* Create form (collapsible) */}
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => setShowForm(f => !f)}
              className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition-colors"
            >
              <span className="font-semibold text-gray-900 flex items-center gap-2">
                <Plus className="w-4 h-4 text-blue-600" />
                New Alert
              </span>
              <ChevronDown className={cn(
                'w-4 h-4 text-gray-400 transition-transform duration-200',
                showForm && 'rotate-180',
              )} />
            </button>

            {showForm && (
              <div className="px-5 pb-5 border-t border-gray-100">
                {atLimit ? (
                  <div className="py-5 text-center text-sm text-gray-500">
                    You&apos;ve reached your limit of {alertLimit} active alerts.
                    {(plan === 'free' || plan === 'pro') && (
                      <> <Link href="/pricing" className="text-blue-600 hover:underline font-medium">
                        Upgrade your plan
                      </Link> to add more.</>
                    )}
                  </div>
                ) : (
                  <div className="pt-4">
                    <AlertForm
                      plan={plan}
                      onSubmit={handleCreate}
                      submitLabel="Create Alert"
                    />
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Alerts table */}
          {alerts.length === 0 ? (
            <div className="text-center py-14 text-gray-400 bg-white border border-gray-200 rounded-xl">
              <Bell className="w-8 h-8 mx-auto mb-3 text-gray-200" />
              <p className="text-sm font-medium">No alerts yet</p>
              <p className="text-xs mt-1">Create one above to get started.</p>
            </div>
          ) : (
            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                    <th className="px-4 py-2.5 text-left">Code</th>
                    <th className="px-4 py-2.5 text-left">Condition</th>
                    <th className="px-4 py-2.5 text-left">Threshold</th>
                    <th className="px-4 py-2.5 text-left">Status</th>
                    <th className="px-4 py-2.5 text-left">Fired</th>
                    <th className="px-4 py-2.5 text-left">Last triggered</th>
                    <th className="px-4 py-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map(a => (
                    <AlertRow
                      key={a.id}
                      alert={a}
                      onToggle={handleToggle}
                      onDelete={handleDelete}
                      onEdit={setEditAlert}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Footer */}
          <p className="text-xs text-gray-400">
            Alerts are checked after each data refresh. Price alerts use the latest available ASX price data.{' '}
            Email notifications sent to <strong>{user.email}</strong>.
          </p>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════ */}
      {/* Triggered History tab                                     */}
      {/* ══════════════════════════════════════════════════════════ */}
      {activeTab === 'history' && (
        <HistoryTable history={history} loading={histLoading} />
      )}

      {/* ── Edit modal ──────────────────────────────────────────── */}
      {editAlert && (
        <EditAlertModal
          alert={editAlert}
          plan={plan}
          onSave={handleSaveEdit}
          onClose={() => setEditAlert(null)}
        />
      )}
    </div>
  )
}
