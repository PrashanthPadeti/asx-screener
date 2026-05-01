'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Star, Trash2, ArrowUpRight, RefreshCw } from 'lucide-react'
import { getScreenerBatch, type ScreenerRow } from '@/lib/api'
import { useWatchlist } from '@/lib/watchlist'
import WatchlistButton from '@/components/WatchlistButton'
import {
  formatPrice, formatMarketCap, formatVolume,
  formatRatio, formatRatioChange, formatPctRaw, cn, SECTOR_COLORS,
} from '@/lib/utils'

// ── Small helpers ─────────────────────────────────────────────

function fmtX(v: number | null | undefined) {
  if (v == null || v === 0) return '—'
  return `${v.toFixed(1)}x`
}

function ChangeCell({ val }: { val: number | null }) {
  if (val == null) return <span className="text-gray-300">—</span>
  return (
    <span className={val >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>
      {formatRatioChange(val)}
    </span>
  )
}

// ── Main page ─────────────────────────────────────────────────

export default function WatchlistPage() {
  const { codes, remove, clear, count, mounted } = useWatchlist()

  const [stocks,      setStocks]      = useState<ScreenerRow[]>([])
  const [loading,     setLoading]     = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  // Fetch live data whenever the watchlist codes change
  useEffect(() => {
    if (!mounted) return
    if (codes.length === 0) { setStocks([]); return }

    setLoading(true)
    getScreenerBatch(codes)
      .then(data => { setStocks(data); setLastRefresh(new Date()) })
      .catch(() => setStocks([]))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes.join(','), mounted])

  const refresh = () => {
    if (codes.length === 0) return
    setLoading(true)
    getScreenerBatch(codes)
      .then(data => { setStocks(data); setLastRefresh(new Date()) })
      .catch(() => setStocks([]))
      .finally(() => setLoading(false))
  }

  // ── Empty state ────────────────────────────────────────────

  if (mounted && codes.length === 0) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-yellow-50 rounded-full mb-4">
          <Star className="w-8 h-8 text-yellow-400" />
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Your Watchlist</h1>
        <p className="text-gray-500 mb-6">
          Click the ☆ star on any stock to add it here. Your list is saved in your browser.
        </p>
        <Link
          href="/screener"
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors"
        >
          <ArrowUpRight className="w-4 h-4" />
          Open Screener
        </Link>
      </div>
    )
  }

  // ── Loading skeleton ───────────────────────────────────────

  if (!mounted || loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 bg-gray-100 rounded w-40 animate-pulse" />
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="flex gap-4 px-5 py-3 border-b border-gray-50 animate-pulse">
              <div className="h-4 bg-gray-100 rounded w-12" />
              <div className="h-4 bg-gray-100 rounded w-40" />
              <div className="h-4 bg-gray-100 rounded w-16 ml-auto" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  // ── Watchlist table ────────────────────────────────────────

  return (
    <div className="space-y-4 max-w-screen-xl">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Star className="w-5 h-5 text-yellow-400 fill-yellow-400" />
            Watchlist
            <span className="text-sm font-normal text-gray-400 ml-1">
              {count} stock{count !== 1 ? 's' : ''}
            </span>
          </h1>
          {lastRefresh && (
            <p className="text-xs text-gray-400 mt-0.5">
              Updated {lastRefresh.toLocaleTimeString()}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
            Refresh
          </button>
          <Link
            href="/screener"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50"
          >
            <ArrowUpRight className="w-3.5 h-3.5" />
            Screener
          </Link>
          {count > 0 && (
            <button
              onClick={() => { if (confirm('Clear all watchlist items?')) clear() }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-500 border border-red-100 rounded-lg hover:bg-red-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Clear all
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                <th className="pl-4 pr-2 py-2.5 text-left w-8" />
                <th className="px-3 py-2.5 text-left">Code</th>
                <th className="px-3 py-2.5 text-left">Company</th>
                <th className="px-3 py-2.5 text-left">Sector</th>
                <th className="px-3 py-2.5 text-right">Price</th>
                <th className="px-3 py-2.5 text-right">1Y Return</th>
                <th className="px-3 py-2.5 text-right">Mkt Cap</th>
                <th className="px-3 py-2.5 text-right">P/E</th>
                <th className="px-3 py-2.5 text-right">Div Yield</th>
                <th className="px-3 py-2.5 text-right">Franking</th>
                <th className="px-3 py-2.5 text-right">ROE</th>
                <th className="px-3 py-2.5 text-right">F-Score</th>
                <th className="pr-4 pl-2 py-2.5 text-right">Remove</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {stocks.map(s => (
                <tr key={s.asx_code} className="hover:bg-blue-50/30 transition-colors">
                  {/* Star */}
                  <td className="pl-4 pr-2">
                    <WatchlistButton code={s.asx_code} size="sm" />
                  </td>

                  {/* Code */}
                  <td className="px-3 py-3">
                    <Link
                      href={`/company/${s.asx_code}`}
                      className="font-mono font-bold text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1"
                    >
                      {s.asx_code}
                      <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100" />
                    </Link>
                  </td>

                  {/* Company */}
                  <td className="px-3 py-3 text-gray-800 max-w-[180px] truncate">
                    {s.company_name}
                  </td>

                  {/* Sector */}
                  <td className="px-3 py-3">
                    {s.sector
                      ? <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium whitespace-nowrap',
                          SECTOR_COLORS[s.sector] || SECTOR_COLORS['Other'])}>{s.sector}</span>
                      : <span className="text-gray-300">—</span>}
                  </td>

                  {/* Price */}
                  <td className="px-3 py-3 text-right font-medium text-gray-900">
                    {formatPrice(s.price)}
                  </td>

                  {/* 1Y Return */}
                  <td className="px-3 py-3 text-right">
                    <ChangeCell val={s.return_1y} />
                  </td>

                  {/* Market Cap */}
                  <td className="px-3 py-3 text-right text-gray-700">
                    {formatMarketCap(s.market_cap)}
                  </td>

                  {/* P/E */}
                  <td className="px-3 py-3 text-right text-gray-700">
                    {fmtX(s.pe_ratio)}
                  </td>

                  {/* Div Yield */}
                  <td className="px-3 py-3 text-right text-gray-700">
                    {s.dividend_yield != null ? formatRatio(s.dividend_yield) : '—'}
                  </td>

                  {/* Franking */}
                  <td className="px-3 py-3 text-right">
                    {s.franking_pct != null
                      ? <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded',
                          s.franking_pct === 100 ? 'bg-green-100 text-green-700' :
                          s.franking_pct > 0    ? 'bg-yellow-100 text-yellow-700' :
                                                   'bg-gray-100 text-gray-500')}>
                          {formatPctRaw(s.franking_pct, 0)}
                        </span>
                      : <span className="text-gray-300">—</span>}
                  </td>

                  {/* ROE */}
                  <td className="px-3 py-3 text-right">
                    {s.roe != null
                      ? <span className={s.roe >= 0.15 ? 'text-green-600 font-medium' : 'text-gray-700'}>
                          {formatRatio(s.roe)}
                        </span>
                      : <span className="text-gray-300">—</span>}
                  </td>

                  {/* Piotroski F-Score */}
                  <td className="px-3 py-3 text-right">
                    {s.piotroski_f_score != null
                      ? <span className={cn('text-xs font-bold px-1.5 py-0.5 rounded',
                          s.piotroski_f_score >= 7 ? 'bg-green-100 text-green-700' :
                          s.piotroski_f_score >= 4 ? 'bg-yellow-100 text-yellow-700' :
                                                      'bg-red-100 text-red-700')}>
                          {s.piotroski_f_score}/9
                        </span>
                      : <span className="text-gray-300">—</span>}
                  </td>

                  {/* Remove */}
                  <td className="pr-4 pl-2 py-3 text-right">
                    <button
                      onClick={() => remove(s.asx_code)}
                      title={`Remove ${s.asx_code} from watchlist`}
                      className="text-gray-300 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}

              {/* Codes in watchlist but not in screener.universe */}
              {codes
                .filter(c => !stocks.find(s => s.asx_code === c))
                .map(code => (
                  <tr key={code} className="opacity-50">
                    <td className="pl-4 pr-2">
                      <WatchlistButton code={code} size="sm" />
                    </td>
                    <td className="px-3 py-3 font-mono font-bold text-gray-400">{code}</td>
                    <td colSpan={10} className="px-3 py-3 text-xs text-gray-400 italic">
                      Not in screener universe
                    </td>
                    <td className="pr-4 pl-2 py-3 text-right">
                      <button onClick={() => remove(code)} className="text-gray-300 hover:text-red-400">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-xs text-gray-400">
        Watchlist saved in your browser. Prices refresh from the ASX data universe (updated nightly).
      </p>
    </div>
  )
}
