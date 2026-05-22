'use client'
import { useEffect, useState, useCallback, useRef } from 'react'
import Link from 'next/link'
import {
  Newspaper, Search, X, RefreshCw, AlertTriangle, Filter,
  ExternalLink, Clock, ChevronLeft, ChevronRight, Bookmark,
  TrendingUp, DollarSign, Users, PauseCircle, BarChart2,
  FileText, Lock, Zap, Calendar,
} from 'lucide-react'
import { HelpDrawer } from '@/components/HelpDrawer'
import { NEWS_SECTIONS } from '@/lib/helpContent'
import {
  getAnnouncements, getLatestAnnouncements,
  AnnouncementFeedItem, AnnouncementFeed,
} from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

// ── Constants ─────────────────────────────────────────────────────────────────

const PAGE_SIZE = 30

// Tabs definition
const TABS = [
  { id: 'all',              label: 'All',               icon: Newspaper,     gate: null   as null | 'pro' | 'premium' },
  { id: 'announcements',   label: 'ASX Announcements',  icon: FileText,      gate: null   as null | 'pro' | 'premium' },
  { id: 'market_sensitive',label: 'Market Sensitive',   icon: AlertTriangle, gate: null   as null | 'pro' | 'premium' },
  { id: 'trading_halts',   label: 'Trading Halts',      icon: PauseCircle,   gate: null   as null | 'pro' | 'premium' },
  { id: 'results',         label: 'Results',             icon: BarChart2,     gate: null   as null | 'pro' | 'premium' },
  { id: 'dividends',       label: 'Dividends',           icon: DollarSign,    gate: null   as null | 'pro' | 'premium' },
  { id: 'capital_raisings',label: 'Capital Raisings',   icon: TrendingUp,    gate: null   as null | 'pro' | 'premium' },
  { id: 'director_changes',label: 'Director Changes',   icon: Users,         gate: null   as null | 'pro' | 'premium' },
  { id: 'watchlist',       label: 'Watchlist News',      icon: Bookmark,      gate: 'pro'  as null | 'pro' | 'premium' },
] as const

type TabId = typeof TABS[number]['id']

