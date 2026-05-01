import Link from 'next/link'
import { BarChart2, Search, TrendingUp, Star, Zap, Shield, ArrowUpRight, ArrowDownRight, Building2 } from 'lucide-react'
import { getMarketSummary, getMarketMovers, getMarketSectors } from '@/lib/api'
import type { MarketSummary, MoversResponse, SectorsResponse } from '@/lib/api'
import { cn, SECTOR_COLORS } from '@/lib/utils'

// ── Static content ────────────────────────────────────────────

const FEATURES = [
  {
    icon: BarChart2,
    title: 'Powerful Screener',
    desc: 'Filter ASX stocks by price, sector, PE ratio, ROE, dividend yield, franking credits, and 40+ more metrics.',
  },
  {
    icon: TrendingUp,
    title: 'Franking Credit Yield',
    desc: 'Unique to Australia — see grossed-up dividend yields with full franking credit calculations for every stock.',
  },
  {
    icon: Shield,
    title: 'Mining & REIT Depth',
    desc: 'AISC, reserve life, NTA per unit, WALE, and occupancy — metrics built specifically for ASX miners and A-REITs.',
  },
  {
    icon: Zap,
    title: 'AI Insights',
    desc: 'Ask questions about any stock in plain English. Powered by Claude AI with access to annual reports and earnings calls.',
  },
  {
    icon: Star,
    title: 'Watchlists & Alerts',
    desc: 'Track your favourite stocks and get alerted when they hit your target price or match your screen criteria.',
  },
  {
    icon: Search,
    title: 'ASIC Short Data',
    desc: 'Live ASIC short-selling positions updated daily — see which stocks are most heavily shorted on the ASX.',
  },
]

