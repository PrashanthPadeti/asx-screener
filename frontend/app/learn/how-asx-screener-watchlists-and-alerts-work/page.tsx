import Link from 'next/link'
import { ChevronLeft, AlertTriangle, BookOpen, Bell, Star, Eye } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How ASX Screener Watchlists and Alerts Help Investors Stay Organised | ASX Screener',
  description:
    'How to use ASX Screener watchlists and price alerts to track your shortlisted stocks, get notified at your target prices, and stay on top of market moves without constant monitoring.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-asx-screener-watchlists-and-alerts-work' },
}

const WORKFLOW_STEPS = [
  { step: 'Screen for candidates', detail: 'Run a screen using Filter mode, AI Query, or an Alpha Screen. Generate a shortlist of 10–20 stocks matching your criteria.' },
  { step: 'Research each candidate', detail: 'Click through to each company profile. Check the financial ratios, announcements, dividend history, and sector context. Eliminate the stocks that don\'t hold up under scrutiny.' },
  { step: 'Add to watchlist', detail: 'Add the survivors to your watchlist — the 5–10 stocks you want to monitor closely without necessarily owning them yet.' },
  { step: 'Set price alerts', detail: 'For each watchlisted stock, set an alert at your target entry price. If the price drops to your level, you get notified — no need to check daily.' },
  { step: 'Act on alerts, not impulse', detail: 'When an alert fires, you already know you\'ve done the research. Review what has changed (if anything) and decide whether to act.' },
]

const ALERT_TYPES = [
  { type: 'Price falls below target', useCase: 'Entry point alerts — you want to buy at a lower price than the current market. Set the alert and wait.' },
  { type: 'Price rises above target', useCase: 'Exit alerts for a position you own, or breakout alerts for a momentum entry strategy.' },
  { type: 'Percentage change (daily)', useCase: 'Large single-day moves (±5%) often follow earnings results or major announcements. Alert helps you react quickly.' },
  { type: '52-week high/low proximity', useCase: 'Know when a stock approaches a key technical level — useful for both breakout and mean-reversion strategies.' },
]

export default function WatchlistsAndAlertsPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="How ASX Screener Watchlists and Alerts Help Investors Stay Organised"
        description="How to use ASX Screener watchlists and price alerts to track your shortlisted stocks, get notified at your target prices, and stay on top of market moves without constant monitoring."
        url="https://asxscreener.com.au/learn/how-asx-screener-watchlists-and-alerts-work"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'How Watchlists and Alerts Work', href: '/learn/how-asx-screener-watchlists-and-alerts-work' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-sky-100 text-sky-700">Product Feature</span>
          <span className="text-xs text-slate-400">6 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How ASX Screener Watchlists and Alerts Help Investors Stay Organised
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Most investors spend too much time monitoring stocks they&apos;ve already researched — refreshing prices, reading the same announcements twice, watching for entry points that may not come for weeks. ASX Screener watchlists and alerts solve this: track your shortlisted stocks in one place, and let the alerts tell you when something worth acting on happens.
        </p>
      </div>

      <div className="flex gap-3">
        <Link
          href="/watchlist"
          className="flex-1 flex items-center gap-3 bg-gradient-to-r from-sky-600 to-blue-600 text-white rounded-2xl p-5 hover:from-sky-700 hover:to-blue-700 transition-all"
        >
          <Star className="w-6 h-6 shrink-0" />
          <div className="flex-1">
            <p className="font-bold">Go to My Watchlist</p>
            <p className="text-sky-200 text-sm">Track your shortlisted ASX stocks</p>
          </div>
          <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
        </Link>
        <Link
          href="/alerts"
          className="flex-1 flex items-center gap-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-2xl p-5 hover:from-amber-600 hover:to-orange-600 transition-all"
        >
          <Bell className="w-6 h-6 shrink-0" />
          <div className="flex-1">
            <p className="font-bold">Set Price Alerts</p>
            <p className="text-amber-100 text-sm">Get notified at your target price</p>
          </div>
          <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
        </Link>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3 flex items-center gap-2">
          <Eye className="w-5 h-5 text-slate-500" />
          What is the watchlist?
        </h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Your watchlist is a personal list of ASX stocks you want to monitor — typically companies you&apos;ve researched and like, but are waiting for a better entry price, a catalyst, or more information before buying. The watchlist shows you live prices, key metrics, and recent price movement for all your tracked stocks in one view.
        </p>
        <div className="space-y-2">
          {[
            { feature: 'Live price updates', detail: 'See current prices, daily % change, and intraday movement across all your watchlisted stocks.' },
            { feature: 'Key metrics at a glance', detail: 'Dividend yield, P/E ratio, market cap, and 52-week range — no need to open each company profile.' },
            { feature: 'Multiple watchlists', detail: 'Organise stocks by strategy — one list for dividend candidates, one for growth, one for sectors you\'re researching.' },
            { feature: 'Synced across devices', detail: 'Your watchlist is saved to your account, accessible from any device.' },
          ].map(({ feature, detail }) => (
            <div key={feature} className="flex items-start gap-3 bg-white border border-slate-200 rounded-xl p-3">
              <span className="text-sky-500 font-bold text-sm shrink-0">→</span>
              <div>
                <p className="text-sm font-medium text-slate-800">{feature}</p>
                <p className="text-xs text-slate-500 leading-relaxed mt-0.5">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3 flex items-center gap-2">
          <Bell className="w-5 h-5 text-slate-500" />
          What are price alerts?
        </h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Price alerts notify you — via email or in-app notification — when a stock reaches a price you specify. They are the solution to the &quot;I need to wait for this stock to get cheaper before I buy it&quot; problem: set the alert, stop monitoring, and go do something else.
        </p>
        <div className="space-y-2">
          {ALERT_TYPES.map(({ type, useCase }) => (
            <div key={type} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-semibold text-slate-900 text-sm mb-1">{type}</p>
              <p className="text-xs text-slate-500 leading-relaxed">{useCase}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">The screening-to-watchlist workflow</h2>
        <div className="space-y-3">
          {WORKFLOW_STEPS.map(({ step, detail }, i) => (
            <div key={step} className="bg-white border border-slate-200 rounded-xl p-4 flex gap-3">
              <span className="w-6 h-6 rounded-full bg-sky-600 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
              <div>
                <p className="font-semibold text-slate-900 text-sm mb-1">{step}</p>
                <p className="text-xs text-slate-500 leading-relaxed">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3">How to add a stock to your watchlist</h2>
        <div className="space-y-2 text-sm text-blue-900">
          {[
            'From the screener results table: click the star (☆) icon next to any stock ticker',
            'From a company profile page: click "Add to watchlist" in the page header',
            'From the watchlist page directly: search for any ASX code and add it',
          ].map((item, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="text-blue-500 shrink-0 font-mono text-xs mt-0.5">{i + 1}.</span>
              <span className="text-sm">{item}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-3">How to set a price alert</h2>
        <div className="space-y-2 text-sm text-amber-900">
          {[
            'Go to Alerts in the top navigation',
            'Click "New Alert" and search for the ASX code',
            'Select the alert condition (below / above a price, or % change)',
            'Enter your target price',
            'Choose notification method (email, in-app, or both)',
            'Alerts stay active until they fire or you delete them',
          ].map((item, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="text-amber-600 shrink-0 font-mono text-xs mt-0.5">{i + 1}.</span>
              <span className="text-sm">{item}</span>
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
            { href: '/learn/how-to-build-an-asx-watchlist', label: 'How to Build and Maintain an ASX Watchlist' },
            { href: '/learn/how-asx-screener-ai-query-works', label: 'How ASX Screener AI Query Works' },
            { href: '/learn/how-to-use-asx-alpha-screens', label: 'How to Use ASX Screener Alpha Screens' },
            { href: '/learn/how-to-research-asx-stocks-dyor', label: 'How to Research ASX Stocks (DYOR)' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> Watchlists and alerts are organisational tools. Adding a stock to your watchlist does not constitute a recommendation to buy or sell.</p>
      </div>
    </div>
  )
}
