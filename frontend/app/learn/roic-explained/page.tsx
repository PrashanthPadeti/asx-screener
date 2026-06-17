import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, TrendingUp } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'ROIC Explained: Return on Invested Capital for ASX Investors | ASX Screener',
  description:
    'What is Return on Invested Capital (ROIC), how to calculate it, why it beats ROE for comparing companies, and how to screen for high-ROIC ASX stocks.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/roic-explained' },
}

const ROIC_VS_ROE = [
  { metric: 'ROE', formula: 'Net Profit ÷ Shareholders\' Equity', weakness: 'Inflated by debt — a company can boost ROE simply by borrowing more, making it look more efficient than it is.' },
  { metric: 'ROCE', formula: 'EBIT ÷ Capital Employed', weakness: 'Better than ROE but uses EBIT (pre-tax), which can include non-operating items. Capital Employed definition varies.' },
  { metric: 'ROIC', formula: 'NOPAT ÷ Invested Capital', weakness: 'Most accurate. Uses after-tax operating profit vs. the actual capital deployed in the business. Excludes excess cash and non-operating assets.' },
]

const BENCHMARKS = [
  { sector: 'Consumer Staples', typical: '15–25%', note: 'Strong brands and pricing power often deliver consistent high ROIC (e.g. Woolworths, Coles)' },
  { sector: 'Technology / SaaS', typical: '20–50%+', note: 'Asset-light models with recurring revenue can sustain very high ROIC once at scale' },
  { sector: 'Healthcare', typical: '15–30%', note: 'IP moats and high switching costs support above-average ROIC. CSL is a benchmark example.' },
  { sector: 'Materials (Miners)', typical: '5–20%', note: 'Highly capital-intensive and commodity-price dependent. High ROIC in boom years, low in busts.' },
  { sector: 'Industrials', typical: '10–20%', note: 'Varies significantly. Asset-heavy businesses tend toward the lower end of the range.' },
  { sector: 'A-REITs', typical: '4–8%', note: 'Real estate is inherently capital-intensive. ROIC is less useful here — use FFO yield and NTA instead.' },
]

