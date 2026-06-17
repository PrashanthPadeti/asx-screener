import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, Filter, Brain, Code2 } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata = {
  title: 'One ASX Screener, Three Ways to Search | ASX Screener',
  description:
    'ASX Screener offers three ways to find stocks: click filters, plain English AI queries, and SQL-like query mode. Learn which approach suits your investing style.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/asx-screener-three-ways-to-search' },
}

const MODES = [
  {
    icon: Filter,
    mode: 'Filter Mode',
    who: 'Best for beginners and visual investors',
    color: 'blue',
    desc: 'The classic click-and-drag approach. You select metrics from a list, set a range using sliders or dropdowns, and the screener instantly filters results. No typing required.',
    example: 'Add filters: Sector = Materials, Market Cap > $500M, Dividend Yield > 2%, Franking % = 100%',
    pros: ['No experience needed — fully visual', 'Instant results as you adjust sliders', 'Pre-built preset screens to start from', 'Export to CSV with one click'],
    best: 'When you know broadly what you want and prefer clicking to typing.',
  },
  {
    icon: Brain,
    mode: 'AI Query Mode',
    who: 'Best for investors with an idea but unsure of the metrics',
    color: 'purple',
    desc: 'Type your investment idea in plain English. ASX Screener\'s AI reads your intent and translates it into a structured screen — no knowledge of metric names required.',
    example: '"profitable small caps with low debt and consistent dividend growth"',
    pros: ['No need to know metric names', 'Handles complex intent in one sentence', 'Great for exploring new ideas quickly', 'AI explains what filters it applied'],
    best: 'When you have a qualitative investment thesis and want the AI to operationalise it.',
  },
  {
    icon: Code2,
    mode: 'Query Mode',
    who: 'Best for power users and systematic investors',
    color: 'orange',
    desc: 'Write conditions directly using a SQL-like syntax. Supports OR logic, parentheses, and nested conditions — something the visual filter builder cannot express.',
    example: 'roe > 15 AND (roce > 15 OR roic > 15) AND debt_to_equity < 0.5',
    pros: ['Full OR logic — not just AND', 'Nested conditions with parentheses', 'All 235+ fields available by name or alias', 'Exact, reproducible, shareable queries'],
    best: 'When you know exactly what you want and need full control over the logic.',
  },
]

const EXAMPLES = [
  {
    idea: 'I want high dividend stocks with franking',
    filter: 'Dividend Yield > 4%, Franking % = 100%, Payout Ratio < 80%',
    ai: '"ASX stocks with high fully franked dividends and sustainable payout ratios"',
    query: 'dividend_yield > 4 AND franking_pct = 100 AND payout_ratio < 80',
  },
  {
    idea: 'I want quality companies at reasonable prices',
    filter: 'ROE > 15%, P/E 10–25, Debt/Equity < 0.5, Market Cap > $1B',
    ai: '"quality ASX companies with strong returns, low debt and reasonable valuations"',
    query: 'roe > 15 AND pe_ratio < 25 AND pe_ratio > 10 AND debt_to_equity < 0.5',
  },
  {
    idea: 'I want growth stocks with momentum',
    filter: 'Revenue Growth 3Y > 10%, Return 6M > 10%, Above SMA 200',
    ai: '"ASX growth companies with strong revenue growth and positive price momentum"',
    query: 'revenue_growth_3y_cagr > 10 AND return_6m > 10 AND above_sma200 = true',
  },
]

