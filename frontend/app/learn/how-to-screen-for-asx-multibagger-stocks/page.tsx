import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, TrendingUp, Search } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How to Screen for ASX Multibagger Stocks | ASX Screener',
  description:
    'The key metrics for identifying multibagger candidates on the ASX — growth, ROIC, cash flow, reinvestment, and valuation — with 8 practical screen examples.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-screen-for-asx-multibagger-stocks' },
}

const METRIC_GROUPS = [
  {
    group: 'Growth Metrics',
    color: 'blue',
    desc: 'Growth is the fuel. A company cannot become a multibagger if the business is not growing over time.',
    metrics: [
      { name: 'Revenue CAGR (5Y / 10Y)', field: 'revenue_cagr_5y', target: '> 10% per year', why: 'Shows whether the company is consistently expanding its business. One lucky year is not enough — look for sustained growth across 5 or 10 years.' },
      { name: 'EPS Growth (5Y / 10Y)', field: 'eps_cagr_5y', target: '> 15% per year', why: 'Profit per share must grow for the stock to compound long-term. EPS growth above revenue growth indicates improving margins — a quality signal.' },
    ],
  },
  {
    group: 'Quality & Efficiency Metrics',
    color: 'purple',
    desc: 'Growth alone is not enough. Quality determines whether growth creates or destroys shareholder value.',
    metrics: [
      { name: 'ROIC (5Y / 10Y Average)', field: 'avg_roic_5y', target: '> 15%', why: 'The most important multibagger metric. A company with sustained ROIC above 15% earns more than its cost of capital — it creates value. A company with ROIC below its cost of capital destroys value even while growing.' },
      { name: 'ROCE (5Y Average)', field: 'avg_roce_5y', target: '> 15%', why: 'Similar to ROIC. Measures how efficiently the business converts its capital base into profit. Consistently high ROCE over 5+ years signals a durable competitive advantage.' },
      { name: 'Cash Conversion Ratio', field: 'fcf_conversion', target: '> 80%', why: 'Confirms that reported profits are becoming real cash. Companies with poor cash conversion can report growing profits while actually becoming less financially healthy.' },
      { name: 'Operating Margin (5Y)', field: 'avg_operating_margin_5y', target: '> 10%', why: 'Stable or improving margins over time show pricing power and operational discipline. Compressing margins while growing revenue is an early warning sign.' },
    ],
  },
  {
    group: 'Reinvestment & Financial Strength',
    color: 'emerald',
    desc: 'Multibaggers compound because they reinvest profits at high rates of return — for years.',
    metrics: [
      { name: 'Payout Ratio', field: 'payout_ratio', target: '< 25–30%', why: 'A low payout ratio means the company retains most of its earnings to reinvest for growth. When combined with high ROIC, this creates a compounding engine.' },
      { name: 'Interest Coverage', field: 'interest_coverage', target: '> 10×', why: 'The company can comfortably pay its debt costs. Strong interest coverage means debt is not a constraint on growth investment — and the balance sheet can survive a bad year.' },
      { name: 'Free Cash Flow', field: 'ocf_positive', target: 'Positive FCF', why: 'Positive free cash flow confirms the business generates more cash than it consumes. Negative FCF companies must constantly raise capital — diluting shareholders and adding risk.' },
    ],
  },
  {
    group: 'Valuation',
    color: 'amber',
    desc: 'Even the best business can be a poor investment if bought at too high a price.',
    metrics: [
      { name: 'P/E Ratio', field: 'pe_ratio', target: '< 30', why: 'Prevents paying an extreme premium for expected growth. For quality growth companies, a higher P/E may sometimes be justified — but extreme multiples leave little room for error.' },
      { name: 'PEG Ratio', field: 'peg_ratio', target: '< 1.0–1.5', why: 'P/E divided by earnings growth rate. A company growing at 20% with a P/E of 20 (PEG = 1.0) is usually more attractive than one growing at 5% with a P/E of 30 (PEG = 6.0).' },
    ],
  },
]

const SCREENS = [
  { name: 'Quality Growth Screen', desc: 'Strong growth combined with ROE/ROCE quality and manageable debt. Starting point for most multibagger searches.', filters: ['revenue_cagr_5y > 10', 'eps_cagr_5y > 10', 'avg_roe_5y > 15', 'avg_roce_5y > 15', 'avg_operating_margin_5y > 10', 'debt_to_equity < 0.5'] },
  { name: 'Long-Term Compounder Screen', desc: 'Sustained 10-year growth with high ROIC and positive FCF — for investors seeking durable businesses.', filters: ['revenue_cagr_10y > 10', 'eps_cagr_10y > 10', 'avg_roic_5y > 15', 'ocf_positive = true', 'market_cap > 1000'] },
  { name: 'High ROIC Reinvestment Screen', desc: 'Companies earning high returns and reinvesting most of their cash — the compounding engine profile.', filters: ['avg_roic_5y > 15', 'revenue_cagr_5y > 10', 'payout_ratio < 30', 'fcf_growth_5y > 10', 'ocf_positive = true'] },
  { name: 'Growth at Reasonable Price (GARP)', desc: 'Growing companies that may not yet be overpriced — avoids paying extreme multiples for growth.', filters: ['eps_cagr_5y > 10', 'revenue_cagr_5y > 10', 'avg_roe_5y > 10', 'pe_ratio < 25', 'peg_ratio < 1.5'] },
  { name: 'Cash Flow Quality Screen', desc: 'Earnings backed by real cash — rules out companies with accounting profits but weak cash generation.', filters: ['ocf_positive = true', 'fcf_yield > 3', 'fcf_conversion > 0.8', 'avg_roe_5y > 10', 'debt_to_equity < 0.5'] },
  { name: 'Profitable Small-Cap Growth Screen', desc: 'Smaller companies already growing and profitable — higher risk, higher potential. Always check liquidity.', filters: ['market_cap < 1000', 'revenue_cagr_5y > 15', 'eps_cagr_5y > 15', 'roe > 10', 'debt_to_equity < 0.5'] },
  { name: 'Margin Expansion Screen', desc: 'Revenue growing AND margins improving — a powerful combination that accelerates profit growth.', filters: ['revenue_cagr_5y > 10', 'avg_operating_margin_5y > 10', 'avg_roe_5y > 10', 'ocf_positive = true'] },
  { name: 'Market Leader Compounder', desc: 'Large, established companies still growing strongly and earning high returns — lower risk profile.', filters: ['market_cap > 5000', 'revenue_cagr_5y > 8', 'avg_roe_5y > 15', 'avg_roce_5y > 15', 'debt_to_equity < 0.5', 'ocf_positive = true'] },
]

