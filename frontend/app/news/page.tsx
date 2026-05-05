'use client'
import { useEffect, useState, useCallback, useRef } from 'react'
import Link from 'next/link'
import {
  Newspaper, Search, X, RefreshCw, AlertTriangle, Filter,
  ExternalLink, Clock, ChevronLeft, ChevronRight,
} from 'lucide-react'
import { getAnnouncements, AnnouncementFeedItem, AnnouncementFeed } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1)  return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-AU', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

const TYPE_COLORS: Record<string, string> = {
  'Dividend':                    'bg-green-100 text-green-700',
  'Trading Halt':                'bg-red-100 text-red-700',
  'Quarterly Activities Report': 'bg-blue-100 text-blue-700',
  'Annual Report':               'bg-purple-100 text-purple-700',
  'Half Yearly Report':          'bg-indigo-100 text-indigo-700',
  'Placement':                   'bg-orange-100 text-orange-700',
  'Earnings':                    'bg-teal-100 text-teal-700',
  'Merger':                      'bg-pink-100 text-pink-700',
  'Acquisition':                 'bg-pink-100 text-pink-700',
}

function typeBadge(docType: string | null): string {
  if (!docType) return 'bg-gray-100 text-gray-600'
  for (const [key, cls] of Object.entries(TYPE_COLORS)) {
    if (docType.toLowerCase().includes(key.toLowerCase())) return cls
  }
  return 'bg-gray-100 text-gray-600'
}

// ── Announcement card ─────────────────────────────────────────────────────────

function AnnouncementCard({ ann }: { ann: AnnouncementFeedItem }) {
  return (
    <div className={cn(
      'bg-white border rounded-xl p-4 hover:border-blue-200 hover:shadow-sm transition-all',
      ann.market_sensitive ? 'border-amber-200' : 'border-gray-200',
    )}>
      <div className="flex items-start gap-3">
        {/* Code badge */}
        <Link
          href={`/company/${ann.asx_code}`}
          className="shrink-0 px-2.5 py-1 bg-slate-800 text-white text-xs font-bold rounded-lg hover:bg-slate-700 transition-colors"
        >
          {ann.asx_code}
        </Link>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-medium text-gray-900 leading-snug line-clamp-2">
              {ann.title}
            </p>
            {ann.url && (
              <a
                href={ann.url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 text-gray-400 hover:text-blue-600 transition-colors"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2 mt-2">
            {ann.document_type && (
              <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded-full', typeBadge(ann.document_type))}>
                {ann.document_type}
              </span>
            )}
            {ann.market_sensitive && (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 flex items-center gap-1">
                <AlertTriangle className="w-2.5 h-2.5" /> Market Sensitive
              </span>
            )}
            {ann.company_name && (
              <span className="text-xs text-gray-400 truncate">{ann.company_name}</span>
            )}
            <span className="text-xs text-gray-400 flex items-center gap-1 ml-auto">
              <Clock className="w-3 h-3" />
              <span title={fmtDate(ann.released_at)}>{timeAgo(ann.released_at)}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Ticker strip ──────────────────────────────────────────────────────────────

function LiveTicker({ items }: { items: AnnouncementFeedItem[] }) {
  const ref = useRef<HTMLDivElement>(null)

  if (!items.length) return null

  return (
    <div className="bg-slate-900 border-b border-slate-700 overflow-hidden">
      <div className="flex items-center">
        <div className="shrink-0 bg-blue-600 px-3 py-2 text-xs font-bold text-white uppercase tracking-wide">
          Live
        </div>
        <div className="relative overflow-hidden flex-1">
          <div
            ref={ref}
            className="flex gap-8 animate-marquee whitespace-nowrap py-2 px-4 text-xs text-slate-300"
            style={{ animationDuration: `${Math.max(20, items.length * 4)}s` }}
          >
            {[...items, ...items].map((ann, i) => (
              <span key={i} className="inline-flex items-center gap-2 shrink-0">
                <span className="font-bold text-white">{ann.asx_code}</span>
                <span className="text-slate-400">·</span>
                <span className="max-w-[280px] truncate">{ann.title}</span>
                {ann.market_sensitive && (
                  <span className="text-amber-400 font-semibold">⚡</span>
                )}
                <span className="text-slate-600 mx-2">|</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

const PAGE_SIZE = 30

export default function NewsPage() {
  const [feed, setFeed]           = useState<AnnouncementFeed | null>(null)
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)
  const [page, setPage]           = useState(0)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  // Filters
  const [search, setSearch]       = useState('')
  const [docType, setDocType]     = useState('')
  const [sensitiveOnly, setSensitiveOnly] = useState(false)

  const load = useCallback(async (pg = page) => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAnnouncements({
        search:         search || undefined,
        document_type:  docType || undefined,
        sensitive_only: sensitiveOnly || undefined,
        limit:          PAGE_SIZE,
        offset:         pg * PAGE_SIZE,
      })
      setFeed(data)
      setLastRefresh(new Date())
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [search, docType, sensitiveOnly, page])

  // Initial load + auto-refresh every 2 min
  useEffect(() => {
    load(0)
    setPage(0)
  }, [search, docType, sensitiveOnly]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const interval = setInterval(() => load(page), 2 * 60 * 1000)
    return () => clearInterval(interval)
  }, [load, page])

  const totalPages = feed ? Math.ceil(feed.total / PAGE_SIZE) : 0

  function changePage(newPage: number) {
    setPage(newPage)
    load(newPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const latestItems = feed?.announcements.slice(0, 10) ?? []

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Live ticker */}
      {latestItems.length > 0 && <LiveTicker items={latestItems} />}

      {/* Hero */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-6 py-6">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Newspaper className="w-6 h-6 text-blue-600" />
                <h1 className="text-xl font-bold text-gray-900">ASX News &amp; Announcements</h1>
              </div>
              <p className="text-sm text-gray-500">
                Official company filings and market announcements, updated every 10 minutes.
              </p>
            </div>
            <div className="flex items-center gap-3">
              {lastRefresh && (
                <span className="text-xs text-gray-400">
                  Updated {lastRefresh.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
              <button
                onClick={() => load(page)}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 space-y-5">
        {/* Filters */}
        <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-wrap items-center gap-3">
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
            <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
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

          {/* Sensitive filter */}
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

          {(search || docType || sensitiveOnly) && (
            <button
              onClick={() => { setSearch(''); setDocType(''); setSensitiveOnly(false) }}
              className="text-xs text-blue-600 hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Stats row */}
        {feed && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              <span className="font-semibold text-gray-900">{feed.total.toLocaleString()}</span> announcements
              {(search || docType || sensitiveOnly) && ' matching filters'}
            </span>
            <span className="text-xs">Page {page + 1} of {totalPages || 1}</span>
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
          <div className="space-y-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-20 bg-white border border-gray-200 rounded-xl animate-pulse" />
            ))}
          </div>
        )}

        {/* Empty */}
        {!loading && feed && feed.announcements.length === 0 && (
          <div className="text-center py-16">
            <Newspaper className="w-10 h-10 text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 text-sm">No announcements found.</p>
            <p className="text-xs text-gray-400 mt-1">
              The announcement feed is populated by the nightly data pipeline.
            </p>
          </div>
        )}

        {/* Announcement list */}
        {feed && feed.announcements.length > 0 && (
          <div className="space-y-2">
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
                const p = totalPages <= 7 ? i : Math.max(0, Math.min(page - 3, totalPages - 7)) + i
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
      </div>
    </div>
  )
}
