import type { Metadata } from 'next'
import { Database, Clock, RefreshCw, AlertTriangle } from 'lucide-react'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'Data Freshness Policy',
  description: 'How frequently ASX Screener updates its financial data — prices, financials, dividends, announcements, and screener metrics.',
  alternates: { canonical: 'https://asxscreener.com.au/data-freshness' },
}

const DATA_TYPES = [
  {
    category: 'Share Prices',
    frequency: 'End of day',
    source: 'Market data provider',
    notes: 'Prices reflect the previous trading day\'s close. Intraday prices are not available.',
    delay: '~15 min after market close',
  },
  {
    category: 'Financial Statements',
    frequency: 'As reported',
    source: 'Company ASX filings',
    notes: 'Updated when companies file half-year and full-year results. Typically August–September (FY results) and February–March (HY results) for June-year companies.',
    delay: '1–3 business days after filing',
  },
  {
    category: 'Dividend Data',
    frequency: 'As announced',
    source: 'ASX company announcements',
    notes: 'Dividend amount, franking %, ex-date, and payment date updated when declared by the company.',
    delay: '1–2 business days after announcement',
  },
  {
    category: 'ASX Announcements',
    frequency: 'Daily',
    source: 'ASX public announcements API',
    notes: 'Announcement count, capital raise history, trading halt counts, and director change signals are derived from the free public ASX announcements feed.',
    delay: 'Updated nightly',
  },
  {
    category: 'Screener Metrics (screener.universe)',
    frequency: 'Nightly',
    source: 'Computed from financials + price data',
    notes: 'Every screener metric is recomputed each night. This includes PE ratio, EV/EBITDA, ROE, dividend yield, composite scores, and qualitative signals.',
    delay: 'Reflects previous day\'s close',
  },
  {
    category: 'Analyst Consensus',
    frequency: 'Weekly',
    source: 'Third-party data provider',
    notes: 'Analyst target prices and consensus ratings. Coverage is available only for larger ASX companies.',
    delay: 'May lag by up to 7 days',
  },
  {
    category: 'Short Interest (ASIC)',
    frequency: 'Weekly',
    source: 'ASIC short position reports',
    notes: 'ASIC publishes short position data weekly. Short ratio (days to cover) is derived from this data combined with 50-day average volume.',
    delay: '3–5 business days after reporting date',
  },
  {
    category: 'AI Insights',
    frequency: 'On demand',
    source: 'Claude AI + ASX filings',
    notes: 'AI responses are generated in real time using available company data. The underlying training data has a knowledge cutoff — recent events may not be reflected.',
    delay: 'Real time, but knowledge cutoff applies',
  },
]

/**
 * The four outcomes of the applicability contract, in customer language.
 *
 * These mirror backend/compute/engine/applicability.py exactly. The state
 * names are the ones the engine records, so a support question about a blank
 * can be answered with the same vocabulary the system uses internally.
 */
const REASONS = [
  {
    state: 'APPLICABLE',
    label: 'The figure is shown',
    detail: 'The metric is meaningful for this kind of company, the inputs exist, and the '
          + 'units are compatible. This is the only case in which a number is published.',
  },
  {
    state: 'NOT_MEANINGFUL',
    label: 'Withheld because the number would mislead',
    detail: 'The metric does not apply to this company, or the inputs would make it '
          + 'meaningless. A P/E on a loss-making company, a debt ratio on a business with '
          + 'no debt, or a ratio mixing an AUD share price with financial statements '
          + 'reported in another currency. The data exists; publishing it would not inform you.',
  },
  {
    state: 'UNAVAILABLE',
    label: 'The metric applies, but no value could be obtained',
    detail: 'This is deliberately distinct from the case above. Either this company has no '
          + 'value for it, or the feed that supplies it is unhealthy. We separate "cannot '
          + 'exist" from "we failed to obtain it", because only the second is our problem to fix.',
  },
  {
    state: 'INSUFFICIENT_DATA',
    label: 'Not enough history yet',
    detail: 'The metric needs a longer run of observations than this company has — a recent '
          + 'listing, or a three-year growth rate with two years of filings behind it.',
  },
]

export default function DataFreshnessPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      <div>
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
            <Database className="w-5 h-5 text-blue-600" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Data Freshness Policy</h1>
        </div>

      </div>

      <p className="text-slate-600 leading-relaxed">
        ASX Screener aggregates financial data from multiple sources. Different data types are updated at different frequencies. This page explains when each type of data is refreshed, what delays to expect, and — just as importantly — what it means when a figure is not shown at all.
      </p>

      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <p className="text-sm text-amber-800">
          <strong>Always verify critical data from primary sources.</strong> For any investment decision, confirm important figures directly from ASX announcements, company annual reports, or your broker's platform.
        </p>
      </div>

      <div className="space-y-4">
        {DATA_TYPES.map(({ category, frequency, source, notes, delay }) => (
          <div key={category} className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
              <h2 className="font-semibold text-slate-900">{category}</h2>
              <div className="flex items-center gap-1.5 bg-blue-50 text-blue-700 text-xs font-medium px-2.5 py-1 rounded-full shrink-0">
                <RefreshCw className="w-3 h-3" />
                {frequency}
              </div>
            </div>
            <div className="grid sm:grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-1">Source</p>
                <p className="text-slate-600">{source}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-1 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> Typical Delay
                </p>
                <p className="text-slate-600">{delay}</p>
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-3 leading-relaxed border-t border-slate-100 pt-3">{notes}</p>
          </div>
        ))}
      </div>

      {/* ── What a blank means ──────────────────────────────────────────────
          Added 2 Oct 2026. The screener withholds figures it cannot
          substantiate, which is a deliberate design decision rather than a
          gap, and nothing on the site said so. A dash that looks like missing
          data undersells the work; a dash that explains itself is the whole
          argument for the product. */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900">When a figure is not shown</h2>
        <p className="text-slate-600 leading-relaxed text-sm">
          A dash in place of a number is a statement, not a gap. Every governed metric
          is classified before it is served, and a value is published only when the
          system can substantiate it. Four outcomes are possible:
        </p>

        <div className="space-y-3">
          {REASONS.map(({ state, label, detail }) => (
            <div key={state} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="font-mono text-[11px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                  {state}
                </span>
                <h3 className="font-semibold text-slate-800 text-sm">{label}</h3>
              </div>
              <p className="text-sm text-slate-600 leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
          <p className="text-sm text-blue-900 leading-relaxed">
            <strong>Why this matters.</strong> A screener that always prints a number is
            not more complete than one that sometimes declines — it is less honest about
            which of its numbers mean anything. A P/E computed from an AUD share price and
            a statement reported in another currency is arithmetic, not a valuation. We
            would rather show you nothing than show you that.
          </p>
        </div>

        <p className="text-slate-600 leading-relaxed text-sm">
          Separately from classification, a price is only eligible to be served while the
          source that produced it is still in use. When a data source is retired, prices
          already collected from it remain stored for history but stop qualifying as a
          current price — so an instrument whose only price came from a retired feed shows
          no price rather than an old one.
        </p>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-2">
        <h2 className="font-semibold text-slate-800 text-sm">Related pages</h2>
        <div className="flex flex-wrap gap-4">
          {[
            { href: '/disclaimer', label: 'Disclaimer' },
            { href: '/ai-insights-limitations', label: 'AI Insights Limitations' },
            { href: '/terms', label: 'Terms of Service' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="text-sm text-blue-600 hover:underline">
              {label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