export default function ThreeWaysToSearchPage() {
  const colorMap: Record<string, string> = {
    blue:   'bg-blue-50 border-blue-200 text-blue-700',
    purple: 'bg-purple-50 border-purple-200 text-purple-700',
    orange: 'bg-orange-50 border-orange-200 text-orange-700',
  }
  const iconColor: Record<string, string> = {
    blue: 'text-blue-600', purple: 'text-purple-600', orange: 'text-orange-600',
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'Three Ways to Search', href: '/learn/asx-screener-three-ways-to-search' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Product Guide</span>
          <span className="text-xs text-slate-400">8 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          One ASX Screener, Three Ways to Search
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Most stock screeners give you one way to find stocks — a set of click filters. ASX Screener offers three: visual filters, plain English AI queries, and a SQL-like query mode. Each is designed for a different type of investor and a different type of question.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Open the ASX Screener</p>
          <p className="text-blue-200 text-sm">Try all three modes on 2,100+ ASX stocks</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      {MODES.map(({ icon: Icon, mode, who, color, desc, example, pros, best }) => (
        <div key={mode} className="space-y-4">
          <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm font-semibold ${colorMap[color]}`}>
            <Icon className={`w-4 h-4 ${iconColor[color]}`} />
            {mode}
          </div>
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{who}</p>
          <p className="text-slate-600 leading-relaxed text-sm">{desc}</p>

          <div className="bg-slate-900 rounded-xl p-4">
            <p className="text-slate-500 text-xs mb-1">Example:</p>
            <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{example}</code>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {pros.map(pro => (
              <div key={pro} className="flex items-start gap-2 text-xs text-slate-600">
                <span className="text-emerald-500 shrink-0 font-bold">✓</span>
                {pro}
              </div>
            ))}
          </div>

          <div className={`rounded-xl p-3 border text-xs ${colorMap[color]}`}>
            <strong>Use this when:</strong> {best}
          </div>
        </div>
      ))}

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Same idea, three different inputs</h2>
        <p className="text-slate-500 text-sm mb-5">Here is how the same investment idea looks across all three modes:</p>
        <div className="space-y-6">
          {EXAMPLES.map(({ idea, filter, ai, query }) => (
            <div key={idea} className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3">
              <p className="font-semibold text-slate-900 text-sm">{idea}</p>
              <div>
                <p className="text-xs text-slate-400 font-medium mb-1">Filter mode:</p>
                <p className="text-xs text-slate-600 bg-slate-50 rounded-lg px-3 py-2">{filter}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 font-medium mb-1">AI Query:</p>
                <p className="text-xs text-purple-700 bg-purple-50 rounded-lg px-3 py-2 italic">{ai}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 font-medium mb-1">Query Mode:</p>
                <code className="text-xs text-emerald-300 bg-slate-900 rounded-lg px-3 py-2 block font-mono">{query}</code>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Which mode should you use?</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-slate-100">
                <th className="text-left p-3 text-xs font-semibold text-slate-600 rounded-tl-lg">Situation</th>
                <th className="text-left p-3 text-xs font-semibold text-slate-600 rounded-tr-lg">Recommended mode</th>
              </tr>
            </thead>
            <tbody>
              {[
                { situation: 'New to screening, not sure where to start', mode: 'Filter Mode — try a preset screen from Alpha Screens' },
                { situation: 'You have an idea but don\'t know the metric names', mode: 'AI Query — type your idea in plain English' },
                { situation: 'You want OR logic (e.g. ROE > 15 OR ROCE > 15)', mode: 'Query Mode — filter mode is AND-only' },
                { situation: 'You want to save and share an exact reproducible screen', mode: 'Query Mode — the query string is self-contained' },
                { situation: 'You\'re exploring what the screener can do', mode: 'Start with Filter Mode, switch to AI Query for inspiration' },
              ].map(({ situation, mode }, i) => (
                <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
                  <td className="p-3 text-xs text-slate-600 border-b border-slate-100">{situation}</td>
                  <td className="p-3 text-xs text-slate-700 font-medium border-b border-slate-100">{mode}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
            { href: '/learn/what-is-an-asx-stock-screener', label: 'What Is an ASX Stock Screener?' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/scans', label: 'Explore Alpha Screens — Ready-Made Screens' },
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
          <strong>Not financial advice.</strong> Stock screening is a research tool, not a recommendation engine. Always conduct your own research before making investment decisions.
        </p>
      </div>

    </div>
  )
}
