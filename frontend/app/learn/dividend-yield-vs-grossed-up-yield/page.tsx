import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, TrendingUp } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'Dividend Yield vs Grossed-Up Yield Explained | ASX Screener',
  description:
    'What grossed-up yield means for Australian investors, how franking credits increase effective yield, and how to compare fully franked and unfranked dividends on an equal basis.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/dividend-yield-vs-grossed-up-yield' },
}

const TAX_TABLE = [
  { bracket: '0% (Below tax-free threshold)', rate: 0, regularYield: '5.0%', grossedUp: '7.14%', benefit: '+2.14%' },
  { bracket: '19% (Up to $18,200)', rate: 19, regularYield: '5.0%', grossedUp: '7.14%', benefit: '+2.14%' },
  { bracket: '32.5% (Up to $45,000)', rate: 32.5, regularYield: '5.0%', grossedUp: '7.14%', benefit: '+2.14%' },
  { bracket: '37% (Up to $120,000)', rate: 37, regularYield: '5.0%', grossedUp: '7.14%', benefit: '+2.14%' },
  { bracket: '45% (Over $120,000)', rate: 45, regularYield: '5.0%', grossedUp: '7.14%', benefit: '+2.14%' },
]

export default function DividendYieldVsGrossedUpYieldPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="Dividend Yield vs Grossed-Up Yield Explained"
        description="What grossed-up yield means for Australian investors, how franking credits increase effective yield, and how to compare fully franked and unfranked dividends on an equal basis."
        url="https://asxscreener.com.au/learn/dividend-yield-vs-grossed-up-yield"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'Dividend Yield vs Grossed-Up Yield', href: '/learn/dividend-yield-vs-grossed-up-yield' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Beginner</span>
          <span className="text-xs text-slate-400">8 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Dividend Yield vs Grossed-Up Yield Explained
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Two ASX stocks both yield 5%. One pays a fully franked dividend; the other is unfranked. After tax, they are not equal — the franked dividend is worth significantly more to most Australian investors. This guide explains grossed-up yield, how to calculate it, and why it matters when comparing income stocks.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen by Grossed-Up Yield</p>
          <p className="text-blue-200 text-sm">Filter by grossed_up_yield, franking_pct, dividend_yield and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What is dividend yield?</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Dividend yield is the annual dividend per share divided by the current share price, expressed as a percentage.
        </p>
        <div className="bg-slate-900 rounded-xl p-4 mb-3">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{`Dividend Yield = (Annual Dividend per Share / Share Price) × 100

Example:
  Share price:    $10.00
  Annual dividend: $0.50
  Dividend yield:   5.0%`}</code>
        </div>
        <p className="text-slate-600 leading-relaxed text-sm">
          Dividend yield only measures the cash amount of the dividend — it does not account for franking credits, which can make the dividend worth significantly more to an Australian resident taxpayer.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">What is grossed-up yield?</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Grossed-up yield (also called grossed-up dividend yield) adds the value of the franking credit to the cash dividend to show the total pre-tax income generated. For a <strong>fully franked</strong> dividend, the formula is:
        </p>
        <div className="bg-slate-900 rounded-xl p-4 mb-3">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{`Corporate tax rate = 30%
Gross-up factor (fully franked) = 1 / (1 - 0.30) = 1.4286

Grossed-Up Yield = Cash Yield × Gross-up Factor

Example (5% fully franked yield):
  Grossed-Up Yield = 5.0% × 1.4286 = 7.14%

The 2.14% difference = the franking credit component`}</code>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
          <p className="text-sm text-blue-900 leading-relaxed">
            <strong>What this means in practice:</strong> a 5% fully franked dividend is equivalent to a 7.14% unfranked dividend on a pre-tax basis. If the company in the unfranked scenario only paid 5%, you would be worse off by 2.14 percentage points of income — before your marginal tax rate makes it even more lopsided.
          </p>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">How franking credits work in practice</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Australian companies pay 30% corporate tax on their profits. When they distribute those after-tax profits as dividends, they attach a <strong>franking credit</strong> representing the tax already paid. The investor receives:
        </p>
        <div className="space-y-2">
          {[
            { step: 'Cash dividend', val: '$0.35 per share (e.g., 70% of $0.50 pre-tax profit per share)' },
            { step: 'Franking credit', val: '$0.15 per share (the 30% corporate tax already paid)' },
            { step: 'Total grossed-up dividend', val: '$0.50 per share (added together)' },
            { step: 'Your tax', val: 'Applied to $0.50 at your marginal rate — then franking credit reduces the bill' },
          ].map(({ step, val }) => (
            <div key={step} className="flex items-start gap-3 bg-white border border-slate-200 rounded-xl p-3">
              <span className="text-blue-500 font-bold text-sm shrink-0">→</span>
              <div>
                <p className="text-sm font-medium text-slate-800">{step}</p>
                <p className="text-xs text-slate-500">{val}</p>
              </div>
            </div>
          ))}
        </div>
        <p className="text-slate-500 text-xs mt-3">
          If your marginal tax rate is below 30%, the ATO refunds the difference. If your rate is above 30%, you pay the gap. For investors with low taxable income (retirees in pension phase, low earners), fully franked dividends can generate a cash refund from the ATO — making them extremely tax-efficient.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-slate-500" />
          Grossed-up yield at different tax brackets
        </h2>
        <p className="text-slate-500 text-sm mb-3">For a stock with 5% fully franked yield (gross-up factor: ×1.4286):</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border border-slate-200 rounded-xl overflow-hidden">
            <thead className="bg-slate-50">
              <tr>
                <th className="text-left p-3 font-semibold text-slate-700">Tax bracket</th>
                <th className="text-left p-3 font-semibold text-slate-700">Cash yield</th>
                <th className="text-left p-3 font-semibold text-slate-700">Grossed-up yield</th>
                <th className="text-left p-3 font-semibold text-slate-700">Credit benefit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {TAX_TABLE.map(({ bracket, regularYield, grossedUp, benefit }) => (
                <tr key={bracket}>
                  <td className="p-3 text-slate-700">{bracket}</td>
                  <td className="p-3 text-slate-600 font-mono">{regularYield}</td>
                  <td className="p-3 font-mono font-semibold text-emerald-700">{grossedUp}</td>
                  <td className="p-3 font-mono text-blue-600">{benefit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-400 mt-2">The grossed-up yield is constant — how much of the credit you personally benefit from depends on your tax rate.</p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Partial franking</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          Not all ASX dividends are fully franked. A 50% franked dividend means only half the dividend carries a franking credit. The formula adjusts proportionally:
        </p>
        <div className="bg-slate-900 rounded-xl p-4">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{`Grossed-Up Yield = Cash Yield × (1 + (Franking % / 100) × (Corporate Tax Rate / (1 - Corporate Tax Rate)))

Example: 5% yield, 50% franked:
= 5.0% × (1 + 0.50 × (0.30 / 0.70))
= 5.0% × (1 + 0.50 × 0.4286)
= 5.0% × 1.2143
= 6.07%`}</code>
        </div>
        <p className="text-slate-500 text-xs mt-2">In the ASX Screener, the <code className="bg-slate-100 px-1 rounded">grossed_up_yield</code> field applies this formula automatically using the actual franking percentage of each stock&apos;s most recent dividend.</p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">When to use grossed-up yield</h2>
        <div className="space-y-2">
          {[
            { use: 'Comparing franked vs unfranked stocks', detail: 'Grossed-up yield puts both on the same pre-tax basis, making comparisons valid.' },
            { use: 'Comparing ASX dividends to term deposits or bonds', detail: 'Term deposit rates are pre-tax. Grossed-up yield lets you compare income sources directly.' },
            { use: 'Screening for income investors in the 0–30% tax bracket', detail: 'For retirees and low-income investors, grossed-up yield closely reflects after-tax income received (including refunds).' },
            { use: 'Comparing companies in the same sector', detail: 'Two banks or two REITs with the same cash yield but different franking levels have meaningfully different income value to Australian residents.' },
          ].map(({ use, detail }) => (
            <div key={use} className="flex items-start gap-3 bg-emerald-50 border border-emerald-200 rounded-xl p-3">
              <span className="text-emerald-600 font-bold text-sm shrink-0">✓</span>
              <div>
                <p className="text-sm font-medium text-emerald-900">{use}</p>
                <p className="text-xs text-emerald-700 leading-relaxed">{detail}</p>
              </div>
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
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained' },
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained' },
            { href: '/learn/how-to-find-asx-dividend-stocks-with-franking', label: 'How to Find ASX Dividend Stocks with Franking Credits' },
            { href: '/learn/how-to-check-asx-dividend-sustainability', label: 'How to Check If an ASX Dividend Is Sustainable' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial or tax advice.</strong> Tax treatment of franking credits depends on your individual circumstances. Consult a registered tax adviser for personal advice.</p>
      </div>
    </div>
  )
}
