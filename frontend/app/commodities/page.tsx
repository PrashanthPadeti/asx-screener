'use client'
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { RefreshCw, TrendingUp, TrendingDown, Minus, ArrowLeft, Info } from 'lucide-react'
import { getCommodities, CommoditiesResponse, CommodityPrice } from '@/lib/api'
import { PlanGate } from '@/components/PlanGate'

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

const COMMODITY_ICONS: Record<string, string> = {
  GC: 'Au',  // Gold
  SI: 'Ag',  // Silver
  PL: 'Pt',  // Platinum
  HG: 'Cu',  // Copper
  AL: 'Al',  // Aluminium
  NI: 'Ni',  // Nickel
  ZN: 'Zn',  // Zinc
  CL: 'WTI', // WTI Oil
  BZ: 'BRT', // Brent Oil
  NG: 'GAS', // Nat Gas
  IO: 'Fe',  // Iron Ore
  CO: 'CC',  // Coal
}

// Related ASX stocks per commodity code
const RELATED_STOCKS: Record<string, { codes: string[]; label: string }> = {
  GC: { codes: ['NST', 'EVN', 'DEG', 'GMD', 'RRL'], label: 'Gold miners' },
  SI: { codes: ['SFR', 'AIS'], label: 'Silver/base metals' },
  HG: { codes: ['SFR', 'AIS', '29M', 'OZL'], label: 'Copper miners' },
  AL: { codes: ['AWC', 'AIS'], label: 'Aluminium' },
  NI: { codes: ['IGO', 'WSA', 'NIC'], label: 'Nickel miners' },
  ZN: { codes: ['CBH', 'AIS'], label: 'Zinc miners' },
  CL: { codes: ['WDS', 'STO', 'BPT', 'KAR'], label: 'Oil & gas' },
  BZ: { codes: ['WDS', 'STO', 'BPT'], label: 'Oil & gas' },
  NG: { codes: ['WDS', 'STO', 'BPT', 'KAR'], label: 'Gas producers' },
  IO: { codes: ['BHP', 'RIO', 'FMG', 'MIN'], label: 'Iron ore miners' },
  CO: { codes: ['WHC', 'YAL', 'NHC', 'BHP'], label: 'Coal miners' },
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Determine if a unit is AUD-denominated */
function isAUD(unit: string | null): boolean {
  return unit != null && unit.startsWith('AUD')
}

/** Human-friendly unit label */
function fmtUnit(unit: string | null): string {
  if (!unit) return ''
  // Replace USD/ or AUD/ with A$/ for AUD, or US$/ for USD
  if (unit.startsWith('AUD/')) return 'A$/' + unit.slice(4)
  if (unit.startsWith('USD/')) return 'US$/' + unit.slice(4)
  return unit
}

/** Format price with correct currency prefix */
function fmtPrice(v: number | null, unit: string | null): string {
  if (v == null) return '—'
  const prefix = isAUD(unit) ? 'A$' : 'US$'
  const baseUnit = unit?.split('/')[1] ?? ''

  if (baseUnit === 'oz')    return prefix + v.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (baseUnit === 'bbl')   return prefix + v.toFixed(2)
  if (baseUnit === 'lb')    return prefix + v.toFixed(4)
  if (baseUnit === 'MMBtu') return prefix + v.toFixed(3)
  if (baseUnit === 't')     return prefix + v.toLocaleString('en-AU', { maximumFractionDigits: 0 })
  return prefix + v.toLocaleString('en-AU', { maximumFractionDigits: 2 })
}

/** Format percentage */
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

  // Duplicate list for seamless infinite marquee
  const items = [...all, ...all]

  return (
    <div className="overflow-hidden w-full" style={{ maskImage: 'linear-gradient(to right, transparent, black 8%, black 92%, transparent)' }}>
      <div
        className="flex gap-8 animate-marquee"
        style={{ width: 'max-content', animationDuration: `${Math.max(20, all.length * 4)}s` }}
      >
        {items.map((c, i) => (
          <div key={`${c.commodity_code}-${i}`} className="flex items-center gap-2 shrink-0 py-1">
            <span className="text-xs font-bold text-slate-400 bg-slate-700/60 px-1.5 py-0.5 rounded">
              {COMMODITY_ICONS[c.commodity_code] ?? c.commodity_code}
            </span>
            <span className="text-sm text-slate-300 font-medium">{c.commodity_name}</span>
            <span className="text-sm font-bold text-white">{fmtPrice(c.close_price, c.unit)}</span>
            <span className={`text-xs font-semibold flex items-center gap-0.5 ${retColor(c.return_1d)}`}>
              {c.return_1d != null && c.return_1d > 0 ? <TrendingUp className="w-3 h-3" /> :
               c.return_1d != null && c.return_1d < 0 ? <TrendingDown className="w-3 h-3" /> :
               <Minus className="w-3 h-3" />}
              {fmtPct(c.return_1d)}
            </span>
            <span className="text-slate-700 text-xs">|</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Commodity Card ────────────────────────────────────────────────────────────

function CommodityCard({ c }: { c: CommodityPrice }) {
  const iconCode = COMMODITY_ICONS[c.commodity_code] ?? c.commodity_code.slice(0, 3)
  const meta     = CATEGORY_META[c.category] ?? { color: 'text-slate-400', border: 'border-slate-700', bg: 'bg-slate-700/20' }
  const related  = RELATED_STOCKS[c.commodity_code]
  const unitLabel = fmtUnit(c.unit)

  return (
    <div className={`bg-slate-800/60 rounded-xl border ${meta.border} hover:border-slate-500/50 transition-colors p-5 flex flex-col`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <span className={`w-9 h-9 flex items-center justify-center rounded-lg ${meta.bg} text-[11px] font-bold tracking-wide shrink-0 ${meta.color}`}>
            {iconCode}
          </span>
          <div>
            <div className="text-sm font-bold text-slate-100">{c.commodity_name}</div>
            <div className="text-xs text-slate-500 mt-0.5">{unitLabel || '—'}</div>
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
      <div className="grid grid-cols-3 gap-2 text-center mb-4">
        {[
          { label: '1W',  v: c.return_1w  },
          { label: '1M',  v: c.return_1m  },
          { label: 'YTD', v: c.return_ytd },
        ].map(({ label, v }) => (
          <div key={label} className="bg-slate-900/50 rounded-lg py-2">
            <div className="text-[10px] text-slate-500 mb-0.5">{label}</div>
            <div className={`text-xs font-semibold ${retColor(v)}`}>{fmtPct(v)}</div>
          </div>
        ))}
      </div>

      {/* Related ASX stocks */}
      {related && (
        <div className="mt-auto pt-3 border-t border-slate-700/40">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-[10px] text-slate-500 uppercase tracking-wide">{related.label}</span>
            <div className="flex flex-wrap gap-1">
              {related.codes.map(code => (
                <Link
                  key={code}
                  href={`/company/${code}`}
                  className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 hover:text-white transition-colors"
                  onClick={e => e.stopPropagation()}
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
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">

          {/* Top bar */}
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

          {/* Title + Gold widget */}
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-5">
            <div>
              <h1 className="text-3xl font-bold text-white mb-1">Commodities</h1>
              <p className="text-slate-400 text-sm">
                Precious metals, base metals, energy and bulk materials
              </p>
              {data?.as_of && (
                <p className="text-slate-500 text-xs mt-1">As of {data.as_of}</p>
              )}
              {lastUpdated && (
                <p className="text-slate-500 text-xs mt-0.5 sm:hidden">
                  Updated {fmtTimestamp(lastUpdated)}
                </p>
              )}
              {/* Currency note */}
              <div className="flex items-center gap-1.5 mt-2">
                <Info className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                <p className="text-[11px] text-slate-500">
                  Prices shown in USD unless marked A$. Currency as per exchange standard.
                </p>
              </div>
            </div>

            {/* Gold spotlight */}
            {gold && (
              <div className="sm:text-right bg-slate-800/60 rounded-xl px-5 py-3 border border-amber-500/30 shrink-0">
                <div className="text-xs text-slate-500 mb-0.5 flex items-center sm:justify-end gap-1">
                  <span className="text-[11px] font-bold text-amber-500 bg-amber-500/10 px-1.5 py-0.5 rounded">Au</span>
                  Gold
                </div>
                <div className="text-3xl font-bold text-amber-300">{fmtPrice(gold.close_price, gold.unit)}</div>
                <div className="text-xs text-slate-500 mt-0.5">{fmtUnit(gold.unit)}</div>
                <div className={`text-sm font-medium mt-1 ${retColor(gold.return_1d)}`}>
                  {fmtPct(gold.return_1d)} today
                </div>
              </div>
            )}
          </div>

          {/* Ticker strip — auto-scrolling marquee, no scrollbar */}
          {data && !loading && (
            <div className="pt-4 border-t border-slate-700/50">
              <TickerStrip categories={data.categories} />
            </div>
          )}
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-10">

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
              {/* Category header */}
              <div className="flex items-center gap-3 mb-4">
                <span className={`w-8 h-8 flex items-center justify-center rounded-lg bg-slate-800 border ${meta.border} text-[11px] font-bold shrink-0 ${meta.color}`}>
                  {iconCode}
                </span>
                <h2 className={`text-lg font-semibold ${meta.color}`}>{meta.label}</h2>
                <span className="text-xs text-slate-500">· {commodities.length} commodities</span>
              </div>

              {/* 3-col desktop, 2-col tablet, 1-col mobile */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
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

        {/* Why commodities matter */}
        {data && data.categories.length > 0 && (
          <div className="bg-slate-900 rounded-xl border border-slate-700/50 p-6">
            <h3 className="text-base font-semibold text-slate-200 mb-3 flex items-center gap-2">
              <span className="w-6 h-6 flex items-center justify-center rounded bg-slate-700 text-[10px] font-bold text-slate-300">?</span>
              Why commodities matter for ASX investors
            </h3>
            <p className="text-sm text-slate-400 leading-relaxed mb-3">
              Australia's sharemarket is heavily weighted toward resources — mining and energy stocks account
              for a significant share of the ASX 200. Commodity prices are a leading indicator for earnings
              revisions in this sector.
            </p>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs text-slate-500">
              <div className="bg-slate-800/60 rounded-lg p-3">
                <p className="font-semibold text-amber-400 mb-1">Gold</p>
                <p>Drives NST, EVN, DEG and smaller gold explorers. Higher gold price = stronger margins.</p>
              </div>
              <div className="bg-slate-800/60 rounded-lg p-3">
                <p className="font-semibold text-sky-400 mb-1">Iron Ore</p>
                <p>BHP, RIO and FMG generate the majority of earnings from iron ore exports to China.</p>
              </div>
              <div className="bg-slate-800/60 rounded-lg p-3">
                <p className="font-semibold text-orange-400 mb-1">Oil & Gas</p>
                <p>WDS and STO benefit from higher oil and LNG prices. Energy prices affect transport costs broadly.</p>
              </div>
              <div className="bg-slate-800/60 rounded-lg p-3">
                <p className="font-semibold text-sky-300 mb-1">Copper & Base Metals</p>
                <p>SFR and OZL are key copper plays. Nickel and lithium prices impact battery-related miners.</p>
              </div>
            </div>
          </div>
        )}

        {/* Footer disclaimer */}
        {data && (
          <p className="text-[11px] text-slate-600 text-center border-t border-slate-800 pt-6 pb-2">
            Commodity prices are sourced from global futures markets and may be delayed. Prices shown in the
            currency standard for each exchange. Not financial advice.
          </p>
        )}
      </div>
    </div>
    </PlanGate>
  )
}