// Type badge colors
const TYPE_COLORS: Record<string, string> = {
  'Dividend':                    'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  'Trading Halt':                'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  'Quarterly Activities Report': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  'Annual Report':               'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  'Half Yearly Report':          'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  'Placement':                   'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  'Earnings':                    'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400',
  'Merger':                      'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400',
  'Acquisition':                 'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400',
  'Director':                    'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400',
  'Capital Raising':             'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  'Rights Issue':                'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  'AGM':                         'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1)  return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 7)  return `${d}d ago`
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function typeBadge(docType: string | null): string {
  if (!docType) return 'bg-gray-100 text-gray-600'
  for (const [key, cls] of Object.entries(TYPE_COLORS)) {
    if (docType.toLowerCase().includes(key.toLowerCase())) return cls
  }
  return 'bg-gray-100 text-gray-600'
}

function getSource(url: string | null): string {
  if (!url) return 'ASX'
  try {
    const hostname = new URL(url).hostname.replace('www.', '')
    if (hostname.includes('asx.com.au'))   return 'ASX'
    if (hostname.includes('asic.gov.au'))  return 'ASIC'
    if (hostname.includes('afr.com'))      return 'AFR'
    if (hostname.includes('smh.com.au'))   return 'SMH'
    return hostname.split('.')[0].toUpperCase()
  } catch {
    return 'ASX'
  }
}

// ── Source badge config ───────────────────────────────────────────────────────

const SOURCE_CONFIG = {
  asx_filing:     { color: 'bg-blue-100 text-blue-700',   dot: 'bg-blue-500' },
  company_filing: { color: 'bg-purple-100 text-purple-700', dot: 'bg-purple-500' },
  market_news:    { color: 'bg-gray-100 text-gray-600',   dot: 'bg-gray-400' },
} as const

// ── Announcement card ─────────────────────────────────────────────────────────

function AnnouncementCard({ ann }: { ann: AnnouncementFeedItem }) {
  const srcType   = (ann.source_type ?? 'market_news') as keyof typeof SOURCE_CONFIG
  const srcCfg    = SOURCE_CONFIG[srcType] ?? SOURCE_CONFIG.market_news
  const srcLabel  = ann.source_label ?? 'Finance News'
  const isOfficial = srcType === 'asx_filing'
  const btnLabel  = isOfficial ? 'Open Announcement' : 'Open Article'

  return (
    <div className={cn(
      'bg-white border rounded-xl p-4 hover:shadow-sm transition-all group',
      ann.market_sensitive
        ? 'border-l-[3px] border-l-amber-500 border-t border-r border-b border-gray-200'
        : 'border-gray-200 hover:border-blue-200',
    )}>
      <div className="flex items-start gap-3">
        {/* ASX code badge — clickable → company page */}
        <Link
          href={`/company/${ann.asx_code}`}
          className="shrink-0 px-2.5 py-1 bg-slate-800 text-white text-xs font-bold rounded-lg hover:bg-blue-700 transition-colors"
          title={ann.company_name ?? ann.asx_code}
        >
          {ann.asx_code}
        </Link>

        <div className="flex-1 min-w-0">
          {/* Title + open button row */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              {ann.url ? (
                <a
                  href={ann.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-gray-900 leading-snug line-clamp-2 hover:text-blue-700 transition-colors"
                >
                  {ann.title}
                </a>
              ) : (
                <p className="text-sm font-medium text-gray-900 leading-snug line-clamp-2">
                  {ann.title}
                </p>
              )}
              {ann.company_name && (
                <Link
                  href={`/company/${ann.asx_code}`}
                  className="text-xs text-gray-400 hover:text-blue-600 transition-colors mt-0.5 block truncate"
                >
                  {ann.company_name}
                </Link>
              )}
            </div>

            {/* Open button */}
            {ann.url && (
              <a
                href={ann.url}
                target="_blank"
                rel="noopener noreferrer"
                title={btnLabel}
                className={cn(
                  'shrink-0 flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-lg border transition-colors whitespace-nowrap',
                  isOfficial
                    ? 'border-blue-200 text-blue-700 hover:bg-blue-50'
                    : 'border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-700',
                )}
              >
                <ExternalLink className="w-3 h-3" />
                {btnLabel}
              </a>
            )}
          </div>

          {/* Badge row */}
          <div className="flex flex-wrap items-center gap-1.5 mt-2">

            {/* Market sensitive — prominent badge */}
            {ann.market_sensitive && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500 text-white text-[10px] font-bold shadow-sm">
                <AlertTriangle className="w-2.5 h-2.5" />
                MARKET SENSITIVE
              </span>
            )}

            {/* Doc type */}
            {ann.document_type && ann.document_type.toLowerCase() !== 'general' && (
              <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded-full', typeBadge(ann.document_type))}>
                {ann.document_type}
              </span>
            )}

            {/* Page count */}
            {ann.num_pages && (
              <span className="text-[10px] text-gray-400 px-1.5 py-0.5 rounded bg-gray-50 border border-gray-100">
                {ann.num_pages}p
              </span>
            )}

            {/* Right-aligned: source label + time */}
            <div className="ml-auto flex items-center gap-2">
              {/* Source badge */}
              <span className={cn(
                'inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full',
                srcCfg.color,
              )}>
                <span className={cn('w-1.5 h-1.5 rounded-full', srcCfg.dot)} />
                {srcLabel}
              </span>

              <span
                title={fmtDate(ann.released_at)}
                className="text-xs text-gray-400 flex items-center gap-1"
              >
                <Clock className="w-3 h-3" />
                {timeAgo(ann.released_at)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Live ticker ───────────────────────────────────────────────────────────────

function LiveTicker({ items }: { items: AnnouncementFeedItem[] }) {
  const [paused, setPaused] = useState(false)

  // Deduplicate by id
  const deduped = Array.from(new Map(items.map(i => [i.id, i])).values())
  if (!deduped.length) return null

  // Duplicate array so marquee loops seamlessly
  const tickerItems = [...deduped, ...deduped]
  const duration = Math.max(25, deduped.length * 5)

  return (
    <div className="bg-slate-900 border-b border-slate-700 overflow-hidden">
      <div className="flex items-center">
        {/* LIVE label */}
        <div className="shrink-0 bg-blue-600 px-3 py-2 text-xs font-bold text-white uppercase tracking-wide flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse inline-block" />
          Live
        </div>

        {/* Scrolling strip */}
        <div
          className="relative overflow-hidden flex-1 cursor-pointer"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          title="Hover to pause"
        >
          <div
            className="flex gap-8 whitespace-nowrap py-2 px-4 text-xs text-slate-300 animate-marquee"
            style={{
              animationDuration: `${duration}s`,
              animationPlayState: paused ? 'paused' : 'running',
            }}
          >
            {tickerItems.map((ann, i) => (
              <a
                key={`${ann.id}-${i}`}
                href={ann.url ?? `/company/${ann.asx_code}`}
                target={ann.url ? '_blank' : '_self'}
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 shrink-0 hover:text-white transition-colors"
              >
                <Link
                  href={`/company/${ann.asx_code}`}
                  onClick={e => e.stopPropagation()}
                  className="font-bold text-blue-400 hover:text-blue-300"
                >
                  {ann.asx_code}
                </Link>
                <span className="text-slate-500">·</span>
                <span className="max-w-[260px] truncate text-slate-300">
                  {ann.title.length > 60 ? ann.title.slice(0, 60) + '…' : ann.title}
                </span>
                {ann.market_sensitive && (
                  <span className="text-amber-400 font-semibold text-[10px]">⚡ SENSITIVE</span>
                )}
                <span className="text-slate-600 mx-1">|</span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Subscription gate banner ──────────────────────────────────────────────────

function UpgradeBanner({ tier, feature }: { tier: 'pro' | 'premium'; feature: string }) {
  return (
    <div className="flex items-center justify-between gap-4 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl">
      <div className="flex items-center gap-3">
        <Lock className="w-5 h-5 text-blue-600 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-blue-900">{feature}</p>
          <p className="text-xs text-blue-600 mt-0.5">
            Available on {tier === 'pro' ? 'Pro and Premium' : 'Premium'} plans
          </p>
        </div>
      </div>
      <Link
        href="/pricing"
        className="shrink-0 px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 transition-colors"
      >
        Upgrade
      </Link>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function NewsPage() {
  const { user } = useAuth()

  const isPro     = user && ['pro', 'premium', 'enterprise_pro', 'enterprise_premium'].includes(user.plan)
  const isPremium = user && ['premium', 'enterprise_premium'].includes(user.plan)

  const [feed, setFeed]               = useState<AnnouncementFeed | null>(null)
  const [tickerItems, setTickerItems] = useState<AnnouncementFeedItem[]>([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState<string | null>(null)
  const [page, setPage]               = useState(0)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  // Tab
  const [activeTab, setActiveTab] = useState<TabId>('all')

  // Filters
  const [search, setSearch]             = useState('')
  const [docType, setDocType]           = useState('')
  const [sensitiveOnly, setSensitiveOnly] = useState(false)
  const [watchlistOnly, setWatchlistOnly] = useState(false)
  const [dateFrom, setDateFrom]         = useState('')
  const [dateTo, setDateTo]             = useState('')
  const [showDateFilter, setShowDateFilter] = useState(false)

  // ── Tab → API params ───────────────────────────────────────────────────────
  function tabToParams(tab: TabId): { tab?: string; sensitive_only?: boolean; watchlist_only?: boolean } {
    if (tab === 'all')              return {}
    if (tab === 'watchlist')        return { watchlist_only: true }
    if (tab === 'market_sensitive') return { tab: 'market_sensitive' }
    return { tab }
  }

  // ── Fetch feed ─────────────────────────────────────────────────────────────
  const load = useCallback(async (pg = 0) => {
    setLoading(true)
    setError(null)
    try {
      const tabParams = tabToParams(activeTab)
      const data = await getAnnouncements({
        search:         search || undefined,
        document_type:  docType || undefined,
        sensitive_only: sensitiveOnly || undefined,
        watchlist_only: (watchlistOnly || tabParams.watchlist_only) || undefined,
        tab:            tabParams.tab,
        date_from:      dateFrom || undefined,
        date_to:        dateTo   || undefined,
        limit:          PAGE_SIZE,
        offset:         pg * PAGE_SIZE,
      })
      setFeed(data)
      setLastRefresh(new Date())
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'Failed to load announcements')
    } finally {
      setLoading(false)
    }
  }, [activeTab, search, docType, sensitiveOnly, watchlistOnly, dateFrom, dateTo]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Fetch ticker independently ─────────────────────────────────────────────
  useEffect(() => {
    getLatestAnnouncements(30)
      .then(d => setTickerItems(d.announcements))
      .catch(() => {})
  }, [])

  // ── Re-fetch on filter/tab change ──────────────────────────────────────────
  useEffect(() => {
    setPage(0)
    load(0)
  }, [activeTab, search, docType, sensitiveOnly, watchlistOnly, dateFrom, dateTo]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Auto-refresh every 2 min ───────────────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      load(page)
      getLatestAnnouncements(30).then(d => setTickerItems(d.announcements)).catch(() => {})
    }, 2 * 60 * 1000)
    return () => clearInterval(interval)
  }, [load, page])

  const totalPages = feed ? Math.ceil(feed.total / PAGE_SIZE) : 0

  function changePage(newPage: number) {
    setPage(newPage)
    load(newPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function handleTabChange(tab: TabId) {
    // Gate watchlist tab for Pro+
    if (tab === 'watchlist' && !isPro) return
    setActiveTab(tab)
    setPage(0)
  }

  const hasFilters = !!(search || docType || sensitiveOnly || watchlistOnly || dateFrom || dateTo)

  function clearFilters() {
    setSearch('')
    setDocType('')
    setSensitiveOnly(false)
    setWatchlistOnly(false)
    setDateFrom('')
    setDateTo('')
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-50">

      {/* Live ticker */}
      <LiveTicker items={tickerItems} />

      {/* Hero */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Newspaper className="w-6 h-6 text-blue-600" />
                <h1 className="text-xl font-bold text-gray-900">ASX News &amp; Announcements</h1>
              </div>
              <p className="text-sm text-gray-500">
                Official company filings and market announcements, updated every 10 minutes.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {lastRefresh && (
                <span className="text-xs text-gray-400 hidden sm:block">
                  Updated {lastRefresh.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
              <HelpDrawer sections={NEWS_SECTIONS} title="News Guide" subtitle="Announcement types, filters, and the live ticker" />
              <button
                onClick={() => { load(page); getLatestAnnouncements(30).then(d => setTickerItems(d.announcements)).catch(() => {}) }}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
                Refresh
              </button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-6xl mx-auto px-6">
          <div className="flex gap-0.5 overflow-x-auto scrollbar-hide pb-px">
            {TABS.map(tab => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              const isLocked = tab.gate === 'pro' && !isPro

              return (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-3 text-xs font-medium whitespace-nowrap border-b-2 transition-colors',
                    isActive
                      ? 'border-blue-600 text-blue-700'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
                    isLocked && 'opacity-60',
                  )}
                  title={isLocked ? `Requires Pro plan` : undefined}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {tab.label}
                  {isLocked && <Lock className="w-3 h-3 text-gray-400" />}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-5 space-y-4">

        {/* Watchlist upgrade gate */}
        {activeTab === 'watchlist' && !isPro && (
          <UpgradeBanner tier="pro" feature="Watchlist News — see announcements only from your watchlisted stocks" />
        )}

        {/* Filters */}
        <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search company, code, or title…"
                className="w-full pl-9 pr-8 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {search && (
                <button onClick={() => setSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2">
                  <X className="w-4 h-4 text-gray-400 hover:text-gray-600" />
                </button>
              )}
            </div>

            {/* Doc type filter */}
            <div className="relative">
              <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              <select
                value={docType}
                onChange={e => setDocType(e.target.value)}
                className="pl-8 pr-4 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none"
              >
                <option value="">All Types</option>
                {(feed?.document_types ?? []).map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            {/* Sensitive only */}
            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={sensitiveOnly}
                onChange={e => setSensitiveOnly(e.target.checked)}
                className="w-4 h-4 rounded text-amber-500 focus:ring-amber-400"
              />
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              Market sensitive only
            </label>

            {/* Watchlist only (Pro+) */}
            <label className={cn(
              'flex items-center gap-2 text-sm cursor-pointer select-none',
              isPro ? 'text-gray-600' : 'text-gray-400 opacity-60',
            )}>
              <input
                type="checkbox"
                checked={watchlistOnly}
                onChange={e => isPro ? setWatchlistOnly(e.target.checked) : undefined}
                disabled={!isPro}
                className="w-4 h-4 rounded text-blue-500 focus:ring-blue-400 disabled:opacity-50"
              />
              <Bookmark className="w-3.5 h-3.5 text-blue-500" />
              Watchlist only
              {!isPro && <Lock className="w-3 h-3" />}
            </label>

            {/* Date range toggle */}
            <button
              onClick={() => setShowDateFilter(v => !v)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg transition-colors',
                showDateFilter || dateFrom || dateTo
                  ? 'border-blue-400 bg-blue-50 text-blue-700'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50',
              )}
            >
              <Calendar className="w-3.5 h-3.5" />
              Date range
            </button>

            {/* Clear filters */}
            {hasFilters && (
              <button
                onClick={clearFilters}
                className="text-xs text-blue-600 hover:underline ml-auto"
              >
                Clear filters
              </button>
            )}
          </div>

          {/* Date range inputs */}
          {showDateFilter && (
            <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-gray-100">
              <span className="text-xs text-gray-500 font-medium">Date range:</span>
              <input
                type="date"
                value={dateFrom}
                onChange={e => setDateFrom(e.target.value)}
                className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="From"
              />
              <span className="text-gray-400 text-xs">to</span>
              <input
                type="date"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
                className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="To"
              />
              {(dateFrom || dateTo) && (
                <button
                  onClick={() => { setDateFrom(''); setDateTo('') }}
                  className="text-xs text-gray-400 hover:text-gray-600"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}
        </div>

        {/* Premium AI features banner */}
        {!isPremium && (
          <div className="flex items-center justify-between gap-4 p-3 bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200 rounded-xl">
            <div className="flex items-center gap-2.5">
              <Zap className="w-4 h-4 text-purple-600 shrink-0" />
              <p className="text-xs text-purple-800">
                <span className="font-semibold">Premium:</span> Get AI summaries, impact analysis, and sentiment tags for every announcement.
              </p>
            </div>
            <Link
              href="/pricing"
              className="shrink-0 px-3 py-1.5 bg-purple-600 text-white text-xs font-semibold rounded-lg hover:bg-purple-700 transition-colors"
            >
              Upgrade
            </Link>
          </div>
        )}

        {/* Stats row */}
        {feed && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              <span className="font-semibold text-gray-900">{feed.total.toLocaleString()}</span> announcements
              {hasFilters && ' matching filters'}
            </span>
            {totalPages > 1 && (
              <span className="text-xs">Page {page + 1} of {totalPages}</span>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && !feed && (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-20 bg-white border border-gray-200 rounded-xl animate-pulse" />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && feed && feed.announcements.length === 0 && (
          <div className="text-center py-16">
            <Newspaper className="w-10 h-10 text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 text-sm font-medium">No announcements found.</p>
            <p className="text-xs text-gray-400 mt-1">
              {hasFilters
                ? 'Try adjusting or clearing your filters.'
                : 'The announcement feed is populated by the nightly data pipeline.'}
            </p>
            {hasFilters && (
              <button
                onClick={clearFilters}
                className="mt-4 px-4 py-2 text-xs text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50 transition-colors"
              >
                Clear all filters
              </button>
            )}
          </div>
        )}

        {/* Announcement list */}
        {feed && feed.announcements.length > 0 && (
          <div className="space-y-2">
            {loading && (
              <div className="text-center py-2">
                <RefreshCw className="w-4 h-4 text-gray-400 animate-spin mx-auto" />
              </div>
            )}
            {feed.announcements.map(ann => (
              <AnnouncementCard key={ann.id} ann={ann} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 pt-4">
            <button
              onClick={() => changePage(page - 1)}
              disabled={page === 0}
              className="flex items-center gap-1 px-3 py-2 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" /> Previous
            </button>

            <div className="flex items-center gap-1">
              {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
                const p = totalPages <= 7
                  ? i
                  : Math.max(0, Math.min(page - 3, totalPages - 7)) + i
                return (
                  <button
                    key={p}
                    onClick={() => changePage(p)}
                    className={cn(
                      'w-8 h-8 text-sm rounded-lg transition-colors',
                      p === page
                        ? 'bg-blue-600 text-white'
                        : 'border border-gray-200 text-gray-600 hover:bg-gray-50',
                    )}
                  >
                    {p + 1}
                  </button>
                )
              })}
            </div>

            <button
              onClick={() => changePage(page + 1)}
              disabled={page >= totalPages - 1}
              className="flex items-center gap-1 px-3 py-2 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition-colors"
            >
              Next <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Free tier history gate */}
        {!isPro && feed && feed.total > PAGE_SIZE && page >= 2 && (
          <UpgradeBanner tier="pro" feature="Full announcement history — access months of filings with Pro" />
        )}
      </div>
    </div>
  )
}
