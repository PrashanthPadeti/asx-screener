'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  Star, Trash2, ArrowUpRight, RefreshCw, Plus, Pencil,
  Check, X, LogIn, FolderOpen, Search, Bell, Lock,
  TrendingUp, TrendingDown, BarChart3, DollarSign,
  AlertTriangle, ChevronRight, Crown,
} from 'lucide-react'
import { HelpDrawer } from '@/components/HelpDrawer'
import { WATCHLIST_SECTIONS } from '@/lib/helpContent'
import {
  getScreenerBatch, type ScreenerRow,
  getWatchlists, createWatchlist, getWatchlist, updateWatchlist,
  deleteWatchlist, addToWatchlist, removeFromWatchlist,
  type WatchlistSummary, type WatchlistDetail,
  searchCompanies, type SearchResult,
} from '@/lib/api'
import { useWatchlist } from '@/lib/watchlist'
import WatchlistButton from '@/components/WatchlistButton'
import { useAuth } from '@/lib/auth'
import {
  formatPrice, formatMarketCap,
  formatRatio, formatRatioChange, formatPctRaw, cn, SECTOR_COLORS,
} from '@/lib/utils'

// ── Plan limits ───────────────────────────────────────────────────────────────

const PLAN_LIMITS = {
  free:               { watchlists: 1,  stocks: 50  },
  pro:                { watchlists: 20, stocks: 500 },
  premium:            { watchlists: 50, stocks: 500 },
  enterprise_pro:     { watchlists: 20, stocks: 500 },
  enterprise_premium: { watchlists: 50, stocks: 500 },
} as const

type Plan = keyof typeof PLAN_LIMITS

function getLimits(plan: string) {
  return PLAN_LIMITS[plan as Plan] ?? PLAN_LIMITS.free
}

