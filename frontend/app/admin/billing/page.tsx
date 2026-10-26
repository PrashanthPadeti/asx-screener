'use client'

/**
 * Admin → Paying Customers
 *
 * Reads the application database AND Stripe, and shows where they disagree.
 *
 * The reason is a specific incident: on 26 Oct 2026 a Premium subscriber had
 * turned off auto-renewal, with his subscription ending 22 November. Every
 * local record read `active` with no end date, because Stripe does not fire
 * `customer.subscription.deleted` until the period actually ends. The
 * cancellation was invisible here until the day it took effect.
 *
 * So "Cancelling" is its own lifecycle state on this page, and drift between
 * the two systems is shown on the row rather than buried.
 */

import { useEffect, useState, useCallback, Fragment } from 'react'
import { api } from '@/lib/api'
import {
  AlertTriangle, RefreshCw, Loader2, ChevronDown, ChevronRight,
  ExternalLink, CreditCard, Users, TrendingUp, XCircle,
} from 'lucide-react'

interface StripeSub {
  subscription_id: string | null
  status: string | null
  amount_minor: number | null
  currency: string
  interval: string | null
  interval_count: number
  current_period_start: string | null
  next_billing_date: string | null
  cancel_at_period_end: boolean
  canceled_at: string | null
  trial_end: string | null
  started_at: string | null
  discount: string | null
}

interface Subscriber {
  user_id: string
  email: string
  name: string | null
  joined: string | null
  last_login: string | null
  email_verified: boolean
  app_plan: string | null
  app_status: string | null
  app_billing_period: string | null
  app_access_until: string | null
  plan_locked_until: string | null
  plan_locked_reason: string | null
  is_founding_member: boolean
  stripe_customer_id: string | null
  stripe: StripeSub | null
  stripe_error: string | null
  lifecycle: string
  mrr_minor: number
  drift: string[]
}

interface Txn {
  invoice_id: string
  number: string | null
  created: string | null
  status: string | null
  description: string | null
  period_start: string | null
  period_end: string | null
  amount_due: number | null
  amount_paid: number | null
  amount_refunded: number | null
  currency: string
  hosted_url: string | null
  pdf_url: string | null
}

const money = (minor: number | null | undefined, ccy = 'AUD') =>
  minor === null || minor === undefined
    ? '—'
    : new Intl.NumberFormat('en-AU', { style: 'currency', currency: ccy || 'AUD' })
        .format(minor / 100)

