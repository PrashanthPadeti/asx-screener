import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, Brain, Zap } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How ASX Screener AI Query Helps Investors Search in Plain English | ASX Screener',
  description:
    'ASX Screener AI Query lets you type investment ideas in plain English and get structured stock results instantly — no filter-building required.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-asx-screener-ai-query-works' },
}

const EXAMPLES = [
  { idea: 'Show me ASX healthcare stocks with strong earnings growth and low debt', result: 'Sector = Healthcare, eps_growth_1y > 10, debt_to_equity < 0.5' },
  { idea: 'High dividend yield stocks with franking credits above 75%', result: 'dividend_yield > 4, franking_pct > 75, payout_ratio < 80' },
  { idea: 'Small cap ASX miners with revenue growth and positive cash flow', result: 'sector = Materials, market_cap < 500, revenue_growth_1y > 10, ocf_positive = true' },
  { idea: 'Quality compounders with high ROIC and consistent earnings', result: 'roic > 15, eps_cagr_5y > 10, gross_margin > 40, piotroski_f_score >= 7' },
  { idea: 'ASX momentum stocks near 52-week highs', result: 'pct_from_52w_high > -10, above_sma200 = true, return_3m > 10' },
]

export default function AIQueryPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="How ASX Screener AI Query Helps Investors Search in Plain English"
        description="ASX Screener AI Query lets you type investment ideas in plain English and get structured stock results instantly — no filter-building required."
        url="https://asxscreener.com.au/learn/how-asx-screener-ai-query-works"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'How AI Query Works', href: '/learn/how-asx-screener-ai-query-works' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-violet-100 text-violet-700">Product Feature</span>
          <span className="text-xs text-slate-400">6 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How ASX Screener AI Query Helps Investors Search in Plain English
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Most investors know what they&apos;re looking for — they just don&apos;t know which exact filter combinations to use. AI Query solves this by letting you describe your investment idea in plain English, then translating it into structured filters and running the screen automatically.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-violet-600 to-purple-600 text-white rounded-2xl p-5 hover:from-violet-700 hover:to-purple-700 transition-all"
      >
        <Brain className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Try AI Query Now</p>
          <p className="text-violet-200 text-sm">Open the screener → select AI Query tab → type your idea</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What is AI Query?</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          AI Query is a search mode inside the ASX Screener that accepts natural language input — the way you&apos;d describe a stock idea to a colleague — and converts it into a structured screen using the screener&apos;s data fields. The results appear just like a regular screen: a sortable table of ASX stocks matching your criteria.
        </p>
        <p className="text-slate-600 leading-relaxed">
          Unlike the click-based Filter mode (where you build screens by selecting fields and setting values one at a time), AI Query lets you express a multi-condition idea in a single sentence. It works best for ideas that combine 3–6 conditions across different metric categories.
        </p>
      </div>

      <div className="bg-violet-50 border border-violet-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-violet-800 uppercase tracking-wide mb-4 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Example queries and what they become
        </h2>
        <div className="space-y-3">
          {EXAMPLES.map(({ idea, result }) => (
            <div key={idea} className="bg-white rounded-xl border border-violet-100 p-4">
              <p className="text-sm font-medium text-slate-800 mb-2 italic">&quot;{idea}&quot;</p>
              <div className="bg-slate-900 rounded-lg p-2">
                <code className="text-emerald-300 font-mono text-xs leading-relaxed">{result}</code>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">How to use AI Query — step by step</h2>
        <div className="space-y-3">
          {[
            { step: 'Open the ASX Screener', detail: 'Navigate to the Screener page. You\'ll see three mode tabs at the top: Filters, AI Query, and Query Mode.' },
            { step: 'Select the AI Query tab', detail: 'Click "AI Query" to switch to the natural language input mode.' },
            { step: 'Type your investment idea', detail: 'Describe what you\'re looking for in plain English. Be as specific as possible — mention sectors, metrics, thresholds, and any qualitative characteristics you care about.' },
            { step: 'Review the interpreted filters', detail: 'AI Query shows you which filters it applied before running the screen. Review these to make sure they match your intent — you can adjust them if needed.' },
            { step: 'Review results and refine', detail: 'The results appear in the standard screener table. Sort, compare, and click through to individual company profiles. If the result set is too large or too small, refine your query.' },
          ].map(({ step, detail }, i) => (
            <div key={step} className="bg-white border border-slate-200 rounded-xl p-4 flex gap-3">
              <span className="w-6 h-6 rounded-full bg-violet-600 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
              <div>
                <p className="font-semibold text-slate-900 text-sm mb-1">{step}</p>
                <p className="text-xs text-slate-500 leading-relaxed">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Tips for better AI Query results</h2>
        <div className="space-y-2">
          {[
            { tip: 'Be specific about numbers', detail: 'Instead of "high dividend yield", say "dividend yield above 4%". Specific thresholds give more predictable results.' },
            { tip: 'Mention the sector if relevant', detail: '"ASX technology stocks with..." or "ASX healthcare companies..." helps the query focus on the right universe.' },
            { tip: 'Combine fundamentals and technicals', detail: 'AI Query handles multi-factor ideas well: "quality companies with strong earnings growth that are also trending above their 200-day moving average".' },
            { tip: 'Review the interpreted filters', detail: 'Always check what filters were applied. If the AI misinterpreted a term, you can see exactly where and adjust.' },
            { tip: 'Iterate', detail: 'Start broad and add conditions. If 400 stocks match, narrow with an additional constraint. If 3 stocks match, relax a threshold.' },
          ].map(({ tip, detail }) => (
            <div key={tip} className="flex items-start gap-3 bg-white border border-slate-200 rounded-xl p-3">
              <span className="text-violet-500 font-bold text-sm shrink-0">→</span>
              <div>
                <p className="text-sm font-medium text-slate-800">{tip}</p>
                <p className="text-xs text-slate-500 leading-relaxed mt-0.5">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">AI Query vs. Filter mode vs. Query Mode</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border border-slate-200 rounded-xl overflow-hidden">
            <thead className="bg-slate-50">
              <tr>
                <th className="text-left p-3 font-semibold text-slate-700">Mode</th>
                <th className="text-left p-3 font-semibold text-slate-700">Best for</th>
                <th className="text-left p-3 font-semibold text-slate-700">Access</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr>
                <td className="p-3 font-medium text-slate-900">Filter mode</td>
                <td className="p-3 text-slate-600">Building precise screens by selecting individual fields and values. Full control over every parameter.</td>
                <td className="p-3"><span className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full text-xs">All users</span></td>
              </tr>
              <tr>
                <td className="p-3 font-medium text-slate-900">AI Query</td>
                <td className="p-3 text-slate-600">Converting a plain-English investment idea into a screen instantly. Best for exploration and idea generation.</td>
                <td className="p-3"><span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full text-xs">Free & Pro</span></td>
              </tr>
              <tr>
                <td className="p-3 font-medium text-slate-900">Query Mode</td>
                <td className="p-3 text-slate-600">Writing SQL-like conditions directly (e.g. <code className="bg-slate-100 px-1 rounded">roe &gt; 15 AND (roce &gt; 20 OR roic &gt; 20)</code>). Supports OR logic. Power-user mode.</td>
                <td className="p-3"><span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full text-xs">Pro / Admin</span></td>
              </tr>
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
            { href: '/learn/asx-screener-three-ways-to-search', label: 'One ASX Screener, Three Ways to Search' },
            { href: '/learn/how-to-use-asx-alpha-screens', label: 'How to Use ASX Screener Alpha Screens' },
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
        <p><strong>Not financial advice.</strong> AI Query is a research tool. Stock screening results are starting points for research — not buy or sell recommendations.</p>
      </div>
    </div>
  )
}