export default function ROICExplainedPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema headline="ROIC Explained: Return on Invested Capital for ASX Investors" description="What is Return on Invested Capital (ROIC), how to calculate it, why it beats ROE for comparing companies, and how to screen for high-ROIC ASX stocks." url="https://asxscreener.com.au/learn/roic-explained" />
      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'ROIC Explained', href: '/learn/roic-explained' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">Intermediate</span>
          <span className="text-xs text-slate-400">9 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          ROIC Explained: Return on Invested Capital for ASX Investors
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Return on Invested Capital (ROIC) is widely considered the most rigorous measure of business quality. It tells you how much profit a company generates for every dollar of capital actually deployed in its operations — stripping out the distortions that debt creates in simpler metrics like ROE.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Stocks by ROIC</p>
          <p className="text-blue-200 text-sm">Filter by ROIC, Avg ROIC 3Y, Avg ROIC 5Y and combine with other quality metrics</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What is ROIC?</h2>
        <p className="text-slate-600 leading-relaxed mb-4">
          ROIC measures the return a company generates on all the capital invested in its core business operations:
        </p>
        <div className="bg-slate-900 rounded-xl p-4 mb-4 text-center">
          <code className="text-emerald-300 font-mono text-sm">ROIC = NOPAT ÷ Invested Capital × 100</code>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
            <p className="font-semibold text-slate-900 text-sm mb-2">NOPAT</p>
            <p className="text-xs text-slate-500 leading-relaxed">Net Operating Profit After Tax — the profit from core operations after tax, excluding interest income/expense and non-operating items.</p>
            <code className="text-xs text-blue-600 bg-blue-50 rounded px-2 py-1 block mt-2 font-mono">EBIT × (1 − tax rate)</code>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
            <p className="font-semibold text-slate-900 text-sm mb-2">Invested Capital</p>
            <p className="text-xs text-slate-500 leading-relaxed">The total capital deployed in the business: equity + debt − excess cash − non-operating assets. Represents money actually working in the business.</p>
            <code className="text-xs text-blue-600 bg-blue-50 rounded px-2 py-1 block mt-2 font-mono">Equity + Net Debt</code>
          </div>
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <TrendingUp className="w-4 h-4" /> Why ROIC matters: the WACC test
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed mb-3">
          Every company has a cost of capital — the return it needs to deliver to satisfy its debt holders and equity investors. This is called WACC (Weighted Average Cost of Capital), typically 8–12% for ASX companies.
        </p>
        <ul className="space-y-2 text-sm text-blue-900">
          <li className="flex items-start gap-2">
            <span className="text-emerald-500 font-bold shrink-0">✓</span>
            <span><strong>ROIC &gt; WACC:</strong> The company is creating value — earning more than its cost of capital. The excess return compounds into shareholder wealth over time.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-red-500 font-bold shrink-0">✗</span>
            <span><strong>ROIC &lt; WACC:</strong> The company is destroying value — even if it&apos;s profitable on paper. Growth in a value-destroying business makes things worse.</span>
          </li>
        </ul>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">ROIC vs ROE vs ROCE — which to use?</h2>
        <div className="space-y-3">
          {ROIC_VS_ROE.map(({ metric, formula, weakness }) => (
            <div key={metric} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <p className="font-bold text-slate-900">{metric}</p>
                <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{formula}</code>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{weakness}</p>
            </div>
          ))}
        </div>
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mt-4">
          <p className="text-sm text-emerald-900 leading-relaxed">
            <strong>Use ROIC when you want the most honest picture.</strong> Two companies can have identical ROE but very different ROIC if one is using far more debt. ROIC puts them on a level playing field.
          </p>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What is a good ROIC on the ASX?</h2>
        <p className="text-slate-500 text-sm mb-4">As a rule of thumb, ROIC consistently above 15% indicates a business with a genuine competitive advantage. Context varies by sector:</p>
        <div className="space-y-2">
          {BENCHMARKS.map(({ sector, typical, note }) => (
            <div key={sector} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
                <p className="font-semibold text-slate-900 text-sm">{sector}</p>
                <span className="text-xs font-mono font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">{typical}</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{note}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Consistency is the signal</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-4">
          A single year of high ROIC can be a one-off — a favourable commodity cycle, an asset sale, or a non-recurring contract. What separates a great business from a good one is <strong>sustained ROIC above cost of capital for 5–10+ years</strong>. That kind of consistency usually points to a real competitive advantage: a brand, a switching cost, a network effect, or a cost structure rivals can&apos;t match.
        </p>
        <p className="text-slate-600 text-sm leading-relaxed">
          ASX Screener shows Avg ROIC 3Y and Avg ROIC 5Y alongside the current figure, so you can assess the trend rather than relying on a single data point.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example screens using ROIC</h2>
        <div className="space-y-4">
          {[
            {
              name: 'High-ROIC quality compounders',
              filters: ['avg_roic_5y > 15', 'avg_roe_5y > 15', 'debt_to_equity < 0.5', 'revenue_growth_3y_cagr > 5', 'market_cap > 500'],
            },
            {
              name: 'ROIC above WACC with growth',
              filters: ['roic > 12', 'revenue_growth_3y_cagr > 8', 'earnings_growth_3y_cagr > 8', 'piotroski_f_score >= 7'],
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
            { href: '/learn/roe-explained', label: 'ROE Explained: How Investors Use Return on Equity' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
            { href: '/learn/how-to-research-asx-stocks-dyor', label: 'How to Research ASX Stocks (DYOR)' },
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
          <strong>Not financial advice.</strong> ROIC and related metrics are research tools only. Always conduct your own research and consider advice from a licensed financial adviser before making investment decisions.
        </p>
      </div>

    </div>
  )
}
