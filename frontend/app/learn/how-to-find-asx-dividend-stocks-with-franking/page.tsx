import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, DollarSign, Zap } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'How to Find ASX Dividend Stocks with Franking Credits | ASX Screener',
  description:
    'How to screen for ASX dividend stocks that pay fully franked or partially franked dividends. Includes key metrics, example screens, and what to check before investing.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-find-asx-dividend-stocks-with-franking' },
}

const SCREEN_STEPS = [
  { step: 'Set minimum dividend yield', detail: 'Start at 3.5–4% to filter out low-yielding stocks while keeping quality large-caps in the results.' },
  { step: 'Set minimum franking percentage', detail: 'Filter for franking_pct ≥ 75 to focus on substantially franked dividends. Set to 100 for fully franked only.' },
  { step: 'Cap the payout ratio', detail: 'payout_ratio < 80 ensures the dividend has room to survive an earnings dip. This removes the most stretched payers.' },
  { step: 'Filter out excessive debt', detail: 'debt_to_equity < 1 or net_debt_to_ebitda < 2.5 keeps out companies where debt may force a future dividend cut.' },
  { step: 'Set a minimum market cap', detail: 'market_cap > 500 keeps the screen focused on established companies with more predictable dividend histories.' },
  { step: 'Review results', detail: 'Sort by grossed-up yield (if shown) or calculate manually. Open each company\'s profile to check the 3–5 year dividend trend before adding to your shortlist.' },
]

const TAX_TABLE = [
  { rate: '0% (super pension phase)', cashYield: '5.0%', frankingCredit: '2.14%', grossedUp: '7.14%', taxSaving: '+2.14%' },
  { rate: '15% (super accumulation)', cashYield: '5.0%', frankingCredit: '2.14%', grossedUp: '7.14%', taxSaving: '+1.50%' },
  { rate: '32.5% (mid marginal rate)', cashYield: '5.0%', frankingCredit: '2.14%', grossedUp: '7.14%', taxSaving: '+0.68%' },
  { rate: '45% (top marginal rate)', cashYield: '5.0%', frankingCredit: '2.14%', grossedUp: '7.14%', taxSaving: '−0.21% (net refund at 0%)' },
]

