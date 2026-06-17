import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, DollarSign, PieChart, Shield } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata = {
  title: 'Building a Dividend Portfolio on the ASX | ASX Screener',
  description:
    'How to construct a diversified ASX income portfolio — sector allocation, stock selection criteria, franking credits, reinvestment, and common mistakes to avoid.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/building-an-asx-dividend-portfolio' },
}

const SECTORS = [
  { sector: 'Financials (Banks + Insurance)', alloc: '20–30%', note: 'Big Four banks dominate ASX income. Highly franked, consistent payers. Concentration risk — cap individual bank positions.' },
  { sector: 'Consumer Staples', alloc: '10–15%', note: 'Woolworths, Coles, Treasury Wine. Defensive earnings and reliable dividends through the cycle.' },
  { sector: 'Healthcare', alloc: '10–15%', note: 'CSL, Sonic, Ramsay. Lower yields but growing dividends backed by strong earnings and demographic tailwinds.' },
  { sector: 'Utilities / Infrastructure', alloc: '10–15%', note: 'APA, AGL, Transurban. Regulated revenue streams. Capital-intensive but predictable cash flows support consistent distributions.' },
  { sector: 'A-REITs', alloc: '10–20%', note: 'Goodman, Scentre, Dexus. High distribution yields but lower franking. Sensitive to interest rate moves.' },
  { sector: 'Industrials', alloc: '10–15%', note: 'Broad category. Seek asset-light businesses with strong free cash flow conversion and dividend growth track records.' },
  { sector: 'Materials (Selective)', alloc: '5–10%', note: 'Some large miners pay substantial dividends at peak cycle. Cyclical — size positions conservatively and don\'t rely on them for baseline income.' },
]

const SELECTION_CRITERIA = [
  { criterion: 'Dividend yield 3–7%', detail: 'Yields above 7% on the ASX are rare for sustainable businesses. Below 3% for an income portfolio means you\'re sacrificing yield without enough growth to compensate.' },
  { criterion: 'Payout ratio below 75%', detail: 'Leaves enough room for earnings to soften without forcing a cut. REITs are the exception — 90%+ payout is normal.' },
  { criterion: 'Dividend paid for 5+ consecutive years', detail: 'Track record of consistency is one of the strongest signals of management\'s commitment to income shareholders.' },
  { criterion: 'Dividend growing or stable — not shrinking', detail: 'Even flat dividends erode real value through inflation. Aim for dividend growth at or above CPI over time.' },
  { criterion: 'Franking credits ≥ 50%', detail: 'Fully franked dividends are significantly more valuable on an after-tax basis for Australian resident investors in a 30–45% tax bracket.' },
  { criterion: 'Free cash flow covers dividends', detail: 'Dividends should be funded from operating cash flow — not debt or asset sales. Check FCF payout ratio, not just earnings payout ratio.' },
  { criterion: 'Net debt/EBITDA below 2.5×', detail: 'Excessive debt is the most common reason for unexpected dividend cuts. Leave room for rates to rise or earnings to soften.' },
]

const MISTAKES = [
  { mistake: 'Concentrating in the Big Four banks', why: 'ANZ, CBA, NAB, and WBC can easily become 50%+ of an ASX income portfolio. A single sector event (housing downturn, credit crunch, regulatory change) hits all four simultaneously.' },
  { mistake: 'Chasing the highest yield', why: 'A 9% yield that gets cut to 4% — with a 30% share price fall on the cut — produces a significantly worse outcome than a steady 5% yield that grows every year.' },
  { mistake: 'Ignoring total return', why: 'Income investing is not the same as ignoring share price. A stock that pays 6% while the share price falls 10% per year is destroying wealth.' },
  { mistake: 'Forgetting to check franking', why: 'Two dividends of 5% yield can be very different after tax: fully franked vs. unfranked. The grossed-up yield on a fully franked 5% is approximately 7.1% for a 30% tax rate investor.' },
  { mistake: 'Not reinvesting during accumulation phase', why: 'Dividend reinvestment (DRP or manual) is one of the most powerful compounders available. A portfolio that reinvests dividends for 20 years vastly outperforms one that spends them.' },
  { mistake: 'Treating special dividends as recurring', why: 'Miners and some industrials pay large special dividends in strong years. These are not part of the base dividend and should not be used to calculate sustainable yield.' },
]

export default function BuildingDividendPortfolioPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'Building an ASX Dividend Portfolio', href: '/learn/building-an-asx-dividend-portfolio' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Intermediate</span>
          <span className="text-xs text-slate-400">12 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Building a Dividend Portfolio on the ASX
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          The ASX is one of the best markets in the world for income investors — high dividend yields, franking credits, and a deep pool of quality businesses with long dividend histories. This guide walks through how to construct a diversified ASX income portfolio from the ground up.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Dividend Stocks</p>
          <p className="text-blue-200 text-sm">Filter by yield, payout ratio, franking, dividend cover and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Why the ASX suits income investors</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          The ASX300 has one of the highest average dividend yields of any major market — typically 4–5% including franking credits — compared to 1–2% for the S&P 500. This is partly structural: Australian companies have a strong cultural tradition of returning capital to shareholders, reinforced by the franking credit system which makes retained earnings tax-inefficient for many businesses.
        </p>
        <p className="text-slate-600 leading-relaxed">
          Franking credits add significant value on top of the cash yield. A fully franked 5% dividend is equivalent to approximately 7.1% gross yield for an investor in the 30% tax bracket — one of the most tax-efficient income sources available to Australian investors.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <DollarSign className="w-4 h-4" /> The franking credit advantage
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed mb-3">
          Franking credits reduce the double-taxation of corporate profits. When a company pays tax at 30% and then distributes the after-tax profit as a dividend, the franking credit attached to that dividend reduces your personal tax liability by the amount of corporate tax already paid.
        </p>
        <div className="bg-slate-900 rounded-xl p-3 font-mono text-xs text-emerald-300 leading-relaxed">
          {`Cash dividend:        $0.70 per share
Franking credit:      $0.30 per share  (30% corporate tax paid)
Grossed-up dividend:  $1.00 per share
─────────────────────────────────────────
Cash yield:           5.0%
Grossed-up yield:     7.1%  (for a 30% marginal rate investor)`}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <PieChart className="w-5 h-5 text-slate-500" />
          Sector allocation framework
        </h2>
        <p className="text-slate-500 text-sm mb-4">A diversified ASX income portfolio typically spreads across 5–7 sectors. Suggested allocation ranges — adjust based on your risk tolerance and income goals:</p>
        <div className="space-y-2">
          {SECTORS.map(({ sector, alloc, note }) => (
            <div key={sector} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
                <p className="font-semibold text-slate-900 text-sm">{sector}</p>
                <span className="text-xs font-mono font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full">{alloc}</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{note}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400 mt-3 leading-relaxed">
          No single stock should represent more than 8–10% of the portfolio. No single sector more than 30%. The ASX is heavily weighted toward financials and materials — a passive approach will result in heavy concentration in these two sectors.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Shield className="w-5 h-5 text-slate-500" />
          Stock selection criteria
        </h2>
        <div className="space-y-3">
          {SELECTION_CRITERIA.map(({ criterion, detail }) => (
            <div key={criterion} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-semibold text-slate-900 text-sm mb-1">{criterion}</p>
              <p className="text-xs text-slate-500 leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example portfolio screens</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Core income holdings screen',
              desc: 'Quality large-cap dividend payers with strong coverage — suitable as portfolio anchors.',
              filters: [
                'dividend_yield > 4',
                'franking_pct >= 75',
                'payout_ratio < 75',
                'dividend_growth_3y > 0',
                'market_cap > 2000',
                'net_debt_to_ebitda < 2.5',
              ],
            },
            {
              name: 'Dividend growth compounders',
              desc: 'Lower current yield but growing fast — builds income over time through compounding.',
              filters: [
                'dividend_growth_3y > 7',
                'dividend_yield > 2.5',
                'payout_ratio < 60',
                'eps_growth_1y > 5',
                'roe > 12',
              ],
            },
          ].map(({ name, desc, filters }) => (
            <div key={name} className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
              <h3 className="font-bold text-slate-900 mb-1">{name}</h3>
              <p className="text-xs text-slate-500 mb-3">{desc}</p>
              <div className="bg-slate-900 rounded-xl p-3">
                <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{filters.join('\n')}</code>
              </div>
              <Link href="/screener" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800">
                Apply this screen <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
              </Link>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Dividend reinvestment vs. taking income</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-3">
          If you are in the accumulation phase (building wealth, not yet drawing income), reinvesting dividends is one of the most effective compounding strategies available. Most large ASX dividend payers offer a Dividend Reinvestment Plan (DRP) — new shares issued at a small discount instead of cash.
        </p>
        <p className="text-slate-600 text-sm leading-relaxed mb-3">
          If you are in the income phase (drawing on the portfolio for living expenses), taking dividends as cash gives you flexibility — you choose which positions to trim rather than automatically adding to everything.
        </p>
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
          <p className="text-sm text-emerald-900 leading-relaxed">
            <strong>Rule of thumb:</strong> If you don&apos;t need the cash, reinvest. The long-run impact of reinvesting a 5% dividend over 20 years is enormous — roughly 2.7× more wealth than a portfolio that spends dividends, assuming the same total return.
          </p>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Common mistakes to avoid</h2>
        <div className="space-y-3">
          {MISTAKES.map(({ mistake, why }) => (
            <div key={mistake} className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="font-semibold text-amber-900 text-sm mb-1">{mistake}</p>
              <p className="text-xs text-amber-700 leading-relaxed">{why}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-check-asx-dividend-sustainability', label: 'How to Check If an ASX Dividend Is Sustainable' },
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained for ASX Investors' },
            { href: '/learn/franking-credits-explained', label: 'Understanding Franking Credits' },
            { href: '/learn/how-to-screen-asx-stocks-for-beginners', label: 'How to Screen ASX Stocks for Beginners' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
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
          <strong>Not financial advice.</strong> This article is for educational purposes only. Past dividend history does not guarantee future payments. Consider advice from a licensed financial adviser before making investment decisions, particularly regarding tax treatment of franking credits.
        </p>
      </div>

    </div>
  )
}
