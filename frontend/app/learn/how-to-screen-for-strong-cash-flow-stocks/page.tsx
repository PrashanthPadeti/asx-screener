import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, TrendingUp } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How to Screen for Strong Cash Flow ASX Stocks | ASX Screener',
  description:
    'Why free cash flow matters more than earnings, and how to screen ASX stocks for strong FCF generation, high cash conversion, and sustainable capital allocation.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-screen-for-strong-cash-flow-stocks' },
}

const CASH_METRICS = [
  { metric: 'Free Cash Flow (FCF)', key: 'free_cash_flow', what: 'Operating cash flow minus capital expenditure. The actual cash the business generates after maintaining and investing in its assets. This is the most honest measure of what a company can return to shareholders.' },
  { metric: 'FCF Margin %', key: 'fcf_margin', what: 'Free cash flow as a percentage of revenue. A high FCF margin (15%+) indicates a business that turns revenue efficiently into cash — typically a sign of pricing power and low capital intensity.' },
  { metric: 'FCF / Net Income (Cash Conversion)', key: 'fcf_conversion', what: 'How much of reported net profit converts to actual free cash flow. Above 80% is good; above 100% means the business is generating more cash than its accounting profit suggests. Below 60% warrants investigation.' },
  { metric: 'Operating Cash Flow Positive', key: 'ocf_positive', what: 'Boolean: is operating cash flow positive? A basic filter to exclude companies that are burning cash from operations — useful for removing pre-revenue or structurally cash-negative businesses.' },
  { metric: 'FCF Yield %', key: 'fcf_yield', what: 'Free cash flow divided by market cap. Comparable to earnings yield but using actual cash. An FCF yield above 5% on a quality business is often considered attractive — it represents the cash return you are theoretically receiving on your investment.' },
  { metric: 'Capex as % of Revenue', key: 'capex_pct_revenue', what: 'Capital expenditure as a percentage of revenue. Lower is better for capital-light businesses — it means more of each revenue dollar flows through to free cash flow. Asset-heavy businesses (miners, utilities) have unavoidably high capex.' },
]

export default function StrongCashFlowStocksPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="How to Screen for Strong Cash Flow ASX Stocks"
        description="Why free cash flow matters more than earnings, and how to screen ASX stocks for strong FCF generation, high cash conversion, and sustainable capital allocation."
        url="https://asxscreener.com.au/learn/how-to-screen-for-strong-cash-flow-stocks"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'How to Screen for Strong Cash Flow Stocks', href: '/learn/how-to-screen-for-strong-cash-flow-stocks' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Intermediate</span>
          <span className="text-xs text-slate-400">9 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Screen for Strong Cash Flow ASX Stocks
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Earnings can be manipulated through accounting choices. Cash flow cannot. Free cash flow — the actual cash a business generates after investing in its operations — is one of the most reliable indicators of business quality and the ability to pay dividends, buy back shares, or invest in growth without borrowing.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-cyan-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-cyan-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Stocks by Free Cash Flow</p>
          <p className="text-blue-200 text-sm">Filter by FCF margin, FCF yield, cash conversion, capex and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Earnings vs. free cash flow — why it matters</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Reported earnings (net profit) include non-cash items — depreciation, amortisation, share-based compensation, deferred revenue, and accruals. These are legitimate accounting entries, but they mean that a company can report strong profits while generating little or no actual cash.
        </p>
        <div className="bg-slate-900 rounded-xl p-4 mb-3">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{`Free Cash Flow = Operating Cash Flow − Capital Expenditure

High-quality FCF business:
  Net profit:           $100M
  Operating cash flow:  $120M   ← more cash than profit
  Capex:               − $20M
  Free cash flow:       $100M   ← matches profit (100% conversion)

Weak FCF business:
  Net profit:           $100M
  Operating cash flow:   $60M   ← much less cash than profit
  Capex:               − $40M
  Free cash flow:        $20M   ← only 20% conversion (investigate why)`}</code>
        </div>
        <p className="text-slate-600 leading-relaxed text-sm">
          The second company has the same reported profit but is actually 5× less cash-generative. It has less capacity to pay dividends, reduce debt, or invest without raising capital.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-slate-500" />
          Key cash flow metrics for ASX screening
        </h2>
        <div className="space-y-3">
          {CASH_METRICS.map(({ metric, key, what }) => (
            <div key={key} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
                <p className="font-semibold text-slate-900 text-sm">{metric}</p>
                <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{key}</code>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{what}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Cash flow screens</h2>
        <div className="space-y-4">
          {[
            {
              name: 'High FCF quality screen',
              desc: 'Strong free cash flow conversion with high margins and low debt — the hallmarks of a capital-light, high-quality business.',
              filters: ['fcf_margin > 15', 'fcf_conversion > 0.8', 'ocf_positive = true', 'net_debt_to_ebitda < 1.5', 'market_cap > 300'],
            },
            {
              name: 'FCF yield screen',
              desc: 'Stocks offering attractive FCF yield — cash being generated relative to market price.',
              filters: ['fcf_yield > 5', 'ocf_positive = true', 'piotroski_f_score >= 6', 'market_cap > 200'],
            },
            {
              name: 'Cash flow + dividend reliability',
              desc: 'Companies with strong FCF cover over their dividend — sustainable income backed by real cash.',
              filters: ['ocf_positive = true', 'fcf_payout_ratio < 70', 'dividend_yield > 3', 'fcf_margin > 10', 'market_cap > 500'],
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
        <h2 className="text-xl font-bold text-slate-900 mb-3">Low FCF warning signs</h2>
        <div className="space-y-2">
          {[
            { sign: 'Net profit rising but FCF flat or falling', why: 'Earnings may be boosted by revenue recognition changes, lower provisions, or capitalised costs. The cash tells the real story.' },
            { sign: 'Capex consistently above depreciation', why: 'Maintenance capex (keeping assets running) should roughly equal depreciation. Structural capex above this level signals an asset-intensive business with limited FCF headroom.' },
            { sign: 'Working capital growing faster than revenue', why: 'Rising receivables or inventory absorbs cash. A company can grow revenue while generating less and less cash if it\'s extending credit terms or accumulating stock.' },
            { sign: 'Dividends funded by debt rather than FCF', why: 'If total dividends paid exceed FCF in multiple consecutive years, the company is borrowing to pay shareholders — unsustainable.' },
          ].map(({ sign, why }) => (
            <div key={sign} className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="font-semibold text-amber-900 text-sm mb-1">{sign}</p>
              <p className="text-xs text-amber-700 leading-relaxed">{why}</p>
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
            { href: '/learn/how-to-find-quality-asx-companies', label: 'How to Find Quality ASX Companies' },
            { href: '/learn/roic-explained', label: 'ROIC Explained: Return on Invested Capital' },
            { href: '/learn/how-to-check-asx-dividend-sustainability', label: 'How to Check If an ASX Dividend Is Sustainable' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> Cash flow metrics are research tools only. Always conduct your own research before making investment decisions.</p>
      </div>
    </div>
  )
}
