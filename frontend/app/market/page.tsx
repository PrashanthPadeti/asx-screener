'use client'
import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import {
  TrendingUp, TrendingDown, Activity, BarChart2,
  Calendar, RefreshCw, ArrowUp, ArrowDown, Zap, AlertTriangle,
} from 'lucide-react'
import {
  getMarketDashboard, getMarketMovers, getMarketSignals, getMarketAnomalies,
  MarketDashboard, DashboardStock, ActiveStock, VolumePressureStock,
  ExDivStock, MoverStock, SignalStock, AnomalyFlag,
} from '@/lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  return (pct >= 0 ? '+' : '') + pct.toFixed(decimals) + '%'
}

function fmtPctRaw(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + v.toFixed(decimals) + '%'
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
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-slate-400">Stocks</p>
          <p className="font-semibold text-slate-800">{snap.stock_count.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Avg 1W Return</p>
          <p className={`font-semibold ${retColor(snap.avg_return_1w)}`}>{fmtPct(snap.avg_return_1w)}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Gainers / Losers</p>
          <p className="font-semibold text-slate-800">
            <span className="text-emerald-600">{snap.gainers}</span>
            {' / '}
            <span className="text-red-500">{snap.losers}</span>
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Market Cap</p>
          <p className="font-semibold text-slate-800">{fmtCap(snap.total_market_cap_bn)}</p>
        </div>
      </div>
    </div>
  )
}

type MoverRetKey = 'return_1d' | 'return_1w' | 'return_1m'
function MoverRow({ s, rank, retKey, period }: { s: MoverStock; rank: number; retKey: MoverRetKey; period: Period }) {
  const ret = s[retKey]
  const periodLabel = period.toUpperCase()
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3 text-xs text-slate-400 w-6">{rank}</td>
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">{s.asx_code}</Link>
        <div className="text-xs text-slate-500 truncate max-w-[100px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm text-right">{fmtPrice(s.price)}</td>
      <td className="py-2 px-3 text-sm text-right text-emerald-600 hidden md:table-cell">
        {s.period_high != null ? fmtPrice(s.period_high) : '—'}
      </td>
      <td className="py-2 px-3 text-sm text-right text-red-500 hidden md:table-cell">
        {s.period_low != null ? fmtPrice(s.period_low) : '—'}
      </td>
      <td className={`py-2 px-3 text-sm text-right font-semibold ${retColor(ret)}`}>{fmtPct(ret)}</td>
    </tr>
  )
}

function MoverTableHeader({ period, retKey }: { period: Period; retKey: MoverRetKey }) {
  const p = period.toUpperCase()
  return (
    <tr className="text-xs text-slate-400 bg-slate-50">
      <th className="py-2 px-3 text-left w-6">#</th>
      <th className="py-2 px-3 text-left">Stock</th>
      <th className="py-2 px-3 text-right">Price</th>
      <th className="py-2 px-3 text-right text-emerald-600 hidden md:table-cell">{p} High</th>
      <th className="py-2 px-3 text-right text-red-500 hidden md:table-cell">{p} Low</th>
      <th className="py-2 px-3 text-right">{p} Chg</th>
    </tr>
  )
}

function ActiveRow({ s, rank }: { s: ActiveStock; rank: number }) {
  const volRatio = s.volume && s.avg_volume_20d ? s.volume / s.avg_volume_20d : null
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3 text-xs text-slate-400 w-6">{rank}</td>
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">{s.asx_code}</Link>
        <div className="text-xs text-slate-500 truncate max-w-[120px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm text-right">{fmtPrice(s.price)}</td>
      <td className="py-2 px-3 text-sm text-right text-slate-700">{fmtVol(s.volume)}</td>
      <td className="py-2 px-3 text-sm text-right">
        {volRatio != null ? (
          <span className={`font-medium ${volRatio >= 3 ? 'text-orange-600' : volRatio >= 2 ? 'text-amber-600' : 'text-slate-500'}`}>
            {volRatio.toFixed(1)}×
          </span>
        ) : '—'}
      </td>
    </tr>
  )
}

