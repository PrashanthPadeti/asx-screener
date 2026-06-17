import Link from 'next/link'
import { BarChart2, Search, TrendingUp, Star, Zap, Shield, ArrowUpRight, ArrowDownRight, Database, Calculator, Building2, Brain } from 'lucide-react'
import { getMarketMovers, getMarketSectors } from '@/lib/api'
import type { Metadata } from 'next'
import type { MarketSummary, MoversResponse, SectorsResponse } from '@/lib/api'
import { cn, SECTOR_COLORS } from '@/lib/utils'

export const metadata: Metadata = {
  title: 'ASX Screener | ASX Stock Screener & Australian Stock Research Tool',
  description: 'Discover, filter, compare, monitor, and research ASX stocks using simple filters, AI queries, advanced screens, watchlists, alerts, and market data tools. Free for Australian investors.',
  alternates: { canonical: 'https://asxscreener.com.au/' },
}

// Force dynamic rendering so every request fetches live data.
export const dynamic = 'force-dynamic'

// Internal API URL for server-side fetches (avoids firewall on public port 8000)
const INTERNAL_API = process.env.API_INTERNAL_URL || 'http://localhost:8000'

async function fetchMarketSummary(): Promise<MarketSummary> {
  try {
    const res = await fetch(`${INTERNAL_API}/api/v1/market/summary`, { cache: 'no-store' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json()
  } catch {
    return { total_stocks: 0, asx200_stocks: 0, stocks_with_dividends: 0,
             avg_dividend_yield: null, median_pe: null, total_market_cap_bn: null, universe_built_at: null }
  }
}

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

// ── Sample preview table rows (real-looking ASX data) ─────────
const PREVIEW_STOCKS = [
  { code: 'BHP',  name: 'BHP Group',               sector: 'Materials',    price: 43.82, pe: 11.4, yield: 5.2, roe: 28.1, rsi: 54.2, yieldColor: 'text-green-600' },
  { code: 'CBA',  name: 'Commonwealth Bank',        sector: 'Financials',   price: 138.50, pe: 22.1, yield: 3.4, roe: 13.8, rsi: 61.7, yieldColor: 'text-green-600' },
  { code: 'CSL',  name: 'CSL Limited',              sector: 'Health Care',  price: 292.10, pe: 38.6, yield: 1.1, roe: 22.4, rsi: 48.3, yieldColor: 'text-gray-600' },
  { code: 'WES',  name: 'Wesfarmers',               sector: 'Cons. Disc.',  price: 74.40, pe: 29.3, yield: 3.1, roe: 41.2, rsi: 57.9, yieldColor: 'text-green-600' },
  { code: 'NAB',  name: 'National Australia Bank',  sector: 'Financials',   price: 38.95, pe: 14.8, yield: 5.8, roe: 12.1, rsi: 52.4, yieldColor: 'text-green-600' },
  { code: 'RIO',  name: 'Rio Tinto',                sector: 'Materials',    price: 118.20, pe: 9.7, yield: 6.4, roe: 24.7, rsi: 46.8, yieldColor: 'text-green-600' },
  { code: 'WBC',  name: 'Westpac Banking',          sector: 'Financials',   price: 32.10, pe: 13.2, yield: 6.1, roe: 10.9, rsi: 44.5, yieldColor: 'text-green-600' },
  { code: 'GMG',  name: 'Goodman Group',            sector: 'Real Estate',  price: 36.80, pe: 31.5, yield: 1.2, roe: 18.3, rsi: 63.1, yieldColor: 'text-gray-600' },
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
    <div className="text-center px-2">
      <div className="text-3xl md:text-4xl font-extrabold text-blue-600 tracking-tight leading-none">
        {val}
      </div>
      <div className="text-xs md:text-sm text-gray-500 font-medium mt-2 uppercase tracking-wide">
        {label}
      </div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
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

// ── FAQ schema ────────────────────────────────────────────────

const faqSchema = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: [
    {
      '@type': 'Question',
      name: 'What is ASX Screener?',
      acceptedAnswer: { '@type': 'Answer', text: 'ASX Screener is an Australian stock screening and research platform that helps investors discover, filter, compare, monitor, and research ASX-listed stocks using simple filters, AI queries, advanced screens, watchlists, alerts, and market data tools.' },
    },
    {
      '@type': 'Question',
      name: 'What can I screen for on ASX Screener?',
      acceptedAnswer: { '@type': 'Answer', text: 'You can screen ASX stocks by market cap, sector, P/E ratio, ROE, ROIC, dividend yield, franking credits, revenue growth, earnings growth, cash flow, debt, returns, price momentum, Piotroski F-Score, and 80+ more metrics.' },
    },
    {
      '@type': 'Question',
      name: 'What are franking credits and why does ASX Screener show them?',
      acceptedAnswer: { '@type': 'Answer', text: 'Franking credits (imputation credits) are tax credits attached to Australian dividends. ASX Screener shows grossed-up dividend yields that include franking, so Australian investors can compare the true after-tax value of dividends across stocks.' },
    },
    {
      '@type': 'Question',
      name: 'Does ASX Screener support AI stock screening?',
      acceptedAnswer: { '@type': 'Answer', text: 'Yes. ASX Screener includes an AI Query mode that lets you type plain English stock screening ideas — for example "profitable small caps with low debt and growing revenue" — and converts them into structured screens automatically.' },
    },
    {
      '@type': 'Question',
      name: 'Is ASX Screener financial advice?',
      acceptedAnswer: { '@type': 'Answer', text: 'No. ASX Screener is a data, screening, and research tool only. It does not provide personal financial advice. Always do your own research or consult a licensed financial adviser before making investment decisions.' },
    },
    {
      '@type': 'Question',
      name: 'Is ASX Screener free to use?',
      acceptedAnswer: { '@type': 'Answer', text: 'Yes, ASX Screener has a free plan that gives access to the core stock screener and market data. Premium plans unlock additional features including AI insights, advanced screens, watchlists, alerts, and portfolio tracking.' },
    },
  ],
}

// ── Page ──────────────────────────────────────────────────────

export default async function HomePage() {
  const [summary, movers, sectors] = await Promise.all([
    fetchMarketSummary(),
    getMarketMovers('1w').catch((): MoversResponse => ({ gainers: [], losers: [], period: '1w' })),
    getMarketSectors().catch((): SectorsResponse => ({ sectors: [] })),
  ])

  const hasMovers  = movers.gainers.length > 0 || movers.losers.length > 0
  const hasSectors = sectors.sectors.length > 0

  return (
    <div className="space-y-10">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }}
      />

      {/* ── Hero ──────────────────────────────────────────────── */}
      <section className="py-10 px-4">
        <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr_220px] gap-6 items-center">

          {/* ── Left: Monthly founding deal ── */}
          <div className="hidden lg:flex flex-col gap-3 bg-[#0f172a] rounded-2xl p-4 border border-amber-500/20 self-stretch justify-center">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full tracking-wide">FOUNDING MEMBER</span>
            </div>
            <div>
              <p className="text-slate-400 text-xs mb-1">Monthly plan</p>
              <p className="text-white text-sm font-semibold leading-snug">Pay <span className="text-amber-400">1 month</span></p>
              <p className="text-slate-300 text-xs mt-0.5">→ get <span className="text-amber-400 font-semibold">6 months</span> access</p>
            </div>
            <div className="bg-white/5 rounded-lg px-3 py-1.5 text-center">
              <span className="text-emerald-400 text-xs font-semibold">5× value</span>
              <span className="text-slate-500 text-xs"> · save 83%</span>
            </div>
            <Link href="/pricing" className="block text-center bg-amber-500 hover:bg-amber-400 text-slate-900 text-xs font-semibold py-2 rounded-lg transition-colors">
              Claim deal →
            </Link>
          </div>

          {/* ── Centre: existing hero content (unchanged) ── */}
          <div className="text-center">
            <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 text-sm font-medium px-3 py-1 rounded-full mb-4">
              <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
              {summary.total_stocks > 0
                ? `${summary.total_stocks.toLocaleString()} active stocks · ASX end-of-day data`
                : '2,100+ active stocks · ASX end-of-day data'
              }
            </div>

            <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
              ASX Stock Screener for Australian Investors
            </h1>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto mb-8">
              Discover, filter, compare, monitor, and research ASX stocks using simple filters, AI queries, advanced screens, watchlists, and market data tools. Built for Australian investors — with franking credits, mining depth, and A-REIT metrics you won&apos;t find anywhere else.
            </p>

            <div className="flex flex-wrap gap-3 justify-center mb-8">
              <Link href="/screener" className="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors shadow-sm">
                Open Screener
              </Link>
              <Link href="/screener?preset=asx200" className="px-6 py-3 bg-white text-blue-700 font-semibold rounded-lg border-2 border-blue-200 hover:bg-blue-50 transition-colors">
                Explore ASX 200
              </Link>
              <Link href="/company/BHP" className="px-6 py-3 bg-white text-gray-700 font-semibold rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors">
                View BHP Example →
              </Link>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-gray-500">
              <span className="flex items-center gap-1.5"><Database className="w-3.5 h-3.5 text-blue-400" />ASX end-of-day data</span>
              <span className="hidden sm:block text-gray-200">|</span>
              <span className="flex items-center gap-1.5"><Calculator className="w-3.5 h-3.5 text-blue-400" />Franking credit calculations</span>
              <span className="hidden sm:block text-gray-200">|</span>
              <span className="flex items-center gap-1.5"><Building2 className="w-3.5 h-3.5 text-blue-400" />Mining &amp; A-REIT metrics</span>
              <span className="hidden sm:block text-gray-200">|</span>
              <span className="flex items-center gap-1.5"><Brain className="w-3.5 h-3.5 text-blue-400" />AI stock insights</span>
            </div>
          </div>

          {/* ── Right: Annual founding deal + scarcity ── */}
          <div className="hidden lg:flex flex-col gap-3 bg-[#0f172a] rounded-2xl p-4 border border-amber-500/30 self-stretch justify-center">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full tracking-wide">BEST VALUE</span>
              <span className="text-[10px] text-slate-500">100 spots only</span>
            </div>
            <div>
              <p className="text-slate-400 text-xs mb-1">Annual plan</p>
              <p className="text-white text-sm font-semibold leading-snug">Pay <span className="text-amber-400">1 year</span></p>
              <p className="text-slate-300 text-xs mt-0.5">→ get <span className="text-amber-400 font-semibold">3 years</span> access</p>
            </div>
            <div className="bg-white/5 rounded-lg px-3 py-1.5 text-center">
              <span className="text-emerald-400 text-xs font-semibold">3× value</span>
              <span className="text-slate-500 text-xs"> · save 67%</span>
            </div>
            {/* Scarcity bar */}
            <div>
              <div className="flex justify-between text-[10px] mb-1">
                <span className="text-slate-500">Spots claimed</span>
                <span className="text-amber-400 font-semibold">68 / 100</span>
              </div>
              <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
                <div className="h-full w-[68%] bg-amber-400 rounded-full" />
              </div>
            </div>
            <Link href="/pricing" className="block text-center bg-amber-500 hover:bg-amber-400 text-slate-900 text-xs font-semibold py-2 rounded-lg transition-colors">
              Claim deal →
            </Link>
          </div>

        </div>

        {/* Mobile banner — shown instead of side cards on small screens */}
        <div className="lg:hidden mt-6 bg-[#0f172a] rounded-2xl p-4 border border-amber-500/20">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full">FOUNDING MEMBER · 100 spots only</span>
          </div>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div className="bg-white/5 rounded-xl p-3">
              <p className="text-slate-400 text-xs mb-1">Monthly</p>
              <p className="text-white text-sm font-semibold">Pay 1 month</p>
              <p className="text-amber-400 text-xs mt-0.5">→ get 6 months</p>
            </div>
            <div className="bg-white/5 rounded-xl p-3 border border-amber-500/20">
              <p className="text-slate-400 text-xs mb-1">Annual</p>
              <p className="text-white text-sm font-semibold">Pay 1 year</p>
              <p className="text-amber-400 text-xs mt-0.5">→ get 3 years</p>
            </div>
          </div>
          <Link href="/pricing" className="block text-center bg-amber-500 hover:bg-amber-400 text-slate-900 text-sm font-semibold py-2.5 rounded-lg transition-colors">
            Claim founding member deal →
          </Link>
        </div>
      </section>

      {/* ── Market Snapshot ───────────────────────────────────── */}
      <section className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Market Snapshot</h2>
          <FreshnessBadge builtAt={summary.universe_built_at} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 divide-x-0 md:divide-x divide-gray-100">
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
            <Link href="/screener" className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1">
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
              className={`px-4 py-2 rounded-lg border text-sm font-medium transition-all hover:shadow-sm ${s.color}`}
            >
              {s.label}
            </Link>
          ))}
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────────── */}
      <section>
        <h2 className="text-xl md:text-2xl font-bold text-gray-900 mb-1">
          Everything Australian investors need to screen ASX stocks
        </h2>
        <p className="text-sm text-gray-500 mb-5">Built from the ground up for the ASX — not adapted from a US tool.</p>
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

      {/* ── Preview Table ─────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">See it in action</h2>
            <p className="text-sm text-gray-500 mt-0.5">A snapshot of ASX stocks available in the screener</p>
          </div>
          <Link
            href="/screener"
            className="hidden sm:flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 transition-colors"
          >
            Open Full Screener <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          {/* Table — scrollable on mobile */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide w-20">Code</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide">Company</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide hidden md:table-cell">Sector</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide">Price</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide hidden sm:table-cell">P/E</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide">Div Yield</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide hidden lg:table-cell">ROE</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide hidden lg:table-cell">RSI</th>
                  <th className="text-right px-4 py-3 font-semibold text-gray-600 text-xs uppercase tracking-wide"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {PREVIEW_STOCKS.map((s) => (
                  <tr key={s.code} className="hover:bg-blue-50/40 transition-colors group">
                    <td className="px-4 py-3">
                      <span className="font-mono font-bold text-blue-600">{s.code}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium text-gray-800 truncate max-w-[160px] block">{s.name}</span>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full font-medium">{s.sector}</span>
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-gray-800">${s.price.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-gray-600 hidden sm:table-cell">{s.pe.toFixed(1)}x</td>
                    <td className={`px-4 py-3 text-right font-semibold ${s.yieldColor}`}>{s.yield.toFixed(1)}%</td>
                    <td className="px-4 py-3 text-right text-gray-600 hidden lg:table-cell">{s.roe.toFixed(1)}%</td>
                    <td className="px-4 py-3 text-right hidden lg:table-cell">
                      <span className={cn(
                        'text-xs font-semibold px-2 py-0.5 rounded-full',
                        s.rsi >= 70 ? 'bg-red-50 text-red-600' :
                        s.rsi <= 30 ? 'bg-green-50 text-green-600' :
                        'bg-gray-100 text-gray-600'
                      )}>
                        {s.rsi.toFixed(1)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/company/${s.code}`}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Table footer */}
          <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between gap-4">
            <p className="text-xs text-gray-400">
              Sample preview only — open the full screener for latest available data.
            </p>
            <Link
              href="/screener"
              className="text-xs text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1 shrink-0"
            >
              Screen all {summary.total_stocks > 0 ? summary.total_stocks.toLocaleString() : '2,100+'} stocks <ArrowUpRight className="w-3 h-3" />
            </Link>
          </div>
        </div>
      </section>

      {/* ── SEO Section ───────────────────────────────────────── */}
      <section className="bg-blue-50 border border-blue-100 rounded-xl p-6 md:p-8">
        <h2 className="text-xl md:text-2xl font-bold text-gray-900 mb-3">
          Why use an ASX-specific stock screener?
        </h2>
        <p className="text-gray-600 mb-5 leading-relaxed max-w-3xl">
          Most stock screeners are built for US markets and adapted for the ASX as an afterthought.
          Australian investors have unique needs that generic tools simply don&apos;t cover.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            {
              title: 'Franking Credits',
              desc: 'Australian dividend imputation means a 4% dividend with full franking is worth up to 5.7% gross. Only an ASX-specific screener shows you the true grossed-up yield.',
            },
            {
              title: 'Mining & Resources Depth',
              desc: 'The ASX is dominated by miners. Key metrics like AISC (all-in sustaining cost), reserve life, and production guidance are critical for evaluating BHP, RIO, FMG, and hundreds of junior miners.',
            },
            {
              title: 'A-REIT Metrics',
              desc: 'Australian Real Estate Investment Trusts (A-REITs) require NTA per unit, WALE (weighted average lease expiry), and occupancy rates — metrics that US screeners don\'t include.',
            },
            {
              title: 'ASIC Short Position Data',
              desc: 'ASIC publishes daily short-selling data for ASX-listed stocks. Tracking short interest helps identify stocks under pressure — data unique to the Australian regulatory environment.',
            },
            {
              title: 'ASX Index Membership',
              desc: 'Whether a stock is in the ASX 200, ASX 300, or a GICS sector index affects liquidity, index fund ownership, and institutional coverage. Filter directly by index membership.',
            },
            {
              title: 'End-of-Day ASX Pricing',
              desc: 'Prices sourced directly from ASX end-of-day feeds — updated nightly after market close. No stale data, no US market hours confusion, no currency conversion required.',
            },
          ].map(item => (
            <div key={item.title} className="bg-white rounded-lg p-4 border border-blue-100">
              <h3 className="font-semibold text-gray-900 mb-1.5 text-sm">{item.title}</h3>
              <p className="text-xs text-gray-600 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-5">
          ASX Screener is built from the ground up for the Australian Securities Exchange.
          Not financial advice — always do your own research before making investment decisions.
        </p>
      </section>

    </div>
  )
}
