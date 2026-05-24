import Link from 'next/link'
import { ChevronLeft, BarChart2, BookOpen, ArrowRight, AlertTriangle, Zap } from 'lucide-react'

export const metadata = {
  title: 'Key Financial Ratios for ASX Investors | ASX Screener Education',
  description:
    'P/E, P/B, ROE, EV/EBITDA, D/E — the essential financial ratios for evaluating ASX stocks explained with formulas, benchmarks, and Australian examples.',
}

interface Ratio {
  id: string
  name: string
  formula: string
  whatItTells: string
  goodRange: string
  watchOut: string
  category: string
}

const RATIOS: Ratio[] = [
  {
    id: 'pe',
    name: 'P/E Ratio (Price-to-Earnings)',
    formula: 'P/E = Share Price ÷ EPS',
    whatItTells: 'How much investors pay for each dollar of earnings. A lower P/E means cheaper relative to earnings.',
    goodRange: 'ASX average 16–18×. Banks 10–15×. Growth stocks 25–50×+',
    watchOut: 'Meaningless for loss-making companies. Always compare within the same sector.',
    category: 'Valuation',
  },
  {
    id: 'pb',
    name: 'P/B Ratio (Price-to-Book)',
    formula: 'P/B = Share Price ÷ Book Value Per Share',
    whatItTells: 'How much you pay relative to the net asset value. P/B < 1 means trading below asset value.',
    goodRange: 'Banks 1–2×. Industrials 1.5–3×. Asset-light tech 3–10×+',
    watchOut: 'Less meaningful for services/tech companies with few hard assets.',
    category: 'Valuation',
  },
  {
    id: 'ev_ebitda',
    name: 'EV/EBITDA',
    formula: 'EV/EBITDA = Enterprise Value ÷ EBITDA',
    whatItTells: 'Like P/E but debt-adjusted. Useful for comparing companies with different capital structures.',
    goodRange: 'Below 10× often considered value. 10–15× fair. 15×+ expensive or high-growth.',
    watchOut: 'Ignores capex requirements — important for capital-intensive businesses like miners.',
    category: 'Valuation',
  },
  {
    id: 'roe',
    name: 'ROE (Return on Equity)',
    formula: 'ROE = Net Profit ÷ Shareholders\' Equity × 100',
    whatItTells: 'How efficiently a company generates profit from shareholders\' money.',
    goodRange: 'Below 10%: weak. 10–15%: adequate. 15–20%: good. Above 20%: excellent.',
    watchOut: 'High ROE can be inflated by debt. Check alongside debt-to-equity ratio.',
    category: 'Profitability',
  },
  {
    id: 'de',
    name: 'Debt-to-Equity (D/E)',
    formula: 'D/E = Total Debt ÷ Shareholders\' Equity',
    whatItTells: 'How much debt a company carries relative to its equity base. Lower is generally safer.',
    goodRange: 'Below 0.5: conservative. 0.5–1.5: moderate. Above 2×: elevated risk.',
    watchOut: 'Banks have naturally high D/E (8–12×) — use different metrics for financials.',
    category: 'Financial Health',
  },
  {
    id: 'current_ratio',
    name: 'Current Ratio',
    formula: 'Current Ratio = Current Assets ÷ Current Liabilities',
    whatItTells: 'Whether a company can cover short-term debts with short-term assets.',
    goodRange: 'Above 1.5: healthy. 1.0–1.5: acceptable. Below 1.0: potential liquidity risk.',
    watchOut: 'Very high ratios (above 3) may indicate excess idle cash or poor capital allocation.',
    category: 'Financial Health',
  },
  {
    id: 'gross_margin',
    name: 'Gross Margin',
    formula: 'Gross Margin = (Revenue − Cost of Goods Sold) ÷ Revenue × 100',
    whatItTells: 'How much profit remains after direct production costs. High gross margins indicate pricing power.',
    goodRange: 'Software/services: 50–80%+. Retailers: 25–45%. Mining/materials: 20–50% (varies with commodity).',
    watchOut: 'Compare within sectors only — margin profiles vary wildly by industry.',
    category: 'Profitability',
  },
  {
    id: 'fcf_yield',
    name: 'Free Cash Flow Yield',
    formula: 'FCF Yield = Free Cash Flow Per Share ÷ Share Price × 100',
    whatItTells: 'The real cash return you get for each dollar invested. Often more reliable than earnings-based metrics.',
    goodRange: 'Above 5%: attractive. 3–5%: fair value. Below 3%: potentially expensive.',
    watchOut: 'Highly capital-intensive periods (capex spikes) can temporarily depress FCF.',
    category: 'Valuation',
  },
]

const CATEGORY_COLORS: Record<string, string> = {
  Valuation:       'bg-blue-100 text-blue-700',
  Profitability:   'bg-purple-100 text-purple-700',
  'Financial Health': 'bg-emerald-100 text-emerald-700',
}

