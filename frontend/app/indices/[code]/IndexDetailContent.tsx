'use client'
import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import {
  ArrowLeft, TrendingUp, TrendingDown, Minus,
  Info, RefreshCw, ChevronUp, ChevronDown,
  Search, ExternalLink, Download, Bell, Bookmark,
} from 'lucide-react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, CartesianGrid, PieChart, Pie, Cell, BarChart, Bar,
  Legend,
} from 'recharts'
import {
  IndexDetail, IndexConstituent, IndexSectorBreakdown,
  getIndexHistory, getIndexDetail,
} from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Constants ─────────────────────────────────────────────────────────────────

const SECTOR_COLORS: Record<string, string> = {
  'Financials':             '#3b82f6',
  'Materials':              '#f59e0b',
  'Health Care':            '#10b981',
  'Consumer Staples':       '#8b5cf6',
  'Consumer Discretionary': '#f97316',
  'Industrials':            '#06b6d4',
  'Energy':                 '#ef4444',
  'Information Technology': '#6366f1',
  'Communication Services': '#ec4899',
  'Real Estate':            '#84cc16',
  'Utilities':              '#14b8a6',
  'Other':                  '#94a3b8',
}

const COMPARE_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#f97316', '#06b6d4', '#ec4899', '#84cc16', '#94a3b8',
]

const ALL_INDICES = ['ASX20', 'ASX50', 'ASX100', 'ASX200', 'ASX300', 'AXJO', 'AXFJ', 'AXMJ', 'AXEJ', 'AXHJ']

