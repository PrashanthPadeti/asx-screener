'use client'
import { useState, useCallback, useEffect, useRef } from 'react'
import {
  runScreener, getScreenerFields, getScreenerPresets, exportScreener,
  nlScreener,
  type ScreenerFilter, type ScreenerRow, type ScreenerFieldMeta,
  type ScreenerPreset, type NLScreenerResponse,
} from '@/lib/api'
import {
  formatPrice, formatVolume, formatMarketCap,
  formatRatio, formatRatioChange, formatPctRaw, cn, SECTOR_COLORS, SECTORS,
} from '@/lib/utils'
import {
  Plus, Trash2, Play, ChevronUp, ChevronDown,
  ChevronLeft, ChevronRight, SlidersHorizontal, Zap, X, Download,
  Sparkles, Search, Lock,
} from 'lucide-react'
import Link from 'next/link'
import WatchlistButton from '@/components/WatchlistButton'
import { useAuth } from '@/lib/auth'

// ── Column definitions ────────────────────────────────────────────────────────

interface ColDef {
  key:     keyof ScreenerRow | '_badge'
  label:   string
  sortKey?: string          // key used for ORDER BY (must be in SORTABLE_COLS)
  default: boolean
  always?: boolean
  align?:  'left' | 'right'
  render:  (r: ScreenerRow) => React.ReactNode
}

