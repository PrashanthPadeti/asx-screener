'use client'
import { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import {
  ArrowLeft, TrendingUp, TrendingDown, Minus, ExternalLink,
  RefreshCw, DollarSign, BarChart2, Percent, Calendar,
} from 'lucide-react'
import {
  ResponsiveContainer, ComposedChart, LineChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts'
import { FundDetail, FundRow, getFundDetail, getSimilarFunds } from '@/lib/api'
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
  ETF:     'bg-blue-100 text-blue-700',
  LIC:     'bg-purple-100 text-purple-700',
  MANAGED: 'bg-green-100 text-green-700',
}

const ASSET_COLORS: Record<string, string> = {
  'Australian Equities': 'bg-emerald-50 text-emerald-700 border-emerald-200',
  'Global Equities':     'bg-blue-50 text-blue-700 border-blue-200',
  'Fixed Income':        'bg-indigo-50 text-indigo-700 border-indigo-200',
  'Property':            'bg-orange-50 text-orange-700 border-orange-200',
  'Commodities':         'bg-amber-50 text-amber-700 border-amber-200',
  'Multi-Asset':         'bg-slate-50 text-slate-700 border-slate-200',
}

const PERIOD_DAYS: Record<string, number> = { '1M': 30, '3M': 90, '6M': 180, '1Y': 365, '3Y': 1095, '5Y': 1825 }

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
  if (v == null) return 'text-gray-400'
  return v > 0 ? 'text-emerald-600' : v < 0 ? 'text-red-500' : 'text-gray-500'
}

function ReturnBadge({ value, multiply = true }: { value: number | null; multiply?: boolean }) {
  if (value == null) return <span className="text-gray-400">—</span>
  const pct = fmtPct(value, 2, multiply)
  return (
    <span className={cn('inline-flex items-center gap-0.5 font-semibold', retColor(value))}>
      {value > 0 ? <TrendingUp className="w-3.5 h-3.5" /> : value < 0 ? <TrendingDown className="w-3.5 h-3.5" /> : <Minus className="w-3.5 h-3.5" />}
      {pct}
    </span>
  )
}

