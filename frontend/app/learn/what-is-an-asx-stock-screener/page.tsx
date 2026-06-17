import Link from 'next/link'
import { ChevronLeft, BarChart2, Search, Filter, ArrowRight, AlertTriangle, Zap, BookOpen, CheckCircle2 } from 'lucide-react'

export const metadata = {
  title: 'What Is an ASX Stock Screener? How Investors Use One | ASX Screener',
  description:
    'Learn what an ASX stock screener is, how it works, and how Australian investors use screening criteria like PE ratio, dividend yield, and ROE to find stocks worth researching.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/what-is-an-asx-stock-screener' },
}

const CRITERIA = [
  { label: 'PE Ratio',        desc: 'Price relative to earnings — a valuation check.' },
  { label: 'Dividend Yield',  desc: 'Annual dividend as a percentage of the share price.' },
  { label: 'Franking %',      desc: 'How much of the dividend carries a tax credit.' },
  { label: 'ROE',             desc: 'Return on equity — how efficiently management uses shareholder funds.' },
  { label: 'Debt / Equity',   desc: 'Balance sheet leverage — higher can mean more risk.' },
  { label: 'Revenue Growth',  desc: 'Whether the business is growing or shrinking.' },
  { label: 'Market Cap',      desc: 'Total market value — filters by company size.' },
  { label: 'Sector',          desc: 'Industry category — financials, materials, healthcare, etc.' },
]

export default function WhatIsAnASXStockScreenerPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Link href="/learn" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-blue-600 transition-colors">
        <ChevronLeft className="w-4 h-4" />
        Education Hub
      </Link>

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner</span>
          <span className="text-xs text-slate-400">7 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          What Is an ASX Stock Screener — And How Do Investors Use One?
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          The ASX lists over 2,000 companies. A stock screener lets you filter that universe down to a shortlist of stocks that meet your specific research criteria — in seconds. Here is exactly how it works.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Key Takeaways
        </h2>
        <ul className="space-y-2">
          {[
            'A stock screener filters thousands of stocks down to a shortlist using criteria you define.',
            'You set the rules — PE ratio below 15, dividend yield above 4%, ROE above 12% — and the screener returns every stock that matches.',
            'Screening is a research starting point, not a buy recommendation. A stock that passes your screen still needs individual analysis.',
            'ASX investors benefit from screeners that include Australian-specific data like franking credits and grossed-up yield.',
          ].map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-900">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {point}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-8 text-slate-700 leading-relaxed">

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">The problem a screener solves</h2>
          <p>
            The ASX has over 2,000 listed companies across sectors from mining to healthcare to technology. Reviewing each one individually would take months. Most investors never look beyond the top 20 or 30 names they hear about in the media — which means they miss a large part of the market.
          </p>
          <p className="mt-3">
            A stock screener solves this by letting you apply a set of financial filters across the entire market simultaneously. Instead of browsing randomly, you define criteria that matter to your strategy — and the screener instantly surfaces every stock that qualifies.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">How a stock screener works</h2>
          <p>
            At its core, a screener is a filter tool. You set one or more conditions — minimum or maximum values for financial metrics — and the screener queries a database of company data to return all stocks that satisfy every condition.
          </p>
          <p className="mt-3">
            For example, you might define:
          </p>
          <div className="mt-4 bg-slate-900 rounded-xl p-4">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Example Screen</p>
            <code className="text-emerald-300 font-mono text-sm leading-relaxed block">
              PE Ratio &lt; 15{'\n'}
              Dividend Yield &gt; 4%{'\n'}
              Franking % = 100%{'\n'}
              Debt / Equity &lt; 0.5{'\n'}
              Market Cap &gt; $500M
            </code>
          </div>
          <p className="mt-4">
            The screener returns every ASX stock that simultaneously meets all five conditions. You get a shortlist to investigate — not a list of stocks to buy.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Common screening criteria for ASX investors</h2>
          <div className="grid sm:grid-cols-2 gap-3 mt-4">
            {CRITERIA.map(({ label, desc }) => (
              <div key={label} className="bg-white border border-slate-200 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-1">
                  <Filter className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                  <span className="font-semibold text-sm text-slate-800">{label}</span>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-slate-500">
            ASX Screener includes 80+ metrics including ASX-specific data points like franking credits, grossed-up yield, mining resource data, and REIT-specific metrics not typically found in global screeners.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">What a screener is — and what it is not</h2>
          <div className="grid sm:grid-cols-2 gap-4 mt-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
              <h3 className="font-semibold text-emerald-800 mb-2 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4" /> A screener IS
              </h3>
              <ul className="space-y-1.5 text-sm text-emerald-900">
                {[
                  'A research starting point',
                  'A way to narrow 2,000+ stocks to a manageable shortlist',
                  'A tool for applying your own investment criteria systematically',
                  'A time-saving filter across an entire market',
                ].map(item => <li key={item} className="flex items-start gap-1.5"><span className="mt-1 shrink-0">·</span>{item}</li>)}
              </ul>
            </div>
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <h3 className="font-semibold text-red-800 mb-2 flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4" /> A screener is NOT
              </h3>
              <ul className="space-y-1.5 text-sm text-red-900">
                {[
                  'A buy or sell recommendation',
                  'A substitute for reading annual reports',
                  'A guarantee of future returns',
                  'Investment advice of any kind',
                ].map(item => <li key={item} className="flex items-start gap-1.5"><span className="mt-1 shrink-0">·</span>{item}</li>)}
              </ul>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">A practical screening workflow</h2>
          <ol className="space-y-4">
            {[
              { n: 1, title: 'Define your strategy', body: 'Are you looking for income (high yield), value (low PE), growth (revenue CAGR), or quality (high ROE, low debt)? Your strategy determines which metrics to filter on.' },
              { n: 2, title: 'Set your filters', body: 'Choose your criteria and thresholds. Start with 3–4 filters. Too many criteria at once often returns zero results.' },
              { n: 3, title: 'Review the shortlist', body: 'Look at what the screen returned. Check whether the results make intuitive sense — does this list of companies actually fit your strategy?' },
              { n: 4, title: 'Research each company individually', body: 'Open the annual report, read the latest ASX announcements, understand the business model. A screen narrows the field; your analysis decides.' },
              { n: 5, title: 'Add to your watchlist', body: 'Companies that survive your research process go on your watchlist. You monitor them over time and review when conditions change.' },
            ].map(({ n, title, body }) => (
              <li key={n} className="flex gap-4">
                <span className="w-7 h-7 rounded-full bg-blue-600 text-white text-sm font-bold flex items-center justify-center shrink-0 mt-0.5">{n}</span>
                <div>
                  <p className="font-semibold text-slate-800">{title}</p>
                  <p className="text-sm text-slate-600 mt-1">{body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Why ASX investors need an ASX-specific screener</h2>
          <p>
            Generic global screeners (like Finviz or TradingView) include ASX stocks, but they typically lack Australian-specific data. For ASX investors, the data gaps matter:
          </p>
          <ul className="mt-3 space-y-2 text-sm">
            {[
              'Franking credits and grossed-up yield — critical for income investors but absent from most global tools',
              'JORC-compliant resource estimates for mining stocks',
              'NTA (Net Tangible Assets) and FFO for A-REITs',
              'ASIC short-interest data for gauging market sentiment',
              'ASX announcement data — placement history, trading halts, director changes',
            ].map(item => (
              <li key={item} className="flex items-start gap-2">
                <Search className="w-3.5 h-3.5 text-blue-500 shrink-0 mt-0.5" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-3">Related ASX Screener Filters</h2>
        <div className="flex flex-wrap gap-2">
          {['PE Ratio', 'Dividend Yield', 'Franking %', 'ROE', 'Debt / Equity', 'Revenue Growth', 'Market Cap'].map(f => (
            <span key={f} className="text-xs font-medium bg-white border border-amber-300 text-amber-800 px-2.5 py-1 rounded-full">{f}</span>
          ))}
        </div>
        <Link href="/screener" className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-amber-700 hover:text-amber-900">
          Run Your First Screen <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Continue Learning
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-research-asx-stocks-dyor', label: 'How to Research ASX Stocks: A DYOR Workflow' },
            { href: '/learn/asx-stock-research-checklist', label: 'ASX Stock Research Checklist' },
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained' },
            { href: '/glossary', label: 'Metrics Glossary — Every filter defined' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />
              {label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p>
          <strong>Not financial advice.</strong> Stock screeners are research and educational tools. Nothing on this page constitutes a recommendation to buy or sell any security. Always conduct your own research (DYOR) and consider seeking advice from a licensed financial adviser.
        </p>
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Start screening ASX stocks now</h2>
        <p className="text-blue-100 mb-5 text-sm">Filter 2,000+ ASX stocks by PE ratio, dividend yield, franking credits, ROE, and 80+ more metrics. Free to use.</p>
        <Link
          href="/screener"
          className="inline-flex items-center gap-2 bg-white text-blue-700 font-semibold px-5 py-2.5 rounded-xl hover:bg-blue-50 transition-colors"
        >
          <BarChart2 className="w-4 h-4" />
          Open the Screener
        </Link>
      </div>

    </div>
  )
}
