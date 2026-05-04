'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import {
  listPortfolios,
  createPortfolio,
  deletePortfolio,
  getPortfolioPerformance,
  listTransactions,
  addTransaction,
  deleteTransaction,
  importHoldingsCsv,
  importTransactionsCsv,
  PortfolioOut,
  PortfolioPerformance,
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

        {/* Mode selector */}
        <div className="flex gap-2 mb-4">
          {(['holdings', 'transactions'] as const).map(m => (
            <button key={m} onClick={() => { setMode(m); setResult(null); if (fileRef.current) fileRef.current.value = '' }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${mode === m ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
              {m === 'holdings' ? 'Portfolio Holdings' : 'Transaction History'}
            </button>
          ))}
        </div>

        {/* Format description */}
        <div className="bg-slate-50 rounded-lg p-3 mb-4 text-xs text-slate-600 font-mono">
          {mode === 'holdings'
            ? 'asx_code, quantity, avg_cost, purchase_date (optional)'
            : 'date, asx_code, type (buy/sell/drp), quantity, price, brokerage (optional)'}
        </div>

        <div className="flex gap-2 mb-4">
          <button onClick={downloadTemplate}
            className="text-xs text-blue-600 hover:underline">
            ↓ Download template
          </button>
        </div>

        {/* Upload */}
        <label className="block w-full border-2 border-dashed border-slate-300 rounded-xl p-6 text-center cursor-pointer hover:border-blue-400 transition-colors">
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleFile} />
          {loading
            ? <span className="text-sm text-slate-500">Importing…</span>
            : <span className="text-sm text-slate-500">Click to upload CSV file</span>}
        </label>

        {/* Result */}
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

export default function PortfolioPage() {
  const { user, loading: authLoading } = useAuth()

  const [portfolios, setPortfolios]   = useState<PortfolioOut[]>([])
  const [activeId, setActiveId]       = useState<string | null>(null)
  const [perf, setPerf]               = useState<PortfolioPerformance | null>(null)
  const [txns, setTxns]               = useState<TransactionOut[]>([])
  const [view, setView]               = useState<'holdings' | 'transactions'>('holdings')

  const [loading, setLoading]         = useState(false)
  const [perfLoading, setPerfLoading] = useState(false)
  const [perfError, setPerfError]     = useState<string | null>(null)

  const [showCreate, setShowCreate]   = useState(false)
  const [newName, setNewName]         = useState('')
  const [newSmsf, setNewSmsf]         = useState(false)
  const [creating, setCreating]       = useState(false)

  const [showAddTxn, setShowAddTxn]   = useState(false)
  const [showImport, setShowImport]   = useState(false)

  // ── Load portfolios on mount ──────────────────────────────────
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

  // ── Load performance + transactions when active portfolio changes ──
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

  // ── Auth gate ─────────────────────────────────────────────────
  if (authLoading) return <div className="flex items-center justify-center h-64 text-slate-500">Loading…</div>
  if (!user) return (
    <div className="flex flex-col items-center justify-center h-64 gap-4">
      <p className="text-slate-600">Sign in to track your portfolio.</p>
      <Link href="/auth/login" className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">Sign In</Link>
    </div>
  )

  const activePortfolio = portfolios.find(p => p.id === activeId)

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

              {/* View toggle */}
              <div className="flex items-center justify-between">
                <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
                  {(['holdings', 'transactions'] as const).map(v => (
                    <button key={v} onClick={() => setView(v)}
                      className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${view === v ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                      {v === 'holdings' ? `Holdings (${perf.holdings.length})` : `Transactions (${txns.length})`}
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
