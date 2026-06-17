import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, Zap, Filter } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How to Use ASX Screener Alpha Screens | ASX Screener',
  description:
    'Alpha Screens are ready-made ASX stock screens for dividend, growth, value, momentum, quality, and sector strategies. Learn how to run them and customise them.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-use-asx-alpha-screens' },
}

const SCREEN_CATEGORIES = [
  { cat: 'Dividend & Income', examples: ['High Franked Yield', 'Dividend Growth Stars', 'REIT Income Screen', 'Fully Franked Quality Income'], desc: 'Ready-made screens for income investors — focused on sustainable yield, franking credits, and dividend growth track records.' },
  { cat: 'Value', examples: ['Deep Value Screen', 'Low P/E Quality', 'Below Book with Profit', 'FCF Value'], desc: 'Classic and modern value screens — from Graham-style deep value to FCF-yield-based approaches. Includes value trap filters.' },
  { cat: 'Growth', examples: ['Revenue Growth Accelerators', 'EPS Momentum', 'High ROIC Growth', 'Small Cap Growth'], desc: 'Revenue and earnings growth screens across market cap ranges — from large-cap compounders to emerging small-cap growers.' },
  { cat: 'Quality', examples: ['Quality Compounders', 'High F-Score', 'Capital Efficient Leaders', 'Cash Machine Screen'], desc: 'Screens focused on financial quality — high ROIC, strong free cash flow conversion, low leverage, and consistent earnings.' },
  { cat: 'Momentum', examples: ['ASX 52-Week High Breakout', 'Golden Cross Screen', 'Volume Surge Leaders', 'Strong Trend + Quality'], desc: 'Technical and price-momentum screens — for traders and investors who want to combine fundamental quality with price strength.' },
  { cat: 'Sector', examples: ['ASX Banks Deep Dive', 'Healthcare Quality', 'Resources Momentum', 'Tech Growth'], desc: 'Sector-focused screens pre-filtered by GICS sector with sector-appropriate metrics. No need to add a sector filter manually.' },
]

export default function AlphaScreensPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="How to Use ASX Screener Alpha Screens"
        description="Alpha Screens are ready-made ASX stock screens for dividend, growth, value, momentum, quality, and sector strategies. Learn how to run them and customise them."
        url="https://asxscreener.com.au/learn/how-to-use-asx-alpha-screens"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'How to Use Alpha Screens', href: '/learn/how-to-use-asx-alpha-screens' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Product Feature</span>
          <span className="text-xs text-slate-400">6 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Use ASX Screener Alpha Screens
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Alpha Screens are ready-made stock screens built around proven investment strategies. Instead of building a screen from scratch, you run a curated strategy in one click — then customise it to match your own criteria.
        </p>
      </div>

      <Link
        href="/scans"
        className="flex items-center gap-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-2xl p-5 hover:from-emerald-700 hover:to-teal-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Browse All Alpha Screens</p>
          <p className="text-emerald-200 text-sm">Dividend, value, growth, quality, momentum, and sector screens — run any instantly</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What are Alpha Screens?</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Alpha Screens are pre-built stock screens designed around specific investment strategies — dividend income, deep value, quality compounders, momentum trading, and more. Each screen applies a set of carefully chosen criteria to the full ASX universe and returns a ranked list of stocks that match.
        </p>
        <p className="text-slate-600 leading-relaxed">
          They are designed to give you a useful starting shortlist in seconds, without needing to know which fields to filter or what thresholds to use. You can run any screen as-is, or open the underlying filters and customise them.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-500" />
          Screen categories
        </h2>
        <div className="space-y-3">
          {SCREEN_CATEGORIES.map(({ cat, examples, desc }) => (
            <div key={cat} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-bold text-slate-900 text-sm mb-1">{cat}</p>
              <p className="text-xs text-slate-500 leading-relaxed mb-2">{desc}</p>
              <div className="flex flex-wrap gap-1.5">
                {examples.map(ex => (
                  <span key={ex} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{ex}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">How to run an Alpha Screen</h2>
        <div className="space-y-3">
          {[
            { step: 'Go to Alpha Screens', detail: 'Click "Scans" in the main navigation, or visit /scans directly. You\'ll see all available screens grouped by strategy category.' },
            { step: 'Browse or search for a strategy', detail: 'Scroll through the categories or use the search box to find a screen matching your investment approach.' },
            { step: 'Run the screen', detail: 'Click any screen card to run it instantly. Results appear as a sortable table of ASX stocks — same format as the manual screener.' },
            { step: 'Customise if needed', detail: 'Click "Edit filters" to open the underlying criteria. Adjust any value — tighten a threshold, relax a condition, or add a new filter.' },
            { step: 'Save or export', detail: 'Save the customised screen as your own, or export results to CSV for further analysis.' },
          ].map(({ step, detail }, i) => (
            <div key={step} className="bg-white border border-slate-200 rounded-xl p-4 flex gap-3">
              <span className="w-6 h-6 rounded-full bg-emerald-600 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
              <div>
                <p className="font-semibold text-slate-900 text-sm mb-1">{step}</p>
                <p className="text-xs text-slate-500 leading-relaxed">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> How to use Alpha Screen results
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed mb-3">
          Alpha Screen results are <strong>starting points for research — not buy recommendations</strong>. A stock appearing on a &quot;Quality Compounders&quot; screen has passed a set of quantitative criteria, but you still need to:
        </p>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'Read recent company announcements to understand current business conditions',
            'Check the dividend history and management commentary for guidance',
            'Review the valuation — a quality company at a very high price may offer limited upside',
            'Understand sector-specific risks that metrics alone cannot capture',
            'Consider position sizing relative to your overall portfolio',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-blue-500 shrink-0">→</span>{item}
            </li>
          ))}
        </ul>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/asx-screener-three-ways-to-search', label: 'One ASX Screener, Three Ways to Search' },
            { href: '/learn/how-asx-screener-ai-query-works', label: 'How ASX Screener AI Query Works' },
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
            { href: '/scans', label: 'Browse All Alpha Screens' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> Alpha Screens are research and discovery tools. Results are not recommendations to buy or sell any security.</p>
      </div>
    </div>
  )
}
