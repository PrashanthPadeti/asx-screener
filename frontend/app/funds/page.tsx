'use client'
import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { TrendingUp, TrendingDown, Filter, RefreshCw, Info, Search, X } from 'lucide-react'
import { getFunds, FundsResponse, FundRow } from '@/lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  return (pct >= 0 ? '+' : '') + pct.toFixed(decimals) + '%'
}

function fmtDist(v: number | null): string {
  if (v == null) return '—'
  return (v * 100).toFixed(2) + '%'
}

function fmtAUM(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1) return '$' + v.toFixed(1) + 'B'
  return '$' + (v * 1000).toFixed(0) + 'M'
}

function fmtMER(v: number | null): string {
  if (v == null) return '—'
  return (v * 100).toFixed(2) + '%'
}

function fmtPrice(v: number | null): string {
  if (v == null) return '—'
  return '$' + v.toFixed(2)
}

function retColor(v: number | null): string {
  if (v == null) return 'text-slate-400'
  if (v > 0) return 'text-emerald-500'
  if (v < 0) return 'text-red-400'
  return 'text-slate-400'
}

function typeBadge(type: string): string {
  switch (type) {
    case 'ETF':     return 'bg-blue-900/60 text-blue-300 border border-blue-700/50'
    case 'LIC':     return 'bg-purple-900/60 text-purple-300 border border-purple-700/50'
    case 'MANAGED': return 'bg-amber-900/60 text-amber-300 border border-amber-700/50'
    default:        return 'bg-slate-700 text-slate-300'
  }
}

const ASSET_CLASSES = [
  'All',
  'Australian Equities',
  'Global Equities',
  'Fixed Income',
  'Property',
  'Commodities',
  'Multi-Asset',
]

const SORT_OPTIONS: { label: string; value: string }[] = [
  { label: 'AUM',         value: 'funds_under_mgmt_bn' },
  { label: '1Y Return',   value: 'return_1y' },
  { label: 'YTD Return',  value: 'return_ytd' },
  { label: 'Dist. Yield', value: 'distribution_yield' },
  { label: 'MER (low)',   value: 'mer_pct' },
]

// ── Fund row ──────────────────────────────────────────────────────────────────

