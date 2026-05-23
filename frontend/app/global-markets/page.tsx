'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Globe, RefreshCw, ArrowLeft } from 'lucide-react'
import { getGlobalMarkets, GlobalMarketsResponse, GlobalIndexPrice, GlobalFxRate } from '@/lib/api'
import { PlanGate } from '@/components/PlanGate'

// ── Constants ─────────────────────────────────────────────────────────────────

const REGION_DISPLAY: Record<string, string> = {
  US:     'United States',
  Europe: 'Europe',
  Asia:   'Asia',
}

// Two-letter country codes for styled badges (no emoji dependency)
const COUNTRY_CODES: Record<string, string> = {
  'United States':  'US',
  'United Kingdom': 'GB',
  'Germany':        'DE',
  'France':         'FR',
  'Japan':          'JP',
  'Hong Kong':      'HK',
  'China':          'CN',
  'South Korea':    'KR',
}

const REGION_ICONS: Record<string, string> = {
  US:     'US',
  Europe: 'EU',
  Asia:   'AS',
}

const FX_META: Record<string, { code: string; desc: string }> = {
  AUDUSD: { code: 'USD', desc: 'US Dollar'       },
  AUDEUR: { code: 'EUR', desc: 'Euro'             },
  AUDGBP: { code: 'GBP', desc: 'British Pound'   },
  AUDJPY: { code: 'JPY', desc: 'Japanese Yen'    },
  AUDCNY: { code: 'CNY', desc: 'Chinese Yuan'    },
}

// Display order for FX pairs
const FX_ORDER = ['AUDUSD', 'AUDEUR', 'AUDGBP', 'AUDJPY', 'AUDCNY']

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null): string {
  if (v == null) return 'Pending'
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%'
}

function fmtPrice(v: number | null, large = false): string {
  if (v == null) return 'Unavailable'
  if (large || v >= 1000) return v.toLocaleString('en-AU', { maximumFractionDigits: 0 })
  if (v >= 100) return v.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v.toFixed(4)
}

function retColor(v: number | null): string {
  if (v == null) return 'text-slate-500'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-400'
}

function retBadge(v: number | null): string {
  if (v == null) return 'bg-slate-700/60 text-slate-500'
  const p = v * 100
  if (p >= 1)  return 'bg-emerald-600/30 text-emerald-400'
  if (p >= 0)  return 'bg-emerald-900/30 text-emerald-500'
  if (p >= -1) return 'bg-red-900/30 text-red-400'
  return 'bg-red-600/30 text-red-400'
}

function fmtTimestamp(d: Date): string {
  return d.toLocaleTimeString('en-AU', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: 'Australia/Sydney',
  }) + ' AEST'
}

// ── Index row ─────────────────────────────────────────────────────────────────

function CountryBadge({ country }: { country: string }) {
  const code = COUNTRY_CODES[country] ?? country.slice(0, 2).toUpperCase()
  return (
    <span className="shrink-0 w-7 h-7 flex items-center justify-center rounded-md bg-slate-700 text-[10px] font-bold text-slate-300 uppercase tracking-wide">
      {code}
    </span>
  )
}

