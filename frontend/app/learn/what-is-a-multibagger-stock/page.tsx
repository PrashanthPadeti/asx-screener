import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, TrendingUp, Zap } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'What Is a Multibagger Stock? | ASX Screener',
  description:
    'What multibagger stocks are, the traits they share before becoming big winners, and why growth, quality, reinvestment, and patience are the core ingredients.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/what-is-a-multibagger-stock' },
}

const TRAITS = [
  { trait: 'Strong and sustained revenue growth', detail: 'A company cannot become a 5x or 10x stock if the business itself is not growing. Long-term revenue CAGR above 10% over 5–10 years is the starting point for most multibaggers.' },
  { trait: 'Growing earnings per share (EPS)', detail: 'Revenue growth without profit growth is not enough. EPS growth shows that the company is not just selling more — it is converting growth into shareholder value. EPS CAGR above 15% over 5–10 years is a strong signal.' },
  { trait: 'High Return on Invested Capital (ROIC)', detail: 'ROIC above 15% consistently means the company earns more from every dollar deployed than it costs to deploy it. This is the single most powerful quality signal. A high-ROIC business can reinvest profits and compound at its own rate of return.' },
  { trait: 'Strong cash flow conversion', detail: 'Profits on paper are not always profits in the bank. Cash conversion above 80% (FCF ÷ net income) confirms that reported earnings are translating into real cash — the lifeblood of reinvestment and dividends.' },
  { trait: 'Ability to reinvest at high returns', detail: 'The most powerful compounders reinvest most of their free cash flow back into the business — not paid out as dividends. A low payout ratio (below 25–30%) combined with high ROIC creates a compounding engine.' },
  { trait: 'Manageable debt', detail: 'High debt amplifies both gains and losses — but mostly losses in a downturn. Multibaggers typically have manageable debt levels and strong interest coverage (above 10×), giving them the flexibility to survive hard years and invest through cycles.' },
  { trait: 'Long growth runway', detail: 'A company can only grow for many years if the market opportunity is large and still expanding. Multibaggers often operate in industries that are themselves growing — or are taking market share from competitors in larger markets.' },
  { trait: 'Reasonable starting valuation', detail: 'Even the best business can be a poor investment if bought at an unreasonable price. Multibaggers are often identified before the market fully recognises their quality — when P/E or PEG ratios are still sensible rather than stretched.' },
]

export default function WhatIsAMultibaggerStockPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="What Is a Multibagger Stock?"
        description="What multibagger stocks are, the traits they share before becoming big winners, and why growth, quality, reinvestment, and patience are the core ingredients."
        url="https://asxscreener.com.au/learn/what-is-a-multibagger-stock"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'What Is a Multibagger Stock?', href: '/learn/what-is-a-multibagger-stock' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner</span>
          <span className="text-xs text-slate-400">8 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          What Is a Multibagger Stock?
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          A multibagger is a stock that grows many times its original price — 2×, 5×, 10×, or even 100× over the long term. But multibaggers rarely happen by luck. The biggest long-term winners share a set of common traits, and understanding those traits is the first step to finding them before the crowd does.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-2xl p-5 hover:from-emerald-700 hover:to-teal-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen for Multibagger Candidates</p>
          <p className="text-emerald-200 text-sm">Filter by ROIC, revenue CAGR, EPS growth, FCF, PEG ratio and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What does &quot;multibagger&quot; mean?</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          The term was coined by legendary investor Peter Lynch in his book <em>One Up on Wall Street</em>. &quot;Bagger&quot; comes from cricket — a two-bagger doubles your money, a ten-bagger grows it ten times, and so on. A 100-bagger, the holy grail, turns $10,000 into $1,000,000.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: '2-bagger', desc: 'Doubles', example: '$10K → $20K' },
            { label: '5-bagger', desc: 'Grows 5×', example: '$10K → $50K' },
            { label: '10-bagger', desc: 'Grows 10×', example: '$10K → $100K' },
            { label: '100-bagger', desc: 'Grows 100×', example: '$10K → $1M' },
          ].map(({ label, desc, example }) => (
            <div key={label} className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-center">
              <p className="font-bold text-emerald-900 text-sm">{label}</p>
              <p className="text-xs text-emerald-700">{desc}</p>
              <p className="text-xs text-slate-500 mt-1 font-mono">{example}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-slate-500" />
          8 traits most multibaggers share
        </h2>
        <p className="text-slate-500 text-sm mb-4">These traits are observable <em>before</em> the stock becomes a big winner — not after. That&apos;s what makes them useful for screening.</p>
        <div className="space-y-3">
          {TRAITS.map(({ trait, detail }, i) => (
            <div key={trait} className="bg-white border border-slate-200 rounded-xl p-4 flex gap-3">
              <span className="w-6 h-6 rounded-full bg-slate-800 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
              <div>
                <p className="font-semibold text-slate-900 text-sm mb-1">{trait}</p>
                <p className="text-xs text-slate-500 leading-relaxed">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-900 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4 text-emerald-400" /> The multibagger formula (simplified)
        </h2>
        <div className="space-y-1 text-sm text-slate-300">
          {[
            'Long-Term Revenue + Earnings Growth',
            '+ High ROIC (reinvestment at high rates of return)',
            '+ Strong Free Cash Flow',
            '+ Reinvestment Opportunity (long runway)',
            '+ Good Management',
            '+ Reasonable Valuation',
            '+ Patience',
          ].map((line, i) => (
            <p key={i} className={`font-mono text-xs ${i === 0 ? 'text-emerald-300' : ''}`}>{line}</p>
          ))}
          <div className="border-t border-slate-700 mt-3 pt-3">
            <p className="text-emerald-300 font-mono text-xs">= Potential Multibagger Candidate</p>
            <p className="text-slate-500 text-xs mt-1">Not guaranteed — only worth researching deeply.</p>
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Why most multibaggers take time</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          A 10-bagger over 25 years requires only 10% annual return. The same result over 10 years requires 26% per year — much harder to achieve consistently. Most genuine multibaggers are not fast stories. They are businesses that compound quietly for a long time.
        </p>
        <p className="text-slate-600 leading-relaxed">
          This is why the world&apos;s best multibagger investors — Lynch, Buffett, Munger, Fisher — all emphasise patience above almost everything else. Finding the business is hard. Holding it through volatility, temporary setbacks, and boring periods is harder.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">A screening shortlist is just the start</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          A stock screener can identify candidates that match the quantitative traits above. What it cannot do is judge the quality of management, the durability of the competitive advantage, the size of the growth runway, or whether the company&apos;s best days are ahead or behind it.
        </p>
        <p className="text-slate-600 leading-relaxed">
          The correct process is: screen → shortlist → understand the business → check valuation → check risks → add to watchlist → follow results over time → decide carefully. The screen is step one, not the final answer.
        </p>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-screen-for-asx-multibagger-stocks', label: 'How to Screen for ASX Multibagger Stocks' },
            { href: '/learn/lessons-from-successful-multibagger-investors', label: 'Lessons from the World\'s Best Multibagger Investors' },
            { href: '/learn/how-to-find-quality-asx-companies', label: 'How to Find Quality ASX Companies' },
            { href: '/learn/roic-explained', label: 'ROIC Explained: Return on Invested Capital' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> Past multibagger performance does not indicate future returns. All investing involves risk. Always conduct your own research before making investment decisions.</p>
      </div>
    </div>
  )
}