function VolumePressureRow({ s, rank, type }: { s: VolumePressureStock; rank: number; type: 'buying' | 'selling' }) {
  const ratioColor = type === 'buying'
    ? (s.volume_ratio ?? 0) >= 3 ? 'text-emerald-700 font-bold' : 'text-emerald-600 font-semibold'
    : (s.volume_ratio ?? 0) >= 3 ? 'text-red-700 font-bold' : 'text-red-500 font-semibold'
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3 text-xs text-slate-400 w-6">{rank}</td>
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">{s.asx_code}</Link>
        <div className="text-xs text-slate-500 truncate max-w-[110px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm text-right">{fmtPrice(s.price)}</td>
      <td className={`py-2 px-3 text-sm text-right ${ratioColor}`}>
        {s.volume_ratio != null ? s.volume_ratio.toFixed(1) + '×' : '—'}
      </td>
      <td className={`py-2 px-3 text-sm text-right ${retColor(s.return_1w)}`}>{fmtPct(s.return_1w)}</td>
    </tr>
  )
}

function ExDivRow({ s }: { s: ExDivStock }) {
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">{s.asx_code}</Link>
        <div className="text-xs text-slate-500 truncate max-w-[120px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm font-medium text-slate-700">{s.ex_div_date ?? '—'}</td>
      <td className="py-2 px-3 text-sm text-slate-500 hidden sm:table-cell">{s.pay_date ?? '—'}</td>
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

function SignalHighLowRow({ s, type, period }: { s: SignalStock; type: 'high' | 'low'; period: SigPeriod }) {
  const pct = type === 'high' ? s.pct_from_high : s.pct_from_low
  const ret = (period === '1m' || period === '3m' || period === '52w') ? s.return_1m : s.return_1w
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">{s.asx_code}</Link>
        <div className="text-xs text-slate-500 truncate max-w-[110px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm text-right">{fmtPrice(s.price)}</td>
      <td className="py-2 px-3 text-sm text-right text-slate-500">
        {fmtPrice(type === 'high' ? s.period_high : s.period_low)}
      </td>
      <td className={`py-2 px-3 text-sm text-right font-semibold ${type === 'high' ? 'text-emerald-600' : 'text-red-500'}`}>
        {pct != null ? fmtPctRaw(pct) : '—'}
      </td>
      <td className={`py-2 px-3 text-sm text-right ${retColor(ret)}`}>{fmtPct(ret)}</td>
    </tr>
  )
}

function VolSurgeRow({ s, period }: { s: SignalStock; period: SigPeriod }) {
  const ret = (period === '1m' || period === '3m' || period === '52w') ? s.return_1m : s.return_1w
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
      <td className="py-2 px-3">
        <Link href={`/company/${s.asx_code}`} className="font-semibold text-blue-600 hover:underline text-sm">{s.asx_code}</Link>
        <div className="text-xs text-slate-500 truncate max-w-[110px]">{s.company_name}</div>
      </td>
      <td className="py-2 px-3 text-sm text-slate-500 hidden sm:table-cell truncate max-w-[90px]">{s.sector ?? '—'}</td>
      <td className="py-2 px-3 text-sm text-right">{fmtPrice(s.price)}</td>
      <td className="py-2 px-3 text-sm text-right">{fmtVol(s.volume)}</td>
      <td className="py-2 px-3 text-sm text-right">
        {s.vol_ratio != null ? (
          <span className={`font-bold ${s.vol_ratio >= 5 ? 'text-orange-600' : s.vol_ratio >= 3 ? 'text-amber-600' : 'text-slate-700'}`}>
            {s.vol_ratio.toFixed(1)}×
          </span>
        ) : '—'}
      </td>
      <td className={`py-2 px-3 text-sm text-right ${retColor(ret)}`}>{fmtPct(ret)}</td>
    </tr>
  )
}

