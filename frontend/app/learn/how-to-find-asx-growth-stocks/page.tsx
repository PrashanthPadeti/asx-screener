import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, TrendingUp, Zap } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata = {
  title: 'How to Find ASX Growth Stocks Using Revenue Growth | ASX Screener',
  description:
    'How to screen for ASX growth stocks using revenue growth, earnings growth, and momentum metrics. Includes example screens and key signals to watch.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-find-asx-growth-stocks' },
}

const GROWTH_METRICS = [
  { metric: 'Revenue Growth 1Y %', key: 'revenue_growth_1y', why: 'The most direct measure of whether the business is expanding. Single year — check the trend over 3–5 years before trusting it.' },
  { metric: 'Revenue CAGR 3Y %', key: 'revenue_growth_3y_cagr', why: 'Compound annual revenue growth over three years. Smooths out one-off years and gives a more reliable picture of the growth trajectory.' },
  { metric: 'Revenue CAGR 5Y %', key: 'revenue_cagr_5y', why: 'Five-year compounded growth. A company sustaining 10%+ revenue CAGR over 5 years in a competitive market has demonstrated real staying power.' },
  { metric: 'EPS Growth 1Y %', key: 'eps_growth_1y', why: 'Earnings per share growth. Growth in EPS means the profit improvement is flowing through to shareholders — not being eroded by dilution.' },
  { metric: 'EPS CAGR 5Y %', key: 'eps_cagr_5y', why: 'Five-year compounded EPS growth. The gold standard for quality growth — revenue growing and earnings growing faster than revenue (operating leverage).' },
  { metric: 'Revenue Growth Accelerating', key: 'revenue_growth_accelerating', why: 'Boolean signal: is revenue growth speeding up? Acceleration often precedes stronger re-rating by the market.' },
]

const RED_FLAGS = [
  { flag: 'Revenue growing but earnings falling', why: 'Could mean rising costs, margin compression, or heavy reinvestment. Understand which before buying.' },
  { flag: 'Growth driven by acquisitions', why: 'Organic growth is more valuable than growth through buying other companies. Check if revenue growth is happening inside the existing business.' },
  { flag: 'High P/E with decelerating growth', why: 'Growth stocks are valued on future growth. If growth is slowing, the high multiple becomes harder to justify.' },
  { flag: 'Share count rising fast', why: 'If shares on issue are growing at 10% per year, shareholders are being diluted. EPS growth will lag revenue growth significantly.' },
  { flag: 'Negative operating cash flow', why: 'Revenue growth that doesn\'t convert to cash is fragile. Companies can grow themselves into a cash crisis if they\'re not careful.' },
]

export default function HowToFindASXGrowthStocksPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'How to Find ASX Growth Stocks', href: '/learn/how-to-find-asx-growth-stocks' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Intermediate</span>
          <span className="text-xs text-slate-400">10 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Find ASX Growth Stocks Using Revenue Growth
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Growth investing on the ASX means finding companies that are expanding their revenue and earnings faster than the market average — and holding them as that growth compounds into share price returns. This guide covers the key metrics to use, how to screen for them, and the red flags to watch for.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-2xl p-5 hover:from-emerald-700 hover:to-teal-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Growth Stocks</p>
          <p className="text-emerald-200 text-sm">Filter by revenue growth, EPS CAGR, earnings growth and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What makes a growth stock?</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          A growth stock is one where the market expects earnings to grow significantly faster than the broader economy — typically above 10–15% per year. These companies often trade at higher P/E multiples because investors are paying for the future earnings stream, not just today&apos;s profits.
        </p>
        <p className="text-slate-600 leading-relaxed">
          On the ASX, growth stocks tend to cluster in technology, healthcare, consumer discretionary, and some materials names where production growth is the story. Banks and utilities — steady but slow-growing — are rarely growth stocks.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-slate-500" />
          Key growth metrics to screen for
        </h2>
        <div className="space-y-3">
          {GROWTH_METRICS.map(({ metric, key, why }) => (
            <div key={key} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
                <p className="font-semibold text-slate-900 text-sm">{metric}</p>
                <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{key}</code>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{why}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> The most important signal: EPS growing faster than revenue
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed">
          When EPS grows faster than revenue, it means margins are expanding — the company is getting more efficient as it scales. This is called <strong>operating leverage</strong>, and it is one of the most powerful signs of a quality growth business. A company where revenue grows 15% but EPS grows 25% is demonstrating exactly this. ASX Screener&apos;s <em>EPS Beats Revenue Growth</em> filter finds these companies directly.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example growth screens</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Consistent revenue growth screen',
              desc: 'Companies with sustained multi-year revenue growth, positive earnings momentum, and manageable debt.',
              filters: ['revenue_growth_3y_cagr > 10', 'eps_growth_1y > 10', 'debt_to_equity < 0.5', 'market_cap > 200'],
            },
            {
              name: 'High-conviction growth + quality',
              desc: 'Strong 5-year revenue and EPS CAGR, with EPS growing faster than revenue (operating leverage).',
              filters: ['revenue_cagr_5y > 12', 'eps_cagr_5y > 15', 'eps_beats_revenue_growth = true', 'ocf_positive = true'],
            },
            {
              name: 'Accelerating growth screen',
              desc: 'Companies where growth is getting faster — often a leading indicator of a re-rating.',
              filters: ['revenue_growth_accelerating = true', 'revenue_growth_1y > 15', 'return_3m > 5', 'market_cap > 100'],
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
        <h2 className="text-xl font-bold text-slate-900 mb-3">Growth vs. value: does the price matter?</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-3">
          Growth stocks typically trade at premium P/E multiples — sometimes 30, 40, or 50× earnings. This is rational if the growth rate justifies the multiple. The PEG ratio (P/E ÷ earnings growth rate) is a quick way to check whether a growth stock is expensive relative to its growth:
        </p>
        <div className="bg-slate-900 rounded-xl p-4 mb-3">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{`PEG < 1.0  →  potentially undervalued relative to growth
PEG 1–2    →  fairly valued for a quality growth company
PEG > 2    →  growth priced in — limited upside unless growth accelerates`}</code>
        </div>
        <p className="text-slate-600 text-sm leading-relaxed">
          A PEG below 1 on a quality growth company is often considered a buying opportunity — though the ratio has limitations and works best alongside other metrics.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Red flags for growth investors</h2>
        <div className="space-y-3">
          {RED_FLAGS.map(({ flag, why }) => (
            <div key={flag} className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="font-semibold text-amber-900 text-sm mb-1">{flag}</p>
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
            { href: '/learn/roic-explained', label: 'ROIC Explained: Return on Invested Capital' },
            { href: '/learn/roe-explained', label: 'ROE Explained: Return on Equity' },
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/screener/asx-market-cap', label: 'Screening ASX Stocks by Market Cap' },
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
          <strong>Not financial advice.</strong> Growth investing involves higher risk than investing in established dividend-paying companies. Past revenue growth does not guarantee future performance. Always conduct your own research.
        </p>
      </div>

    </div>
  )
}
