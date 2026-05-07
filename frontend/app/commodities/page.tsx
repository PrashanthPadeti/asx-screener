'use client'
import { useEffect, useState } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { getCommodities, CommoditiesResponse, CommodityPrice } from '@/lib/api'
import { PlanGate } from '@/components/PlanGate'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPrice(v: number | null, unit: string | null): string {
  if (v == null) return '—'
  if (unit === 'USD/oz')    return '$' + v.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (unit === 'USD/bbl')   return '$' + v.toFixed(2)
  if (unit === 'USD/lb')    return '$' + v.toFixed(4)
  if (unit === 'USD/MMBtu') return '$' + v.toFixed(3)
  if (unit === 'USD/t')     return '$' + v.toFixed(2)
  return '$' + v.toLocaleString('en-AU', { maximumFractionDigits: 2 })
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%'
}

function retColor(v: number | null): string {
  if (v == null) return 'text-slate-400'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-400'
}

function retBg(v: number | null): string {
  if (v == null) return 'bg-slate-700/50 text-slate-400'
  const p = v * 100
  if (p >= 1)  return 'bg-emerald-500/20 text-emerald-400'
  if (p >= 0)  return 'bg-emerald-900/30 text-emerald-500'
  if (p >= -1) return 'bg-red-900/30 text-red-400'
  return 'bg-red-500/20 text-red-400'
}

const CATEGORY_META: Record<string, { icon: string; color: string; border: string }> = {
  'Precious Metals': { icon: '🥇', color: 'text-amber-400',  border: 'border-amber-500/30' },
  'Base Metals':     { icon: '⚙️',  color: 'text-sky-400',    border: 'border-sky-500/30'   },
  'Energy':          { icon: '⚡',  color: 'text-orange-400', border: 'border-orange-500/30' },
  'Bulk':            { icon: '⛏️',  color: 'text-stone-400',  border: 'border-stone-500/30' },
}

const COMMODITY_ICONS: Record<string, string> = {
  GC: '🥇', SI: '🥈', PL: '⬜',
  HG: '🔶',
  CL: '🛢️', BZ: '🛢️', NG: '🔥',
  IO: '🪨',
}

// ── Commodity Card ────────────────────────────────────────────────────────────

