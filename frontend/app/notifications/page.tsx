'use client'
import { useEffect, useState } from 'react'
import {
  Bell, Mail, MessageSquare, TrendingUp, Newspaper,
  CheckCircle2, Loader2, AlertTriangle, History, Send,
} from 'lucide-react'
import {
  getNotificationPreferences, updateNotificationPreferences,
  getNotificationHistory, sendTestNotification,
  NotificationPreferences, NotificationHistoryItem,
} from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Toggle component ──────────────────────────────────────────────────────────

function Toggle({
  checked, onChange, disabled,
}: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors',
        'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1',
        disabled && 'opacity-40 cursor-not-allowed',
        checked ? 'bg-blue-600' : 'bg-gray-300',
      )}
    >
      <span className={cn(
        'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow',
        'translate-y-0.5 transition-transform',
        checked ? 'translate-x-4' : 'translate-x-0.5',
      )} />
    </button>
  )
}

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({ title, icon, children }: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        {icon}
        <h2 className="font-semibold text-gray-900">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function Row({ label, sub, emailVal, smsVal, onEmail, onSms, smsDisabled }: {
  label: string
  sub?: string
  emailVal: boolean
  smsVal: boolean
  onEmail: (v: boolean) => void
  onSms: (v: boolean) => void
  smsDisabled?: boolean
}) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-50 last:border-0">
      <div>
        <p className="text-sm font-medium text-gray-800">{label}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
      <div className="flex items-center gap-6">
        <div className="flex flex-col items-center gap-1">
          <span className="text-[10px] text-gray-400">Email</span>
          <Toggle checked={emailVal} onChange={onEmail} />
        </div>
        <div className="flex flex-col items-center gap-1">
          <span className="text-[10px] text-gray-400">SMS</span>
          <Toggle checked={smsVal} onChange={onSms} disabled={smsDisabled} />
        </div>
      </div>
    </div>
  )
}

// ── History item ──────────────────────────────────────────────────────────────

const TYPE_LABELS: Record<string, string> = {
  price_alert:           'Price Alert',
  portfolio_weekly:      'Weekly Summary',
  portfolio_threshold:   'Portfolio Alert',
  announcement:          'Announcement',
}

const STATUS_COLORS: Record<string, string> = {
  sent:    'text-green-600 bg-green-50',
  failed:  'text-red-600 bg-red-50',
  pending: 'text-amber-600 bg-amber-50',
}

