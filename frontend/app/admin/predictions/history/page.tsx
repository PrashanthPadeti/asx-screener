'use client'
/**
 * ASX Price Predictions — Historical View
 * ========================================
 * Search up to 5 stocks and overlay their 60-day prediction history on a
 * Recharts line chart.  One line per horizon (5 / 10 / 20 / 30 / 50d).
 *
 * DISCLAIMER: Statistical models only. Not investment advice.
 */

import { useState, useCallback } from 'react'
import { api } from '@/lib/api'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import {
  History, Search, X, TrendingUp, TrendingDown, Minus,
  AlertTriangle, Info,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

type SeriesPoint = {
  date:          string
  current_price: number | null
  h5?:           number | null
  h10?:          number | null
  h20?:          number | null
  h30?:          number | null
  h50?:          number | null
  [key: string]: string | number | null | undefined
}

type HistoryResp = {
  asx_code:     string
  company_name: string
  model:        string
  days:         number
  horizons:     number[]
  series:       SeriesPoint[]
}

// ── Constants ─────────────────────────────────────────────────────────────────

const MODELS = [
  { key: 'ensemble', label: 'Ensemble' },
  { key: 'xgboost',  label: 'XGBoost'  },
  { key: 'rf',       label: 'Random Forest' },
  { key: 'svm',      label: 'SVM'      },
  { key: 'lstm',     label: 'LSTM'     },
]

const HORIZONS = [5, 10, 20, 30, 50]

// Distinct colours for each horizon line
const H_COLORS: Record<number, string> = {
  5:  '#6366f1',   // indigo
  10: '#10b981',   // emerald
  20: '#f59e0b',   // amber
  30: '#ef4444',   // red
  50: '#8b5cf6',   // violet
}

// Up to 5 stocks — each gets a distinct dash pattern for multi-stock compare
const DASH_PATTERNS = ['', '5 5', '10 5', '3 3', '8 3 3 3']

// Muted stock colours for multi-stock mode (overrides horizon colours)
const STOCK_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(d: string) {
  return new Date(d + 'T00:00:00').toLocaleDateString('en-AU', {
    day: '2-digit', month: 'short',
  })
}

function fmtPct(v: number | null | undefined) {
  if (v == null) return '—'
  return (v > 0 ? '+' : '') + v.toFixed(2) + '%'
}

function pctColor(v: number | null | undefined) {
  if (v == null) return 'text-gray-400'
  if (v >  2) return 'text-emerald-600 font-semibold'
  if (v < -2) return 'text-red-600 font-semibold'
  return 'text-gray-700'
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label, stocks, selectedHorizon, singleHorizon }: {
  active?: boolean
  payload?: { name: string; value: number; color: string }[]
  label?: string
  stocks: string[]
  selectedHorizon: number | null
  singleHorizon: boolean
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-xl p-3 text-xs min-w-[160px]">
      <p className="font-semibold text-slate-700 mb-2">{label ? fmtDate(label) : ''}</p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center justify-between gap-4 mb-0.5">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ background: p.color }} />
            <span className="text-slate-600">{p.name}</span>
          </span>
          <span className={p.value > 2 ? 'text-emerald-600 font-semibold' : p.value < -2 ? 'text-red-600 font-semibold' : 'text-gray-700'}>
            {fmtPct(p.value)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Main Page
// ══════════════════════════════════════════════════════════════════════════════

export default function PredictionHistoryPage() {
  // ── State ──────────────────────────────────────────────────────────────────
  const [search,          setSearch]          = useState('')
  const [model,           setModel]           = useState('ensemble')
  const [days,            setDays]            = useState(30)
  const [selectedHorizon, setSelectedHorizon] = useState<number | null>(null)  // null = all
  const [stocks,          setStocks]          = useState<string[]>([])  // up to 5
  const [data,            setData]            = useState<Record<string, HistoryResp>>({})
  const [loading,         setLoading]         = useState<Record<string, boolean>>({})
  const [error,           setError]           = useState<Record<string, string>>({})

  // ── Fetch history for one stock ────────────────────────────────────────────
  const fetchStock = useCallback(async (code: string, currentModel = model, currentDays = days) => {
    const key = `${code}:${currentModel}:${currentDays}`
    setLoading(l => ({ ...l, [code]: true }))
    setError(e => { const n = { ...e }; delete n[code]; return n })
    try {
      const r = await api.get(`/api/v1/predictions/history/${code}`, {
        params: { model: currentModel, days: currentDays },
      })
      if (!r.data.series?.length) {
        setError(e => ({ ...e, [code]: `No prediction history found for ${code}` }))
        setStocks(s => s.filter(c => c !== code))
      } else {
        setData(d => ({ ...d, [code]: r.data }))
      }
    } catch {
      setError(e => ({ ...e, [code]: `Failed to load ${code}` }))
      setStocks(s => s.filter(c => c !== code))
    } finally {
      setLoading(l => ({ ...l, [code]: false }))
    }
  }, [model, days])

  // ── Add a stock ────────────────────────────────────────────────────────────
  function addStock() {
    const code = search.trim().toUpperCase()
    if (!code || stocks.includes(code) || stocks.length >= 5) return
    setSearch('')
    setStocks(s => [...s, code])
    fetchStock(code)
  }

  // ── Remove a stock ─────────────────────────────────────────────────────────
  function removeStock(code: string) {
    setStocks(s => s.filter(c => c !== code))
    setData(d => { const n = { ...d }; delete n[code]; return n })
    setError(e => { const n = { ...e }; delete n[code]; return n })
  }

  // ── Re-fetch all when model or days change ─────────────────────────────────
  function changeModel(m: string) {
    setModel(m)
    setData({})
    stocks.forEach(c => fetchStock(c, m, days))
  }

  function changeDays(d: number) {
    setDays(d)
    setData({})
    stocks.forEach(c => fetchStock(c, model, d))
  }

  // ── Build chart data ───────────────────────────────────────────────────────
  // Multi-stock mode: one line per stock × horizon (or per stock if single horizon)
  // Single-stock mode: one line per horizon

  const singleStock  = stocks.length === 1
  const singleHorizon = selectedHorizon !== null

  // Merge all dates across selected stocks
  const allDates = Array.from(
    new Set(stocks.flatMap(c => (data[c]?.series ?? []).map(p => p.date)))
  ).sort()

  // Chart series: flat list, keyed by unique name
  type ChartEntry = Record<string, string | number | null | undefined>
  const chartData: ChartEntry[] = allDates.map(date => {
    const entry: ChartEntry = { date }
    stocks.forEach(code => {
      const pt = data[code]?.series.find(p => p.date === date)
      const horizons = singleHorizon ? [selectedHorizon] : HORIZONS
      horizons.forEach(h => {
        const key = singleStock ? `h${h}` : `${code}_h${h}`
        entry[key] = pt?.[`h${h}`] ?? null
      })
    })
    return entry
  })

  // Lines to draw
  const lines: { key: string; name: string; color: string; dash: string }[] = []
  if (singleStock) {
    const horizons = singleHorizon ? [selectedHorizon] : HORIZONS
    horizons.forEach(h => {
      lines.push({ key: `h${h}`, name: `${h}d`, color: H_COLORS[h], dash: '' })
    })
  } else {
    stocks.forEach((code, si) => {
      const horizons = singleHorizon ? [selectedHorizon] : HORIZONS
      horizons.forEach((h, hi) => {
        lines.push({
          key:   `${code}_h${h}`,
          name:  `${code} ${h}d`,
          color: singleHorizon ? STOCK_COLORS[si] : H_COLORS[h],
          dash:  DASH_PATTERNS[si] ?? '',
        })
      })
    })
  }

  const anyLoading = Object.values(loading).some(Boolean)

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-900 px-6 py-5">
        <div className="max-w-7xl mx-auto flex items-center gap-3">
          <div className="p-2 bg-indigo-500/20 rounded-xl">
            <History className="w-6 h-6 text-indigo-300" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Prediction History</h1>
            <p className="text-slate-400 text-xs mt-0.5">
              Up to 60 days · compare up to 5 stocks · all horizons
            </p>
          </div>
          <span className="ml-2 px-2 py-0.5 bg-red-500/20 text-red-300 text-[10px] font-bold rounded-full border border-red-500/30">
            ADMIN ONLY
          </span>
          <a
            href="/admin/predictions"
            className="ml-auto text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            ← Back to Predictions
          </a>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-5">

        {/* Disclaimer */}
        <div className="flex items-start gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
          <span>
            <strong>Statistical models only — not investment advice.</strong> Historical predictions
            show what the model <em>predicted</em> on each past date, not necessarily what happened.
          </span>
        </div>

        {/* Controls */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
          {/* Stock search */}
          <div className="flex gap-2">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && addStock()}
                placeholder="ASX code (e.g. CBA)…"
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg text-slate-800 placeholder:text-slate-400"
                maxLength={6}
              />
            </div>
            <button
              onClick={addStock}
              disabled={!search.trim() || stocks.length >= 5}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors"
            >
              Add Stock
            </button>
            <span className="self-center text-xs text-slate-400">
              {stocks.length}/5 stocks
            </span>
          </div>

          {/* Active stock chips */}
          {stocks.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {stocks.map((code, i) => (
                <div
                  key={code}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold text-white"
                  style={{ background: STOCK_COLORS[i] }}
                >
                  {loading[code]
                    ? <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                    : null}
                  {code}
                  {data[code] && (
                    <span className="opacity-75 font-normal truncate max-w-[100px]">
                      · {data[code].company_name}
                    </span>
                  )}
                  <button onClick={() => removeStock(code)} className="ml-0.5 hover:opacity-70">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
              {stocks.length > 0 && (
                <button
                  onClick={() => { setStocks([]); setData({}); setError({}) }}
                  className="px-3 py-1 rounded-full text-xs text-slate-500 border border-slate-200 hover:bg-slate-100"
                >
                  Clear all
                </button>
              )}
            </div>
          )}

          {/* Errors */}
          {Object.entries(error).map(([code, msg]) => (
            <div key={code} className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {msg}
            </div>
          ))}

          {/* Filters row */}
          <div className="flex flex-wrap gap-3 items-center pt-1 border-t border-slate-100">
            {/* Model */}
            <div className="flex gap-1">
              {MODELS.map(m => (
                <button
                  key={m.key}
                  onClick={() => changeModel(m.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                    model === m.key
                      ? 'bg-indigo-100 text-indigo-700 ring-1 ring-inset ring-indigo-300'
                      : 'text-slate-500 hover:bg-slate-100'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>

            <div className="h-5 border-l border-slate-200" />

            {/* Days */}
            <div className="flex gap-1">
              {[7, 14, 30, 45, 60].map(d => (
                <button
                  key={d}
                  onClick={() => changeDays(d)}
                  className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                    days === d
                      ? 'bg-slate-800 text-white'
                      : 'text-slate-500 hover:bg-slate-100'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>

            <div className="h-5 border-l border-slate-200" />

            {/* Horizon filter */}
            <div className="flex gap-1 items-center">
              <span className="text-xs text-slate-500 mr-1">Show:</span>
              <button
                onClick={() => setSelectedHorizon(null)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  selectedHorizon === null
                    ? 'bg-slate-800 text-white'
                    : 'text-slate-500 hover:bg-slate-100'
                }`}
              >
                All horizons
              </button>
              {HORIZONS.map(h => (
                <button
                  key={h}
                  onClick={() => setSelectedHorizon(selectedHorizon === h ? null : h)}
                  className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-colors`}
                  style={selectedHorizon === h
                    ? { background: H_COLORS[h], color: 'white' }
                    : { color: '#64748b' }
                  }
                >
                  {h}d
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Empty state */}
        {stocks.length === 0 && (
          <div className="text-center py-16 bg-white rounded-2xl border border-slate-200">
            <History className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="font-semibold text-slate-700 mb-1">Add stocks to view history</h3>
            <p className="text-sm text-slate-500">
              Type an ASX code above (e.g. <strong>CBA</strong>) and press <kbd className="px-1.5 py-0.5 bg-slate-100 rounded text-xs">Enter</kbd>.
              <br />Add up to 5 stocks to compare their prediction trends side by side.
            </p>
          </div>
        )}

        {/* Chart */}
        {stocks.length > 0 && chartData.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-semibold text-slate-800 text-sm">
                  Predicted % Change Over Time
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Each point = what the model predicted on that date
                  {selectedHorizon ? ` for a ${selectedHorizon}-day horizon` : ' across all horizons'}
                </p>
              </div>
              <div className="flex gap-3 text-[11px] text-slate-400">
                {!singleHorizon && HORIZONS.map(h => (
                  <span key={h} className="flex items-center gap-1">
                    <span className="w-3 h-0.5 inline-block" style={{ background: H_COLORS[h] }} />
                    {h}d
                  </span>
                ))}
              </div>
            </div>

            <ResponsiveContainer width="100%" height={380}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis
                  dataKey="date"
                  tickFormatter={fmtDate}
                  tick={{ fontSize: 11, fill: '#94a3b8' }}
                  tickLine={false}
                  axisLine={{ stroke: '#e2e8f0' }}
                />
                <YAxis
                  tickFormatter={v => `${v > 0 ? '+' : ''}${v}%`}
                  tick={{ fontSize: 11, fill: '#94a3b8' }}
                  tickLine={false}
                  axisLine={false}
                  width={55}
                />
                <Tooltip
                  content={
                    <ChartTooltip
                      stocks={stocks}
                      selectedHorizon={selectedHorizon}
                      singleHorizon={singleHorizon}
                    />
                  }
                />
                <ReferenceLine y={0} stroke="#cbd5e1" strokeDasharray="4 4" />
                <Legend
                  wrapperStyle={{ fontSize: '11px', paddingTop: '12px' }}
                  formatter={(v) => <span className="text-slate-600">{v}</span>}
                />
                {lines.map(l => (
                  <Line
                    key={l.key}
                    type="monotone"
                    dataKey={l.key}
                    name={l.name}
                    stroke={l.color}
                    strokeWidth={singleHorizon ? 2.5 : 1.8}
                    strokeDasharray={l.dash}
                    dot={chartData.length <= 14}
                    activeDot={{ r: 4 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Loading skeleton */}
        {anyLoading && chartData.length === 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-8 flex justify-center">
            <div className="flex items-center gap-3 text-slate-500 text-sm">
              <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              Loading prediction history…
            </div>
          </div>
        )}

        {/* Data table */}
        {stocks.length > 0 && stocks.map((code, si) => {
          const hist = data[code]
          if (!hist?.series?.length) return null
          return (
            <div key={code} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <div
                className="px-4 py-3 border-b border-slate-100 flex items-center gap-2"
                style={{ borderLeft: `3px solid ${STOCK_COLORS[si]}` }}
              >
                <span className="font-bold text-slate-800">{code}</span>
                <span className="text-slate-500 text-sm">{hist.company_name}</span>
                <span className="ml-auto text-[11px] text-slate-400">
                  {hist.series.length} prediction dates · {hist.model} model
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50 text-slate-500 text-[11px] uppercase tracking-wide">
                      <th className="text-left px-4 py-2.5 font-semibold">Date</th>
                      <th className="text-right px-3 py-2.5 font-semibold">Price</th>
                      {(selectedHorizon ? [selectedHorizon] : HORIZONS).map(h => (
                        <th key={h} className="text-right px-3 py-2.5 font-semibold">
                          <span className="flex items-center justify-end gap-1">
                            <span
                              className="w-2 h-2 rounded-full"
                              style={{ background: H_COLORS[h] }}
                            />
                            {h}d
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...hist.series].reverse().map((pt, i) => (
                      <tr
                        key={pt.date}
                        className={`border-t border-slate-50 ${i % 2 === 0 ? '' : 'bg-slate-50/30'}`}
                      >
                        <td className="px-4 py-2 text-slate-700 font-medium">
                          {fmtDate(pt.date)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-slate-600">
                          {pt.current_price != null ? `$${pt.current_price.toFixed(3)}` : '—'}
                        </td>
                        {(selectedHorizon ? [selectedHorizon] : HORIZONS).map(h => {
                          const v = pt[`h${h}`] as number | null | undefined
                          const dir = pt[`h${h}_dir`] as string | undefined
                          return (
                            <td key={h} className="px-3 py-2 text-right">
                              <span className={`font-mono ${pctColor(v)}`}>
                                {fmtPct(v)}
                              </span>
                              {dir === 'bullish' && (
                                <TrendingUp className="w-3 h-3 text-emerald-400 inline ml-1" />
                              )}
                              {dir === 'bearish' && (
                                <TrendingDown className="w-3 h-3 text-red-400 inline ml-1" />
                              )}
                              {dir === 'neutral' && (
                                <Minus className="w-3 h-3 text-gray-300 inline ml-1" />
                              )}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        })}

        {/* Horizon legend */}
        {stocks.length > 0 && (
          <div className="flex flex-wrap gap-2 pb-2">
            {HORIZONS.map(h => (
              <div
                key={h}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white rounded-lg border border-slate-200 text-xs text-slate-600"
              >
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: H_COLORS[h] }} />
                <strong>{h}d</strong> horizon
              </div>
            ))}
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 rounded-lg border border-amber-200 text-xs text-amber-700 ml-auto">
              <Info className="w-3 h-3" />
              Longer horizons (30d–50d) are speculative
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
