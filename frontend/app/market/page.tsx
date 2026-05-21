'use client'
import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import {
  TrendingUp, TrendingDown, Activity, BarChart2,
  Calendar, RefreshCw, ArrowUp, ArrowDown, Zap, AlertTriangle,
  ExternalLink, Lock,
} from 'lucide-react'
import { HelpDrawer } from '@/components/HelpDrawer'
import { MARKET_SECTIONS } from '@/lib/helpContent'
import {
  getMarketDashboard, getMarketMovers, getMarketSignals, getMarketAnomalies,
  getVolumeActivity,
  MarketDashboard, DashboardStock, ActiveStock, VolumePressureStock,
  VolumeActivityResponse,
  ExDivStock, MoverStock, SignalStock, AnomalyFlag,
} from '@/lib/api'
import { ANOMALY_TYPES } from '@/lib/constants'
import { useAuth } from '@/lib/auth'

// ── Anomaly tooltips ──────────────────────────────────────────────────────────
const ANOMALY_TOOLTIPS: Record<string, string> = {
  'PRICE_EARNINGS_DIVERGENCE': 'Price is diverging from what earnings justify — potential mispricing opportunity',
  'HIGH_SHORT_INTEREST':       'High proportion of float is sold short — squeeze risk or confirmed bearish signal',
  'OVERSOLD_QUALITY':          'High-quality stock that is technically oversold — potential snap-back candidate',
  'OVERBOUGHT_WEAK':           'Weak fundamentals but technically overbought — elevated reversal risk',
  'DIVIDEND_YIELD_SPIKE':      'Yield has spiked — may signal a price drop, special dividend, or elevated payout risk',
  'VALUE_GROWTH':              'Stock is cheap (low P/E) but growing earnings — a rare and valuable combination',
  'SHORT_SQUEEZE_RISK':        'Short interest jumped sharply in one week — elevated squeeze or distribution risk',
}

// Anomaly type → closest screener preset
const ANOMALY_SCREENER: Record<string, string> = {
  'VALUE_GROWTH':              'value_franked',
  'OVERSOLD_QUALITY':          'rsi_oversold',
  'OVERBOUGHT_WEAK':           'rsi_overbought',
  'PRICE_EARNINGS_DIVERGENCE': 'quality_undervalued',
  'DIVIDEND_YIELD_SPIKE':      'franking_optimiser',
  'HIGH_SHORT_INTEREST':       'short_interest_risk',
  'SHORT_SQUEEZE_RISK':        'short_interest_risk',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  // Extreme outliers (>100% or <-50%) get no extra decimals
  if (Math.abs(pct) >= 100) return (pct >= 0 ? '+' : '') + pct.toFixed(0) + '%'
  return (pct >= 0 ? '+' : '') + pct.toFixed(decimals) + '%'
}

function fmtPctRaw(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  if (Math.abs(v) >= 100) return (v >= 0 ? '+' : '') + v.toFixed(0) + '%'
  return (v >= 0 ? '+' : '') + v.toFixed(decimals) + '%'
}

function fmtCap(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1_000_000_000) return '$' + (v / 1_000_000_000).toFixed(1) + 'T'
  if (v >= 1_000_000)     return '$' + (v / 1_000_000).toFixed(0) + 'B'
  if (v >= 1_000)         return '$' + (v / 1_000).toFixed(0) + 'M'
  return '$' + v.toFixed(0) + 'K'
}

function fmtVol(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M'
  if (v >= 1_000)     return (v / 1_000).toFixed(0) + 'K'
  return v.toString()
}

function fmtPrice(v: number | null): string {
  if (v == null) return '—'
  return '$' + v.toFixed(2)
}

