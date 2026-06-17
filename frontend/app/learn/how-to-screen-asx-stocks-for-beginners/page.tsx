import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, Filter, CheckCircle2 } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata = {
  title: 'How to Screen ASX Stocks for Beginners | ASX Screener',
  description:
    'A step-by-step guide to screening ASX stocks for beginners. Learn what a stock screener does, which filters to start with, and how to research the results.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-screen-asx-stocks-for-beginners' },
}

const BEGINNER_FILTERS = [
  { filter: 'Market Cap > $500M', why: 'Larger companies tend to be more stable, better researched, and more liquid. Avoids speculative micro-caps while you are still learning.' },
  { filter: 'P/E Ratio 10–25', why: 'Excludes very expensive growth stocks (high P/E) and companies with potential problems (very low P/E). A starting range that covers most quality businesses.' },
  { filter: 'Dividend Yield > 2%', why: 'Optional — but dividend payers tend to be profitable, established businesses. A yield filter quickly narrows the list to cash-generative companies.' },
  { filter: 'ROE > 10%', why: 'Return on Equity above 10% means the company is generating decent profits from shareholders\' money. A basic quality signal.' },
  { filter: 'Debt / Equity < 1', why: 'Keeps highly leveraged companies out of your starting list. High debt can amplify losses and creates risk in rate-rising environments.' },
]

const STEPS = [
  { num: '01', title: 'Open the screener', body: 'Go to the ASX Screener and click "Add Filter" to start building your screen. You can also start with a pre-built screen from Alpha Screens.' },
  { num: '02', title: 'Set 2–3 filters', body: 'Don\'t try to filter for everything at once. Start with market cap, one valuation metric (P/E or EV/EBITDA), and one quality metric (ROE or gross margin). This usually gives you 30–100 results.' },
  { num: '03', title: 'Sort the results', body: 'Sort by market cap (largest first) or by dividend yield if you\'re an income investor. This puts the most well-known names at the top, which are easier to research.' },
  { num: '04', title: 'Research the candidates', body: 'Click on any stock to see its full company profile. Read the business description, check the trend in revenue and earnings, and look at the dividend history.' },
  { num: '05', title: 'Add to a watchlist', body: 'Don\'t rush to a decision. Add interesting companies to your watchlist and come back over a few days or weeks. Watching how a stock behaves helps build your understanding.' },
  { num: '06', title: 'Refine your screen', body: 'Once you see what comes through, tighten or loosen your filters. Screening is iterative — you\'ll get better at it with each run.' },
]

const MISTAKES = [
  { mistake: 'Too many filters', fix: 'Start with 2–3. Adding 10 filters narrows results to near-zero and may introduce contradictions.' },
  { mistake: 'Chasing the highest yield', fix: 'A 12% yield often signals a dividend that is about to be cut. Check the payout ratio and cash flow before trusting a high yield.' },
  { mistake: 'Ignoring the business', fix: 'A screener finds candidates — not investments. You still need to understand what the company actually does.' },
  { mistake: 'Using P/E on loss-making companies', fix: 'P/E is meaningless for companies with negative earnings. Use EV/Revenue or EV/EBITDA instead for early-stage or mining companies.' },
  { mistake: 'Acting on screen results immediately', fix: 'Treat the results as a shortlist to research further, not a buy list.' },
]

