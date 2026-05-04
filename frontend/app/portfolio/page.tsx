'use client'

import { useEffect, useRef, useState, useMemo } from 'react'
import Link from 'next/link'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { useAuth } from '@/lib/auth'
import {
  listPortfolios,
  createPortfolio,
  deletePortfolio,
  getPortfolioPerformance,
  getPortfolioHistory,
  getPortfolioDividends,
  listTransactions,
  addTransaction,
  deleteTransaction,
  importHoldingsCsv,
  importTransactionsCsv,
  PortfolioOut,
  PortfolioPerformance,
  PortfolioHistory,
  PortfolioDividends,
  TransactionOut,
  ImportResult,
} from '@/lib/api'

// ── Helpers ───────────────────────────────────────────────────

const fmt = (n: number | null | undefined, decimals = 2, prefix = '') =>
  n == null ? '—' : `${prefix}${n.toLocaleString('en-AU', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`

const fmtMoney = (n: number | null | undefined) => fmt(n, 2, '$')
const fmtPct   = (n: number | null | undefined) => n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`

const glColor = (n: number | null | undefined) =>
  n == null ? 'text-slate-500' : n >= 0 ? 'text-emerald-600' : 'text-red-500'

const PIE_COLORS = [
  '#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6',
  '#06b6d4','#84cc16','#f97316','#ec4899','#6366f1',
  '#14b8a6','#a855f7','#eab308','#64748b','#0ea5e9',
]

// ── Subcomponents ─────────────────────────────────────────────

function SummaryCard({ label, value, sub, subColor }: { label: string; value: string; sub?: string; subColor?: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-slate-900">{value}</p>
      {sub && <p className={`text-xs mt-0.5 font-medium ${subColor ?? 'text-slate-400'}`}>{sub}</p>}
    </div>
  )
}

// ── Portfolio Chart ───────────────────────────────────────────

const CHART_PERIODS = ['1m', '3m', '6m', '1y', '2y', 'all'] as const
type ChartPeriod = typeof CHART_PERIODS[number]

function PortfolioChart({ portfolioId }: { portfolioId: string }) {
  const [period, setPeriod]   = useState<ChartPeriod>('1y')
  const [data, setData]       = useState<PortfolioHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getPortfolioHistory(portfolioId, period)
      .then(setData)
      .catch(() => setError('Failed to load history'))
      .finally(() => setLoading(false))
  }, [portfolioId, period])

  const latest = data?.history.at(-1)
  const first  = data?.history[0]
  const totalReturn = (latest && first)
    ? ((latest.value - first.cost) / first.cost * 100)
    : null

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Portfolio Value Over Time</h3>
          {latest && (
            <p className={`text-xs mt-0.5 ${latest.gain_loss >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
              {fmtMoney(latest.gain_loss)} ({totalReturn != null ? fmtPct(totalReturn) : '—'}) vs cost
            </p>
          )}
        </div>
        <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
          {CHART_PERIODS.map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${period === p ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-64 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <div className="h-64 flex items-center justify-center text-sm text-slate-400">{error}</div>
      ) : !data?.history.length ? (
        <div className="h-64 flex items-center justify-center text-sm text-slate-400">
          No price history available yet. Add transactions and wait for data to populate.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data.history} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#94a3b8' }}
              tickFormatter={d => {
                const dt = new Date(d)
                return `${dt.toLocaleString('en-AU', { month: 'short' })} '${String(dt.getFullYear()).slice(2)}`
              }}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#94a3b8' }}
              tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
              width={55}
            />
            <Tooltip
              formatter={(val: any, name: any) => [fmtMoney(val as number), name === 'value' ? 'Market Value' : 'Cost Basis']}
              labelFormatter={d => new Date(d).toLocaleDateString('en-AU')}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
            />
            <Line type="monotone" dataKey="cost" stroke="#94a3b8" strokeWidth={1.5} dot={false} strokeDasharray="4 2" name="cost" />
            <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2.5} dot={false} name="value" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Allocation Charts ─────────────────────────────────────────

