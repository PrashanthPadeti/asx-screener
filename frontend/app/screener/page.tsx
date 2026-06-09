'use client'
import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  runScreener, getScreenerFields, getScreenerPresets, exportScreener,
  nlScreener, queryScreener, getQueryFields,
  type ScreenerFilter, type ScreenerRow, type ScreenerFieldMeta,
  type ScreenerPreset, type NLScreenerResponse, type QueryFieldRef,
} from '@/lib/api'
import {
  formatPrice, formatVolume, formatMarketCap,
  formatRatio, formatRatioChange, formatPctRaw, cn, SECTOR_COLORS, SECTORS,
} from '@/lib/utils'
import {
  Plus, Trash2, Play, ChevronUp, ChevronDown, RefreshCw,
  ChevronLeft, ChevronRight, SlidersHorizontal, Zap, X, Download,
  Sparkles, Search, Lock, Bookmark, Globe, Eye, EyeOff, Pencil,
  Code2, AlertCircle, FileText,
} from 'lucide-react'
import Link from 'next/link'
import WatchlistButton from '@/components/WatchlistButton'
import { HelpDrawer } from '@/components/HelpDrawer'
import { SCREENER_SECTIONS } from '@/lib/helpContent'
import { useAuth } from '@/lib/auth'
import {
  saveScreen, getMyScreens, updateScreen, deleteScreen,
  getCommunityScreens, incrementScreenUse,
  type SavedScreen,
} from '@/lib/api'
import BrowseSectors from '@/app/screener/components/BrowseSectors'

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

// ── Market Cap tier quick-filter ──────────────────────────────────────────────
// Values are in AUD millions (market_cap field has scale=1_000_000 in the backend)

type CapTierKey = 'all' | 'mega' | 'large' | 'mid' | 'small' | 'micro' | 'nano'

const CAP_TIER_LABELS: Record<CapTierKey, string> = {
  all:   'All',
  mega:  'Mega ≥$50B',
  large: 'Large $10B–$50B',
  mid:   'Mid $2B–$10B',
  small: 'Small $300M–$2B',
  micro: 'Micro $50M–$300M',
  nano:  'Nano <$50M',
}

// gte / lt values in AUD millions (backend multiplies by 1_000_000)
const CAP_TIER_RANGES: Record<CapTierKey, { gte?: number; lt?: number }> = {
  all:   {},
  mega:  { gte: 50_000 },
  large: { gte: 10_000, lt: 50_000 },
  mid:   { gte: 2_000,  lt: 10_000 },
  small: { gte: 300,    lt: 2_000 },
  micro: { gte: 50,     lt: 300 },
  nano:  { lt: 50 },
}

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

// ── Preset tier helper ────────────────────────────────────────────────────────
function presetTier(p: ScreenerPreset): 'free' | 'pro' | 'premium' {
  if (p.min_plan === 'premium') return 'premium'
  if (p.premium)                return 'pro'
  return 'free'
}

// ── Main page ─────────────────────────────────────────────────────────────────

const NL_EXAMPLES = [
  'Profitable miners under $1B market cap',
  'High dividend yield with franking credit',
  'REITs with low debt and positive earnings',
  'Momentum stocks near 52-week high',
  'Cheap banks with P/E under 12',
  'Small caps with strong revenue growth',
  'Energy stocks with low P/E and high yield',
  'Healthcare companies with no debt',
]

