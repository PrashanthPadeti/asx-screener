'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { RefreshCw, TrendingUp, TrendingDown, Minus, ArrowLeft, Info, Bell, Star } from 'lucide-react'
import { getCommodities, CommoditiesResponse, CommodityPrice } from '@/lib/api'
import { PlanGate } from '@/components/PlanGate'
import Breadcrumb from '@/components/Breadcrumb'

// ── Constants ─────────────────────────────────────────────────────────────────

const CATEGORY_META: Record<string, { label: string; color: string; border: string; bg: string }> = {
  'Precious Metals': { label: 'Precious Metals', color: 'text-amber-400',  border: 'border-amber-500/30',  bg: 'bg-amber-500/10'  },
  'Base Metals':     { label: 'Base Metals',     color: 'text-sky-400',    border: 'border-sky-500/30',    bg: 'bg-sky-500/10'    },
  'Energy':          { label: 'Energy',          color: 'text-orange-400', border: 'border-orange-500/30', bg: 'bg-orange-500/10' },
  'Bulk':            { label: 'Bulk',            color: 'text-stone-400',  border: 'border-stone-500/30',  bg: 'bg-stone-500/10'  },
}

const CATEGORY_ICONS: Record<string, string> = {
  'Precious Metals': 'PM',
  'Base Metals':     'BM',
  'Energy':          'EN',
  'Bulk':            'BK',
}

// Symbol badge and short ticker label
const COMMODITY_SYMBOL: Record<string, string> = {
  GC: 'Au', SI: 'Ag', PL: 'Pt',
  HG: 'Cu', AL: 'Al', NI: 'Ni', ZN: 'Zn',
  CL: 'WTI', BZ: 'BRT', NG: 'GAS',
  IO: 'Fe', CO: 'CC',
}

const COMMODITY_SHORT: Record<string, string> = {
  GC: 'Gold', SI: 'Silver', PL: 'Platinum',
  HG: 'Copper', AL: 'Aluminium', NI: 'Nickel', ZN: 'Zinc',
  CL: 'WTI Oil', BZ: 'Brent Oil', NG: 'Nat Gas',
  IO: 'Iron Ore', CO: 'Coal',
}