const QUICK_SCREENS = [
  { label: 'High Franking Yield',    href: '/screener?preset=high_franking',    color: 'bg-green-50 text-green-700 border-green-200' },
  { label: 'ASX200 Value Stocks',    href: '/screener?preset=asx200_value',     color: 'bg-blue-50 text-blue-700 border-blue-200' },
  { label: 'High Piotroski Score',   href: '/screener?preset=piotroski',        color: 'bg-purple-50 text-purple-700 border-purple-200' },
  { label: 'Materials > $1',         href: '/screener?preset=materials',        color: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
  { label: 'Low Debt, High ROE',     href: '/screener?preset=quality',          color: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
  { label: 'A-REITs',                href: '/screener?preset=reits',            color: 'bg-pink-50 text-pink-700 border-pink-200' },
]

// ── Formatting helpers ────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(decimals)}%`
}

function fmtPrice(v: number | null) {
  if (v == null) return '—'
  return `$${v.toFixed(2)}`
}

function fmtBn(v: number | null) {
  if (v == null) return '—'
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}T`
  return `$${v.toFixed(0)}B`
}

// ── Sub-components ─────────────────────────────────────────────

function StatCard({ val, label, sub }: { val: string; label: string; sub?: string }) {
  return (
    <div className="text-center">
      <div className="text-2xl font-bold text-blue-600">{val}</div>
      <div className="text-sm text-gray-600 font-medium mt-0.5">{label}</div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  )
}

function MoverRow({ stock, isGainer }: { stock: { asx_code: string; company_name: string; price: number | null; return_1w: number | null; return_1m: number | null }; isGainer: boolean }) {
  const pct = stock.return_1w ?? 0
  return (
    <Link
      href={`/company/${stock.asx_code}`}
      className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 transition-colors group"
    >
      <div className="flex items-center gap-3 min-w-0">
        <span className="font-mono font-bold text-blue-600 text-sm w-12 shrink-0">
          {stock.asx_code}
        </span>
        <span className="text-sm text-gray-700 truncate">{stock.company_name}</span>
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-3">
        <span className="text-sm text-gray-600 w-14 text-right">{fmtPrice(stock.price)}</span>
        <span className={cn(
          'text-sm font-semibold w-16 text-right flex items-center justify-end gap-0.5',
          isGainer ? 'text-green-600' : 'text-red-600'
        )}>
          {isGainer
            ? <ArrowUpRight className="w-3.5 h-3.5 shrink-0" />
            : <ArrowDownRight className="w-3.5 h-3.5 shrink-0" />}
          {Math.abs(pct * 100).toFixed(1)}%
        </span>
      </div>
    </Link>
  )
}

function SectorCard({ s }: { s: { sector: string; stock_count: number; avg_pe: number | null; avg_dividend_yield: number | null; avg_return_1y: number | null; total_market_cap_bn: number | null } }) {
  const color = SECTOR_COLORS[s.sector] || SECTOR_COLORS['Other']
  const ret = s.avg_return_1y
  return (
    <Link
      href={`/screener?sector=${encodeURIComponent(s.sector)}`}
      className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md hover:border-blue-200 transition-all group"
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full leading-tight', color)}>
          {s.sector}
        </span>
        <span className="text-xs text-gray-400 shrink-0">{s.stock_count} stocks</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-xs text-gray-400 mb-0.5">Avg P/E</div>
          <div className="text-sm font-semibold text-gray-800">
            {s.avg_pe != null ? s.avg_pe.toFixed(1) : '—'}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-400 mb-0.5">Avg Yield</div>
          <div className="text-sm font-semibold text-gray-800">{fmtPct(s.avg_dividend_yield)}</div>
        </div>
        <div>
          <div className="text-xs text-gray-400 mb-0.5">1Y Return</div>
          <div className={cn('text-sm font-semibold',
            ret == null ? 'text-gray-400' :
            ret >= 0    ? 'text-green-600' : 'text-red-600')}>
            {ret != null ? `${ret >= 0 ? '+' : ''}${(ret * 100).toFixed(1)}%` : '—'}
          </div>
        </div>
      </div>
      <div className="mt-2.5 pt-2 border-t border-gray-50 text-right">
        <span className="text-xs text-gray-400">{fmtBn(s.total_market_cap_bn)} mkt cap</span>
      </div>
    </Link>
  )
}

// ── Data freshness badge ──────────────────────────────────────

function FreshnessBadge({ builtAt }: { builtAt: string | null }) {
  if (!builtAt) return null
  const d = new Date(builtAt)
  const formatted = d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
  return (
    <span className="text-xs text-gray-400">
      Data as at {formatted}
    </span>
  )
}

// ── Page ──────────────────────────────────────────────────────

export default async function HomePage() {
  // Fetch all three endpoints in parallel; fall back gracefully if API is down
  const [summary, movers, sectors] = await Promise.all([
    getMarketSummary().catch((): MarketSummary => ({
      total_stocks: 0, asx200_stocks: 0, stocks_with_dividends: 0,
      avg_dividend_yield: null, median_pe: null, total_market_cap_bn: null, universe_built_at: null,
    })),
    getMarketMovers().catch((): MoversResponse => ({ gainers: [], losers: [], period: '1w' })),
    getMarketSectors().catch((): SectorsResponse => ({ sectors: [] })),
  ])

  const hasMovers  = movers.gainers.length > 0 || movers.losers.length > 0
  const hasSectors = sectors.sectors.length > 0

  return (
    <div className="space-y-10">

      {/* ── Hero ──────────────────────────────────────────────── */}
      <section className="text-center py-10 px-4">
        <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 text-sm font-medium px-3 py-1 rounded-full mb-4">
          <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
          {summary.total_stocks > 0
            ? `${summary.total_stocks.toLocaleString()} active stocks · ASX end-of-day data`
            : '1,800+ active stocks · ASX end-of-day data'
          }
        </div>
        <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
          ASX Stock Screener
        </h1>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto mb-8">
          The most comprehensive ASX screener — franking credits, mining metrics,
          A-REIT depth, and AI insights. Built for Australian investors.
        </p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link
            href="/screener"
            className="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg
                       hover:bg-blue-700 transition-colors shadow-sm"
          >
            Open Screener
          </Link>
          <Link
            href="/company/BHP"
            className="px-6 py-3 bg-white text-gray-700 font-semibold rounded-lg
                       border border-gray-300 hover:bg-gray-50 transition-colors"
          >
            View BHP Example →
          </Link>
        </div>
      </section>

      {/* ── Live stats bar ────────────────────────────────────── */}
      <section className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Market Snapshot</h2>
          <FreshnessBadge builtAt={summary.universe_built_at} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <StatCard
            val={summary.total_stocks > 0 ? summary.total_stocks.toLocaleString() : '—'}
            label="ASX Active Stocks"
          />
          <StatCard
            val={summary.asx200_stocks > 0 ? summary.asx200_stocks.toString() : '—'}
            label="ASX 200 Members"
          />
          <StatCard
            val={summary.stocks_with_dividends > 0 ? summary.stocks_with_dividends.toLocaleString() : '—'}
            label="Dividend Paying"
            sub={summary.total_stocks > 0 && summary.stocks_with_dividends > 0
              ? `${((summary.stocks_with_dividends / summary.total_stocks) * 100).toFixed(0)}% of universe`
              : undefined}
          />
          <StatCard
            val={summary.avg_dividend_yield != null ? `${(summary.avg_dividend_yield * 100).toFixed(1)}%` : '—'}
            label="Avg Dividend Yield"
            sub={summary.median_pe != null ? `Median P/E ${summary.median_pe.toFixed(1)}x` : undefined}
          />
        </div>
      </section>

      {/* ── Market Movers ─────────────────────────────────────── */}
      {hasMovers && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-800">Market Movers</h2>
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded-full">Past week · price &gt; $0.10 · mkt cap &gt; $50M</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

            {/* Gainers */}
            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-green-50">
                <ArrowUpRight className="w-4 h-4 text-green-600" />
                <span className="text-sm font-semibold text-green-700">Top Gainers</span>
                <span className="text-xs text-green-500 ml-auto">1-Week Return</span>
              </div>
              <div className="divide-y divide-gray-50">
                {movers.gainers.map(s => (
                  <MoverRow key={s.asx_code} stock={s} isGainer={true} />
                ))}
                {movers.gainers.length === 0 && (
                  <p className="px-4 py-3 text-sm text-gray-400">No data available</p>
                )}
              </div>
            </div>

            {/* Losers */}
            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-red-50">
                <ArrowDownRight className="w-4 h-4 text-red-500" />
                <span className="text-sm font-semibold text-red-600">Biggest Losers</span>
                <span className="text-xs text-red-400 ml-auto">1-Week Return</span>
              </div>
              <div className="divide-y divide-gray-50">
                {movers.losers.map(s => (
                  <MoverRow key={s.asx_code} stock={s} isGainer={false} />
                ))}
                {movers.losers.length === 0 && (
                  <p className="px-4 py-3 text-sm text-gray-400">No data available</p>
                )}
              </div>
            </div>

          </div>
        </section>
      )}

      {/* ── Sector Snapshot ───────────────────────────────────── */}
      {hasSectors && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-800">Sector Snapshot</h2>
            <Link
              href="/screener"
              className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              Filter by sector <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {sectors.sectors.map(s => (
              <SectorCard key={s.sector} s={s} />
            ))}
          </div>
        </section>
      )}

      {/* ── Quick screens ─────────────────────────────────────── */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Quick Screens</h2>
        <div className="flex flex-wrap gap-2">
          {QUICK_SCREENS.map(s => (
            <Link
              key={s.label}
              href={s.href}
              className={`px-4 py-2 rounded-lg border text-sm font-medium transition-all
                          hover:shadow-sm ${s.color}`}
            >
              {s.label}
            </Link>
          ))}
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────────── */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Everything you need</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map(f => (
            <div key={f.title} className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow">
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 bg-blue-50 rounded-lg">
                  <f.icon className="w-5 h-5 text-blue-600" />
                </div>
                <h3 className="font-semibold text-gray-900">{f.title}</h3>
              </div>
              <p className="text-sm text-gray-600 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

    </div>
  )
}