function CommodityCard({ c }: { c: CommodityPrice }) {
  const icon  = COMMODITY_ICONS[c.commodity_code] ?? '📦'
  const meta  = CATEGORY_META[c.category] ?? { icon: '📦', color: 'text-slate-400', border: 'border-slate-700' }
  const up    = c.return_1d != null && c.return_1d > 0
  const down  = c.return_1d != null && c.return_1d < 0

  return (
    <div className={`bg-slate-800/60 rounded-xl border ${meta.border} hover:border-slate-500/50 transition-colors p-5`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <span className="text-2xl leading-none">{icon}</span>
          <div>
            <div className="text-sm font-bold text-slate-100">{c.commodity_name}</div>
            <div className="text-xs text-slate-500 mt-0.5">{c.unit ?? '—'}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-white">{fmtPrice(c.close_price, c.unit)}</div>
          <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded mt-1 ${retBg(c.return_1d)}`}>
            {fmtPct(c.return_1d)}
          </span>
        </div>
      </div>

      {/* 52W range bar */}
      {c.high_52w != null && c.low_52w != null && c.close_price != null && (
        <div className="mb-4">
          <div className="flex justify-between text-[10px] text-slate-500 mb-1">
            <span>52W Low {fmtPrice(c.low_52w, c.unit)}</span>
            <span>52W High {fmtPrice(c.high_52w, c.unit)}</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-red-500 via-amber-400 to-emerald-500 rounded-full"
              style={{
                width: `${Math.min(100, Math.max(2,
                  ((c.close_price - c.low_52w) / (c.high_52w - c.low_52w)) * 100
                ))}%`
              }}
            />
          </div>
        </div>
      )}

      {/* Period returns */}
      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          { label: '1W',  v: c.return_1w },
          { label: '1M',  v: c.return_1m },
          { label: 'YTD', v: c.return_ytd },
        ].map(({ label, v }) => (
          <div key={label} className="bg-slate-900/50 rounded-lg py-2">
            <div className="text-[10px] text-slate-500 mb-0.5">{label}</div>
            <div className={`text-xs font-semibold ${retColor(v)}`}>{fmtPct(v)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Ticker strip ──────────────────────────────────────────────────────────────

function TickerStrip({ categories }: { categories: CommoditiesResponse['categories'] }) {
  const all = categories.flatMap(c => c.commodities)
  if (!all.length) return null
  return (
    <div className="flex gap-6 overflow-x-auto pb-1 scrollbar-hide">
      {all.map(c => (
        <div key={c.commodity_code} className="flex items-center gap-2 shrink-0">
          <span className="text-sm text-slate-300 font-medium">{c.commodity_name}</span>
          <span className="text-sm font-bold text-white">{fmtPrice(c.close_price, c.unit)}</span>
          <span className={`text-xs font-semibold ${retColor(c.return_1d)}`}>
            {c.return_1d != null && c.return_1d > 0 ? <TrendingUp className="w-3 h-3 inline mr-0.5" /> :
             c.return_1d != null && c.return_1d < 0 ? <TrendingDown className="w-3 h-3 inline mr-0.5" /> :
             <Minus className="w-3 h-3 inline mr-0.5" />}
            {fmtPct(c.return_1d)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CommoditiesPage() {
  const [data,       setData]       = useState<CommoditiesResponse | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error,      setError]      = useState<string | null>(null)

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      setData(await getCommodities())
      setError(null)
    } catch {
      setError('Failed to load commodities data')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { load() }, [])

  const gold = data?.categories
    .flatMap(c => c.commodities)
    .find(c => c.commodity_code === 'GC')

  return (
    <PlanGate required="premium" feature="Commodities">
    <div className="min-h-screen bg-slate-950 text-slate-100">

      {/* ── Hero ─────────────────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-b from-slate-800 to-slate-900 border-b border-slate-700/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2 text-slate-400 text-sm">
              <span>⛏️</span>
              <span>Precious Metals · Base Metals · Energy · Bulk</span>
            </div>
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
              <h1 className="text-3xl font-bold text-white mb-2">Commodities</h1>
              <p className="text-slate-400 text-sm">
                Key global commodity prices — ASX-relevant metals, energy and bulk materials
              </p>
              {data?.as_of && (
                <p className="text-slate-500 text-xs mt-1">As of {data.as_of}</p>
              )}
            </div>

            {/* Gold prominent display */}
            {gold && (
              <div className="sm:text-right bg-slate-800/60 rounded-xl px-5 py-3 border border-amber-500/30">
                <div className="text-xs text-slate-500 mb-0.5">🥇 Gold</div>
                <div className="text-3xl font-bold text-amber-300">{fmtPrice(gold.close_price, gold.unit)}</div>
                <div className={`text-sm font-medium ${retColor(gold.return_1d)}`}>
                  {fmtPct(gold.return_1d)} today
                </div>
              </div>
            )}
          </div>

          {/* Ticker strip */}
          {data && !loading && (
            <div className="mt-5 pt-5 border-t border-slate-700/50">
              <TickerStrip categories={data.categories} />
            </div>
          )}
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-10">

        {loading && (
          <div className="text-center py-24 text-slate-400 text-sm">Loading commodities…</div>
        )}
        {error && !loading && (
          <div className="text-center py-24 text-red-400 text-sm">{error}</div>
        )}

        {data && data.categories.map(({ category, commodities }) => {
          const meta = CATEGORY_META[category] ?? { icon: '📦', color: 'text-slate-400', border: 'border-slate-700' }
          return (
            <div key={category}>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-xl leading-none">{meta.icon}</span>
                <h2 className={`text-lg font-semibold ${meta.color}`}>{category}</h2>
                <span className="text-xs text-slate-500 ml-1">{commodities.length} commodities</span>
              </div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {commodities.map(c => (
                  <CommodityCard key={c.commodity_code} c={c} />
                ))}
              </div>
            </div>
          )
        })}

        {data && data.categories.length === 0 && !loading && (
          <div className="text-center py-16 text-slate-400 text-sm">
            No commodity data yet. Run the backfill script to populate.
          </div>
        )}

        {/* ASX Relevance note */}
        {data && data.categories.length > 0 && (
          <div className="bg-slate-900/60 rounded-xl border border-slate-700/40 p-5 text-sm text-slate-400">
            <p className="font-medium text-slate-300 mb-1">Why commodities matter for ASX investors</p>
            <p>
              Australia's market is heavily weighted toward resources. Gold and copper prices directly impact
              miners like NCM, OZL and IGO. Iron ore drives BHP, RIO and FMG earnings. Energy prices
              influence WDS, STO and Beach Energy. Monitoring commodities gives early signals for ASX resource stocks.
            </p>
          </div>
        )}
      </div>
    </div>
    </PlanGate>
  )
}
