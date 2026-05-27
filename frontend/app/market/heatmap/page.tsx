'use client'
import { useEffect, useState, useMemo, useCallback } from 'react'
import Link from 'next/link'
import {
  LayoutGrid, ChevronUp, ChevronDown, RefreshCw,
  TrendingUp, TrendingDown, Filter, Info, Download,
} from 'lucide-react'
import { getMarketHeatmap, type HeatmapRow } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

// ── Constants ─────────────────────────────────────────────────────────────────

const SECTORS = [
  'All Sectors',
  'Materials',
  'Financials',
  'Industrials',
  'Energy',
  'Healthcare',
  'Technology',
  'Consumer Discretionary',
  'Consumer Staples',
  'Real Estate',
  'Communication Services',
  'Utilities',
  'Other',
]

const CAP_TIERS: { label: string; minCap: number }[] = [
  { label: 'All Caps',  minCap: 0       },
  { label: '$1B+',      minCap: 1000    },
  { label: '$500M+',    minCap: 500     },
  { label: '$100M+',    minCap: 100     },
  { label: '$50M+',     minCap: 50      },
]

type SortKey = 'company_name' | 'sector' | 'price' | 'market_cap' | 'p1' | 'p2' | 'p3' | 'p4' | 'p5'
type SortDir = 'asc' | 'desc'

// ── Heat colour helpers ───────────────────────────────────────────────────────

function heatBg(pct: number | null): string {
  if (pct === null || pct === undefined) return 'bg-gray-100'
  if (pct >=  0.05) return 'bg-emerald-700'
  if (pct >=  0.02) return 'bg-emerald-500'
  if (pct >=  0.005) return 'bg-emerald-200'
  if (pct >= -0.005) return 'bg-orange-300'   // ~flat
  if (pct >= -0.02) return 'bg-red-200'
  if (pct >= -0.05) return 'bg-red-500'
  return 'bg-red-700'
}

function heatText(pct: number | null): string {
  if (pct === null || pct === undefined) return 'text-gray-400'
  if (Math.abs(pct) >= 0.02) return 'text-white'
  if (Math.abs(pct) < 0.005) return 'text-orange-900'  // flat — dark on orange
  if (pct > 0) return 'text-emerald-800'
  return 'text-red-800'
}

function fmtPct(v: number | null): string {
  if (v === null || v === undefined) return '—'
  const p = v * 100
  return (p >= 0 ? '+' : '') + p.toFixed(1) + '%'
}

function fmtCap(v: number | null): string {
  if (v === null || v === undefined) return '—'
  const m = v / 1_000_000  // raw AUD → AUD M
  if (m >= 1000) return '$' + (m / 1000).toFixed(1) + 'B'
  if (m >= 1)    return '$' + m.toFixed(0) + 'M'
  return '$' + m.toFixed(1) + 'M'
}

// ── Sort helpers ──────────────────────────────────────────────────────────────