function IndexRow({ idx }: { idx: GlobalIndexPrice }) {
  const isLargePrice = (idx.close_price ?? 0) >= 1000
  const priceStr = fmtPrice(idx.close_price, isLargePrice)
  const isPriceMissing = idx.close_price == null

  return (
    <Link
      href={`/global-markets/${idx.index_code.toLowerCase()}`}
      className="grid grid-cols-8 gap-2 px-5 py-4 border-b border-slate-700/40 hover:bg-slate-700/20 transition-colors last:border-0 group"
    >
      {/* Name + country */}
      <div className="col-span-2 flex items-center gap-2.5">
        <CountryBadge country={idx.country} />
        <div>
          <div className="text-sm font-semibold text-slate-100 group-hover:text-blue-400 transition-colors">{idx.index_name}</div>
          <div className="text-xs text-slate-500">{idx.country} · {idx.currency}</div>
        </div>
      </div>
      {/* Price + 1D */}
      <div className="col-span-2 text-right">
        <div className={`text-sm font-semibold ${isPriceMissing ? 'text-slate-500 italic' : 'text-slate-100'}`}>
          {priceStr}
        </div>
        <span className={`inline-block text-xs font-medium px-1.5 py-0.5 rounded mt-0.5 ${retBadge(idx.return_1d)}`}>
          {fmtPct(idx.return_1d)}
        </span>
      </div>
      {/* 1W */}
      <div className={`text-right text-sm font-medium ${idx.return_1w == null ? 'text-slate-500 italic text-xs' : retColor(idx.return_1w)}`}>
        {fmtPct(idx.return_1w)}
      </div>
      {/* 1M */}
      <div className={`text-right text-sm font-medium ${idx.return_1m == null ? 'text-slate-500 italic text-xs' : retColor(idx.return_1m)}`}>
        {fmtPct(idx.return_1m)}
      </div>
      {/* 3M */}
      <div className={`text-right text-sm font-medium ${idx.return_3m == null ? 'text-slate-500 italic text-xs' : retColor(idx.return_3m)}`}>
        {fmtPct(idx.return_3m)}
      </div>
      {/* YTD */}
      <div className={`text-right text-sm font-medium ${idx.return_ytd == null ? 'text-slate-500 italic text-xs' : retColor(idx.return_ytd)}`}>
        {fmtPct(idx.return_ytd)}
      </div>
    </Link>
  )
}

// ── FX card ───────────────────────────────────────────────────────────────────