// Related ASX stocks per commodity code
const RELATED_STOCKS: Record<string, { codes: string[]; label: string }> = {
  GC: { codes: ['NST', 'EVN', 'DEG', 'GMD', 'RRL'],   label: 'Gold miners'       },
  SI: { codes: ['SFR', 'AIS'],                          label: 'Silver/base metals' },
  HG: { codes: ['SFR', 'AIS', '29M', 'OZL'],           label: 'Copper miners'     },
  AL: { codes: ['AWC', 'AIS'],                          label: 'Aluminium'         },
  NI: { codes: ['IGO', 'WSA', 'NIC'],                   label: 'Nickel miners'     },
  ZN: { codes: ['CBH', 'AIS'],                          label: 'Zinc miners'       },
  CL: { codes: ['WDS', 'STO', 'BPT', 'KAR'],           label: 'Oil & gas'         },
  BZ: { codes: ['WDS', 'STO', 'BPT'],                   label: 'Oil & gas'         },
  NG: { codes: ['WDS', 'STO', 'BPT', 'KAR'],           label: 'Gas producers'     },
  IO: { codes: ['BHP', 'RIO', 'FMG', 'MIN'],            label: 'Iron ore miners'   },
  CO: { codes: ['WHC', 'YAL', 'NHC', 'BHP'],            label: 'Coal miners'       },
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function isAUD(unit: string | null): boolean {
  return unit != null && unit.startsWith('AUD')
}

/** Detect copper-style mislabelling: USD/lb with large value → treat as USD/t */
function effectiveUnit(unit: string | null, price: number | null): string | null {
  if (!unit) return unit
  if (unit.endsWith('/lb') && price != null && price > 500) return unit.replace('/lb', '/t')
  return unit
}

/** Display-friendly unit string e.g. "US$/oz", "A$/t" */
function fmtUnit(unit: string | null, price?: number | null): string {
  const u = effectiveUnit(unit, price ?? null) ?? ''
  if (!u) return ''
  if (u.startsWith('AUD/')) return 'A$/' + u.slice(4)
  if (u.startsWith('USD/')) return 'US$/' + u.slice(4)
  return u
}

/** Format price with correct currency, decimals, and thousands separator */
function fmtPrice(v: number | null, unit: string | null): string {
  if (v == null) return '—'
  const u        = effectiveUnit(unit, v)
  const prefix   = isAUD(u) ? 'A$' : 'US$'
  const baseUnit = u?.split('/')[1] ?? ''

  if (baseUnit === 'oz')    return prefix + v.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (baseUnit === 'bbl')   return prefix + v.toFixed(2)
  if (baseUnit === 'lb')    return prefix + v.toFixed(4)
  if (baseUnit === 'MMBtu') return prefix + v.toFixed(2)   // 2dp cleaner than 3dp
  if (baseUnit === 't')     return prefix + v.toLocaleString('en-AU', { maximumFractionDigits: 0 })
  return prefix + v.toLocaleString('en-AU', { maximumFractionDigits: 2 })
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%'
}

function retColor(v: number | null): string {
  if (v == null) return 'text-slate-500'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-400'
}

function retBg(v: number | null): string {
  if (v == null) return 'bg-slate-700/50 text-slate-500'
  const p = v * 100
  if (p >= 1)  return 'bg-emerald-500/20 text-emerald-400'
  if (p >= 0)  return 'bg-emerald-900/30 text-emerald-500'
  if (p >= -1) return 'bg-red-900/30 text-red-400'
  return 'bg-red-500/20 text-red-400'
}

function fmtTimestamp(d: Date): string {
  return d.toLocaleTimeString('en-AU', {
    hour: 'numeric', minute: '2-digit', hour12: true,
    timeZone: 'Australia/Sydney',
  }) + ' AEST'
}

// ── Ticker strip ──────────────────────────────────────────────────────────────

function TickerStrip({ categories }: { categories: CommoditiesResponse['categories'] }) {
  const all = categories.flatMap(c => c.commodities)
  if (!all.length) return null

  // Triple-duplicate for seamless infinite loop on any screen width
  const items = [...all, ...all, ...all]
  const speed = Math.max(30, all.length * 5)

  return (
    <div
      className="overflow-hidden w-full select-none"
      style={{
        maskImage: 'linear-gradient(to right, transparent, black 6%, black 94%, transparent)',
        WebkitMaskImage: 'linear-gradient(to right, transparent, black 6%, black 94%, transparent)',
      }}
    >
      <div
        className="flex animate-marquee"
        style={{ width: 'max-content', animationDuration: `${speed}s`, gap: '0px' }}
      >
        {items.map((c, i) => {
          const sym   = COMMODITY_SYMBOL[c.commodity_code] ?? c.commodity_code
          const short = COMMODITY_SHORT[c.commodity_code] ?? c.commodity_name
          const up    = c.return_1d != null && c.return_1d > 0
          const dn    = c.return_1d != null && c.return_1d < 0
          return (
            <div key={`${c.commodity_code}-${i}`} className="flex items-center shrink-0 px-4 py-1.5 border-r border-slate-700/40">
              <span className="text-[10px] font-bold text-slate-400 bg-slate-700/50 px-1.5 py-0.5 rounded mr-2">
                {sym}
              </span>
              <span className="text-xs text-slate-400 mr-1.5">{short}</span>
              <span className="text-sm font-semibold text-white mr-1.5">{fmtPrice(c.close_price, c.unit)}</span>
              <span className={`text-xs font-medium flex items-center gap-0.5 ${retColor(c.return_1d)}`}>
                {up ? <TrendingUp className="w-3 h-3" /> : dn ? <TrendingDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
                {fmtPct(c.return_1d)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Commodity Card ────────────────────────────────────────────────────────────

function CommodityCard({ c }: { c: CommodityPrice }) {
  const sym      = COMMODITY_SYMBOL[c.commodity_code] ?? c.commodity_code.slice(0, 3)
  const meta     = CATEGORY_META[c.category] ?? { color: 'text-slate-400', border: 'border-slate-700', bg: 'bg-slate-700/20' }
  const related  = RELATED_STOCKS[c.commodity_code]
  const unitLabel = fmtUnit(c.unit, c.close_price)
  const slug     = c.commodity_code.toLowerCase()

  return (
    <div className={`relative bg-slate-800/60 rounded-xl border ${meta.border} hover:border-slate-500/60 transition-all duration-200 p-5 flex flex-col group`}>

      {/* Overlay link — makes whole card clickable */}
      <Link href={`/commodities/${slug}`} className="absolute inset-0 z-[1] rounded-xl" aria-label={c.commodity_name} />

      {/* Header row */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <span className={`w-9 h-9 flex items-center justify-center rounded-lg ${meta.bg} text-[11px] font-bold tracking-wide shrink-0 ${meta.color} pointer-events-none`}>
            {sym}
          </span>
          <div className="pointer-events-none">
            <div className="text-sm font-bold text-slate-100 group-hover:text-white transition-colors">{c.commodity_name}</div>
            <div className="text-xs text-slate-500 mt-0.5">{unitLabel || '—'}</div>
          </div>
        </div>

        {/* Alert + Watchlist actions — above the overlay */}
        <div className="relative z-[2] flex items-center gap-1 ml-2">
          <Link
            href={`/alerts?commodity=${c.commodity_code}`}
            className="p-1.5 rounded-lg text-slate-500 hover:text-amber-400 hover:bg-slate-700/60 transition-colors"
            title="Set price alert"
          >
            <Bell className="w-3.5 h-3.5" />
          </Link>
          <Link
            href={`/watchlist?add_commodity=${c.commodity_code}`}
            className="p-1.5 rounded-lg text-slate-500 hover:text-blue-400 hover:bg-slate-700/60 transition-colors"
            title="Add to watchlist"
          >
            <Star className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* Price + 1D change */}
      <div className="flex items-center justify-between mb-4 pointer-events-none">
        <div className="text-2xl font-bold text-white">{fmtPrice(c.close_price, c.unit)}</div>
        <span className={`text-sm font-semibold px-2.5 py-1 rounded-lg ${retBg(c.return_1d)}`}>
          {fmtPct(c.return_1d)}
        </span>
      </div>

      {/* 52W range bar */}
      {c.high_52w != null && c.low_52w != null && c.close_price != null && (
        <div className="mb-4 pointer-events-none">
          <div className="flex justify-between text-[10px] text-slate-500 mb-1.5">
            <span>52W Low {fmtPrice(c.low_52w, c.unit)}</span>
            <span>52W High {fmtPrice(c.high_52w, c.unit)}</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-red-500 via-amber-400 to-emerald-500 rounded-full"
              style={{
                width: `${Math.min(100, Math.max(2,
                  ((c.close_price - c.low_52w) / (c.high_52w - c.low_52w)) * 100
                ))}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Period returns */}
      <div className="grid grid-cols-3 gap-2 text-center mb-4 pointer-events-none">
        {([
          { label: '1W',  v: c.return_1w  },
          { label: '1M',  v: c.return_1m  },
          { label: 'YTD', v: c.return_ytd },
        ] as const).map(({ label, v }) => (
          <div key={label} className="bg-slate-900/60 rounded-lg py-2">
            <div className="text-[10px] text-slate-500 mb-0.5">{label}</div>
            <div className={`text-xs font-semibold ${retColor(v)}`}>{fmtPct(v)}</div>
          </div>
        ))}
      </div>

      {/* Related ASX stocks — z-[2] so they're above overlay */}
      {related && (
        <div className="mt-auto pt-3 border-t border-slate-700/40">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-[10px] text-slate-500 uppercase tracking-wide pointer-events-none">{related.label}</span>
            <div className="relative z-[2] flex flex-wrap gap-1">
              {related.codes.map(code => (
                <Link
                  key={code}
                  href={`/company/${code}`}
                  className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-slate-700 text-slate-300 hover:bg-blue-600 hover:text-white transition-colors border border-slate-600/50 hover:border-blue-500"
                >
                  {code}
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CommoditiesPage() {
  const [data,        setData]        = useState<CommoditiesResponse | null>(null)
  const [loading,     setLoading]     = useState(true)
  const [refreshing,  setRefreshing]  = useState(false)
  const [error,       setError]       = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      setData(await getCommodities())
      setLastUpdated(new Date())
      setError(null)
    } catch {
      setError('Failed to load commodities data')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { load() }, [])

  const gold = data?.categories.flatMap(c => c.commodities).find(c => c.commodity_code === 'GC')

  return (
    <PlanGate required="premium" feature="Commodities">
    <div className="min-h-screen bg-slate-950 text-slate-100 overflow-x-hidden">

      {/* ── Hero ─────────────────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-b from-slate-800 to-slate-900 border-b border-slate-700/50">
        <div className="max-w-screen-xl mx-auto px-4 sm:px-6 xl:px-10 py-8">

          {/* Breadcrumb */}
          <div className="mb-4">
            <Breadcrumb theme="dark" crumbs={[{ label: 'Market', href: '/market' }, { label: 'Commodities', href: '/commodities' }]} />
          </div>

          {/* Top bar */}
          <div className="flex items-center justify-between mb-6">
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
                disabled={refreshing}
                className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 text-sm transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          {/* Title + Gold widget */}
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6">
            <div>
              <h1 className="text-3xl font-bold text-white mb-1">Commodities</h1>
              <p className="text-slate-400 text-sm">Precious metals, base metals, energy and bulk materials</p>
              {data?.as_of && <p className="text-slate-500 text-xs mt-1">As of {data.as_of}</p>}
              {lastUpdated && (
                <p className="text-slate-500 text-xs mt-0.5 sm:hidden">Updated {fmtTimestamp(lastUpdated)}</p>
              )}
              <div className="flex items-center gap-1.5 mt-2">
                <Info className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                <p className="text-[11px] text-slate-500">
                  Prices in USD unless marked A$. Currency as per exchange standard.
                </p>
              </div>
            </div>

            {/* Gold spotlight */}
            {gold && (
              <Link
                href="/commodities/gc"
                className="sm:text-right bg-slate-800/60 rounded-xl px-5 py-3 border border-amber-500/30 shrink-0 hover:border-amber-400/50 transition-colors"
              >
                <div className="text-xs text-slate-500 mb-0.5 flex items-center sm:justify-end gap-1.5">
                  <span className="text-[10px] font-bold text-amber-500 bg-amber-500/10 px-1.5 py-0.5 rounded">Au</span>
                  Gold
                </div>
                <div className="text-3xl font-bold text-amber-300">{fmtPrice(gold.close_price, gold.unit)}</div>
                <div className="text-xs text-slate-500 mt-0.5">{fmtUnit(gold.unit)}</div>
                <div className={`text-sm font-medium mt-1 ${retColor(gold.return_1d)}`}>
                  {fmtPct(gold.return_1d)} today
                </div>
              </Link>
            )}
          </div>

          {/* Ticker strip */}
          {data && !loading && (
            <div className="pt-4 border-t border-slate-700/40">
              <TickerStrip categories={data.categories} />
            </div>
          )}
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────────────── */}
      <div className="max-w-screen-xl mx-auto px-4 sm:px-6 xl:px-10 py-10 space-y-12">

        {loading && (
          <div className="text-center py-24 text-slate-400 text-sm flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin" /> Loading commodities…
          </div>
        )}
        {error && !loading && (
          <div className="text-center py-24 text-red-400 text-sm">{error}</div>
        )}

        {/* Category sections */}
        {data && data.categories.map(({ category, commodities }) => {
          const meta     = CATEGORY_META[category] ?? { label: category, color: 'text-slate-400', border: 'border-slate-700', bg: 'bg-slate-700/20' }
          const iconCode = CATEGORY_ICONS[category] ?? category.slice(0, 2).toUpperCase()
          return (
            <div key={category}>
              <div className="flex items-center gap-3 mb-5">
                <span className={`w-8 h-8 flex items-center justify-center rounded-lg bg-slate-800 border ${meta.border} text-[11px] font-bold shrink-0 ${meta.color}`}>
                  {iconCode}
                </span>
                <h2 className={`text-lg font-semibold ${meta.color}`}>{meta.label}</h2>
                <span className="text-xs text-slate-500">· {commodities.length} commodities</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {commodities.map(c => <CommodityCard key={c.commodity_code} c={c} />)}
              </div>
            </div>
          )
        })}

        {data && data.categories.length === 0 && !loading && (
          <div className="text-center py-16 text-slate-400 text-sm">
            No commodity data yet. Run the backfill script to populate.
          </div>
        )}

        {/* Why commodities matter */}
        {data && data.categories.length > 0 && (
          <div className="bg-slate-900 rounded-xl border border-slate-700/50 p-6 lg:p-8">
            <h3 className="text-base font-semibold text-slate-200 mb-2 flex items-center gap-2">
              <span className="w-6 h-6 flex items-center justify-center rounded bg-slate-700 text-[10px] font-bold text-slate-300 shrink-0">?</span>
              Why commodities matter for ASX investors
            </h3>
            <p className="text-sm text-slate-400 leading-relaxed mb-5">
              Australia's sharemarket is heavily weighted toward resources — mining and energy stocks make up a
              significant share of the ASX 200. Commodity prices are a leading indicator for earnings revisions
              in this sector.
            </p>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs text-slate-500">
              {[
                { color: 'text-amber-400',  title: 'Gold',                body: 'Drives NST, EVN, DEG and smaller gold explorers. Higher gold price = stronger margins and cashflow.' },
                { color: 'text-sky-400',    title: 'Iron Ore',            body: 'BHP, RIO and FMG generate the majority of earnings from iron ore exports to China.' },
                { color: 'text-orange-400', title: 'Oil & Gas',           body: 'WDS and STO benefit from higher oil and LNG prices. Energy prices affect transport costs broadly.' },
                { color: 'text-sky-300',    title: 'Copper & Base Metals',body: 'SFR and OZL are key copper plays. Nickel and lithium prices impact battery-related miners.' },
              ].map(({ color, title, body }) => (
                <div key={title} className="bg-slate-800/60 rounded-lg p-4">
                  <p className={`font-semibold ${color} mb-1.5`}>{title}</p>
                  <p className="leading-relaxed">{body}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        {data && (
          <p className="text-[11px] text-slate-600 text-center border-t border-slate-800 pt-6 pb-2">
            Commodity prices sourced from global futures markets and may be delayed. Not financial advice.
          </p>
        )}
      </div>
    </div>
    </PlanGate>
  )
}
