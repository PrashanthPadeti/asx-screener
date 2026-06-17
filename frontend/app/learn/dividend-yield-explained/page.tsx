import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, Zap, BookOpen, TrendingDown } from 'lucide-react'

export const metadata = {
  title: 'Dividend Yield Explained for ASX Investors | ASX Screener',
  description:
    'What is dividend yield, how to calculate it, what counts as a good yield on the ASX, and how to spot yield traps. Includes grossed-up yield with franking credits for Australian investors.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/dividend-yield-explained' },
}

const YIELD_COMPARISON = [
  { type: 'Bank savings account',  yield: '~4–5%',    franked: 'No',   note: 'Risk-free but taxed as income' },
  { type: 'ASX 200 average',       yield: '~4%',      franked: 'Partial', note: 'Diversified market exposure' },
  { type: 'Big 4 banks (ASX)',     yield: '4.5–6%',   franked: 'Yes (100%)', note: 'High fully franked, grossed-up ~6.5–8.5%' },
  { type: 'ASX REITs',             yield: '5–7%',     franked: 'No (mostly)', note: 'High raw yield but unfranked distributions' },
  { type: 'Speculative small-cap', yield: '8–12%+',   franked: 'Often No', note: 'May be unsustainable — check payout ratio' },
]

export default function DividendYieldExplainedPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Link href="/learn" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-blue-600 transition-colors">
        <ChevronLeft className="w-4 h-4" />
        Education Hub
      </Link>

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner</span>
          <span className="text-xs text-slate-400">8 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Dividend Yield Explained for ASX Investors
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Dividend yield is one of the most widely used metrics for income investing on the ASX — and one of the most misunderstood. Here is what it means, how to calculate it, what a good yield looks like, and how to avoid the yield trap.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Key Takeaways
        </h2>
        <ul className="space-y-2">
          {[
            'Dividend yield = annual dividend per share ÷ share price × 100. It rises when the share price falls, and falls when the share price rises.',
            'For ASX investors, always calculate grossed-up yield — which adds franking credits back into the effective return.',
            'A high yield is not automatically good. A stock with a 10% yield may be priced that way because the market expects the dividend to be cut.',
            'A sustainable yield requires a manageable payout ratio (ideally under 80% of earnings for most sectors).',
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
          <h2 className="text-xl font-bold text-slate-900 mb-3">What is dividend yield?</h2>
          <p>
            Dividend yield measures how much a company pays out in dividends relative to its share price. It expresses the income return of a stock as a percentage of what you pay for it.
          </p>
          <div className="mt-4 bg-slate-900 rounded-xl p-4">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Formula</p>
            <code className="text-emerald-300 font-mono text-sm leading-relaxed block">
              Dividend Yield = (Annual Dividend Per Share ÷ Share Price) × 100
            </code>
          </div>
          <div className="mt-4 bg-sky-50 border border-sky-200 rounded-xl p-4 text-sm text-sky-900">
            <p className="font-medium mb-1">Example:</p>
            <p>A stock trades at <strong>$20.00</strong> and pays an annual dividend of <strong>$0.80/share</strong>.</p>
            <p className="mt-1">Dividend Yield = $0.80 ÷ $20.00 × 100 = <strong>4.0%</strong></p>
            <p className="mt-2 text-sky-700">If the share price falls to $16.00 and the dividend stays the same, the yield rises to 5.0% — this is why a falling share price can make a yield look more attractive even when nothing has improved at the company.</p>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Grossed-up yield — the Australian advantage</h2>
          <p>
            For Australian resident investors, the raw dividend yield understates the true return when the dividend is franked. Franking credits reduce the income tax you pay on dividends — or, for SMSFs in pension phase, generate a cash refund from the ATO.
          </p>
          <div className="mt-4 bg-slate-900 rounded-xl p-4">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Grossed-Up Yield Formula</p>
            <code className="text-emerald-300 font-mono text-sm leading-relaxed block whitespace-pre-wrap">
{`Grossed-Up Yield = Dividend Yield × (1 + Franking% × 0.4286)

where 0.4286 = 30% ÷ (1 − 30%)`}
            </code>
          </div>
          <div className="mt-4 bg-sky-50 border border-sky-200 rounded-xl p-4 text-sm text-sky-900">
            <p className="font-medium mb-1">Example:</p>
            <p>A stock with a 4% raw yield, 100% franked:</p>
            <p className="mt-1">Grossed-Up Yield = 4% × (1 + 1.0 × 0.4286) = 4% × 1.4286 = <strong>5.71%</strong></p>
            <p className="mt-2 text-sky-700">A 43% effective bonus in pre-tax yield terms, purely from franking — not captured in the raw yield figure.</p>
          </div>
          <Link href="/learn/franking-credits-explained" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800">
            Full guide to franking credits <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
          </Link>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">What is a good dividend yield on the ASX?</h2>
          <p>
            There is no single answer — it depends on the sector, interest rate environment, and the investor's marginal tax rate. As a general reference:
          </p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-slate-100">
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Type of stock</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Typical yield</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Franked?</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Notes</th>
                </tr>
              </thead>
              <tbody>
                {YIELD_COMPARISON.map(({ type, yield: y, franked, note }) => (
                  <tr key={type} className="border border-slate-200 hover:bg-slate-50">
                    <td className="px-3 py-2 font-medium">{type}</td>
                    <td className="px-3 py-2">{y}</td>
                    <td className="px-3 py-2">{franked}</td>
                    <td className="px-3 py-2 text-slate-500 text-xs">{note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3 flex items-center gap-2">
            <TrendingDown className="w-5 h-5 text-red-500" />
            The yield trap — when a high yield is a warning signal
          </h2>
          <p>
            A high dividend yield is not always a sign of value. Sometimes it reflects a falling share price — the market has priced the stock down because it expects the dividend to be cut, the business to deteriorate, or significant risk ahead. This is the yield trap.
          </p>
          <div className="mt-4 bg-red-50 border border-red-200 rounded-xl p-4">
            <p className="text-sm font-semibold text-red-800 mb-2">Signs a high yield may be unsustainable:</p>
            <ul className="space-y-1.5">
              {[
                'Payout ratio above 100% — the company is paying out more than it earns',
                'Negative or deteriorating operating cash flow',
                'Earnings declining while the dividend has not yet been cut',
                'The company has repeatedly raised equity capital to fund dividends',
                'The yield is far above the sector average without a clear quality reason',
              ].map(item => (
                <li key={item} className="flex items-start gap-2 text-sm text-red-900">
                  <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Payout ratio — measuring dividend sustainability</h2>
          <p>
            The payout ratio tells you what percentage of earnings a company distributes as dividends. A lower payout ratio means the company retains more earnings for reinvestment and has more buffer before a dividend cut.
          </p>
          <div className="mt-4 bg-slate-900 rounded-xl p-4">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Formula</p>
            <code className="text-emerald-300 font-mono text-sm block">
              Payout Ratio = (Dividends Per Share ÷ Earnings Per Share) × 100
            </code>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-slate-100">
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Payout Ratio</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Interpretation</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['Under 50%', 'Low payout — room to grow the dividend and reinvest in the business'],
                  ['50%–80%', 'Moderate — common for mature, stable businesses (banks, consumer staples)'],
                  ['80%–100%', 'High — monitor closely; little buffer if earnings disappoint'],
                  ['Over 100%', 'Paying out more than earned — not sustainable; dividend cut risk is elevated'],
                ].map(([ratio, interp]) => (
                  <tr key={ratio} className="border border-slate-200 hover:bg-slate-50">
                    <td className="px-3 py-2 font-medium">{ratio}</td>
                    <td className="px-3 py-2 text-slate-600">{interp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-3">Screen for Dividend Stocks on the ASX</h2>
        <div className="flex flex-wrap gap-2">
          {['Dividend Yield', 'Grossed-Up Yield', 'Franking %', 'Payout Ratio', 'Dividend CAGR 3Y', 'Dividend Coverage'].map(f => (
            <span key={f} className="text-xs font-medium bg-white border border-amber-300 text-amber-800 px-2.5 py-1 rounded-full">{f}</span>
          ))}
        </div>
        <Link href="/screener" className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-amber-700 hover:text-amber-900">
          Run a Dividend Screen <ChevronLeft className="w-4 h-4 rotate-180" />
        </Link>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related Guides
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained — The ASX Investor\'s Guide' },
            { href: '/learn/how-to-build-an-asx-watchlist', label: 'How to Build an ASX Watchlist' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/glossary', label: 'Metrics Glossary — Dividend Yield, Payout Ratio & more' },
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
          <strong>Not financial advice.</strong> Dividend yield metrics are tools for research and comparison, not a recommendation to buy or sell any security. Past dividend payments do not guarantee future payments. Always conduct your own research and consider advice from a licensed financial adviser.
        </p>
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Screen for ASX income stocks</h2>
        <p className="text-blue-100 mb-5 text-sm">Filter by dividend yield, grossed-up yield, franking %, payout ratio, and 80+ more metrics. Free to use.</p>
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