export default function HowToFindFrankingPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="How to Find ASX Dividend Stocks with Franking Credits"
        description="How to screen for ASX dividend stocks that pay fully franked or partially franked dividends. Includes key metrics, example screens, and what to check before investing."
        url="https://asxscreener.com.au/learn/how-to-find-asx-dividend-stocks-with-franking"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'ASX Dividend Stocks with Franking', href: '/learn/how-to-find-asx-dividend-stocks-with-franking' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner–Intermediate</span>
          <span className="text-xs text-slate-400">9 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Find ASX Dividend Stocks with Franking Credits
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Australia&apos;s franking credit system makes high-yield ASX dividend stocks significantly more valuable than their face yield suggests. This guide shows you how to screen for them, what to look for beyond the raw yield, and how franking credits affect your actual after-tax return.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-2xl p-5 hover:from-emerald-700 hover:to-teal-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Franked Dividend Stocks</p>
          <p className="text-emerald-200 text-sm">Filter by dividend yield, franking %, payout ratio, and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Why franking credits matter</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          When an Australian company pays tax at the 30% corporate rate and then distributes its after-tax profit as a dividend, it can attach a &quot;franking credit&quot; representing the tax already paid. This credit offsets your personal tax liability — meaning you don&apos;t pay tax twice on the same income.
        </p>
        <div className="bg-slate-900 rounded-xl p-4 mb-4">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{`Cash dividend:          $0.70
Franking credit:        $0.30  (30% tax already paid by the company)
Grossed-up dividend:    $1.00
─────────────────────────────
For a 30% tax rate investor: the $0.30 credit offsets your tax bill dollar-for-dollar
Net result: you pay no additional tax on this dividend`}</code>
        </div>
        <p className="text-slate-600 leading-relaxed">
          A fully franked 5% cash yield is equivalent to a <strong>~7.1% grossed-up yield</strong> for an investor on a 30% marginal tax rate. For super funds in pension phase (0% tax), franking credits are refunded in cash — making fully franked dividends even more valuable.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Grossed-up yield by tax bracket (5% fully franked dividend)
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-blue-700 border-b border-blue-200">
                <th className="text-left py-1.5 pr-3">Tax rate</th>
                <th className="text-right py-1.5 pr-3">Cash yield</th>
                <th className="text-right py-1.5 pr-3">Franking credit</th>
                <th className="text-right py-1.5 pr-3">Grossed-up</th>
                <th className="text-right py-1.5">Benefit</th>
              </tr>
            </thead>
            <tbody className="text-blue-900">
              {TAX_TABLE.map(({ rate, cashYield, frankingCredit, grossedUp, taxSaving }) => (
                <tr key={rate} className="border-b border-blue-100">
                  <td className="py-1.5 pr-3">{rate}</td>
                  <td className="text-right py-1.5 pr-3">{cashYield}</td>
                  <td className="text-right py-1.5 pr-3">{frankingCredit}</td>
                  <td className="text-right py-1.5 pr-3 font-bold">{grossedUp}</td>
                  <td className="text-right py-1.5 text-emerald-700 font-medium">{taxSaving}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-blue-700 mt-2">Based on 100% franking at 30% corporate tax rate. Consult a tax adviser for your specific situation.</p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-slate-500" />
          How to screen for franked ASX dividend stocks — step by step
        </h2>
        <div className="space-y-3">
          {SCREEN_STEPS.map(({ step, detail }, i) => (
            <div key={step} className="bg-white border border-slate-200 rounded-xl p-4 flex gap-3">
              <span className="w-6 h-6 rounded-full bg-emerald-600 text-white text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
              <div>
                <p className="font-semibold text-slate-900 text-sm mb-1">{step}</p>
                <p className="text-xs text-slate-500 leading-relaxed">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example screens</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Core fully franked income screen',
              desc: 'Large-cap, fully franked dividend payers with sustainable payout ratios.',
              filters: ['dividend_yield > 4', 'franking_pct = 100', 'payout_ratio < 75', 'market_cap > 1000', 'net_debt_to_ebitda < 2.5'],
            },
            {
              name: 'Franked dividend growth screen',
              desc: 'Companies growing their fully franked dividend over time — compounding income.',
              filters: ['franking_pct = 100', 'dividend_growth_3y > 5', 'payout_ratio < 65', 'roe > 12', 'market_cap > 500'],
            },
            {
              name: 'High grossed-up yield screen',
              desc: 'Maximising after-tax income for investors in lower tax brackets or super.',
              filters: ['dividend_yield > 5', 'franking_pct >= 75', 'payout_ratio < 85', 'market_cap > 300', 'eps_growth_1y > -10'],
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
        <h2 className="text-xl font-bold text-slate-900 mb-3">Which sectors pay the most franked dividends?</h2>
        <div className="space-y-2">
          {[
            { sector: 'Financials (Banks)', franking: '100%', note: 'Big Four banks pay fully franked dividends consistently. Highest franking reliability on the ASX.' },
            { sector: 'Consumer Staples', franking: '70–100%', note: 'Woolworths, Coles — domestically-focused earnings, strong franking.' },
            { sector: 'Industrials', franking: '50–100%', note: 'Varies by company. Asset-light businesses with domestic earnings tend toward higher franking.' },
            { sector: 'Healthcare', franking: '30–75%', note: 'Large offshore earners like CSL have limited franking. Domestically-focused health services companies rank higher.' },
            { sector: 'A-REITs', franking: '0–30%', note: 'Most REIT distributions are unfranked (trust structure distributes rent, not franked profit). Check each one.' },
            { sector: 'Materials (Miners)', franking: '50–100%', note: 'Depends on the company\'s tax position. BHP and Rio pay substantial franking credits when domestic profits are strong.' },
          ].map(({ sector, franking, note }) => (
            <div key={sector} className="bg-white border border-slate-200 rounded-xl p-3 flex items-start gap-3">
              <div className="shrink-0">
                <p className="font-semibold text-slate-900 text-xs">{sector}</p>
                <span className="text-xs font-mono text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">{franking}</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{note}</p>
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
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained — Full Guide' },
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained for ASX Investors' },
            { href: '/learn/how-to-check-asx-dividend-sustainability', label: 'How to Check If an ASX Dividend Is Sustainable' },
            { href: '/learn/building-an-asx-dividend-portfolio', label: 'Building a Dividend Portfolio on the ASX' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> The tax treatment of franking credits depends on your personal tax situation. This article is for general educational purposes only. Consult a registered tax agent or financial adviser for advice specific to your circumstances.</p>
      </div>
    </div>
  )
}
