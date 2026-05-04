'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { TrendingUp, TrendingDown, Activity, BarChart2, Calendar, RefreshCw } from 'lucide-react'
import { getMarketDashboard, MarketDashboard, DashboardStock, ActiveStock, ShortedStock, ExDivStock } from '@/lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  return (pct >= 0 ? '+' : '') + pct.toFixed(decimals) + '%'
}

function fmtCap(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1000) return '$' + (v / 1000).toFixed(1) + 'T'
  return '$' + v.toFixed(0) + 'B'
}

function fmtVol(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M'
  if (v >= 1_000) return (v / 1_000).toFixed(0) + 'K'
  return v.toString()
}

function fmtPrice(v: number | null): string {
  if (v == null) return '—'
  return '$' + v.toFixed(2)
}

function retColor(v: number | null): string {
  if (v == null) return 'text-slate-500'
  if (v > 0) return 'text-emerald-600'
  if (v < 0) return 'text-red-500'
  return 'text-slate-500'
}

function heatColor(v: number | null): string {
  if (v == null) return 'bg-slate-100 text-slate-600'
  const pct = v * 100
  if (pct >= 3)  return 'bg-emerald-600 text-white'
  if (pct >= 1)  return 'bg-emerald-500 text-white'
  if (pct >= 0)  return 'bg-emerald-100 text-emerald-800'
  if (pct >= -1) return 'bg-red-100 text-red-800'
  if (pct >= -3) return 'bg-red-400 text-white'
  return 'bg-red-600 text-white'
}

// ── Sub-components ────────────────────────────────────────────────────────────

function IndexCard({ label, snap }: { label: string; snap: MarketDashboard['asx200'] }) {
  const dir = (snap.avg_return_1w ?? 0) >= 0
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-500 uppercase tracking-wide">{label}</span>
        {dir
          ? <TrendingUp className="w-4 h-4 text-emerald-500" />
          : <TrendingDown className="w-4 h-4 text-red-500" />}
      </div>
      <div className={`text-2xl font-bold ${retColor(snap.avg_return_1w)}`}>
        {fmtPct(snap.avg_return_1w)} <span className="text-sm font-normal text-slate-400">1W avg</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="bg-emerald-50 rounded-lg py-1.5">
          <div className="font-semibold text-emerald-700">{snap.gainers}</div>
          <div className="text-emerald-600">Up</div>
        </div>
        <div className="bg-red-50 rounded-lg py-1.5">
          <div className="font-semibold text-red-600">{snap.losers}</div>
          <div className="text-red-500">Down</div>
        </div>
        <div className="bg-slate-50 rounded-lg py-1.5">
          <div className="font-semibold text-slate-600">{snap.unchanged}</div>
          <div className="text-slate-500">Flat</div>
        </div>
      </div>
      <div className="text-xs text-slate-400">
        {snap.stock_count} stocks · {fmtCap(snap.total_market_cap_bn)} mkt cap
      </div>
    </div>
  )
}

function MoverRow({ s, rank }: { s: DashboardStock; rank: number }) {
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3 text-xs text-slate-400 w-6">{rank}</td>
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">
          {s.asx_code}
        </Link>
        <div className="text-xs text-slate-500 truncate max-w-[140px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm text-slate-600 hidden sm:table-cell">{s.sector ?? '—'}</td>
      <td className="py-2 px-3 text-sm text-right">{fmtPrice(s.price)}</td>
      <td className={`py-2 px-3 text-sm font-semibold text-right ${retColor(s.return_1w)}`}>{fmtPct(s.return_1w)}</td>
    </tr>
  )
}

function ActiveRow({ s, rank }: { s: ActiveStock; rank: number }) {
  const volRatio = s.volume && s.avg_volume_20d ? s.volume / s.avg_volume_20d : null
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3 text-xs text-slate-400 w-6">{rank}</td>
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">
          {s.asx_code}
        </Link>
        <div className="text-xs text-slate-500 truncate max-w-[120px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm text-right">{fmtPrice(s.price)}</td>
      <td className="py-2 px-3 text-sm text-right text-slate-700">{fmtVol(s.volume)}</td>
      <td className="py-2 px-3 text-right">
        {volRatio != null && (
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${volRatio >= 2 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>
            {volRatio.toFixed(1)}x
          </span>
        )}
      </td>
    </tr>
  )
}

function ShortedRow({ s, rank }: { s: ShortedStock; rank: number }) {
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3 text-xs text-slate-400 w-6">{rank}</td>
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">
          {s.asx_code}
        </Link>
        <div className="text-xs text-slate-500 truncate max-w-[120px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm text-right font-semibold text-red-600">
        {s.short_pct != null ? s.short_pct.toFixed(1) + '%' : '—'}
      </td>
      <td className={`py-2 px-3 text-sm text-right ${retColor(s.return_1w)}`}>{fmtPct(s.return_1w)}</td>
    </tr>
  )
}