export default function ScreenerPage() {
  const { user } = useAuth()
  const userPlan  = user?.plan ?? 'free'
  const isFree    = !['pro', 'premium', 'enterprise_pro', 'enterprise_premium'].includes(userPlan)
  const isPro     = ['pro', 'premium', 'enterprise_pro', 'enterprise_premium'].includes(userPlan)
  const isPremium = ['premium', 'enterprise_premium'].includes(userPlan)
  const isAdmin   = user?.is_admin ?? false
  const searchParams = useSearchParams()

  // null = closed; 'pro' or 'premium' = show relevant upgrade modal
  const [upgradeForTier, setUpgradeForTier] = useState<'pro' | 'premium' | null>(null)

  // Filter state
  const [filters, setFilters] = useState<FilterRow[]>([])

  // API-loaded field metadata (for the filter builder dropdowns)
  const [fieldsByCategory, setFieldsByCategory] =
    useState<Record<string, ScreenerFieldMeta[]>>({})
  const [allFields, setAllFields] = useState<ScreenerFieldMeta[]>([])

  // Presets
  const [presets, setPresets] = useState<ScreenerPreset[]>([])
  const [activePreset, setActivePreset] = useState<string | null>(null)

  // Index auto-run support (?index=ASX200 from Indices page)
  const [pendingIndexParam, setPendingIndexParam] = useState<string | null>(null)

  // Results state
  const [results, setResults]       = useState<ScreenerRow[]>([])
  const [total, setTotal]           = useState(0)
  const [page, setPage]             = useState(1)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading]       = useState(false)
  const [ran, setRan]               = useState(false)
  const [resultsStale, setResultsStale] = useState(false)
  const [exporting, setExporting]       = useState(false)
  const [nlExporting, setNlExporting]   = useState(false)
  const [isCapped, setIsCapped]     = useState(false)
  const [totalRaw, setTotalRaw]     = useState(0)   // actual unfiltered count (for capped banner)
  const [sortBy, setSortBy]         = useState('market_cap')
  const [sortDir, setSortDir]       = useState<'asc' | 'desc'>('desc')

  // Screener mode
  const [screenerMode, setScreenerMode] = useState<'manual' | 'ai' | 'query'>('manual')

  // Browse Sectors
  const [selectedSector, setSelectedSector] = useState<string | undefined>(undefined)

  // Query Mode state
  const queryTextareaRef                              = useRef<HTMLTextAreaElement>(null)
  const [queryText, setQueryText]                     = useState('')
  const [queryLoading, setQueryLoading]               = useState(false)
  const [queryError, setQueryError]                   = useState<string | null>(null)
  const [queryFields, setQueryFields]                 = useState<QueryFieldRef[]>([])
  const [queryFieldSearch, setQueryFieldSearch]       = useState('')
  const [queryFieldsLoaded, setQueryFieldsLoaded]     = useState(false)

  // NL screener state
  const [nlQuery, setNlQuery]               = useState('')
  const [nlLoading, setNlLoading]           = useState(false)
  const [nlError, setNlError]               = useState<string | null>(null)
  const [nlResult, setNlResult]             = useState<NLScreenerResponse | null>(null)
  const [nlPage, setNlPage]                 = useState(1)
  const [nlTotalPages, setNlTotalPages]     = useState(0)
  const [nlTotal, setNlTotal]               = useState(0)
  const [nlRows, setNlRows]                 = useState<ScreenerRow[]>([])

  // Saved screens state
  const [myScreens, setMyScreens]           = useState<SavedScreen[]>([])
  const [showSaveModal, setShowSaveModal]   = useState(false)
  const [saveName, setSaveName]             = useState('')
  const [saveDesc, setSaveDesc]             = useState('')
  const [savePublic, setSavePublic]         = useState(false)
  const [saving, setSaving]                 = useState(false)
  const [showMyScreens, setShowMyScreens]   = useState(false)
  const [editingScreen, setEditingScreen]   = useState<SavedScreen | null>(null)

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
      // Auto-apply preset from URL ?preset=id
      const presetId = searchParams.get('preset')
      if (presetId) {
        const found = d.presets.find((p: ScreenerPreset) => p.id === presetId)
        if (found) applyPresetDirect(found)
      }
    }).catch(console.error)

    // Auto-apply sector filter (?sector=Energy)
    // ?autorun=true (added by Indices page links) immediately runs the screen.
    // Without autorun (e.g. Market heatmap links), filter is set but user clicks Run Screen.
    const sectorParam  = searchParams.get('sector')
    const autorunParam = searchParams.get('autorun') === 'true'
    if (sectorParam) {
      setFilters([{ id: nextId++, field: 'sector', operator: 'eq', value: sectorParam }])
      if (autorunParam) {
        // Call fetchResults directly to avoid stale-closure issues with buildApiFilters.
        // fetchResults has stable [] deps so it's safe to reference here.
        setTimeout(() => fetchResults(1, 'market_cap', 'desc', [
          { field: 'sector', operator: 'eq', value: sectorParam },
        ]), 50)
      }
    }

    // Auto-apply index membership filter + auto-run (?index=ASX200 from Indices page)
    const indexParam = searchParams.get('index')
    if (indexParam) {
      setPendingIndexParam(indexParam.toUpperCase())
    }

    // Auto-load community screen from URL ?screen=id
    const screenId = searchParams.get('screen')
    if (screenId) {
      getCommunityScreens().then(d => {
        const found = d.screens.find(s => s.id === screenId)
        if (found) {
          loadSavedScreen(found)
          incrementScreenUse(screenId)
        }
      }).catch(console.error)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Map ASX index codes to screener boolean field names.
  // AXJO (All Ordinaries, ~500 stocks) has no dedicated screener field — omitted intentionally.
  const INDEX_FIELD_MAP: Record<string, string> = {
    ASX20:  'is_asx20',
    ASX50:  'is_asx50',
    ASX100: 'is_asx100',
    ASX200: 'is_asx200',
    ASX300: 'is_asx300',
  }

  // When allFields loads and we have a pending index param, set the filter and auto-run.
  // Calls fetchResults directly (stable [] deps) to avoid stale-closure issues.
  useEffect(() => {
    if (!pendingIndexParam || allFields.length === 0) return
    const field = INDEX_FIELD_MAP[pendingIndexParam]
    if (!field) { setPendingIndexParam(null); return }
    const fieldMeta = allFields.find(f => f.key === field)
    if (!fieldMeta) { setPendingIndexParam(null); return }
    setFilters([{ id: nextId++, field, operator: 'eq', value: 'true' }])
    setTimeout(() => fetchResults(1, 'market_cap', 'desc', [
      { field, operator: 'eq', value: 'true' },
    ]), 50)
    setPendingIndexParam(null)
  }, [pendingIndexParam, allFields]) // eslint-disable-line react-hooks/exhaustive-deps

  // Filter operations
  const addFilter = () => {
    const firstField = allFields[0]?.key || 'pe_ratio'
    const firstType  = allFields[0]?.type || 'number'
    const firstOp    = firstType === 'boolean' ? 'eq' : 'gte'
    const firstValue = firstType === 'boolean' ? 'true' : ''
    setFilters(f => [...f, { id: nextId++, field: firstField, operator: firstOp, value: firstValue }])
    setActivePreset(null)
    if (ran) setResultsStale(true)
  }

  const removeFilter = (id: number) => {
    setFilters(f => f.filter(r => r.id !== id))
    setActivePreset(null)
    if (ran) setResultsStale(true)
  }

  const updateFilter = (id: number, key: keyof FilterRow, val: string) => {
    setFilters(f => f.map(r => {
      if (r.id !== id) return r
      const updated = { ...r, [key]: val }
      // Auto-reset operator + value when field type changes
      if (key === 'field') {
        const meta  = allFields.find(x => x.key === val)
        const ftype = meta?.type || 'text'   // default text → eq, not number → gte
        const ops   = OPERATORS[ftype] ?? OPERATORS.text
        updated.operator = ops[0].value
        // Boolean fields must default to 'true' so buildApiFilters doesn't skip them
        updated.value    = ftype === 'boolean' ? 'true' : ''
      }
      return updated
    }))
    setActivePreset(null)
    if (ran) setResultsStale(true)
  }

  const applyPresetDirect = (preset: ScreenerPreset) => {
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

  const applyPreset = (preset: ScreenerPreset) => {
    const tier = presetTier(preset)
    if (tier === 'premium' && !isPremium) { setUpgradeForTier('premium'); return }
    if (tier === 'pro'     && !isPro)     { setUpgradeForTier('pro');     return }
    applyPresetDirect(preset)
  }

  // Derive the active cap tier from the current market_cap filters (stays in sync automatically)
  const derivedCapTier = useMemo<CapTierKey>(() => {
    const mcap = filters.filter(f => f.field === 'market_cap')
    if (mcap.length === 0) return 'all'
    const gte = mcap.find(f => f.operator === 'gte')
    const lt  = mcap.find(f => f.operator === 'lt')
    const gteVal = gte ? Number(gte.value) : null
    const ltVal  = lt  ? Number(lt.value)  : null
    for (const [tier, range] of Object.entries(CAP_TIER_RANGES) as [CapTierKey, typeof CAP_TIER_RANGES[CapTierKey]][]) {
      if (tier === 'all') continue
      const matchGte = range.gte !== undefined ? gteVal === range.gte : gteVal == null
      const matchLt  = range.lt  !== undefined ? ltVal  === range.lt  : ltVal  == null
      if (matchGte && matchLt) return tier
    }
    return 'all' // custom range — no tier highlighted
  }, [filters])

  const applyCapTier = (tier: CapTierKey) => {
    setFilters(prev => {
      const withoutMcap = prev.filter(f => f.field !== 'market_cap')
      if (tier === 'all') return withoutMcap
      const range = CAP_TIER_RANGES[tier]
      const newRows: FilterRow[] = []
      if (range.gte !== undefined)
        newRows.push({ id: nextId++, field: 'market_cap', operator: 'gte', value: String(range.gte) })
      if (range.lt !== undefined)
        newRows.push({ id: nextId++, field: 'market_cap', operator: 'lt',  value: String(range.lt) })
      return [...withoutMcap, ...newRows]
    })
    setActivePreset(null)
  }

  const clearAll = () => {
    setFilters([])
    setActivePreset(null)
    setResults([])
    setRan(false)
  }

  // Handle sector selection from BrowseSectors component
  const handleSectorSelect = (sector: string) => {
    // Clear existing filters and set sector filter
    setFilters([{ id: nextId++, field: 'sector', operator: 'eq', value: sector }])
    setActivePreset(null)
    setSelectedSector(sector)
    // Immediately run the screener with the sector filter
    setTimeout(() => fetchResults(1, 'market_cap', 'desc', [
      { field: 'sector', operator: 'eq', value: sector },
    ]), 50)
  }

  // Load my screens when panel opens
  const loadMyScreens = async () => {
    if (!user) return
    try {
      const d = await getMyScreens()
      setMyScreens(d.screens)
    } catch { /* ignore */ }
  }

  const handleSaveScreen = async () => {
    if (!saveName.trim()) return
    setSaving(true)
    try {
      const screen = await saveScreen({
        name:      saveName.trim(),
        description: saveDesc.trim() || undefined,
        filters:   buildApiFilters(),
        sort_by:   sortBy,
        sort_dir:  sortDir,
        is_public: savePublic,
      })
      setMyScreens(s => [screen, ...s])
      setShowSaveModal(false)
      setSaveName('')
      setSaveDesc('')
      setSavePublic(false)
    } catch { /* ignore */ } finally {
      setSaving(false)
    }
  }

  const handleUpdateScreen = async (id: string, patch: { is_public?: boolean; name?: string; description?: string }) => {
    try {
      const updated = await updateScreen(id, patch)
      setMyScreens(s => s.map(x => x.id === id ? updated : x))
    } catch { /* ignore */ }
  }

  const handleDeleteScreen = async (id: string) => {
    try {
      await deleteScreen(id)
      setMyScreens(s => s.filter(x => x.id !== id))
    } catch { /* ignore */ }
  }

  const loadSavedScreen = (screen: SavedScreen) => {
    const rows: FilterRow[] = screen.filters.map(f => ({
      id:       nextId++,
      field:    f.field,
      operator: f.operator,
      value:    String(f.value),
    }))
    setFilters(rows)
    setSortBy(screen.sort_by)
    setSortDir(screen.sort_dir as 'asc' | 'desc')
    setActivePreset(null)
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
    setResultsStale(false)
    try {
      const res = await runScreener(apiFilters, { sort_by: by, sort_dir: dir, page: p, page_size: 50 })
      setResults(res.data)
      setTotal(res.total)
      setPage(res.page)
      setTotalPages(res.total_pages)
      setIsCapped(res.is_capped ?? false)
      if (res.is_capped) setTotalRaw(res.free_limit ?? 500)
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

  // Export AI query results as CSV — reuses the same filters Claude generated
  const handleNlExport = useCallback(async () => {
    if (!nlResult) return
    setNlExporting(true)
    try {
      await exportScreener(nlResult.filters, { sort_by: nlResult.sort_by })
    } catch (e) {
      console.error('NL export failed', e)
    } finally {
      setNlExporting(false)
    }
  }, [nlResult])

  // Resolve visible columns in order
  const visibleCols = ALL_COLUMNS.filter(c => c.always || visibleKeys.has(c.key as string))

  const SortIcon = ({ col }: { col: ColDef }) => {
    if (!col.sortKey || sortBy !== col.sortKey) return null
    return sortDir === 'asc'
      ? <ChevronUp className="w-3 h-3 inline ml-0.5" />
      : <ChevronDown className="w-3 h-3 inline ml-0.5" />
  }

  // Run NL screener — page=1 re-invokes Claude; page>1 re-uses the same query
  const runNLScreen = async (page = 1) => {
    if (!nlQuery.trim()) return
    setNlLoading(true)
    setNlError(null)
    try {
      const res = await nlScreener(nlQuery.trim(), page)
      setNlResult(res)
      setNlRows(res.data)
      setNlTotal(res.total)
      setNlTotalPages(res.total_pages)
      setNlPage(page)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (e as Error).message
        || 'Failed to run AI screen'
      setNlError(msg)
    } finally {
      setNlLoading(false)
    }
  }

  // ── Query Mode — run SQL-like query ───────────────────────────────────────
  const runQueryScreen = async (page = 1) => {
    if (!queryText.trim()) return
    setQueryLoading(true)
    setQueryError(null)
    setRan(true)
    try {
      const res = await queryScreener({
        query:     queryText.trim(),
        sort_by:   sortBy,
        sort_dir:  sortDir,
        page,
        page_size: 50,
      })
      setResults(res.data)
      setTotal(res.total)
      setPage(res.page)
      setTotalPages(res.total_pages)
      setIsCapped(res.is_capped ?? false)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (e as Error).message
        || 'Query failed'
      setQueryError(msg)
    } finally {
      setQueryLoading(false)
    }
  }

  // Load field reference when Query Mode is first entered
  const loadQueryFields = async () => {
    if (queryFieldsLoaded) return
    try {
      const fields = await getQueryFields()
      setQueryFields(fields)
      setQueryFieldsLoaded(true)
    } catch {
      // Silently fail — field reference is optional UI enhancement
    }
  }

  // Insert field key at current cursor position in the query textarea
  const insertFieldAtCursor = (fieldKey: string) => {
    const ta = queryTextareaRef.current
    if (!ta) {
      setQueryText(prev => prev + (prev ? ' ' : '') + fieldKey)
      return
    }
    const start = ta.selectionStart
    const end   = ta.selectionEnd
    const before = queryText.slice(0, start)
    const after  = queryText.slice(end)
    const sep    = before && !before.endsWith(' ') && !before.endsWith('\n') ? ' ' : ''
    const newText = before + sep + fieldKey + after
    setQueryText(newText)
    // Restore cursor after the inserted text
    setTimeout(() => {
      ta.focus()
      const newPos = start + sep.length + fieldKey.length
      ta.setSelectionRange(newPos, newPos)
    }, 0)
  }

  // Smart textarea: auto-insert newline after AND/OR keywords for readability
  const handleQueryKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      runQueryScreen(1)
      return
    }
  }

  const handleQueryChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    setQueryText(val)
    setQueryError(null)

    // Auto-newline: if user just typed " AND " or " OR ", replace the trailing
    // space with a newline so each condition goes on its own line.
    const upper = val.toUpperCase()
    if (upper.endsWith(' AND ') || upper.endsWith(' OR ')) {
      const keyword = upper.endsWith(' AND ') ? ' AND ' : ' OR '
      const base    = val.slice(0, val.length - keyword.length)
      const kw      = val.slice(val.length - keyword.length).trimEnd()
      setQueryText(base + kw + '\n')
    }
  }

  // CSV download for field reference
  const downloadFieldRefCSV = () => {
    if (!queryFields.length) return
    const header = 'Field Key,Label,Unit,Category,Type,Aliases'
    const rows   = queryFields.map(f =>
      [f.key, f.label, f.unit, f.category, f.type, f.aliases.join(' | ')]
        .map(v => `"${String(v).replace(/"/g, '""')}"`)
        .join(',')
    )
    const csv  = [header, ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = 'asx_screener_query_fields.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      {/* Header + Mode Tabs — always full width */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-gray-900">Stock Screener</h1>
        <div className="flex items-center gap-2">
          <HelpDrawer sections={SCREENER_SECTIONS} title="Screener Guide" subtitle="Filters, AI query, presets, and columns explained" />
          <div className="flex items-center gap-1 bg-gray-100 rounded-xl p-1">
          <button
            onClick={() => setScreenerMode('manual')}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition-colors',
              screenerMode === 'manual'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            )}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            Filter Screen
          </button>
          <button
            onClick={() => setScreenerMode('ai')}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition-colors',
              screenerMode === 'ai'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            )}
          >
            <Sparkles className="w-3.5 h-3.5 text-blue-500" />
            AI Query
            {isPremium
              ? <span className="text-[10px] bg-purple-600 text-white rounded px-1.5 py-0.5 font-bold">PREMIUM</span>
              : <span className="text-[10px] bg-amber-500 text-white rounded px-1.5 py-0.5 font-bold">UPGRADE</span>
            }
          </button>
          {isAdmin && (
            <button
              onClick={() => { setScreenerMode('query'); loadQueryFields() }}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold transition-colors',
                screenerMode === 'query'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              )}
            >
              <Code2 className="w-3.5 h-3.5 text-orange-500" />
              Query Mode
              <span className="text-[10px] bg-orange-100 text-orange-700 rounded px-1.5 py-0.5 font-bold">ADMIN</span>
            </button>
          )}
        </div>
        </div>
      </div>

      {/* Main content area — flex layout with sidebar */}
      <div className="flex flex-col lg:flex-row gap-4">

      {/* ── AI Query Mode ────────────────────────────────────────── */}
      {screenerMode === 'ai' && (
        <div className="w-full space-y-4">
          {isPremium ? (
            <div className="bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 rounded-2xl border border-white/10 overflow-hidden">
              {/* Search area */}
              <div className="p-6">
                <div className="flex items-center gap-2 mb-4">
                  <Sparkles className="w-5 h-5 text-blue-400" />
                  <span className="text-base font-bold text-white">AI Natural Language Query</span>
                  <span className="text-xs text-slate-400">Powered by Claude</span>
                </div>

                <div className="flex gap-3">
                  <input
                    type="text"
                    value={nlQuery}
                    onChange={e => setNlQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && runNLScreen(1)}
                    placeholder='e.g. "show me profitable miners under $1B"'
                    className="flex-1 bg-white/10 border border-white/20 text-white placeholder-slate-400
                               rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-400
                               focus:bg-white/15 transition-all"
                    autoFocus
                  />
                  <button
                    onClick={() => runNLScreen(1)}
                    disabled={nlLoading || !nlQuery.trim()}
                    className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-500
                               disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm
                               font-semibold rounded-xl transition-colors shrink-0">
                    {nlLoading
                      ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      : <Search className="w-4 h-4" />}
                    {nlLoading ? 'Thinking…' : 'Search'}
                  </button>
                </div>

                {/* Example chips */}
                <div className="mt-3">
                  <p className="text-xs text-slate-500 mb-2">Try an example:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {NL_EXAMPLES.map(q => (
                      <button
                        key={q}
                        onClick={() => { setNlQuery(q); setTimeout(() => runNLScreen(1), 50) }}
                        className="text-xs px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20
                                   text-slate-300 hover:text-white border border-white/10
                                   hover:border-white/20 transition-colors"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>

                {nlError && (
                  <div className="mt-3 flex items-start gap-2 px-4 py-3 bg-red-900/30 border border-red-500/30 rounded-xl">
                    <span className="text-sm text-red-400">{nlError}</span>
                  </div>
                )}

                {nlResult && !nlLoading && (
                  <div className="mt-4 px-4 py-3 bg-white/5 rounded-xl border border-white/10 space-y-2">
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
                    <p className="text-xs text-slate-500">{nlTotal.toLocaleString()} stocks matched</p>
                    <p className="text-xs text-amber-400/80 border-t border-white/10 pt-2 mt-1">
                      Results are filtered data only — not investment advice. Always verify independently before acting.
                    </p>
                  </div>
                )}
              </div>

              {/* AI Results table */}
              {nlRows.length > 0 && (
                <div className="border-t border-white/10">
                  {/* Table header */}
                  <div className="flex items-center justify-between px-6 py-3 bg-white/5">
                    <span className="text-sm font-semibold text-white">
                      {nlTotal.toLocaleString()} results
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleNlExport}
                        disabled={nlExporting}
                        title="Download AI query results as CSV"
                        className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border
                                   border-white/20 text-slate-300 hover:bg-white/10 hover:text-white
                                   disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium">
                        <Download className="w-3.5 h-3.5" />
                        {nlExporting ? 'Exporting…' : 'Export CSV'}
                      </button>
                      <ColumnPicker visibleKeys={visibleKeys} onChange={setVisibleKeys} />
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-white/5 border-b border-white/10">
                        <tr>
                          {visibleCols.map(col => (
                            <th key={col.key as string}
                              className={cn(
                                'px-3 py-2.5 text-xs font-semibold text-slate-400 uppercase tracking-wide whitespace-nowrap',
                                col.align === 'right' ? 'text-right' : 'text-left',
                              )}>
                              {col.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {nlRows.map(r => (
                          <tr key={r.asx_code} className="hover:bg-white/5 transition-colors">
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
                  {nlTotalPages > 1 && (
                    <div className="flex items-center justify-between px-6 py-3 border-t border-white/10">
                      <span className="text-sm text-slate-400">
                        Page {nlPage} of {nlTotalPages}
                      </span>
                      <div className="flex gap-2">
                        <button onClick={() => runNLScreen(nlPage - 1)} disabled={nlPage <= 1 || nlLoading}
                          className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-white/20
                                     disabled:opacity-40 hover:bg-white/10 font-medium text-slate-300">
                          <ChevronLeft className="w-4 h-4" /> Prev
                        </button>
                        <button onClick={() => runNLScreen(nlPage + 1)} disabled={nlPage >= nlTotalPages || nlLoading}
                          className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-white/20
                                     disabled:opacity-40 hover:bg-white/10 font-medium text-slate-300">
                          Next <ChevronRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {nlResult && !nlLoading && nlRows.length === 0 && (
                <div className="border-t border-white/10 px-6 py-10 text-center">
                  <p className="text-slate-400">No stocks matched your query.</p>
                  <p className="text-sm text-slate-500 mt-1">Try relaxing the criteria or rephrasing.</p>
                </div>
              )}
            </div>
          ) : (
            /* Upgrade CTA for non-premium users */
            <div className="bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 rounded-2xl p-8 border border-white/10 text-center">
              <Sparkles className="w-10 h-10 text-purple-400 mx-auto mb-3" />
              <h2 className="text-lg font-bold text-white mb-2">AI Natural Language Query</h2>
              <p className="text-slate-400 text-sm max-w-md mx-auto mb-4">
                Ask questions in plain English — <span className="text-white">&quot;show me profitable miners under $1B&quot;</span> — and AI instantly queries the ASX database for you.
              </p>
              <div className="flex flex-wrap justify-center gap-1.5 mb-6">
                {['Profitable miners under $1B', 'High franked dividends', 'REITs with low debt', 'Momentum near 52W high'].map(q => (
                  <span key={q} className="text-xs px-3 py-1.5 rounded-full bg-white/10 text-slate-400 border border-white/10">{q}</span>
                ))}
              </div>
              <span className="inline-block mb-3 text-xs font-semibold px-3 py-1 rounded-full bg-purple-700/40 text-purple-300 border border-purple-500/30">
                Premium Plan Feature
              </span>
              <br />
              <Link
                href="/pricing"
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-purple-600 hover:bg-purple-500
                           text-white text-sm font-semibold rounded-xl transition-colors mt-2"
              >
                <Zap className="w-4 h-4" /> Upgrade to Premium
              </Link>
            </div>
          )}
        </div>
      )}

      {/* ── Query Mode ───────────────────────────────────────────── */}
      {screenerMode === 'query' && isAdmin && (
        <div className="w-full space-y-4">

          {/* Query input card */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-orange-50 border-b border-orange-100">
              <div className="flex items-center gap-2">
                <Code2 className="w-4 h-4 text-orange-600" />
                <span className="font-semibold text-gray-800 text-sm">Query Mode</span>
                <span className="text-[10px] bg-orange-100 text-orange-700 border border-orange-200 rounded px-1.5 py-0.5 font-bold">ADMIN</span>
              </div>
              <span className="text-xs text-gray-500">
                Use field names + operators · AND / OR · ( ) grouping · Ctrl+Enter to run
              </span>
            </div>

            {/* Textarea */}
            <div className="p-4">
              <textarea
                ref={queryTextareaRef}
                value={queryText}
                onChange={handleQueryChange}
                onKeyDown={handleQueryKeyDown}
                placeholder={`roe > 10 AND\n(roce > 10 OR\n  roic > 10)`}
                rows={6}
                className="w-full font-mono text-sm bg-gray-50 border border-gray-200 rounded-lg p-3
                           text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2
                           focus:ring-orange-300 focus:border-orange-400 resize-y leading-relaxed"
                spellCheck={false}
                autoCapitalize="off"
                autoCorrect="off"
              />

              {/* Actions row */}
              <div className="flex items-center gap-3 mt-3">
                <button
                  onClick={() => runQueryScreen(1)}
                  disabled={queryLoading || !queryText.trim()}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600
                             disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm
                             font-semibold rounded-lg transition-colors"
                >
                  {queryLoading
                    ? <RefreshCw className="w-4 h-4 animate-spin" />
                    : <Play className="w-4 h-4" />
                  }
                  {queryLoading ? 'Running…' : 'Run Query'}
                </button>
                <button
                  onClick={() => { setQueryText(''); setQueryError(null); setResults([]); setTotal(0); setRan(false) }}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-500 hover:text-gray-700
                             border border-gray-200 rounded-lg transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                  Clear
                </button>
                {ran && !queryLoading && total > 0 && (
                  <span className="ml-auto text-xs text-gray-500">
                    {total.toLocaleString()} result{total !== 1 ? 's' : ''}
                  </span>
                )}
              </div>

              {/* Error banner */}
              {queryError && (
                <div className="flex items-start gap-2 mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-red-700">Parse Error</p>
                    <p className="text-sm text-red-600 mt-0.5">{queryError}</p>
                    <p className="text-xs text-red-400 mt-1">
                      Check the Field Reference below for valid field names.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Field Reference panel */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-gray-500" />
                <span className="font-semibold text-gray-700 text-sm">Field Reference</span>
                {queryFields.length > 0 && (
                  <span className="text-xs text-gray-400">{queryFields.length} fields</span>
                )}
              </div>
              <button
                onClick={downloadFieldRefCSV}
                disabled={queryFields.length === 0}
                className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700
                           disabled:opacity-40 border border-gray-200 rounded px-2 py-1 transition-colors"
              >
                <Download className="w-3 h-3" />
                CSV
              </button>
            </div>

            {/* Search */}
            <div className="px-4 py-2 border-b border-gray-100">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                <input
                  type="text"
                  value={queryFieldSearch}
                  onChange={e => setQueryFieldSearch(e.target.value)}
                  placeholder="Search fields by name or alias…"
                  className="w-full pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg
                             focus:outline-none focus:ring-2 focus:ring-orange-200"
                />
              </div>
            </div>

            {/* Fields list */}
            <div className="max-h-64 overflow-y-auto">
              {queryFields.length === 0 ? (
                <div className="px-4 py-6 text-center text-sm text-gray-400">
                  Loading field reference…
                </div>
              ) : (() => {
                const search = queryFieldSearch.toLowerCase()
                const filtered = queryFields.filter(f =>
                  !search ||
                  f.key.includes(search) ||
                  f.label.toLowerCase().includes(search) ||
                  f.category.toLowerCase().includes(search) ||
                  f.aliases.some(a => a.includes(search))
                )
                // Group by category
                const byCategory: Record<string, QueryFieldRef[]> = {}
                filtered.forEach(f => {
                  ;(byCategory[f.category] = byCategory[f.category] || []).push(f)
                })

                return Object.entries(byCategory).map(([cat, fields]) => (
                  <div key={cat}>
                    <div className="px-4 py-1.5 text-[10px] font-bold text-gray-400 uppercase tracking-wider
                                    bg-gray-50 border-b border-gray-100 sticky top-0">
                      {cat}
                    </div>
                    {fields.map(f => (
                      <div
                        key={f.key}
                        className="flex items-start justify-between px-4 py-2 hover:bg-orange-50
                                   border-b border-gray-50 group"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <code className="text-xs font-mono font-semibold text-orange-700 bg-orange-50
                                             px-1.5 py-0.5 rounded border border-orange-100">{f.key}</code>
                            {f.unit && (
                              <span className="text-[10px] text-gray-400">{f.unit}</span>
                            )}
                          </div>
                          <p className="text-xs text-gray-600 mt-0.5 truncate">{f.label}</p>
                          {f.aliases.length > 0 && (
                            <p className="text-[10px] text-gray-400 mt-0.5 truncate">
                              aliases: {f.aliases.slice(0, 3).join(', ')}{f.aliases.length > 3 ? '…' : ''}
                            </p>
                          )}
                        </div>
                        <button
                          onClick={() => insertFieldAtCursor(f.key)}
                          className="ml-3 flex-shrink-0 opacity-0 group-hover:opacity-100 text-[10px]
                                     text-orange-600 hover:text-orange-700 border border-orange-200
                                     hover:border-orange-400 rounded px-1.5 py-0.5 transition-all font-medium"
                        >
                          + Insert
                        </button>
                      </div>
                    ))}
                  </div>
                ))
              })()}
            </div>
          </div>
        </div>
      )}

      {/* ── Manual Filter Mode (Left Column) ────────────────────── */}
      <div className={screenerMode === 'manual' ? 'space-y-4 flex-1' : 'hidden'}>

      {/* Filter builder — manual mode only [MOVED TO TOP] */}
      {screenerMode === 'manual' && <div className="bg-white border-2 border-blue-200 rounded-xl p-4 space-y-3 shadow-sm hover:shadow-md transition-shadow">
        <div className="flex items-center justify-between px-3 py-2 -mx-4 -mt-4 mb-2 bg-blue-50 border-l-4 border-blue-500 rounded-t-lg">
          <h2 className="font-semibold text-gray-800 text-sm flex items-center gap-2">
            <SlidersHorizontal className="w-4 h-4 text-blue-600" />
            Filters
          </h2>
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

        {/* Market Cap Tier quick filter */}
        <div className="flex items-center gap-2 flex-wrap pb-2 border-b border-gray-100">
          <span className="text-xs font-medium text-gray-500 whitespace-nowrap">Market Cap</span>
          <div className="flex gap-1 flex-wrap">
            {(Object.keys(CAP_TIER_LABELS) as CapTierKey[]).map(t => (
              <button key={t} onClick={() => applyCapTier(t)}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md border transition-colors ${
                  derivedCapTier === t
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-blue-400 hover:text-blue-600'
                }`}>
                {CAP_TIER_LABELS[t]}
              </button>
            ))}
          </div>
        </div>

        {filters.length === 0 && (
          <p className="text-sm text-gray-400 py-2">
            No filters — click "Add Filter" to start or select a Quick Screen below
          </p>
        )}

        {filters.map(f => {
          const meta   = allFields.find(x => x.key === f.field)
          const ftype  = meta?.type || 'text'
          const ops    = OPERATORS[ftype] ?? OPERATORS.text
          // If the stored operator isn't valid for this field type, auto-correct to first valid op
          const validOp = ops.find(o => o.value === f.operator) ? f.operator : ops[0].value
          if (validOp !== f.operator) updateFilter(f.id, 'operator', validOp)
          const isBool = ftype === 'boolean'
          const isText = ftype === 'text'

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
              <select value={validOp}
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

        <div className="pt-2 flex items-center gap-3 flex-wrap">
          <button onClick={() => runScreen(1)} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-semibold
                       rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-60">
            <Play className="w-4 h-4" />
            {loading ? 'Running…' : 'Run Screen'}
          </button>
          {user && filters.length > 0 && (
            <button
              onClick={() => setShowSaveModal(true)}
              className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-300 rounded-lg
                         bg-white hover:bg-gray-50 text-gray-700 font-medium">
              <Bookmark className="w-4 h-4" /> Save Screen
            </button>
          )}
          {user && (
            <button
              onClick={() => { setShowMyScreens(v => !v); if (!showMyScreens) loadMyScreens() }}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg font-medium transition-colors',
                showMyScreens
                  ? 'bg-blue-50 border-blue-300 text-blue-700'
                  : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
              )}>
              <Eye className="w-4 h-4" /> My Screens
            </button>
          )}
          {ran && !loading && (
            <span className="text-sm text-gray-500">
              {total.toLocaleString()} stocks matched
            </span>
          )}
        </div>

        {/* My Screens panel */}
        {showMyScreens && user && (
          <div className="border-t border-gray-100 pt-3 mt-1">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">My Saved Screens</p>
            {myScreens.length === 0 ? (
              <p className="text-sm text-gray-400">No saved screens yet. Run a screen and click &quot;Save Screen&quot;.</p>
            ) : (
              <div className="space-y-2">
                {myScreens.map(s => (
                  <div key={s.id} className="flex items-center gap-2 group">
                    <button
                      onClick={() => loadSavedScreen(s)}
                      className="flex-1 text-left px-3 py-2 rounded-lg border border-gray-200
                                 hover:border-blue-300 hover:bg-blue-50 transition-colors">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-800">{s.name}</span>
                        {s.is_public
                          ? <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700 font-semibold">Public</span>
                          : <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 font-semibold">Private</span>
                        }
                      </div>
                      {s.description && <p className="text-xs text-gray-400 mt-0.5">{s.description}</p>}
                    </button>
                    <button
                      onClick={() => handleUpdateScreen(s.id, { is_public: !s.is_public })}
                      title={s.is_public ? 'Make private' : 'Make public'}
                      className="p-1.5 text-gray-400 hover:text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity">
                      {s.is_public ? <EyeOff className="w-4 h-4" /> : <Globe className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => handleDeleteScreen(s.id)}
                      title="Delete"
                      className="p-1.5 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>}


      {/* Upgrade modal — Pro */}
      {upgradeForTier === 'pro' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 text-center">
            <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Lock className="w-6 h-6 text-blue-600" />
            </div>
            <h2 className="text-lg font-bold text-slate-900 mb-2">Pro Screen</h2>
            <p className="text-sm text-slate-500 mb-5">
              This is a <span className="font-semibold text-blue-600">Pro screen</span>.
              Upgrade to Pro or Premium to unlock it, plus CSV export and more advanced screens.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setUpgradeForTier(null)}
                className="flex-1 px-4 py-2 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50">
                Maybe later
              </button>
              <Link href="/pricing" onClick={() => setUpgradeForTier(null)}
                className="flex-1 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold">
                Upgrade to Pro
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Upgrade modal — Premium */}
      {upgradeForTier === 'premium' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6 text-center">
            <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Lock className="w-6 h-6 text-purple-600" />
            </div>
            <h2 className="text-lg font-bold text-slate-900 mb-2">Premium Screen</h2>
            <p className="text-sm text-slate-500 mb-5">
              This is a <span className="font-semibold text-purple-600">Premium screen</span>.
              Upgrade to Premium to unlock advanced ASX insights — AI Ranked screens, Mining Value, A-REIT Income, Franking Optimiser and more.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setUpgradeForTier(null)}
                className="flex-1 px-4 py-2 text-sm border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50">
                Maybe later
              </button>
              <Link href="/pricing" onClick={() => setUpgradeForTier(null)}
                className="flex-1 px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold">
                Upgrade to Premium
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Save Screen modal */}
      {showSaveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-900">Save Screen</h2>
              <button onClick={() => setShowSaveModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Name *</label>
                <input
                  value={saveName}
                  onChange={e => setSaveName(e.target.value)}
                  placeholder="e.g. High Yield Franked Miners"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                             focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Description (optional)</label>
                <textarea
                  value={saveDesc}
                  onChange={e => setSaveDesc(e.target.value)}
                  placeholder="What does this screen look for?"
                  rows={2}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                             focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSavePublic(v => !v)}
                  className={cn(
                    'flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-colors',
                    savePublic
                      ? 'bg-green-50 border-green-300 text-green-700'
                      : 'bg-gray-50 border-gray-300 text-gray-600'
                  )}>
                  {savePublic ? <Globe className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                  {savePublic ? 'Public — visible to all' : 'Private — only you'}
                </button>
              </div>
              <p className="text-xs text-gray-400">
                {filters.filter(f => f.value !== '').length} filter{filters.filter(f => f.value !== '').length !== 1 ? 's' : ''} will be saved
              </p>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setShowSaveModal(false)}
                className="flex-1 px-4 py-2 text-sm border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={handleSaveScreen}
                disabled={saving || !saveName.trim()}
                className="flex-1 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white
                           rounded-lg font-semibold disabled:opacity-60">
                {saving ? 'Saving…' : 'Save Screen'}
              </button>
            </div>
          </div>
        </div>
      )}

      </div>

      {/* Browse Sectors Sidebar — Manual Mode Only */}
      {screenerMode === 'manual' && (
        <div className="hidden lg:block lg:w-64 flex-shrink-0">
          <BrowseSectors onSectorSelect={handleSectorSelect} selectedSector={selectedSector} />
        </div>
      )}
      </div>

      {/* ── Results table — shown for BOTH manual and query modes ─────────── */}
      {(screenerMode === 'manual' || screenerMode === 'query') && results.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">

          {/* Free-tier cap banner */}
          {isCapped && (
            <div className="flex items-center justify-between px-4 py-2.5 bg-amber-50 border-b border-amber-200">
              <span className="text-sm text-amber-800">
                <span className="font-semibold">Free plan:</span> showing first 500 stocks.
                Upgrade to <span className="font-semibold">Pro or Premium</span> to see all results and export to CSV.
              </span>
              <Link href="/pricing"
                className="flex-shrink-0 ml-4 px-3 py-1 text-xs font-semibold rounded-lg
                           bg-amber-500 text-white hover:bg-amber-600 transition-colors">
                Upgrade →
              </Link>
            </div>
          )}

          {resultsStale && screenerMode === 'manual' && (
            <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-700 font-medium">
              <RefreshCw className="w-3.5 h-3.5 shrink-0" />
              Filters changed — click <button onClick={() => runScreen(1)} className="underline font-semibold hover:text-amber-900">Run Screen</button> to apply them.
            </div>
          )}

          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-200 bg-gray-50">
            <span className="text-sm font-semibold text-gray-700">
              {total.toLocaleString()} results
              {screenerMode === 'manual' && filters.length > 0 && (
                <span className="text-gray-400 font-normal"> · {filters.length} filter{filters.length > 1 ? 's' : ''}</span>
              )}
            </span>
            <div className="flex items-center gap-2">
              {isPro ? (
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
              ) : (
                <button
                  disabled
                  title="Export CSV — Pro or Premium plan required"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-gray-200
                             text-gray-400 cursor-not-allowed opacity-60 font-medium bg-gray-50">
                  <Download className="w-3.5 h-3.5" />
                  Export CSV
                  <Lock className="w-3 h-3" />
                </button>
              )}
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
              <button
                onClick={() => screenerMode === 'query' ? runQueryScreen(page - 1) : runScreen(page - 1)}
                disabled={page <= 1 || loading || queryLoading}
                className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-gray-300
                           disabled:opacity-40 hover:bg-white font-medium text-gray-600">
                <ChevronLeft className="w-4 h-4" /> Prev
              </button>
              <button
                onClick={() => screenerMode === 'query' ? runQueryScreen(page + 1) : runScreen(page + 1)}
                disabled={page >= totalPages || loading || queryLoading}
                className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-gray-300
                           disabled:opacity-40 hover:bg-white font-medium text-gray-600">
                Next <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {(screenerMode === 'manual' || screenerMode === 'query') && ran && !loading && !queryLoading && results.length === 0 && !queryError && (
        <div className="text-center py-12 bg-white border border-gray-200 rounded-xl">
          <p className="text-gray-500 font-medium">No stocks match your {screenerMode === 'query' ? 'query' : 'filters'}.</p>
          <p className="text-sm text-gray-400 mt-1">Try relaxing the criteria.</p>
        </div>
      )}
    </>
  )
}
