import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, AlertTriangle, ChevronLeft, Zap, BookOpen, Filter } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: 'Screen ASX Stocks by Market Cap — Large, Mid & Small Cap | ASX Screener',
  description: 'Filter ASX stocks by market capitalisation. Screen large-cap ASX 200 stocks, mid-cap, small-cap, and micro-cap companies. Find stocks by size category.',
  alternates: { canonical: 'https://asxscreener.com.au/screener/asx-market-cap' },
}

const CAP_TIERS = [
  {
    name: 'Large Cap (ASX 100)',
    range: 'Market Cap > $5B',
    color: 'blue',
    characteristics: [
      'Institutional grade — held by superannuation funds and ETFs',
      'High liquidity — easy to enter and exit positions',
      'Typically in the ASX 200 or ASX 100 index',
      'More analyst coverage and institutional research',
      'Slower growth potential but more predictable earnings',
    ],
    examples: 'CBA, BHP, CSL, NAB, WES, ANZ, WBC, RIO, MQG',
  },
  {
    name: 'Mid Cap',
    range: '$500M < Market Cap < $5B',
    color: 'purple',
    characteristics: [
      'Balance of liquidity and growth potential',
      'Often in the ASX 200 or ASX 300 index',
      'Less analyst coverage than large caps — more research opportunity',
      'Can still pay reliable dividends with reasonable growth',
      'More volatile than large caps but less than small caps',
    ],
    examples: 'NST, BXB, ILU, REA, CPU, IGO, NIC',
  },
  {
    name: 'Small Cap',
    range: '$50M < Market Cap < $500M',
    color: 'amber',
    characteristics: [
      'Higher growth potential but higher risk',
      'Limited analyst coverage — research advantage possible',
      'Lower liquidity — harder to build or exit large positions',
      'Often pre-dividend or paying smaller yields',
      'Require more due diligence on management and balance sheet',
    ],
    examples: 'Typically outside ASX 300 — sector-specific names',
  },
  {
    name: 'Micro Cap',
    range: 'Market Cap < $50M',
    color: 'rose',
    characteristics: [
      'Speculative — many are pre-revenue or early stage',
      'Very low liquidity — large spreads and thin order books',
      'High binary risk: significant upside or significant loss',
      'Rarely pay dividends; cash burn is a key risk factor',
      'Suitable only for investors who understand speculative investing',
    ],
    examples: 'Explorers, early-stage biotech, micro-technology',
  },
]

const COLOR_MAP: Record<string, { bg: string; text: string; border: string; badge: string }> = {
  blue:   { bg: 'bg-blue-50',   text: 'text-blue-800',   border: 'border-blue-200',   badge: 'bg-blue-100 text-blue-700' },
  purple: { bg: 'bg-purple-50', text: 'text-purple-800', border: 'border-purple-200', badge: 'bg-purple-100 text-purple-700' },
  amber:  { bg: 'bg-amber-50',  text: 'text-amber-800',  border: 'border-amber-200',  badge: 'bg-amber-100 text-amber-700' },
  rose:   { bg: 'bg-rose-50',   text: 'text-rose-800',   border: 'border-rose-200',   badge: 'bg-rose-100 text-rose-700' },
}

export default function ASXMarketCapScreenPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Screener', href: '/screener' }, { label: 'ASX Market Cap', href: '/screener/asx-market-cap' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Market Cap Screening</span>
          <span className="text-xs text-slate-400">Filter by company size</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Screen ASX Stocks by Market Capitalisation
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Market capitalisation is one of the most important initial filters for any ASX screen. It determines liquidity, volatility, analyst coverage, and risk profile. Use it alongside quality and valuation metrics to define your investable universe.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Open the ASX Screener</p>
          <p className="text-blue-200 text-sm">Set Market Cap minimum and combine with PE, ROE, Yield and 80+ other filters</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> How market cap is calculated
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed">
          Market Cap = Share Price × Total Shares on Issue. It represents the total market value of all outstanding shares. It changes daily as the share price moves. On the ASX Screener, market cap data is updated end of day from ASX pricing data.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-500" />
          ASX market cap categories
        </h2>
        <div className="space-y-4">
          {CAP_TIERS.map(({ name, range, color, characteristics, examples }) => {
            const c = COLOR_MAP[color]
            return (
              <div key={name} className={`${c.bg} border ${c.border} rounded-2xl p-6`}>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <h3 className={`font-bold ${c.text}`}>{name}</h3>
                  <code className={`text-xs font-mono px-2 py-1 rounded ${c.badge}`}>{range}</code>
                </div>
                <ul className="space-y-1.5 mb-3">
                  {characteristics.map(ch => (
                    <li key={ch} className="flex items-start gap-2 text-sm text-slate-700">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0" />
                      {ch}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-slate-500 font-medium">Examples: {examples}</p>
              </div>
            )
          })}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Combining market cap with other filters</h2>
        <div className="space-y-3">
          {[
            { name: 'Large-cap quality income', filters: ['Market Cap > $5B', 'Dividend Yield > 4%', 'Franking % = 100%', 'ROE > 12%'] },
            { name: 'Mid-cap value screen', filters: ['$500M < Market Cap < $5B', 'PE Ratio < 15', 'ROE > 10%', 'Net Debt / EBITDA < 2.0'] },
            { name: 'Small-cap growth screen', filters: ['$50M < Market Cap < $500M', 'Revenue Growth 3Y > 15%', 'Gross Margin > 40%', 'Net Cash (no debt)'] },
          ].map(({ name, filters }) => (
            <div key={name} className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
              <h3 className="font-bold text-slate-900 mb-2">{name}</h3>
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
            { href: '/resources/asx-stock-screening-checklist', label: 'ASX Stock Screening Checklist' },
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
          <strong>Not financial advice.</strong> Market cap tiers and example screens are for educational purposes only. Stock selection requires individual research. Always conduct your own due diligence.
        </p>
      </div>

    </div>
  )
}
