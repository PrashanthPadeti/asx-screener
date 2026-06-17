import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, Activity, TrendingUp } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How ASX Traders Use Volume and Momentum | ASX Screener',
  description:
    'How to use trading volume, price momentum, RSI, and moving averages to find ASX stocks showing strength. Practical screens for active ASX traders.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-use-asx-volume-and-momentum' },
}

const MOMENTUM_METRICS = [
  { metric: 'Return 1M / 3M / 6M %', key: 'return_1m / return_3m / return_6m', why: 'Price momentum over different periods. Stocks that have outperformed over 3–6 months often continue outperforming in the near term — a well-documented market anomaly.' },
  { metric: 'RSI (14-day)', key: 'rsi_14', why: 'Relative Strength Index. Measures how overbought or oversold a stock is. RSI above 70 = potentially overbought. RSI below 30 = potentially oversold. RSI 50–70 in an uptrend = momentum zone.' },
  { metric: 'Above SMA 200', key: 'above_sma200', why: 'Whether the price is above the 200-day moving average. Widely used to define whether a stock is in a long-term uptrend. Many institutional investors only buy stocks above their 200 DMA.' },
  { metric: 'Golden Cross', key: 'golden_cross', why: 'When the 50-day moving average crosses above the 200-day moving average. A classic bullish signal that a medium-term uptrend has begun.' },
  { metric: 'Volume Ratio vs 20D Avg', key: 'volume_ratio', why: 'Today\'s volume divided by the 20-day average volume. A ratio above 2 means the stock is trading at twice its normal volume — often signals institutional interest or a news event.' },
  { metric: 'Volume Breakout', key: 'volume_breakout', why: 'Boolean: volume is significantly above the 20-day average AND price has moved meaningfully. Often precedes sustained moves.' },
  { metric: 'ADX (14)', key: 'adx_14', why: 'Average Directional Index. Measures trend strength — not direction. ADX above 25 signals a strong trend. Above 40 = very strong. Below 20 = no trend (choppy market).' },
]

const SCREENS = [
  {
    name: 'Strong momentum screen',
    desc: 'Stocks in a confirmed uptrend with strong recent performance and high relative volume.',
    filters: ['above_sma200 = true', 'return_3m > 10', 'return_6m > 15', 'volume_ratio > 1.5', 'rsi_14 > 50', 'rsi_14 < 70'],
  },
  {
    name: 'Volume breakout scan',
    desc: 'Stocks trading on unusually high volume — potential early mover signal.',
    filters: ['volume_breakout = true', 'return_1m > 5', 'above_sma50 = true', 'market_cap > 100'],
  },
  {
    name: 'Trend + fundamentals combo',
    desc: 'Combines price momentum with quality fundamentals — avoids buying speculative breakouts.',
    filters: ['golden_cross = true', 'roe > 12', 'revenue_growth_1y > 8', 'debt_to_equity < 1', 'market_cap > 300'],
  },
  {
    name: 'Near 52-week high screen',
    desc: 'Stocks close to their annual high — often a sign of sustained strength, not a reason to avoid.',
    filters: ['pct_from_52w_high > -10', 'return_6m > 10', 'above_sma200 = true', 'adx_14 > 20'],
  },
]

