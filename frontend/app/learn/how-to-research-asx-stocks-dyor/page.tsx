import Link from 'next/link'
import { ChevronLeft, BarChart2, Search, ArrowRight, AlertTriangle, Zap, BookOpen, FileText, TrendingUp } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata = {
  title: 'How to Research ASX Stocks: A Practical DYOR Workflow | ASX Screener',
  description:
    'A step-by-step DYOR (Do Your Own Research) workflow for ASX investors. Learn how to analyse a company\'s financials, announcements, management, and valuation before adding it to your watchlist.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-research-asx-stocks-dyor' },
}

const STEPS = [
  {
    n: 1, title: 'Understand the business model',
    body: 'Before looking at any numbers, understand what the company does and how it makes money. Read the "About" section of the annual report and the most recent investor presentation. Ask: What problem does this business solve? Who are its customers? How does it generate revenue — subscription, transaction, commodity, project?',
    tips: [
      'Annual report — letter to shareholders and operations review',
      'Latest investor presentation (filed on ASX)',
      'Company website and product/service pages',
    ],
  },
  {
    n: 2, title: 'Check the financial health',
    body: 'Review three core financial statements — income statement, balance sheet, and cash flow statement. You are looking for consistent revenue, positive or growing profit, manageable debt, and positive operating cash flow. A company can report accounting profit while burning cash — always check cash flow.',
    tips: [
      'Revenue trend over 3–5 years (growing, stable, or declining?)',
      'Net profit margin and whether it is improving',
      'Debt-to-equity ratio (under 1.0 is generally safer for non-financials)',
      'Operating cash flow — is the business generating real cash?',
    ],
  },
  {
    n: 3, title: 'Review valuation metrics',
    body: 'Once you understand the business and its financial health, assess whether the current share price reflects fair value. No single metric tells the full story — compare multiple measures and benchmark against sector peers.',
    tips: [
      'PE ratio vs. sector average and historical range',
      'EV/EBITDA for capital-intensive businesses',
      'Price-to-book for banks and financial stocks',
      'Dividend yield and grossed-up yield for income stocks',
    ],
  },
  {
    n: 4, title: 'Assess management and governance',
    body: 'Great businesses can be destroyed by poor management. Review who is running the company, how long they have been in their roles, and whether their incentives align with shareholders. Check for red flags like excessive related-party transactions or frequent director departures.',
    tips: [
      'Board composition and independence',
      'CEO and CFO tenure and track record',
      'Executive pay vs. company performance',
      'Director buying or selling their own shares (check ASX director interest notices)',
    ],
  },
  {
    n: 5, title: 'Read recent ASX announcements',
    body: 'ASX-listed companies must disclose material information to the market. The last 6–12 months of announcements give you a real-time picture of what is happening at the company — capital raises, trading updates, management changes, and strategy shifts.',
    tips: [
      'Trading updates and quarterly/half-year results',
      'Capital raising activity (placements, rights issues, SPPs)',
      'Trading halts — what triggered them?',
      'Director changes and their stated reasons',
    ],
  },
  {
    n: 6, title: 'Understand the risks',
    body: 'Every investment carries risk. Good research means identifying the specific risks for this company — not just generic market risk. Read the risk section of the annual report. Consider sector-specific risks: commodity price risk for miners, interest rate risk for REITs, regulatory risk for healthcare companies.',
    tips: [
      'Commodity or currency exposure',
      'Key person risk — does the business depend on one leader?',
      'Competitive landscape — is the business\'s advantage durable?',
      'Balance sheet — can the company survive a downturn without diluting shareholders?',
    ],
  },
  {
    n: 7, title: 'Form a view and add to your watchlist',
    body: 'After completing your research, form a view: does this business meet your criteria? If yes, add it to your watchlist and set a price alert at the level where you would consider investing. Revisit when results are released or material announcements are made.',
    tips: [
      'Document your thesis — write down why you think this stock is interesting',
      'Set a price level where valuation becomes attractive',
      'Schedule a review at the next half-year or full-year results',
      'Monitor ASX announcements for material changes',
    ],
  },
]