function FxCard({ fx }: { fx: GlobalFxRate }) {
  const meta = FX_META[fx.fx_pair] ?? { code: fx.fx_pair.slice(3), desc: fx.fx_pair }
  const quote = fx.fx_pair.slice(3)
  const rateStr = fx.fx_pair === 'AUDJPY' ? fx.rate?.toFixed(2) : fx.rate?.toFixed(4)
  return (
    <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50 hover:border-slate-600/50 transition-colors">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-9 h-9 flex items-center justify-center rounded-lg bg-slate-700 text-[11px] font-bold text-slate-200 uppercase tracking-wide shrink-0">
          {meta.code}
        </span>
        <div>
          <div className="text-sm font-bold text-slate-100">AUD/{quote}</div>
          <div className="text-xs text-slate-500">{meta.desc}</div>
        </div>
      </div>
      <div className={`text-2xl font-bold mb-2 ${rateStr == null ? 'text-slate-500 italic text-base' : 'text-white'}`}>
        {rateStr ?? 'Unavailable'}
      </div>
      <div className="flex flex-col gap-1 text-xs">
        <div className="flex justify-between">
          <span className="text-slate-500">Today</span>
          <span className={fx.return_1d == null ? 'text-slate-500 italic' : retColor(fx.return_1d)}>{fmtPct(fx.return_1d)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">1 week</span>
          <span className={fx.return_1w == null ? 'text-slate-500 italic' : retColor(fx.return_1w)}>{fmtPct(fx.return_1w)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">1 month</span>
          <span className={fx.return_1m == null ? 'text-slate-500 italic' : retColor(fx.return_1m)}>{fmtPct(fx.return_1m)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">YTD</span>
          <span className={fx.return_ytd == null ? 'text-slate-500 italic' : retColor(fx.return_ytd)}>{fmtPct(fx.return_ytd)}</span>
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function GlobalMarketsPage() {
  const [data,        setData]        = useState<GlobalMarketsResponse | null>(null)
  const [loading,     setLoading]     = useState(true)
  const [refreshing,  setRefreshing]  = useState(false)
  const [error,       setError]       = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      setData(await getGlobalMarkets())
      setLastUpdated(new Date())
      setError(null)
    } catch {
      setError('Failed to load global markets data')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { load() }, [])

  const audusd = data?.fx_rates.find(f => f.fx_pair === 'AUDUSD')

  // Sort FX rates in preferred display order
  const sortedFx = data?.fx_rates
    ? [...data.fx_rates].sort((a, b) => {
        const ai = FX_ORDER.indexOf(a.fx_pair)
        const bi = FX_ORDER.indexOf(b.fx_pair)
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
      })
    : []

  return (
    <PlanGate required="premium" feature="Global Markets">
    <div className="min-h-screen bg-slate-950 text-slate-100">

      {/* ── Hero ─────────────────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-b from-slate-800 to-slate-900 border-b border-slate-700/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-center justify-between mb-5">
            <Link href="/market" className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors">
              <ArrowLeft className="w-4 h-4" /> Market Overview
            </Link>
            <div className="flex items-center gap-3">
              {lastUpdated && (
                <span className="text-xs text-slate-500 hidden sm:block">
                  Updated {fmtTimestamp(lastUpdated)}
                </span>
              )}
              <button
                onClick={() => load(true)}
                className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Globe className="w-7 h-7 text-blue-400 shrink-0" />
                <h1 className="text-3xl font-bold text-white">Global Markets</h1>
              </div>
              <p className="text-slate-400 text-sm">US, European and Asian indices — plus AUD exchange rates</p>
              {data?.as_of && (
                <p className="text-slate-500 text-xs mt-1">As of {data.as_of}</p>
              )}
              {lastUpdated && (
                <p className="text-slate-500 text-xs mt-0.5 sm:hidden">
                  Updated {fmtTimestamp(lastUpdated)}
                </p>
              )}
            </div>

            {/* AUD/USD prominent display */}
            {audusd && (
              <div className="sm:text-right bg-slate-800/60 rounded-xl px-5 py-3 border border-slate-700/50">
                <div className="text-xs text-slate-500 mb-0.5">AUD / USD</div>
                <div className="text-3xl font-bold text-white">{audusd.rate?.toFixed(4) ?? '—'}</div>
                <div className={`text-sm font-medium ${retColor(audusd.return_1d)}`}>
                  {fmtPct(audusd.return_1d)} today
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">

        {loading && (
          <div className="text-center py-24 text-slate-400 text-sm">Loading global markets…</div>
        )}
        {error && !loading && (
          <div className="text-center py-24 text-red-400 text-sm">{error}</div>
        )}

        {/* Region sections */}
        {data && data.regions.map(region => {
          const displayName = REGION_DISPLAY[region.region] ?? region.region
          const regionCode = REGION_ICONS[region.region] ?? region.region.slice(0, 2).toUpperCase()
          return (
            <div key={region.region} className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
              {/* Region header */}
              <div className="px-5 py-4 border-b border-slate-700/50 flex items-center gap-3">
                <span className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-700 text-[11px] font-bold text-slate-300 uppercase tracking-wide shrink-0">
                  {regionCode}
                </span>
                <h2 className="text-lg font-semibold text-white">{displayName}</h2>
                <span className="text-xs text-slate-500">· {region.indices.length} indices</span>
              </div>

              {/* Table — horizontal scroll on mobile */}
              <div className="overflow-x-auto">
                {/* Column headers */}
                <div className="grid grid-cols-8 gap-2 px-5 py-2.5 bg-slate-800/40 border-b border-slate-700/40 text-xs font-medium text-slate-500 uppercase tracking-wide min-w-[600px]">
                  <div className="col-span-2">Index</div>
                  <div className="col-span-2 text-right">Price / 1D</div>
                  <div className="text-right">1W</div>
                  <div className="text-right">1M</div>
                  <div className="text-right">3M</div>
                  <div className="text-right">YTD</div>
                </div>

                {region.indices.length === 0 ? (
                  <div className="px-5 py-6 text-slate-500 text-sm">No data yet — run the backfill.</div>
                ) : (
                  <div className="min-w-[600px]">
                    {region.indices.map(idx => <IndexRow key={idx.index_code} idx={idx} />)}
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {/* No data at all yet */}
        {data && data.regions.length === 0 && !loading && (
          <div className="text-center py-16 text-slate-400 text-sm">
            No global market data yet. Run the backfill script to populate.
          </div>
        )}

        {/* AUD FX rates */}
        {data && sortedFx.length > 0 && (
          <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-700/50 flex items-center gap-3">
              <span className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-700 text-[11px] font-bold text-slate-300 tracking-wide shrink-0">FX</span>
              <h2 className="text-lg font-semibold text-white">AUD Exchange Rates</h2>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 p-5">
              {sortedFx.map(fx => <FxCard key={fx.fx_pair} fx={fx} />)}
            </div>
          </div>
        )}

        {/* Data source note */}
        {data && (
          <p className="text-xs text-slate-600 text-center border-t border-slate-800 pt-6">
            Global market data is sourced from the latest available market feed. Some international indices may be
            delayed depending on exchange availability.
          </p>
        )}
      </div>
    </div>
    </PlanGate>
  )
}
