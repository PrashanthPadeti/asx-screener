import Link from 'next/link'
import { ChevronLeft, BarChart2, Bell, Eye, AlertTriangle, Zap, BookOpen, TrendingUp, CheckCircle2 } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How to Build and Maintain an ASX Watchlist | ASX Screener',
  description:
    'Learn how to build and maintain an ASX stock watchlist. Covers how to choose stocks for your watchlist, what to monitor, when to set price alerts, and how to manage your watchlist over time.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-build-an-asx-watchlist' },
}

export default function HowToBuildWatchlistPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema headline="How to Build and Maintain an ASX Watchlist" description="Learn how to build and maintain an ASX stock watchlist. Covers how to choose stocks for your watchlist, what to monitor, when to set price alerts, and how to manage your watchlist over time." url="https://asxscreener.com.au/learn/how-to-build-an-asx-watchlist" />
      <Breadcrumb crumbs={[{ label: 'Education Hub', href: '/learn' }, { label: 'How to Build an ASX Watchlist', href: '/learn/how-to-build-an-asx-watchlist' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner</span>
          <span className="text-xs text-slate-400">7 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Build and Maintain an ASX Watchlist
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          A watchlist is how disciplined investors stay organised. It separates stocks worth monitoring from the noise — and ensures you are ready when a price moves into a range you find attractive.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Key Takeaways
        </h2>
        <ul className="space-y-2">
          {[
            'A watchlist contains stocks you have researched and found interesting — but are not yet ready to act on.',
            'Each stock on your watchlist should have a documented reason for being there and a price level you find attractive.',
            'Price alerts notify you when a stock enters your target range — so you are not constantly checking prices.',
            'Review your watchlist at every half-year and full-year result for each company on it.',
          ].map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-900">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {point}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-8 text-slate-700 leading-relaxed">

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">What is a watchlist and why does it matter?</h2>
          <p>
            A watchlist is a curated list of ASX stocks you have researched and are actively monitoring. It is not a portfolio — you do not own these stocks. It is a pipeline of companies you understand well enough to act quickly if conditions change.
          </p>
          <p className="mt-3">
            Without a watchlist, most investors react to news and price movements impulsively. With one, you have pre-done the research, know the business, and have a price level in mind. When a stock hits that level, you review your thesis rather than scramble to understand a company from scratch under time pressure.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Step 1 — Screen for candidates</h2>
          <p>
            Your watchlist starts with a screener. Use the ASX Screener to filter the market down to companies that meet your general criteria — quality, valuation, income, or sector. This creates a candidate list that you will then research individually.
          </p>
          <div className="mt-4 bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm">
            <p className="font-semibold text-slate-700 mb-2">Example starting screen for a quality income watchlist:</p>
            <ul className="space-y-1 text-slate-600 font-mono text-xs">
              <li>Dividend Yield &gt; 3.5%</li>
              <li>Franking % = 100%</li>
              <li>Payout Ratio &lt; 80%</li>
              <li>ROE &gt; 10%</li>
              <li>Debt / Equity &lt; 1.0</li>
            </ul>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Step 2 — Research each candidate</h2>
          <p>
            Not every stock that passes your screen belongs on your watchlist. Research each candidate using a structured process — understanding the business, reviewing financials, assessing valuation and management, and reading recent announcements. Only stocks that survive your research process make the watchlist.
          </p>
          <Link href="/learn/how-to-research-asx-stocks-dyor" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800">
            Full DYOR research workflow <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
          </Link>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Step 3 — Add with a documented thesis</h2>
          <p>
            When you add a stock to your watchlist, document why. A thesis does not need to be long — two or three sentences is enough:
          </p>
          <div className="mt-4 bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm text-emerald-900">
            <p className="font-medium mb-1">Example thesis note:</p>
            <p className="italic">
              "High-quality bank with 100% franking, consistent dividend history over 10 years, and strong ROE. Currently trading at a PE of 14x which is above my fair value estimate of ~12x. Watchlist entry at $25 — represents ~5% grossed-up yield which is attractive for income."
            </p>
          </div>
          <p className="mt-3">
            This written thesis does two things: it forces you to be clear about why the stock is interesting, and it gives you something to check when conditions change later.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Step 4 — Set price alerts</h2>
          <p>
            Once a stock is on your watchlist with a documented thesis and target price, set a price alert. An alert notifies you when the share price reaches your target level — so you are not checking prices every day but you will not miss your opportunity.
          </p>
          <div className="mt-4 grid sm:grid-cols-2 gap-4">
            {[
              { icon: Bell, title: 'Price target alert', desc: 'Triggers when the stock reaches the price you identified as attractive based on your valuation.' },
              { icon: TrendingUp, title: 'Volume or movement alert', desc: 'Triggers on unusual price or volume activity — often signals a material announcement is coming or has just landed.' },
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} className="bg-white border border-slate-200 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="w-4 h-4 text-blue-500 shrink-0" />
                  <span className="font-semibold text-sm text-slate-800">{title}</span>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
          <Link href="/alerts" className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800">
            Set up price alerts <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
          </Link>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Step 5 — Maintain the watchlist over time</h2>
          <p>
            A watchlist that is never reviewed becomes noise. Schedule a regular review — at minimum, review each stock when it reports results (usually half-year in February and full-year in August for June-year companies).
          </p>
          <div className="mt-4 space-y-3">
            {[
              { title: 'Review at results', desc: 'Read the half-year and full-year result. Does the business still meet your criteria? Has anything changed in the thesis?' },
              { title: 'Review on material announcements', desc: 'A capital raise, management change, or trading update may change your view. Your alert will flag unusual activity.' },
              { title: 'Remove stale entries', desc: 'If a company\'s fundamentals have deteriorated, the thesis has changed, or the price has moved well above your target, remove it. A watchlist is only useful if it is current.' },
              { title: 'Add new candidates from regular screening', desc: 'Run a fresh screen every 1–3 months to discover new candidates — the market changes and new opportunities emerge.' },
            ].map(({ title, desc }) => (
              <div key={title} className="flex items-start gap-3">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-slate-800 text-sm">{title}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">How many stocks should be on a watchlist?</h2>
          <p>
            There is no perfect number. A focused watchlist of 10–20 stocks you understand well is more useful than 200 stocks you added without real research. The constraint is the quality of your research, not the size of the list. If you cannot articulate the thesis for a stock in two sentences, it may not belong on your watchlist yet.
          </p>
        </section>

      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-3">Useful Screener Filters for Watchlist Building</h2>
        <div className="flex flex-wrap gap-2">
          {['Dividend Yield', 'Grossed-Up Yield', 'Franking %', 'ROE', 'PE Ratio', 'Payout Ratio', 'Market Cap'].map(f => (
            <span key={f} className="text-xs font-medium bg-white border border-amber-300 text-amber-800 px-2.5 py-1 rounded-full">{f}</span>
          ))}
        </div>
        <Link href="/screener" className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-amber-700 hover:text-amber-900">
          Start Screening <ChevronLeft className="w-4 h-4 rotate-180" />
        </Link>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related Guides
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-research-asx-stocks-dyor', label: 'How to Research ASX Stocks: A DYOR Workflow' },
            { href: '/learn/asx-stock-research-checklist', label: 'ASX Stock Research Checklist' },
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained for ASX Investors' },
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
          <strong>Not financial advice.</strong> A watchlist is a personal research tool. Nothing in this guide constitutes a recommendation to buy or sell any security. Always conduct your own research and consider advice from a licensed financial adviser.
        </p>
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Build your ASX watchlist now</h2>
        <p className="text-blue-100 mb-5 text-sm">Screen for candidates, research them, and save the ones worth monitoring — all in one place.</p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link href="/screener" className="inline-flex items-center gap-2 bg-white text-blue-700 font-semibold px-5 py-2.5 rounded-xl hover:bg-blue-50 transition-colors">
            <BarChart2 className="w-4 h-4" /> Open the Screener
          </Link>
          <Link href="/watchlist" className="inline-flex items-center gap-2 bg-blue-500 hover:bg-blue-400 text-white font-semibold px-5 py-2.5 rounded-xl transition-colors">
            <Eye className="w-4 h-4" /> My Watchlist
          </Link>
        </div>
      </div>

    </div>
  )
}
