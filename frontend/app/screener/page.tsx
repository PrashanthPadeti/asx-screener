'use client'
import { useState, useCallback } from 'react'
import { runScreener, type ScreenerFilter, type ScreenerRow } from '@/lib/api'
import { formatPrice, formatChangePct, formatVolume, formatMarketCap, cn, SECTOR_COLORS, SECTORS } from '@/lib/utils'
import { Plus, Trash2, Play, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import Link from 'next/link'

// ── Filter config ─────────────────────────────────────────────
const FILTER_FIELDS = [
  { value: 'sector',           label: 'Sector',              type: 'sector' },
  { value: 'close',            label: 'Price (AUD)',          type: 'number' },
  { value: 'volume',           label: 'Volume',              type: 'number' },
  { value: 'change_pct',       label: '1D Change %',         type: 'number' },
  { value: 'high_52w',         label: '52W High',            type: 'number' },
  { value: 'low_52w',          label: '52W Low',             type: 'number' },
  { value: 'is_reit',          label: 'Is REIT',             type: 'boolean' },
  { value: 'is_miner',         label: 'Is Miner',            type: 'boolean' },
  { value: 'is_asx200',        label: 'In ASX 200',          type: 'boolean' },
  { value: 'market_cap',       label: 'Market Cap (AUD M)',  type: 'number' },
  { value: 'pe_ratio',         label: 'P/E Ratio',           type: 'number' },
  { value: 'pb_ratio',         label: 'P/B Ratio',           type: 'number' },
  { value: 'dividend_yield',   label: 'Dividend Yield %',    type: 'number' },
  { value: 'grossed_up_yield', label: 'Grossed-Up Yield %',  type: 'number' },
  { value: 'roe',              label: 'ROE %',               type: 'number' },
  { value: 'debt_to_equity',   label: 'Debt / Equity',       type: 'number' },
  { value: 'piotroski_score',  label: 'Piotroski Score',     type: 'number' },
]

const NUMBER_OPS = [
  { value: 'gte', label: '>=' },
  { value: 'lte', label: '<=' },
  { value: 'gt',  label: '>'  },
  { value: 'lt',  label: '<'  },
  { value: 'eq',  label: '='  },
]

interface FilterRow { id: number; field: string; operator: string; value: string }

let nextId = 1

export default function ScreenerPage() {
  const [filters, setFilters]     = useState<FilterRow[]>([])
  const [results, setResults]     = useState<ScreenerRow[]>([])
  const [total, setTotal]         = useState(0)
  const [page, setPage]           = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading]     = useState(false)
  const [sortBy, setSortBy]       = useState('close')
  const [sortDir, setSortDir]     = useState<'asc'|'desc'>('desc')
  const [ran, setRan]             = useState(false)

  const addFilter = () => {
    setFilters(f => [...f, { id: nextId++, field: 'close', operator: 'gte', value: '' }])
  }

  const removeFilter = (id: number) => setFilters(f => f.filter(r => r.id !== id))

  const updateFilter = (id: number, key: keyof FilterRow, val: string) => {
    setFilters(f => f.map(r => r.id === id ? { ...r, [key]: val } : r))
  }

  const handleSort = (col: string) => {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortDir('desc') }
  }

  const runScreen = useCallback(async (p = 1) => {
    setLoading(true)
    setRan(true)
    try {
      const apiFilters: ScreenerFilter[] = filters
        .filter(f => f.value !== '')
        .map(f => {
          const fieldCfg = FILTER_FIELDS.find(x => x.value === f.field)
          let value: string | number | boolean = f.value
          if (fieldCfg?.type === 'number') value = parseFloat(f.value)
          if (fieldCfg?.type === 'boolean') value = f.value === 'true'
          return { field: f.field, operator: f.operator, value }
        })

      const res = await runScreener(apiFilters, { sort_by: sortBy, sort_dir: sortDir, page: p, page_size: 50 })
      setResults(res.data)
      setTotal(res.total)
      setPage(res.page)
      setTotalPages(res.total_pages)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [filters, sortBy, sortDir])

  const SortIcon = ({ col }: { col: string }) => {
    if (sortBy !== col) return null
    return sortDir === 'asc'
      ? <ChevronUp className="w-3 h-3 inline ml-0.5" />
      : <ChevronDown className="w-3 h-3 inline ml-0.5" />
  }

  const thCls = (col: string) =>
    cn('px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-800 whitespace-nowrap',
       sortBy === col && 'text-blue-600')

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Stock Screener</h1>
        <span className="text-sm text-gray-500">1,978 ASX stocks</span>
      </div>

      {/* Filter builder */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-800 text-sm">Filters</h2>
          <button onClick={addFilter}
            className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 font-medium">
            <Plus className="w-4 h-4" /> Add Filter
          </button>
        </div>

        {filters.length === 0 && (
          <p className="text-sm text-gray-400 py-2">
            No filters — click "Add Filter" or run to see all stocks
          </p>
        )}

        {filters.map(f => {
          const fieldCfg = FILTER_FIELDS.find(x => x.value === f.field)
          return (
            <div key={f.id} className="flex items-center gap-2 flex-wrap">
              {/* Field */}
              <select value={f.field} onChange={e => updateFilter(f.id, 'field', e.target.value)}
                className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                {FILTER_FIELDS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>

              {/* Operator */}
              {fieldCfg?.type === 'number' && (
                <select value={f.operator} onChange={e => updateFilter(f.id, 'operator', e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                  {NUMBER_OPS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              )}

              {/* Value */}
              {fieldCfg?.type === 'number' && (
                <input type="number" value={f.value} onChange={e => updateFilter(f.id, 'value', e.target.value)}
                  placeholder="Value"
                  className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 w-28 focus:outline-none focus:ring-2 focus:ring-blue-500" />
              )}
              {fieldCfg?.type === 'sector' && (
                <>
                  <span className="text-sm text-gray-500">=</span>
                  <select value={f.value} onChange={e => updateFilter(f.id, 'value', e.target.value)}
                    className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option value="">Select sector</option>
                    {SECTORS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </>
              )}
              {fieldCfg?.type === 'boolean' && (
                <>
                  <span className="text-sm text-gray-500">=</span>
                  <select value={f.value} onChange={e => updateFilter(f.id, 'value', e.target.value)}
                    className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                  </select>
                </>
              )}

              <button onClick={() => removeFilter(f.id)} className="text-gray-400 hover:text-red-500 p-1">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          )
        })}

        <div className="pt-2 flex items-center gap-3">
          <button onClick={() => runScreen(1)} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-semibold
                       rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-60">
            <Play className="w-4 h-4" />
            {loading ? 'Running...' : 'Run Screen'}
          </button>
          {ran && !loading && (
            <span className="text-sm text-gray-500">
              {total.toLocaleString()} stocks matched
            </span>
          )}
        </div>
      </div>

      {/* Results table */}
      {results.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className={thCls('asx_code')} onClick={() => handleSort('asx_code')}>Code <SortIcon col="asx_code" /></th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Company</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Sector</th>
                  <th className={thCls('close')} onClick={() => handleSort('close')}>Price <SortIcon col="close" /></th>
                  <th className={thCls('change_pct')} onClick={() => handleSort('change_pct')}>1D% <SortIcon col="change_pct" /></th>
                  <th className={thCls('volume')} onClick={() => handleSort('volume')}>Volume <SortIcon col="volume" /></th>
                  <th className={thCls('high_52w')} onClick={() => handleSort('high_52w')}>52W High <SortIcon col="high_52w" /></th>
                  <th className={thCls('low_52w')} onClick={() => handleSort('low_52w')}>52W Low <SortIcon col="low_52w" /></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {results.map(r => (
                  <tr key={r.asx_code} className="hover:bg-blue-50 transition-colors">
                    <td className="px-3 py-2.5">
                      <Link href={`/company/${r.asx_code}`}
                        className="font-mono font-bold text-blue-600 hover:text-blue-800 hover:underline">
                        {r.asx_code}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-gray-800 max-w-[180px] truncate">{r.company_name}</td>
                    <td className="px-3 py-2.5">
                      {r.gics_sector && (
                        <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium',
                          SECTOR_COLORS[r.gics_sector] || SECTOR_COLORS['Other'])}>
                          {r.gics_sector}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 font-medium text-gray-900">{formatPrice(r.close)}</td>
                    <td className={cn('px-3 py-2.5 font-medium',
                      r.change_pct == null ? 'text-gray-400' :
                      r.change_pct >= 0 ? 'text-green-600' : 'text-red-600')}>
                      {formatChangePct(r.change_pct)}
                    </td>
                    <td className="px-3 py-2.5 text-gray-600">{formatVolume(r.volume)}</td>
                    <td className="px-3 py-2.5 text-gray-600">{formatPrice(r.high_52w)}</td>
                    <td className="px-3 py-2.5 text-gray-600">{formatPrice(r.low_52w)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
            <span className="text-sm text-gray-500">
              Page {page} of {totalPages} · {total.toLocaleString()} results
            </span>
            <div className="flex gap-2">
              <button onClick={() => runScreen(page - 1)} disabled={page <= 1 || loading}
                className="p-1.5 rounded-lg border border-gray-300 disabled:opacity-40 hover:bg-white">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button onClick={() => runScreen(page + 1)} disabled={page >= totalPages || loading}
                className="p-1.5 rounded-lg border border-gray-300 disabled:opacity-40 hover:bg-white">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {ran && !loading && results.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          No stocks match your filters. Try relaxing the criteria.
        </div>
      )}
    </div>
  )
}