export default function KeyFinancialRatiosPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      {/* Breadcrumb */}
      <Link href="/learn" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-blue-600 transition-colors">
        <ChevronLeft className="w-4 h-4" />
        Education Hub
      </Link>

      {/* Header */}
      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Intermediate</span>
          <span className="text-xs text-slate-400">10 min read</span>
          <span className="text-xs text-slate-400">· Last updated May 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Key Financial Ratios for ASX Investors
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          P/E, P/B, ROE, EV/EBITDA, D/E — these eight ratios form the toolkit every ASX investor needs. Here's what each one measures, how to benchmark it, and where it can mislead you.
        </p>
      </div>

      {/* Key takeaways */}
      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Key Takeaways
        </h2>
        <ul className="space-y-2">
          {[
            'No single ratio tells the full story — always use a combination.',
            'Always compare ratios within the same sector. A "high" P/E for a bank is normal for a tech company.',
            'Profitability ratios (ROE, margins) tell you how well the business runs. Valuation ratios (P/E, P/B) tell you whether the market price is fair.',
            'Financial health ratios (D/E, current ratio) flag whether the business can survive a downturn.',
          ].map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-900">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {point}
            </li>
          ))}
        </ul>
      </div>

      {/* Ratios */}
      <div className="space-y-6">
        {RATIOS.map((r, i) => (
          <div key={r.id} className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            {/* Card header */}
            <div className="flex items-center gap-3 p-5 border-b border-slate-100">
              <span className="w-7 h-7 rounded-full bg-slate-800 text-white text-xs font-bold flex items-center justify-center shrink-0">
                {i + 1}
              </span>
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-base font-bold text-slate-900">{r.name}</h2>
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${CATEGORY_COLORS[r.category] ?? 'bg-slate-100 text-slate-600'}`}>
                    {r.category}
                  </span>
                </div>
              </div>
            </div>

            <div className="p-5 space-y-4">
              {/* Formula */}
              <div className="bg-slate-900 rounded-xl p-3">
                <code className="text-emerald-300 font-mono text-sm">{r.formula}</code>
              </div>

              <div className="grid sm:grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">What it tells you</p>
                  <p className="text-slate-700 leading-snug">{r.whatItTells}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1">Benchmarks</p>
                  <p className="text-slate-700 leading-snug">{r.goodRange}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold text-amber-600 uppercase tracking-wide mb-1">Watch out for</p>
                  <p className="text-slate-700 leading-snug">{r.watchOut}</p>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* How to use together */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6 space-y-4">
        <h2 className="text-lg font-bold text-slate-900">Using ratios together: a simple framework</h2>
        <div className="grid sm:grid-cols-3 gap-4">
          {[
            { step: '1', label: 'Is it profitable?', ratios: 'ROE, Gross Margin, FCF Yield', color: 'purple' },
            { step: '2', label: 'Is it financially healthy?', ratios: 'D/E, Current Ratio', color: 'emerald' },
            { step: '3', label: 'Is it cheap enough?', ratios: 'P/E, P/B, EV/EBITDA', color: 'blue' },
          ].map(({ step, label, ratios, color }) => (
            <div key={step} className="bg-white rounded-xl border border-slate-200 p-4">
              <span className={`text-[10px] font-bold uppercase tracking-wide ${color === 'purple' ? 'text-purple-600' : color === 'emerald' ? 'text-emerald-600' : 'text-blue-600'}`}>
                Step {step}
              </span>
              <p className="font-semibold text-slate-800 mt-1 mb-1.5">{label}</p>
              <p className="text-xs text-slate-500">{ratios}</p>
            </div>
          ))}
        </div>
        <p className="text-sm text-slate-600">
          A company that passes all three checks — profitable, financially sound, and reasonably priced — is a strong screener candidate.
        </p>
      </div>

      {/* Related screener filters */}
      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-3">Use These Ratios in the ASX Screener</h2>
        <div className="flex flex-wrap gap-2">
          {['P/E Ratio', 'P/B Ratio', 'EV/EBITDA', 'ROE', 'Debt-to-Equity', 'Current Ratio', 'Gross Margin', 'FCF Yield'].map(f => (
            <span key={f} className="text-xs font-medium bg-white border border-amber-300 text-amber-800 px-2.5 py-1 rounded-full">{f}</span>
          ))}
        </div>
        <Link href="/screener" className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-amber-700 hover:text-amber-900">
          Try a Value Screen <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      {/* Related glossary */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Deep-dive in the Metrics Glossary
        </h2>
        <div className="flex flex-wrap gap-2">
          {['P/E Ratio', 'P/B Ratio', 'ROE', 'EV/EBITDA', 'Debt-to-Equity', 'Piotroski F-Score', 'Current Ratio'].map(m => (
            <Link key={m} href="/glossary" className="text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:border-blue-300 hover:text-blue-700 px-2.5 py-1 rounded-full transition-colors">
              {m}
            </Link>
          ))}
        </div>
      </div>

      {/* Disclaimer */}
      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p>
          <strong>Not financial advice.</strong> Ratios and benchmarks are general guidelines. Sector norms vary significantly — always conduct your own research or consult a licensed financial adviser before making investment decisions.
        </p>
      </div>

      {/* CTA */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Screen ASX stocks by these ratios</h2>
        <p className="text-blue-100 mb-5 text-sm">Filter 200+ ASX stocks by P/E, ROE, D/E, EV/EBITDA and more in real time.</p>
        <Link
          href="/screener"
          className="inline-flex items-center gap-2 bg-white text-blue-700 font-semibold px-5 py-2.5 rounded-xl hover:bg-blue-50 transition-colors"
        >
          <BarChart2 className="w-4 h-4" />
          Open the Screener
        </Link>
      </div>

    </div>
  )
}
