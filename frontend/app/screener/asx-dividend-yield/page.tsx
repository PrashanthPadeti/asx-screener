import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, AlertTriangle, ChevronLeft, Zap, BookOpen, TrendingUp, Filter } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: 'ASX Dividend Yield Stocks — Screen by Yield & Franking | ASX Screener',
  description: 'Screen ASX stocks by dividend yield, grossed-up yield, franking credits, and payout ratio. Find high-yield fully franked ASX stocks for income investing.',
  alternates: { canonical: 'https://asxscreener.com.au/screener/asx-dividend-yield' },
}

const FILTERS = [
  { label: 'Dividend Yield', desc: 'Annual dividend ÷ share price. Set a minimum (e.g. 3.5%) to focus on income-generating stocks.', example: '> 3.5%' },
  { label: 'Grossed-Up Yield', desc: 'Yield including the tax value of franking credits. More meaningful than raw yield for Australian resident investors.', example: '> 5%' },
  { label: 'Franking %', desc: 'How much of the dividend is fully franked. 100% is the best for tax efficiency.', example: '= 100%' },
  { label: 'Payout Ratio', desc: 'Dividend as a % of earnings. Below 80% means the dividend is well-covered.', example: '< 80%' },
  { label: 'Dividend CAGR 3Y', desc: 'Annual dividend growth rate over 3 years. Positive growth means the dividend is increasing.', example: '> 0%' },
  { label: 'Market Cap', desc: 'Filter by company size. Larger companies tend to have more reliable dividend histories.', example: '> $1B' },
]

const EXAMPLE_SCREENS = [
  {
    name: 'High-Yield Fully Franked',
    desc: 'Quality income stocks with strong grossed-up yield and conservative payout.',
    filters: [
      'Dividend Yield > 4%',
      'Franking % = 100%',
      'Payout Ratio < 80%',
      'Market Cap > $500M',
    ],
  },
  {
    name: 'Growing Dividend Payers',
    desc: 'Companies that have been consistently growing their dividend payments.',
    filters: [
      'Dividend Yield > 3%',
      'Dividend CAGR 3Y > 5%',
      'ROE > 12%',
      'Debt / Equity < 1.0',
    ],
  },
  {
    name: 'SMSF Income Focus',
    desc: 'Fully franked stocks where the tax credit provides maximum benefit in a low-tax environment.',
    filters: [
      'Grossed-Up Yield > 6%',
      'Franking % = 100%',
      'Payout Ratio < 90%',
      'Market Cap > $1B',
    ],
  },
]

export default function ASXDividendYieldScreenPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Screener', href: '/screener' }, { label: 'ASX Dividend Yield', href: '/screener/asx-dividend-yield' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Income Investing</span>
          <span className="text-xs text-slate-400">Curated screen · Updated daily</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Screen ASX Stocks by Dividend Yield
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          The ASX is one of the world's best markets for dividend income — especially with franking credits adding up to 43% extra value for Australian resident investors. Use our screener to filter by yield, franking, payout ratio, and dividend growth.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-emerald-500 to-teal-600 text-white rounded-2xl p-5 hover:from-emerald-600 hover:to-teal-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Open the ASX Screener</p>
          <p className="text-emerald-100 text-sm">Filter by Dividend Yield, Grossed-Up Yield, Franking % and 80+ metrics</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Why dividend yield matters for ASX investors
        </h2>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'ASX 200 historically yields ~4% — significantly above US or European markets.',
            'Franking credits add up to 43% extra value for investors paying tax at the 30% company rate.',
            'For SMSFs in pension phase, fully franked dividends generate a cash refund from the ATO.',
            'High yield alone is not enough — payout ratio and cash flow sustainability matter most.',
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
          Key dividend filters in the screener
        </h2>
        <div className="space-y-3">
          {FILTERS.map(({ label, desc, example }) => (
            <div key={label} className="bg-white border border-slate-200 rounded-xl p-4 flex items-start gap-4">
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="font-semibold text-slate-900 text-sm">{label}</span>
                  <code className="text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded font-mono">e.g. {example}</code>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example dividend screens</h2>
        <div className="space-y-4">
          {EXAMPLE_SCREENS.map(({ name, desc, filters }) => (
            <div key={name} className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
              <h3 className="font-bold text-slate-900 mb-1">{name}</h3>
              <p className="text-sm text-slate-500 mb-3">{desc}</p>
              <div className="bg-slate-900 rounded-xl p-3">
                <code className="text-emerald-300 font-mono text-xs leading-relaxed block">
                  {filters.join('\n')}
                </code>
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
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained for ASX Investors' },
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained' },
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
          <strong>Not financial advice.</strong> Screens are research tools, not buy recommendations. Past dividend payments do not guarantee future payments. Always conduct your own research.
        </p>
      </div>

    </div>
  )
}