function ExDivRow({ s }: { s: ExDivStock }) {
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">
          {s.asx_code}
        </Link>
        <div className="text-xs text-slate-500 truncate max-w-[120px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm font-medium text-slate-700">{s.ex_div_date ?? '—'}</td>
      <td className="py-2 px-3 text-sm text-slate-500">{s.pay_date ?? '—'}</td>
      <td className="py-2 px-3 text-sm text-right text-slate-700">
        {s.dps_ttm != null ? '$' + s.dps_ttm.toFixed(3) : '—'}
      </td>
      <td className="py-2 px-3 text-sm text-right text-emerald-600">
        {s.dividend_yield != null ? (s.dividend_yield * 100).toFixed(1) + '%' : '—'}
      </td>
      <td className="py-2 px-3 text-sm text-right">
        {s.franking_pct != null ? (
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${s.franking_pct >= 100 ? 'bg-emerald-100 text-emerald-700' : s.franking_pct > 0 ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'}`}>
            {s.franking_pct.toFixed(0)}%
          </span>
        ) : '—'}
      </td>
    </tr>
  )
}

function TableCard({ title, icon: Icon, children }: { title: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
        <Icon className="w-4 h-4 text-slate-500" />
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        {children}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketPage() {
  const [data, setData] = useState<MarketDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await getMarketDashboard())
    } catch {
      setError('Failed to load market data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex items-center gap-2 text-slate-500">
        <Activity className="w-5 h-5 animate-pulse" />
        Loading market overview…
      </div>
    </div>
  )

  if (error || !data) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-red-500">{error ?? 'No data available.'}</div>
    </div>
  )

  const builtAt = data.universe_built_at
    ? new Date(data.universe_built_at).toLocaleString('en-AU', { dateStyle: 'medium', timeStyle: 'short' })
    : null

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Market Overview</h1>
          {builtAt && <p className="text-xs text-slate-400 mt-0.5">Data as at {builtAt} AEST</p>}
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {/* Index Snapshots */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <IndexCard label="ASX 200" snap={data.asx200} />
        <IndexCard label="ASX 300" snap={data.asx300} />
      </div>

      {/* Sector Heatmap */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
          <BarChart2 className="w-4 h-4 text-slate-500" />
          <h2 className="text-sm font-semibold text-slate-700">Sector Heatmap — 1W Performance</h2>
        </div>
        <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
          {data.sector_heatmap.map(s => (
            <div key={s.sector} className={`rounded-lg p-3 text-center ${heatColor(s.avg_return_1w)}`}>
              <div className="text-xs font-semibold leading-tight mb-1">{s.sector}</div>
              <div className="text-sm font-bold">{fmtPct(s.avg_return_1w)}</div>
              <div className="text-xs opacity-75 mt-0.5">{s.stock_count} stocks</div>
            </div>
          ))}
        </div>
      </div>

      {/* Movers + Active + Shorted */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Top Gainers */}
        <TableCard title="Top 10 Gainers (1W)" icon={TrendingUp}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left w-6">#</th>
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-left hidden sm:table-cell">Sector</th>
                <th className="py-2 px-3 text-right">Price</th>
                <th className="py-2 px-3 text-right">1W</th>
              </tr>
            </thead>
            <tbody>
              {data.top_gainers.map((s, i) => <MoverRow key={s.asx_code} s={s} rank={i + 1} />)}
            </tbody>
          </table>
        </TableCard>

        {/* Top Losers */}
        <TableCard title="Top 10 Losers (1W)" icon={TrendingDown}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left w-6">#</th>
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-left hidden sm:table-cell">Sector</th>
                <th className="py-2 px-3 text-right">Price</th>
                <th className="py-2 px-3 text-right">1W</th>
              </tr>
            </thead>
            <tbody>
              {data.top_losers.map((s, i) => <MoverRow key={s.asx_code} s={s} rank={i + 1} />)}
            </tbody>
          </table>
        </TableCard>

        {/* Most Active */}
        <TableCard title="Most Active by Volume" icon={Activity}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left w-6">#</th>
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-right">Price</th>
                <th className="py-2 px-3 text-right">Volume</th>
                <th className="py-2 px-3 text-right">vs 20D Avg</th>
              </tr>
            </thead>
            <tbody>
              {data.most_active.map((s, i) => <ActiveRow key={s.asx_code} s={s} rank={i + 1} />)}
            </tbody>
          </table>
        </TableCard>

        {/* Most Shorted */}
        <TableCard title="Most Heavily Shorted" icon={TrendingDown}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left w-6">#</th>
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-right">Short %</th>
                <th className="py-2 px-3 text-right">1W Return</th>
              </tr>
            </thead>
            <tbody>
              {data.most_shorted.map((s, i) => <ShortedRow key={s.asx_code} s={s} rank={i + 1} />)}
            </tbody>
          </table>
        </TableCard>
      </div>

      {/* Upcoming Ex-Div Dates */}
      <TableCard title="Upcoming Ex-Dividend Dates — Next 14 Days" icon={Calendar}>
        {data.upcoming_exdiv.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-slate-400">
            No upcoming ex-dividend dates in the next 14 days.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-left">Ex-Div Date</th>
                <th className="py-2 px-3 text-left hidden sm:table-cell">Pay Date</th>
                <th className="py-2 px-3 text-right">DPS</th>
                <th className="py-2 px-3 text-right">Yield</th>
                <th className="py-2 px-3 text-right">Franking</th>
              </tr>
            </thead>
            <tbody>
              {data.upcoming_exdiv.map(s => <ExDivRow key={s.asx_code} s={s} />)}
            </tbody>
          </table>
        )}
      </TableCard>

    </div>
  )
}