function NavDiscountBadge({ value }: { value: number | null }) {
  if (value == null) return <span className="text-gray-400">—</span>
  const pct = (value * 100).toFixed(2)
  if (Math.abs(value) < 0.001) return <span className="text-gray-600 text-sm font-medium">At NAV</span>
  if (value > 0) return <span className="text-emerald-600 text-sm font-semibold">+{pct}% Premium</span>
  return <span className="text-amber-600 text-sm font-semibold">{pct}% Discount</span>
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 flex items-start gap-3">
      <div className="text-blue-500 mt-0.5">{icon}</div>
      <div>
        <p className="text-xs text-gray-500 mb-0.5">{label}</p>
        <div className="text-base font-bold text-gray-900">{value}</div>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
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
      <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
        No price history available for this period
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={sliced} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="date"
          tickFormatter={d => new Date(d).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}
          tick={{ fontSize: 11 }}
          interval="preserveStartEnd"
        />
        <YAxis
          yAxisId="price"
          domain={[minY, maxY]}
          tickFormatter={v => `$${v.toFixed(2)}`}
          tick={{ fontSize: 11 }}
          width={55}
        />
        <YAxis
          yAxisId="nav"
          orientation="right"
          tickFormatter={v => `${(v * 100).toFixed(1)}%`}
          tick={{ fontSize: 11 }}
          width={50}
        />
        <Tooltip
          formatter={(v: number, name: string) =>
            name === 'close' ? [`$${v.toFixed(3)}`, 'Price'] : [`${(v * 100).toFixed(2)}%`, 'NAV Disc/Prem']
          }
          labelFormatter={l => new Date(l).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
        />
        <Line yAxisId="price" type="monotone" dataKey="close" stroke="#3b82f6" strokeWidth={2} dot={false} name="close" />
        <Line yAxisId="nav" type="monotone" dataKey="nav_discount" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="nav_discount" strokeDasharray="4 2" />
        <Legend />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── Performance Table ─────────────────────────────────────────────────────────

function PerformanceTable({ latest }: { latest: FundDetail['latest'] }) {
  if (!latest) return <p className="text-sm text-gray-400">No performance data available</p>

  const rows = [
    { period: '1 Day',       value: latest.return_1d,    ann: false },
    { period: '1 Week',      value: latest.return_1w,    ann: false },
    { period: '1 Month',     value: latest.return_1m,    ann: false },
    { period: '1 Year',      value: latest.return_1y,    ann: true },
    { period: 'Year-to-Date',value: latest.return_ytd,   ann: false },
    { period: '3 Year p.a.', value: latest.return_3y_pa, ann: true },
    { period: '5 Year p.a.', value: latest.return_5y_pa, ann: true },
  ].filter(r => r.value != null)

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-gray-100">
          <th className="py-2 text-left text-xs font-semibold text-gray-500">Period</th>
          <th className="py-2 text-right text-xs font-semibold text-gray-500">Return</th>
          <th className="py-2 text-right text-xs font-semibold text-gray-500">Type</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50">
        {rows.map(({ period, value, ann }) => (
          <tr key={period}>
            <td className="py-2.5 text-gray-700">{period}</td>
            <td className="py-2.5 text-right font-semibold">
              <ReturnBadge value={value} />
            </td>
            <td className="py-2.5 text-right text-xs text-gray-400">{ann ? 'Annualised' : ''}</td>
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

  if (loading) return <div className="h-16 bg-gray-50 rounded-xl animate-pulse" />
  if (funds.length === 0) return null

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-900">Similar Funds</h2>
      </div>
      <div className="divide-y divide-gray-50">
        {funds.map(f => (
          <div key={f.asx_code} className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition-colors">
            <Link
              href={`/funds/${f.asx_code}`}
              className="shrink-0 px-2 py-0.5 bg-slate-800 text-white text-xs font-bold rounded hover:bg-slate-700"
            >
              {f.asx_code}
            </Link>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-800 truncate">{f.fund_name}</p>
              <p className="text-xs text-gray-400">{f.fund_manager}</p>
            </div>
            <div className="text-right shrink-0">
              {f.return_1y != null && <ReturnBadge value={f.return_1y} />}
              <p className="text-xs text-gray-400 mt-0.5">{fmtAUM(f.funds_under_mgmt_bn)}</p>
            </div>
          </div>
        ))}
      </div>
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
    <div className="min-h-screen bg-gray-50">
      {/* Hero */}
      <div className="bg-slate-900 text-white">
        <div className="max-w-6xl mx-auto px-6 py-6">
          <Link href="/funds" className="inline-flex items-center gap-1.5 text-slate-400 hover:text-white text-sm mb-4 transition-colors">
            <ArrowLeft className="w-4 h-4" /> Back to Funds
          </Link>

          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center flex-wrap gap-2 mb-2">
                <span className="text-2xl font-bold">{code}</span>
                {data.fund_type && (
                  <span className={cn('text-xs font-bold px-2 py-0.5 rounded-full', TYPE_COLORS[data.fund_type] || 'bg-gray-100 text-gray-600')}>
                    {data.fund_type}
                  </span>
                )}
                {data.is_hedged && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-900 text-blue-300">Hedged</span>
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
                  <span className="text-2xl font-bold">${l.close_price.toFixed(3)}</span>
                  <ReturnBadge value={l.return_1d} />
                  {l.price_date && (
                    <span className="text-xs text-slate-400">
                      as of {new Date(l.price_date).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </span>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              {data.asx_url && (
                <a href={data.asx_url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors">
                  <ExternalLink className="w-4 h-4" /> ASX
                </a>
              )}
              <button onClick={refresh} disabled={refreshing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors disabled:opacity-50">
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
          <div className="lg:col-span-2 bg-white border border-gray-200 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-900">Price History</h2>
              <div className="flex gap-1">
                {Object.keys(PERIOD_DAYS).map(p => (
                  <button
                    key={p}
                    onClick={() => setChartPeriod(p)}
                    className={cn(
                      'px-2 py-0.5 text-xs rounded font-medium transition-colors',
                      chartPeriod === p ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <div className="p-5">
              <PriceChart history={data.history} days={PERIOD_DAYS[chartPeriod]} />
              <p className="text-[10px] text-gray-400 mt-2">
                Blue line = price. Dashed amber line = NAV discount/premium (right axis).
              </p>
            </div>
          </div>

          {/* Performance table */}
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-900">Performance Returns</h2>
            </div>
            <div className="p-5">
              <PerformanceTable latest={data.latest} />
            </div>
          </div>
        </div>

        {/* Index tracked */}
        {data.index_tracked && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 flex items-center gap-4">
            <BarChart2 className="w-8 h-8 text-blue-500 shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-blue-700 font-semibold">Tracks: {data.index_tracked}</p>
              <p className="text-xs text-blue-600 mt-0.5">
                This fund aims to replicate the performance of the {data.index_tracked} index.
              </p>
            </div>
            {indexCode && (
              <Link
                href={`/indices/${indexCode}`}
                className="shrink-0 flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
              >
                View Index <ExternalLink className="w-3.5 h-3.5" />
              </Link>
            )}
          </div>
        )}

        {/* Similar funds */}
        <SimilarFunds code={code} />
      </div>
    </div>
  )
}