function sortRows(rows: HeatmapRow[], key: SortKey, dir: SortDir): HeatmapRow[] {
  return [...rows].sort((a, b) => {
    const av = a[key]
    const bv = b[key]
    if (av === null || av === undefined) return 1
    if (bv === null || bv === undefined) return -1
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return dir === 'asc' ? cmp : -cmp
  })
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SortTh({
  label, sortKey, current, dir, onClick,
}: {
  label: string
  sortKey: SortKey
  current: SortKey
  dir: SortDir
  onClick: (k: SortKey) => void
}) {
  const active = current === sortKey
  return (
    <th
      className={cn(
        'px-2 py-2 text-left text-xs font-semibold cursor-pointer select-none whitespace-nowrap',
        'hover:bg-gray-100 transition-colors',
        active ? 'text-blue-700 bg-blue-50' : 'text-gray-600',
      )}
      onClick={() => onClick(sortKey)}
    >
      <span className="flex items-center gap-0.5">
        {label}
        {active
          ? dir === 'asc'
            ? <ChevronUp className="w-3 h-3" />
            : <ChevronDown className="w-3 h-3" />
          : <ChevronDown className="w-3 h-3 opacity-30" />}
      </span>
    </th>
  )
}

function PeriodTh({
  label, pKey, current, dir, onClick,
}: {
  label: string
  pKey: SortKey
  current: SortKey
  dir: SortDir
  onClick: (k: SortKey) => void
}) {
  const active = current === pKey
  return (
    <th
      className={cn(
        'w-24 px-1 py-2 text-center text-xs font-semibold cursor-pointer select-none',
        'hover:bg-gray-100 transition-colors',
        active ? 'text-blue-700 bg-blue-50' : 'text-gray-600',
      )}
      onClick={() => onClick(pKey)}
    >
      <span className="flex flex-col items-center gap-0">
        <span>{label}</span>
        {active
          ? dir === 'asc'
            ? <ChevronUp className="w-3 h-3" />
            : <ChevronDown className="w-3 h-3" />
          : <ChevronDown className="w-3 h-3 opacity-20" />}
      </span>
    </th>
  )
}

// ── Legend ────────────────────────────────────────────────────────────────────

function Legend() {
  const steps: { bg: string; text: string; label: string }[] = [
    { bg: 'bg-red-700',     text: 'text-white',       label: '< −5%' },
    { bg: 'bg-red-500',     text: 'text-white',       label: '−5 to −2%' },
    { bg: 'bg-red-200',     text: 'text-red-800',     label: '−2 to 0%' },
    { bg: 'bg-orange-300',  text: 'text-orange-900',  label: '~flat' },
    { bg: 'bg-emerald-200', text: 'text-emerald-800', label: '0 to +2%' },
    { bg: 'bg-emerald-500', text: 'text-white',       label: '+2 to +5%' },
    { bg: 'bg-emerald-700', text: 'text-white',       label: '> +5%' },
  ]
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-xs text-gray-500 mr-1">Legend:</span>
      {steps.map(s => (
        <span key={s.label}
          className={cn('text-xs px-1.5 py-0.5 rounded font-medium', s.bg, s.text)}>
          {s.label}
        </span>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

const PAGE_SIZE = 200

export default function HeatmapPage() {
  const { user } = useAuth()

  const [mode,        setMode]        = useState<'days' | 'weeks'>('days')
  const [sector,      setSector]      = useState('All Sectors')
  const [capTier,     setCapTier]     = useState(0)       // index into CAP_TIERS
  const [rows,        setRows]        = useState<HeatmapRow[]>([])
  const [labels,      setLabels]      = useState<string[]>(['', '', '', '', ''])
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState<string | null>(null)
  const [sortKey,     setSortKey]     = useState<SortKey>('market_cap')
  const [sortDir,     setSortDir]     = useState<SortDir>('desc')
  const [page,        setPage]        = useState(1)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [exporting,   setExporting]   = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const sectorParam = sector === 'All Sectors' ? undefined : sector
      const minCap      = CAP_TIERS[capTier].minCap
      const res = await getMarketHeatmap(mode, sectorParam, minCap)
      setRows(res.rows)
      setLabels(res.labels.length === 5 ? res.labels : ['', '', '', '', ''])
      setLastUpdated(new Date())
      setPage(1)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load heatmap')
    } finally {
      setLoading(false)
    }
  }, [mode, sector, capTier])

  useEffect(() => { fetchData() }, [fetchData])

  const handleExport = useCallback(async () => {
    setExporting(true)
    try {
      const sectorParam = sector === 'All Sectors' ? '' : `&sector=${encodeURIComponent(sector)}`
      const minCap      = CAP_TIERS[capTier].minCap
      const url = `/api/v1/market/heatmap/export?mode=${mode}${sectorParam}&min_cap=${minCap}`
      const res = await fetch(url)
      if (!res.ok) throw new Error('Export failed')
      const blob  = await res.blob()
      const href  = URL.createObjectURL(blob)
      const a     = document.createElement('a')
      const today = new Date().toISOString().slice(0, 10)
      a.href     = href
      a.download = `ASX_Heatmap_${mode}_${today}.xlsx`
      a.click()
      URL.revokeObjectURL(href)
    } catch {
      // silently ignore — network errors will surface via the fetch
    } finally {
      setExporting(false)
    }
  }, [mode, sector, capTier])

  // Sort
  const sorted = useMemo(
    () => sortRows(rows, sortKey, sortDir),
    [rows, sortKey, sortDir],
  )

  const paginated = useMemo(
    () => sorted.slice(0, page * PAGE_SIZE),
    [sorted, page],
  )

  const hasMore = paginated.length < sorted.length

  function handleSort(k: SortKey) {
    if (k === sortKey) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(k)
      setSortDir(['price', 'market_cap', 'p1', 'p2', 'p3', 'p4', 'p5'].includes(k) ? 'desc' : 'asc')
    }
  }

  // Stats bar
  const stats = useMemo(() => {
    if (!rows.length) return null
    const withP1 = rows.filter(r => r.p1 !== null)
    const gainers = withP1.filter(r => (r.p1 ?? 0) > 0).length
    const losers  = withP1.filter(r => (r.p1 ?? 0) < 0).length
    return { gainers, losers, total: rows.length }
  }, [rows])

  const modeLabel = mode === 'days' ? 'Daily Returns' : 'Weekly Returns'

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-screen-2xl mx-auto px-4 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-50 rounded-lg">
                <LayoutGrid className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">Performance Heatmap</h1>
                <p className="text-sm text-gray-500">
                  Rolling {mode === 'days' ? '5-day' : '5-week'} price performance — all ASX stocks
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {lastUpdated && (
                <span className="text-xs text-gray-400">
                  Updated {lastUpdated.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
              <button
                onClick={handleExport}
                disabled={loading || exporting || rows.length === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium
                           text-emerald-700 bg-emerald-50 hover:bg-emerald-100
                           border border-emerald-200 rounded-lg transition-colors
                           disabled:opacity-40 disabled:cursor-not-allowed"
                title="Download as colour-coded Excel file"
              >
                <Download className={cn('w-3.5 h-3.5', exporting && 'animate-bounce')} />
                {exporting ? 'Exporting…' : 'Export Excel'}
              </button>
              <button
                onClick={fetchData}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 bg-gray-100
                           hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
              >
                <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-screen-2xl mx-auto px-4 py-4 space-y-4">

        {/* ── Controls ────────────────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex flex-wrap items-center gap-3">

            {/* Mode toggle */}
            <div className="flex rounded-lg border border-gray-200 overflow-hidden">
              <button
                onClick={() => setMode('days')}
                className={cn(
                  'px-4 py-2 text-sm font-medium transition-colors',
                  mode === 'days'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-50',
                )}
              >
                Last 5 Days
              </button>
              <button
                onClick={() => setMode('weeks')}
                className={cn(
                  'px-4 py-2 text-sm font-medium transition-colors border-l border-gray-200',
                  mode === 'weeks'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-50',
                )}
              >
                Last 5 Weeks
              </button>
            </div>

            {/* Sector filter */}
            <div className="flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5 text-gray-400" />
              <select
                value={sector}
                onChange={e => setSector(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white
                           text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {SECTORS.map(s => <option key={s}>{s}</option>)}
              </select>
            </div>

            {/* Cap tier filter */}
            <select
              value={capTier}
              onChange={e => setCapTier(Number(e.target.value))}
              className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white
                         text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {CAP_TIERS.map((t, i) => (
                <option key={t.label} value={i}>{t.label}</option>
              ))}
            </select>

            {/* Stats */}
            {stats && !loading && (
              <div className="ml-auto flex items-center gap-4 text-sm">
                <span className="text-gray-500">{stats.total.toLocaleString()} stocks</span>
                <span className="flex items-center gap-1 text-emerald-600 font-medium">
                  <TrendingUp className="w-3.5 h-3.5" />
                  {stats.gainers} up
                </span>
                <span className="flex items-center gap-1 text-red-500 font-medium">
                  <TrendingDown className="w-3.5 h-3.5" />
                  {stats.losers} down
                </span>
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="mt-3 pt-3 border-t border-gray-100">
            <Legend />
          </div>
        </div>

        {/* ── Info note ───────────────────────────────────────────────────────── */}
        <div className="flex items-start gap-2 p-3 bg-blue-50 border border-blue-100 rounded-lg text-xs text-blue-700">
          <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <span>
            {mode === 'days'
              ? 'Each column shows the daily % price change for that trading day. Column 1 is the most recent trading day.'
              : 'Each column shows the weekly % change (Friday close vs prior Friday close). Column 1 is the most recent completed week.'}
            {' '}Columns are sorted newest → oldest (left to right).
          </span>
        </div>

        {/* ── Error ───────────────────────────────────────────────────────────── */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* ── Table ───────────────────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-20 gap-3 text-gray-500">
              <RefreshCw className="w-5 h-5 animate-spin" />
              <span>Loading {modeLabel.toLowerCase()}…</span>
            </div>
          ) : rows.length === 0 ? (
            <div className="flex items-center justify-center py-20 text-gray-500 text-sm">
              No data available for the selected filters.
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 w-16">#</th>
                      <th className="px-2 py-2 text-left text-xs font-semibold text-gray-500 w-16">Code</th>
                      <SortTh label="Company"     sortKey="company_name" current={sortKey} dir={sortDir} onClick={handleSort} />
                      <SortTh label="Sector"      sortKey="sector"       current={sortKey} dir={sortDir} onClick={handleSort} />
                      <th className="px-2 py-2 text-left text-xs font-semibold text-gray-500 hidden lg:table-cell">Industry</th>
                      <SortTh label="Price"       sortKey="price"        current={sortKey} dir={sortDir} onClick={handleSort} />
                      <SortTh label="Mkt Cap"     sortKey="market_cap"   current={sortKey} dir={sortDir} onClick={handleSort} />
                      <PeriodTh label={labels[0] || 'P1'} pKey="p1" current={sortKey} dir={sortDir} onClick={handleSort} />
                      <PeriodTh label={labels[1] || 'P2'} pKey="p2" current={sortKey} dir={sortDir} onClick={handleSort} />
                      <PeriodTh label={labels[2] || 'P3'} pKey="p3" current={sortKey} dir={sortDir} onClick={handleSort} />
                      <PeriodTh label={labels[3] || 'P4'} pKey="p4" current={sortKey} dir={sortDir} onClick={handleSort} />
                      <PeriodTh label={labels[4] || 'P5'} pKey="p5" current={sortKey} dir={sortDir} onClick={handleSort} />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {paginated.map((row, idx) => (
                      <tr
                        key={row.asx_code}
                        className="hover:bg-blue-50/40 transition-colors"
                      >
                        <td className="px-3 py-1.5 text-xs text-gray-400 tabular-nums">
                          {idx + 1}
                        </td>
                        <td className="px-2 py-1.5 font-mono font-semibold text-xs">
                          <Link
                            href={`/company/${row.asx_code}`}
                            className="text-blue-600 hover:text-blue-800 hover:underline"
                          >
                            {row.asx_code}
                          </Link>
                        </td>
                        <td className="px-2 py-1.5 text-xs text-gray-800 max-w-[180px] truncate">
                          <Link
                            href={`/company/${row.asx_code}`}
                            className="hover:text-blue-600 hover:underline"
                            title={row.company_name}
                          >
                            {row.company_name}
                          </Link>
                        </td>
                        <td className="px-2 py-1.5 text-xs text-gray-600 whitespace-nowrap">
                          {row.sector ?? '—'}
                        </td>
                        <td className="px-2 py-1.5 text-xs text-gray-500 hidden lg:table-cell max-w-[140px] truncate"
                            title={row.industry ?? ''}>
                          {row.industry ?? '—'}
                        </td>
                        <td className="px-2 py-1.5 text-xs text-right font-mono tabular-nums">
                          {row.price != null ? `$${row.price.toFixed(3)}` : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-xs text-right tabular-nums text-gray-600">
                          {fmtCap(row.market_cap)}
                        </td>
                        {/* Heat cells */}
                        {(['p1', 'p2', 'p3', 'p4', 'p5'] as const).map(pk => (
                          <td key={pk} className="px-1 py-1">
                            <div className={cn(
                              'flex items-center justify-center w-full h-7 rounded text-xs font-semibold tabular-nums',
                              heatBg(row[pk]),
                              heatText(row[pk]),
                            )}>
                              {fmtPct(row[pk])}
                            </div>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Load more */}
              {hasMore && (
                <div className="flex items-center justify-center py-4 border-t border-gray-100">
                  <button
                    onClick={() => setPage(p => p + 1)}
                    className="px-6 py-2 text-sm font-medium text-blue-600 bg-blue-50
                               hover:bg-blue-100 rounded-lg transition-colors"
                  >
                    Load more ({sorted.length - paginated.length} remaining)
                  </button>
                </div>
              )}

              {/* Footer summary */}
              <div className="px-4 py-2.5 bg-gray-50 border-t border-gray-100 text-xs text-gray-500">
                Showing {paginated.length.toLocaleString()} of {sorted.length.toLocaleString()} stocks
                {sector !== 'All Sectors' && ` · Sector: ${sector}`}
                {CAP_TIERS[capTier].minCap > 0 && ` · Min cap: ${CAP_TIERS[capTier].label}`}
              </div>
            </>
          )}
        </div>

        {/* ── Disclaimer ──────────────────────────────────────────────────────── */}
        <p className="text-xs text-gray-400 text-center pb-4">
          Price data sourced from EOD Historical Data. Past performance is not indicative of future results.
          This is not financial advice.
        </p>
      </div>
    </div>
  )
}