const PERIOD_DAYS: Record<string, number> = { '1M': 30, '3M': 90, '6M': 180, '1Y': 365, '3Y': 1095, '5Y': 1825 }

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 2) {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(decimals)}%`
}

function fmtNum(v: number | null, decimals = 0) {
  if (v == null) return '—'
  return v.toLocaleString('en-AU', { maximumFractionDigits: decimals })
}

function retColor(v: number | null) {
  if (v == null) return 'text-gray-400'
  return v > 0 ? 'text-emerald-600' : v < 0 ? 'text-red-500' : 'text-gray-500'
}

/**
 * Format index total market cap.
 * Backend stores total_market_cap_bn in millions of AUD (despite the "_bn" suffix).
 * Divide by 1,000,000 → billions, then auto-scale to T when ≥ 1 000 B.
 */
function fmtIndexTotalCap(v: number | null): string {
  if (v == null) return '—'
  const billions = v / 1_000_000
  if (billions >= 1_000) return `$${(billions / 1_000).toFixed(2)}T`
  if (billions >= 1)     return `$${billions.toLocaleString('en-AU', { maximumFractionDigits: 0 })}B`
  return `$${(billions * 1_000).toFixed(0)}M`
}

/**
 * Format a constituent market cap stored in millions of AUD.
 * Produces M / B / T suffixes with sensible decimal places.
 */
function fmtMktCapM(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}T`
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(1)}B`
  if (v >= 1)         return `$${v.toFixed(0)}M`
  return '—'
}

function exportDetailCSV(constituents: IndexConstituent[], code: string) {
  const headers = ['#', 'Code', 'Company', 'Sector', 'Mkt Cap', 'Weight %', '1D %', '1Y %', 'Div Yield %']
  const rows = constituents.map((c, i) => [
    i + 1,
    c.asx_code,
    `"${c.company_name}"`,
    c.sector ?? '',
    c.market_cap != null ? (c.market_cap >= 1000 ? `${(c.market_cap / 1000).toFixed(1)}B` : `${c.market_cap}M`) : '',
    c.weight_pct != null ? c.weight_pct.toFixed(2) : '',
    c.return_1d  != null ? (c.return_1d  * 100).toFixed(2) : '',
    c.return_1y  != null ? (c.return_1y  * 100).toFixed(2) : '',
    c.dividend_yield != null ? (c.dividend_yield * 100).toFixed(1) : '',
  ])
  const csv  = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `${code}-constituents-${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function ReturnBadge({ value }: { value: number | null }) {
  if (value == null) return <span className="text-gray-400 text-xs">—</span>
  const pct = fmtPct(value)
  return (
    <span className={cn('inline-flex items-center gap-0.5 text-xs font-semibold', retColor(value))}>
      {value > 0 ? <TrendingUp className="w-3 h-3" /> : value < 0 ? <TrendingDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
      {pct}
    </span>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-lg font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

function SectionCard({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('bg-white border border-gray-200 rounded-xl overflow-hidden', className)}>
      <div className="px-5 py-3 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

// ── Performance Chart ─────────────────────────────────────────────────────────

function PerformanceChart({ code }: { code: string }) {
  const [period, setPeriod] = useState('1Y')
  const [history, setHistory] = useState<{ date: string; close: number | null }[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getIndexHistory(code, PERIOD_DAYS[period])
      .then(r => setHistory(r.history))
      .finally(() => setLoading(false))
  }, [code, period])

  const formatted = history
    .filter(h => h.close != null)
    .map(h => ({ date: h.date, close: h.close as number }))

  const minY = formatted.length ? Math.min(...formatted.map(h => h.close)) * 0.98 : 0
  const maxY = formatted.length ? Math.max(...formatted.map(h => h.close)) * 1.02 : 100

  return (
    <SectionCard title="Historical Performance">
      <div className="flex gap-1 mb-4">
        {Object.keys(PERIOD_DAYS).map(p => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={cn(
              'px-3 py-1 text-xs rounded-lg font-medium transition-colors',
              period === p ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            )}
          >
            {p}
          </button>
        ))}
      </div>
      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <RefreshCw className="w-5 h-5 text-gray-300 animate-spin" />
        </div>
      ) : formatted.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
          No price history available yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={formatted} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="date"
              tickFormatter={d => {
                const dt = new Date(d)
                return dt.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
              }}
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[minY, maxY]}
              tickFormatter={v => v.toLocaleString('en-AU', { maximumFractionDigits: 0 })}
              tick={{ fontSize: 11 }}
              width={60}
            />
            <Tooltip
              formatter={(v: unknown) => [(v as number).toLocaleString('en-AU', { maximumFractionDigits: 2 }), 'Close']}
              labelFormatter={l => new Date(l).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
            />
            <Line type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </SectionCard>
  )
}

// ── Compare Chart ─────────────────────────────────────────────────────────────

function CompareChart({ currentCode }: { currentCode: string }) {
  const [selected, setSelected] = useState<string[]>([])
  const [period, setPeriod] = useState('1Y')
  const [seriesData, setSeriesData] = useState<Record<string, { date: string; value: number }[]>>({})
  const [loading, setLoading] = useState(false)

  const allSelected = [currentCode, ...selected]

  useEffect(() => {
    if (allSelected.length === 0) return
    setLoading(true)
    Promise.all(allSelected.map(c => getIndexHistory(c, PERIOD_DAYS[period]).then(r => ({ code: c, history: r.history }))))
      .then(results => {
        const map: Record<string, { date: string; value: number }[]> = {}
        results.forEach(({ code, history }) => {
          const valid = history.filter(h => h.close != null)
          if (valid.length === 0) return
          const base = valid[0].close as number
          map[code] = valid.map(h => ({ date: h.date, value: Math.round(((h.close as number) / base) * 1000) / 10 }))
        })
        setSeriesData(map)
      })
      .finally(() => setLoading(false))
  }, [selected, period, currentCode]) // eslint-disable-line react-hooks/exhaustive-deps

  const mergedDates = useMemo(() => {
    const dates = new Set<string>()
    Object.values(seriesData).forEach(series => series.forEach(p => dates.add(p.date)))
    return Array.from(dates).sort()
  }, [seriesData])

  const chartData = mergedDates.map(date => {
    const point: Record<string, unknown> = { date }
    allSelected.forEach(c => {
      const match = seriesData[c]?.find(p => p.date === date)
      if (match) point[c] = match.value
    })
    return point
  })

  return (
    <SectionCard title="Compare Indices">
      <div className="mb-4 flex flex-wrap gap-2">
        {ALL_INDICES.filter(c => c !== currentCode).map(c => (
          <button
            key={c}
            onClick={() => setSelected(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])}
            className={cn(
              'px-2.5 py-1 text-xs font-medium rounded-lg border transition-colors',
              selected.includes(c)
                ? 'bg-slate-800 text-white border-slate-800'
                : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
            )}
          >
            {c}
          </button>
        ))}
        <div className="flex gap-1 ml-auto">
          {Object.keys(PERIOD_DAYS).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={cn('px-2 py-1 text-xs rounded font-medium', period === p ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600')}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center"><RefreshCw className="w-5 h-5 text-gray-300 animate-spin" /></div>
      ) : chartData.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-sm text-gray-400">Select indices to compare</div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="date" tickFormatter={d => new Date(d).toLocaleDateString('en-AU', { month: 'short', year: '2-digit' })} tick={{ fontSize: 11 }} interval="preserveStartEnd" />
            <YAxis tickFormatter={v => `${v}`} tick={{ fontSize: 11 }} width={45} />
            <Tooltip
              formatter={(v: unknown, name: unknown) => [`${(v as number).toFixed(1)} (rebased 100)`, name as string]}
              labelFormatter={l => new Date(l).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
            />
            <Legend />
            {allSelected.map((c, i) => (
              <Line key={c} type="monotone" dataKey={c} stroke={COMPARE_COLORS[i % COMPARE_COLORS.length]} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
      <p className="text-[10px] text-gray-400 mt-2">All series rebased to 100 at the start of the selected period.</p>
    </SectionCard>
  )
}

// ── Sector Breakdown ──────────────────────────────────────────────────────────

function SectorBreakdown({ data }: { data: IndexSectorBreakdown[] }) {
  const [view, setView] = useState<'pie' | 'bar'>('pie')

  return (
    <SectionCard title="Sector Breakdown">
      <div className="flex gap-2 mb-4">
        {(['pie', 'bar'] as const).map(v => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={cn('px-3 py-1 text-xs rounded-lg font-medium transition-colors capitalize', view === v ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600')}
          >
            {v === 'pie' ? 'Pie Chart' : 'Bar Chart'}
          </button>
        ))}
      </div>

      {data.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">No sector data available</p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {view === 'pie' ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={data} dataKey="weight_pct" nameKey="sector" cx="50%" cy="50%" outerRadius={100} label={({ name, value }: { name?: string; value?: number }) => `${(name ?? '').split(' ')[0]} ${(value ?? 0).toFixed(1)}%`} labelLine={false}>
                  {data.map((entry) => (
                    <Cell key={entry.sector} fill={SECTOR_COLORS[entry.sector] || SECTOR_COLORS['Other']} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: unknown) => [`${(v as number).toFixed(2)}%`, 'Weight']} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data} layout="vertical" margin={{ left: 100, right: 20 }}>
                <XAxis type="number" tickFormatter={v => `${v.toFixed(0)}%`} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="sector" tick={{ fontSize: 11 }} width={100} />
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <Tooltip formatter={(v: unknown) => [`${(v as number).toFixed(2)}%`, 'Weight']} />
                <Bar dataKey="weight_pct" radius={[0, 4, 4, 0]}>
                  {data.map((entry) => (
                    <Cell key={entry.sector} fill={SECTOR_COLORS[entry.sector] || SECTOR_COLORS['Other']} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}

          <div className="space-y-1.5">
            {data.map(s => (
              <div key={s.sector} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm shrink-0" style={{ background: SECTOR_COLORS[s.sector] || SECTOR_COLORS['Other'] }} />
                <span className="text-sm text-gray-700 flex-1">{s.sector}</span>
                <span className="text-xs text-gray-500">{s.count}co</span>
                <span className="text-sm font-semibold text-gray-900 w-14 text-right">{s.weight_pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  )
}

// ── Constituents Table ────────────────────────────────────────────────────────

type SortKey = 'market_cap' | 'weight_pct' | 'return_1d' | 'return_1y' | 'dividend_yield'

function ConstituentsTable({ constituents }: { constituents: IndexConstituent[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('weight_pct')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [search, setSearch] = useState('')

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const sorted = useMemo(() => {
    const filtered = constituents.filter(c =>
      c.asx_code.toLowerCase().includes(search.toLowerCase()) ||
      c.company_name.toLowerCase().includes(search.toLowerCase())
    )
    return [...filtered].sort((a, b) => {
      const av = a[sortKey] ?? -Infinity
      const bv = b[sortKey] ?? -Infinity
      return sortDir === 'desc' ? (bv as number) - (av as number) : (av as number) - (bv as number)
    })
  }, [constituents, sortKey, sortDir, search])

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronDown className="w-3 h-3 text-gray-300" />
    return sortDir === 'desc'
      ? <ChevronDown className="w-3 h-3 text-blue-600" />
      : <ChevronUp className="w-3 h-3 text-blue-600" />
  }

  function ColHeader({ label, k }: { label: string; k: SortKey }) {
    return (
      <th className="px-3 py-2 text-right cursor-pointer hover:bg-gray-50 select-none" onClick={() => toggleSort(k)}>
        <span className="inline-flex items-center gap-1 justify-end text-xs font-semibold text-gray-600">
          {label}<SortIcon k={k} />
        </span>
      </th>
    )
  }

  const maxWeight = Math.max(...constituents.map(c => c.weight_pct ?? 0))

  return (
    <SectionCard title={`Constituents (${constituents.length})`}>
      <div className="mb-3 relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by code or name…"
          className="w-full max-w-xs pl-9 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600 w-8">#</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600">Code</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600">Company</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600">Sector</th>
              <ColHeader label="Mkt Cap" k="market_cap" />
              <ColHeader label="Weight" k="weight_pct" />
              <ColHeader label="1D" k="return_1d" />
              <ColHeader label="1Y" k="return_1y" />
              <ColHeader label="Div Yield" k="dividend_yield" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((c, i) => (
              <tr key={c.asx_code} className="hover:bg-gray-50 transition-colors">
                <td className="px-3 py-2 text-xs text-gray-400">{i + 1}</td>
                <td className="px-3 py-2">
                  <Link
                    href={`/company/${c.asx_code}`}
                    className="inline-block px-2 py-0.5 bg-slate-800 text-white text-xs font-bold rounded hover:bg-slate-700 transition-colors"
                  >
                    {c.asx_code}
                  </Link>
                </td>
                <td className="px-3 py-2 text-sm text-gray-800 max-w-[180px] truncate">{c.company_name}</td>
                <td className="px-3 py-2">
                  {c.sector && (
                    <span
                      className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                      style={{
                        background: `${SECTOR_COLORS[c.sector] || '#94a3b8'}20`,
                        color: SECTOR_COLORS[c.sector] || '#94a3b8',
                      }}
                    >
                      {c.sector}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right text-xs text-gray-700">
                  {fmtMktCapM(c.market_cap)}
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex items-center gap-2 justify-end">
                    <div className="w-16 bg-gray-100 rounded-full h-1.5 hidden sm:block">
                      <div
                        className="bg-blue-500 h-1.5 rounded-full"
                        style={{ width: `${maxWeight > 0 ? ((c.weight_pct ?? 0) / maxWeight) * 100 : 0}%` }}
                      />
                    </div>
                    <span className="text-xs font-medium text-gray-800 w-10 text-right">
                      {c.weight_pct != null ? `${c.weight_pct.toFixed(2)}%` : '—'}
                    </span>
                  </div>
                </td>
                <td className="px-3 py-2 text-right"><ReturnBadge value={c.return_1d} /></td>
                <td className="px-3 py-2 text-right"><ReturnBadge value={c.return_1y} /></td>
                <td className="px-3 py-2 text-right text-xs text-gray-700">
                  {c.dividend_yield != null ? `${(c.dividend_yield * 100).toFixed(1)}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

// ── Gainers / Losers ──────────────────────────────────────────────────────────

function GainersLosers({ constituents }: { constituents: IndexConstituent[] }) {
  const valid = constituents.filter(c => c.return_1d != null)
  const gainers = [...valid].sort((a, b) => (b.return_1d ?? 0) - (a.return_1d ?? 0)).slice(0, 5)
  const losers  = [...valid].sort((a, b) => (a.return_1d ?? 0) - (b.return_1d ?? 0)).slice(0, 5)

  function MoverRow({ c }: { c: IndexConstituent }) {
    return (
      <div className="flex items-center gap-2 py-2 border-b border-gray-50 last:border-0">
        <Link href={`/company/${c.asx_code}`} className="text-xs font-bold px-2 py-0.5 bg-slate-800 text-white rounded hover:bg-slate-700">
          {c.asx_code}
        </Link>
        <span className="text-sm text-gray-700 flex-1 truncate">{c.company_name}</span>
        <ReturnBadge value={c.return_1d} />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <SectionCard title="Top Gainers (1D)" className="flex-1">
        {gainers.length === 0
          ? <p className="text-sm text-gray-400">No data available</p>
          : gainers.map(c => <MoverRow key={c.asx_code} c={c} />)
        }
      </SectionCard>
      <SectionCard title="Top Losers (1D)" className="flex-1">
        {losers.length === 0
          ? <p className="text-sm text-gray-400">No data available</p>
          : losers.map(c => <MoverRow key={c.asx_code} c={c} />)
        }
      </SectionCard>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function IndexDetailContent({
  initialData,
  code,
}: {
  initialData: IndexDetail
  code: string
}) {
  const [data, setData] = useState<IndexDetail>(initialData)
  const [refreshing, setRefreshing] = useState(false)

  function refresh() {
    setRefreshing(true)
    getIndexDetail(code)
      .then(setData)
      .finally(() => setRefreshing(false))
  }

  const p = data.price

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Hero */}
      <div className="bg-slate-900 text-white">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <Link href="/indices" className="inline-flex items-center gap-1.5 text-slate-400 hover:text-white text-sm mb-4 transition-colors">
            <ArrowLeft className="w-4 h-4" /> Back to Indices
          </Link>

          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <span className="text-2xl font-bold tracking-tight">{code}</span>
                <span className="text-lg text-slate-300">{data.display_name}</span>
                {data.rebalance_freq && (
                  <span className="text-xs px-2 py-0.5 bg-slate-700 rounded-full text-slate-300">
                    {data.rebalance_freq} rebalance
                  </span>
                )}
              </div>

              {p?.close_price && (
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-3xl font-bold">{fmtNum(p.close_price, 2)}</span>
                  <ReturnBadge value={p.return_1d} />
                  {p.price_date && (
                    <span className="text-xs text-slate-400">
                      as of {new Date(p.price_date).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </span>
                  )}
                </div>
              )}

              {data.market_coverage && (
                <p className="text-sm text-slate-400 mt-2">{data.market_coverage}</p>
              )}
            </div>

            <div className="flex items-center gap-2">
              {data.constituents.length > 0 && (
                <button
                  onClick={() => exportDetailCSV(data.constituents, code)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
                  title="Export constituents as CSV"
                >
                  <Download className="w-4 h-4" />
                  Export CSV
                </button>
              )}
              <Link
                href={`/alerts?index=${encodeURIComponent(code)}`}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-amber-600 rounded-lg transition-colors"
                title="Create a price alert for this index"
              >
                <Bell className="w-4 h-4" />
                Alert
              </Link>
              <Link
                href={`/watchlist?add_index=${encodeURIComponent(code)}`}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-blue-600 rounded-lg transition-colors"
                title="Add this index to your watchlist"
              >
                <Bookmark className="w-4 h-4" />
                Watchlist
              </Link>
              <button
                onClick={refresh}
                disabled={refreshing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors disabled:opacity-50"
              >
                <RefreshCw className={cn('w-4 h-4', refreshing && 'animate-spin')} />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Performance summary */}
        {p && (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            {[
              { label: '1 Day',   value: fmtPct(p.return_1d),  color: retColor(p.return_1d) },
              { label: '1 Week',  value: fmtPct(p.return_1w),  color: retColor(p.return_1w) },
              { label: '1 Month', value: fmtPct(p.return_1m),  color: retColor(p.return_1m) },
              { label: '3 Month', value: fmtPct(p.return_3m),  color: retColor(p.return_3m) },
              { label: '6 Month', value: fmtPct(p.return_6m),  color: retColor(p.return_6m) },
              { label: '1 Year',  value: fmtPct(p.return_1y),  color: retColor(p.return_1y) },
              { label: 'YTD',     value: fmtPct(p.return_ytd), color: retColor(p.return_ytd) },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-white border border-gray-200 rounded-xl p-3 text-center">
                <p className="text-[10px] text-gray-500 mb-1">{label}</p>
                <p className={cn('text-sm font-bold', color)}>{value}</p>
              </div>
            ))}
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Constituents" value={String(data.constituent_count)} />
          <StatCard label="Total Market Cap" value={fmtIndexTotalCap(data.total_market_cap_bn)} />
          {p?.high_52w && <StatCard label="52W High" value={fmtNum(p.high_52w, 2)} />}
          {p?.low_52w  && <StatCard label="52W Low"  value={fmtNum(p.low_52w, 2)} />}
        </div>

        {/* Overview + ETF */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <SectionCard title="About this Index">
              {data.description && <p className="text-sm text-gray-700 leading-relaxed mb-4">{data.description}</p>}
              {data.eligibility && (
                <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 mb-4">
                  <p className="text-xs font-semibold text-blue-700 mb-1">Eligibility Criteria</p>
                  <p className="text-xs text-blue-800 leading-relaxed">{data.eligibility}</p>
                </div>
              )}
              {data.methodology && (
                <div className="bg-gray-50 border border-gray-100 rounded-lg p-3">
                  <p className="text-xs font-semibold text-gray-600 mb-1">Methodology</p>
                  <p className="text-xs text-gray-700 leading-relaxed">{data.methodology}</p>
                </div>
              )}
            </SectionCard>
          </div>

          {data.primary_etf && data.primary_etf.asx_code && (
            <SectionCard title="Primary Tracking ETF">
              <div className="text-center space-y-3">
                <Link
                  href={`/funds/${data.primary_etf.asx_code}`}
                  className="inline-block text-2xl font-bold text-blue-600 hover:underline"
                >
                  {data.primary_etf.asx_code}
                </Link>
                <p className="text-sm text-gray-700">{data.primary_etf.name}</p>
                {data.primary_etf.mer_pct != null && (
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Management Expense Ratio</p>
                    <p className="text-xl font-bold text-gray-900">{(data.primary_etf.mer_pct * 100).toFixed(2)}% p.a.</p>
                  </div>
                )}
                <Link
                  href={`/funds/${data.primary_etf.asx_code}`}
                  className="flex items-center justify-center gap-1.5 text-sm text-blue-600 hover:underline"
                >
                  View ETF Details <ExternalLink className="w-3.5 h-3.5" />
                </Link>
              </div>
            </SectionCard>
          )}
        </div>

        {/* Performance chart */}
        <PerformanceChart code={code} />

        {/* Compare */}
        <CompareChart currentCode={code} />

        {/* Sector breakdown */}
        {data.sector_breakdown.length > 0 && <SectorBreakdown data={data.sector_breakdown} />}

        {/* Gainers / Losers */}
        {data.constituents.length > 0 && <GainersLosers constituents={data.constituents} />}

        {/* Constituents */}
        {data.constituents.length > 0 && <ConstituentsTable constituents={data.constituents} />}
      </div>
    </div>
  )
}