function FundCard({ fund }: { fund: FundRow }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 hover:border-slate-600 transition-all hover:bg-slate-750">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              href={`/company/${fund.asx_code}`}
              className="text-sm font-bold text-white hover:text-blue-400 transition-colors"
            >
              {fund.asx_code}
            </Link>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${typeBadge(fund.fund_type)}`}>
              {fund.fund_type}
            </span>
            {fund.is_hedged && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-700 text-slate-400 border border-slate-600">AUD Hedged</span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-1 leading-tight line-clamp-2">{fund.fund_name}</p>
        </div>
        <div className="text-right ml-3 shrink-0">
          <div className="text-sm font-semibold text-slate-100">{fmtPrice(fund.close_price)}</div>
          <div className={`text-xs font-medium ${retColor(fund.return_1d)}`}>{fmtPct(fund.return_1d)} 1D</div>
        </div>
      </div>

      {/* Manager & asset class */}
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-3">
        {fund.fund_manager && <span>{fund.fund_manager}</span>}
        {fund.fund_manager && fund.asset_class && <span className="text-slate-700">·</span>}
        {fund.asset_class && <span>{fund.asset_class}</span>}
        {fund.index_tracked && (
          <>
            <span className="text-slate-700">·</span>
            <span className="text-slate-400 italic truncate">{fund.index_tracked}</span>
          </>
        )}
      </div>

      {/* Performance grid */}
      <div className="grid grid-cols-5 gap-2 bg-slate-900/50 rounded-lg p-2.5 mb-3">
        {[
          { label: '1W',  v: fund.return_1w },
          { label: '1M',  v: fund.return_1m },
          { label: '1Y',  v: fund.return_1y },
          { label: 'YTD', v: fund.return_ytd },
          { label: 'Yield', v: null, custom: fmtDist(fund.distribution_yield), color: 'text-blue-400' },
        ].map(({ label, v, custom, color }) => (
          <div key={label} className="text-center">
            <div className="text-[10px] text-slate-500 uppercase">{label}</div>
            <div className={`text-xs font-semibold mt-0.5 ${custom ? color : retColor(v)}`}>
              {custom ?? fmtPct(v)}
            </div>
          </div>
        ))}
      </div>

      {/* Footer: AUM + MER */}
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>AUM: <span className="text-slate-300 font-medium">{fmtAUM(fund.funds_under_mgmt_bn)}</span></span>
        <span>MER: <span className="text-slate-300 font-medium">{fmtMER(fund.mer_pct)}</span></span>
        {fund.distribution_freq && (
          <span className="capitalize text-slate-600">{fund.distribution_freq} dist.</span>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FundsPage() {
  const [data, setData] = useState<FundsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [fundType, setFundType] = useState<'ETF' | 'LIC' | 'MANAGED' | 'ALL'>('ALL')
  const [assetClass, setAssetClass] = useState('All')
  const [sort, setSort] = useState('funds_under_mgmt_bn')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string | number> = { sort, order: sortOrder, limit: 100 }
      if (fundType !== 'ALL') params.fund_type = fundType
      if (assetClass !== 'All') params.asset_class = assetClass
      const res = await getFunds(params as Parameters<typeof getFunds>[0])
      setData(res)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail ?? (e as { message?: string })?.message ?? 'Failed to load'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [fundType, assetClass, sort, sortOrder])

  useEffect(() => { load() }, [load])

  const filtered = (data?.funds ?? []).filter(f => {
    if (!search) return true
    const q = search.toLowerCase()
    return f.asx_code.toLowerCase().includes(q) || f.fund_name.toLowerCase().includes(q) || (f.fund_manager ?? '').toLowerCase().includes(q)
  })

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {/* Hero */}
      <div className="bg-gradient-to-br from-slate-800 via-slate-800 to-slate-900 border-b border-slate-700">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                <Filter className="w-7 h-7 text-purple-400" />
                ETFs &amp; Managed Funds
              </h1>
              <p className="text-slate-400 text-sm mt-1">
                ASX-listed ETFs, LICs, and managed funds — performance, yield, AUM, and MER.
              </p>
              {data?.as_of && <p className="text-slate-500 text-xs mt-1">As of {data.as_of}</p>}
            </div>
            <Link href="/market" className="text-sm text-slate-400 hover:text-blue-400 transition-colors">
              ← Market Overview
            </Link>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Filters */}
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-4">
          {/* Fund type tabs */}
          <div className="flex items-center gap-1">
            {(['ALL', 'ETF', 'LIC', 'MANAGED'] as const).map(t => (
              <button
                key={t}
                onClick={() => setFundType(t)}
                className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  fundType === t
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-600'
                }`}
              >
                {t === 'ALL' ? 'All Types' : t}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Asset class */}
            <div className="flex flex-wrap gap-1">
              {ASSET_CLASSES.map(ac => (
                <button
                  key={ac}
                  onClick={() => setAssetClass(ac)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    assetClass === ac
                      ? 'bg-purple-600/30 text-purple-300 border border-purple-600/50'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {ac}
                </button>
              ))}
            </div>

            {/* Sort */}
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-xs text-slate-500">Sort:</span>
              <select
                value={sort}
                onChange={e => setSort(e.target.value)}
                className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-slate-300 focus:outline-none"
              >
                {SORT_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <button
                onClick={() => setSortOrder(o => o === 'desc' ? 'asc' : 'desc')}
                className="px-2 py-1 bg-slate-700 rounded text-xs text-slate-400 hover:text-slate-200"
              >
                {sortOrder === 'desc' ? '↓ Desc' : '↑ Asc'}
              </button>
            </div>

            {/* Search */}
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search funds…"
                className="bg-slate-700 border border-slate-600 rounded-lg pl-8 pr-8 py-1.5 text-xs text-slate-300 placeholder-slate-500 focus:outline-none focus:border-blue-500 w-48"
              />
              {search && (
                <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2">
                  <X className="w-3.5 h-3.5 text-slate-500 hover:text-slate-300" />
                </button>
              )}
            </div>

            <button
              onClick={load}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-xs text-slate-300 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 flex items-center gap-3">
            <Info className="w-5 h-5 text-red-400 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-red-300">Failed to load fund data</p>
              <p className="text-xs text-red-400 mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && !data && (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <RefreshCw className="w-8 h-8 text-purple-400 animate-spin mx-auto mb-3" />
              <p className="text-slate-400 text-sm">Loading fund data…</p>
            </div>
          </div>
        )}

        {/* No data */}
        {!loading && data && data.total === 0 && (
          <div className="bg-amber-900/20 border border-amber-700/50 rounded-xl p-5 flex items-start gap-3">
            <Info className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-amber-300">No fund data available yet</p>
              <p className="text-xs text-amber-400 mt-1">
                Fund data is populated by the data ingestion pipeline. Run{' '}
                <code className="bg-amber-900/40 px-1 rounded">compute/engine/fund_ingestion.py</code>{' '}
                to seed fund metadata and prices.
              </p>
            </div>
          </div>
        )}

        {/* Results count */}
        {data && filtered.length > 0 && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-400">
              <span className="font-semibold text-slate-200">{filtered.length}</span> fund{filtered.length !== 1 ? 's' : ''}
              {search && ` matching "${search}"`}
            </p>
          </div>
        )}

        {/* Fund grid */}
        {filtered.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map(fund => (
              <FundCard key={fund.asx_code} fund={fund} />
            ))}
          </div>
        )}

        {/* Disclaimer */}
        <div className="flex items-start gap-2 text-xs text-slate-600 pb-4">
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <p>
            Fund information is for research purposes only and does not constitute financial advice.
            MER, AUM and distribution yield figures sourced from public data and may not be current.
            Past performance is not indicative of future results. Always read the fund&apos;s PDS before investing.
          </p>
        </div>
      </div>
    </div>
  )
}