function retColor(v: number | null): string {
  if (v == null) return 'text-slate-500'
  if (v > 0)  return 'text-emerald-600'
  if (v < 0)  return 'text-red-500'
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

// ── "Open in Screener" button ─────────────────────────────────────────────────
function ScreenerLink({ href, label = 'Open in Screener' }: { href: string; label?: string }) {
  return (
    <Link href={href}
      className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:underline font-medium whitespace-nowrap">
      <ExternalLink className="w-3 h-3" />
      {label}
    </Link>
  )
}

// ── Pro gate overlay ──────────────────────────────────────────────────────────
function ProGate({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative">
      <div className="blur-sm pointer-events-none select-none" style={{ maxHeight: 220, overflow: 'hidden' }}>
        {children}
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/85 rounded-b-xl gap-3">
        <Lock className="w-6 h-6 text-blue-500" />
        <div className="text-center">
          <p className="text-sm font-semibold text-slate-800">Pro Feature</p>
          <p className="text-xs text-slate-500 mt-0.5">Upgrade to access full volume activity, market signals, and anomalies.</p>
        </div>
        <Link href="/pricing"
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg transition-colors">
          Upgrade to Pro →
        </Link>
      </div>
    </div>
  )
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

type MoverRetKey = 'return_1d' | 'return_1w' | 'return_1m' | 'return_3m'
function MoverRow({ s, rank, retKey }: { s: MoverStock; rank: number; retKey: MoverRetKey }) {
  const ret = s[retKey]
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

function TableCard({ title, icon: Icon, action, children, className }: {
  title: string; icon: React.ElementType; action?: React.ReactNode; children: React.ReactNode; className?: string
}) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 overflow-hidden ${className ?? ''}`}>
      <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-slate-500" />
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
        </div>
        {action}
      </div>
      <div className="overflow-x-auto">{children}</div>
    </div>
  )
}

// ── Pill tab ──────────────────────────────────────────────────────────────────
function TabPills<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void
  options: { value: T; label: string }[]
}) {
  return (
    <div className="flex gap-1 bg-slate-100 rounded-lg p-1 flex-wrap">
      {options.map(o => (
        <button key={o.value} onClick={() => onChange(o.value)}
          className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors ${value === o.value ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

// ── Types ─────────────────────────────────────────────────────────────────────
type Period    = '1d' | '1w' | '1m' | '3m'
type SigPeriod = '1d' | '1w' | '1m' | '3m' | '52w'
type CapTier   = 'asx300' | 'all' | 'mega' | 'large' | 'mid' | 'small' | 'micro' | 'nano'

const PERIOD_OPTIONS: { value: Period; label: string }[] = [
  { value: '1d', label: '1D' }, { value: '1w', label: '1W' },
  { value: '1m', label: '1M' }, { value: '3m', label: '3M' },
]
const SIG_PERIOD_OPTIONS: { value: SigPeriod; label: string }[] = [
  { value: '1d', label: '1D' }, { value: '1w', label: '1W' }, { value: '1m', label: '1M' },
  { value: '3m', label: '3M' }, { value: '52w', label: '52W' },
]
const CAP_TIER_OPTIONS: { value: CapTier; label: string }[] = [
  { value: 'asx300', label: 'ASX 300+' },
  { value: 'all',    label: 'All Sizes' },
  { value: 'mega',   label: 'Mega ≥$50B' },
  { value: 'large',  label: 'Large $10B–$50B' },
  { value: 'mid',    label: 'Mid $2B–$10B' },
  { value: 'small',  label: 'Small $300M–$2B' },
  { value: 'micro',  label: 'Micro $50M–$300M' },
  { value: 'nano',   label: 'Nano <$50M' },
]

// API cap_tier value — 'asx300' and 'all' both send no cap_tier to API ('all' = default)
function apiCapTier(t: CapTier): 'mega' | 'large' | 'mid' | 'small' | 'micro' | 'nano' | 'asx300' | undefined {
  if (t === 'all') return undefined
  return t as 'mega' | 'large' | 'mid' | 'small' | 'micro' | 'nano' | 'asx300'
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketPage() {
  const { user } = useAuth()
  const userPlan  = user?.plan ?? 'free'
  const isPro     = ['pro', 'premium', 'enterprise_pro', 'enterprise_premium'].includes(userPlan)

  const [data, setData]       = useState<MarketDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const [moverPeriod, setMoverPeriod] = useState<Period>('1w')
  const [capTier, setCapTier]         = useState<CapTier>('asx300')   // default: ≥$300M
  const [movers, setMovers]           = useState<{ gainers: MoverStock[]; losers: MoverStock[] } | null>(null)
  const [moversLoading, setMoversLoading] = useState(false)

  const [volumeCapTier, setVolumeCapTier]   = useState<CapTier>('asx300')
  const [volumeActivity, setVolumeActivity] = useState<VolumeActivityResponse | null>(null)
  const [volumeLoading, setVolumeLoading]   = useState(false)

  const [sigPeriod, setSigPeriod] = useState<SigPeriod>('52w')
  const [signals, setSignals]     = useState<{ near_period_high: SignalStock[]; near_period_low: SignalStock[]; volume_surge: SignalStock[] } | null>(null)
  const [signalsLoading, setSignalsLoading] = useState(false)
  const [sigTab, setSigTab]       = useState<'high' | 'low' | 'volume'>('high')

  const [anomalies, setAnomalies]             = useState<AnomalyFlag[]>([])
  const [anomaliesLoading, setAnomaliesLoading] = useState(false)
  const [anomalyFilter, setAnomalyFilter]     = useState('all')

  const loadDashboard = async () => {
    setLoading(true); setError(null)
    try { setData(await getMarketDashboard()); setLastRefresh(new Date()) }
    catch { setError('Failed to load market data.') }
    finally { setLoading(false) }
  }

  const loadMovers = useCallback(async (period: Period, tier: CapTier) => {
    setMoversLoading(true)
    try { setMovers(await getMarketMovers(period, 10, apiCapTier(tier))) }
    catch { /* keep previous */ }
    finally { setMoversLoading(false) }
  }, [])

  const loadVolumeActivity = useCallback(async (tier: CapTier) => {
    setVolumeLoading(true)
    try { setVolumeActivity(await getVolumeActivity(apiCapTier(tier))) }
    catch { /* keep previous */ }
    finally { setVolumeLoading(false) }
  }, [])

  const loadSignals = useCallback(async (period: SigPeriod) => {
    setSignalsLoading(true)
    try { setSignals(await getMarketSignals(period)) }
    catch { /* keep previous */ }
    finally { setSignalsLoading(false) }
  }, [])

  const loadAnomalies = useCallback(async (flagType?: string) => {
    setAnomaliesLoading(true)
    try {
      const res = await getMarketAnomalies(100, flagType === 'all' ? undefined : flagType)
      setAnomalies(res.flags)
    } catch { /* keep previous */ }
    finally { setAnomaliesLoading(false) }
  }, [])

  useEffect(() => {
    loadDashboard(); loadSignals('52w'); loadAnomalies(); loadVolumeActivity('asx300')
  }, [loadSignals, loadAnomalies, loadVolumeActivity])
  useEffect(() => { loadMovers(moverPeriod, capTier) }, [moverPeriod, capTier, loadMovers])
  useEffect(() => { loadSignals(sigPeriod) }, [sigPeriod, loadSignals])
  useEffect(() => { loadVolumeActivity(volumeCapTier) }, [volumeCapTier, loadVolumeActivity])

  const refreshAll = () => {
    loadDashboard()
    loadMovers(moverPeriod, capTier)
    loadSignals(sigPeriod)
    loadAnomalies(anomalyFilter)
    loadVolumeActivity(volumeCapTier)
    setLastRefresh(new Date())
  }

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

  const refreshedAt = lastRefresh
    ? lastRefresh.toLocaleTimeString('en-AU', { timeStyle: 'short' })
    : null

  const retKey: MoverRetKey =
    moverPeriod === '1d' ? 'return_1d' :
    moverPeriod === '1w' ? 'return_1w' :
    moverPeriod === '3m' ? 'return_3m' : 'return_1m'

  // Screener URL for current mover period
  const moverScreenerUrl = moverPeriod === '1d' || moverPeriod === '1w'
    ? '/screener?preset=momentum' : '/screener?preset=high_growth'

  // Signal tab → screener preset
  const sigScreenerPreset = sigTab === 'high' ? 'new_52w_highs' : sigTab === 'low' ? 'new_52w_lows' : 'volume_breakout'

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Market Overview</h1>
          <div className="flex items-center gap-3 mt-0.5 flex-wrap">
            {builtAt && (
              <p className="text-xs text-slate-400">Data as at {builtAt} AEST</p>
            )}
            {refreshedAt && (
              <p className="text-xs text-slate-400">· Last refreshed {refreshedAt}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <HelpDrawer sections={MARKET_SECTIONS} />
          <button onClick={refreshAll}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50">
            <RefreshCw className="w-3.5 h-3.5" />Refresh
          </button>
        </div>
      </div>

      {/* ── Index Snapshots ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <IndexCard label="ASX 200" snap={data.asx200} />
        <IndexCard label="ASX 300" snap={data.asx300} />
      </div>

      {/* ── Sector Heatmap ─────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <BarChart2 className="w-4 h-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-700">Sector Heatmap — 1W Performance</h2>
          </div>
          <span className="text-xs text-slate-400">Click a sector to screen it</span>
        </div>
        <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
          {data.sector_heatmap.map(s => (
            <Link
              key={s.sector}
              href={`/screener?sector=${encodeURIComponent(s.sector)}`}
              title={`Screen ${s.sector} stocks in Screener`}
              className={`rounded-lg p-3 text-center transition-opacity hover:opacity-90 hover:ring-2 hover:ring-white/50 cursor-pointer ${heatColor(s.avg_return_1w)}`}
            >
              <div className="text-xs font-semibold leading-tight mb-1">{s.sector}</div>
              <div className="text-sm font-bold">{fmtPct(s.avg_return_1w)}</div>
              <div className="text-xs opacity-75 mt-0.5">{s.stock_count} stocks</div>
            </Link>
          ))}
        </div>
      </div>

      {/* ── Top Movers ─────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-slate-500" />
            <h2 className="text-sm font-semibold text-slate-700">Top Movers</h2>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <TabPills value={capTier} onChange={setCapTier} options={CAP_TIER_OPTIONS} />
            <TabPills value={moverPeriod} onChange={setMoverPeriod} options={PERIOD_OPTIONS} />
          </div>
        </div>
        {moversLoading ? (
          <div className="h-48 flex items-center justify-center text-slate-400 text-sm">Loading…</div>
        ) : !movers || (movers.gainers.length === 0 && movers.losers.length === 0) ? (
          <div className="h-32 flex items-center justify-center text-slate-400 text-sm">
            No mover data available for this period
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-slate-100">
            {/* Gainers */}
            <div>
              <div className="px-4 py-2 bg-emerald-50 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ArrowUp className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="text-xs font-semibold text-emerald-700">Top Gainers — {moverPeriod.toUpperCase()}</span>
                </div>
                <ScreenerLink href={moverScreenerUrl} label="Screen Gainers" />
              </div>
              <table className="w-full text-sm">
                <thead><MoverTableHeader period={moverPeriod} retKey={retKey} /></thead>
                <tbody>
                  {movers.gainers.map((s, i) => <MoverRow key={s.asx_code} s={s} rank={i + 1} retKey={retKey} />)}
                </tbody>
              </table>
            </div>
            {/* Losers */}
            <div>
              <div className="px-4 py-2 bg-red-50 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <ArrowDown className="w-3.5 h-3.5 text-red-600" />
                  <span className="text-xs font-semibold text-red-700">Top Losers — {moverPeriod.toUpperCase()}</span>
                </div>
                <ScreenerLink href="/screener?preset=turnaround" label="Screen Losers" />
              </div>
              <table className="w-full text-sm">
                <thead><MoverTableHeader period={moverPeriod} retKey={retKey} /></thead>
                <tbody>
                  {movers.losers.map((s, i) => <MoverRow key={s.asx_code} s={s} rank={i + 1} retKey={retKey} />)}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ── Market Signals ─────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-700">Market Signals</h2>
            {!isPro && (
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-semibold">Pro</span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Signal type tabs — renamed "Near Highs" / "Near Lows" */}
            <TabPills
              value={sigTab}
              onChange={setSigTab}
              options={[
                { value: 'high',   label: '↑ Near Highs' },
                { value: 'low',    label: '↓ Near Lows'  },
                { value: 'volume', label: '⚡ Volume'     },
              ]}
            />
            <TabPills value={sigPeriod} onChange={setSigPeriod} options={SIG_PERIOD_OPTIONS} />
          </div>
        </div>

        {!isPro ? (
          <ProGate>
            {/* Fake blurred rows */}
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-right">Price</th>
                <th className="py-2 px-3 text-right">Period High</th>
                <th className="py-2 px-3 text-right">From High</th>
                <th className="py-2 px-3 text-right">1W</th>
              </tr></thead>
              <tbody>
                {[['BHP', 'BHP Group', '43.20', '+2.1%', '+4.5%'],
                  ['CBA', 'Commonwealth Bank', '141.00', '-0.5%', '+1.8%'],
                  ['CSL', 'CSL Limited', '285.50', '+0.8%', '+3.2%'],
                ].map(([code, name, price, from, ret]) => (
                  <tr key={code} className="border-t border-slate-100">
                    <td className="py-2 px-3"><span className="font-semibold text-blue-600">{code}</span><div className="text-xs text-slate-400">{name}</div></td>
                    <td className="py-2 px-3 text-right">${price}</td>
                    <td className="py-2 px-3 text-right text-slate-400">—</td>
                    <td className="py-2 px-3 text-right text-emerald-600">{from}</td>
                    <td className="py-2 px-3 text-right text-emerald-600">{ret}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ProGate>
        ) : signalsLoading ? (
          <div className="h-48 flex items-center justify-center text-slate-400 text-sm">Loading…</div>
        ) : signals ? (
          <>
            {/* Action bar */}
            <div className="px-4 py-2 bg-slate-50 border-b border-slate-100 flex justify-end">
              <ScreenerLink href={`/screener?preset=${sigScreenerPreset}`} />
            </div>
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
                          <th className="py-2 px-3 text-right">{SIG_PERIOD_OPTIONS.find(o => o.value === sigPeriod)?.label} High</th>
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
                          <th className="py-2 px-3 text-right">{SIG_PERIOD_OPTIONS.find(o => o.value === sigPeriod)?.label} Low</th>
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

      {/* ── Volume Activity ─────────────────────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-slate-400" />
            <span className="text-sm font-semibold text-slate-700">Volume Activity</span>
            {!isPro && (
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-semibold">Pro</span>
            )}
          </div>
          <TabPills value={volumeCapTier} onChange={setVolumeCapTier} options={CAP_TIER_OPTIONS} />
        </div>

        {!isPro ? (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <ProGate>
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 divide-y lg:divide-y-0 lg:divide-x divide-slate-100">
                {['Most Active by Volume', 'Heavy Buying', 'Heavy Selling'].map(t => (
                  <div key={t} className="p-4">
                    <div className="font-semibold text-sm text-slate-700 mb-2">{t}</div>
                    {[1,2,3].map(i => (
                      <div key={i} className="flex justify-between py-1.5 border-t border-slate-50">
                        <span className="text-blue-600 font-semibold text-sm">XXX</span>
                        <span className="text-slate-400 text-sm">$0.00</span>
                        <span className="text-emerald-600 text-sm">+0.0%</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </ProGate>
          </div>
        ) : volumeLoading ? (
          <div className="h-48 flex items-center justify-center text-slate-400 text-sm">Loading…</div>
        ) : (
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
                  {(volumeActivity?.most_active ?? []).length === 0
                    ? <tr><td colSpan={5} className="py-8 text-center text-sm text-slate-400">No stocks in this tier</td></tr>
                    : (volumeActivity?.most_active ?? []).map((s, i) => <ActiveRow key={s.asx_code} s={s} rank={i + 1} />)}
                </tbody>
              </table>
            </TableCard>

            <TableCard
              title="Heavy Buying"
              icon={ArrowUp}
              action={<ScreenerLink href="/screener?preset=volume_breakout" />}
            >
              <div className="px-4 py-1.5 bg-emerald-50 border-b border-emerald-100">
                <p className="text-xs text-emerald-700">Volume surge + price rising — accumulation signal</p>
              </div>
              {(volumeActivity?.heavy_buying ?? []).length === 0 ? (
                <div className="py-8 text-center text-sm text-slate-400">
                  No heavy buying detected{volumeCapTier !== 'all' && volumeCapTier !== 'asx300' ? ' in this tier' : ' today'}
                </div>
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
                    {(volumeActivity?.heavy_buying ?? []).map((s, i) => <VolumePressureRow key={s.asx_code} s={s} rank={i + 1} type="buying" />)}
                  </tbody>
                </table>
              )}
            </TableCard>

            <TableCard
              title="Heavy Selling"
              icon={ArrowDown}
              action={<ScreenerLink href="/screener?preset=rsi_oversold" />}
            >
              <div className="px-4 py-1.5 bg-red-50 border-b border-red-100">
                <p className="text-xs text-red-700">Volume surge + price falling — potential oversold bounce</p>
              </div>
              {(volumeActivity?.heavy_selling ?? []).length === 0 ? (
                <div className="py-8 text-center text-sm text-slate-400">
                  No heavy selling detected{volumeCapTier !== 'all' && volumeCapTier !== 'asx300' ? ' in this tier' : ' today'}
                </div>
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
                    {(volumeActivity?.heavy_selling ?? []).map((s, i) => <VolumePressureRow key={s.asx_code} s={s} rank={i + 1} type="selling" />)}
                  </tbody>
                </table>
              )}
            </TableCard>
          </div>
        )}
      </div>

      {/* ── Anomaly Feed ───────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-700">Market Anomalies</h2>
            {anomalies.length > 0 && isPro && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                {anomalies.length} active
              </span>
            )}
            {!isPro && (
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-semibold">Pro</span>
            )}
          </div>
          <div className="flex gap-1 bg-slate-100 rounded-lg p-1 flex-wrap">
            {ANOMALY_TYPES.map(({ value, label }) => (
              <button key={value}
                onClick={() => { setAnomalyFilter(value); loadAnomalies(value) }}
                title={ANOMALY_TOOLTIPS[value] ?? ''}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-colors ${anomalyFilter === value ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                {label}
              </button>
            ))}
          </div>
        </div>

        {!isPro ? (
          <ProGate>
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-slate-400 bg-slate-50">
                <th className="py-2 px-3 text-left">Stock</th>
                <th className="py-2 px-3 text-left hidden sm:table-cell">Type</th>
                <th className="py-2 px-3 text-left">Description</th>
                <th className="py-2 px-3 text-right">Price</th>
                <th className="py-2 px-3 text-right">1W</th>
                <th className="py-2 px-3 text-right hidden md:table-cell">Severity</th>
              </tr></thead>
              <tbody>
                {[
                  ['BHP',  'BHP Group',           'VALUE_GROWTH',              'Trading at 8.2x PE with 14% earnings growth — strong value signal', '43.20', '+4.2%', 'high'],
                  ['WBC',  'Westpac Banking',      'OVERSOLD_QUALITY',          'RSI 26 — technically oversold quality bank stock', '26.80', '-3.1%', 'medium'],
                  ['RIO',  'Rio Tinto',            'PRICE_EARNINGS_DIVERGENCE', 'Price fell 8% while EPS guidance raised — PE now 9.1x vs sector 14x', '118.50', '-2.4%', 'high'],
                ].map(([code, name, type, desc, price, ret, sev]) => (
                  <tr key={code} className="border-t border-slate-100">
                    <td className="py-2 px-3"><span className="font-semibold text-blue-600">{code}</span><div className="text-xs text-slate-400">{name}</div></td>
                    <td className="py-2 px-3 hidden sm:table-cell"><span className="text-xs text-slate-500">{(type as string).replace(/_/g, ' ')}</span></td>
                    <td className="py-2 px-3 text-xs text-slate-600 max-w-[200px]">{desc}</td>
                    <td className="py-2 px-3 text-right text-sm">${price}</td>
                    <td className="py-2 px-3 text-right text-sm font-medium text-emerald-600">{ret}</td>
                    <td className="py-2 px-3 text-right hidden md:table-cell"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sev === 'high' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>{sev}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ProGate>
        ) : anomaliesLoading ? (
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
                <th className="py-2 px-3 text-right">1W</th>
                <th className="py-2 px-3 text-right hidden md:table-cell">Severity</th>
                <th className="py-2 px-3 text-right hidden lg:table-cell">Screen</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.slice(0, 30).map((a, i) => {
                const sevColor =
                  a.severity === 'high'   ? 'bg-red-100 text-red-700' :
                  a.severity === 'medium' ? 'bg-amber-100 text-amber-700' :
                                            'bg-slate-100 text-slate-600'
                const screenerPreset = ANOMALY_SCREENER[a.flag_type]
                const tooltip = ANOMALY_TOOLTIPS[a.flag_type]
                return (
                  <tr key={i} className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3">
                      <Link href={`/company/${a.asx_code}`} className="font-semibold text-blue-600 hover:underline">{a.asx_code}</Link>
                      <div className="text-xs text-slate-500 truncate max-w-[90px]">{a.company_name}</div>
                    </td>
                    <td className="py-2 px-3 hidden sm:table-cell">
                      <span
                        className="text-xs text-slate-500 cursor-help border-b border-dotted border-slate-300"
                        title={tooltip ?? a.flag_type.replace(/_/g, ' ')}
                      >
                        {a.flag_type.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-xs text-slate-600 max-w-[200px]">{a.description}</td>
                    <td className="py-2 px-3 text-right text-sm">{a.price != null ? `$${a.price.toFixed(2)}` : '—'}</td>
                    <td className={`py-2 px-3 text-right text-sm font-medium ${a.return_1w != null ? (a.return_1w >= 0 ? 'text-emerald-600' : 'text-red-500') : 'text-slate-400'}`}>
                      {a.return_1w != null ? fmtPct(a.return_1w) : '—'}
                    </td>
                    <td className="py-2 px-3 text-right hidden md:table-cell">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sevColor}`}>
                        {a.severity}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right hidden lg:table-cell">
                      {screenerPreset && (
                        <ScreenerLink href={`/screener?preset=${screenerPreset}`} label="Screen" />
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Upcoming Ex-Dividend Dates ───────────────────────────────────── */}
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
