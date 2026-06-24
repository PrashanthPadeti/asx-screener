'use client'
import { useState, useCallback, useEffect } from 'react'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { useRouter } from 'next/navigation'
import {
  getAdminMovers,
  type AdminMoverPeriod,
  type AdminCapTier,
  type AdminMoverStock,
} from '@/lib/api'
import { TrendingUp, TrendingDown, RefreshCw } from 'lucide-react'

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtPct = (v: number | null) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`

const fmtPrice = (v: number | null) =>
  v == null ? '—' : `$${v < 1 ? v.toFixed(3) : v.toFixed(2)}`

const fmtCap = (v: number | null) => {
  if (v == null) return '—'
  const b = v / 1_000_000_000
  if (b >= 1) return `$${b.toFixed(1)}B`
  const m = v / 1_000_000
  return `$${m.toFixed(0)}M`
}

const retColor = (v: number | null) =>
  v == null ? 'text-slate-400' : v > 0 ? 'text-emerald-600' : v < 0 ? 'text-red-500' : 'text-slate-500'

// ── Period options ────────────────────────────────────────────────────────────

const PERIODS: { value: AdminMoverPeriod; label: string }[] = [
  { value: '1d',  label: '1D'  },
  { value: '1w',  label: '1W'  },
  { value: '1m',  label: '1M'  },
  { value: '3m',  label: '3M'  },
  { value: '6m',  label: '6M'  },
  { value: '1y',  label: '1Y'  },
  { value: 'ytd', label: 'YTD' },
  { value: '2y',  label: '2Y'  },
  { value: '3y',  label: '3Y'  },
  { value: '5y',  label: '5Y'  },
  { value: '10y', label: '10Y' },
]

const CAP_TIERS: { value: AdminCapTier | 'all'; label: string }[] = [
  { value: 'all',   label: 'All Sizes'      },
  { value: 'mega',  label: 'Mega ≥$50B'     },
  { value: 'large', label: 'Large $10B–$50B' },
  { value: 'mid',   label: 'Mid $2B–$10B'   },
  { value: 'small', label: 'Small $300M–$2B' },
  { value: 'micro', label: 'Micro $50M–$300M' },
  { value: 'nano',  label: 'Nano <$50M'     },
]

// ── Components ────────────────────────────────────────────────────────────────

function MoverTable({
  stocks,
  side,
  period,
}: {
  stocks: AdminMoverStock[]
  side: 'gainers' | 'losers'
  period: AdminMoverPeriod
}) {
  const pLabel = period.toUpperCase()
  const isGainer = side === 'gainers'
  const hasPeriodHiLo = ['1d', '1w', '1m', '3m'].includes(period)

  return (
    <div className="flex-1 min-w-0">
      <div className={`flex items-center gap-2 px-4 py-2 rounded-t-lg ${isGainer ? 'bg-emerald-50' : 'bg-red-50'}`}>
        {isGainer
          ? <TrendingUp className="w-4 h-4 text-emerald-600" />
          : <TrendingDown className="w-4 h-4 text-red-500" />}
        <span className={`text-sm font-semibold ${isGainer ? 'text-emerald-700' : 'text-red-700'}`}>
          Top {isGainer ? 'Gainers' : 'Losers'} — {pLabel}
        </span>
        <span className="ml-auto text-xs text-slate-400">{stocks.length} stocks</span>
      </div>

      <div className="overflow-x-auto border border-t-0 rounded-b-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-400 bg-slate-50 border-b">
              <th className="py-2 px-3 text-left w-8">#</th>
              <th className="py-2 px-3 text-left">Stock</th>
              <th className="py-2 px-3 text-left">Sector</th>
              <th className="py-2 px-3 text-right">Price</th>
              {hasPeriodHiLo && (
                <>
                  <th className="py-2 px-3 text-right text-emerald-600">{pLabel} High</th>
                  <th className="py-2 px-3 text-right text-red-500">{pLabel} Low</th>
                </>
              )}
              <th className="py-2 px-3 text-right">Mkt Cap</th>
              <th className={`py-2 px-3 text-right font-semibold ${isGainer ? 'text-emerald-600' : 'text-red-500'}`}>
                {pLabel} Chg
              </th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((s, i) => (
              <tr key={s.asx_code} className="border-t border-slate-100 hover:bg-slate-50 transition-colors">
                <td className="py-2 px-3 text-xs text-slate-400">{i + 1}</td>
                <td className="py-2 px-3">
                  <Link
                    href={`/company/${s.asx_code}`}
                    className="font-semibold text-blue-600 hover:underline"
                    target="_blank"
                  >
                    {s.asx_code}
                  </Link>
                  <div className="text-xs text-slate-500 truncate max-w-[130px]">{s.company_name}</div>
                </td>
                <td className="py-2 px-3 text-xs text-slate-500">
                  {s.sector ?? '—'}
                </td>
                <td className="py-2 px-3 text-right">{fmtPrice(s.price)}</td>
                {hasPeriodHiLo && (
                  <>
                    <td className="py-2 px-3 text-right text-emerald-600">
                      {fmtPrice(s.period_high)}
                    </td>
                    <td className="py-2 px-3 text-right text-red-500">
                      {fmtPrice(s.period_low)}
                    </td>
                  </>
                )}
                <td className="py-2 px-3 text-right text-xs text-slate-500">{fmtCap(s.market_cap)}</td>
                <td className={`py-2 px-3 text-right font-semibold ${retColor(s.period_return)}`}>
                  {fmtPct(s.period_return)}
                </td>
              </tr>
            ))}
            {stocks.length === 0 && (
              <tr>
                <td colSpan={hasPeriodHiLo ? 8 : 6} className="py-8 text-center text-slate-400 text-sm">
                  No data available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminMoversPage() {
  const { user, loading: authLoading } = useAuth()
  const router = useRouter()

  const [period, setPeriod]   = useState<AdminMoverPeriod>('1w')
  const [capTier, setCapTier] = useState<AdminCapTier | 'all'>('all')
  const [limit, setLimit]     = useState(50)
  const [gainers, setGainers] = useState<AdminMoverStock[]>([])
  const [losers, setLosers]   = useState<AdminMoverStock[]>([])
  const [loading, setLoading] = useState(false)
  const [lastFetch, setLastFetch] = useState<Date | null>(null)

  useEffect(() => {
    if (!authLoading && !user?.is_admin) router.replace('/admin')
  }, [authLoading, user, router])

  const load = useCallback(async (p: AdminMoverPeriod, ct: AdminCapTier | 'all', lim: number) => {
    setLoading(true)
    try {
      const res = await getAdminMovers(p, lim, ct === 'all' ? undefined : ct)
      setGainers(res.gainers)
      setLosers(res.losers)
      setLastFetch(new Date())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (user?.is_admin) load(period, capTier, limit)
  }, [period, capTier, limit, load, user])

  if (authLoading || !user?.is_admin) return null

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-6">
      <div className="max-w-[1600px] mx-auto space-y-4">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800">Top Movers — Extended</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Admin view · live from screener.universe
              {lastFetch && ` · last updated ${lastFetch.toLocaleTimeString()}`}
            </p>
          </div>
          <button
            onClick={() => load(period, capTier, limit)}
            disabled={loading}
            className="flex items-center gap-1.5 text-xs bg-white border border-slate-200 rounded-lg px-3 py-2 hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Controls */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
          {/* Period tabs */}
          <div className="flex flex-wrap gap-1.5">
            {PERIODS.map(p => (
              <button
                key={p.value}
                onClick={() => setPeriod(p.value)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  period === p.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Cap tier + limit */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-1">
              {CAP_TIERS.map(ct => (
                <button
                  key={ct.value}
                  onClick={() => setCapTier(ct.value)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    capTier === ct.value
                      ? 'bg-slate-700 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {ct.label}
                </button>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs text-slate-500">Show top</span>
              {[25, 50, 100].map(n => (
                <button
                  key={n}
                  onClick={() => setLimit(n)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    limit === n
                      ? 'bg-slate-700 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Tables */}
        {loading ? (
          <div className="flex justify-center py-16 text-slate-400 text-sm">Loading movers…</div>
        ) : (
          <div className="flex flex-col gap-4">
            <MoverTable stocks={gainers} side="gainers" period={period} />
            <MoverTable stocks={losers}  side="losers"  period={period} />
          </div>
        )}
      </div>
    </div>
  )
}
