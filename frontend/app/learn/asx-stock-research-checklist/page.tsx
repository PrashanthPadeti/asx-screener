import Link from 'next/link'
import { ChevronLeft, BarChart2, CheckCircle2, AlertTriangle, Zap, BookOpen, XCircle } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'ASX Stock Research Checklist for Investors | ASX Screener',
  description:
    'A practical checklist for researching ASX stocks. Covers business model, financial health, valuation, management, recent announcements, and risk factors — use this before adding any stock to your watchlist.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/asx-stock-research-checklist' },
}

const CHECKLIST = [
  {
    section: 'Business Understanding',
    color: 'blue',
    items: [
      'I can explain in one paragraph what this company does and how it makes money.',
      'I understand who the customers are and why they use this product or service.',
      'I know the main competitors and how this company is differentiated.',
      'I understand the revenue model: recurring, transactional, project-based, or commodity-linked.',
      'I have read the CEO\'s letter in the most recent annual report.',
    ],
  },
  {
    section: 'Financial Health',
    color: 'emerald',
    items: [
      'Revenue has grown or remained stable over the past 3 years.',
      'Net profit margin is positive and consistent (or improving).',
      'Operating cash flow is positive — the business generates real cash.',
      'Debt-to-equity ratio is within a comfortable range for the sector.',
      'The company has not needed to raise equity capital repeatedly to fund operations.',
      'Interest coverage ratio is healthy (EBIT > 3x interest expense as a rough guide).',
    ],
  },
  {
    section: 'Valuation',
    color: 'purple',
    items: [
      'I have looked at PE ratio and compared it to sector peers and the stock\'s own history.',
      'I have considered EV/EBITDA for capital-intensive or debt-heavy businesses.',
      'For income stocks: I have calculated grossed-up yield including franking credits.',
      'The valuation appears reasonable given the growth rate and quality of the business.',
      'I understand why the stock might be cheap (if it is) — and whether that reason is justified.',
    ],
  },
  {
    section: 'Management & Governance',
    color: 'amber',
    items: [
      'The CEO and CFO have relevant experience and a track record at this company.',
      'The board has a majority of independent directors.',
      'Executive remuneration is linked to meaningful performance metrics.',
      'Directors have meaningful share ownership (skin in the game).',
      'No recent patterns of excessive related-party transactions or governance controversies.',
    ],
  },
  {
    section: 'Recent ASX Announcements',
    color: 'rose',
    items: [
      'I have read the last 12 months of ASX announcements for this company.',
      'There are no unexpected capital raises (placements, rights issues) in the past year.',
      'No unexplained trading halts or unusual price-sensitive delays.',
      'Key management has not departed suddenly or without clear explanation.',
      'The most recent trading update or results were in line with guidance or above.',
    ],
  },
  {
    section: 'Risk Assessment',
    color: 'slate',
    items: [
      'I can identify the top 3 specific risks to this company\'s business.',
      'I understand any commodity, currency, or interest rate exposures.',
      'The business is not entirely dependent on one customer, contract, or person.',
      'Regulatory or licensing risks are understood and manageable.',
      'I have considered what could permanently impair this business (not just short-term volatility).',
    ],
  },
]

const COLOR_MAP: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  blue:    { bg: 'bg-blue-50',    text: 'text-blue-800',   border: 'border-blue-200',   dot: 'bg-blue-500' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-800',border: 'border-emerald-200',dot: 'bg-emerald-500' },
  purple:  { bg: 'bg-purple-50',  text: 'text-purple-800', border: 'border-purple-200', dot: 'bg-purple-500' },
  amber:   { bg: 'bg-amber-50',   text: 'text-amber-800',  border: 'border-amber-200',  dot: 'bg-amber-500' },
  rose:    { bg: 'bg-rose-50',    text: 'text-rose-800',   border: 'border-rose-200',   dot: 'bg-rose-500' },
  slate:   { bg: 'bg-slate-50',   text: 'text-slate-800',  border: 'border-slate-200',  dot: 'bg-slate-500' },
}

export default function ASXStockResearchChecklistPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema headline="ASX Stock Research Checklist for Investors" description="A practical checklist for researching ASX stocks. Covers business model, financial health, valuation, management, recent announcements, and risk factors." url="https://asxscreener.com.au/learn/asx-stock-research-checklist" />
      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'ASX Stock Research Checklist', href: '/learn/asx-stock-research-checklist' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner</span>
          <span className="text-xs text-slate-400">6 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          ASX Stock Research Checklist for Investors
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Before adding any ASX stock to your watchlist or portfolio, run through this checklist. It covers six key areas of due diligence — from understanding the business to assessing specific risks.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> How to use this checklist
        </h2>
        <ul className="space-y-2">
          {[
            'Work through each section for every stock you are considering adding to your watchlist.',
            'You do not need to tick every box — some items may not be relevant for every company type.',
            'If you find a major red flag in any section, that is a reason to investigate further, not necessarily a reason to discard the stock entirely.',
            'This is a research framework, not a scoring system. Judgement matters.',
          ].map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-900">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {point}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-6">
        {CHECKLIST.map(({ section, color, items }) => {
          const c = COLOR_MAP[color]
          return (
            <div key={section} className={`${c.bg} border ${c.border} rounded-2xl p-6`}>
              <h2 className={`font-bold ${c.text} mb-4 flex items-center gap-2`}>
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                {section}
              </h2>
              <ul className="space-y-3">
                {items.map(item => (
                  <li key={item} className="flex items-start gap-3">
                    <div className={`mt-1 w-4 h-4 rounded border-2 ${c.border} flex items-center justify-center shrink-0`}>
                      <div className={`w-2 h-2 rounded-sm ${c.dot} opacity-30`} />
                    </div>
                    <span className="text-sm text-slate-700 leading-relaxed">{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-6">
        <h2 className="font-bold text-slate-900 mb-4 flex items-center gap-2">
          <XCircle className="w-4 h-4 text-red-500 shrink-0" />
          Common red flags — investigate further if you see these
        </h2>
        <ul className="space-y-2">
          {[
            'Frequent capital raises (placements, rights issues) to fund ongoing operations — suggests the business cannot sustain itself from revenue',
            'Auditor qualifications or going-concern notes in the financial statements',
            'Sudden CEO or CFO departure with vague explanation',
            'Revenue growing but cash flow consistently negative over multiple years',
            'Excessive director selling while publicly positive statements are being made',
            'Guidance repeatedly missed — suggests management does not understand its own business',
            'Debt growing faster than revenue or EBITDA',
          ].map(flag => (
            <li key={flag} className="flex items-start gap-2 text-sm text-slate-600">
              <span className="mt-1.5 w-2 h-2 rounded-full bg-red-400 shrink-0" />
              {flag}
            </li>
          ))}
        </ul>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related Guides
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-research-asx-stocks-dyor', label: 'How to Research ASX Stocks: A DYOR Workflow' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/learn/how-to-read-company-announcements', label: 'How to Read ASX Company Announcements' },
            { href: '/learn/how-to-build-an-asx-watchlist', label: 'How to Build an ASX Watchlist' },
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
          <strong>Not financial advice.</strong> This checklist is a general educational framework only. It is not a recommendation to buy or sell any security. Always conduct your own research and consider advice from a licensed financial adviser before making investment decisions.
        </p>
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Find stocks to research using the Screener</h2>
        <p className="text-blue-100 mb-5 text-sm">Filter the ASX by PE ratio, ROE, dividend yield, debt, and 80+ more metrics to build your research shortlist.</p>
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