function HistoryRow({ item }: { item: NotificationHistoryItem }) {
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0 text-sm">
      <span className={cn(
        'shrink-0 w-1.5 h-1.5 rounded-full',
        item.status === 'sent' ? 'bg-green-500' : item.status === 'failed' ? 'bg-red-400' : 'bg-amber-400',
      )} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-900">{TYPE_LABELS[item.notification_type] ?? item.notification_type}</span>
          <span className="text-xs text-gray-400">{item.channel === 'email' ? '✉' : '💬'}</span>
          {item.subject && (
            <span className="text-xs text-gray-500 truncate">{item.subject}</span>
          )}
        </div>
        {item.error_message && (
          <p className="text-xs text-red-500 mt-0.5">{item.error_message}</p>
        )}
      </div>
      <div className="shrink-0 text-right">
        <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize', STATUS_COLORS[item.status] ?? STATUS_COLORS.pending)}>
          {item.status}
        </span>
        <p className="text-[10px] text-gray-400 mt-1">
          {item.sent_at
            ? new Date(item.sent_at).toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
            : new Date(item.created_at).toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
          }
        </p>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function NotificationsPage() {
  const [prefs, setPrefs]         = useState<NotificationPreferences | null>(null)
  const [history, setHistory]     = useState<NotificationHistoryItem[]>([])
  const [histTotal, setHistTotal] = useState(0)
  const [loading, setLoading]     = useState(true)
  const [saving, setSaving]       = useState(false)
  const [saved, setSaved]         = useState(false)
  const [error, setError]         = useState<string | null>(null)
  const [testLoading, setTestLoading] = useState<'email' | 'sms' | null>(null)
  const [testResult, setTestResult]   = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      getNotificationPreferences(),
      getNotificationHistory({ limit: 20 }),
    ]).then(([p, h]) => {
      setPrefs(p)
      setHistory(h.items)
      setHistTotal(h.total)
    }).catch(e => {
      setError(e?.response?.data?.detail ?? 'Failed to load preferences')
    }).finally(() => setLoading(false))
  }, [])

  function update(patch: Partial<NotificationPreferences>) {
    setPrefs(p => p ? { ...p, ...patch } : p)
    setSaved(false)
  }

  async function save() {
    if (!prefs) return
    setSaving(true)
    setError(null)
    try {
      await updateNotificationPreferences(prefs)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function sendTest(channel: 'email' | 'sms') {
    setTestLoading(channel)
    setTestResult(null)
    try {
      const res = await sendTestNotification(channel)
      setTestResult(res.ok
        ? `Test ${channel} sent to ${res.recipient} ✓`
        : `${channel} not configured (no-op)`
      )
    } catch (e: any) {
      setTestResult(e?.response?.data?.detail ?? `${channel} test failed`)
    } finally {
      setTestLoading(null)
    }
  }

  const smsDisabled = !prefs?.phone_number

  if (loading) {
    return (
      <div className="max-w-2xl space-y-4">
        {[1, 2, 3].map(i => <div key={i} className="h-40 bg-gray-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }

  if (!prefs) {
    return (
      <div className="text-center py-20 text-gray-500">
        <Bell className="w-10 h-10 text-gray-200 mx-auto mb-3" />
        <p>Failed to load notification preferences.</p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <Bell className="w-5 h-5" />
          Notification Preferences
        </h1>
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle2 className="w-4 h-4" /> : null}
          {saved ? 'Saved!' : saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Contact info */}
      <Section title="Contact Details" icon={<MessageSquare className="w-4 h-4 text-gray-500" />}>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Phone number <span className="text-gray-400 font-normal">(for SMS notifications)</span>
            </label>
            <div className="flex gap-2">
              <input
                type="tel"
                value={prefs.phone_number ?? ''}
                onChange={e => update({ phone_number: e.target.value || null })}
                placeholder="+61 4XX XXX XXX"
                className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Include country code. Australian numbers: +61 4XX XXX XXX
            </p>
          </div>

          {/* Test buttons */}
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              onClick={() => sendTest('email')}
              disabled={testLoading !== null}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              {testLoading === 'email' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              Send test email
            </button>
            <button
              onClick={() => sendTest('sms')}
              disabled={testLoading !== null || !prefs.phone_number}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              {testLoading === 'sms' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              Send test SMS
            </button>
          </div>
          {testResult && (
            <p className="text-xs text-gray-600 bg-gray-50 rounded-lg px-3 py-2">{testResult}</p>
          )}
        </div>
      </Section>

      {/* Portfolio notifications */}
      <Section title="Portfolio Notifications" icon={<TrendingUp className="w-4 h-4 text-blue-500" />}>
        <Row
          label="Weekly portfolio summary"
          sub="Every Monday morning — value, P&L, top movers"
          emailVal={prefs.portfolio_weekly_email}
          smsVal={false}
          onEmail={v => update({ portfolio_weekly_email: v })}
          onSms={() => {}}
          smsDisabled
        />
        <Row
          label="Significant portfolio movement"
          sub={`Alert when portfolio changes by more than ${prefs.portfolio_threshold_pct}%`}
          emailVal={prefs.portfolio_threshold_email}
          smsVal={prefs.portfolio_threshold_sms}
          onEmail={v => update({ portfolio_threshold_email: v })}
          onSms={v => update({ portfolio_threshold_sms: v })}
          smsDisabled={smsDisabled}
        />
        <div className="pt-3">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Movement threshold (%)
          </label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={1}
              max={20}
              step={0.5}
              value={prefs.portfolio_threshold_pct}
              onChange={e => update({ portfolio_threshold_pct: parseFloat(e.target.value) })}
              className="flex-1"
            />
            <span className="w-12 text-sm font-semibold text-gray-900 text-right">
              {prefs.portfolio_threshold_pct}%
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Notify when total portfolio value moves more than this % since last notification (min 4h cooldown).
          </p>
        </div>
      </Section>

      {/* Alert notifications */}
      <Section title="Price Alert Notifications" icon={<Bell className="w-4 h-4 text-amber-500" />}>
        <Row
          label="Price & percentage alerts"
          sub="Triggered when your saved alerts fire"
          emailVal={prefs.alerts_email}
          smsVal={prefs.alerts_sms}
          onEmail={v => update({ alerts_email: v })}
          onSms={v => update({ alerts_sms: v })}
          smsDisabled={smsDisabled}
        />
        <p className="text-xs text-gray-400 mt-3">
          Configure individual alerts on the <a href="/alerts" className="text-blue-600 hover:underline">Alerts</a> page.
        </p>
      </Section>

      {/* Announcement notifications */}
      <Section title="ASX Announcement Notifications" icon={<Newspaper className="w-4 h-4 text-purple-500" />}>
        <Row
          label="Market-sensitive announcements"
          sub="For stocks in your watchlists — earnings, dividends, trading halts"
          emailVal={prefs.announcements_email}
          smsVal={prefs.announcements_sms}
          onEmail={v => update({ announcements_email: v })}
          onSms={v => update({ announcements_sms: v })}
          smsDisabled={smsDisabled}
        />
        <p className="text-xs text-gray-400 mt-3">
          Only market-sensitive filings for stocks in your <a href="/watchlist" className="text-blue-600 hover:underline">watchlists</a>.
        </p>
      </Section>

      {/* Weekly report timing */}
      <Section title="Weekly Report Timing" icon={<Mail className="w-4 h-4 text-gray-500" />}>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Day</label>
            <select
              value={prefs.weekly_report_day}
              onChange={e => update({ weekly_report_day: parseInt(e.target.value) })}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((d, i) => (
                <option key={i} value={i + 1}>{d}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Hour (AEST)</label>
            <select
              value={prefs.weekly_report_hour}
              onChange={e => update({ weekly_report_hour: parseInt(e.target.value) })}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>
                  {i === 0 ? '12:00 AM' : i < 12 ? `${i}:00 AM` : i === 12 ? '12:00 PM' : `${i - 12}:00 PM`}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Section>

      {/* Notification history */}
      <Section title={`Notification History (${histTotal})`} icon={<History className="w-4 h-4 text-gray-500" />}>
        {history.length === 0 ? (
          <p className="text-sm text-gray-400 py-4 text-center">No notifications sent yet.</p>
        ) : (
          <div>
            {history.map(item => <HistoryRow key={item.id} item={item} />)}
            {histTotal > 20 && (
              <p className="text-xs text-gray-400 text-center pt-3">
                Showing 20 of {histTotal} notifications
              </p>
            )}
          </div>
        )}
      </Section>

      {/* Save button (bottom) */}
      <div className="flex justify-end pb-4">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle2 className="w-4 h-4" /> : null}
          {saved ? 'Saved!' : saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  )
}
