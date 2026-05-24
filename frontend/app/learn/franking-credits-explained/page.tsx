import Link from 'next/link'
import { ChevronLeft, Zap, BarChart2, BookOpen, ArrowRight, Info, AlertTriangle } from 'lucide-react'

export const metadata = {
  title: 'Franking Credits Explained — ASX Investor Guide | ASX Screener',
  description:
    'Learn how Australian franking credits work, how to calculate grossed-up dividend yield, and why fully franked dividends are so valuable for ASX income investors.',
}

export default function FrankingCreditsPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      {/* Breadcrumb */}
      <Link href="/learn" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-blue-600 transition-colors">
        <ChevronLeft className="w-4 h-4" />
        Education Hub
      </Link>

      {/* Article header */}
      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Beginner</span>
          <span className="text-xs text-slate-400">8 min read</span>
          <span className="text-xs text-slate-400">· Last updated May 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Franking Credits Explained — The ASX Investor's Guide
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Australia's dividend imputation system is unique in the world. Understanding how franking credits work — and how to use them — is one of the biggest edges an ASX income investor can have.
        </p>
      </div>

      {/* Key takeaways */}
      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Key Takeaways
        </h2>
        <ul className="space-y-2">
          {[
            'Franking credits are a tax credit passed on to shareholders when a company pays corporate tax on its profits.',
            'A fully franked 4% dividend is worth ~5.7% grossed-up — a 43% bonus for Australian resident investors.',
            'Superannuation funds in pension phase can receive franking credits as a cash refund from the ATO.',
            'Always compare ASX income stocks using grossed-up yield, not raw dividend yield.',
          ].map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-900">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {point}
            </li>
          ))}
        </ul>
      </div>

      {/* Article body */}
      <div className="space-y-8 text-slate-700 leading-relaxed">

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">What is dividend imputation?</h2>
          <p>
            When an Australian company earns a profit, it pays <strong>30% corporate tax</strong> to the ATO (or 25% for small companies). When it then pays that after-tax profit to shareholders as a dividend, shareholders would normally pay income tax again on the same money — effectively taxing the same profit twice.
          </p>
          <p className="mt-3">
            Australia solved this in 1987 with <strong>dividend imputation</strong>. The idea is simple: the tax the company already paid is credited to shareholders, who can use it to offset their own income tax. These credits are called <strong>franking credits</strong> (or imputation credits).
          </p>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Fully franked vs. partially franked</h2>
          <p>
            A dividend is <strong>fully franked</strong> when the company has paid the full 30% corporate tax on the profits being distributed. It's <strong>partially franked</strong> when only some of the profit was taxed at the corporate level (common for companies with international income). It's <strong>unfranked</strong> when no corporate tax was paid on that income.
          </p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-slate-100">
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Type</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Franking %</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Example</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Common in</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['Fully franked',    '100%', 'CBA, ANZ, BHP', 'Banks, large ASX miners'],
                  ['Partially franked','50%',  'Some retailers', 'Companies with foreign earnings'],
                  ['Unfranked',        '0%',   'Infigen Energy', 'REITs, companies with tax losses'],
                ].map(([type, pct, ex, common]) => (
                  <tr key={type} className="border border-slate-200 hover:bg-slate-50">
                    <td className="px-3 py-2 font-medium">{type}</td>
                    <td className="px-3 py-2">{pct}</td>
                    <td className="px-3 py-2 text-slate-500">{ex}</td>
                    <td className="px-3 py-2 text-slate-500">{common}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">How to calculate grossed-up yield</h2>
          <p>The grossed-up yield converts a franked dividend into its tax-equivalent value for Australian investors:</p>

          {/* Formula box */}
          <div className="mt-4 bg-slate-900 rounded-xl p-4">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Formula</p>
            <code className="text-emerald-300 font-mono text-sm leading-relaxed block whitespace-pre-wrap">
{`Grossed-Up Yield = Dividend Yield × (1 + Franking% × 0.4286)

where 0.4286 = Corporate Tax Rate ÷ (1 − Corporate Tax Rate)
            = 30% ÷ 70% = 0.4286`}
            </code>
          </div>

          {/* Example box */}
          <div className="mt-4 bg-sky-50 border border-sky-200 rounded-xl p-4">
            <p className="text-xs font-bold text-sky-700 uppercase tracking-wide mb-2 flex items-center gap-1.5">
              <BarChart2 className="w-3.5 h-3.5" /> Real-World Example
            </p>
            <p className="text-sm text-sky-900">
              A bank stock trading at <strong>$28.00</strong> pays an annual dividend of <strong>$1.12/share</strong> (4% raw yield), fully franked.
            </p>
            <ul className="mt-2 space-y-1 text-sm text-sky-900">
              <li>Raw yield = 1.12 ÷ 28.00 = <strong>4.0%</strong></li>
              <li>Franking credit = 4.0% × 0.4286 = 1.71%</li>
              <li>Grossed-up yield = 4.0% + 1.71% = <strong>5.71%</strong></li>
            </ul>
            <p className="mt-2 text-sm text-sky-700 font-medium">
              An SMSF in pension phase receiving $1,000 in dividends would also receive an extra ~$430 as a franking credit refund cheque from the ATO.
            </p>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Who benefits most from franking credits?</h2>
          <p>The value of a franking credit depends on your <strong>marginal tax rate</strong>:</p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-slate-100">
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Investor type</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Tax rate</th>
                  <th className="text-left px-3 py-2 font-semibold text-slate-700 border border-slate-200">Benefit</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['SMSF in pension phase', '0%', 'Full refund of all franking credits as cash'],
                  ['SMSF in accumulation', '15%', 'Credit offsets 15% tax, 15% refunded as cash'],
                  ['Low-income earner',     '19%', 'Credits offset most income tax liability'],
                  ['Middle income (32.5%)', '32.5%','Credits offset personal tax — no refund, but lower tax bill'],
                  ['High income (47%)',     '47%', 'Credits partially offset; some benefit still received'],
                  ['Foreign investor',      'N/A', 'Receives no benefit — franking credits are non-refundable'],
                ].map(([type, rate, benefit]) => (
                  <tr key={type} className="border border-slate-200 hover:bg-slate-50">
                    <td className="px-3 py-2 font-medium">{type}</td>
                    <td className="px-3 py-2">{rate}</td>
                    <td className="px-3 py-2 text-slate-600">{benefit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-bold text-slate-900 mb-3">Practical tips for income investors</h2>
          <ul className="space-y-3">
            {[
              { tip: 'Always use grossed-up yield to compare ASX income stocks — raw yield understates the true return for Australian residents.' },
              { tip: 'You must hold shares "at risk" for at least 45 days around the ex-dividend date to be eligible for franking credits (the "holding period rule").' },
              { tip: 'REITs typically pay unfranked distributions because they pass income through without paying corporate tax — their raw yield is their true yield.' },
              { tip: 'Companies with accumulated tax losses (common in mining and tech) may not be able to frank their dividends even if they\'re profitable now.' },
            ].map(({ tip }, i) => (
              <li key={i} className="flex items-start gap-3 text-sm">
                <span className="mt-0.5 w-5 h-5 rounded-full bg-slate-100 text-slate-600 text-xs font-bold flex items-center justify-center shrink-0">{i + 1}</span>
                <span>{tip}</span>
              </li>
            ))}
          </ul>
        </section>

      </div>

      {/* Related screener filters */}
      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-amber-800 uppercase tracking-wide mb-3">Related ASX Screener Filters</h2>
        <div className="flex flex-wrap gap-2">
          {['Dividend Yield', 'Grossed-Up Yield', 'Franking %', 'Payout Ratio', 'Dividend CAGR 3Y'].map(f => (
            <span key={f} className="text-xs font-medium bg-white border border-amber-300 text-amber-800 px-2.5 py-1 rounded-full">{f}</span>
          ))}
        </div>
        <Link href="/screener" className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-amber-700 hover:text-amber-900">
          Try a Dividend Screen <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      {/* Related glossary metrics */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related Glossary Metrics
        </h2>
        <div className="flex flex-wrap gap-2">
          {['Dividend Yield', 'Grossed-Up Yield', 'Franking %', 'Payout Ratio', 'Income Score'].map(m => (
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
          <strong>Not financial advice.</strong> This article is for educational purposes only. Tax rules may change — consult a registered tax agent or financial adviser for advice specific to your situation.
        </p>
      </div>

      {/* CTA */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Screen for the best franked dividends on the ASX</h2>
        <p className="text-blue-100 mb-5 text-sm">Filter by grossed-up yield, franking %, payout ratio and more — across all 200+ ASX stocks.</p>
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
