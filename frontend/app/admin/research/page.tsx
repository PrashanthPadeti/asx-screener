'use client'

/**
 * ASX Research Assistant — Admin-only investment analysis tool.
 *
 * Mode 1 — Historical Backtester   ("If I had invested $X in A vs B…")
 * Mode 2 — Stock Comparator        (side-by-side metric table)
 * Mode 3 — AI Research Chat        (Claude, ASX-only, no buy/sell advice)
 */

import { useState, useRef, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { api } from '@/lib/api'
import { FlaskConical, TrendingUp, BarChart2, MessageSquare,
         Send, RefreshCw, Plus, X, AlertTriangle } from 'lucide-react'

// ── Colour palette for up to 4 stocks ──────────────────────────────────────
const STOCK_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444']

// ── Preset period helpers ───────────────────────────────────────────────────
function offsetDate(years: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}
const today = () => new Date().toISOString().slice(0, 10)

// ── Formatters ──────────────────────────────────────────────────────────────
function fmtVal(val: number | null | undefined, fmt: string): string {
  if (val == null) return '—'
  switch (fmt) {
    case 'price':   return `$${Number(val).toFixed(3)}`
    case 'dollar':  return `$${Number(val).toFixed(2)}`
    case 'pct':     return `${Number(val).toFixed(2)}%`
    case 'x':       return `${Number(val).toFixed(2)}x`
    case 'number':  return Number(val).toFixed(1)
    default:        return String(val)
  }
}

function signClass(v: number | null | undefined) {
  if (v == null) return 'text-gray-500'
  return v > 0 ? 'text-emerald-600' : v < 0 ? 'text-red-500' : 'text-gray-500'
}

function fmtAUD(n: number) {
  return new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD', maximumFractionDigits: 0 }).format(n)
}

// ── Disclaimer Banner ────────────────────────────────────────────────────────
function Disclaimer() {
  return (
    <div className="flex items-start gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
      <span>
        <strong>Not financial advice.</strong> This tool is for analysis and educational purposes only.
        Past performance is not indicative of future returns. Always consult a licensed financial
        adviser (AFSL holder) before making investment decisions.
      </span>
    </div>
  )
}

// ── Tag input: enter ASX codes ───────────────────────────────────────────────
function CodeInput({
  codes, onChange, max = 4, placeholder = 'e.g. BHP',
}: {
  codes: string[]
  onChange: (c: string[]) => void
  max?: number
  placeholder?: string
}) {
  const [input, setInput] = useState('')

  function add(raw: string) {
    const code = raw.trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
    if (!code || codes.includes(code) || codes.length >= max) return
    onChange([...codes, code])
    setInput('')
  }

  return (
    <div className="flex flex-wrap gap-2 border border-gray-200 rounded-lg px-3 py-2 bg-white min-h-[42px] items-center">
      {codes.map(c => (
        <span key={c} className="flex items-center gap-1 bg-blue-100 text-blue-800 text-xs font-bold px-2 py-0.5 rounded-full">
          {c}
          <button onClick={() => onChange(codes.filter(x => x !== c))} className="hover:text-red-600">
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      {codes.length < max && (
        <input
          className="flex-1 min-w-[80px] outline-none text-sm text-gray-700 placeholder-gray-400"
          placeholder={codes.length === 0 ? placeholder : `Add code…`}
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ' ' || e.key === ',') {
              e.preventDefault()
              add(input)
            }
          }}
          onBlur={() => { if (input) add(input) }}
        />
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// MODE 1 — Historical Backtester
// ════════════════════════════════════════════════════════════════════════════

type BacktestStock = {
  code: string
  company_name: string
  error?: string
  buy_price: number
  sell_price: number
  actual_start_date: string
  actual_end_date: string
  shares_purchased: number
  invested: number
  price_end_value: number
  dividends_received: number
  franking_credits: number
  total_end_value: number
  price_return_pct: number
  total_return_pct: number
  cagr_price: number
  cagr_total: number
  div_events: { ex_date: string; amount_ps: number; franking_pct: number; cash: number }[]
  chart: { date: string; price_value: number; total_value: number }[]
}

type BacktestResult = {
  amount: number
  start_date: string
  end_date: string
  years_held: number
  results: BacktestStock[]
}

const PERIOD_PRESETS = [
  { label: '1Y', years: 1 },
  { label: '3Y', years: 3 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: 10 },
  { label: 'Custom', years: 0 },
]

function BacktestMode() {
  const [codes, setCodes]           = useState<string[]>(['BOQ', 'NAB'])
  const [amount, setAmount]         = useState('10000')
  const [period, setPeriod]         = useState('5Y')
  const [startDate, setStartDate]   = useState(offsetDate(5))
  const [endDate, setEndDate]       = useState(today())
  const [inclDiv, setInclDiv]       = useState(true)
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [result, setResult]         = useState<BacktestResult | null>(null)
  const [showDivs, setShowDivs]     = useState<string | null>(null)

  function onPeriodChange(p: string) {
    setPeriod(p)
    const preset = PERIOD_PRESETS.find(x => x.label === p)
    if (preset && preset.years > 0) {
      setStartDate(offsetDate(preset.years))
      setEndDate(today())
    }
  }

  async function run() {
    if (codes.length < 1) { setError('Add at least one ASX code'); return }
    const amt = parseFloat(amount)
    if (isNaN(amt) || amt < 100) { setError('Minimum investment is $100'); return }
    setLoading(true); setError(null); setResult(null)
    try {
      const { data } = await api.post('/api/v1/research/backtest', {
        codes,
        amount: amt,
        start_date: startDate,
        end_date:   endDate,
        include_dividends: inclDiv,
      })
      setResult(data)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  // Merge chart data across all stocks into one array keyed by date
  const mergedChart = (() => {
    if (!result) return []
    const dateMap: Record<string, Record<string, number>> = {}
    result.results.filter(r => !r.error).forEach(r => {
      r.chart.forEach(p => {
        if (!dateMap[p.date]) dateMap[p.date] = {}
        dateMap[p.date][`${r.code}_total`] = p.total_value
        dateMap[p.date][`${r.code}_price`] = p.price_value
      })
    })
    return Object.entries(dateMap)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, vals]) => ({ date, ...vals }))
  })()

  const validResults = result?.results.filter(r => !r.error) ?? []

  return (
    <div className="space-y-5">
      <Disclaimer />

      {/* ── Inputs ── */}
      <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm space-y-4">
        <h3 className="text-sm font-bold text-gray-700">Configure Backtest</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1.5">
              ASX Stocks (up to 4)
            </label>
            <CodeInput codes={codes} onChange={setCodes} max={4} placeholder="e.g. BOQ" />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1.5">
              Investment Amount (A$)
            </label>
            <input
              type="number"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400"
              placeholder="10000"
            />
          </div>
        </div>

        <div>
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1.5">
            Period
          </label>
          <div className="flex items-center gap-2 flex-wrap">
            {PERIOD_PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => onPeriodChange(p.label)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                  period === p.label
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {p.label}
              </button>
            ))}
            {period === 'Custom' && (
              <div className="flex items-center gap-2 ml-2">
                <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                  className="border border-gray-200 rounded px-2 py-1 text-xs outline-none focus:border-blue-400" />
                <span className="text-xs text-gray-400">→</span>
                <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                  className="border border-gray-200 rounded px-2 py-1 text-xs outline-none focus:border-blue-400" />
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <input type="checkbox" id="inclDiv" checked={inclDiv}
            onChange={e => setInclDiv(e.target.checked)}
            className="rounded border-gray-300 text-blue-600" />
          <label htmlFor="inclDiv" className="text-xs text-gray-600 font-medium">
            Include dividends & franking credits
          </label>
        </div>

        {error && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded px-3 py-2">{error}</p>
        )}

        <button
          onClick={run}
          disabled={loading || codes.length === 0}
          className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50
                     text-white text-sm font-bold rounded-lg transition-colors"
        >
          {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
          {loading ? 'Running…' : 'Run Backtest'}
        </button>
      </div>

      {/* ── Results ── */}
      {result && validResults.length > 0 && (
        <div className="space-y-4">

          {/* Summary cards */}
          <div className={`grid gap-4 ${validResults.length === 1 ? 'grid-cols-1 max-w-sm' : `grid-cols-1 sm:grid-cols-${Math.min(validResults.length, 2)} lg:grid-cols-${validResults.length}`}`}>
            {validResults.map((r, i) => {
              const color  = STOCK_COLORS[i % STOCK_COLORS.length]
              const winner = validResults.length > 1 &&
                r.total_end_value === Math.max(...validResults.map(x => x.total_end_value))
              return (
                <div key={r.code}
                  className={`relative bg-white border rounded-xl p-5 shadow-sm overflow-hidden
                    ${winner ? 'border-emerald-300 ring-1 ring-emerald-200' : 'border-gray-100'}`}
                >
                  {winner && (
                    <span className="absolute top-2 right-2 text-[10px] bg-emerald-100 text-emerald-700 font-bold px-2 py-0.5 rounded-full">
                      BEST RETURN
                    </span>
                  )}
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-3 h-3 rounded-full shrink-0" style={{ background: color }} />
                    <span className="font-black text-gray-900 text-lg">{r.code}</span>
                    <span className="text-xs text-gray-400 truncate">{r.company_name}</span>
                  </div>

                  <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                    <div>
                      <p className="text-gray-400 uppercase tracking-wide">Invested</p>
                      <p className="font-bold text-gray-800">{fmtAUD(r.invested)}</p>
                    </div>
                    <div>
                      <p className="text-gray-400 uppercase tracking-wide">Final Value</p>
                      <p className={`font-bold text-lg ${signClass(r.total_end_value - r.invested)}`}>
                        {fmtAUD(r.total_end_value)}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 uppercase tracking-wide">Price Return</p>
                      <p className={`font-semibold ${signClass(r.price_return_pct)}`}>
                        {r.price_return_pct > 0 ? '+' : ''}{r.price_return_pct.toFixed(2)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 uppercase tracking-wide">Total Return</p>
                      <p className={`font-bold text-base ${signClass(r.total_return_pct)}`}>
                        {r.total_return_pct > 0 ? '+' : ''}{r.total_return_pct.toFixed(2)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 uppercase tracking-wide">CAGR (total)</p>
                      <p className={`font-semibold ${signClass(r.cagr_total)}`}>
                        {r.cagr_total > 0 ? '+' : ''}{r.cagr_total.toFixed(2)}% p.a.
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-400 uppercase tracking-wide">Dividends</p>
                      <p className="font-semibold text-indigo-600">{fmtAUD(r.dividends_received)}</p>
                    </div>
                    {r.franking_credits > 0 && (
                      <div>
                        <p className="text-gray-400 uppercase tracking-wide">Franking Credits</p>
                        <p className="font-semibold text-purple-600">{fmtAUD(r.franking_credits)}</p>
                      </div>
                    )}
                    <div>
                      <p className="text-gray-400 uppercase tracking-wide">Buy → Sell</p>
                      <p className="text-gray-600">${r.buy_price.toFixed(3)} → ${r.sell_price.toFixed(3)}</p>
                    </div>
                  </div>

                  {r.div_events.length > 0 && (
                    <button
                      onClick={() => setShowDivs(showDivs === r.code ? null : r.code)}
                      className="mt-3 text-[10px] text-blue-600 hover:underline"
                    >
                      {showDivs === r.code ? '▲ Hide' : '▼ Show'} {r.div_events.length} dividend payments
                    </button>
                  )}
                  {showDivs === r.code && (
                    <div className="mt-2 max-h-40 overflow-y-auto border border-gray-100 rounded-lg">
                      <table className="w-full text-[10px]">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-2 py-1 text-left text-gray-500">Ex-Date</th>
                            <th className="px-2 py-1 text-right text-gray-500">$/Share</th>
                            <th className="px-2 py-1 text-right text-gray-500">Franking</th>
                            <th className="px-2 py-1 text-right text-gray-500">Cash Received</th>
                          </tr>
                        </thead>
                        <tbody>
                          {r.div_events.map((d, di) => (
                            <tr key={di} className="border-t border-gray-50">
                              <td className="px-2 py-1 text-gray-600">{d.ex_date}</td>
                              <td className="px-2 py-1 text-right text-gray-700">${d.amount_ps.toFixed(4)}</td>
                              <td className="px-2 py-1 text-right text-gray-700">{d.franking_pct.toFixed(0)}%</td>
                              <td className="px-2 py-1 text-right font-medium text-indigo-700">{fmtAUD(d.cash)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Chart */}
          {mergedChart.length > 1 && (
            <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">
                Portfolio Value Over Time (A$) — Total Return incl. Dividends
              </h4>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={mergedChart} margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(0, 7)} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                  <Tooltip
                    formatter={(v: unknown, name: unknown) => [fmtAUD(Number(v)), String(name).replace('_total', ' (total)').replace('_price', ' (price only)')]}
                    labelFormatter={(l: unknown) => `Date: ${l}`}
                    contentStyle={{ fontSize: 11 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {validResults.map((r, i) => (
                    <Line
                      key={`${r.code}_total`}
                      type="monotone"
                      dataKey={`${r.code}_total`}
                      stroke={STOCK_COLORS[i % STOCK_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                      name={`${r.code} total return`}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              <p className="text-[10px] text-gray-400 mt-2 text-center">
                Period: {result.start_date} → {result.end_date} ({result.years_held.toFixed(1)} years)
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// MODE 2 — Stock Comparator
// ════════════════════════════════════════════════════════════════════════════

type CompareMetric = { col: string; label: string; format: string; section: string; higher_better: boolean | null }
type CompareData = {
  codes: string[]
  stocks: Record<string, Record<string, unknown>>
  metrics: CompareMetric[]
}

const SECTION_COLORS: Record<string, string> = {
  Price:      'bg-slate-50 text-slate-600',
  Valuation:  'bg-blue-50 text-blue-700',
  Growth:     'bg-green-50 text-green-700',
  Quality:    'bg-purple-50 text-purple-700',
  Dividends:  'bg-yellow-50 text-yellow-700',
  Returns:    'bg-teal-50 text-teal-700',
  Technical:  'bg-gray-50 text-gray-600',
}

function ComparatorMode() {
  const [codes, setCodes]     = useState<string[]>(['CBA', 'WBC', 'ANZ', 'NAB'])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const [data, setData]       = useState<CompareData | null>(null)

  async function run() {
    if (codes.length < 2) { setError('Add at least 2 ASX codes'); return }
    setLoading(true); setError(null)
    try {
      const { data: d } = await api.post('/api/v1/research/compare', { codes })
      setData(d)
    } catch (e: unknown) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  // Group metrics by section
  const sections = data
    ? Array.from(new Set(data.metrics.map(m => m.section)))
    : []

  // Find best/worst value per metric row (for highlighting)
  function getBest(metric: CompareMetric, validCodes: string[]): string | null {
    if (metric.higher_better === null) return null
    const vals = validCodes.map(c => {
      const v = data?.stocks[c]?.[metric.col]
      return v != null ? { code: c, v: parseFloat(String(v)) } : null
    }).filter(Boolean) as { code: string; v: number }[]
    if (vals.length < 2) return null
    return metric.higher_better
      ? vals.reduce((a, b) => b.v > a.v ? b : a).code
      : vals.reduce((a, b) => b.v < a.v ? b : a).code
  }

  const validCodes = data ? data.codes.filter(c => data.stocks[c]) : []

  return (
    <div className="space-y-5">
      <Disclaimer />

      <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm space-y-4">
        <h3 className="text-sm font-bold text-gray-700">Compare Stocks (up to 6)</h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div className="md:col-span-2">
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1.5">
              ASX Codes
            </label>
            <CodeInput codes={codes} onChange={setCodes} max={6} placeholder="e.g. BHP" />
          </div>
          <button
            onClick={run}
            disabled={loading || codes.length < 2}
            className="flex items-center justify-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700
                       disabled:opacity-50 text-white text-sm font-bold rounded-lg transition-colors"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <BarChart2 className="w-4 h-4" />}
            {loading ? 'Loading…' : 'Compare'}
          </button>
        </div>
        {error && <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded px-3 py-2">{error}</p>}
      </div>

      {data && validCodes.length > 0 && (
        <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden">

          {/* Header row */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-900 text-white">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 w-40 sticky left-0 bg-slate-900">Metric</th>
                  {validCodes.map((c, i) => (
                    <th key={c} className="px-4 py-3 text-center min-w-[120px]">
                      <div className="flex flex-col items-center gap-0.5">
                        <div className="flex items-center gap-1.5">
                          <div className="w-2.5 h-2.5 rounded-full" style={{ background: STOCK_COLORS[i % STOCK_COLORS.length] }} />
                          <span className="font-black text-base">{c}</span>
                        </div>
                        <span className="text-[10px] text-slate-400 font-normal truncate max-w-[110px]">
                          {(data.stocks[c]?.company_name as string | null)?.split(' ').slice(0, 3).join(' ')}
                        </span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {sections.map(section => {
                  const sectionMetrics = data.metrics.filter(m => m.section === section)
                  const headerStyle = SECTION_COLORS[section] || 'bg-gray-50 text-gray-600'
                  return [
                    <tr key={`section-${section}`}>
                      <td colSpan={validCodes.length + 1}
                        className={`px-4 py-2 text-[10px] font-bold uppercase tracking-widest border-y border-gray-100 ${headerStyle}`}>
                        {section}
                      </td>
                    </tr>,
                    ...sectionMetrics.map((metric, mi) => {
                      const bestCode = getBest(metric, validCodes)
                      return (
                        <tr key={metric.col}
                          className={`border-b border-gray-50 ${mi % 2 === 0 ? '' : 'bg-gray-50/40'} hover:bg-blue-50/30`}>
                          <td className="px-4 py-2.5 text-xs text-gray-600 font-medium sticky left-0 bg-white border-r border-gray-50">
                            {metric.label}
                          </td>
                          {validCodes.map(c => {
                            const raw = data.stocks[c]?.[metric.col]
                            const isBest = bestCode === c
                            const numVal = raw != null ? parseFloat(String(raw)) : null
                            const formatted = fmtVal(numVal, metric.format)
                            const isSign = ['pct', 'dollar'].includes(metric.format)

                            return (
                              <td key={c}
                                className={`px-4 py-2.5 text-center text-xs font-semibold ${
                                  isBest ? 'text-emerald-700 bg-emerald-50' :
                                  isSign && numVal != null ? signClass(numVal) : 'text-gray-700'
                                }`}>
                                {isBest && <span className="mr-1 text-emerald-500">✦</span>}
                                {formatted}
                              </td>
                            )
                          })}
                        </tr>
                      )
                    }),
                  ]
                })}
              </tbody>
            </table>
          </div>

          <p className="text-[10px] text-gray-400 px-4 py-2.5 border-t border-gray-100">
            ✦ = best value for this metric among compared stocks
          </p>
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// MODE 3 — AI Research Chat
// ════════════════════════════════════════════════════════════════════════════

type Message = { role: 'user' | 'assistant'; content: string }

const EXAMPLE_QUESTIONS = [
  'If I had invested $10,000 in BOQ and NAB 5 years ago, which would have given more profit?',
  'Compare the dividend yield and franking credits of CBA, WBC, ANZ and NAB',
  'What does a high P/E ratio mean for a mining company like BHP?',
  'Explain the Piotroski F-Score and what a score of 8 means',
  'What sectors on the ASX typically have the highest dividend yields?',
  'What are the key risks of investing in small-cap ASX stocks?',
]

function ChatMode() {
  const [messages, setMessages]   = useState<Message[]>([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send(question?: string) {
    const q = (question ?? input).trim()
    if (!q || loading) return
    setInput('')
    setError(null)

    const newMessages: Message[] = [...messages, { role: 'user', content: q }]
    setMessages(newMessages)
    setLoading(true)

    try {
      const { data } = await api.post('/api/v1/research/ask', {
        question: q,
        history:  messages.slice(-10),
      })
      setMessages([...newMessages, { role: 'assistant', content: data.answer }])
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'AI service error — please try again')
      setMessages(newMessages)   // leave user message visible
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  // Simple markdown rendering (bold, headers, lists, divider)
  function renderMarkdown(text: string) {
    return text
      .split('\n')
      .map((line, i) => {
        if (line.startsWith('### ')) return <h4 key={i} className="font-bold text-gray-800 mt-2 mb-0.5 text-sm">{line.slice(4)}</h4>
        if (line.startsWith('## '))  return <h3 key={i} className="font-bold text-gray-800 mt-3 mb-1">{line.slice(3)}</h3>
        if (line.startsWith('---'))  return <hr key={i} className="border-amber-200 my-2" />
        if (line.startsWith('- ') || line.startsWith('* ')) {
          const content = line.slice(2)
          return (
            <div key={i} className="flex items-start gap-1.5 my-0.5">
              <span className="text-blue-400 mt-0.5 shrink-0">•</span>
              <span dangerouslySetInnerHTML={{ __html: boldify(content) }} />
            </div>
          )
        }
        if (line.trim() === '') return <div key={i} className="h-1.5" />
        return <p key={i} className="leading-relaxed" dangerouslySetInnerHTML={{ __html: boldify(line) }} />
      })
  }

  function boldify(s: string) {
    return s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  }

  return (
    <div className="space-y-4">
      <Disclaimer />

      {/* Chat window */}
      <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden flex flex-col"
        style={{ minHeight: 480 }}>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4" style={{ maxHeight: 560 }}>

          {messages.length === 0 && (
            <div className="text-center py-8">
              <div className="w-12 h-12 bg-blue-50 rounded-full flex items-center justify-center mx-auto mb-3">
                <MessageSquare className="w-6 h-6 text-blue-500" />
              </div>
              <p className="text-sm font-semibold text-gray-700 mb-1">ASX Research Assistant</p>
              <p className="text-xs text-gray-400 mb-6 max-w-sm mx-auto">
                Ask any question about ASX stocks, metrics, or investment analysis.
                For education and research only — not financial advice.
              </p>
              <div className="space-y-2 max-w-lg mx-auto text-left">
                <p className="text-[10px] text-gray-400 uppercase tracking-widest font-semibold px-1">Example questions</p>
                {EXAMPLE_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => send(q)}
                    className="w-full text-left text-xs text-gray-600 hover:text-blue-700
                               border border-gray-100 hover:border-blue-200 hover:bg-blue-50/30
                               rounded-lg px-3 py-2.5 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-sm'
                  : 'bg-gray-50 border border-gray-100 text-gray-700 rounded-bl-sm'
              }`}>
                {msg.role === 'user'
                  ? <p className="leading-relaxed">{msg.content}</p>
                  : <div className="space-y-0.5">{renderMarkdown(msg.content)}</div>
                }
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-50 border border-gray-100 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex items-center gap-1.5">
                  {[0,1,2].map(d => (
                    <div key={d} className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"
                      style={{ animationDelay: `${d * 0.15}s` }} />
                  ))}
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="flex justify-center">
              <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                {error}
              </p>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        <div className="border-t border-gray-100 p-4 flex items-end gap-3">
          {messages.length > 0 && (
            <button
              onClick={() => { setMessages([]); setError(null) }}
              className="shrink-0 p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
              title="Clear chat"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
          <textarea
            ref={inputRef}
            rows={2}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about ASX stocks, metrics, or investment analysis… (Enter to send, Shift+Enter for new line)"
            className="flex-1 text-sm border border-gray-200 rounded-xl px-3 py-2.5 outline-none
                       focus:border-blue-400 resize-none placeholder-gray-400"
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || loading}
            className="shrink-0 p-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40
                       text-white rounded-xl transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Root Page
// ════════════════════════════════════════════════════════════════════════════

type Mode = 'backtest' | 'compare' | 'chat'

const MODES: { id: Mode; label: string; icon: React.ReactNode; desc: string }[] = [
  {
    id:    'backtest',
    label: 'Historical Backtester',
    icon:  <TrendingUp className="w-5 h-5" />,
    desc:  'If I had invested $X in A vs B…',
  },
  {
    id:    'compare',
    label: 'Stock Comparator',
    icon:  <BarChart2 className="w-5 h-5" />,
    desc:  'Side-by-side metric comparison',
  },
  {
    id:    'chat',
    label: 'Research Chat',
    icon:  <MessageSquare className="w-5 h-5" />,
    desc:  'AI-powered ASX research Q&A',
  },
]

export default function ResearchPage() {
  const [mode, setMode] = useState<Mode>('backtest')

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">

      {/* Page header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center shrink-0">
          <FlaskConical className="w-5 h-5 text-blue-600" />
        </div>
        <div>
          <h1 className="text-xl font-black text-gray-900">Research Assistant</h1>
          <p className="text-sm text-gray-400">
            ASX investment analysis tools — for education and research only
          </p>
        </div>
        <span className="ml-auto text-xs bg-red-100 text-red-700 font-bold px-2.5 py-1 rounded-full border border-red-200">
          Admin Preview
        </span>
      </div>

      {/* Mode selector */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {MODES.map(m => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            className={`flex items-start gap-3 p-4 rounded-xl border text-left transition-all ${
              mode === m.id
                ? 'bg-blue-600 border-blue-600 text-white shadow-md shadow-blue-200'
                : 'bg-white border-gray-200 text-gray-700 hover:border-blue-300 hover:bg-blue-50/30'
            }`}
          >
            <div className={`shrink-0 mt-0.5 ${mode === m.id ? 'text-blue-200' : 'text-blue-500'}`}>
              {m.icon}
            </div>
            <div>
              <p className={`text-sm font-bold ${mode === m.id ? 'text-white' : 'text-gray-800'}`}>
                {m.label}
              </p>
              <p className={`text-xs mt-0.5 ${mode === m.id ? 'text-blue-200' : 'text-gray-400'}`}>
                {m.desc}
              </p>
            </div>
          </button>
        ))}
      </div>

      {/* Active mode */}
      {mode === 'backtest' && <BacktestMode />}
      {mode === 'compare'  && <ComparatorMode />}
      {mode === 'chat'     && <ChatMode />}
    </div>
  )
}