const ALL_COLUMNS: ColDef[] = [
  // Always visible
  {
    key: 'asx_code', label: 'Code', sortKey: 'asx_code',
    always: true, default: true, align: 'left',
    render: r => (
      <div className="flex items-center gap-1.5">
        <WatchlistButton code={r.asx_code} size="sm" />
        <Link href={`/company/${r.asx_code}`}
          className="font-mono font-bold text-blue-600 hover:text-blue-800 hover:underline">
          {r.asx_code}
        </Link>
      </div>
    ),
  },
  {
    key: 'company_name', label: 'Company',
    always: true, default: true, align: 'left',
    render: r => <span className="text-gray-800 max-w-[160px] truncate block">{r.company_name}</span>,
  },
  // Default columns
  {
    key: 'sector', label: 'Sector',
    default: true, align: 'left',
    render: r => r.sector
      ? <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium whitespace-nowrap',
          SECTOR_COLORS[r.sector] || SECTOR_COLORS['Other'])}>{r.sector}</span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'price', label: 'Price', sortKey: 'price',
    default: true, align: 'right',
    render: r => <span className="font-medium text-gray-900">{formatPrice(r.price)}</span>,
  },
  {
    key: 'market_cap', label: 'Mkt Cap', sortKey: 'market_cap',
    default: true, align: 'right',
    render: r => <span className="text-gray-700">{formatMarketCap(r.market_cap)}</span>,
  },
  {
    key: 'pe_ratio', label: 'P/E', sortKey: 'pe_ratio',
    default: true, align: 'right',
    render: r => r.pe_ratio != null
      ? <span className="text-gray-700">{r.pe_ratio.toFixed(1)}x</span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'roe', label: 'ROE %', sortKey: 'roe',
    default: true, align: 'right',
    render: r => r.roe != null
      ? <span className={r.roe >= 0.15 ? 'text-green-600 font-medium' : 'text-gray-700'}>
          {formatRatio(r.roe)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'dividend_yield', label: 'Div Yield', sortKey: 'dividend_yield',
    default: true, align: 'right',
    render: r => r.dividend_yield != null
      ? <span className="text-gray-700">{formatRatio(r.dividend_yield)}</span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'grossed_up_yield', label: 'Grossed-Up', sortKey: 'grossed_up_yield',
    default: true, align: 'right',
    render: r => r.grossed_up_yield != null
      ? <span className={r.grossed_up_yield >= 0.06 ? 'text-green-600 font-medium' : 'text-gray-700'}>
          {formatRatio(r.grossed_up_yield)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'franking_pct', label: 'Franking', sortKey: 'franking_pct',
    default: true, align: 'right',
    render: r => r.franking_pct != null
      ? <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded',
          r.franking_pct === 100 ? 'bg-green-100 text-green-700' :
          r.franking_pct > 0    ? 'bg-yellow-100 text-yellow-700' :
                                   'bg-gray-100 text-gray-500')}>
          {formatPctRaw(r.franking_pct, 0)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'piotroski_f_score', label: 'F-Score', sortKey: 'piotroski_f_score',
    default: true, align: 'right',
    render: r => r.piotroski_f_score != null
      ? <span className={cn('text-xs font-bold px-1.5 py-0.5 rounded',
          r.piotroski_f_score >= 7 ? 'bg-green-100 text-green-700' :
          r.piotroski_f_score >= 4 ? 'bg-yellow-100 text-yellow-700' :
                                      'bg-red-100 text-red-700')}>
          {r.piotroski_f_score}/9
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'return_1y', label: '1Y Return', sortKey: 'return_1y',
    default: true, align: 'right',
    render: r => r.return_1y != null
      ? <span className={r.return_1y >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>
          {formatRatioChange(r.return_1y)}
        </span>
      : <span className="text-gray-300">—</span>,
  },

  // Optional columns
  {
    key: 'forward_pe', label: 'Fwd P/E', sortKey: 'forward_pe',
    default: false, align: 'right',
    render: r => r.forward_pe != null
      ? <span className="text-gray-700">{r.forward_pe.toFixed(1)}x</span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'price_to_book', label: 'P/B', sortKey: 'price_to_book',
    default: false, align: 'right',
    render: r => r.price_to_book != null
      ? <span className="text-gray-700">{r.price_to_book.toFixed(2)}x</span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'ev_to_ebitda', label: 'EV/EBITDA', sortKey: 'ev_to_ebitda',
    default: false, align: 'right',
    render: r => r.ev_to_ebitda != null
      ? <span className="text-gray-700">{r.ev_to_ebitda.toFixed(1)}x</span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'net_margin', label: 'Net Margin', sortKey: 'net_margin',
    default: false, align: 'right',
    render: r => r.net_margin != null
      ? <span className={r.net_margin >= 0 ? 'text-gray-700' : 'text-red-500'}>
          {formatRatio(r.net_margin)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'ebitda_margin', label: 'EBITDA Mgn', sortKey: 'ebitda_margin',
    default: false, align: 'right',
    render: r => r.ebitda_margin != null
      ? <span className="text-gray-700">{formatRatio(r.ebitda_margin)}</span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'gross_margin', label: 'Gross Mgn', sortKey: 'gross_margin',
    default: false, align: 'right',
    render: r => r.gross_margin != null
      ? <span className="text-gray-700">{formatRatio(r.gross_margin)}</span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'revenue_growth_1y', label: 'Rev Growth 1Y', sortKey: 'revenue_growth_1y',
    default: false, align: 'right',
    render: r => r.revenue_growth_1y != null
      ? <span className={r.revenue_growth_1y >= 0 ? 'text-green-600' : 'text-red-500'}>
          {formatRatioChange(r.revenue_growth_1y)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'revenue_growth_hoh', label: 'Rev HoH ★', sortKey: 'revenue_growth_hoh',
    default: false, align: 'right',
    render: r => r.revenue_growth_hoh != null
      ? <span className={r.revenue_growth_hoh >= 0 ? 'text-green-600 font-medium' : 'text-red-500'}>
          {formatRatioChange(r.revenue_growth_hoh)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'eps_growth_hoh', label: 'EPS HoH ★', sortKey: 'eps_growth_hoh',
    default: false, align: 'right',
    render: r => r.eps_growth_hoh != null
      ? <span className={r.eps_growth_hoh >= 0 ? 'text-green-600 font-medium' : 'text-red-500'}>
          {formatRatioChange(r.eps_growth_hoh)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'debt_to_equity', label: 'D/E', sortKey: 'debt_to_equity',
    default: false, align: 'right',
    render: r => r.debt_to_equity != null
      ? <span className={r.debt_to_equity > 2 ? 'text-red-500' : 'text-gray-700'}>
          {r.debt_to_equity.toFixed(2)}x
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'current_ratio', label: 'Curr Ratio', sortKey: 'current_ratio',
    default: false, align: 'right',
    render: r => r.current_ratio != null
      ? <span className={r.current_ratio >= 1.5 ? 'text-green-600' : r.current_ratio < 1 ? 'text-red-500' : 'text-gray-700'}>
          {r.current_ratio.toFixed(2)}x
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'altman_z_score', label: 'Altman Z', sortKey: 'altman_z_score',
    default: false, align: 'right',
    render: r => r.altman_z_score != null
      ? <span className={r.altman_z_score >= 2.99 ? 'text-green-600' : r.altman_z_score < 1.81 ? 'text-red-500' : 'text-yellow-600'}>
          {r.altman_z_score.toFixed(2)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'rsi_14', label: 'RSI 14', sortKey: 'rsi_14',
    default: false, align: 'right',
    render: r => r.rsi_14 != null
      ? <span className={r.rsi_14 >= 70 ? 'text-red-500' : r.rsi_14 <= 30 ? 'text-green-600' : 'text-gray-700'}>
          {r.rsi_14.toFixed(1)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'return_ytd', label: 'YTD Return', sortKey: 'return_ytd',
    default: false, align: 'right',
    render: r => r.return_ytd != null
      ? <span className={r.return_ytd >= 0 ? 'text-green-600' : 'text-red-600'}>
          {formatRatioChange(r.return_ytd)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'return_3m', label: '3M Return', sortKey: 'return_3m',
    default: false, align: 'right',
    render: r => r.return_3m != null
      ? <span className={r.return_3m >= 0 ? 'text-green-600' : 'text-red-600'}>
          {formatRatioChange(r.return_3m)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'short_pct', label: 'Short %', sortKey: 'short_pct',
    default: false, align: 'right',
    render: r => r.short_pct != null
      ? <span className={r.short_pct >= 5 ? 'text-red-500' : 'text-gray-700'}>
          {formatPctRaw(r.short_pct)}
        </span>
      : <span className="text-gray-300">—</span>,
  },
  {
    key: 'volume', label: 'Volume', sortKey: 'volume',
    default: false, align: 'right',
    render: r => <span className="text-gray-600">{formatVolume(r.volume)}</span>,
  },
]

// ── Filter row types ──────────────────────────────────────────────────────────

interface FilterRow { id: number; field: string; operator: string; value: string }

let nextId = 1

// Operators by field type
const OPERATORS: Record<string, { value: string; label: string }[]> = {
  number:  [
    { value: 'gte', label: '>=' },
    { value: 'lte', label: '<=' },
    { value: 'gt',  label: '>'  },
    { value: 'lt',  label: '<'  },
    { value: 'eq',  label: '='  },
    { value: 'neq', label: '≠'  },
  ],
  boolean: [{ value: 'eq', label: 'is' }],
  text:    [
    { value: 'eq',  label: '=' },
    { value: 'neq', label: '≠' },
  ],
}

// ── Column picker popover ─────────────────────────────────────────────────────

function ColumnPicker({
  visibleKeys, onChange,
}: { visibleKeys: Set<string>; onChange: (keys: Set<string>) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const optional = ALL_COLUMNS.filter(c => !c.always)

  const toggle = (key: string) => {
    const next = new Set(visibleKeys)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onChange(next)
  }

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-lg
                   bg-white hover:bg-gray-50 text-gray-700 font-medium">
        <SlidersHorizontal className="w-4 h-4" /> Columns
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-20 bg-white border border-gray-200
                        rounded-xl shadow-lg p-3 w-64">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Toggle Columns
          </p>
          <div className="space-y-1 max-h-72 overflow-y-auto">
            {optional.map(col => (
              <label key={col.key as string}
                className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer
                           hover:text-gray-900 py-0.5">
                <input type="checkbox"
                  checked={visibleKeys.has(col.key as string)}
                  onChange={() => toggle(col.key as string)}
                  className="w-3.5 h-3.5 rounded border-gray-300 text-blue-600" />
                {col.label}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ScreenerPage() {
  const { user } = useAuth()
  const userPlan = user?.plan ?? 'free'
  const isPro = ['pro', 'premium', 'enterprise_pro', 'enterprise_premium'].includes(userPlan)

  const [showUpgradeModal, setShowUpgradeModal] = useState(false)

  // Filter state
  const [filters, setFilters] = useState<FilterRow[]>([])

  // API-loaded field metadata (for the filter builder dropdowns)
  const [fieldsByCategory, setFieldsByCategory] =
    useState<Record<string, ScreenerFieldMeta[]>>({})
  const [allFields, setAllFields] = useState<ScreenerFieldMeta[]>([])

  // Presets
  const [presets, setPresets] = useState<ScreenerPreset[]>([])
  const [activePreset, setActivePreset] = useState<string | null>(null)

  // Results state
  const [results, setResults]       = useState<ScreenerRow[]>([])
  const [total, setTotal]           = useState(0)
  const [page, setPage]             = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading]       = useState(false)
  const [ran, setRan]               = useState(false)
  const [exporting, setExporting]   = useState(false)
  const [sortBy, setSortBy]         = useState('market_cap')
  const [sortDir, setSortDir]       = useState<'asc' | 'desc'>('desc')

  // NL screener state
  const [nlQuery, setNlQuery]               = useState('')
  const [nlLoading, setNlLoading]           = useState(false)
  const [nlError, setNlError]               = useState<string | null>(null)
  const [nlResult, setNlResult]             = useState<NLScreenerResponse | null>(null)

  // Column visibility — persisted to localStorage
  const STORAGE_KEY = 'screener_visible_columns_v1'
  const defaultVisible = new Set(
    ALL_COLUMNS.filter(c => c.default || c.always).map(c => c.key as string)
  )
  const [visibleKeys, setVisibleKeysState] = useState<Set<string>>(defaultVisible)

  // Restore from localStorage on mount (client-only)
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed: string[] = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) {
          // Always include 'always' columns
          const alwaysKeys = ALL_COLUMNS.filter(c => c.always).map(c => c.key as string)
          setVisibleKeysState(new Set([...alwaysKeys, ...parsed]))
        }
      }
    } catch { /* ignore */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Persist + update state
  const setVisibleKeys = (keys: Set<string>) => {
    setVisibleKeysState(keys)
    try {
      // Save only optional keys (always-visible are implicit)
      const optional = [...keys].filter(k =>
        ALL_COLUMNS.find(c => c.key === k && !c.always)
      )
      localStorage.setItem(STORAGE_KEY, JSON.stringify(optional))
    } catch { /* ignore */ }
  }

  // Load fields and presets on mount
  useEffect(() => {
    getScreenerFields().then(d => {
      setFieldsByCategory(d.categories)
      const flat = Object.values(d.categories).flat()
      setAllFields(flat)
    }).catch(console.error)

    getScreenerPresets().then(d => {
      setPresets(d.presets)
    }).catch(console.error)
  }, [])

  // Filter operations
  const addFilter = () => {
    const firstField = allFields[0]?.key || 'pe_ratio'
    const firstType  = allFields[0]?.type || 'number'
    const firstOp    = firstType === 'boolean' ? 'eq' : 'gte'
    setFilters(f => [...f, { id: nextId++, field: firstField, operator: firstOp, value: '' }])
    setActivePreset(null)
  }

  const removeFilter = (id: number) => {
    setFilters(f => f.filter(r => r.id !== id))
    setActivePreset(null)
  }

  const updateFilter = (id: number, key: keyof FilterRow, val: string) => {
    setFilters(f => f.map(r => {
      if (r.id !== id) return r
      const updated = { ...r, [key]: val }
      // Auto-reset operator when field type changes
      if (key === 'field') {
        const meta = allFields.find(x => x.key === val)
        const ops  = OPERATORS[meta?.type || 'number']
        updated.operator = ops[0].value
        updated.value    = ''
      }
      return updated
    }))
    setActivePreset(null)
  }

  const applyPreset = (preset: ScreenerPreset) => {
    if (preset.premium && !isPro) {
      setShowUpgradeModal(true)
      return
    }
    const rows: FilterRow[] = preset.filters.map(f => ({
      id:       nextId++,
      field:    f.field,
      operator: f.operator,
      value:    String(f.value),
    }))
    setFilters(rows)
    setSortBy(preset.sort_by)
    setSortDir(preset.sort_dir as 'asc' | 'desc')
    setActivePreset(preset.id)
  }

  const clearAll = () => {
    setFilters([])
    setActivePreset(null)
    setResults([])
    setRan(false)
  }

  // Build API filters from current filter rows
  const buildApiFilters = useCallback((): ScreenerFilter[] =>
    filters
      .filter(f => f.value !== '')
      .map(f => {
        const meta = allFields.find(x => x.key === f.field)
        let value: string | number | boolean = f.value
        if (meta?.type === 'number') value = parseFloat(f.value)
        if (meta?.type === 'boolean') value = f.value === 'true'
        return { field: f.field, operator: f.operator, value }
      }),
  [filters, allFields])

  // Core fetch function — accepts explicit sort so state-update latency is bypassed
  const fetchResults = useCallback(async (
    p: number,
    by: string,
    dir: 'asc' | 'desc',
    apiFilters: ScreenerFilter[],
  ) => {
    setLoading(true)
    setRan(true)
    try {
      const res = await runScreener(apiFilters, { sort_by: by, sort_dir: dir, page: p, page_size: 50 })
      setResults(res.data)
      setTotal(res.total)
      setPage(res.page)
      setTotalPages(res.total_pages)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  // Run screen (button click)
  const runScreen = useCallback((p = 1) => {
    fetchResults(p, sortBy, sortDir, buildApiFilters())
  }, [fetchResults, sortBy, sortDir, buildApiFilters])

  // Sort header click — update state AND immediately re-fetch with new sort
  const handleSortAndRun = useCallback((col: ColDef) => {
    if (!col.sortKey) return
    const newBy  = col.sortKey
    const newDir: 'asc' | 'desc' =
      sortBy === col.sortKey ? (sortDir === 'asc' ? 'desc' : 'asc') : 'desc'
    setSortBy(newBy)
    setSortDir(newDir)
    fetchResults(1, newBy, newDir, buildApiFilters())
  }, [sortBy, sortDir, fetchResults, buildApiFilters])

  // Export current screen as CSV
  const handleExport = useCallback(async () => {
    setExporting(true)
    try {
      await exportScreener(buildApiFilters(), { sort_by: sortBy, sort_dir: sortDir })
    } catch (e) {
      console.error('Export failed', e)
    } finally {
      setExporting(false)
    }
  }, [buildApiFilters, sortBy, sortDir])

  // Resolve visible columns in order
  const visibleCols = ALL_COLUMNS.filter(c => c.always || visibleKeys.has(c.key as string))

  const SortIcon = ({ col }: { col: ColDef }) => {
    if (!col.sortKey || sortBy !== col.sortKey) return null
    return sortDir === 'asc'
      ? <ChevronUp className="w-3 h-3 inline ml-0.5" />
      : <ChevronDown className="w-3 h-3 inline ml-0.5" />
  }

  // Run NL screener
  const runNLScreen = async () => {
    if (!nlQuery.trim()) return
    setNlLoading(true)
    setNlError(null)
    setNlResult(null)
    try {
      const res = await nlScreener(nlQuery.trim())
      setNlResult(res)
      setResults(res.data)
      setTotal(res.total)
      setTotalPages(res.total_pages)
      setPage(1)
      setRan(true)
      // Populate the filter builder with the interpreted filters
      const rows: FilterRow[] = res.filters.map(f => ({
        id:       nextId++,
        field:    f.field,
        operator: f.operator,
        value:    String(f.value),
      }))
      setFilters(rows)
      setSortBy(res.sort_by)
      setSortDir(res.sort_dir as 'asc' | 'desc')
      setActivePreset(null)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (e as Error).message
        || 'Failed to run AI screen'
      setNlError(msg)
    } finally {
      setNlLoading(false)
    }
  }

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Stock Screener</h1>
        <span className="text-sm text-gray-500">ASX-listed stocks</span>
      </div>

      {/* AI Natural Language Search */}
      <div className="bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 rounded-2xl p-5 border border-white/10">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-semibold text-white">AI Screen</span>
          <span className="text-xs text-slate-400 ml-1">Powered by Claude</span>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={nlQuery}
            onChange={e => setNlQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && runNLScreen()}
            placeholder='e.g. "profitable miners with low debt and high franked dividends"'
            className="flex-1 bg-white/10 border border-white/20 text-white placeholder-slate-400
                       rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-400
                       focus:bg-white/15 transition-all"
          />
          <button
            onClick={runNLScreen}
            disabled={nlLoading || !nlQuery.trim()}
            className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500
                       disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm
                       font-semibold rounded-xl transition-colors shrink-0">
            {nlLoading
              ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              : <Search className="w-4 h-4" />}
            {nlLoading ? 'Thinking…' : 'Screen'}
          </button>
        </div>

        {nlError && (
          <p className="mt-2 text-sm text-red-400">{nlError}</p>
        )}

        {nlResult && !nlLoading && (
          <div className="mt-3 space-y-2">
            <p className="text-sm text-blue-300 leading-snug">
              <span className="font-semibold text-white">Interpreted as:</span> {nlResult.interpretation}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {nlResult.filters.map((f, i) => (
                <span key={i} className="text-xs bg-white/10 text-slate-300 border border-white/10
                                          px-2 py-0.5 rounded-full font-mono">
                  {f.field} {f.operator} {String(f.value)}
                </span>
              ))}
            </div>
            <p className="text-xs text-slate-500">{nlResult.total} stocks matched</p>
          </div>
        )}
      </div>

      {/* Quick Presets */}
      {presets.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-yellow-500" />
            <span className="text-sm font-semibold text-gray-700">Quick Screens</span>
            {!isPro && (
              <span className="ml-auto text-xs text-slate-400">
                <Lock className="w-3 h-3 inline mr-1" />Pro screens below
              </span>
            )}
          </div>
          {/* Free presets */}
          <div className="flex flex-wrap gap-2 mb-3">
            {presets.filter(p => !p.premium).map(p => (
              <button key={p.id} onClick={() => applyPreset(p)}
                className={cn(
                  'px-3 py-1.5 text-sm rounded-lg border font-medium transition-colors',
                  activePreset === p.id
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400 hover:text-blue-600'
                )}>
                {p.name}
              </button>
            ))}
          </div>
          {/* Premium presets */}
          <div className="border-t border-slate-100 pt-3">
            <div className="flex items-center gap-1.5 mb-2">
              <span className="text-xs font-semibold text-amber-600 uppercase tracking-wide">Pro Screens</span>
              {!isPro && <Lock className="w-3 h-3 text-amber-500" />}
            </div>
            <div className="flex flex-wrap gap-2">
              {presets.filter(p => p.premium).map(p => (
                <button key={p.id} onClick={() => applyPreset(p)}
                  title={p.description}
                  className={cn(
                    'px-3 py-1.5 text-sm rounded-lg border font-medium transition-colors flex items-center gap-1.5',
                    activePreset === p.id
                      ? 'bg-amber-500 text-white border-amber-500'
                      : isPro
                        ? 'bg-white text-gray-700 border-amber-200 hover:border-amber-400 hover:text-amber-700'
                        : 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100 cursor-pointer'
                  )}>
                  {!isPro && <Lock className="w-3 h-3 flex-shrink-0" />}
                  {p.name}
                  {!isPro && (
                    <span className="text-[10px] bg-amber-500 text-white rounded px-1 py-0.5 font-bold leading-none">PRO</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Upgrade modal */}
      {showUpgradeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 text-center">
            <div className="w-12 h-12 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Lock className="w-6 h-6 text-amber-600" />
            </div>
            <h2 className="text-lg font-bold text-slate-900 mb-2">Pro Screen</h2>
            <p className="text-sm text-slate-500 mb-5">
              This screen is available on the <span className="font-semibold text-amber-600">Pro plan</span> and above.
              Upgrade to unlock all 7 premium screens, NL Screener, CSV export, and more.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setShowUpgradeModal(false)}
                className="flex-1 px-4 py-2 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50">
                Maybe later
              </button>
              <Link href="/account" onClick={() => setShowUpgradeModal(false)}
                className="flex-1 px-4 py-2 text-sm bg-amber-500 hover:bg-amber-600 text-white rounded-lg font-semibold">
                Upgrade to Pro
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Filter builder */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-800 text-sm">Filters</h2>
          <div className="flex items-center gap-3">
            {filters.length > 0 && (
              <button onClick={clearAll}
                className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600">
                <X className="w-3.5 h-3.5" /> Clear
              </button>
            )}
            <button onClick={addFilter}
              className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 font-medium">
              <Plus className="w-4 h-4" /> Add Filter
            </button>
          </div>
        </div>

        {filters.length === 0 && (
          <p className="text-sm text-gray-400 py-2">
            No filters — click a Quick Screen above or &quot;Add Filter&quot; to start
          </p>
        )}

        {filters.map(f => {
          const meta = allFields.find(x => x.key === f.field)
          const ops  = OPERATORS[meta?.type || 'number'] || OPERATORS.number
          const isBool = meta?.type === 'boolean'
          const isText = meta?.type === 'text'

          return (
            <div key={f.id} className="flex items-center gap-2 flex-wrap">

              {/* Field selector — grouped by category */}
              <select value={f.field}
                onChange={e => updateFilter(f.id, 'field', e.target.value)}
                className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white
                           focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-[220px]">
                {Object.entries(fieldsByCategory).map(([cat, fields]) => (
                  <optgroup key={cat} label={cat}>
                    {fields.map(fi => (
                      <option key={fi.key} value={fi.key}>{fi.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>

              {/* Operator */}
              <select value={f.operator}
                onChange={e => updateFilter(f.id, 'operator', e.target.value)}
                className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white
                           focus:outline-none focus:ring-2 focus:ring-blue-500 w-16">
                {ops.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>

              {/* Value */}
              {isBool ? (
                <select value={f.value}
                  onChange={e => updateFilter(f.id, 'value', e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white
                             focus:outline-none focus:ring-2 focus:ring-blue-500">
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              ) : isText && f.field === 'sector' ? (
                <select value={f.value}
                  onChange={e => updateFilter(f.id, 'value', e.target.value)}
                  className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 bg-white
                             focus:outline-none focus:ring-2 focus:ring-blue-500">
                  <option value="">Select…</option>
                  {SECTORS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              ) : (
                <div className="flex items-center gap-1">
                  <input type={isText ? 'text' : 'number'}
                    value={f.value}
                    onChange={e => updateFilter(f.id, 'value', e.target.value)}
                    placeholder={meta?.unit ? `Value (${meta.unit})` : 'Value'}
                    className="text-sm border border-gray-300 rounded-lg px-2 py-1.5 w-28
                               focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {meta?.unit && (
                    <span className="text-xs text-gray-400">{meta.unit}</span>
                  )}
                </div>
              )}

              <button onClick={() => removeFilter(f.id)}
                className="text-gray-400 hover:text-red-500 p-1">
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
            {loading ? 'Running…' : 'Run Screen'}
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
          {/* Table header bar */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-200 bg-gray-50">
            <span className="text-sm font-semibold text-gray-700">
              {total.toLocaleString()} results
              {filters.length > 0 && (
                <span className="text-gray-400 font-normal"> · {filters.length} filter{filters.length > 1 ? 's' : ''}</span>
              )}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleExport}
                disabled={exporting}
                title="Download CSV (max 5,000 rows)"
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-gray-300
                           text-gray-600 hover:border-blue-400 hover:text-blue-600 disabled:opacity-50
                           transition-colors font-medium bg-white">
                <Download className="w-3.5 h-3.5" />
                {exporting ? 'Exporting…' : 'Export CSV'}
              </button>
              <ColumnPicker visibleKeys={visibleKeys} onChange={setVisibleKeys} />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {visibleCols.map(col => (
                    <th key={col.key as string}
                      onClick={() => { if (col.sortKey) handleSortAndRun(col) }}
                      className={cn(
                        'px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap',
                        col.align === 'right' ? 'text-right' : 'text-left',
                        col.sortKey && 'cursor-pointer hover:text-gray-800',
                        sortBy === col.sortKey && 'text-blue-600',
                      )}>
                      {col.label} <SortIcon col={col} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {results.map(r => (
                  <tr key={r.asx_code} className="hover:bg-blue-50 transition-colors">
                    {visibleCols.map(col => (
                      <td key={col.key as string}
                        className={cn('px-3 py-2.5',
                          col.align === 'right' ? 'text-right' : 'text-left')}>
                        {col.render(r)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
            <span className="text-sm text-gray-500">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button onClick={() => runScreen(page - 1)} disabled={page <= 1 || loading}
                className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-gray-300
                           disabled:opacity-40 hover:bg-white font-medium text-gray-600">
                <ChevronLeft className="w-4 h-4" /> Prev
              </button>
              <button onClick={() => runScreen(page + 1)} disabled={page >= totalPages || loading}
                className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-gray-300
                           disabled:opacity-40 hover:bg-white font-medium text-gray-600">
                Next <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {ran && !loading && results.length === 0 && (
        <div className="text-center py-12 bg-white border border-gray-200 rounded-xl">
          <p className="text-gray-500 font-medium">No stocks match your filters.</p>
          <p className="text-sm text-gray-400 mt-1">Try relaxing the criteria.</p>
        </div>
      )}
    </div>
  )
}
