import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, CheckCircle2, AlertTriangle, ChevronLeft, Zap, BookOpen } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: 'ASX Stock Screening Checklist — Free Download | ASX Screener',
  description: 'A free printable checklist for running a disciplined ASX stock screen. Covers setting your strategy, choosing filters, reviewing results, and building your watchlist.',
  alternates: { canonical: 'https://asxscreener.com.au/resources/asx-stock-screening-checklist' },
}

const SECTIONS = [
  {
    title: 'Before You Screen — Define Your Strategy',
    color: 'blue',
    items: [
      'I know what I am looking for: income, value, growth, or quality.',
      'I have a clear investment time horizon (short-term vs long-term holding).',
      'I understand what sectors or market-cap ranges I want to focus on.',
      'I know my risk tolerance — am I comfortable with small caps or do I prefer large, liquid stocks?',
    ],
  },
  {
    title: 'Setting Your Filters',
    color: 'purple',
    items: [
      'I am starting with 3–5 filters, not 20 (too many returns zero results).',
      'My valuation filter is set (e.g. PE Ratio, EV/EBITDA, or Price-to-Book).',
      'My quality filter is set (e.g. ROE, ROCE, or Net Margin).',
      'My risk filter is set (e.g. Debt/Equity or Interest Coverage).',
      'For income screens: Dividend Yield and Franking % are included.',
      'I have applied a minimum Market Cap to avoid illiquid micro-caps (if relevant).',
    ],
  },
  {
    title: 'Reviewing the Results',
    color: 'emerald',
    items: [
      'The shortlist is a manageable size — under 30 stocks for detailed review.',
      'I have scanned the names: are these the types of companies I expected?',
      'I have spot-checked 2–3 results to confirm the data looks correct.',
      'I have sorted by different columns to see which stocks rank highly across multiple metrics.',
      'I have noted any obvious false positives (e.g. a stock with a high yield due to a special dividend).',
    ],
  },
  {
    title: 'Researching Each Candidate',
    color: 'amber',
    items: [
      'I have read the business model summary for each candidate.',
      'I have checked the last 12 months of ASX announcements.',
      'I have reviewed the trend in key metrics — not just the latest snapshot.',
      'I have compared each stock to its sector peers.',
      'I have noted any red flags: capital raises, guidance misses, debt growth.',
    ],
  },
  {
    title: 'Adding to Your Watchlist',
    color: 'rose',
    items: [
      'Each stock added has a documented thesis (2–3 sentences minimum).',
      'I have noted the price level at which I find the stock attractive.',
      'I have set a price alert at my target level.',
      'I have scheduled a review date (next results announcement).',
      'My watchlist has no more stocks than I can actively monitor.',
    ],
  },
]

const COLOR_MAP: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  blue:    { bg: 'bg-blue-50',    text: 'text-blue-800',    border: 'border-blue-200',    dot: 'bg-blue-500' },
  purple:  { bg: 'bg-purple-50',  text: 'text-purple-800',  border: 'border-purple-200',  dot: 'bg-purple-500' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-800', border: 'border-emerald-200', dot: 'bg-emerald-500' },
  amber:   { bg: 'bg-amber-50',   text: 'text-amber-800',   border: 'border-amber-200',   dot: 'bg-amber-500' },
  rose:    { bg: 'bg-rose-50',    text: 'text-rose-800',    border: 'border-rose-200',    dot: 'bg-rose-500' },
}

export default function ASXScreeningChecklistPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Resources', href: '/resources' }, { label: 'ASX Stock Screening Checklist', href: '/resources/asx-stock-screening-checklist' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Checklist</span>
          <span className="text-xs text-slate-400">5 min read · Free to print</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          ASX Stock Screening Checklist
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          A disciplined screening process turns a 2,000-stock market into a focused research shortlist. Use this checklist every time you run a screen to ensure you are getting the most out of your filters.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> How to use this checklist
        </h2>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'Work through each section in order — strategy comes before filters.',
            'Not every item applies to every screen — skip where irrelevant.',
            'Save or print this page and use it each time you run a new screen.',
            'Revisit your strategy definition every 6 months as your goals evolve.',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-5">
        {SECTIONS.map(({ title, color, items }) => {
          const c = COLOR_MAP[color]
          return (
            <div key={title} className={`${c.bg} border ${c.border} rounded-2xl p-6`}>
              <h2 className={`font-bold ${c.text} mb-4 flex items-center gap-2`}>
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                {title}
              </h2>
              <ul className="space-y-3">
                {items.map(item => (
                  <li key={item} className="flex items-start gap-3">
                    <div className={`mt-1 w-4 h-4 rounded border-2 ${c.border} flex items-center justify-center shrink-0`}>
                      <div className={`w-2 h-2 rounded-sm ${c.dot} opacity-30`} />
                    </div>
                    <span className="text-sm text-slate-700 leading-relaxed">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related Resources
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/what-is-an-asx-stock-screener', label: 'What Is an ASX Stock Screener?' },
            { href: '/learn/asx-stock-research-checklist', label: 'ASX Stock Research Checklist' },
            { href: '/learn/how-to-build-an-asx-watchlist', label: 'How to Build an ASX Watchlist' },
            { href: '/resources/dividend-research-checklist', label: 'Dividend Research Checklist' },
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
          <strong>Not financial advice.</strong> This checklist is an educational resource only. It does not constitute a recommendation to buy or sell any security. Always conduct your own research and consider advice from a licensed financial adviser.
        </p>
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Run your screen now</h2>
        <p className="text-blue-100 mb-5 text-sm">Filter 2,000+ ASX stocks by PE ratio, ROE, dividend yield, debt, and 80+ more metrics. Free to use.</p>
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
