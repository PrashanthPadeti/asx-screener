'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Bell, Plus, Trash2, ToggleLeft, ToggleRight, LogIn, Loader2 } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Types ─────────────────────────────────────────────────────

interface Alert {
  id:               string
  asx_code:         string
  alert_type:       string
  threshold_value:  number
  via_email:        boolean
  is_active:        boolean
  repeat_mode:      string
  trigger_count:    number
  last_triggered_at: string | null
  created_at:       string | null
}

const ALERT_TYPE_LABELS: Record<string, string> = {
  price_above:      'Price rises above',
  price_below:      'Price falls below',
  pct_change_above: '1W change above',
  pct_change_below: '1W change below',
}

const ALERT_TYPE_UNIT: Record<string, string> = {
  price_above:      '$',
  price_below:      '$',
  pct_change_above: '%',
  pct_change_below: '%',
}

// ── Create alert form ─────────────────────────────────────────

function CreateAlertForm({ onCreated }: { onCreated: (a: Alert) => void }) {
  const [code,       setCode]       = useState('')
  const [alertType,  setAlertType]  = useState('price_above')
  const [threshold,  setThreshold]  = useState('')
  const [viaEmail,   setViaEmail]   = useState(true)
  const [repeatMode, setRepeatMode] = useState('every_time')
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!code.trim() || !threshold) return
    setLoading(true); setError(null)
    try {
      const { data } = await api.post('/api/v1/alerts', {
        asx_code:        code.toUpperCase().trim(),
        alert_type:      alertType,
        threshold_value: parseFloat(threshold),
        via_email:       viaEmail,
        repeat_mode:     repeatMode,
      })
      onCreated(data)
      setCode(''); setThreshold('')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Failed to create alert')
    } finally { setLoading(false) }
  }

  const unit = ALERT_TYPE_UNIT[alertType] || '$'

  return (
    <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
      <h3 className="font-semibold text-gray-900">New Alert</h3>

      {error && (
        <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* Code */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">ASX Code</label>
          <input
            value={code} onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="e.g. CBA" required maxLength={10}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono uppercase
                       focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Type */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Condition</label>
          <select value={alertType} onChange={e => setAlertType(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            {Object.entries(ALERT_TYPE_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>

        {/* Threshold */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Threshold ({unit})
          </label>
          <input
            type="number" step="0.001" value={threshold}
            onChange={e => setThreshold(e.target.value)}
            placeholder={unit === '$' ? '0.00' : '5.0'} required
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Repeat */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Repeat</label>
          <select value={repeatMode} onChange={e => setRepeatMode(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            <option value="every_time">Every time</option>
            <option value="once">Once only</option>
            <option value="daily_max">Max once/day</option>
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
          <input type="checkbox" checked={viaEmail} onChange={e => setViaEmail(e.target.checked)}
            className="rounded border-gray-300 text-blue-600" />
          Email notification
        </label>
        <button type="submit" disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400
                     text-white text-sm font-medium rounded-lg transition-colors">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Create Alert
        </button>
      </div>
    </form>
  )
}

// ── Alert row ─────────────────────────────────────────────────

function AlertRow({ alert, onToggle, onDelete }: {
  alert: Alert
  onToggle: (id: string) => void
  onDelete: (id: string) => void
}) {
  const unit = ALERT_TYPE_UNIT[alert.alert_type] || '$'
  const label = ALERT_TYPE_LABELS[alert.alert_type] || alert.alert_type

  return (
    <tr className={cn('border-b border-gray-50 transition-colors', !alert.is_active && 'opacity-50')}>
      <td className="px-4 py-3">
        <Link href={`/company/${alert.asx_code}`}
          className="font-mono font-bold text-blue-600 hover:underline text-sm">
          {alert.asx_code}
        </Link>
      </td>
      <td className="px-4 py-3 text-sm text-gray-700">{label}</td>
      <td className="px-4 py-3 text-sm font-medium text-gray-900">
        {unit}{alert.threshold_value.toFixed(unit === '%' ? 1 : 3)}
      </td>
      <td className="px-4 py-3">
        <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium',
          alert.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500')}>
          {alert.is_active ? 'Active' : 'Paused'}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">{alert.trigger_count}×</td>
      <td className="px-4 py-3 text-xs text-gray-400">
        {alert.last_triggered_at
          ? new Date(alert.last_triggered_at).toLocaleDateString('en-AU')
          : '—'}
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-2">
          <button onClick={() => onToggle(alert.id)} title={alert.is_active ? 'Pause' : 'Activate'}
            className="text-gray-400 hover:text-blue-500 transition-colors">
            {alert.is_active
              ? <ToggleRight className="w-5 h-5 text-blue-500" />
              : <ToggleLeft className="w-5 h-5" />}
          </button>
          <button onClick={() => onDelete(alert.id)} title="Delete alert"
            className="text-gray-300 hover:text-red-400 transition-colors">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Main page ─────────────────────────────────────────────────

export default function AlertsPage() {
  const { user, loading: authLoading } = useAuth()
  const [alerts,  setAlerts]  = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!user) { setLoading(false); return }
    api.get('/api/v1/alerts')
      .then(r => setAlerts(r.data.alerts))
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false))
  }, [user])

  const handleToggle = async (id: string) => {
    try {
      const { data } = await api.patch(`/api/v1/alerts/${id}`)
      setAlerts(prev => prev.map(a => a.id === id ? data : a))
    } catch { /* ignore */ }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this alert?')) return
    try {
      await api.delete(`/api/v1/alerts/${id}`)
      setAlerts(prev => prev.filter(a => a.id !== id))
    } catch { /* ignore */ }
  }

  if (authLoading || loading) {
    return (
      <div className="space-y-4 max-w-4xl">
        {[1,2,3].map(i => <div key={i} className="h-12 bg-gray-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }

  if (!user) {
    return (
      <div className="max-w-lg mx-auto text-center py-20">
        <Bell className="w-12 h-12 text-gray-200 mx-auto mb-4" />
        <h1 className="text-xl font-bold text-gray-900 mb-2">Price Alerts</h1>
        <p className="text-gray-500 mb-6">Sign in to set price alerts and get email notifications.</p>
        <Link href="/auth/login"
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700">
          <LogIn className="w-4 h-4" />
          Sign in
        </Link>
      </div>
    )
  }

  const activeCount = alerts.filter(a => a.is_active).length
  const freeLimit   = user.plan === 'free' ? 3 : 50

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Bell className="w-5 h-5 text-blue-600" />
            Price Alerts
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {activeCount} of {freeLimit} active alerts used
            {user.plan === 'free' && activeCount >= freeLimit && (
              <Link href="/account" className="ml-2 text-blue-600 hover:underline font-medium">
                Upgrade for more →
              </Link>
            )}
          </p>
        </div>
      </div>

      {/* Create form */}
      <CreateAlertForm onCreated={a => setAlerts(prev => [a, ...prev])} />

      {/* Alerts table */}
      {alerts.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white border border-gray-200 rounded-xl">
          <Bell className="w-8 h-8 mx-auto mb-3 text-gray-200" />
          <p className="text-sm">No alerts yet. Create one above.</p>
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
                <AlertRow key={a.id} alert={a} onToggle={handleToggle} onDelete={handleDelete} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-gray-400">
        Alerts are checked every 15 minutes against the latest price data.
        Email notifications sent to <strong>{user.email}</strong>.
      </p>
    </div>
  )
}
