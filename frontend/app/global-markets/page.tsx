'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import Link from 'next/link'
import { Globe, RefreshCw, ArrowLeft } from 'lucide-react'
import { getGlobalMarkets, GlobalMarketsResponse, GlobalIndexPrice, GlobalFxRate } from '@/lib/api'
import { PlanGate } from '@/components/PlanGate'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%'
}

function fmtPrice(v: number | null, large = false): string {
  if (v == null) return '—'
  if (large || v >= 1000) return v.toLocaleString('en-AU', { maximumFractionDigits: 0 })
  if (v >= 100) return v.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v.toFixed(4)
}

function retColor(v: number | null): string {
  if (v == null) return 'text-slate-400'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-400'
}

function retBadge(v: number | null): string {
  if (v == null) return 'bg-slate-700 text-slate-400'
  const p = v * 100
  if (p >= 1)  return 'bg-emerald-600/30 text-emerald-400'
  if (p >= 0)  return 'bg-emerald-900/30 text-emerald-500'
  if (p >= -1) return 'bg-red-900/30 text-red-400'
  return 'bg-red-600/30 text-red-400'
}

const COUNTRY_FLAGS: Record<string, string> = {
  'United States':  '🇺🇸',
  'United Kingdom': '🇬🇧',
  'Germany':        '🇩🇪',
  'France':         '🇫🇷',
  'Japan':          '🇯🇵',
  'Hong Kong':      '🇭🇰',
  'China':          '🇨🇳',
  'South Korea':    '🇰🇷',
}

const REGION_FLAGS: Record<string, string> = {
  'US':     '🇺🇸',
  'Europe': '🇪🇺',
  'Asia':   '🌏',
}

const FX_META: Record<string, { flag: string; desc: string }> = {
  AUDUSD: { flag: '🇺🇸', desc: 'US Dollar' },
  AUDEUR: { flag: '🇪🇺', desc: 'Euro' },
  AUDGBP: { flag: '🇬🇧', desc: 'British Pound' },
  AUDJPY: { flag: '🇯🇵', desc: 'Japanese Yen' },
  AUDCNY: { flag: '🇨🇳', desc: 'Chinese Yuan' },
}

// ── Index row ─────────────────────────────────────────────────────────────────

function IndexRow({ idx }: { idx: GlobalIndexPrice }) {
  const isLargePrice = (idx.close_price ?? 0) >= 1000
  return (
    <Link href={`/global-markets/${idx.index_code.toLowerCase()}`} className="grid grid-cols-8 gap-2 px-5 py-4 border-b border-slate-700/40 hover:bg-slate-700/20 transition-colors last:border-0 group">
      {/* Name + country */}
      <div className="col-span-2 flex items-center gap-2.5">
        <span className="text-xl leading-none">{COUNTRY_FLAGS[idx.country] ?? '🌐'}</span>
        <div>
          <div className="text-sm font-semibold text-slate-100 group-hover:text-blue-400 transition-colors">{idx.index_name}</div>
          <div className="text-xs text-slate-500">{idx.country} · {idx.currency}</div>
        </div>
      </div>
      {/* Price + 1D */}
      <div className="col-span-2 text-right">
        <div className="text-sm font-semibold text-slate-100">{fmtPrice(idx.close_price, isLargePrice)}</div>
        <span className={`inline-block text-xs font-medium px-1.5 py-0.5 rounded mt-0.5 ${retBadge(idx.return_1d)}`}>
          {fmtPct(idx.return_1d)}
        </span>
      </div>
      {/* 1W */}
      <div className={`text-right text-sm font-medium ${retColor(idx.return_1w)}`}>
        {fmtPct(idx.return_1w)}
      </div>
      {/* 1M */}
      <div className={`text-right text-sm font-medium ${retColor(idx.return_1m)}`}>
        {fmtPct(idx.return_1m)}
      </div>
      {/* 3M */}
      <div className={`text-right text-sm font-medium ${retColor(idx.return_3m)}`}>
        {fmtPct(idx.return_3m)}
      </div>
      {/* YTD */}
      <div className={`text-right text-sm font-medium ${retColor(idx.return_ytd)}`}>
        {fmtPct(idx.return_ytd)}
      </div>
    </Link>
  )
}

// ── FX card ───────────────────────────────────────────────────────────────────

function FxCard({ fx }: { fx: GlobalFxRate }) {
  const meta = FX_META[fx.fx_pair] ?? { flag: '🌐', desc: fx.fx_pair }
  const quote = fx.fx_pair.slice(3)
  const rateStr = fx.fx_pair === 'AUDJPY' ? fx.rate?.toFixed(2) : fx.rate?.toFixed(4)
  return (
    <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50 hover:border-slate-600/50 transition-colors">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-2xl leading-none">{meta.flag}</span>
        <div>
          <div className="text-sm font-bold text-slate-100">AUD/{quote}</div>
          <div className="text-xs text-slate-500">{meta.desc}</div>
        </div>
      </div>
      <div className="text-2xl font-bold text-white mb-2">{rateStr ?? '—'}</div>
      <div className="flex flex-col gap-1 text-xs">
        <div className="flex justify-between">
          <span className="text-slate-500">Today</span>
          <span className={retColor(fx.return_1d)}>{fmtPct(fx.return_1d)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">1 week</span>
          <span className={retColor(fx.return_1w)}>{fmtPct(fx.return_1w)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">1 month</span>
          <span className={retColor(fx.return_1m)}>{fmtPct(fx.return_1m)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">YTD</span>
          <span className={retColor(fx.return_ytd)}>{fmtPct(fx.return_ytd)}</span>
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function GlobalMarketsPage() {
  const [data,       setData]       = useState<GlobalMarketsResponse | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error,      setError]      = useState<string | null>(null)

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      setData(await getGlobalMarkets())
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
            <button
              onClick={() => load(true)}
              className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
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
        {data && data.regions.map(region => (
          <div key={region.region} className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
            {/* Region header */}
            <div className="px-5 py-4 border-b border-slate-700/50 flex items-center gap-2.5">
              <span className="text-xl leading-none">{REGION_FLAGS[region.region] ?? '🌐'}</span>
              <h2 className="text-lg font-semibold text-white">{region.region}</h2>
              <span className="text-xs text-slate-500 ml-1">{region.indices.length} indices</span>
            </div>

            {/* Column headers */}
            <div className="grid grid-cols-8 gap-2 px-5 py-2.5 bg-slate-800/40 border-b border-slate-700/40 text-xs font-medium text-slate-500 uppercase tracking-wide">
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
              region.indices.map(idx => <IndexRow key={idx.index_code} idx={idx} />)
            )}
          </div>
        ))}

        {/* No data at all yet */}
        {data && data.regions.length === 0 && !loading && (
          <div className="text-center py-16 text-slate-400 text-sm">
            No global market data yet. Run the backfill script to populate.
          </div>
        )}

        {/* AUD FX rates */}
        {data && data.fx_rates.length > 0 && (
          <div className="bg-slate-900 rounded-xl border border-slate-700/50 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-700/50 flex items-center gap-2.5">
              <span className="text-xl leading-none">💱</span>
              <h2 className="text-lg font-semibold text-white">AUD Exchange Rates</h2>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 p-5">
              {data.fx_rates.map(fx => <FxCard key={fx.fx_pair} fx={fx} />)}
            </div>
          </div>
        )}
      </div>
    </div>
    </PlanGate>
  )
}