const COLOR_MAP: Record<string, string> = {
  blue: 'bg-blue-50 border-blue-200 text-blue-700',
  purple: 'bg-purple-50 border-purple-200 text-purple-700',
  emerald: 'bg-emerald-50 border-emerald-200 text-emerald-700',
  amber: 'bg-amber-50 border-amber-200 text-amber-700',
}

export default function ScreenForMultibaggersPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="How to Screen for ASX Multibagger Stocks"
        description="The key metrics for identifying multibagger candidates on the ASX — growth, ROIC, cash flow, reinvestment, and valuation — with 8 practical screen examples."
        url="https://asxscreener.com.au/learn/how-to-screen-for-asx-multibagger-stocks"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'How to Screen for ASX Multibagger Stocks', href: '/learn/how-to-screen-for-asx-multibagger-stocks' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Intermediate</span>
          <span className="text-xs text-slate-400">12 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Screen for ASX Multibagger Stocks
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          A stock screener cannot guarantee a multibagger — but it can systematically surface companies with the growth, quality, and financial profile that multibaggers typically share before the market recognises them. This guide walks through the key metrics and gives you 8 ready-to-use screens for different multibagger strategies.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen for Multibagger Candidates</p>
          <p className="text-blue-200 text-sm">ROIC, revenue CAGR, EPS growth, FCF, PEG ratio — all available as filters</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-5 flex items-center gap-2">
          <Search className="w-5 h-5 text-slate-500" /> The key metrics
        </h2>
        <div className="space-y-6">
          {METRIC_GROUPS.map(({ group, color, desc, metrics }) => (
            <div key={group}>
              <div className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border mb-3 ${COLOR_MAP[color]}`}>
                {group}
              </div>
              <p className="text-slate-500 text-xs mb-3">{desc}</p>
              <div className="space-y-2">
                {metrics.map(({ name, field, target, why }) => (
                  <div key={field} className="bg-white border border-slate-200 rounded-xl p-4">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <p className="font-semibold text-slate-900 text-sm">{name}</p>
                      <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{field}</code>
                      <span className="text-xs font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">{target}</span>
                    </div>
                    <p className="text-xs text-slate-500 leading-relaxed">{why}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-slate-500" /> 8 multibagger screen examples
        </h2>
        <div className="space-y-4">
          {SCREENS.map(({ name, desc, filters }) => (
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
        <h2 className="text-xl font-bold text-slate-900 mb-4">After the screen: qualitative checks</h2>
        <p className="text-slate-600 leading-relaxed text-sm mb-3">A screener finds candidates. It cannot judge these questions — which separate genuine multibaggers from companies that merely look like them:</p>
        <div className="grid sm:grid-cols-2 gap-3">
          {[
            { q: 'Business quality', items: ['What does the company do?', 'Why do customers choose it?', 'Is the product/service still needed in 10 years?'] },
            { q: 'Competitive advantage', items: ['Does it have a strong brand or pricing power?', 'Network effects or switching costs?', 'Hard for competitors to copy?'] },
            { q: 'Management quality', items: ['Is management honest and capable?', 'Do they communicate clearly?', 'Are insiders aligned with shareholders?'] },
            { q: 'Growth runway', items: ['Can the company keep growing for many years?', 'Is the market opportunity large?', 'Is growth slowing or accelerating?'] },
          ].map(({ q, items }) => (
            <div key={q} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-semibold text-slate-900 text-sm mb-2">{q}</p>
              <ul className="space-y-1">
                {items.map(item => (
                  <li key={item} className="flex items-start gap-1.5 text-xs text-slate-500">
                    <span className="text-slate-300 shrink-0">→</span>{item}
                  </li>
                ))}
              </ul>
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
            { href: '/learn/what-is-a-multibagger-stock', label: 'What Is a Multibagger Stock?' },
            { href: '/learn/lessons-from-successful-multibagger-investors', label: 'Lessons from the World\'s Best Multibagger Investors' },
            { href: '/learn/roic-explained', label: 'ROIC Explained: Return on Invested Capital' },
            { href: '/learn/how-to-find-quality-asx-companies', label: 'How to Find Quality ASX Companies' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> These screens are research starting points only. A stock passing all filters is not guaranteed to be a multibagger — it is only worth researching in depth. All investing involves risk of loss.</p>
      </div>
    </div>
  )
}