const date = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString('en-AU',
    { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

/** Deliberately distinct colours for "cancelling" and "ended": one is still
 *  paying and recoverable, the other is gone. Collapsing them is how churn
 *  gets noticed a month late. */
const LIFECYCLE: Record<string, { label: string; cls: string }> = {
  active:          { label: 'Active',          cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  cancelling:      { label: 'Cancelling',      cls: 'bg-amber-50 text-amber-800 border-amber-300' },
  trialing:        { label: 'Trialing',        cls: 'bg-blue-50 text-blue-700 border-blue-200' },
  payment_failing: { label: 'Payment failing', cls: 'bg-red-50 text-red-700 border-red-200' },
  ended:           { label: 'Ended',           cls: 'bg-slate-100 text-slate-600 border-slate-200' },
  no_subscription: { label: 'No subscription', cls: 'bg-slate-100 text-slate-500 border-slate-200' },
  unknown:         { label: 'Unknown',         cls: 'bg-slate-100 text-slate-500 border-dashed border-slate-300' },
}

export default function AdminBillingPage() {
  const [rows, setRows] = useState<Subscriber[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [txns, setTxns] = useState<Record<string, any>>({})
  const [txnLoading, setTxnLoading] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const { data } = await api.get('/api/v1/admin/billing/subscribers')
      setRows(data.subscribers || [])
      setSummary(data.summary || null)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Could not load subscribers')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const openRow = async (id: string) => {
    if (open === id) { setOpen(null); return }
    setOpen(id)
    if (txns[id]) return
    setTxnLoading(id)
    try {
      const { data } = await api.get(
        `/api/v1/admin/billing/subscribers/${id}/transactions`)
      setTxns(prev => ({ ...prev, [id]: data }))
    } catch (e: any) {
      setTxns(prev => ({ ...prev, [id]: {
        error: e?.response?.data?.detail || e?.message || 'Unavailable' } }))
    } finally {
      setTxnLoading(null)
    }
  }

  return (
    <div className="p-6 max-w-[1400px]">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Paying Customers</h1>
          <p className="text-sm text-slate-500 mt-1">
            Billing state from Stripe, access state from the database, and any
            disagreement between them.
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border
                     border-slate-300 hover:bg-slate-50 disabled:opacity-50">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" />
                   : <RefreshCw className="w-4 h-4" />}
          Refresh
        </button>
      </div>

      {/* A dashboard whose numbers came from a failed call must say so where
          the numbers are read, not in a log. */}
      {summary?.stripe_error && (
        <div className="mb-4 p-4 rounded-lg border border-red-300 bg-red-50 flex gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div className="text-sm text-red-800">
            <p className="font-semibold">Stripe could not be read — billing figures below are incomplete.</p>
            <p className="mt-1 font-mono text-xs">{summary.stripe_error}</p>
            <p className="mt-1">
              Rows show database state only. A blank billing column here means
              “not retrieved”, <strong>not</strong> “no subscription”.
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-4 rounded-lg border border-red-300 bg-red-50 text-sm text-red-800">
          {error}
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Stat icon={Users} label="Customers" value={summary.customers} />
          <Stat icon={TrendingUp} label="MRR"
                value={money(summary.mrr_minor)}
                sub={`${money(summary.arr_minor)} annualised`} />
          <Stat icon={XCircle} label="Cancelling"
                value={summary.by_lifecycle?.cancelling || 0}
                sub="paying now, will not renew"
                warn={(summary.by_lifecycle?.cancelling || 0) > 0} />
          <Stat icon={AlertTriangle} label="Needs attention"
                value={summary.with_drift}
                sub="app and Stripe disagree"
                warn={summary.with_drift > 0} />
        </div>
      )}

      <div className="border border-slate-200 rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-3 py-3 text-left w-6"></th>
              <th className="px-3 py-3 text-left">Customer</th>
              <th className="px-3 py-3 text-left">Joined</th>
              <th className="px-3 py-3 text-left">Plan</th>
              <th className="px-3 py-3 text-right">Amount</th>
              <th className="px-3 py-3 text-left">Cycle</th>
              <th className="px-3 py-3 text-left">Next billing</th>
              <th className="px-3 py-3 text-left">State</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && rows.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-10 text-center text-slate-400">
                <Loader2 className="w-5 h-5 animate-spin inline" /> Loading…
              </td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-10 text-center text-slate-400">
                No customers with a Stripe record or paid plan.
              </td></tr>
            )}
            {rows.map(r => {
              const lc = LIFECYCLE[r.lifecycle] || LIFECYCLE.unknown
              const s = r.stripe
              const isOpen = open === r.user_id
              return (
                // The key belongs on the Fragment, not on the rows inside it:
                // a map returning a bare <> gives React nothing to reconcile
                // against, and rows reorder incorrectly on refresh.
                <Fragment key={r.user_id}>
                  <tr onClick={() => openRow(r.user_id)}
                      className={`cursor-pointer hover:bg-slate-50 ${
                        r.drift.length ? 'bg-amber-50/40' : ''}`}>
                    <td className="px-3 py-3 text-slate-400">
                      {isOpen ? <ChevronDown className="w-4 h-4" />
                              : <ChevronRight className="w-4 h-4" />}
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-medium text-slate-800">{r.email}</div>
                      {r.name && <div className="text-xs text-slate-500">{r.name}</div>}
                    </td>
                    <td className="px-3 py-3 text-slate-600">{date(r.joined)}</td>
                    <td className="px-3 py-3">
                      <span className="font-medium capitalize">{r.app_plan || 'free'}</span>
                      {r.is_founding_member && (
                        <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-violet-50
                                         text-violet-700 border border-violet-200">founding</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      {s ? money(s.amount_minor, s.currency) : '—'}
                    </td>
                    <td className="px-3 py-3 text-slate-600">
                      {s?.interval
                        ? `${s.interval_count > 1 ? s.interval_count + ' ' : ''}${s.interval}ly`
                            .replace('monthly', 'Monthly').replace('yearly', 'Yearly')
                        : '—'}
                    </td>
                    <td className="px-3 py-3 text-slate-600 tabular-nums">
                      {s?.cancel_at_period_end
                        ? <span className="text-amber-700">ends {date(s.next_billing_date)}</span>
                        : date(s?.next_billing_date)}
                    </td>
                    <td className="px-3 py-3">
                      <span className={`text-xs px-2 py-1 rounded border ${lc.cls}`}>
                        {lc.label}
                      </span>
                    </td>
                  </tr>

                  {r.drift.length > 0 && (
                    <tr className="bg-amber-50/60">
                      <td></td>
                      <td colSpan={7} className="px-3 pb-3">
                        {r.drift.map((d, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs text-amber-900">
                            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                            <span>{d}</span>
                          </div>
                        ))}
                      </td>
                    </tr>
                  )}

                  {isOpen && (
                    <tr>
                      <td></td>
                      <td colSpan={7} className="px-3 py-4 bg-slate-50/70">
                        <Detail row={r} txn={txns[r.user_id]}
                                loading={txnLoading === r.user_id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      {summary?.generated_at && (
        <p className="mt-3 text-xs text-slate-400">
          Read from Stripe at {new Date(summary.generated_at).toLocaleString('en-AU')}.
        </p>
      )}
    </div>
  )
}

function Stat({ icon: Icon, label, value, sub, warn }: any) {
  return (
    <div className={`p-4 rounded-lg border bg-white ${
      warn ? 'border-amber-300' : 'border-slate-200'}`}>
      <div className="flex items-center gap-2 text-xs text-slate-500 uppercase tracking-wide">
        <Icon className={`w-3.5 h-3.5 ${warn ? 'text-amber-600' : 'text-slate-400'}`} />
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold text-slate-800 tabular-nums">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  )
}

function Detail({ row, txn, loading }: {
  row: Subscriber; txn: any; loading: boolean
}) {
  const s = row.stripe
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-2 text-xs">
        <Field label="Stripe customer" value={row.stripe_customer_id} mono />
        <Field label="Subscription" value={s?.subscription_id} mono />
        <Field label="Stripe status" value={s?.status} />
        <Field label="Started" value={date(s?.started_at)} />
        <Field label="Current period began" value={date(s?.current_period_start)} />
        <Field label="App access until" value={date(row.app_access_until)} />
        <Field label="App status" value={row.app_status} />
        <Field label="Last login" value={date(row.last_login)} />
        {row.plan_locked_until && (
          <Field label="Plan locked until" value={date(row.plan_locked_until)}
                 hint={row.plan_locked_reason || undefined} />
        )}
        {s?.discount && <Field label="Discount" value={s.discount} />}
        {s?.trial_end && <Field label="Trial ends" value={date(s.trial_end)} />}
      </div>

      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2
                       flex items-center gap-2">
          <CreditCard className="w-3.5 h-3.5" /> Transaction history
        </h4>

        {loading && (
          <div className="text-xs text-slate-400 flex items-center gap-2">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Reading Stripe…
          </div>
        )}

        {txn?.error && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2">
            {txn.error} — the history exists but could not be retrieved. This is
            not “no transactions”.
          </div>
        )}

        {txn?.note && <div className="text-xs text-slate-500">{txn.note}</div>}

        {txn?.transactions?.length > 0 && (
          <>
            <table className="w-full text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="text-left py-1">Date</th>
                  <th className="text-left py-1">Invoice</th>
                  <th className="text-left py-1">Period</th>
                  <th className="text-right py-1">Paid</th>
                  <th className="text-right py-1">Refunded</th>
                  <th className="text-left py-1 pl-3">Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {txn.transactions.map((t: Txn) => (
                  <tr key={t.invoice_id}>
                    <td className="py-1.5">{date(t.created)}</td>
                    <td className="py-1.5 font-mono text-[11px]">{t.number || '—'}</td>
                    <td className="py-1.5 text-slate-500">
                      {t.period_start ? `${date(t.period_start)} → ${date(t.period_end)}` : '—'}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">
                      {money(t.amount_paid, t.currency)}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">
                      {t.amount_refunded ? (
                        <span className="text-red-600">−{money(t.amount_refunded, t.currency)}</span>
                      ) : '—'}
                    </td>
                    <td className="py-1.5 pl-3 capitalize">{t.status}</td>
                    <td className="py-1.5 text-right">
                      {t.hosted_url && (
                        <a href={t.hosted_url} target="_blank" rel="noreferrer"
                           onClick={e => e.stopPropagation()}
                           className="text-blue-600 hover:underline inline-flex items-center gap-1">
                          view <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-2 flex gap-6 text-xs text-slate-600">
              <span>Net paid: <strong className="tabular-nums">{money(txn.net_paid_minor)}</strong></span>
              {txn.refunded_minor > 0 && (
                <span>Refunded: <strong className="tabular-nums text-red-600">
                  {money(txn.refunded_minor)}</strong></span>
              )}
              {txn.credit_balance_minor !== 0 && (
                <span>Credit balance: <strong className="tabular-nums">
                  {money(Math.abs(txn.credit_balance_minor))}</strong>
                  {txn.credit_balance_minor < 0 ? ' (applies to next invoice)' : ' (owed)'}
                </span>
              )}
            </div>
          </>
        )}

        {txn && !txn.error && !txn.note && txn.transactions?.length === 0 && (
          <div className="text-xs text-slate-500">
            No invoices — this customer has never been charged.
          </div>
        )}
      </div>
    </div>
  )
}

function Field({ label, value, mono, hint }: {
  label: string; value: any; mono?: boolean; hint?: string
}) {
  return (
    <div>
      <div className="text-slate-400 uppercase tracking-wide text-[10px]">{label}</div>
      <div className={`text-slate-800 ${mono ? 'font-mono text-[11px]' : ''}`}>
        {value || '—'}
      </div>
      {hint && <div className="text-slate-500 text-[10px] mt-0.5">{hint}</div>}
    </div>
  )
}
