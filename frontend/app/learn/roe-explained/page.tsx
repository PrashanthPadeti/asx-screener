import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, TrendingUp } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'ROE Explained: How Investors Use Return on Equity | ASX Screener',
  description:
    'What is Return on Equity (ROE), how to calculate it, what counts as a good ROE on the ASX, and how to use it alongside other metrics to find quality ASX stocks.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/roe-explained' },
}

const ASX_ROE_BENCHMARKS = [
  { sector: 'Financials (Banks)', typical: '10–15%', note: 'Big 4 banks target 10–13% ROE; higher means strong capital efficiency' },
  { sector: 'Materials (Miners)', typical: '10–30%+', note: 'Highly variable — commodity price dependent. Quality miners sustain >15%' },
  { sector: 'Consumer Discretionary', typical: '15–30%', note: 'Retailers like Wesfarmers often achieve high ROE through asset-light models' },
  { sector: 'Healthcare', typical: '15–25%', note: 'Strong IP and recurring revenue often support high ROE. CSL ~20–25%' },
  { sector: 'A-REITs', typical: '5–10%', note: 'Asset-heavy structure suppresses ROE; use NTA and FFO yield instead' },
  { sector: 'Technology', typical: '15–40%+', note: 'Asset-light SaaS businesses can achieve very high ROE once profitable' },
]

const DUPONT = [
  { component: 'Net Profit Margin', formula: 'Net Profit ÷ Revenue', what: 'How much profit the company keeps from each dollar of sales' },
  { component: 'Asset Turnover', formula: 'Revenue ÷ Total Assets', what: 'How efficiently the company uses its assets to generate sales' },
  { component: 'Financial Leverage', formula: 'Total Assets ÷ Shareholders\' Equity', what: 'How much debt is used to amplify returns (higher = more leverage)' },
]

export default function ROEExplainedPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema headline="ROE Explained: How Investors Use Return on Equity" description="What is Return on Equity (ROE), how to calculate it, what counts as a good ROE on the ASX, and how to use it alongside other metrics to find quality ASX stocks." url="https://asxscreener.com.au/learn/roe-explained" />
      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'ROE Explained', href: '/learn/roe-explained' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Intermediate</span>
          <span className="text-xs text-slate-400">9 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          ROE Explained: How Investors Use Return on Equity
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Return on Equity (ROE) measures how much profit a company generates for every dollar of shareholders&apos; money invested. It is one of the most widely used measures of business quality — and one of the first metrics Warren Buffett looks at when evaluating a company.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Stocks by ROE</p>
          <p className="text-blue-200 text-sm">Filter by ROE, Avg ROE 3Y, Avg ROE 5Y and combine with other quality metrics</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What is Return on Equity?</h2>
        <p className="text-slate-600 leading-relaxed mb-4">
          ROE is calculated as:
        </p>
        <div className="bg-slate-900 rounded-xl p-4 mb-4 text-center">
          <code className="text-emerald-300 font-mono text-sm">ROE = Net Profit ÷ Shareholders&apos; Equity × 100</code>
        </div>
        <p className="text-slate-600 leading-relaxed mb-3">
          If a company earns $20M in net profit and has $100M of shareholders&apos; equity on its balance sheet, its ROE is 20%.
        </p>
        <p className="text-slate-600 leading-relaxed">
          Shareholders&apos; equity is the money that belongs to shareholders — it&apos;s total assets minus total liabilities. ROE tells you how effectively management is turning that equity base into profit.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <TrendingUp className="w-4 h-4" /> Why ROE matters for investors
        </h2>
        <ul className="space-y-2 text-sm text-blue-900">
          {[
            'High ROE companies can often reinvest profits at high rates — compounding shareholder value over time.',
            'Sustained high ROE (above 15% for 5+ years) is a hallmark of competitively advantaged businesses.',
            'A company with high ROE but no debt is more impressive than one using high leverage to boost the number.',
            'Falling ROE over time can signal a business is losing its competitive edge or taking on more debt.',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <TrendingUp className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What is a good ROE on the ASX?</h2>
        <p className="text-slate-500 text-sm mb-4">As a general rule, ROE above 15% sustained over several years is considered good. But context matters — benchmarks vary significantly by sector:</p>
        <div className="space-y-2">
          {ASX_ROE_BENCHMARKS.map(({ sector, typical, note }) => (
            <div key={sector} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1">
                <p className="font-semibold text-slate-900 text-sm">{sector}</p>
                <span className="text-xs font-mono font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">{typical}</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{note}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">The DuPont breakdown: what drives ROE</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-4">
          ROE can be decomposed into three drivers (the DuPont framework). This tells you <em>why</em> ROE is high or low — which matters for quality assessment:
        </p>
        <div className="space-y-3">
          {DUPONT.map(({ component, formula, what }) => (
            <div key={component} className="bg-slate-50 border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
                <p className="font-semibold text-slate-900 text-sm">{component}</p>
                <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{formula}</code>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{what}</p>
            </div>
          ))}
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mt-4">
          <p className="text-sm text-amber-900 leading-relaxed">
            <strong>Watch out for leverage-inflated ROE.</strong> If a company achieves high ROE primarily through high financial leverage (lots of debt), the ROE is more fragile. Compare ROE with ROA (Return on Assets) — if ROA is much lower than ROE, debt is doing most of the work.
          </p>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Consistency matters more than a single number</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-4">
          A company that earns 20% ROE for one year but 5% the next has not demonstrated quality — it may have had a one-off event. What matters is <strong>sustained ROE over multiple years</strong>. ASX Screener shows Avg ROE 3Y and Avg ROE 5Y for exactly this reason.
        </p>
        <div className="bg-slate-900 rounded-xl p-4">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{`avg_roe_5y > 15     ← sustained quality over 5 years
roe > 15            ← current year only (can be a one-off)
avg_roe_3y > 15 AND debt_to_equity < 1  ← quality + low leverage`}</code>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">ROE vs. ROCE vs. ROIC — which should you use?</h2>
        <div className="space-y-3">
          {[
            { metric: 'ROE (Return on Equity)', when: 'Good starting point for most companies. Easy to find, widely reported.' },
            { metric: 'ROCE (Return on Capital Employed)', when: 'Better when comparing companies with different debt levels. Uses equity + debt in the denominator, so debt doesn\'t inflate it.' },
            { metric: 'ROIC (Return on Invested Capital)', when: 'Most rigorous. Uses net operating profit after tax vs. invested capital. Best for assessing true capital efficiency.' },
          ].map(({ metric, when }) => (
            <div key={metric} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-semibold text-slate-900 text-sm mb-1">{metric}</p>
              <p className="text-xs text-slate-500 leading-relaxed">{when}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example screens using ROE</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Quality compounders screen',
              filters: ['avg_roe_5y > 15', 'debt_to_equity < 0.5', 'revenue_growth_3y_cagr > 5', 'market_cap > 500'],
            },
            {
              name: 'High ROE dividend screen',
              filters: ['roe > 12', 'dividend_yield > 3', 'franking_pct = 100', 'payout_ratio < 80'],
            },
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
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained' },
            { href: '/learn/how-to-research-asx-stocks-dyor', label: 'How to Research ASX Stocks (DYOR)' },
            { href: '/glossary', label: 'ASX Investing Glossary' },
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
          <strong>Not financial advice.</strong> ROE and other financial metrics are tools for research — not guarantees of future performance. Always conduct your own research and consider seeking advice from a licensed financial adviser.
        </p>
      </div>

    </div>
  )
}