const PLAN_LABELS: Record<string, string> = {
  free:               'Free',
  pro:                'Pro',
  premium:            'Premium',
  enterprise_pro:     'Enterprise Pro',
  enterprise_premium: 'Enterprise Premium',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtX(v: number | null | undefined) {
  if (v == null || v === 0) return '—'
  return `${v.toFixed(1)}x`
}

function fmtVolume(v: number | null) {
  if (v == null) return '—'
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`
  if (v >= 1_000_000)     return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000)         return `${(v / 1_000).toFixed(0)}K`
  return v.toFixed(0)
}

function ChangeCell({ val }: { val: number | null }) {
  if (val == null) return <span className="text-gray-300">—</span>
  return (
    <span className={cn('font-medium', val >= 0 ? 'text-green-600' : 'text-red-600')}>
      {formatRatioChange(val)}
    </span>
  )
}

// ── Summary cards ─────────────────────────────────────────────────────────────

function SummaryCards({
  stocks,
  lastRefresh,
}: {
  stocks: ScreenerRow[]
  lastRefresh: Date | null
}) {
  const stats = useMemo(() => {
    if (!stocks.length) return null

    const returns  = stocks.map(s => s.return_1y).filter((v): v is number => v != null)
    const yields   = stocks.map(s => s.dividend_yield).filter((v): v is number => v != null && v > 0)
    const divPayers = stocks.filter(s => s.dividend_yield != null && s.dividend_yield > 0).length

    return {
      count:     stocks.length,
      avgReturn: returns.length  ? returns.reduce((a, b) => a + b, 0) / returns.length  : null,
      avgYield:  yields.length   ? yields.reduce((a, b) => a + b, 0) / yields.length    : null,
      divPayers,
    }
  }, [stocks])

  if (!stats) return null

  const cards = [
    {
      label: 'Stocks',
      value: stats.count.toString(),
      icon:  BarChart3,
      color: 'text-blue-600',
      bg:    'bg-blue-50',
    },
    {
      label: 'Avg 1Y Return',
      value: stats.avgReturn != null
        ? <span className={stats.avgReturn >= 0 ? 'text-green-600' : 'text-red-600'}>
            {formatRatioChange(stats.avgReturn)}
          </span>
        : <span className="text-gray-400">—</span>,
      icon:  stats.avgReturn != null && stats.avgReturn >= 0 ? TrendingUp : TrendingDown,
      color: stats.avgReturn != null && stats.avgReturn >= 0 ? 'text-green-600' : 'text-red-600',
      bg:    stats.avgReturn != null && stats.avgReturn >= 0 ? 'bg-green-50' : 'bg-red-50',
    },
    {
      label: 'Avg Div Yield',
      value: stats.avgYield != null
        ? formatRatio(stats.avgYield)
        : <span className="text-gray-400">—</span>,
      icon:  DollarSign,
      color: 'text-emerald-600',
      bg:    'bg-emerald-50',
    },
    {
      label: 'Dividend Payers',
      value: `${stats.divPayers} / ${stats.count}`,
      icon:  Star,
      color: 'text-amber-600',
      bg:    'bg-amber-50',
    },
    {
      label: 'Last Updated',
      value: lastRefresh
        ? lastRefresh.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })
        : '—',
      icon:  RefreshCw,
      color: 'text-gray-500',
      bg:    'bg-gray-50',
    },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
      {cards.map(card => {
        const Icon = card.icon
        return (
          <div key={card.label} className="bg-white border border-gray-200 rounded-xl p-3">
            <div className="flex items-center gap-2 mb-1">
              <div className={cn('p-1.5 rounded-lg', card.bg)}>
                <Icon className={cn('w-3.5 h-3.5', card.color)} />
              </div>
              <span className="text-xs text-gray-500">{card.label}</span>
            </div>
            <div className="text-sm font-semibold text-gray-900">{card.value}</div>
          </div>
        )
      })}
    </div>
  )
}

// ── Plan usage bar ────────────────────────────────────────────────────────────

function PlanUsageBar({
  plan,
  watchlistCount,
  stockCount,
}: {
  plan: string
  watchlistCount: number
  stockCount: number
}) {
  const limits    = getLimits(plan)
  const planLabel = PLAN_LABELS[plan] ?? 'Free'
  const isPro     = ['pro', 'enterprise_pro', 'premium', 'enterprise_premium'].includes(plan)
  const isPremium = ['premium', 'enterprise_premium'].includes(plan)

  const wlPct  = Math.min(100, (watchlistCount / limits.watchlists) * 100)
  const stPct  = Math.min(100, (stockCount / limits.stocks) * 100)

  return (
    <div className="flex items-center flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 mb-1">
      <span className={cn(
        'font-semibold px-2 py-0.5 rounded-full text-[10px]',
        isPremium ? 'bg-purple-100 text-purple-700' :
        isPro     ? 'bg-blue-100 text-blue-700'     :
                    'bg-gray-100 text-gray-600',
      )}>
        {planLabel} Plan
      </span>

      <span>
        <span className={wlPct >= 100 ? 'text-red-600 font-semibold' : ''}>
          {watchlistCount}
        </span> of {limits.watchlists} watchlists used
      </span>

      <span>
        <span className={stPct >= 100 ? 'text-red-600 font-semibold' : ''}>
          {stockCount}
        </span> of {limits.stocks} stocks in this list
      </span>

      {!isPremium && (
        <Link href="/pricing" className="text-blue-600 hover:underline ml-auto">
          {isPro ? 'Upgrade to Premium ↗' : 'Upgrade plan ↗'}
        </Link>
      )}
    </div>
  )
}

// ── Stock table ───────────────────────────────────────────────────────────────

function StockTable({
  stocks,
  codes,
  onRemove,
}: {
  stocks:   ScreenerRow[]
  codes:    string[]
  onRemove: (code: string) => void
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[1100px]">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
              <th className="pl-4 pr-2 py-2.5 text-left w-8" />
              <th className="px-3 py-2.5 text-left">Code</th>
              <th className="px-3 py-2.5 text-left">Company</th>
              <th className="px-3 py-2.5 text-left">Sector</th>
              <th className="px-3 py-2.5 text-right">Price</th>
              <th className="px-3 py-2.5 text-right" title="1-week change (daily change requires live feed)">1W %</th>
              <th className="px-3 py-2.5 text-right" title="1-week change in dollars">1W $</th>
              <th className="px-3 py-2.5 text-right">Volume</th>
              <th className="px-3 py-2.5 text-right">1Y Return</th>
              <th className="px-3 py-2.5 text-right">Mkt Cap</th>
              <th className="px-3 py-2.5 text-right">P/E</th>
              <th className="px-3 py-2.5 text-right">Div Yield</th>
              <th className="px-3 py-2.5 text-right">Franking</th>
              <th className="px-3 py-2.5 text-right">ROE</th>
              <th className="px-3 py-2.5 text-right">F-Score</th>
              <th className="px-3 py-2.5 text-center">Alert</th>
              <th className="pr-4 pl-2 py-2.5 text-right">Remove</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {stocks.map(s => {
              // Approximate today $ from 1W change × price (best available proxy)
              const change1w     = s.return_1w
              const changeAmt    = change1w != null && s.price != null
                ? s.price * change1w
                : null

              return (
                <tr key={s.asx_code} className="hover:bg-blue-50/30 transition-colors">
                  <td className="pl-4 pr-2"><WatchlistButton code={s.asx_code} size="sm" /></td>

                  {/* Code — clickable */}
                  <td className="px-3 py-3">
                    <Link
                      href={`/company/${s.asx_code}`}
                      className="font-mono font-bold text-blue-600 hover:underline hover:text-blue-800 transition-colors"
                    >
                      {s.asx_code}
                    </Link>
                  </td>

                  <td className="px-3 py-3 text-gray-800 max-w-[160px] truncate">{s.company_name}</td>

                  <td className="px-3 py-3">
                    {s.sector
                      ? <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium whitespace-nowrap',
                          SECTOR_COLORS[s.sector] || SECTOR_COLORS['Other'])}>{s.sector}</span>
                      : <span className="text-gray-300">—</span>}
                  </td>

                  <td className="px-3 py-3 text-right font-medium text-gray-900">{formatPrice(s.price)}</td>

                  {/* 1W % */}
                  <td className="px-3 py-3 text-right"><ChangeCell val={change1w ?? null} /></td>

                  {/* 1W $ */}
                  <td className="px-3 py-3 text-right">
                    {changeAmt != null
                      ? <span className={cn('font-medium', changeAmt >= 0 ? 'text-green-600' : 'text-red-600')}>
                          {changeAmt >= 0 ? '+' : ''}{formatPrice(changeAmt)}
                        </span>
                      : <span className="text-gray-300">—</span>}
                  </td>

                  {/* Volume */}
                  <td className="px-3 py-3 text-right text-gray-600 font-mono text-xs">
                    {fmtVolume(s.volume)}
                  </td>

                  <td className="px-3 py-3 text-right"><ChangeCell val={s.return_1y} /></td>
                  <td className="px-3 py-3 text-right text-gray-700">{formatMarketCap(s.market_cap)}</td>
                  <td className="px-3 py-3 text-right text-gray-700">{fmtX(s.pe_ratio)}</td>

                  <td className="px-3 py-3 text-right text-gray-700">
                    {s.dividend_yield != null ? formatRatio(s.dividend_yield) : '—'}
                  </td>

                  <td className="px-3 py-3 text-right">
                    {s.franking_pct != null
                      ? <span className={cn('text-xs font-medium px-1.5 py-0.5 rounded',
                          s.franking_pct === 100 ? 'bg-green-100 text-green-700' :
                          s.franking_pct > 0     ? 'bg-yellow-100 text-yellow-700' :
                                                    'bg-gray-100 text-gray-500')}>
                          {formatPctRaw(s.franking_pct, 0)}
                        </span>
                      : <span className="text-gray-300">—</span>}
                  </td>

                  <td className="px-3 py-3 text-right">
                    {s.roe != null
                      ? <span className={s.roe >= 0.15 ? 'text-green-600 font-medium' : 'text-gray-700'}>
                          {formatRatio(s.roe)}
                        </span>
                      : <span className="text-gray-300">—</span>}
                  </td>

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

                  {/* Alert */}
                  <td className="px-3 py-3 text-center">
                    <Link
                      href={`/alerts?code=${s.asx_code}`}
                      title={`Set alert for ${s.asx_code}`}
                      className="inline-flex items-center justify-center w-6 h-6 text-gray-300 hover:text-amber-500 transition-colors"
                    >
                      <Bell className="w-3.5 h-3.5" />
                    </Link>
                  </td>

                  {/* Remove */}
                  <td className="pr-4 pl-2 py-3 text-right">
                    <button
                      onClick={() => onRemove(s.asx_code)}
                      className="text-gray-300 hover:text-red-400 transition-colors"
                      title={`Remove ${s.asx_code}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              )
            })}

            {/* Codes not in screener universe */}
            {codes.filter(c => !stocks.find(s => s.asx_code === c)).map(code => (
              <tr key={code} className="opacity-50">
                <td className="pl-4 pr-2"><WatchlistButton code={code} size="sm" /></td>
                <td className="px-3 py-3">
                  <Link
                    href={`/company/${code}`}
                    className="font-mono font-bold text-gray-400 hover:underline"
                  >
                    {code}
                  </Link>
                </td>
                <td colSpan={13} className="px-3 py-3 text-xs text-gray-400 italic">Not in screener universe</td>
                <td className="px-3 py-3 text-center">
                  <Link href={`/alerts?code=${code}`} className="inline-flex items-center justify-center w-6 h-6 text-gray-300 hover:text-amber-500">
                    <Bell className="w-3.5 h-3.5" />
                  </Link>
                </td>
                <td className="pr-4 pl-2 py-3 text-right">
                  <button onClick={() => onRemove(code)} className="text-gray-300 hover:text-red-400">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Add stock search ──────────────────────────────────────────────────────────

function AddStockSearch({ onAdd, disabled, disabledReason }: {
  onAdd: (code: string) => void
  disabled?: boolean
  disabledReason?: string
}) {
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open,    setOpen]    = useState(false)

  useEffect(() => {
    if (query.length < 1) { setResults([]); setOpen(false); return }
    const t = setTimeout(async () => {
      try {
        const r = await searchCompanies(query)
        setResults(r.slice(0, 8))
        setOpen(r.length > 0)
      } catch { setResults([]) }
    }, 200)
    return () => clearTimeout(t)
  }, [query])

  if (disabled) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1.5 border border-gray-200 rounded-lg bg-gray-50 text-xs text-gray-400" title={disabledReason}>
        <Lock className="w-3.5 h-3.5" />
        <span>{disabledReason ?? 'Stock limit reached'}</span>
      </div>
    )
  }

  return (
    <div className="relative">
      <div className="flex items-center gap-1 border border-gray-200 rounded-lg bg-white px-2 py-1.5 focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-blue-400">
        <Search className="w-3.5 h-3.5 text-gray-400 shrink-0" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Add stock…"
          className="w-32 text-sm outline-none"
        />
      </div>
      {open && results.length > 0 && (
        <div className="absolute top-full mt-1 left-0 w-64 bg-white border border-gray-200 rounded-xl shadow-lg z-50 py-1">
          {results.map(r => (
            <button
              key={r.asx_code}
              onClick={() => { onAdd(r.asx_code); setQuery(''); setOpen(false) }}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-blue-50 text-left"
            >
              <span className="font-mono text-xs font-bold text-blue-600 w-12 shrink-0">{r.asx_code}</span>
              <span className="text-xs text-gray-700 truncate">{r.company_name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Upgrade gate banner ───────────────────────────────────────────────────────

function UpgradeBanner({ message, tier }: { message: string; tier: 'pro' | 'premium' }) {
  return (
    <div className="flex items-center justify-between gap-4 p-3 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl">
      <div className="flex items-center gap-2.5">
        <Crown className={cn('w-4 h-4 shrink-0', tier === 'premium' ? 'text-purple-600' : 'text-blue-600')} />
        <p className="text-sm text-blue-900">{message}</p>
      </div>
      <Link
        href="/pricing"
        className={cn(
          'shrink-0 flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg text-white transition-colors',
          tier === 'premium' ? 'bg-purple-600 hover:bg-purple-700' : 'bg-blue-600 hover:bg-blue-700',
        )}
      >
        Upgrade <ChevronRight className="w-3 h-3" />
      </Link>
    </div>
  )
}

// ── Server watchlist view (logged-in) ─────────────────────────────────────────

function ServerWatchlists() {
  const { user } = useAuth()
  const plan      = user?.plan ?? 'free'
  const limits    = getLimits(plan)
  const isPro     = ['pro', 'enterprise_pro', 'premium', 'enterprise_premium'].includes(plan)
  const isPremium = ['premium', 'enterprise_premium'].includes(plan)

  const [watchlists,    setWatchlists]    = useState<WatchlistSummary[]>([])
  const [activeId,      setActiveId]      = useState<string | null>(null)
  const [detail,        setDetail]        = useState<WatchlistDetail | null>(null)
  const [stocks,        setStocks]        = useState<ScreenerRow[]>([])
  const [loading,       setLoading]       = useState(true)
  const [stocksLoading, setStocksLoading] = useState(false)
  const [lastRefresh,   setLastRefresh]   = useState<Date | null>(null)
  const [creating,      setCreating]      = useState(false)
  const [newName,       setNewName]       = useState('')
  const [editingId,     setEditingId]     = useState<string | null>(null)
  const [editName,      setEditName]      = useState('')
  const [limitMsg,      setLimitMsg]      = useState<string | null>(null)
  const [addError,      setAddError]      = useState<string | null>(null)

  // Active watchlist stock count
  const activeStockCount = detail?.item_count ?? 0
  const stockLimitReached = activeStockCount >= limits.stocks
  const wlLimitReached    = watchlists.length >= limits.watchlists

  // ── Data loading ───────────────────────────────────────────────────────────

  const loadWatchlists = useCallback(async () => {
    try {
      const resp = await getWatchlists()
      setWatchlists(resp.watchlists)
      if (resp.watchlists.length > 0 && !activeId) {
        setActiveId(resp.watchlists[0].id)
      }
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [activeId])

  useEffect(() => { loadWatchlists() }, [loadWatchlists])

  useEffect(() => {
    if (!activeId) { setDetail(null); setStocks([]); return }
    setStocksLoading(true)
    getWatchlist(activeId)
      .then(async d => {
        setDetail(d)
        if (d.codes.length > 0) {
          const live = await getScreenerBatch(d.codes).catch(() => [])
          setStocks(live)
          setLastRefresh(new Date())
        } else {
          setStocks([])
        }
      })
      .catch(() => { setDetail(null); setStocks([]) })
      .finally(() => setStocksLoading(false))
  }, [activeId])

  // ── Actions ────────────────────────────────────────────────────────────────

  const handleNewListClick = () => {
    if (wlLimitReached) {
      if (!isPro) {
        setLimitMsg(`Free plan includes 1 watchlist. Upgrade to Pro or Premium to create more watchlists.`)
      } else if (!isPremium) {
        setLimitMsg(`You have reached the Pro watchlist limit (${limits.watchlists}). Upgrade to Premium to create up to 50 watchlists.`)
      }
      return
    }
    setLimitMsg(null)
    setCreating(true)
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      const wl = await createWatchlist(newName.trim())
      setWatchlists(prev => [...prev, wl])
      setActiveId(wl.id)
      setCreating(false)
      setNewName('')
      setLimitMsg(null)
    } catch (e: any) {
      setLimitMsg(e?.response?.data?.detail ?? 'Failed to create watchlist')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this watchlist and all its stocks?')) return
    await deleteWatchlist(id)
    setWatchlists(prev => prev.filter(w => w.id !== id))
    if (activeId === id) setActiveId(watchlists.find(w => w.id !== id)?.id ?? null)
  }

  const handleRename = async (id: string) => {
    if (!editName.trim()) return
    const updated = await updateWatchlist(id, editName.trim())
    setWatchlists(prev => prev.map(w => w.id === id ? updated : w))
    setEditingId(null)
  }

  const handleAdd = async (code: string) => {
    if (!activeId) return
    if (stockLimitReached) {
      setAddError(
        isPro
          ? `Stock limit reached (${limits.stocks}). Upgrade to Premium for more stocks.`
          : `Free plan allows up to ${limits.stocks} stocks per watchlist. Upgrade to Pro or Premium for more.`
      )
      return
    }
    setAddError(null)
    try {
      await addToWatchlist(activeId, code)
      const d = await getWatchlist(activeId)
      setDetail(d)
      setWatchlists(prev => prev.map(w => w.id === activeId ? { ...w, item_count: d.item_count } : w))
      const live = await getScreenerBatch(d.codes).catch(() => [])
      setStocks(live)
      setLastRefresh(new Date())
    } catch (e: any) {
      setAddError(e?.response?.data?.detail ?? 'Could not add stock')
    }
  }

  const handleRemove = async (code: string) => {
    if (!activeId) return
    setAddError(null)
    await removeFromWatchlist(activeId, code).catch(() => {})
    setDetail(prev => prev ? { ...prev, codes: prev.codes.filter(c => c !== code), item_count: (prev.item_count ?? 1) - 1 } : prev)
    setStocks(prev => prev.filter(s => s.asx_code !== code))
    setWatchlists(prev => prev.map(w =>
      w.id === activeId ? { ...w, item_count: Math.max(0, w.item_count - 1) } : w
    ))
  }

  const handleRefresh = async () => {
    if (!detail || detail.codes.length === 0) return
    setStocksLoading(true)
    const live = await getScreenerBatch(detail.codes).catch(() => [])
    setStocks(live)
    setLastRefresh(new Date())
    setStocksLoading(false)
  }

  // ── Loading skeleton ───────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map(i => <div key={i} className="h-12 bg-gray-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Star className="w-5 h-5 text-yellow-400 fill-yellow-400" />
            Watchlists
          </h1>
          <PlanUsageBar
            plan={plan}
            watchlistCount={watchlists.length}
            stockCount={activeStockCount}
          />
        </div>

        <div className="flex items-center gap-2">
          {activeId && (
            <AddStockSearch
              onAdd={handleAdd}
              disabled={stockLimitReached}
              disabledReason={
                stockLimitReached
                  ? `Limit: ${limits.stocks} stocks`
                  : undefined
              }
            />
          )}
          {activeId && (
            <button
              onClick={handleRefresh}
              disabled={stocksLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', stocksLoading && 'animate-spin')} />
              Refresh
            </button>
          )}
          <HelpDrawer sections={WATCHLIST_SECTIONS} title="Watchlist Guide" subtitle="Managing lists, columns, and plan limits" />
          <Link
            href="/screener"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50"
          >
            <ArrowUpRight className="w-3.5 h-3.5" />
            Screener
          </Link>
        </div>
      </div>

      {/* Watchlist limit message */}
      {limitMsg && (
        <UpgradeBanner
          message={limitMsg}
          tier={!isPro ? 'pro' : 'premium'}
        />
      )}

      {/* Stock add error */}
      {addError && (
        <div className="flex items-center justify-between gap-3 p-3 bg-amber-50 border border-amber-200 rounded-xl text-sm">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span className="text-amber-800">{addError}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Link href="/pricing" className="text-xs font-semibold text-blue-600 hover:underline">Upgrade</Link>
            <button onClick={() => setAddError(null)} className="text-gray-400 hover:text-gray-600"><X className="w-3.5 h-3.5" /></button>
          </div>
        </div>
      )}

      {/* Stock limit warning bar (near threshold) */}
      {activeStockCount >= limits.stocks * 0.9 && activeStockCount < limits.stocks && (
        <div className="flex items-center gap-2 p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {limits.stocks - activeStockCount} stock slot{limits.stocks - activeStockCount !== 1 ? 's' : ''} remaining on your {PLAN_LABELS[plan]} plan.
          {!isPremium && <Link href="/pricing" className="ml-1 font-semibold underline">Upgrade</Link>}
        </div>
      )}

      {/* Layout: sidebar + content */}
      <div className="flex gap-4 items-start">

        {/* Sidebar */}
        <div className="w-48 shrink-0 space-y-1">
          {watchlists.map(wl => (
            <div
              key={wl.id}
              className={cn(
                'group flex items-center gap-1 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors',
                activeId === wl.id
                  ? 'bg-blue-50 text-blue-700 font-medium'
                  : 'text-gray-700 hover:bg-gray-100',
              )}
              onClick={() => setActiveId(wl.id)}
            >
              {editingId === wl.id ? (
                <div className="flex items-center gap-1 w-full" onClick={e => e.stopPropagation()}>
                  <input
                    autoFocus
                    value={editName}
                    onChange={e => setEditName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter')  handleRename(wl.id)
                      if (e.key === 'Escape') setEditingId(null)
                    }}
                    className="flex-1 text-xs border border-blue-300 rounded px-1 py-0.5 outline-none"
                  />
                  <button onClick={() => handleRename(wl.id)} className="text-green-600 hover:text-green-700">
                    <Check className="w-3 h-3" />
                  </button>
                  <button onClick={() => setEditingId(null)} className="text-gray-400 hover:text-gray-600">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ) : (
                <>
                  <FolderOpen className="w-3.5 h-3.5 shrink-0" />
                  <span className="flex-1 truncate">{wl.name}</span>
                  <span className="text-xs text-gray-400">{wl.item_count}</span>
                  <div className="hidden group-hover:flex items-center gap-0.5 ml-0.5">
                    <button
                      onClick={e => { e.stopPropagation(); setEditingId(wl.id); setEditName(wl.name) }}
                      className="p-0.5 text-gray-400 hover:text-gray-600"
                    >
                      <Pencil className="w-2.5 h-2.5" />
                    </button>
                    <button
                      onClick={e => { e.stopPropagation(); handleDelete(wl.id) }}
                      className="p-0.5 text-gray-400 hover:text-red-500"
                    >
                      <Trash2 className="w-2.5 h-2.5" />
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}

          {/* Create new */}
          {creating ? (
            <div className="flex items-center gap-1 px-2 py-1.5">
              <input
                autoFocus
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter')  handleCreate()
                  if (e.key === 'Escape') setCreating(false)
                }}
                placeholder="List name…"
                className="flex-1 text-xs border border-blue-300 rounded px-2 py-1 outline-none"
              />
              <button onClick={handleCreate} className="text-green-600"><Check className="w-3.5 h-3.5" /></button>
              <button onClick={() => setCreating(false)} className="text-gray-400"><X className="w-3.5 h-3.5" /></button>
            </div>
          ) : (
            <button
              onClick={handleNewListClick}
              className={cn(
                'flex items-center gap-1.5 w-full px-3 py-2 text-sm rounded-lg transition-colors',
                wlLimitReached
                  ? 'text-gray-400 hover:bg-gray-50 cursor-pointer'
                  : 'text-gray-500 hover:text-blue-600 hover:bg-blue-50',
              )}
            >
              {wlLimitReached
                ? <Lock className="w-3.5 h-3.5" />
                : <Plus className="w-3.5 h-3.5" />}
              New list
              {wlLimitReached && (
                <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded ml-auto">
                  {watchlists.length}/{limits.watchlists}
                </span>
              )}
            </button>
          )}
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {!activeId ? (
            <div className="text-center py-16 text-gray-400">
              <Star className="w-8 h-8 mx-auto mb-3 text-gray-200" />
              <p className="text-sm">Create a watchlist to get started</p>
            </div>
          ) : stocksLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          ) : detail && detail.codes.length === 0 ? (
            <div className="text-center py-16 text-gray-400 bg-white border border-gray-200 rounded-xl">
              <Star className="w-8 h-8 mx-auto mb-3 text-gray-200" />
              <p className="text-sm font-medium text-gray-500 mb-1">This list is empty</p>
              <p className="text-xs">Use the search above or the ☆ button on any stock</p>
            </div>
          ) : (
            <>
              {/* Summary cards */}
              {stocks.length > 0 && (
                <SummaryCards stocks={stocks} lastRefresh={lastRefresh} />
              )}

              {/* Stock table */}
              <StockTable
                stocks={stocks}
                codes={detail?.codes ?? []}
                onRemove={handleRemove}
              />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Anonymous localStorage view ───────────────────────────────────────────────

function LocalWatchlist() {
  const { codes, remove, clear, count, mounted } = useWatchlist()
  const [stocks,      setStocks]      = useState<ScreenerRow[]>([])
  const [loading,     setLoading]     = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

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

  if (!mounted || loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 bg-gray-100 rounded w-40 animate-pulse" />
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4 max-w-screen-xl">
      {/* Sign-in banner */}
      <div className="flex items-center justify-between gap-3 px-4 py-3 bg-blue-50 border border-blue-100 rounded-xl text-sm">
        <p className="text-blue-700">
          <strong>Sign in</strong> to save your watchlist across devices and create multiple lists.
        </p>
        <Link
          href="/auth/login"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 shrink-0"
        >
          <LogIn className="w-3.5 h-3.5" />
          Sign in
        </Link>
      </div>

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
          <p className="text-xs text-gray-400 mt-0.5">
            Free Plan · up to 50 stocks · sign in for multiple lists
          </p>
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
          <Link href="/screener" className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50">
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

      {codes.length === 0 ? (
        <div className="text-center py-20">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-yellow-50 rounded-full mb-4">
            <Star className="w-8 h-8 text-yellow-400" />
          </div>
          <p className="text-gray-500 mb-6">
            Click the ☆ star on any stock to add it here.
          </p>
          <Link
            href="/screener"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700"
          >
            <ArrowUpRight className="w-4 h-4" />
            Open Screener
          </Link>
        </div>
      ) : (
        <>
          {stocks.length > 0 && (
            <SummaryCards stocks={stocks} lastRefresh={lastRefresh} />
          )}
          <StockTable stocks={stocks} codes={codes} onRemove={remove} />
          <p className="text-xs text-gray-400">
            Watchlist saved in your browser. Prices updated nightly.
          </p>
        </>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function WatchlistPage() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="space-y-4 max-w-screen-xl">
        <div className="h-8 bg-gray-100 rounded w-40 animate-pulse" />
        {[1, 2, 3].map(i => <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />)}
      </div>
    )
  }

  return user ? <ServerWatchlists /> : <LocalWatchlist />
}
