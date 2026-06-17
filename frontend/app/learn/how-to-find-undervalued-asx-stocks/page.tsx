import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, TrendingUp } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How to Find Undervalued ASX Stocks | ASX Screener',
  description:
    'How to identify undervalued ASX stocks using P/E, P/B, EV/EBITDA, and intrinsic value metrics. Includes value investing screens and how to avoid value traps.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-find-undervalued-asx-stocks' },
}

const VALUE_METRICS = [
  { metric: 'P/E Ratio', key: 'pe_ratio', range: '< 15 for value', note: 'Price divided by earnings per share. The most commonly used valuation metric. Low P/E can mean cheap — or can reflect poor growth expectations. Always compare within the same sector.' },
  { metric: 'Price-to-Book (P/B)', key: 'pb_ratio', range: '< 1.5 for value', note: 'Price relative to net asset value. Useful for asset-heavy businesses (banks, miners, REITs). A P/B below 1 means you are buying assets for less than their book value — but check why.' },
  { metric: 'EV/EBITDA', key: 'ev_ebitda', range: '< 8 for value', note: 'Enterprise value (market cap + debt − cash) relative to operating earnings. More useful than P/E because it accounts for debt and is less affected by accounting differences.' },
  { metric: 'EV/FCF', key: 'ev_fcf', range: '< 20 for value', note: 'Enterprise value divided by free cash flow. Arguably the most conservative valuation multiple — prices the business on actual cash generated, not accounting profit.' },
  { metric: 'PEG Ratio', key: 'peg_ratio', range: '< 1.0 for value', note: 'P/E divided by earnings growth rate. Adjusts valuation for growth — a P/E of 20 with 20% growth is cheaper than a P/E of 15 with 5% growth. PEG below 1 is often considered attractively valued.' },
  { metric: 'Dividend Yield', key: 'dividend_yield', range: '> 4% for value', note: 'A high dividend yield relative to history can signal undervaluation — the market is offering you more income per dollar invested than usual. Check sustainability before acting on it.' },
]

const TRAPS = [
  { trap: 'Cheap because earnings are about to fall', why: 'A stock with P/E 8 based on last year\'s earnings can quickly become P/E 20 if earnings halve. Always look at forward earnings and sector cycle position.' },
  { trap: 'Low P/B due to impaired assets', why: 'Book value can overstate real asset value if goodwill or property values are written down. Check asset quality before relying on P/B.' },
  { trap: 'Low P/E due to one-off gains', why: 'Asset sales or accounting releases can inflate a single year\'s earnings, making the P/E look artificially low. Check normalised earnings.' },
  { trap: 'Cheap in a structurally declining industry', why: 'Some businesses are cheap for good reason — their industry is shrinking. A low P/E on a declining newspaper or retail business is not a value opportunity.' },
]

export default function FindUndervaluedASXStocksPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="How to Find Undervalued ASX Stocks"
        description="How to identify undervalued ASX stocks using P/E, P/B, EV/EBITDA, and intrinsic value metrics. Includes value investing screens and how to avoid value traps."
        url="https://asxscreener.com.au/learn/how-to-find-undervalued-asx-stocks"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'How to Find Undervalued ASX Stocks', href: '/learn/how-to-find-undervalued-asx-stocks' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">Intermediate</span>
          <span className="text-xs text-slate-400">10 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Find Undervalued ASX Stocks
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Value investing means buying businesses for less than they are worth — and waiting for the market to recognise that value. This guide covers the key metrics ASX investors use to find undervalued stocks, how to screen for them, and how to avoid the value traps that catch most beginners.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-2xl p-5 hover:from-amber-600 hover:to-orange-600 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen for Undervalued ASX Stocks</p>
          <p className="text-amber-100 text-sm">Filter by P/E, P/B, EV/EBITDA, FCF yield, PEG ratio and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What does &quot;undervalued&quot; actually mean?</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          A stock is undervalued when its market price is below the business&apos;s intrinsic value — what a rational buyer would pay for the entire business based on its cash flows. The gap between price and value is called the <strong>margin of safety</strong>.
        </p>
        <p className="text-slate-600 leading-relaxed">
          There is no single &quot;correct&quot; way to calculate intrinsic value — it involves assumptions about future earnings, growth rates, and discount rates. Screener metrics help you build a shortlist of <em>potentially</em> undervalued companies to then research in depth.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-slate-500" />
          Key valuation metrics for value screening
        </h2>
        <div className="space-y-3">
          {VALUE_METRICS.map(({ metric, key, range, note }) => (
            <div key={key} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
                <p className="font-semibold text-slate-900 text-sm">{metric}</p>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-amber-700 bg-amber-50 px-2 py-0.5 rounded">{range}</span>
                  <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{key}</code>
                </div>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{note}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Value investing screens</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Classic value screen',
              desc: 'Low P/E and P/B with positive earnings and manageable debt. Benjamin Graham-style starting point.',
              filters: ['pe_ratio > 0', 'pe_ratio < 15', 'pb_ratio < 1.5', 'debt_to_equity < 1', 'eps_growth_1y > -20', 'market_cap > 200'],
            },
            {
              name: 'Deep value + quality filter',
              desc: 'Cheap on EV/EBITDA with a quality overlay — avoids buying low-quality value traps.',
              filters: ['ev_ebitda < 8', 'ev_ebitda > 0', 'roe > 10', 'piotroski_f_score >= 6', 'ocf_positive = true', 'market_cap > 300'],
            },
            {
              name: 'FCF value screen',
              desc: 'High FCF yield with positive earnings trend — buying real cash generation at a discount.',
              filters: ['fcf_yield > 6', 'ocf_positive = true', 'eps_growth_1y > 0', 'net_debt_to_ebitda < 2', 'market_cap > 200'],
            },
          ].map(({ name, desc, filters }) => (
            <div key={name} className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
              <h3 className="font-bold text-slate-900 mb-1">{name}</h3>
              <p className="text-xs text-slate-500 mb-3">{desc}</p>
              <div className="bg-slate-900 rounded-xl p-3">
                <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{filters.join('\n')}</code>
              </div>
              <Link href="/screener" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800">
                Apply this screen <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
              </Link>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Value traps — and how to avoid them</h2>
        <p className="text-slate-500 text-sm mb-3">A value trap is a stock that looks cheap but keeps falling. The most common causes:</p>
        <div className="space-y-3">
          {TRAPS.map(({ trap, why }) => (
            <div key={trap} className="bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="font-semibold text-red-900 text-sm mb-1">{trap}</p>
              <p className="text-xs text-red-700 leading-relaxed">{why}</p>
            </div>
          ))}
        </div>
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mt-4">
          <p className="text-sm text-emerald-900 leading-relaxed">
            <strong>The simplest value trap filter:</strong> always add a positive earnings trend filter (<code className="text-xs bg-emerald-100 px-1 rounded">eps_growth_1y &gt; -10</code>) and a minimum F-Score (<code className="text-xs bg-emerald-100 px-1 rounded">piotroski_f_score &gt;= 5</code>). These two filters remove most deteriorating businesses that look cheap for bad reasons.
          </p>
        </div>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-find-quality-asx-companies', label: 'How to Find Quality ASX Companies' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
            { href: '/learn/how-to-research-asx-stocks-dyor', label: 'How to Research ASX Stocks (DYOR)' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> Valuation metrics are starting points for research, not buy signals. Always conduct your own due diligence before investing.</p>
      </div>
    </div>
  )
}
