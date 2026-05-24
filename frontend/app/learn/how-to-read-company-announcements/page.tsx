import Link from 'next/link'
import { ChevronLeft, BarChart2, BookOpen, ArrowRight, AlertTriangle, Zap, FileText } from 'lucide-react'

export const metadata = {
  title: 'How to Read ASX Company Announcements | ASX Screener Education',
  description:
    'Learn how to read and interpret ASX company announcements — earnings results, appendix 4C, capital raisings, change of director — with a guide to the most important announcement types.',
}

interface AnnType {
  name: string
  code: string
  whatItIs: string
  whatToLookFor: string
  marketImpact: 'High' | 'Medium' | 'Low'
}

const ANNOUNCEMENT_TYPES: AnnType[] = [
  {
    name: 'Full-Year Results (Appendix 4E)',
    code: '4E',
    whatItIs: 'Annual earnings results including revenue, NPAT, EPS, and dividends declared. Released within 2 months of financial year-end.',
    whatToLookFor: 'Revenue growth vs prior year, NPAT margin, EPS trend, final dividend and franking level, guidance for next year.',
    marketImpact: 'High',
  },
  {
    name: 'Half-Year Results (Appendix 4D)',
    code: '4D',
    whatItIs: 'Six-month financial results. Often includes an investor presentation with outlook commentary.',
    whatToLookFor: 'H1 vs H1 prior year, whether guidance is maintained or upgraded/downgraded, interim dividend.',
    marketImpact: 'High',
  },
  {
    name: 'Quarterly Cash Flow (Appendix 4C)',
    code: '4C',
    whatItIs: 'Mandatory quarterly report for companies spending their own cash (pre-revenue or early-stage companies).',
    whatToLookFor: 'Net cash used in operations, cash on hand, "quarters of funding remaining" (QFR). Below 2 quarters is a red flag.',
    marketImpact: 'Medium',
  },
  {
    name: 'Investor Presentation / AGM Address',
    code: 'PRES',
    whatItIs: 'Management slides presented at investor briefings, AGMs, or conferences. Non-binding but informative.',
    whatToLookFor: 'Strategy updates, market outlook, pipeline commentary, any guidance upgrades or downgrades.',
    marketImpact: 'Medium',
  },
  {
    name: 'Change in Substantial Holding',
    code: 'SH',
    whatItIs: 'Notifies the market when an institutional investor crosses or drops below a 5% ownership threshold.',
    whatToLookFor: 'Whether a large investor is buying or selling, and at what price they transacted.',
    marketImpact: 'Medium',
  },
  {
    name: 'Director Interest Notice',
    code: 'DIR',
    whatItIs: 'Directors must disclose changes to their shareholdings within 2 business days.',
    whatToLookFor: 'Directors buying on-market is a bullish signal. Selling is more ambiguous — check if it\'s a small % of their total holding.',
    marketImpact: 'Low',
  },
  {
    name: 'Capital Raising / Share Placement',
    code: 'CR',
    whatItIs: 'Company raises new equity by issuing new shares, typically at a discount to market price.',
    whatToLookFor: 'Discount to last traded price (>10% is large), what the capital will be used for, dilution impact on EPS.',
    marketImpact: 'High',
  },
  {
    name: 'Trading Halt / Suspension',
    code: 'HALT',
    whatItIs: 'Company requests a temporary halt in trading — usually precedes a material announcement within 2 days.',
    whatToLookFor: 'Reason given. Capital raising halts are common. Extended suspensions (days/weeks) warrant caution.',
    marketImpact: 'High',
  },
]

const IMPACT_BADGE: Record<string, string> = {
  High:   'bg-rose-100 text-rose-700',
  Medium: 'bg-amber-100 text-amber-700',
  Low:    'bg-slate-100 text-slate-600',
}

