import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, CheckCircle2, AlertTriangle, ChevronLeft, Zap, BookOpen, TrendingDown } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: 'ASX Dividend Research Checklist — Free | ASX Screener',
  description: 'A free checklist for researching ASX dividend stocks. Covers yield, franking credits, payout ratio, dividend history, sustainability checks, and yield trap warning signs.',
  alternates: { canonical: 'https://asxscreener.com.au/resources/dividend-research-checklist' },
}

const SECTIONS = [
  {
    title: 'Yield & Franking — The Headline Numbers',
    color: 'blue',
    items: [
      'I have noted the raw dividend yield (annual dividend ÷ current share price).',
      'I have calculated the grossed-up yield, including the value of franking credits.',
      'I know the franking percentage — fully franked (100%), partially franked, or unfranked.',
      'The raw yield is not abnormally high compared to peers — if it is, I have investigated why.',
      'I have compared the yield to: bank savings rate, sector average, and this stock\'s own history.',
    ],
  },
  {
    title: 'Dividend Sustainability',
    color: 'emerald',
    items: [
      'The payout ratio is below 80% of reported earnings (for most non-REIT businesses).',
      'Operating cash flow is positive — the dividend is funded by real cash generation, not debt.',
      'Earnings have been stable or growing over the past 3 years.',
      'The company has not needed to raise equity capital repeatedly to fund dividends.',
      'The dividend has not been cut in the past 5 years (or I understand why it was and the situation has changed).',
    ],
  },
  {
    title: 'Dividend History',
    color: 'purple',
    items: [
      'I have checked the dividend payment history for the past 5–10 years.',
      'The dividend has grown or remained stable — it has not been declining.',
      'There are no gaps or skipped payments (except during COVID or one-off extraordinary circumstances).',
      'The dividend is paid at least annually — semi-annual is common on the ASX.',
      'Special dividends are excluded from my yield calculation (they are non-recurring).',
    ],
  },
  {
    title: 'Business Quality — Behind the Yield',
    color: 'amber',
    items: [
      'I understand the business model and how it generates the cash to pay dividends.',
      'The business has a competitive advantage that protects its revenue and margins.',
      'Debt levels are manageable — high debt can force dividend cuts in downturns.',
      'Management has been consistent in its dividend commitment and communication.',
      'The sector is not in secular decline (e.g. a legacy business being disrupted).',
    ],
  },
  {
    title: 'Yield Trap Warning Signs — Check These',
    color: 'rose',
    items: [
      'The yield is not elevated primarily because the share price has fallen sharply.',
      'There are no analyst consensus downgrades on the dividend in recent research.',
      'The payout ratio has not been rising steeply year on year.',
      'Cash conversion ratio is healthy — accounting profit is translating to real cash.',
      'The company is not borrowing to pay dividends (net debt rising while dividends hold).',
    ],
  },
]

const COLOR_MAP: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  blue:    { bg: 'bg-blue-50',    text: 'text-blue-800',    border: 'border-blue-200',    dot: 'bg-blue-500' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-800', border: 'border-emerald-200', dot: 'bg-emerald-500' },
  purple:  { bg: 'bg-purple-50',  text: 'text-purple-800',  border: 'border-purple-200',  dot: 'bg-purple-500' },
  amber:   { bg: 'bg-amber-50',   text: 'text-amber-800',   border: 'border-amber-200',   dot: 'bg-amber-500' },
  rose:    { bg: 'bg-rose-50',    text: 'text-rose-800',    border: 'border-rose-200',    dot: 'bg-rose-500' },
}

export default function DividendResearchChecklistPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Resources', href: '/resources' }, { label: 'Dividend Research Checklist', href: '/resources/dividend-research-checklist' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Checklist</span>
          <span className="text-xs text-slate-400">5 min read · Free to print</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          ASX Dividend Research Checklist
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          A high yield looks attractive on the surface — but sustainable income investing requires going deeper. Use this checklist before adding any dividend stock to your portfolio.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Key principle
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed">
          A dividend is only as reliable as the cash flow that funds it. The yield is the reward; the checklist is how you assess whether the reward is real. Every item in the Sustainability and Business Quality sections matters more than the yield number itself.
        </p>
      </div>

      <div className="space-y-5">
        {SECTIONS.map(({ title, color, items }) => {
          const c = COLOR_MAP[color]
          return (
            <div key={title} className={`${c.bg} border ${c.border} rounded-2xl p-6`}>
              <h2 className={`font-bold ${c.text} mb-4 flex items-center gap-2`}>
                {color === 'rose'
                  ? <TrendingDown className="w-4 h-4 shrink-0" />
                  : <CheckCircle2 className="w-4 h-4 shrink-0" />
                }
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

      <div className="bg-slate-900 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide mb-4">Quick Reference — Key Metrics to Check</h2>
        <div className="grid sm:grid-cols-2 gap-3">
          {[
            { metric: 'Dividend Yield', target: '> 3.5% for income focus' },
            { metric: 'Grossed-Up Yield', target: '> 5% including franking credits' },
            { metric: 'Franking %', target: '100% preferred; 70%+ acceptable' },
            { metric: 'Payout Ratio', target: '< 80% of earnings for non-REITs' },
            { metric: 'Debt / Equity', target: '< 1.0 for non-financials' },
            { metric: 'Dividend CAGR 3Y', target: 'Positive — growing distributions' },
          ].map(({ metric, target }) => (
            <div key={metric} className="bg-slate-800 rounded-xl p-3">
              <p className="text-xs font-bold text-slate-300">{metric}</p>
              <p className="text-xs text-emerald-400 mt-0.5">{target}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related Resources
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained for ASX Investors' },
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained' },
            { href: '/resources/asx-stock-screening-checklist', label: 'ASX Stock Screening Checklist' },
            { href: '/screener/asx-dividend-yield', label: 'Screen for ASX Dividend Stocks' },
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
          <strong>Not financial advice.</strong> This checklist is for educational purposes only. Past dividend payments do not guarantee future payments. Always conduct your own research and consider advice from a licensed financial adviser.
        </p>
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Screen for ASX income stocks</h2>
        <p className="text-blue-100 mb-5 text-sm">Filter by dividend yield, grossed-up yield, franking %, payout ratio, and 80+ more metrics.</p>
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