function TableCard({ title, icon: Icon, children, className }: {
  title: string; icon: React.ElementType; children: React.ReactNode; className?: string
}) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 overflow-hidden ${className ?? ''}`}>
      <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
        <Icon className="w-4 h-4 text-slate-500" />
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
      </div>
      <div className="overflow-x-auto">{children}</div>
    </div>
  )
}

type Period   = '1d' | '1w' | '1m' | '3m'
type SigPeriod = '1d' | '1w' | '1m' | '3m' | '52w'
const PERIOD_LABELS: Record<Period, string>    = { '1d': '1D', '1w': '1W', '1m': '1M', '3m': '3M' }
const SIG_PERIOD_LABELS: Record<SigPeriod, string> = { '1d': '1D', '1w': '1W', '1m': '1M', '3m': '3M', '52w': '52W' }

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketPage() {
  const [data, setData]         = useState<MarketDashboard | null>(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)

  const [moverPeriod, setMoverPeriod] = useState<Period>('1d')
  const [movers, setMovers]     = useState<{ gainers: MoverStock[]; losers: MoverStock[] } | null>(null)
  const [moversLoading, setMoversLoading] = useState(false)

  const [sigPeriod, setSigPeriod] = useState<SigPeriod>('52w')
  const [signals, setSignals]   = useState<{ near_period_high: SignalStock[]; near_period_low: SignalStock[]; volume_surge: SignalStock[] } | null>(null)
  const [signalsLoading, setSignalsLoading] = useState(false)

  const [sigTab, setSigTab]     = useState<'high' | 'low' | 'volume'>('high')

  const [anomalies, setAnomalies]         = useState<AnomalyFlag[]>([])
  const [anomaliesLoading, setAnomaliesLoading] = useState(false)
  const [anomalyFilter, setAnomalyFilter] = useState('all')

  const loadDashboard = async () => {
    setLoading(true); setError(null)
    try { setData(await getMarketDashboard()) }
    catch { setError('Failed to load market data.') }
    finally { setLoading(false) }
  }

  const loadMovers = useCallback(async (period: Period) => {
    setMoversLoading(true)
    try { setMovers(await getMarketMovers(period, 10)) }
    catch { /* keep previous */ }
    finally { setMoversLoading(false) }
  }, [])

  const loadSignals = useCallback(async (period: SigPeriod) => {
    setSignalsLoading(true)
    try { setSignals(await getMarketSignals(period)) }
    catch { /* keep previous */ }
    finally { setSignalsLoading(false) }
  }, [])

  const loadAnomalies = async (flagType?: string) => {
    setAnomaliesLoading(true)
    try {
      const res = await getMarketAnomalies(100, flagType === 'all' ? undefined : flagType)
      setAnomalies(res.flags)
    } catch { /* keep previous */ }
    finally { setAnomaliesLoading(false) }
  }

  useEffect(() => { loadDashboard(); loadSignals('52w'); loadMovers('1d'); loadAnomalies() }, [loadSignals, loadMovers])
  useEffect(() => { loadMovers(moverPeriod) }, [moverPeriod, loadMovers])
  useEffect(() => { loadSignals(sigPeriod) }, [sigPeriod, loadSignals])

  const refreshAll = () => { loadDashboard(); loadMovers(moverPeriod); loadSignals(sigPeriod); loadAnomalies(anomalyFilter) }

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex items-center gap-2 text-slate-500">
        <Activity className="w-5 h-5 animate-pulse" />Loading market overview…
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

  const retKey: MoverRetKey =
    moverPeriod === '1d' ? 'return_1d' :
    moverPeriod === '1w' ? 'return_1w' : 'return_1m'

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Market Overview</h1>
          {builtAt && <p className="text-xs text-slate-400 mt-0.5">Data as at {builtAt} AEST</p>}
        </div>
        <button onClick={refreshAll}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50">
          <RefreshCw className="w-3.5 h-3.5" />Refresh
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

      {/* Top Movers — period tabs */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-700">Top Movers</h2>
          </div>
          <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
            {(['1d', '1w', '1m', '3m'] as Period[]).map(p => (
              <button key={p} onClick={() => setMoverPeriod(p)}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${moverPeriod === p ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        {moversLoading ? (
          <div className="h-48 flex items-center justify-center text-slate-400 text-sm">Loading…</div>
        ) : movers && (
          <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-slate-100">
            {/* Gainers */}
            <div>
              <div className="px-4 py-2 bg-emerald-50 flex items-center gap-1.5">
                <ArrowUp className="w-3.5 h-3.5 text-emerald-600" />
                <span className="text-xs font-semibold text-emerald-700">Top Gainers — {PERIOD_LABELS[moverPeriod]}</span>
              </div>
              <table className="w-full text-sm">
                <thead><MoverTableHeader period={moverPeriod} retKey={retKey} /></thead>
                <tbody>
                  {movers.gainers.map((s, i) => <MoverRow key={s.asx_code} s={s} rank={i + 1} retKey={retKey} period={moverPeriod} />)}
                </tbody>
              </table>
            </div>
            {/* Losers */}
            <div>
              <div className="px-4 py-2 bg-red-50 flex items-center gap-1.5">
                <ArrowDown className="w-3.5 h-3.5 text-red-600" />
                <span className="text-xs font-semibold text-red-700">Top Losers — {PERIOD_LABELS[moverPeriod]}</span>
              </div>
              <table className="w-full text-sm">
                <thead><MoverTableHeader period={moverPeriod} retKey={retKey} /></thead>
                <tbody>
                  {movers.losers.map((s, i) => <MoverRow key={s.asx_code} s={s} rank={i + 1} retKey={retKey} period={moverPeriod} />)}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Period Highs/Lows + Volume Surge */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-700">Market Signals</h2>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Signal type tabs */}
            <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
              {([['high', '↑ Highs'], ['low', '↓ Lows'], ['volume', '⚡ Volume']] as const).map(([k, label]) => (
                <button key={k} onClick={() => setSigTab(k)}
                  className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${sigTab === k ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                  {label}
                </button>
              ))}
            </div>
            {/* Period selector — independent from movers, includes 52W */}
            <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
              {(Object.keys(SIG_PERIOD_LABELS) as SigPeriod[]).map(p => (
                <button key={p} onClick={() => setSigPeriod(p)}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors ${sigPeriod === p ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                  {SIG_PERIOD_LABELS[p]}
                </button>
              ))}
            </div>
          </div>
        </div>
        {signalsLoading ? (
          <div className="h-48 flex items-center justify-center text-slate-400 text-sm">Loading…</div>
        ) : signals ? (
          <>
            {(() => {
              const retLabel = (sigPeriod === '1m' || sigPeriod === '3m' || sigPeriod === '52w') ? '1M' : '1W'
              return (
                <>
                  {sigTab === 'high' && (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-xs text-slate-400 bg-slate-50">
                          <th className="py-2 px-3 text-left">Stock</th>
                          <th className="py-2 px-3 text-right">Price</th>
                          <th className="py-2 px-3 text-right">{SIG_PERIOD_LABELS[sigPeriod]} High</th>
                          <th className="py-2 px-3 text-right">From High</th>
                          <th className="py-2 px-3 text-right">{retLabel}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {signals.near_period_high.length === 0
                          ? <tr><td colSpan={5} className="py-6 text-center text-slate-400 text-xs">No stocks near period high</td></tr>
                          : signals.near_period_high.map(s => <SignalHighLowRow key={s.asx_code} s={s} type="high" period={sigPeriod} />)}
                      </tbody>
                    </table>
                  )}
                  {sigTab === 'low' && (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-xs text-slate-400 bg-slate-50">
                          <th className="py-2 px-3 text-left">Stock</th>
                          <th className="py-2 px-3 text-right">Price</th>
                          <th className="py-2 px-3 text-right">{SIG_PERIOD_LABELS[sigPeriod]} Low</th>
                          <th className="py-2 px-3 text-right">From Low</th>
                          <th className="py-2 px-3 text-right">{retLabel}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {signals.near_period_low.length === 0
                          ? <tr><td colSpan={5} className="py-6 text-center text-slate-400 text-xs">No stocks near period low</td></tr>
                          : signals.near_period_low.map(s => <SignalHighLowRow key={s.asx_code} s={s} type="low" period={sigPeriod} />)}
                      </tbody>
                    </table>
                  )}
                  {sigTab === 'volume' && (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-xs text-slate-400 bg-slate-50">
                          <th className="py-2 px-3 text-left">Stock</th>
                          <th className="py-2 px-3 text-left hidden sm:table-cell">Sector</th>
                          <th className="py-2 px-3 text-right">Price</th>
                          <th className="py-2 px-3 text-right">Volume</th>
                          <th className="py-2 px-3 text-right">vs 20D Avg</th>
                          <th className="py-2 px-3 text-right">{retLabel}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {signals.volume_surge.length === 0
                          ? <tr><td colSpan={6} className="py-6 text-center text-slate-400 text-xs">No volume surges detected today</td></tr>
                          : signals.volume_surge.map(s => <VolSurgeRow key={s.asx_code} s={s} period={sigPeriod} />)}
                      </tbody>
                    </table>
                  )}
                </>
              )
            })()}
          </>
        ) : (
          <div className="py-6 text-center text-slate-400 text-sm">Failed to load signals</div>
        )}
      </div>

      {/* Most Active + Heavy Buying + Heavy Selling */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TableCard title="Most Active by Volume" icon={Activity}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left w-6">#</th>
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-right">Price</th>
                <th className="py-2 px-3 text-right">Volume</th>
                <th className="py-2 px-3 text-right">vs 20D</th>
              </tr>
            </thead>
            <tbody>
              {data.most_active.map((s, i) => <ActiveRow key={s.asx_code} s={s} rank={i + 1} />)}
            </tbody>
          </table>
        </TableCard>

        <TableCard title="Heavy Buying" icon={ArrowUp}>
          <div className="px-4 py-1.5 bg-emerald-50 border-b border-emerald-100">
            <p className="text-xs text-emerald-700">Volume surge + price rising — potential overbought</p>
          </div>
          {data.heavy_buying.length === 0 ? (
            <div className="py-8 text-center text-sm text-slate-400">No heavy buying detected today</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-400 bg-slate-50">
                  <th className="py-2 px-3 text-left w-6">#</th>
                  <th className="py-2 px-3 text-left">Stock</th>
                  <th className="py-2 px-3 text-right">Price</th>
                  <th className="py-2 px-3 text-right">Vol Ratio</th>
                  <th className="py-2 px-3 text-right">1W</th>
                </tr>
              </thead>
              <tbody>
                {data.heavy_buying.map((s, i) => <VolumePressureRow key={s.asx_code} s={s} rank={i + 1} type="buying" />)}
              </tbody>
            </table>
          )}
        </TableCard>

        <TableCard title="Heavy Selling" icon={ArrowDown}>
          <div className="px-4 py-1.5 bg-red-50 border-b border-red-100">
            <p className="text-xs text-red-700">Volume surge + price falling — potential oversold bounce</p>
          </div>
          {data.heavy_selling.length === 0 ? (
            <div className="py-8 text-center text-sm text-slate-400">No heavy selling detected today</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-400 bg-slate-50">
                  <th className="py-2 px-3 text-left w-6">#</th>
                  <th className="py-2 px-3 text-left">Stock</th>
                  <th className="py-2 px-3 text-right">Price</th>
                  <th className="py-2 px-3 text-right">Vol Ratio</th>
                  <th className="py-2 px-3 text-right">1W</th>
                </tr>
              </thead>
              <tbody>
                {data.heavy_selling.map((s, i) => <VolumePressureRow key={s.asx_code} s={s} rank={i + 1} type="selling" />)}
              </tbody>
            </table>
          )}
        </TableCard>
      </div>

      {/* Anomaly Feed */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-700">Market Anomalies</h2>
            {anomalies.length > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                {anomalies.length} active
              </span>
            )}
          </div>
          <div className="flex gap-1 bg-slate-100 rounded-lg p-1 flex-wrap">
            {([
              ['all',                      'All'],
              ['VALUE_GROWTH',             'Value Growth'],
              ['OVERSOLD_QUALITY',         'Oversold Quality'],
              ['OVERBOUGHT_WEAK',          'Overbought Weak'],
              ['PRICE_EARNINGS_DIVERGENCE','PE Divergence'],
              ['DIVIDEND_YIELD_SPIKE',     'Yield Spike'],
            ] as const).map(([f, label]) => (
              <button key={f} onClick={() => { setAnomalyFilter(f); loadAnomalies(f) }}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors ${anomalyFilter === f ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                {label}
              </button>
            ))}
          </div>
        </div>
        {anomaliesLoading ? (
          <div className="h-40 flex items-center justify-center text-slate-400 text-sm">Loading…</div>
        ) : anomalies.length === 0 ? (
          <div className="py-8 text-center text-sm text-slate-400">No active anomalies detected</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-left hidden sm:table-cell">Type</th>
                <th className="py-2 px-3 text-left">Description</th>
                <th className="py-2 px-3 text-right">Price</th>
                <th className="py-2 px-3 text-right">1D</th>
                <th className="py-2 px-3 text-right hidden md:table-cell">Severity</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.slice(0, 30).map((a, i) => {
                const sevColor =
                  a.severity === 'high'   ? 'bg-red-100 text-red-700' :
                  a.severity === 'medium' ? 'bg-amber-100 text-amber-700' :
                                            'bg-slate-100 text-slate-600'
                return (
                  <tr key={i} className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3">
                      <Link href={`/company/${a.asx_code}`} className="font-semibold text-blue-600 hover:underline">{a.asx_code}</Link>
                      <div className="text-xs text-slate-500 truncate max-w-[90px]">{a.company_name}</div>
                    </td>
                    <td className="py-2 px-3 hidden sm:table-cell">
                      <span className="text-xs text-slate-500">{a.flag_type.replace(/_/g, ' ')}</span>
                    </td>
                    <td className="py-2 px-3 text-xs text-slate-600 max-w-[200px]">{a.description}</td>
                    <td className="py-2 px-3 text-right text-sm">{a.price != null ? `$${a.price.toFixed(3)}` : '—'}</td>
                    <td className={`py-2 px-3 text-right text-sm font-medium ${a.return_1d != null ? (a.return_1d >= 0 ? 'text-emerald-600' : 'text-red-500') : 'text-slate-400'}`}>
                      {a.return_1d != null ? `${a.return_1d >= 0 ? '+' : ''}${a.return_1d.toFixed(2)}%` : '—'}
                    </td>
                    <td className="py-2 px-3 text-right hidden md:table-cell">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sevColor}`}>
                        {a.severity}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
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