export default function CompanyAnnouncementsPage() {
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
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner</span>
          <span className="text-xs text-slate-400">6 min read</span>
          <span className="text-xs text-slate-400">· Last updated May 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Read ASX Company Announcements
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          ASX-listed companies are required to immediately disclose all information that could affect the price of their securities. Knowing which announcements matter — and what to look for in each — is a core investor skill.
        </p>
      </div>

      {/* Key takeaways */}
      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Key Takeaways
        </h2>
        <ul className="space-y-2">
          {[
            'All ASX announcements are publicly available for free at asx.com.au — search any ticker and click "Announcements".',
            'Earnings results (Appendix 4D and 4E) are the most market-moving announcements for established companies.',
            'Director share purchases on-market (their own money, no discount) are one of the strongest buy signals available.',
            'Trading halts almost always precede a capital raising — check the size and discount before the shares resume.',
          ].map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-900">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {point}
            </li>
          ))}
        </ul>
      </div>

      {/* Where to find announcements */}
      <div className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">Where to find announcements</h2>
        <p className="text-slate-700 leading-relaxed">
          Every ASX announcement is filed on the <strong>ASX Market Announcements Platform</strong> (asx.com.au/asx/statistics/announcements.do). You can search by company ticker, date range, or announcement type. All filings are free and available to any investor in real time.
        </p>
        <p className="text-slate-700 leading-relaxed">
          Most broker platforms also display announcements alongside a company's share price chart — look for the "News" or "Announcements" tab on any stock page.
        </p>
      </div>

      {/* Announcement types */}
      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">The 8 most important announcement types</h2>
        <div className="space-y-4">
          {ANNOUNCEMENT_TYPES.map((ann, i) => (
            <div key={ann.code} className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              <div className="flex items-center gap-3 p-4 border-b border-slate-100 bg-slate-50">
                <span className="w-7 h-7 rounded-full bg-slate-800 text-white text-xs font-bold flex items-center justify-center shrink-0">
                  {i + 1}
                </span>
                <div className="flex-1 flex items-center gap-2 flex-wrap">
                  <h3 className="font-bold text-slate-900 text-sm">{ann.name}</h3>
                  <span className="text-[10px] font-mono font-bold bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded">{ann.code}</span>
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${IMPACT_BADGE[ann.marketImpact]}`}>
                    {ann.marketImpact} impact
                  </span>
                </div>
              </div>
              <div className="p-4 grid sm:grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide mb-1.5">What it is</p>
                  <p className="text-slate-700 leading-snug">{ann.whatItIs}</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold text-emerald-600 uppercase tracking-wide mb-1.5">What to look for</p>
                  <p className="text-slate-700 leading-snug">{ann.whatToLookFor}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Reading an earnings result */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6 space-y-4">
        <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
          <FileText className="w-5 h-5 text-slate-600" />
          Reading a results announcement: a checklist
        </h2>
        <div className="space-y-2">
          {[
            { label: 'Revenue', check: 'Did it grow year-on-year? By how much? What was guidance?' },
            { label: 'NPAT / Net profit', check: 'Statutory vs underlying — reconcile what\'s excluded.' },
            { label: 'EPS', check: 'Is it growing? Has the share count changed (dilution)?' },
            { label: 'Dividend', check: 'Maintained, increased, or cut? What franking level?' },
            { label: 'Guidance', check: 'Upgraded, maintained, or downgraded? This is often the most market-moving line.' },
            { label: 'Balance sheet', check: 'Net debt position vs prior period. Is leverage rising?' },
            { label: 'Cash conversion', check: 'Operating cash flow vs reported profit — big divergence is a red flag.' },
          ].map(({ label, check }) => (
            <div key={label} className="flex items-start gap-3 text-sm">
              <span className="mt-0.5 text-emerald-500 font-bold shrink-0">✓</span>
              <div>
                <span className="font-semibold text-slate-800">{label}: </span>
                <span className="text-slate-600">{check}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Related screener filters */}
      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-3">Related ASX Screener Filters</h2>
        <div className="flex flex-wrap gap-2">
          {['Revenue Growth', 'EPS Growth', 'Dividend Yield', 'Franking %', 'Net Debt / EBITDA', 'Payout Ratio'].map(f => (
            <span key={f} className="text-xs font-medium bg-white border border-amber-300 text-amber-800 px-2.5 py-1 rounded-full">{f}</span>
          ))}
        </div>
        <Link href="/screener" className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-amber-700 hover:text-amber-900">
          Screen by earnings metrics <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      {/* Related glossary */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related Glossary Metrics
        </h2>
        <div className="flex flex-wrap gap-2">
          {['EPS', 'Revenue Growth 1Y', 'Payout Ratio', 'Dividend Yield', 'Net Debt / EBITDA', 'Free Cash Flow'].map(m => (
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
          <strong>Not financial advice.</strong> This guide is for educational purposes. Past announcement patterns do not guarantee future price movements. Always conduct your own research or consult a licensed adviser.
        </p>
      </div>

      {/* CTA */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Put your research into action</h2>
        <p className="text-blue-100 mb-5 text-sm">Filter ASX stocks by the metrics behind the announcements — EPS growth, dividend trends, debt levels.</p>
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
