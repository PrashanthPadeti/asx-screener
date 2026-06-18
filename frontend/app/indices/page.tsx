'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { TrendingUp, TrendingDown, BarChart2, RefreshCw, Info, ExternalLink, Download, Bell, Star } from 'lucide-react'
import { getIndices, IndicesResponse, IndexPrice } from '@/lib/api'
import { PlanGate } from '@/components/PlanGate'
import Breadcrumb from '@/components/Breadcrumb'

// ── Screener link mapping ─────────────────────────────────────────────────────

// AXJO (All Ordinaries, ~500 stocks) has no dedicated screener field — excluded intentionally.
const SCREENER_HREF: Record<string, string> = {
  ASX20:  '/screener?index=ASX20',
  ASX50:  '/screener?index=ASX50',
  ASX100: '/screener?index=ASX100',
  ASX200: '/screener?index=ASX200',
  ASX300: '/screener?index=ASX300',
  AXFJ:   '/screener?sector=Financials&autorun=true',
  AXMJ:   '/screener?sector=Materials&autorun=true',
  AXEJ:   '/screener?sector=Energy&autorun=true',
  AXHJ:   '/screener?sector=Health%20Care&autorun=true',
  AXPJ:   '/screener?sector=Property&autorun=true',
  AXIJ:   '/screener?sector=Industrials&autorun=true',
  AXDJ:   '/screener?sector=Consumer%20Discretionary&autorun=true',
  AXSJ:   '/screener?sector=Consumer%20Staples&autorun=true',
  AXUJ:   '/screener?sector=Utilities&autorun=true',
  AXTJ:   '/screener?sector=Information%20Technology&autorun=true',
  AXCJ:   '/screener?sector=Communication%20Services&autorun=true',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 2): string {
  if (v == null) return '—'
  const pct = v * 100
  return (pct >= 0 ? '+' : '') + pct.toFixed(decimals) + '%'
}