function AllocationCharts({ perf }: { perf: PortfolioPerformance }) {
  const holdings = perf.holdings.filter(h => h.current_value != null && h.current_value > 0)
  const totalValue = holdings.reduce((s, h) => s + (h.current_value ?? 0), 0)

  const byStock = holdings
    .map(h => ({ name: h.asx_code, value: h.current_value ?? 0 }))
    .sort((a, b) => b.value - a.value)

  const bySector = Object.entries(
    holdings.reduce<Record<string, number>>((acc, h) => {
      const s = h.sector ?? 'Other'
      acc[s] = (acc[s] ?? 0) + (h.current_value ?? 0)
      return acc
    }, {})
  )
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)

  if (!holdings.length) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500 text-sm">
        No holdings with live prices to display allocation.
      </div>
    )
  }

  const customLabel = ({ name, value }: { name: string; value: number }) => {
    const pct = totalValue > 0 ? ((value / totalValue) * 100).toFixed(1) : '0'
    return `${pct}%`
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
      {/* By Stock */}
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-800 mb-4">By Stock</h3>
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie data={byStock} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}
              label={({ name, value }) => `${name} ${totalValue > 0 ? ((value / totalValue) * 100).toFixed(0) : 0}%`}
              labelLine={false}>
              {byStock.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v: any) => [fmtMoney(v as number)]} contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }} />
          </PieChart>
        </ResponsiveContainer>
        <div className="mt-3 space-y-1.5 max-h-36 overflow-y-auto">
          {byStock.map((item, i) => (
            <div key={item.name} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                <span className="font-medium text-slate-700">{item.name}</span>
              </div>
              <div className="flex items-center gap-3 text-slate-500">
                <span>{fmtMoney(item.value)}</span>
                <span className="w-10 text-right">{totalValue > 0 ? ((item.value / totalValue) * 100).toFixed(1) : 0}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* By Sector */}
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-800 mb-4">By Sector</h3>
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie data={bySector} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80}
              label={({ name, value }) => `${totalValue > 0 ? ((value / totalValue) * 100).toFixed(0) : 0}%`}
              labelLine={false}>
              {bySector.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={(v: any) => [fmtMoney(v as number)]} contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }} />
          </PieChart>
        </ResponsiveContainer>
        <div className="mt-3 space-y-1.5 max-h-36 overflow-y-auto">
          {bySector.map((item, i) => (
            <div key={item.name} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                <span className="font-medium text-slate-700 truncate max-w-32">{item.name}</span>
              </div>
              <div className="flex items-center gap-3 text-slate-500">
                <span>{fmtMoney(item.value)}</span>
                <span className="w-10 text-right">{totalValue > 0 ? ((item.value / totalValue) * 100).toFixed(1) : 0}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Dividend Calendar ─────────────────────────────────────────

function DividendCalendar({ portfolioId }: { portfolioId: string }) {
  const [data, setData]       = useState<PortfolioDividends | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [tab, setTab]         = useState<'upcoming' | 'received'>('upcoming')

  useEffect(() => {
    setLoading(true)
    getPortfolioDividends(portfolioId)
      .then(setData)
      .catch(() => setError('Failed to load dividend data'))
      .finally(() => setLoading(false))
  }, [portfolioId])

  const upcomingTotal  = data?.upcoming.reduce((s, d) => s + (d.est_income ?? 0), 0) ?? 0
  const receivedTotal  = data?.received.reduce((s, d) => s + (d.est_income ?? 0), 0) ?? 0

  const events = tab === 'upcoming' ? (data?.upcoming ?? []) : (data?.received ?? [])

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Dividend Calendar</h3>
          <p className="text-xs text-slate-400 mt-0.5">Based on your current holdings</p>
        </div>
        <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
          <button onClick={() => setTab('upcoming')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${tab === 'upcoming' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            Upcoming {data ? `(${data.upcoming.length})` : ''}
          </button>
          <button onClick={() => setTab('received')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${tab === 'received' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
            Last 12M {data ? `(${data.received.length})` : ''}
          </button>
        </div>
      </div>

      {/* Summary strip */}
      {data && (
        <div className="mb-4 grid grid-cols-2 gap-3">
          <div className="bg-blue-50 rounded-lg p-3">
            <p className="text-xs text-blue-600 font-medium">Upcoming Est. Income</p>
            <p className="text-lg font-bold text-blue-700">{fmtMoney(upcomingTotal)}</p>
            <p className="text-xs text-blue-500 mt-0.5">next 6 months</p>
          </div>
          <div className="bg-emerald-50 rounded-lg p-3">
            <p className="text-xs text-emerald-600 font-medium">Received (12M)</p>
            <p className="text-lg font-bold text-emerald-700">{fmtMoney(receivedTotal)}</p>
            <p className="text-xs text-emerald-500 mt-0.5">estimated</p>
          </div>
        </div>
      )}

      {loading ? (
        <div className="h-40 bg-slate-100 rounded-xl animate-pulse" />
      ) : error ? (
        <div className="text-center text-sm text-slate-400 py-8">{error}</div>
      ) : events.length === 0 ? (
        <div className="text-center text-sm text-slate-400 py-8">
          {tab === 'upcoming'
            ? 'No upcoming dividends found for your holdings in the next 6 months.'
            : 'No dividends received in the last 12 months.'}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                <th className="px-3 py-2 text-left">Stock</th>
                <th className="px-3 py-2 text-left">Ex-Date</th>
                <th className="px-3 py-2 text-left">Pay Date</th>
                <th className="px-3 py-2 text-right">Amount</th>
                <th className="px-3 py-2 text-right">Qty</th>
                <th className="px-3 py-2 text-right">Est. Income</th>
                <th className="px-3 py-2 text-right">Gross Inc.</th>
                <th className="px-3 py-2 text-right">Franking</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {events.map((ev, i) => (
                <tr key={i} className="hover:bg-slate-50 transition-colors">
                  <td className="px-3 py-2.5">
                    <Link href={`/company/${ev.asx_code}`} className="font-semibold text-blue-600 hover:underline">{ev.asx_code}</Link>
                    {ev.company_name && <div className="text-xs text-slate-400 truncate max-w-28">{ev.company_name}</div>}
                  </td>
                  <td className="px-3 py-2.5 text-slate-600 whitespace-nowrap">{ev.ex_date ?? '—'}</td>
                  <td className="px-3 py-2.5 text-slate-400 whitespace-nowrap">{ev.payment_date ?? '—'}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmt(ev.amount, 4, '$')}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-500">{fmt(ev.quantity, 0)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums font-medium text-blue-700">{fmtMoney(ev.est_income)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-emerald-600">
                    {ev.franking_pct > 0 ? fmtMoney(ev.gross_income) : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-500">
                    {ev.franking_pct > 0 ? `${ev.franking_pct.toFixed(0)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Add Transaction Modal ─────────────────────────────────────

function AddTransactionModal({
  portfolioId,
  onClose,
  onAdded,
}: {
  portfolioId: string
  onClose: () => void
  onAdded: () => void
}) {
  const [form, setForm] = useState({
    asx_code: '', transaction_type: 'buy', transaction_date: new Date().toISOString().slice(0, 10),
    shares: '', price_per_share: '', brokerage: '0', notes: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState<string | null>(null)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await addTransaction(portfolioId, {
        asx_code:        form.asx_code.toUpperCase().trim(),
        transaction_type: form.transaction_type,
        transaction_date: form.transaction_date,
        shares:           parseFloat(form.shares),
        price_per_share:  parseFloat(form.price_per_share),
        brokerage:        parseFloat(form.brokerage || '0'),
        notes:            form.notes || undefined,
      })
      onAdded()
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Failed to add transaction')
    } finally {
      setSaving(false)
    }
  }

  const total = (parseFloat(form.shares || '0') * parseFloat(form.price_per_share || '0') + parseFloat(form.brokerage || '0')).toFixed(2)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
        <h2 className="text-lg font-bold text-slate-900 mb-4">Add Transaction</h2>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">ASX Code *</label>
              <input value={form.asx_code} onChange={set('asx_code')} required placeholder="CBA"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm uppercase focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Type *</label>
              <select value={form.transaction_type} onChange={set('transaction_type')}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
                <option value="drp">DRP</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600 block mb-1">Date *</label>
            <input type="date" value={form.transaction_date} onChange={set('transaction_date')} required
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Quantity *</label>
              <input type="number" min="0.0001" step="any" value={form.shares} onChange={set('shares')} required placeholder="100"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Price ($) *</label>
              <input type="number" min="0.0001" step="any" value={form.price_per_share} onChange={set('price_per_share')} required placeholder="45.20"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Brokerage ($)</label>
              <input type="number" min="0" step="any" value={form.brokerage} onChange={set('brokerage')} placeholder="19.95"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600 block mb-1">Notes</label>
            <input value={form.notes} onChange={set('notes')} placeholder="Optional"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div className="text-right text-sm text-slate-500">
            Total: <span className="font-semibold text-slate-900">${total}</span>
          </div>
          {error && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex justify-end gap-3 pt-1">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
              {saving ? 'Saving…' : 'Add Transaction'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Import CSV Modal ──────────────────────────────────────────

function ImportModal({
  portfolioId,
  onClose,
  onImported,
}: {
  portfolioId: string
  onClose: () => void
  onImported: () => void
}) {
  const [mode, setMode]     = useState<'holdings' | 'transactions'>('holdings')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = mode === 'holdings'
        ? await importHoldingsCsv(portfolioId, file)
        : await importTransactionsCsv(portfolioId, file)
      setResult(res)
      if (res.imported > 0) onImported()
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Import failed')
    } finally {
      setLoading(false)
    }
  }

  const holdingsTemplate = 'asx_code,quantity,avg_cost,purchase_date\nCBA,100,145.50,2023-01-15\nBHP,200,43.20,2022-06-10\n'
  const txnTemplate      = 'date,asx_code,type,quantity,price,brokerage\n2023-01-15,CBA,buy,100,145.50,19.95\n2024-03-01,CBA,sell,50,168.00,19.95\n'

  const downloadTemplate = () => {
    const content = mode === 'holdings' ? holdingsTemplate : txnTemplate
    const blob = new Blob([content], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url
    a.download = mode === 'holdings' ? 'holdings_template.csv' : 'transactions_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6">
        <h2 className="text-lg font-bold text-slate-900 mb-4">Import from CSV</h2>

        <div className="flex gap-2 mb-4">
          {(['holdings', 'transactions'] as const).map(m => (
            <button key={m} onClick={() => { setMode(m); setResult(null); if (fileRef.current) fileRef.current.value = '' }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${mode === m ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              {m === 'holdings' ? 'Portfolio Holdings' : 'Transaction History'}
            </button>
          ))}
        </div>

        <div className="bg-slate-50 rounded-lg p-3 mb-4 text-xs text-slate-600 font-mono">
          {mode === 'holdings'
            ? 'asx_code, quantity, avg_cost, purchase_date (optional)'
            : 'date, asx_code, type (buy/sell/drp), quantity, price, brokerage (optional)'}
        </div>

        <div className="flex gap-2 mb-4">
          <button onClick={downloadTemplate} className="text-xs text-blue-600 hover:underline">
            ↓ Download template
          </button>
        </div>

        <label className="block w-full border-2 border-dashed border-slate-300 rounded-xl p-6 text-center cursor-pointer hover:border-blue-400 transition-colors">
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleFile} />
          {loading
            ? <span className="text-sm text-slate-500">Importing…</span>
            : <span className="text-sm text-slate-500">Click to upload CSV file</span>}
        </label>

        {result && (
          <div className={`mt-3 rounded-lg px-4 py-3 text-sm ${result.imported > 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
            <p className="font-semibold">{result.imported} row{result.imported !== 1 ? 's' : ''} imported{result.skipped > 0 ? `, ${result.skipped} skipped` : ''}</p>
            {result.errors.length > 0 && (
              <ul className="mt-1 text-xs space-y-0.5 text-red-600">
                {result.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            )}
          </div>
        )}
        {error && <p className="mt-3 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

        <div className="flex justify-end mt-4">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg">Close</button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────

type ViewTab = 'holdings' | 'transactions' | 'chart' | 'allocation' | 'dividends'

export default function PortfolioPage() {
  const { user, loading: authLoading } = useAuth()

  const [portfolios, setPortfolios]   = useState<PortfolioOut[]>([])
  const [activeId, setActiveId]       = useState<string | null>(null)
  const [perf, setPerf]               = useState<PortfolioPerformance | null>(null)
  const [txns, setTxns]               = useState<TransactionOut[]>([])
  const [view, setView]               = useState<ViewTab>('holdings')

  const [loading, setLoading]         = useState(false)
  const [perfLoading, setPerfLoading] = useState(false)
  const [perfError, setPerfError]     = useState<string | null>(null)

  const [showCreate, setShowCreate]   = useState(false)
  const [newName, setNewName]         = useState('')
  const [newSmsf, setNewSmsf]         = useState(false)
  const [creating, setCreating]       = useState(false)

  const [showAddTxn, setShowAddTxn]   = useState(false)
  const [showImport, setShowImport]   = useState(false)

  useEffect(() => {
    if (!user) return
    setLoading(true)
    listPortfolios()
      .then(r => {
        setPortfolios(r.portfolios)
        if (r.portfolios.length > 0) setActiveId(r.portfolios[0].id)
      })
      .finally(() => setLoading(false))
  }, [user])

  useEffect(() => {
    if (!activeId) return
    setPerfLoading(true)
    setPerfError(null)
    Promise.all([
      getPortfolioPerformance(activeId),
      listTransactions(activeId),
    ]).then(([p, t]) => {
      setPerf(p)
      setTxns(t.transactions)
    }).catch(e => {
      const status = e?.response?.status
      const detail = e?.response?.data?.detail
      const msg = detail
        ? (typeof detail === 'string' ? detail : JSON.stringify(detail))
        : (e?.message ?? 'Unknown error')
      setPerfError(status ? `HTTP ${status}: ${msg}` : msg)
    })
    .finally(() => setPerfLoading(false))
  }, [activeId])

  const refresh = () => {
    if (!activeId) return
    setPerfLoading(true)
    setPerfError(null)
    Promise.all([
      getPortfolioPerformance(activeId),
      listTransactions(activeId),
    ]).then(([p, t]) => {
      setPerf(p)
      setTxns(t.transactions)
    }).catch(e => {
      const status = e?.response?.status
      const detail = e?.response?.data?.detail
      const msg = detail
        ? (typeof detail === 'string' ? detail : JSON.stringify(detail))
        : (e?.message ?? 'Unknown error')
      setPerfError(status ? `HTTP ${status}: ${msg}` : msg)
    })
    .finally(() => setPerfLoading(false))
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newName.trim()) return
    setCreating(true)
    try {
      const p = await createPortfolio(newName.trim(), undefined, newSmsf)
      setPortfolios(prev => [...prev, p])
      setActiveId(p.id)
      setShowCreate(false)
      setNewName('')
    } finally {
      setCreating(false)
    }
  }

  const handleDeletePortfolio = async (id: string) => {
    if (!confirm('Delete this portfolio and all its transactions? This cannot be undone.')) return
    await deletePortfolio(id)
    const updated = portfolios.filter(p => p.id !== id)
    setPortfolios(updated)
    setActiveId(updated[0]?.id ?? null)
    if (updated.length === 0) { setPerf(null); setTxns([]) }
  }

  const handleDeleteTxn = async (txnId: number) => {
    if (!activeId) return
    await deleteTransaction(activeId, txnId)
    refresh()
  }

  if (authLoading) return <div className="flex items-center justify-center h-64 text-slate-500">Loading…</div>
  if (!user) return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <p className="text-slate-600">Sign in to track your portfolio.</p>
      <Link href="/auth/login" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">Sign In</Link>
    </div>
  )

  const activePortfolio = portfolios.find(p => p.id === activeId)

  const VIEW_TABS: { key: ViewTab; label: string }[] = [
    { key: 'holdings',     label: `Holdings${perf ? ` (${perf.holdings.length})` : ''}` },
    { key: 'chart',        label: 'Performance' },
    { key: 'allocation',   label: 'Allocation' },
    { key: 'dividends',    label: 'Dividends' },
    { key: 'transactions', label: `Transactions${txns.length ? ` (${txns.length})` : ''}` },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Portfolio</h1>
          <p className="text-sm text-slate-500 mt-0.5">Track your ASX holdings, P&amp;L, and dividend income</p>
        </div>
        <div className="flex items-center gap-2">
          {activeId && (
            <>
              <button onClick={() => setShowImport(true)}
                className="px-3 py-2 text-sm border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-600">
                ↑ Import CSV
              </button>
              <button onClick={() => setShowAddTxn(true)}
                className="px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
                + Add Transaction
              </button>
            </>
          )}
          <button onClick={() => setShowCreate(true)}
            className="px-3 py-2 text-sm border border-blue-300 rounded-lg hover:bg-blue-50 text-blue-600">
            + New Portfolio
          </button>
        </div>
      </div>

      {/* Portfolio tabs */}
      {portfolios.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          {portfolios.map(p => (
            <button key={p.id} onClick={() => setActiveId(p.id)}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${activeId === p.id ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              {p.name}{p.is_smsf ? ' 🏦' : ''}
            </button>
          ))}
        </div>
      )}

      {/* Create portfolio form */}
      {showCreate && (
        <form onSubmit={handleCreate} className="bg-white border border-slate-200 rounded-xl p-4 flex items-end gap-3 flex-wrap">
          <div className="flex-1 min-w-48">
            <label className="text-xs font-medium text-slate-600 block mb-1">Portfolio Name</label>
            <input autoFocus value={newName} onChange={e => setNewName(e.target.value)} required placeholder="My Portfolio"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer pb-2">
            <input type="checkbox" checked={newSmsf} onChange={e => setNewSmsf(e.target.checked)} className="rounded" />
            SMSF
          </label>
          <div className="flex gap-2 pb-0.5">
            <button type="button" onClick={() => setShowCreate(false)} className="px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
            <button type="submit" disabled={creating} className="px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
              {creating ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      )}

      {/* Empty state */}
      {!loading && portfolios.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center">
          <div className="text-4xl mb-3">📊</div>
          <h2 className="text-lg font-semibold text-slate-800 mb-1">No portfolios yet</h2>
          <p className="text-sm text-slate-500 mb-4">Create a portfolio and start tracking your ASX holdings.</p>
          <button onClick={() => setShowCreate(true)} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            Create Portfolio
          </button>
        </div>
      )}

      {/* Performance */}
      {activeId && (
        <>
          {perfLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[1,2,3,4].map(i => <div key={i} className="h-20 bg-slate-100 rounded-xl animate-pulse" />)}
            </div>
          ) : perfError ? (
            <div className="bg-red-50 border border-red-200 rounded-xl p-5 flex items-start gap-3">
              <span className="text-red-500 text-lg">⚠</span>
              <div className="flex-1">
                <p className="text-sm font-semibold text-red-700">Failed to load portfolio data</p>
                <p className="text-xs text-red-600 mt-0.5">{perfError}</p>
              </div>
              <button onClick={refresh} className="text-xs text-red-600 underline hover:text-red-800">Retry</button>
            </div>
          ) : perf && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <SummaryCard label="Market Value" value={fmtMoney(perf.total_value)} />
                <SummaryCard
                  label="Total Gain / Loss"
                  value={fmtMoney(perf.total_gain_loss)}
                  sub={fmtPct(perf.total_gain_loss_pct)}
                  subColor={glColor(perf.total_gain_loss)}
                />
                <SummaryCard label="Cost Basis" value={fmtMoney(perf.total_cost)} />
                <SummaryCard
                  label="Est. Annual Income"
                  value={fmtMoney(perf.annual_income)}
                  sub={perf.portfolio_yield != null ? `${perf.portfolio_yield.toFixed(2)}% yield` : undefined}
                  subColor="text-blue-600"
                />
              </div>

              {/* View tabs */}
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex gap-1 bg-slate-100 p-1 rounded-lg overflow-x-auto">
                  {VIEW_TABS.map(({ key, label }) => (
                    <button key={key} onClick={() => setView(key)}
                      className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors whitespace-nowrap ${view === key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                      {label}
                    </button>
                  ))}
                </div>
                {activePortfolio && (
                  <button onClick={() => handleDeletePortfolio(activePortfolio.id)}
                    className="text-xs text-red-400 hover:text-red-600">
                    Delete portfolio
                  </button>
                )}
              </div>

              {/* Holdings table */}
              {view === 'holdings' && (
                perf.holdings.length === 0 ? (
                  <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500 text-sm">
                    No holdings yet. Add a transaction or import a CSV to get started.
                  </div>
                ) : (
                  <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-100 bg-slate-50 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                            <th className="px-4 py-3 text-left">Stock</th>
                            <th className="px-4 py-3 text-right">Qty</th>
                            <th className="px-4 py-3 text-right">Avg Cost</th>
                            <th className="px-4 py-3 text-right">Cost Basis</th>
                            <th className="px-4 py-3 text-right">Price</th>
                            <th className="px-4 py-3 text-right">Value</th>
                            <th className="px-4 py-3 text-right">Gain / Loss</th>
                            <th className="px-4 py-3 text-right">Yield</th>
                            <th className="px-4 py-3 text-right">Ann. Income</th>
                            <th className="px-4 py-3 text-right">Franking</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {perf.holdings.map(h => (
                            <tr key={h.asx_code} className="hover:bg-slate-50 transition-colors">
                              <td className="px-4 py-3">
                                <Link href={`/company/${h.asx_code}`} className="font-semibold text-blue-600 hover:underline">{h.asx_code}</Link>
                                {h.company_name && <div className="text-xs text-slate-400 truncate max-w-36">{h.company_name}</div>}
                              </td>
                              <td className="px-4 py-3 text-right tabular-nums">{fmt(h.quantity, 0)}</td>
                              <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(h.avg_cost)}</td>
                              <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(h.cost_basis)}</td>
                              <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(h.current_price)}</td>
                              <td className="px-4 py-3 text-right tabular-nums font-medium">{fmtMoney(h.current_value)}</td>
                              <td className="px-4 py-3 text-right tabular-nums">
                                <div className={`font-medium ${glColor(h.gain_loss)}`}>{fmtMoney(h.gain_loss)}</div>
                                <div className={`text-xs ${glColor(h.gain_loss_pct)}`}>{fmtPct(h.gain_loss_pct)}</div>
                              </td>
                              <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                                {h.dividend_yield != null ? `${(h.dividend_yield * 100).toFixed(2)}%` : '—'}
                              </td>
                              <td className="px-4 py-3 text-right tabular-nums text-blue-600">{fmtMoney(h.annual_income)}</td>
                              <td className="px-4 py-3 text-right tabular-nums text-slate-500">
                                {h.franking_pct != null ? `${h.franking_pct.toFixed(0)}%` : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              )}

              {/* Performance chart */}
              {view === 'chart' && <PortfolioChart portfolioId={activeId} />}

              {/* Allocation */}
              {view === 'allocation' && <AllocationCharts perf={perf} />}

              {/* Dividends */}
              {view === 'dividends' && <DividendCalendar portfolioId={activeId} />}

              {/* Transactions table */}
              {view === 'transactions' && (
                txns.length === 0 ? (
                  <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500 text-sm">
                    No transactions yet.
                  </div>
                ) : (
                  <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-100 bg-slate-50 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                            <th className="px-4 py-3 text-left">Date</th>
                            <th className="px-4 py-3 text-left">Code</th>
                            <th className="px-4 py-3 text-left">Type</th>
                            <th className="px-4 py-3 text-right">Qty</th>
                            <th className="px-4 py-3 text-right">Price</th>
                            <th className="px-4 py-3 text-right">Brokerage</th>
                            <th className="px-4 py-3 text-right">Total</th>
                            <th className="px-4 py-3 text-left">Notes</th>
                            <th className="px-4 py-3"></th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                          {txns.map(t => (
                            <tr key={t.id} className="hover:bg-slate-50 transition-colors">
                              <td className="px-4 py-3 text-slate-500">{t.transaction_date}</td>
                              <td className="px-4 py-3">
                                <Link href={`/company/${t.asx_code}`} className="font-semibold text-blue-600 hover:underline">{t.asx_code}</Link>
                              </td>
                              <td className="px-4 py-3">
                                <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${t.transaction_type === 'buy' || t.transaction_type === 'drp' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                  {t.transaction_type.toUpperCase()}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-right tabular-nums">{fmt(t.shares, 2)}</td>
                              <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(t.price_per_share)}</td>
                              <td className="px-4 py-3 text-right tabular-nums text-slate-400">{t.brokerage > 0 ? fmtMoney(t.brokerage) : '—'}</td>
                              <td className="px-4 py-3 text-right tabular-nums font-medium">{fmtMoney(t.total_cost)}</td>
                              <td className="px-4 py-3 text-slate-400 text-xs">{t.notes ?? '—'}</td>
                              <td className="px-4 py-3 text-right">
                                <button onClick={() => handleDeleteTxn(t.id)} className="text-slate-300 hover:text-red-500 transition-colors text-xs">✕</button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              )}
            </>
          )}
        </>
      )}

      {/* Modals */}
      {showAddTxn && activeId && (
        <AddTransactionModal
          portfolioId={activeId}
          onClose={() => setShowAddTxn(false)}
          onAdded={() => { setShowAddTxn(false); refresh() }}
        />
      )}
      {showImport && activeId && (
        <ImportModal
          portfolioId={activeId}
          onClose={() => setShowImport(false)}
          onImported={refresh}
        />
      )}
    </div>
  )
}
