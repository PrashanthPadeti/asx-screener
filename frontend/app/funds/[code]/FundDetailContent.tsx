'use client'
import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import {
  ArrowLeft, TrendingUp, TrendingDown, Minus, ExternalLink,
  RefreshCw, DollarSign, BarChart2, Percent, Calendar,
  Download, Bell, Star,
} from 'lucide-react'
import {
  ResponsiveContainer, ComposedChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts'
import { FundDetail, FundRow, FundConstituent, getFundDetail, getSimilarFunds, getFundConstituents } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Constants ─────────────────────────────────────────────────────────────────

const INDEX_NAME_TO_CODE: Record<string, string> = {
  'S&P/ASX 20':   'ASX20',
  'S&P/ASX 50':   'ASX50',
  'S&P/ASX 100':  'ASX100',
  'S&P/ASX 200':  'ASX200',
  'S&P/ASX 300':  'ASX300',
  'ASX 200':      'ASX200',
  'ASX 300':      'ASX300',
}

const TYPE_COLORS: Record<string, string> = {
  ETF:     'bg-blue-900/60 text-blue-300 border border-blue-700',
  LIC:     'bg-purple-900/60 text-purple-300 border border-purple-700',
  MANAGED: 'bg-emerald-900/60 text-emerald-300 border border-emerald-700',
}

const ASSET_COLORS: Record<string, string> = {
  'Australian Equities': 'bg-emerald-900/40 text-emerald-300 border-emerald-700',
  'Global Equities':     'bg-blue-900/40 text-blue-300 border-blue-700',
  'Fixed Income':        'bg-indigo-900/40 text-indigo-300 border-indigo-700',
  'Property':            'bg-orange-900/40 text-orange-300 border-orange-700',
  'Commodities':         'bg-amber-900/40 text-amber-300 border-amber-700',
  'Multi-Asset':         'bg-slate-700 text-slate-300 border-slate-600',
}

const PERIOD_DAYS: Record<string, number> = { '1M': 30, '3M': 90, '6M': 180, '1Y': 365, '3Y': 1095, '5Y': 1825 }

const DARK_TOOLTIP = {
  contentStyle: { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9' },
  labelStyle:   { color: '#94a3b8', fontSize: 11 },
  itemStyle:    { color: '#e2e8f0' },
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 2, multiply = true) {
  if (v == null) return '—'
  const val = multiply ? v * 100 : v
  const sign = val > 0 ? '+' : ''
  return `${sign}${val.toFixed(decimals)}%`
}

function fmtAUM(v: number | null) {
  if (v == null) return '—'
  if (v >= 1) return `$${v.toFixed(2)}B`
  return `$${(v * 1000).toFixed(0)}M`
}

function retColor(v: number | null) {
  if (v == null) return 'text-slate-500'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-400'
}

function ReturnBadge({ value, multiply = true }: { value: number | null; multiply?: boolean }) {
  if (value == null) return <span className="text-slate-500">—</span>
  const pct = fmtPct(value, 2, multiply)
  return (
    <span className={cn('inline-flex items-center gap-0.5 font-semibold', retColor(value))}>
      {value > 0 ? <TrendingUp className="w-3.5 h-3.5" /> : value < 0 ? <TrendingDown className="w-3.5 h-3.5" /> : <Minus className="w-3.5 h-3.5" />}
      {pct}
    </span>
  )
}

function NavDiscountBadge({ value }: { value: number | null }) {
  if (value == null) return <span className="text-slate-500">—</span>
  const pct = (value * 100).toFixed(2)
  if (Math.abs(value) < 0.001) return <span className="text-slate-300 text-sm font-medium">At NAV</span>
  if (value > 0) return <span className="text-emerald-400 text-sm font-semibold">+{pct}% Premium</span>
  return <span className="text-amber-400 text-sm font-semibold">{pct}% Discount</span>
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 flex items-start gap-3">
      <div className="text-blue-400 mt-0.5">{icon}</div>
      <div>
        <p className="text-xs text-slate-400 mb-0.5">{label}</p>
        <div className="text-base font-bold text-slate-100">{value}</div>
        {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

// ── Price Chart ───────────────────────────────────────────────────────────────

function PriceChart({ history, days }: { history: FundDetail['history']; days: number }) {
  const sliced = useMemo(() => {
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - days)
    return history
      .filter(h => h.close != null && new Date(h.date) >= cutoff)
      .map(h => ({ date: h.date, close: h.close as number, nav_discount: h.nav_discount_pct }))
  }, [history, days])

  const minY = sliced.length ? Math.min(...sliced.map(h => h.close)) * 0.98 : 0
  const maxY = sliced.length ? Math.max(...sliced.map(h => h.close)) * 1.02 : 100

  if (sliced.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-500 text-sm">
        No price history available for this period
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={sliced} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis
          dataKey="date"
          tickFormatter={d => new Date(d).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          interval="preserveStartEnd"
          axisLine={{ stroke: '#334155' }}
          tickLine={{ stroke: '#334155' }}
        />
        <YAxis
          yAxisId="price"
          domain={[minY, maxY]}
          tickFormatter={v => `$${v.toFixed(2)}`}
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          width={55}
          axisLine={{ stroke: '#334155' }}
          tickLine={{ stroke: '#334155' }}
        />
        <YAxis
          yAxisId="nav"
          orientation="right"
          tickFormatter={v => `${(v * 100).toFixed(1)}%`}
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          width={50}
          axisLine={{ stroke: '#334155' }}
          tickLine={{ stroke: '#334155' }}
        />
        <Tooltip
          {...DARK_TOOLTIP}
          formatter={(v: unknown, name: unknown) => {
            const val = v as number
            return name === 'close' ? [`$${val.toFixed(3)}`, 'Price'] : [`${(val * 100).toFixed(2)}%`, 'NAV Disc/Prem']
          }}
          labelFormatter={l => new Date(l).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
        />
        <Line yAxisId="price" type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot={false} name="close" />
        <Line yAxisId="nav" type="monotone" dataKey="nav_discount" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="nav_discount" strokeDasharray="4 2" />
        <Legend
          wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
          formatter={(value) => value === 'close' ? 'Price' : 'NAV Disc/Prem'}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── Performance Table ─────────────────────────────────────────────────────────

function PerformanceTable({ latest }: { latest: FundDetail['latest'] }) {
  if (!latest) return <p className="text-sm text-slate-500">No performance data available</p>

  const rows = [
    { period: '1 Day',        value: latest.return_1d,    ann: false },
    { period: '1 Week',       value: latest.return_1w,    ann: false },
    { period: '1 Month',      value: latest.return_1m,    ann: false },
    { period: '1 Year',       value: latest.return_1y,    ann: true  },
    { period: 'Year-to-Date', value: latest.return_ytd,   ann: false },
    { period: '3 Year p.a.',  value: latest.return_3y_pa, ann: true  },
    { period: '5 Year p.a.',  value: latest.return_5y_pa, ann: true  },
  ].filter(r => r.value != null)

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-700">
          <th className="py-2 text-left text-xs font-semibold text-slate-400">Period</th>
          <th className="py-2 text-right text-xs font-semibold text-slate-400">Return</th>
          <th className="py-2 text-right text-xs font-semibold text-slate-400">Type</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-700/50">
        {rows.map(({ period, value, ann }) => (
          <tr key={period} className="hover:bg-slate-700/30 transition-colors">
            <td className="py-2.5 text-slate-300">{period}</td>
            <td className="py-2.5 text-right font-semibold">
              <ReturnBadge value={value} />
            </td>
            <td className="py-2.5 text-right text-xs text-slate-500">{ann ? 'Annualised' : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── Similar Funds ─────────────────────────────────────────────────────────────

function SimilarFunds({ code }: { code: string }) {
  const [funds, setFunds] = useState<FundRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getSimilarFunds(code)
      .then(r => setFunds(r.similar))
      .finally(() => setLoading(false))
  }, [code])

  if (loading) return <div className="h-16 bg-slate-800 rounded-xl animate-pulse" />
  if (funds.length === 0) return null

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
      <div className="px-5 py-3 border-b border-slate-700">
        <h2 className="text-sm font-semibold text-slate-100">Similar Funds</h2>
      </div>
      <div className="divide-y divide-slate-700/50">
        {funds.map(f => (
          <div key={f.asx_code} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-700/40 transition-colors">
            <Link
              href={`/funds/${f.asx_code}`}
              className="shrink-0 px-2 py-0.5 bg-slate-600 text-white text-xs font-bold rounded hover:bg-slate-500 transition-colors"
            >
              {f.asx_code}
            </Link>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-200 truncate">{f.fund_name}</p>
              <p className="text-xs text-slate-500">{f.fund_manager}</p>
            </div>
            <div className="text-right shrink-0">
              {f.return_1y != null && <ReturnBadge value={f.return_1y} />}
              <p className="text-xs text-slate-500 mt-0.5">{fmtAUM(f.funds_under_mgmt_bn)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Constituents Table ────────────────────────────────────────────────────────

function FundConstituentsTable({ code, indexTracked }: { code: string; indexTracked: string | null }) {
  const [rows, setRows] = useState<FundConstituent[]>([])
  const [source, setSource] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState<'weight_pct' | 'return_1y' | 'market_cap'>('weight_pct')

  useEffect(() => {
    getFundConstituents(code)
      .then(d => { setRows(d.constituents); setSource(d.source) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [code])

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return rows
      .filter(r => !q || r.asx_code.toLowerCase().includes(q) || r.company_name.toLowerCase().includes(q) || (r.sector ?? '').toLowerCase().includes(q))
      .sort((a, b) => ((b[sortCol] ?? -Infinity) as number) - ((a[sortCol] ?? -Infinity) as number))
  }, [rows, search, sortCol])

  if (!indexTracked) return null
  if (!loading && rows.length === 0) return null

  const fmtPctLocal = (v: number | null) => v == null ? '—' : (v > 0 ? '+' : '') + (v * 100).toFixed(2) + '%'
  const fmtMcap = (v: number | null) => v == null ? '—' : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`
  const rColor = (v: number | null) => v == null ? 'text-slate-500' : v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-500'

  function exportCSV() {
    const header = ['Rank', 'ASX Code', 'Company', 'Sector', 'Market Cap', 'Weight %', 'Price', '1W Return', '1Y Return']
    const dataRows = filtered.slice(0, 300).map((r, i) => [
      i + 1,
      r.asx_code,
      r.company_name,
      r.sector ?? '',
      fmtMcap(r.market_cap),
      r.weight_pct != null ? r.weight_pct.toFixed(2) : '',
      r.price != null ? r.price.toFixed(2) : '',
      r.return_1d != null ? (r.return_1d * 100).toFixed(2) : '',
      r.return_1y != null ? (r.return_1y * 100).toFixed(2) : '',
    ])
    const csv = [header, ...dataRows].map(row => row.map(c => `"${c}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `${code}-holdings.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-700 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">Holdings / Constituents</h2>
          {source && <p className="text-xs text-slate-500 mt-0.5">Based on {source} index membership · {rows.length} stocks · estimated weights</p>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search holdings…"
            className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 w-44"
          />
          <select
            value={sortCol}
            onChange={e => setSortCol(e.target.value as typeof sortCol)}
            className="bg-slate-700 border border-slate-600 rounded-lg px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
          >
            <option value="weight_pct">Sort: Weight</option>
            <option value="market_cap">Sort: Market Cap</option>
            <option value="return_1y">Sort: 1Y Return</option>
          </select>
          <button
            onClick={exportCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-700 border border-slate-600 hover:bg-slate-600 text-slate-200 rounded-lg transition-colors"
          >
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-10">
          <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
        </div>
      ) : (
        <>
          {/* Header */}
          <div className="grid grid-cols-12 gap-2 px-5 py-2 bg-slate-900/60 border-b border-slate-700 text-[10px] font-semibold text-slate-400 uppercase tracking-wide">
            <div className="col-span-3">Stock</div>
            <div className="col-span-3">Sector</div>
            <div className="text-right col-span-2">Market Cap</div>
            <div className="text-right col-span-1">Weight</div>
            <div className="text-right col-span-1">Price</div>
            <div className="text-right col-span-1">1W Ret</div>
            <div className="text-right col-span-1">1Y Ret</div>
          </div>
          <div className="divide-y divide-slate-700/40 max-h-[600px] overflow-y-auto">
            {filtered.slice(0, 300).map((r, i) => (
              <div key={r.asx_code} className="grid grid-cols-12 gap-2 px-5 py-2.5 hover:bg-slate-700/30 transition-colors text-sm">
                <div className="col-span-3 flex items-center gap-2">
                  <span className="text-xs text-slate-500 w-5 shrink-0">{i + 1}</span>
                  <div>
                    <Link href={`/company/${r.asx_code}`} className="text-xs font-bold text-blue-400 hover:text-blue-300">{r.asx_code}</Link>
                    <p className="text-[11px] text-slate-500 truncate max-w-[120px]">{r.company_name}</p>
                  </div>
                </div>
                <div className="col-span-3 text-xs text-slate-400 self-center truncate">{r.sector ?? '—'}</div>
                <div className="col-span-2 text-xs text-slate-300 text-right self-center">{fmtMcap(r.market_cap)}</div>
                <div className="col-span-1 text-xs font-medium text-slate-300 text-right self-center">
                  {r.weight_pct != null ? r.weight_pct.toFixed(2) + '%' : '—'}
                </div>
                <div className="col-span-1 text-xs text-slate-300 text-right self-center">
                  {r.price != null ? `$${r.price.toFixed(2)}` : '—'}
                </div>
                <div className={`col-span-1 text-xs font-medium text-right self-center ${rColor(r.return_1d)}`}>{fmtPctLocal(r.return_1d)}</div>
                <div className={`col-span-1 text-xs font-medium text-right self-center ${rColor(r.return_1y)}`}>{fmtPctLocal(r.return_1y)}</div>
              </div>
            ))}
          </div>
          {filtered.length === 0 && (
            <p className="text-center text-sm text-slate-500 py-8">No holdings match your search.</p>
          )}
        </>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function FundDetailContent({
  initialData,
  code,
}: {
  initialData: FundDetail
  code: string
}) {
  const [data, setData] = useState<FundDetail>(initialData)
  const [chartPeriod, setChartPeriod] = useState('1Y')
  const [refreshing, setRefreshing] = useState(false)

  function refresh() {
    setRefreshing(true)
    getFundDetail(code, 1825)
      .then(setData)
      .finally(() => setRefreshing(false))
  }

  const l = data.latest
  const indexCode = data.index_tracked ? INDEX_NAME_TO_CODE[data.index_tracked] ?? null : null

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Hero */}
      <div className="bg-slate-900 border-b border-slate-800 text-white">
        <div className="max-w-6xl mx-auto px-6 py-6">
          <Link href="/funds" className="inline-flex items-center gap-1.5 text-slate-400 hover:text-white text-sm mb-4 transition-colors">
            <ArrowLeft className="w-4 h-4" /> Back to Funds
          </Link>

          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center flex-wrap gap-2 mb-2">
                <span className="text-2xl font-bold text-white">{code}</span>
                {data.fund_type && (
                  <span className={cn('text-xs font-bold px-2 py-0.5 rounded-full', TYPE_COLORS[data.fund_type] || 'bg-slate-700 text-slate-300 border border-slate-600')}>
                    {data.fund_type}
                  </span>
                )}
                {data.is_hedged && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-900/60 text-blue-300 border border-blue-700">Hedged</span>
                )}
                {data.asset_class && (
                  <span className={cn('text-xs px-2 py-0.5 rounded-full border', ASSET_COLORS[data.asset_class] || 'bg-slate-700 text-slate-300 border-slate-600')}>
                    {data.asset_class}
                  </span>
                )}
              </div>
              <p className="text-lg text-slate-200 font-medium mb-1">{data.fund_name}</p>
              {data.fund_manager && <p className="text-sm text-slate-400">{data.fund_manager}</p>}

              {l?.close_price && (
                <div className="flex items-center gap-3 mt-3">
                  <span className="text-2xl font-bold text-white">${l.close_price.toFixed(3)}</span>
                  <ReturnBadge value={l.return_1d} />
                  {l.price_date && (
                    <span className="text-xs text-slate-400">
                      as of {new Date(l.price_date).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </span>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 flex-wrap justify-end">
              {data.asx_url && (
                <a href={data.asx_url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg transition-colors text-slate-200">
                  <ExternalLink className="w-4 h-4" /> ASX
                </a>
              )}
              <Link
                href={`/alerts?fund=${code}`}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg transition-colors text-slate-200"
                title="Set price alert"
              >
                <Bell className="w-4 h-4" /> Alert
              </Link>
              <Link
                href={`/watchlist?add_fund=${code}`}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg transition-colors text-slate-200"
                title="Add to watchlist"
              >
                <Star className="w-4 h-4" /> Watchlist
              </Link>
              <button onClick={refresh} disabled={refreshing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 border border-slate-600 rounded-lg transition-colors disabled:opacity-50 text-slate-200">
                <RefreshCw className={cn('w-4 h-4', refreshing && 'animate-spin')} />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">
        {/* Key Metrics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            icon={<DollarSign className="w-4 h-4" />}
            label="Funds Under Management"
            value={fmtAUM(data.funds_under_mgmt_bn)}
          />
          <MetricCard
            icon={<Percent className="w-4 h-4" />}
            label="Management Expense Ratio"
            value={data.mer_pct != null ? `${(data.mer_pct * 100).toFixed(2)}% p.a.` : '—'}
          />
          <MetricCard
            icon={<TrendingUp className="w-4 h-4" />}
            label="Distribution Yield"
            value={l?.distribution_yield != null ? `${(l.distribution_yield * 100).toFixed(2)}%` : '—'}
            sub={data.distribution_freq || undefined}
          />
          <MetricCard
            icon={<BarChart2 className="w-4 h-4" />}
            label="NAV Discount / Premium"
            value={<NavDiscountBadge value={l?.nav_discount_pct ?? null} />}
          />
          {l?.high_52w && (
            <MetricCard
              icon={<TrendingUp className="w-4 h-4" />}
              label="52 Week High"
              value={`$${l.high_52w.toFixed(3)}`}
            />
          )}
          {l?.low_52w && (
            <MetricCard
              icon={<TrendingDown className="w-4 h-4" />}
              label="52 Week Low"
              value={`$${l.low_52w.toFixed(3)}`}
            />
          )}
          {data.inception_date && (
            <MetricCard
              icon={<Calendar className="w-4 h-4" />}
              label="Inception Date"
              value={new Date(data.inception_date).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
            />
          )}
          {data.distribution_freq && (
            <MetricCard
              icon={<Calendar className="w-4 h-4" />}
              label="Distribution Frequency"
              value={data.distribution_freq}
            />
          )}
        </div>

        {/* Chart + Performance */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Price chart */}
          <div className="lg:col-span-2 bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-700 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-100">Price History</h2>
              <div className="flex gap-1">
                {Object.keys(PERIOD_DAYS).map(p => (
                  <button
                    key={p}
                    onClick={() => setChartPeriod(p)}
                    className={cn(
                      'px-2 py-0.5 text-xs rounded font-medium transition-colors',
                      chartPeriod === p
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <div className="p-5">
              <PriceChart history={data.history} days={PERIOD_DAYS[chartPeriod]} />
              <p className="text-[10px] text-slate-500 mt-2">
                Blue line = price · Dashed amber line = NAV discount/premium (right axis)
              </p>
            </div>
          </div>

          {/* Performance table */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-700">
              <h2 className="text-sm font-semibold text-slate-100">Performance Returns</h2>
            </div>
            <div className="p-5">
              <PerformanceTable latest={data.latest} />
            </div>
          </div>
        </div>

        {/* Index tracked */}
        {data.index_tracked && (
          <div className="bg-blue-950/40 border border-blue-800/50 rounded-xl p-5 flex items-center gap-4">
            <BarChart2 className="w-8 h-8 text-blue-400 shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-blue-300 font-semibold">Tracks: {data.index_tracked}</p>
              <p className="text-xs text-blue-400/70 mt-0.5">
                This fund aims to replicate the performance of the {data.index_tracked} index.
              </p>
            </div>
            {indexCode && (
              <Link
                href={`/indices/${indexCode}`}
                className="shrink-0 flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-500 transition-colors"
              >
                View Index <ExternalLink className="w-3.5 h-3.5" />
              </Link>
            )}
          </div>
        )}

        {/* Holdings / Constituents */}
        <FundConstituentsTable code={code} indexTracked={data.index_tracked} />

        {/* Similar funds */}
        <SimilarFunds code={code} />

        {/* Footer disclaimer */}
        <p className="text-[11px] text-slate-600 text-center pb-4">
          Fund data is sourced from public ASX disclosures and third-party providers. Holdings are approximate and may not reflect current positions.
          Not financial advice. Past performance is not indicative of future results.
        </p>
      </div>
    </div>
  )
}