export default function HowToScreenASXStocksPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'How to Screen ASX Stocks for Beginners', href: '/learn/how-to-screen-asx-stocks-for-beginners' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Beginner</span>
          <span className="text-xs text-slate-400">10 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Screen ASX Stocks for Beginners
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          An ASX stock screener lets you filter thousands of ASX-listed companies down to a manageable shortlist using financial metrics. This guide walks through how to use a screener step-by-step — including which filters to start with and how to avoid the most common beginner mistakes.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Try the ASX Screener</p>
          <p className="text-blue-200 text-sm">Filter 2,100+ ASX stocks by P/E, ROE, dividend yield, franking, growth and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What does a stock screener do?</h2>
        <p className="text-slate-600 leading-relaxed mb-4">
          The ASX has over 2,000 listed companies. Researching all of them individually would take months. A stock screener lets you apply filters — such as &ldquo;show me all companies with a P/E below 15 and ROE above 10%&rdquo; — and instantly get a list of companies that meet those criteria.
        </p>
        <p className="text-slate-600 leading-relaxed">
          Think of it like a filter on a shopping site. Instead of browsing every product, you narrow down by price, brand, and rating. A screener does the same thing for stocks — it turns a list of 2,000 into a manageable shortlist of 20–50 that are worth researching further.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-500" />
          Good starter filters for beginners
        </h2>
        <p className="text-slate-500 text-sm mb-4">These five filters give a reasonable starting point for most Australian investors researching quality, established ASX stocks:</p>
        <div className="space-y-3">
          {BEGINNER_FILTERS.map(({ filter, why }) => (
            <div key={filter} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-mono font-semibold text-blue-700 text-sm mb-1">{filter}</p>
              <p className="text-xs text-slate-500 leading-relaxed">{why}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-3">You don&apos;t need to use all five. Start with two or three and adjust from there.</p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Step-by-step: your first screen</h2>
        <div className="space-y-4">
          {STEPS.map(({ num, title, body }) => (
            <div key={num} className="flex gap-4">
              <div className="shrink-0 w-10 h-10 rounded-full bg-blue-50 text-blue-600 font-bold text-sm flex items-center justify-center">{num}</div>
              <div className="pt-2">
                <p className="font-semibold text-slate-900 text-sm mb-1">{title}</p>
                <p className="text-sm text-slate-500 leading-relaxed">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3">
          Example: a simple quality + value screen
        </h2>
        <div className="bg-slate-900 rounded-xl p-4 mb-3">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block whitespace-pre">{`Market Cap > $500M
P/E Ratio: 10 – 25
ROE > 10%
Dividend Yield > 2%`}</code>
        </div>
        <p className="text-sm text-blue-900 leading-relaxed">
          Running this screen on the ASX typically returns 50–120 stocks — a manageable list of established, profitable, dividend-paying companies across all sectors. Sort by market cap to start with the largest and most familiar names.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">What to do after you run the screen</h2>
        <div className="space-y-3">
          {[
            'Click through to each company\'s profile page to read the business description.',
            'Check the trend — is revenue and earnings growing, flat, or declining over the past 3–5 years?',
            'Look at the dividend history. Has the company paid dividends consistently? Has it been cut recently?',
            'Check the debt level. Net debt / EBITDA below 2x is generally considered manageable.',
            'Read the most recent company announcement or half-year result to understand what management is focused on.',
          ].map((item, i) => (
            <div key={i} className="flex items-start gap-3">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
              <p className="text-sm text-slate-600 leading-relaxed">{item}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Common beginner mistakes</h2>
        <div className="space-y-3">
          {MISTAKES.map(({ mistake, fix }) => (
            <div key={mistake} className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="font-semibold text-amber-900 text-sm mb-1">{mistake}</p>
              <p className="text-xs text-amber-700 leading-relaxed">{fix}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Three ways to search on ASX Screener</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-4">
          ASX Screener offers three ways to find stocks, depending on how specific your idea is:
        </p>
        <div className="space-y-3">
          {[
            { mode: 'Filter mode', desc: 'Click-and-drag filters. Best for beginners. Use sliders and dropdowns to set your criteria without typing anything.' },
            { mode: 'AI Query', desc: 'Type in plain English — e.g. "profitable small caps with low debt and growing dividends". The AI converts your idea into a structured screen.' },
            { mode: 'Query Mode (Admin/Pro)', desc: 'Type SQL-like conditions directly — e.g. "roe > 15 AND (roce > 15 OR roic > 15)". Best for power users who know exactly what they want.' },
          ].map(({ mode, desc }) => (
            <div key={mode} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-semibold text-slate-900 text-sm mb-1">{mode}</p>
              <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/what-is-an-asx-stock-screener', label: 'What Is an ASX Stock Screener?' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained for ASX Investors' },
            { href: '/learn/how-to-build-an-asx-watchlist', label: 'How to Build an ASX Watchlist' },
            { href: '/learn/asx-stock-research-checklist', label: 'ASX Stock Research Checklist' },
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
          <strong>Not financial advice.</strong> Stock screeners are research tools — not buy lists. Always conduct your own research and consider seeking advice from a licensed financial adviser before making investment decisions.
        </p>
      </div>

    </div>
  )
}
