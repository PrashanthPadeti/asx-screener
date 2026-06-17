import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, AlertTriangle, ChevronLeft, Zap, BookOpen, TrendingUp, Filter } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: 'Screen ASX Stocks by Moving Average | ASX Screener',
  description: 'Filter ASX stocks by 20-day, 50-day, and 200-day moving averages. Find stocks above or below key technical levels using the ASX Screener.',
  alternates: { canonical: 'https://asxscreener.com.au/screener/asx-moving-average' },
}

const MA_TYPES = [
  {
    name: '20-Day Moving Average (20 DMA)',
    shortterm: true,
    desc: 'A short-term trend indicator. Stocks trading above their 20 DMA are in a short-term uptrend. Often used by active traders as a momentum signal.',
    usedFor: 'Short-term momentum; entry/exit timing in active strategies',
    color: 'blue',
  },
  {
    name: '50-Day Moving Average (50 DMA)',
    shortterm: false,
    desc: 'A medium-term trend indicator. Often used to confirm whether a shorter-term move is part of a broader trend. A stock that reclaims its 50 DMA after being below it can signal recovering momentum.',
    usedFor: 'Medium-term trend confirmation; swing trading reference',
    color: 'purple',
  },
  {
    name: '200-Day Moving Average (200 DMA)',
    shortterm: false,
    desc: 'The most widely watched long-term trend indicator. Stocks above their 200 DMA are generally considered to be in a long-term uptrend. Institutional investors often use this as a broad market health indicator.',
    usedFor: 'Long-term trend; portfolio quality filter; market health gauge',
    color: 'emerald',
  },
]

const COLOR_MAP: Record<string, { bg: string; text: string; border: string }> = {
  blue:    { bg: 'bg-blue-50',    text: 'text-blue-800',    border: 'border-blue-200' },
  purple:  { bg: 'bg-purple-50',  text: 'text-purple-800',  border: 'border-purple-200' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-800', border: 'border-emerald-200' },
}

export default function ASXMovingAverageScreenPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Screener', href: '/screener' }, { label: 'ASX Moving Average', href: '/screener/asx-moving-average' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">Technical Filter</span>
          <span className="text-xs text-slate-400">Price vs moving average</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Screen ASX Stocks by Moving Average
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Moving averages are widely used to identify trend direction and filter stocks by momentum. Use the ASX Screener to find stocks trading above or below their 20, 50, or 200-day moving averages — and combine with fundamental filters for a more complete picture.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-purple-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Open the ASX Screener</p>
          <p className="text-purple-200 text-sm">Filter by 20 DMA, 50 DMA, 200 DMA and combine with fundamentals</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 flex items-start gap-3">
        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <p className="text-sm text-amber-900">
          <strong>Moving averages alone are not a trading strategy.</strong> They describe where the price has been — not where it will go. Fundamental investors use them as an additional context filter, not as the primary signal. Always combine with quality and valuation metrics.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> What moving averages tell you
        </h2>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'A stock above its moving average is in an uptrend over that time period.',
            'A stock crossing above its 200 DMA is sometimes called a "golden cross" — seen as a bullish signal.',
            'A stock that has recently dropped below all three MAs may be in broad price decline.',
            'MA filters are most useful as a secondary filter after applying fundamental criteria.',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <TrendingUp className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-500" />
          The three key moving averages
        </h2>
        <div className="space-y-4">
          {MA_TYPES.map(({ name, desc, usedFor, color }) => {
            const c = COLOR_MAP[color]
            return (
              <div key={name} className={`${c.bg} border ${c.border} rounded-2xl p-5`}>
                <h3 className={`font-bold ${c.text} mb-2`}>{name}</h3>
                <p className="text-sm text-slate-700 leading-relaxed mb-2">{desc}</p>
                <p className="text-xs text-slate-500"><span className="font-semibold">Typically used for:</span> {usedFor}</p>
              </div>
            )
          })}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example combined screens</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Quality stocks in uptrend',
              desc: 'Strong fundamentals with positive long-term price momentum.',
              filters: ['Price > 200 DMA', 'ROE > 15%', 'PE Ratio < 20', 'Debt / Equity < 0.5'],
            },
            {
              name: 'Income stocks above 200 DMA',
              desc: 'High-yield stocks where the price is in a long-term uptrend — reducing yield trap risk.',
              filters: ['Price > 200 DMA', 'Dividend Yield > 4%', 'Franking % = 100%', 'Payout Ratio < 80%'],
            },
            {
              name: 'Potential recovery candidates',
              desc: 'Quality stocks that have pulled back below their 50 DMA — possible re-entry for value investors.',
              filters: ['Price < 50 DMA', 'Price > 200 DMA', 'ROE > 12%', 'Market Cap > $500M'],
            },
          ].map(({ name, desc, filters }) => (
            <div key={name} className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
              <h3 className="font-bold text-slate-900 mb-1">{name}</h3>
              <p className="text-sm text-slate-500 mb-3">{desc}</p>
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

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Learn more
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/what-is-an-asx-stock-screener', label: 'What Is an ASX Stock Screener?' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/glossary', label: 'Metrics Glossary — all screener fields defined' },
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
          <strong>Not financial advice.</strong> Moving average filters are technical indicators used for research purposes only. Past price trends do not predict future performance. Always apply fundamental analysis and conduct your own due diligence.
        </p>
      </div>

    </div>
  )
}
