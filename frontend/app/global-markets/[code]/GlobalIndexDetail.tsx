'use client'
import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { ArrowLeft, RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, CartesianGrid,
} from 'recharts'
import { GlobalIndexDetail, getGlobalIndexDetail } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Config ────────────────────────────────────────────────────────────────────

const PERIOD_DAYS: Record<string, number> = { '1M': 30, '3M': 90, '6M': 180, '1Y': 365, '2Y': 730 }

const COUNTRY_FLAGS: Record<string, string> = {
  'United States': '🇺🇸', 'United Kingdom': '🇬🇧', 'Germany': '🇩🇪',
  'France': '🇫🇷', 'Japan': '🇯🇵', 'Hong Kong': '🇭🇰',
  'China': '🇨🇳', 'South Korea': '🇰🇷',
}

const ALL_INDICES = ['SP500', 'NDX100', 'DJIA', 'FTSE100', 'DAX', 'CAC40', 'NKY225', 'HSI', 'SHCOMP', 'KOSPI']
const COMPARE_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#f97316', '#06b6d4', '#ec4899']

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null) {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%'
}

function fmtPrice(v: number | null) {
  if (v == null) return '—'
  return v >= 1000
    ? v.toLocaleString('en-AU', { maximumFractionDigits: 0 })
    : v.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function retColor(v: number | null) {
  if (v == null) return 'text-slate-400'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-400'
}

function retBg(v: number | null) {
  if (v == null) return 'bg-slate-700/50 text-slate-400'
  const p = v * 100
  if (p >= 1)  return 'bg-emerald-500/20 text-emerald-400'
  if (p >= 0)  return 'bg-emerald-900/30 text-emerald-500'
  if (p >= -1) return 'bg-red-900/30 text-red-400'
  return 'bg-red-500/20 text-red-400'
}

// ── Price Chart ───────────────────────────────────────────────────────────────

function PriceChart({ code, initialHistory }: { code: string; initialHistory: { date: string; close: number | null }[] }) {
  const [period, setPeriod]   = useState('1Y')
  const [history, setHistory] = useState(initialHistory)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    getGlobalIndexDetail(code, PERIOD_DAYS[period])
      .then(d => setHistory(d.history))
      .finally(() => setLoading(false))
  }, [code, period])

  const data = history.filter(h => h.close != null).map(h => ({ date: h.date, close: h.close as number }))
  const minY = data.length ? Math.min(...data.map(h => h.close)) * 0.98 : 0
  const maxY = data.length ? Math.max(...data.map(h => h.close)) * 1.02 : 100
  const isUp = data.length >= 2 ? data[data.length - 1].close >= data[0].close : true
  const lineColor = isUp ? '#10b981' : '#ef4444'

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-200">Price History</h2>
        <div className="flex gap-1">
          {Object.keys(PERIOD_DAYS).map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={cn('px-3 py-1 text-xs rounded-lg font-medium transition-colors',
                period === p ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              )}
            >{p}</button>
          ))}
        </div>
      </div>
      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <RefreshCw className="w-5 h-5 text-slate-500 animate-spin" />
        </div>
      ) : data.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-slate-500 text-sm">No history available</div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tickFormatter={d => new Date(d).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}
              tick={{ fontSize: 11, fill: '#64748b' }} interval="preserveStartEnd" />
            <YAxis domain={[minY, maxY]} tickFormatter={v => fmtPrice(v)} tick={{ fontSize: 11, fill: '#64748b' }} width={70} />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: 8 }}
              labelStyle={{ color: '#94a3b8', fontSize: 11 }}
              itemStyle={{ color: lineColor }}
              formatter={(v: unknown) => [fmtPrice(v as number), 'Close']}
              labelFormatter={l => new Date(l).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
            />
            <Line type="monotone" dataKey="close" stroke={lineColor} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Compare Chart ─────────────────────────────────────────────────────────────

function CompareChart({ currentCode }: { currentCode: string }) {
  const [selected, setSelected] = useState<string[]>([])
  const [period,   setPeriod]   = useState('1Y')
  const [series,   setSeries]   = useState<Record<string, { date: string; value: number }[]>>({})
  const [loading,  setLoading]  = useState(false)

  const allSelected = [currentCode, ...selected]

  useEffect(() => {
    setLoading(true)
    Promise.all(allSelected.map(c =>
      getGlobalIndexDetail(c, PERIOD_DAYS[period]).then(d => ({ code: c, history: d.history }))
    )).then(results => {
      const map: Record<string, { date: string; value: number }[]> = {}
      results.forEach(({ code, history }) => {
        const valid = history.filter(h => h.close != null)
        if (!valid.length) return
        const base = valid[0].close as number
        map[code] = valid.map(h => ({ date: h.date, value: Math.round(((h.close as number) / base) * 1000) / 10 }))
      })
      setSeries(map)
    }).finally(() => setLoading(false))
  }, [selected, period, currentCode]) // eslint-disable-line react-hooks/exhaustive-deps

  const dates = useMemo(() => {
    const s = new Set<string>()
    Object.values(series).forEach(arr => arr.forEach(p => s.add(p.date)))
    return Array.from(s).sort()
  }, [series])

  const chartData = dates.map(date => {
    const pt: Record<string, unknown> = { date }
    allSelected.forEach(c => { const m = series[c]?.find(p => p.date === date); if (m) pt[c] = m.value })
    return pt
  })

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700/50 p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-200">Compare (rebased to 100)</h2>
        <div className="flex gap-1">
          {Object.keys(PERIOD_DAYS).map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={cn('px-2 py-1 text-xs rounded font-medium', period === p ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400')}
            >{p}</button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-2 mb-4">
        {ALL_INDICES.filter(c => c !== currentCode).map(c => (
          <button key={c} onClick={() => setSelected(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])}
            className={cn('px-2.5 py-1 text-xs font-medium rounded-lg border transition-colors',
              selected.includes(c) ? 'bg-blue-600 text-white border-blue-600' : 'bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-500'
            )}
          >{c}</button>
        ))}
      </div>
      {loading ? (
        <div className="h-52 flex items-center justify-center"><RefreshCw className="w-5 h-5 text-slate-500 animate-spin" /></div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tickFormatter={d => new Date(d).toLocaleDateString('en-AU', { month: 'short', year: '2-digit' })}
              tick={{ fontSize: 11, fill: '#64748b' }} interval="preserveStartEnd" />
            <YAxis tickFormatter={v => `${v}`} tick={{ fontSize: 11, fill: '#64748b' }} width={40} />
            <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: 8 }}
              labelStyle={{ color: '#94a3b8', fontSize: 11 }}
              formatter={(v: unknown, name: unknown) => [`${(v as number).toFixed(1)}`, name as string]}
              labelFormatter={l => new Date(l).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
            />
            {allSelected.map((c, i) => (
              <Line key={c} type="monotone" dataKey={c} stroke={COMPARE_COLORS[i % COMPARE_COLORS.length]} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function GlobalIndexDetail({ initialData, code }: { initialData: GlobalIndexDetail; code: string }) {
  const [data, setData]         = useState<GlobalIndexDetail>(initialData)
  const [refreshing, setRefreshing] = useState(false)

  function refresh() {
    setRefreshing(true)
    getGlobalIndexDetail(code, 365).then(setData).finally(() => setRefreshing(false))
  }

  const flag = COUNTRY_FLAGS[data.country ?? ''] ?? '🌐'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Hero */}
      <div className="bg-gradient-to-b from-slate-800 to-slate-900 border-b border-slate-700/50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-center justify-between mb-5">
            <Link href="/global-markets" className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors">
              <ArrowLeft className="w-4 h-4" /> Global Markets
            </Link>
            <button onClick={refresh}
              className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors"
            >
              <RefreshCw className={cn('w-4 h-4', refreshing && 'animate-spin')} /> Refresh
            </button>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <span className="text-3xl leading-none">{flag}</span>
                <div>
                  <h1 className="text-2xl font-bold text-white">{data.index_name}</h1>
                  <p className="text-slate-400 text-sm">{data.country} · {data.currency} · {data.region}</p>
                </div>
              </div>
              {data.price_date && (
                <p className="text-slate-500 text-xs mt-1">As of {data.price_date}</p>
              )}
            </div>
            <div className="sm:text-right">
              <div className="text-3xl font-bold text-white">{fmtPrice(data.close_price)}</div>
              <span className={cn('inline-block text-sm font-semibold px-2.5 py-1 rounded mt-1', retBg(data.return_1d))}>
                {fmtPct(data.return_1d)} today
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* Returns strip */}
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-2">
          {[
            { label: '1D',  v: data.return_1d },
            { label: '1W',  v: data.return_1w },
            { label: '1M',  v: data.return_1m },
            { label: '3M',  v: data.return_3m },
            { label: '6M',  v: data.return_6m },
            { label: '1Y',  v: data.return_1y },
            { label: 'YTD', v: data.return_ytd },
          ].map(({ label, v }) => (
            <div key={label} className="bg-slate-900 border border-slate-700/50 rounded-xl p-3 text-center">
              <p className="text-[10px] text-slate-500 mb-1">{label}</p>
              <p className={cn('text-sm font-bold', retColor(v))}>{fmtPct(v)}</p>
            </div>
          ))}
        </div>

        {/* 52W range */}
        {data.high_52w != null && data.low_52w != null && data.close_price != null && (
          <div className="bg-slate-900 border border-slate-700/50 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-slate-200 mb-4">52-Week Range</h2>
            <div className="flex justify-between text-xs text-slate-400 mb-2">
              <span>Low {fmtPrice(data.low_52w)}</span>
              <span>Current {fmtPrice(data.close_price)}</span>
              <span>High {fmtPrice(data.high_52w)}</span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-red-500 via-amber-400 to-emerald-500 rounded-full"
                style={{ width: `${Math.min(100, Math.max(2, ((data.close_price - data.low_52w) / (data.high_52w - data.low_52w)) * 100))}%` }}
              />
            </div>
          </div>
        )}

        {/* Chart */}
        <PriceChart code={code} initialHistory={data.history} />

        {/* Compare */}
        <CompareChart currentCode={code} />
      </div>
    </div>
  )
}