function fmtPrice(v: number | null): string {
  if (v == null) return '—'
  if (v >= 10000) return v.toLocaleString('en-AU', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
  return v.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function retColor(v: number | null): string {
  if (v == null) return 'text-slate-400'
  if (v > 0) return 'text-emerald-500'
  if (v < 0) return 'text-red-400'
  return 'text-slate-400'
}

function retBg(v: number | null): string {
  if (v == null) return 'bg-slate-800'
  const pct = v * 100
  if (pct >= 2)  return 'bg-emerald-600'
  if (pct >= 0)  return 'bg-emerald-800'
  if (pct >= -2) return 'bg-red-800'
  return 'bg-red-600'
}

function exportCSV(indices: IndexPrice[], asOf?: string) {
  const headers = ['Code', 'Name', 'Price', '1D %', '1W %', '1M %', '3M %', '1Y %', '52W Low', '52W High']
  const rows = indices.map(i => [
    i.index_code,
    `"${i.display_name}"`,
    i.close_price ?? '',
    i.return_1d != null ? (i.return_1d * 100).toFixed(2) : '',
    i.return_1w != null ? (i.return_1w * 100).toFixed(2) : '',
    i.return_1m != null ? (i.return_1m * 100).toFixed(2) : '',
    i.return_3m != null ? (i.return_3m * 100).toFixed(2) : '',
    i.return_1y != null ? (i.return_1y * 100).toFixed(2) : '',
    i.low_52w ?? '',
    i.high_52w ?? '',
  ])
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `asx-indices${asOf ? '-' + asOf : ''}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── Row component ─────────────────────────────────────────────────────────────

function IndexRow({ idx, isHighlighted }: { idx: IndexPrice; isHighlighted: boolean }) {
  const pctFromHigh = idx.high_52w && idx.close_price
    ? ((idx.close_price - idx.high_52w) / idx.high_52w) * 100
    : null
  const pctFromLow = idx.low_52w && idx.close_price
    ? ((idx.close_price - idx.low_52w) / idx.low_52w) * 100
    : null

  const screenerHref = SCREENER_HREF[idx.index_code]
  const alertHref    = `/alerts?index=${encodeURIComponent(idx.index_code)}`
  const detailHref   = `/indices/${idx.index_code}`

  return (
    <div
      className={`relative grid grid-cols-9 gap-3 px-5 py-4 border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors cursor-pointer ${isHighlighted ? 'bg-slate-700/20' : ''}`}
    >
      {/* Full-row click overlay — sits below interactive children */}
      <Link
        href={detailHref}
        className="absolute inset-0 z-[1]"
        aria-label={`View ${idx.display_name} detail`}
      />

      {/* Index name — interactive, above overlay */}
      <div className="col-span-2 relative z-[2]">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-bold px-2 py-0.5 rounded ${retBg(idx.return_1d)} text-white`}>
            {idx.index_code}
          </span>
        </div>
        <span className="text-xs text-slate-400 mt-1 leading-tight block">{idx.display_name}</span>
        {screenerHref && (
          <Link
            href={screenerHref}
            className="inline-flex items-center gap-1 mt-1.5 text-[10px] text-blue-400 hover:text-blue-300 transition-colors font-medium"
            title={`Screen ${idx.display_name} constituents`}
          >
            <ExternalLink className="w-2.5 h-2.5" />
            View in Screener
          </Link>
        )}
      </div>

      {/* Close price — pointer-events-none, overlay handles click */}
      <div className="text-right pointer-events-none">
        <div className="text-sm font-semibold text-slate-100">{fmtPrice(idx.close_price)}</div>
        <div className={`text-xs font-medium ${retColor(idx.return_1d)}`}>{fmtPct(idx.return_1d)}</div>
      </div>

      {/* 1W */}
      <div className={`text-right text-sm font-medium pointer-events-none ${retColor(idx.return_1w)}`}>
        {fmtPct(idx.return_1w)}
      </div>

      {/* 1M */}
      <div className={`text-right text-sm font-medium pointer-events-none ${retColor(idx.return_1m)}`}>
        {fmtPct(idx.return_1m)}
      </div>

      {/* 3M */}
      <div className={`text-right text-sm font-medium pointer-events-none ${retColor(idx.return_3m)}`}>
        {fmtPct(idx.return_3m)}
      </div>

      {/* 1Y */}
      <div className={`text-right text-sm font-medium pointer-events-none ${retColor(idx.return_1y)}`}>
        {fmtPct(idx.return_1y)}
      </div>

      {/* 52W range */}
      <div className="text-right pointer-events-none">
        {idx.high_52w && idx.low_52w && idx.close_price ? (
          <div>
            <div className="flex items-center justify-end gap-1 text-xs">
              <span className="text-slate-400">{fmtPrice(idx.low_52w)}</span>
              <span className="text-slate-600">–</span>
              <span className="text-slate-400">{fmtPrice(idx.high_52w)}</span>
            </div>
            <div className="mt-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full"
                style={{
                  width: `${Math.max(2, Math.min(100, ((idx.close_price - idx.low_52w) / (idx.high_52w - idx.low_52w)) * 100))}%`
                }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-500 mt-0.5">
              {pctFromLow != null && <span>+{pctFromLow.toFixed(1)}% from low</span>}
              {pctFromHigh != null && <span>{pctFromHigh.toFixed(1)}% from high</span>}
            </div>
          </div>
        ) : (
          <span className="text-slate-500 text-xs">No data</span>
        )}
      </div>

      {/* Actions — interactive, above overlay */}
      <div className="relative z-[2] flex items-center justify-end gap-1">
        <Link
          href={alertHref}
          className="p-1.5 rounded-lg text-slate-500 hover:text-amber-400 hover:bg-slate-700 transition-colors"
          title="Create price alert for this index"
        >
          <Bell className="w-3.5 h-3.5" />
        </Link>
        <Link
          href={`/watchlist?add_index=${encodeURIComponent(idx.index_code)}`}
          className="p-1.5 rounded-lg text-slate-500 hover:text-yellow-400 hover:bg-slate-700 transition-colors"
          title="Add to watchlist"
        >
          <Star className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  )
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function SummaryCard({ idx }: { idx: IndexPrice }) {
  const r = idx.return_1d
  const screenerHref = SCREENER_HREF[idx.index_code]
  return (
    <div className="relative group bg-slate-800 border border-slate-700 rounded-xl p-4 hover:border-slate-500 transition-colors">
      {/* Full card click — goes to index detail */}
      <Link href={`/indices/${idx.index_code}`} className="absolute inset-0 rounded-xl z-[1]" aria-label={idx.display_name} />

      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wide">{idx.index_code}</div>
          <div className="text-xs text-slate-500 mt-0.5">{idx.display_name}</div>
        </div>
        {r != null && (
          r > 0
            ? <TrendingUp className="w-5 h-5 text-emerald-500" />
            : r < 0
            ? <TrendingDown className="w-5 h-5 text-red-400" />
            : <BarChart2 className="w-5 h-5 text-slate-500" />
        )}
      </div>
      <div className="text-2xl font-bold text-white">{fmtPrice(idx.close_price)}</div>
      <div className={`text-sm font-semibold mt-1 ${retColor(r)}`}>
        {fmtPct(r)} today
      </div>
      <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-slate-700">
        <div>
          <div className="text-[10px] text-slate-500 uppercase">1W</div>
          <div className={`text-xs font-semibold ${retColor(idx.return_1w)}`}>{fmtPct(idx.return_1w, 1)}</div>
        </div>
        <div>
          <div className="text-[10px] text-slate-500 uppercase">1M</div>
          <div className={`text-xs font-semibold ${retColor(idx.return_1m)}`}>{fmtPct(idx.return_1m, 1)}</div>
        </div>
        <div>
          <div className="text-[10px] text-slate-500 uppercase">1Y</div>
          <div className={`text-xs font-semibold ${retColor(idx.return_1y)}`}>{fmtPct(idx.return_1y, 1)}</div>
        </div>
      </div>

      {/* View in Screener — interactive, sits above the card overlay */}
      {screenerHref && (
        <div className="relative z-[2] mt-3 pt-2.5 border-t border-slate-700/60">
          <Link
            href={screenerHref}
            className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300 transition-colors font-medium"
          >
            <ExternalLink className="w-3 h-3" />
            View in Screener
          </Link>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

function IndicesContent() {
  const [data, setData] = useState<IndicesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getIndices()
      setData(res)
      setLastUpdated(new Date())
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail ?? (e as { message?: string })?.message ?? 'Failed to load'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const mainIndices   = data?.indices.filter(i =>  ['ASX20','ASX50','ASX100','ASX200','ASX300','AXJO'].includes(i.index_code)) ?? []
  const sectorIndices = data?.indices.filter(i => !['ASX20','ASX50','ASX100','ASX200','ASX300','AXJO'].includes(i.index_code)) ?? []

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* Hero */}
      <div className="bg-gradient-to-br from-slate-800 via-slate-800 to-slate-900 border-b border-slate-700">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="mb-4">
            <Breadcrumb theme="dark" crumbs={[{ label: 'Market', href: '/market' }, { label: 'ASX Indices', href: '/indices' }]} />
          </div>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3 mb-1">
                <BarChart2 className="w-7 h-7 text-blue-400" />
                <h1 className="text-2xl font-bold text-white">ASX Indices</h1>
              </div>
              <p className="text-slate-400 text-sm mt-1">
                Latest performance for S&P/ASX benchmark indices and GICS sector indices.
              </p>
              {data?.as_of && (
                <p className="text-slate-500 text-xs mt-1">As of {data.as_of}</p>
              )}
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={load}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-200 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              <Link href="/market" className="text-sm text-slate-400 hover:text-blue-400 transition-colors">
                ← Market Overview
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 flex items-center gap-3">
            <Info className="w-5 h-5 text-red-400 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-red-300">Failed to load index data</p>
              <p className="text-xs text-red-400 mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {loading && !data && (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <RefreshCw className="w-8 h-8 text-blue-400 animate-spin mx-auto mb-3" />
              <p className="text-slate-400 text-sm">Loading index data…</p>
            </div>
          </div>
        )}

        {/* No data notice */}
        {!loading && data && data.indices.every(i => i.close_price == null) && (
          <div className="bg-amber-900/20 border border-amber-700/50 rounded-xl p-5 flex items-start gap-3">
            <Info className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-amber-300">Price data not yet available</p>
              <p className="text-xs text-amber-400 mt-1">
                Index prices are ingested by the nightly data pipeline. Run the index ingestion
                script (<code className="bg-amber-900/40 px-1 rounded">compute/engine/index_prices.py</code>) to populate historical data.
              </p>
            </div>
          </div>
        )}

        {/* Summary cards — main indices */}
        {mainIndices.length > 0 && (
          <div>
            <h2 className="text-base font-semibold text-slate-300 mb-4">Benchmark Indices</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {mainIndices.map(idx => (
                <SummaryCard key={idx.index_code} idx={idx} />
              ))}
            </div>
          </div>
        )}

        {/* Full table */}
        {data && data.indices.length > 0 && (
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-700 flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-200">All Indices — Performance</h2>
              <div className="flex items-center gap-3">
                {lastUpdated && (
                  <span className="text-xs text-slate-500">
                    Updated {lastUpdated.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
                {data.indices.length > 0 && (
                  <button
                    onClick={() => exportCSV(data.indices, data.as_of ?? undefined)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-xs text-slate-300 transition-colors"
                    title="Export all index data as CSV"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Export CSV
                  </button>
                )}
              </div>
            </div>

            {/* Table header */}
            <div className="grid grid-cols-9 gap-3 px-5 py-3 bg-slate-900/50 border-b border-slate-700 text-xs font-semibold text-slate-400 uppercase tracking-wide">
              <div className="col-span-2">Index</div>
              <div className="text-right">Price / 1D</div>
              <div className="text-right">1W</div>
              <div className="text-right">1M</div>
              <div className="text-right">3M</div>
              <div className="text-right">1Y</div>
              <div className="text-right">52W Range</div>
              <div className="text-right">Actions</div>
            </div>

            {/* Benchmark rows */}
            {mainIndices.length > 0 && (
              <>
                <div className="px-5 py-2 bg-slate-900/30">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Benchmark</span>
                </div>
                {mainIndices.map(idx => (
                  <IndexRow key={idx.index_code} idx={idx} isHighlighted={idx.index_code === 'ASX200'} />
                ))}
              </>
            )}

            {/* Sector rows */}
            {sectorIndices.length > 0 && (
              <>
                <div className="px-5 py-2 bg-slate-900/30 border-t border-slate-700">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">GICS Sectors</span>
                </div>
                {sectorIndices.map(idx => (
                  <IndexRow key={idx.index_code} idx={idx} isHighlighted={false} />
                ))}
              </>
            )}
          </div>
        )}

        {/* Data source note */}
        <div className="flex items-start gap-2 text-xs text-slate-600 pb-4">
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <p>
            Index data is updated from the latest available market data. Returns are price returns and do not include dividends.
            S&P/ASX indices are rebalanced quarterly. Past performance is not indicative of future results.
          </p>
        </div>
      </div>
    </div>
  )
}

export default function IndicesPage() {
  return (
    <PlanGate required="premium" feature="ASX Indices">
      <IndicesContent />
    </PlanGate>
  )
}
