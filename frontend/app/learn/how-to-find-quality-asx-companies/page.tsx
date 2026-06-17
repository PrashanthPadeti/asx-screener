import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, Shield, TrendingUp } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How to Find Quality ASX Companies | ASX Screener',
  description:
    'What makes a quality ASX company — and how to screen for it. Covers ROIC, margins, earnings consistency, balance sheet strength, and composite quality scores.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-find-quality-asx-companies' },
}

const QUALITY_PILLARS = [
  {
    pillar: 'High and sustained ROIC',
    icon: '①',
    detail: 'Return on Invested Capital consistently above 15% over 5+ years is the strongest single signal of a quality business. It means the company earns more from every dollar deployed than its cost of capital — creating rather than destroying shareholder value.',
    screen: 'avg_roic_5y > 15',
  },
  {
    pillar: 'Expanding or stable gross margins',
    icon: '②',
    detail: 'High gross margins (40%+) indicate pricing power — the ability to raise prices without losing customers. Stable or expanding margins over time show the competitive advantage is holding. Compressing margins are a warning sign.',
    screen: 'gross_margin > 40',
  },
  {
    pillar: 'Consistent earnings growth',
    icon: '③',
    detail: 'Quality businesses grow earnings predictably over multi-year periods. Look for EPS CAGR 5Y above 10% and year-over-year EPS growth that is rarely negative. Erratic earnings suggest low pricing power or high cyclicality.',
    screen: 'eps_cagr_5y > 10',
  },
  {
    pillar: 'Strong free cash flow conversion',
    icon: '④',
    detail: 'A quality business converts most of its reported profit into actual cash. FCF / Net Income > 80% means earnings are real, not accounting artefacts. Companies with low cash conversion often have aggressive revenue recognition or high maintenance capex.',
    screen: 'fcf_conversion > 0.8',
  },
  {
    pillar: 'Conservative balance sheet',
    icon: '⑤',
    detail: 'Debt amplifies both gains and losses. Quality companies either carry minimal debt or generate enough cash flow to service it comfortably. Net Debt/EBITDA below 1.5× is ideal. A strong balance sheet gives management options in a downturn.',
    screen: 'net_debt_to_ebitda < 1.5',
  },
  {
    pillar: 'High Piotroski F-Score',
    icon: '⑥',
    detail: 'The Piotroski F-Score combines 9 signals across profitability, leverage, and operating efficiency into a single 0–9 score. Scores of 7–9 indicate improving financial health across multiple dimensions simultaneously — a composite quality signal.',
    screen: 'piotroski_f_score >= 7',
  },
]

export default function HowToFindQualityASXCompaniesPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="How to Find Quality ASX Companies"
        description="What makes a quality ASX company — and how to screen for it. Covers ROIC, margins, earnings consistency, balance sheet strength, and composite quality scores."
        url="https://asxscreener.com.au/learn/how-to-find-quality-asx-companies"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'How to Find Quality ASX Companies', href: '/learn/how-to-find-quality-asx-companies' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">Intermediate</span>
          <span className="text-xs text-slate-400">10 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Find Quality ASX Companies
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          &quot;Quality investing&quot; means focusing on businesses with durable competitive advantages, predictable earnings, strong cash generation, and conservative balance sheets — then holding them long enough for compounding to work. This guide explains how to identify these characteristics using metrics available in the ASX Screener.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-purple-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen for Quality ASX Companies</p>
          <p className="text-purple-200 text-sm">Filter by ROIC, gross margin, F-Score, EPS CAGR, FCF conversion and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What is a &quot;quality&quot; company?</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          A quality company is one that generates returns on capital consistently above its cost of capital — and can sustain that for years, ideally decades. This usually requires a genuine competitive advantage: a brand, a switching cost, a network effect, or a cost structure rivals cannot easily match.
        </p>
        <p className="text-slate-600 leading-relaxed">
          Quality is not the same as &quot;large cap&quot; or &quot;safe&quot;. A large company can have mediocre returns on capital. A mid-cap with a dominant position in a niche can be very high quality. The metrics below help you distinguish between the two.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Shield className="w-5 h-5 text-slate-500" />
          Six pillars of quality — and how to screen for each
        </h2>
        <div className="space-y-4">
          {QUALITY_PILLARS.map(({ pillar, icon, detail, screen }) => (
            <div key={pillar} className="bg-white border border-slate-200 rounded-2xl p-5">
              <div className="flex items-start gap-3 mb-2">
                <span className="text-xl shrink-0">{icon}</span>
                <div className="flex-1">
                  <p className="font-bold text-slate-900">{pillar}</p>
                  <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{screen}</code>
                </div>
              </div>
              <p className="text-sm text-slate-500 leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <TrendingUp className="w-4 h-4" /> The compounding effect of quality
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed mb-3">
          A business with 20% ROIC that reinvests all its earnings grows intrinsic value at 20% per year. Over 10 years, $1 of invested capital becomes ~$6.19. A business with 8% ROIC grows to only ~$2.16. The quality premium compounds dramatically over time — which is why patient investors who hold quality businesses through short-term volatility tend to do well.
        </p>
        <p className="text-sm text-blue-900 leading-relaxed">
          This also explains why quality companies often trade at premium P/E multiples. The market is (correctly) pricing in the higher future value being generated by superior reinvestment rates.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Quality screens</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Quality compounder screen',
              desc: 'Strong multi-year ROIC and earnings growth with a conservative balance sheet.',
              filters: ['avg_roic_5y > 15', 'eps_cagr_5y > 10', 'gross_margin > 40', 'net_debt_to_ebitda < 1.5', 'piotroski_f_score >= 7', 'market_cap > 500'],
            },
            {
              name: 'High-quality dividend grower',
              desc: 'Quality fundamentals combined with a growing dividend — the best of both worlds.',
              filters: ['avg_roic_5y > 12', 'dividend_growth_3y > 5', 'payout_ratio < 65', 'gross_margin > 35', 'debt_to_equity < 0.5'],
            },
            {
              name: 'Improving quality screen',
              desc: 'Companies where quality metrics are trending upward — potential re-rating candidates.',
              filters: ['piotroski_f_score >= 7', 'roic > 10', 'eps_growth_1y > 10', 'revenue_growth_accelerating = true', 'market_cap > 200'],
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
        <h2 className="text-xl font-bold text-slate-900 mb-3">Quality vs. valuation</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-3">
          Quality and valuation are different things. A quality company at an extremely high price can still be a poor investment — and a low-quality company at a low price can outperform short-term. The goal is to find quality companies at <em>reasonable</em> prices.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Quality at fair value', desc: 'The sweet spot. Buy and hold as compounding works over time.', color: 'emerald' },
            { label: 'Quality at high price', desc: 'May underperform short-term. Wait for a pullback or pay up for exceptional businesses.', color: 'amber' },
            { label: 'Low quality at low price', desc: 'Value trap risk. Cheap for a reason — the business may keep deteriorating.', color: 'amber' },
            { label: 'Low quality at high price', desc: 'Avoid. No margin of safety and no quality to fall back on.', color: 'red' },
          ].map(({ label, desc, color }) => (
            <div key={label} className={`bg-${color}-50 border border-${color}-200 rounded-xl p-3`}>
              <p className={`text-xs font-bold text-${color}-900 mb-1`}>{label}</p>
              <p className={`text-xs text-${color}-700 leading-relaxed`}>{desc}</p>
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
            { href: '/learn/roic-explained', label: 'ROIC Explained: Return on Invested Capital' },
            { href: '/learn/roe-explained', label: 'ROE Explained: Return on Equity' },
            { href: '/learn/how-to-find-asx-growth-stocks', label: 'How to Find ASX Growth Stocks' },
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> Quality metrics are research tools only. Past performance of quality metrics does not guarantee future returns. Always conduct your own research.</p>
      </div>
    </div>
  )
}