export default function VolumeAndMomentumPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema headline="How ASX Traders Use Volume and Momentum" description="How to use trading volume, price momentum, RSI, and moving averages to find ASX stocks showing strength. Practical screens for active ASX traders." url="https://asxscreener.com.au/learn/how-to-use-asx-volume-and-momentum" />
      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'Volume and Momentum for ASX Traders', href: '/learn/how-to-use-asx-volume-and-momentum' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">Trading</span>
          <span className="text-xs text-slate-400">9 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How ASX Traders Use Volume and Momentum
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          While fundamental investors focus on earnings and valuations, active ASX traders also pay close attention to price momentum and volume — signals that reflect what the market is actually doing right now. This guide covers the key technical metrics available in the ASX Screener and how to combine them into practical trading screens.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-2xl p-5 hover:from-amber-600 hover:to-orange-600 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Stocks by Momentum</p>
          <p className="text-amber-100 text-sm">Filter by RSI, moving averages, volume ratio, price returns and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Why momentum matters on the ASX</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Price momentum — the tendency of stocks that have risen to keep rising — is one of the most thoroughly documented factors in financial markets. Academic research going back decades shows that stocks in the top decile of 6-month price performance tend to continue outperforming in the following 3–12 months.
        </p>
        <p className="text-slate-600 leading-relaxed">
          Volume amplifies this signal. When a stock is rising on above-average volume, it suggests institutional money is participating — not just retail traders. Volume spikes on price moves often precede sustained trends.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Activity className="w-5 h-5 text-slate-500" />
          Key momentum and volume metrics
        </h2>
        <div className="space-y-3">
          {MOMENTUM_METRICS.map(({ metric, key, why }) => (
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
          <TrendingUp className="w-4 h-4" /> Moving averages as trend filters
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed mb-3">
          The 200-day moving average (SMA 200) is the most widely watched trend indicator in equity markets. Many active traders and fund managers use it as a simple filter:
        </p>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'Price above SMA 200 → stock is in a long-term uptrend → bias toward long positions',
            'Price below SMA 200 → stock is in a long-term downtrend → extra caution required',
            'SMA 50 above SMA 200 (Golden Cross) → medium-term trend has turned bullish',
            'SMA 50 below SMA 200 (Death Cross) → medium-term trend has turned bearish',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-blue-500 shrink-0">→</span>
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Practical momentum screens for ASX traders</h2>
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
        <h2 className="text-xl font-bold text-slate-900 mb-3">Combining momentum with fundamentals</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-3">
          Pure momentum screens can throw up speculative stocks — small miners on announcements, biotech on trial results, or companies with no earnings. Adding a fundamental filter dramatically improves the quality of the shortlist:
        </p>
        <div className="space-y-2">
          {[
            { filter: '+ Market Cap > $200M', benefit: 'Eliminates micro-cap speculation and illiquid stocks' },
            { filter: '+ ROE > 10%', benefit: 'Ensures the business generating the momentum is actually profitable' },
            { filter: '+ Debt/Equity < 1', benefit: 'Avoids companies whose momentum may be driven by financial engineering' },
            { filter: '+ Piotroski F-Score ≥ 6', benefit: 'A composite quality filter — rules out financially deteriorating companies' },
          ].map(({ filter, benefit }) => (
            <div key={filter} className="flex items-start gap-3 bg-white border border-slate-200 rounded-xl p-3">
              <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded shrink-0">{filter}</code>
              <p className="text-xs text-slate-500 leading-relaxed">{benefit}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Using the Market Overview for top movers</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-3">
          The <Link href="/market" className="text-blue-600 hover:underline">ASX Market Overview</Link> shows today&apos;s top gainers and losers in real time — useful for identifying stocks that are moving on news or volume today. Use it alongside the screener: find the mover on the Market page, then pull up its screener profile to check whether the fundamentals support following the move.
        </p>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-2">Key risk: momentum reversal</h2>
        <p className="text-sm text-amber-900 leading-relaxed">
          Momentum works until it doesn&apos;t. Stocks that have risen sharply can fall just as sharply when sentiment shifts. Always use a stop-loss discipline with momentum trades, size positions appropriately, and avoid chasing stocks that have already made the majority of their move.
        </p>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
            { href: '/learn/how-to-find-asx-growth-stocks', label: 'How to Find ASX Growth Stocks Using Revenue Growth' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/market', label: 'ASX Market Overview — Top Movers Today' },
            { href: '/screener/asx-moving-average', label: 'Screen ASX Stocks by Moving Average' },
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
          <strong>Not financial advice.</strong> Technical indicators and momentum screens are tools for identifying candidates to research — not trading signals. Past price performance does not predict future returns. Always manage risk appropriately and consider seeking advice from a licensed financial adviser.
        </p>
      </div>

    </div>
  )
}
