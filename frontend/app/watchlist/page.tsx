'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import {
  Star, Trash2, ArrowUpRight, RefreshCw, Plus, Pencil,
  Check, X, LogIn, FolderOpen, Search,
} from 'lucide-react'
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

// ── Helpers ───────────────────────────────────────────────────

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

// ── Stock table (shared between both modes) ───────────────────

function StockTable({
  stocks,
  codes,
  onRemove,
}: {
  stocks: ScreenerRow[]
  codes: string[]
  onRemove: (code: string) => void
}) {
  return (
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
                <td className="pl-4 pr-2"><WatchlistButton code={s.asx_code} size="sm" /></td>
                <td className="px-3 py-3">
                  <Link href={`/company/${s.asx_code}`}
                    className="font-mono font-bold text-blue-600 hover:underline">
                    {s.asx_code}
                  </Link>
                </td>
                <td className="px-3 py-3 text-gray-800 max-w-[180px] truncate">{s.company_name}</td>
                <td className="px-3 py-3">
                  {s.sector
                    ? <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium whitespace-nowrap',
                        SECTOR_COLORS[s.sector] || SECTOR_COLORS['Other'])}>{s.sector}</span>
                    : <span className="text-gray-300">—</span>}
                </td>
                <td className="px-3 py-3 text-right font-medium text-gray-900">{formatPrice(s.price)}</td>
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
                <td className="pr-4 pl-2 py-3 text-right">
                  <button onClick={() => onRemove(s.asx_code)}
                    className="text-gray-300 hover:text-red-400 transition-colors">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            ))}
            {/* Codes not in screener.universe */}
            {codes.filter(c => !stocks.find(s => s.asx_code === c)).map(code => (
              <tr key={code} className="opacity-50">
                <td className="pl-4 pr-2"><WatchlistButton code={code} size="sm" /></td>
                <td className="px-3 py-3 font-mono font-bold text-gray-400">{code}</td>
                <td colSpan={10} className="px-3 py-3 text-xs text-gray-400 italic">Not in screener universe</td>
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

// ── Add stock search ──────────────────────────────────────────

function AddStockSearch({ onAdd }: { onAdd: (code: string) => void }) {
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

  return (
    <div className="relative">
      <div className="flex items-center gap-1 border border-gray-200 rounded-lg bg-white px-2 py-1.5">
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

// ── Server watchlist view (logged-in) ─────────────────────────

function ServerWatchlists() {
  const [watchlists,     setWatchlists]     = useState<WatchlistSummary[]>([])
  const [activeId,       setActiveId]       = useState<string | null>(null)
  const [detail,         setDetail]         = useState<WatchlistDetail | null>(null)
  const [stocks,         setStocks]         = useState<ScreenerRow[]>([])
  const [loading,        setLoading]        = useState(true)
  const [stocksLoading,  setStocksLoading]  = useState(false)
  const [lastRefresh,    setLastRefresh]    = useState<Date | null>(null)
  const [creating,       setCreating]       = useState(false)
  const [newName,        setNewName]        = useState('')
  const [editingId,      setEditingId]      = useState<string | null>(null)
  const [editName,       setEditName]       = useState('')

  // Load watchlist list
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

  // Load active watchlist detail + live stock data
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

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      const wl = await createWatchlist(newName.trim())
      setWatchlists(prev => [...prev, wl])
      setActiveId(wl.id)
      setCreating(false)
      setNewName('')
    } catch { /* ignore */ }
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
    await addToWatchlist(activeId, code).catch(() => {})
    // Reload detail
    const d = await getWatchlist(activeId)
    setDetail(d)
    setWatchlists(prev => prev.map(w => w.id === activeId ? { ...w, item_count: d.item_count } : w))
    const live = await getScreenerBatch(d.codes).catch(() => [])
    setStocks(live)
    setLastRefresh(new Date())
  }

  const handleRemove = async (code: string) => {
    if (!activeId) return
    await removeFromWatchlist(activeId, code).catch(() => {})
    setDetail(prev => prev ? { ...prev, codes: prev.codes.filter(c => c !== code) } : prev)
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

  if (loading) {
    return (
      <div className="space-y-4">
        {[1,2,3].map(i => <div key={i} className="h-12 bg-gray-100 rounded-xl animate-pulse" />)}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <Star className="w-5 h-5 text-yellow-400 fill-yellow-400" />
          Watchlists
        </h1>
        <div className="flex items-center gap-2">
          {activeId && detail && detail.codes.length > 0 && (
            <AddStockSearch onAdd={handleAdd} />
          )}
          {activeId && (
            <button onClick={handleRefresh} disabled={stocksLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              <RefreshCw className={cn('w-3.5 h-3.5', stocksLoading && 'animate-spin')} />
              Refresh
            </button>
          )}
          <Link href="/screener"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50">
            <ArrowUpRight className="w-3.5 h-3.5" />
            Screener
          </Link>
        </div>
      </div>

      {/* Watchlist tabs + content */}
      <div className="flex gap-4 items-start">

        {/* Sidebar */}
        <div className="w-48 shrink-0 space-y-1">
          {watchlists.map(wl => (
            <div key={wl.id}
              className={cn(
                'group flex items-center gap-1 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors',
                activeId === wl.id ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700 hover:bg-gray-100'
              )}
              onClick={() => setActiveId(wl.id)}
            >
              {editingId === wl.id ? (
                <div className="flex items-center gap-1 w-full" onClick={e => e.stopPropagation()}>
                  <input
                    autoFocus
                    value={editName}
                    onChange={e => setEditName(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') handleRename(wl.id); if (e.key === 'Escape') setEditingId(null) }}
                    className="flex-1 text-xs border border-blue-300 rounded px-1 py-0.5 outline-none"
                  />
                  <button onClick={() => handleRename(wl.id)} className="text-green-600 hover:text-green-700"><Check className="w-3 h-3" /></button>
                  <button onClick={() => setEditingId(null)} className="text-gray-400 hover:text-gray-600"><X className="w-3 h-3" /></button>
                </div>
              ) : (
                <>
                  <FolderOpen className="w-3.5 h-3.5 shrink-0" />
                  <span className="flex-1 truncate">{wl.name}</span>
                  <span className="text-xs text-gray-400">{wl.item_count}</span>
                  <div className="hidden group-hover:flex items-center gap-0.5 ml-0.5">
                    <button onClick={e => { e.stopPropagation(); setEditingId(wl.id); setEditName(wl.name) }}
                      className="p-0.5 text-gray-400 hover:text-gray-600"><Pencil className="w-2.5 h-2.5" /></button>
                    <button onClick={e => { e.stopPropagation(); handleDelete(wl.id) }}
                      className="p-0.5 text-gray-400 hover:text-red-500"><Trash2 className="w-2.5 h-2.5" /></button>
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
                onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setCreating(false) }}
                placeholder="List name…"
                className="flex-1 text-xs border border-blue-300 rounded px-2 py-1 outline-none"
              />
              <button onClick={handleCreate} className="text-green-600"><Check className="w-3.5 h-3.5" /></button>
              <button onClick={() => setCreating(false)} className="text-gray-400"><X className="w-3.5 h-3.5" /></button>
            </div>
          ) : (
            <button onClick={() => setCreating(true)}
              className="flex items-center gap-1.5 w-full px-3 py-2 text-sm text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
              <Plus className="w-3.5 h-3.5" />
              New list
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
              {[1,2,3].map(i => (
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
              {lastRefresh && (
                <p className="text-xs text-gray-400 mb-2">Updated {lastRefresh.toLocaleTimeString()}</p>
              )}
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

// ── Anonymous localStorage view ───────────────────────────────

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
        {[1,2,3,4,5].map(i => (
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
        <Link href="/auth/login"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 shrink-0">
          <LogIn className="w-3.5 h-3.5" />
          Sign in
        </Link>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <Star className="w-5 h-5 text-yellow-400 fill-yellow-400" />
          Watchlist
          <span className="text-sm font-normal text-gray-400 ml-1">
            {count} stock{count !== 1 ? 's' : ''}
          </span>
        </h1>
        <div className="flex items-center gap-2">
          <button onClick={refresh} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
            <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
            Refresh
          </button>
          <Link href="/screener"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50">
            <ArrowUpRight className="w-3.5 h-3.5" />
            Screener
          </Link>
          {count > 0 && (
            <button onClick={() => { if (confirm('Clear all watchlist items?')) clear() }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-500 border border-red-100 rounded-lg hover:bg-red-50">
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
          <Link href="/screener"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700">
            <ArrowUpRight className="w-4 h-4" />
            Open Screener
          </Link>
        </div>
      ) : (
        <>
          {lastRefresh && (
            <p className="text-xs text-gray-400">Updated {lastRefresh.toLocaleTimeString()}</p>
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

// ── Main page ─────────────────────────────────────────────────

export default function WatchlistPage() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="space-y-4 max-w-screen-xl">
        <div className="h-8 bg-gray-100 rounded w-40 animate-pulse" />
        {[1,2,3].map(i => <div key={i} className="h-12 bg-gray-100 rounded animate-pulse" />)}
      </div>
    )
  }

  return user ? <ServerWatchlists /> : <LocalWatchlist />
}