export default function DYORWorkflowPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'How to Research ASX Stocks', href: '/learn/how-to-research-asx-stocks-dyor' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner</span>
          <span className="text-xs text-slate-400">10 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Research ASX Stocks: A Practical DYOR Workflow
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          DYOR — Do Your Own Research — is the foundation of every sound investment decision. This workflow walks you through how to properly research an ASX stock, from understanding the business to assessing risk and forming a view.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Key Takeaways
        </h2>
        <ul className="space-y-2">
          {[
            'DYOR means forming your own view based on primary sources — annual reports, ASX announcements, and financial data — not tips or headlines.',
            'Research has 7 core areas: business model, financial health, valuation, management, announcements, risks, and your watchlist thesis.',
            'A stock screener helps you identify candidates. Research tells you whether those candidates are worth adding to your watchlist.',
            'Document your reasoning. Written notes help you review your thesis when conditions change.',
          ].map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-900">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {point}
            </li>
          ))}
        </ul>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
        <FileText className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <p className="text-sm text-amber-900">
          <strong>Where to find ASX company information:</strong> Every ASX-listed company must file announcements, financial reports, and investor presentations on the ASX website (asx.com.au → company search → announcements). Annual reports are usually filed in August/September.
        </p>
      </div>

      <div className="space-y-8 text-slate-700 leading-relaxed">

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">What does DYOR actually mean?</h2>
          <p>
            DYOR is not just a disclaimer — it is a mindset. It means forming your investment view from primary sources (company filings, financial statements, market data) rather than relying on secondhand opinions, analyst tips, or forum posts. It means understanding why a stock is in your portfolio, not just that someone told you to buy it.
          </p>
          <p className="mt-3">
            For ASX investors, primary sources are: ASX announcements, annual reports, half-year results, investor presentations, ASIC filings, and financial data providers. Everything else — articles, podcasts, social media — is secondary commentary on those sources.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-6">The 7-step DYOR workflow</h2>
          <div className="space-y-6">
            {STEPS.map(({ n, title, body, tips }) => (
              <div key={n} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-start gap-4">
                  <span className="w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold flex items-center justify-center shrink-0 mt-0.5">{n}</span>
                  <div className="flex-1">
                    <h3 className="font-bold text-slate-900 mb-2">{title}</h3>
                    <p className="text-sm text-slate-600 leading-relaxed mb-3">{body}</p>
                    <div className="bg-slate-50 rounded-lg p-3">
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">What to look at</p>
                      <ul className="space-y-1">
                        {tips.map(tip => (
                          <li key={tip} className="flex items-start gap-1.5 text-xs text-slate-600">
                            <Search className="w-3 h-3 text-blue-400 shrink-0 mt-0.5" />
                            {tip}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Using a screener in your DYOR workflow</h2>
          <p>
            A stock screener sits at the very beginning of your workflow — before step 1. Use it to narrow the 2,000+ ASX-listed companies down to a shortlist of candidates that meet your basic criteria. Then apply the 7-step DYOR process to each candidate.
          </p>
          <div className="mt-4 bg-slate-100 rounded-xl p-4">
            <div className="flex items-center gap-3 text-sm">
              <div className="flex items-center gap-2 bg-blue-600 text-white px-3 py-1.5 rounded-lg font-medium shrink-0">
                <TrendingUp className="w-3.5 h-3.5" /> Screener
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />
              <span className="text-slate-600">Shortlist of candidates matching your criteria</span>
              <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />
              <span className="text-slate-600 font-medium">DYOR on each one</span>
            </div>
          </div>
        </section>

      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-3">Useful Screener Filters for DYOR</h2>
        <div className="flex flex-wrap gap-2">
          {['Revenue Growth', 'Net Margin', 'ROE', 'Debt / Equity', 'Operating Cash Flow', 'PE Ratio', 'Days Since Last Announcement'].map(f => (
            <span key={f} className="text-xs font-medium bg-white border border-amber-300 text-amber-800 px-2.5 py-1 rounded-full">{f}</span>
          ))}
        </div>
        <Link href="/screener" className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-amber-700 hover:text-amber-900">
          Open the Screener <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Continue Learning
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/asx-stock-research-checklist', label: 'ASX Stock Research Checklist' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/learn/how-to-read-company-announcements', label: 'How to Read ASX Company Announcements' },
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
          <strong>Not financial advice.</strong> This article describes a general research process for educational purposes only. It does not constitute a recommendation to buy or sell any security. Always conduct your own research and consider consulting a licensed financial adviser.
        </p>
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Find your next research candidate</h2>
        <p className="text-blue-100 mb-5 text-sm">Use the screener to create a shortlist, then apply your DYOR workflow to each one.</p>
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
