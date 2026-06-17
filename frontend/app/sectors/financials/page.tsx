import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, AlertTriangle, ChevronLeft, Zap, BookOpen, TrendingUp, Filter } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: 'ASX Financials Sector — Banks, REITs & Insurance | ASX Screener',
  description: 'Overview of the ASX Financials sector. Key metrics for ASX banks, insurance companies, and diversified financials. How to screen and research ASX financial stocks.',
  alternates: { canonical: 'https://asxscreener.com.au/sectors/financials' },
}

const KEY_METRICS = [
  { metric: 'Price-to-Book (P/B)', why: 'The primary valuation metric for banks. Banks with high ROE can trade at 2–3x book; those with declining ROE trade below book.' },
  { metric: 'Return on Equity (ROE)', why: 'How efficiently a bank uses shareholders\' equity to generate profit. Sustainable ROE above cost of equity (typically 10–13%) is the benchmark.' },
  { metric: 'Net Interest Margin (NIM)', why: 'The spread between what a bank earns on loans and pays on deposits. Rising rates can expand NIM; intense competition compresses it.' },
  { metric: 'Capital Adequacy Ratio (CET1)', why: 'Core Equity Tier 1 ratio — a regulatory measure of financial strength. Higher CET1 signals resilience; APRA requires a minimum of ~10.5%.' },
  { metric: 'Bad Debt Expense / Impairments', why: 'Indicates credit quality and economic stress. Rising bad debts can rapidly erode bank profits in a recession.' },
  { metric: 'Dividend Yield & Franking', why: 'Big 4 banks have historically been the best fully franked dividend payers on the ASX — yields of 4.5–6.5%, mostly 100% franked.' },
]

const SUB_SECTORS = [
  { name: 'Big 4 Banks', desc: 'CBA, NAB, ANZ, and WBC dominate Australian retail and business banking. Combined ASX weight of ~20%. Highly regulated by APRA. Defensive income with full franking.', examples: 'CBA, NAB, ANZ, WBC' },
  { name: 'Regional Banks', desc: 'Smaller banks focused on specific geographies or customer segments. Often lower returns on equity than Big 4 but different risk profiles.', examples: 'BOQ, BEN, MYS' },
  { name: 'Investment Banks & Diversified Financials', desc: 'Includes investment banks, asset managers, exchanges, and financial services groups. More volatile than retail banks.', examples: 'MQG, ASX, HUB, PTM' },
  { name: 'Insurance', desc: 'General and life insurers. Revenue from premiums; profitability driven by claims ratios, reinsurance costs, and investment returns.', examples: 'SUN, IAG, QBE, MPL' },
  { name: 'A-REITs (Australian REITs)', desc: 'Real estate investment trusts classified under Financials by GICS. Distribute rental income; assessed on NTA, FFO, and gearing rather than PE.', examples: 'GPT, SCG, GMG, CHC, CIP, NSR' },
  { name: 'Buy Now Pay Later & Fintech', desc: 'Newer entrants disrupting traditional finance. Higher growth, higher risk. Pre-profitability in many cases. Assessed on user metrics and loan book quality.', examples: 'ZIP, CPU (Computershare), HGH' },
]

export default function FinancialsSectorPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Sectors', href: '/sectors' }, { label: 'Financials', href: '/sectors/financials' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">GICS Sector</span>
          <span className="text-xs text-slate-400">ASX 200 weight: ~28–32%</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          ASX Financials Sector
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          The Financials sector is the largest sector in the ASX 200 by weight — driven by Australia's Big 4 banks and a broad ecosystem of insurers, REITs, and asset managers. For income investors, it is the primary source of fully franked dividend yield on the ASX.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl p-5 hover:from-blue-700 hover:to-indigo-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Financials Stocks</p>
          <p className="text-blue-200 text-sm">Filter by Sector = Financials, then apply P/B, ROE, NIM, dividend yield and franking metrics</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Sector characteristics
        </h2>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'Interest rate sensitive — rising rates initially expand bank margins but can slow credit growth and increase bad debts.',
            'Highly regulated by APRA (banking), ASIC (markets), and APRA/RBNZ for trans-Tasman banks.',
            'Defensive income — Big 4 banks have paid fully franked dividends continuously for decades.',
            'Housing market exposure — Australian bank loan books are ~60–70% residential mortgages.',
            'A-REITs: interest rate sensitive — rising rates increase financing costs and compress valuations.',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <TrendingUp className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Filter className="w-5 h-5 text-slate-500" />
          Key metrics for financials stocks
        </h2>
        <div className="space-y-3">
          {KEY_METRICS.map(({ metric, why }) => (
            <div key={metric} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-semibold text-slate-900 text-sm mb-1">{metric}</p>
              <p className="text-xs text-slate-500 leading-relaxed">{why}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Sub-sectors within ASX Financials</h2>
        <div className="space-y-3">
          {SUB_SECTORS.map(({ name, desc, examples }) => (
            <div key={name} className="bg-slate-50 border border-slate-200 rounded-xl p-4">
              <p className="font-semibold text-slate-900 mb-1">{name}</p>
              <p className="text-sm text-slate-600 leading-relaxed mb-2">{desc}</p>
              <p className="text-xs text-slate-400"><span className="font-medium">Examples:</span> {examples}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example screens for Financials</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Quality bank income screen',
              filters: ['Sector = Financials', 'Sub-sector = Banks', 'Dividend Yield > 4.5%', 'Franking % = 100%', 'ROE > 10%', 'CET1 Ratio > 11%'],
            },
            {
              name: 'A-REIT income screen',
              filters: ['Sector = Financials', 'Sub-sector = A-REIT', 'Dividend Yield > 5%', 'Gearing Ratio < 35%', 'Market Cap > $1B'],
            },
          ].map(({ name, filters }) => (
            <div key={name} className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
              <h3 className="font-bold text-slate-900 mb-2">{name}</h3>
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

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Learn more
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained' },
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained for ASX Investors' },
            { href: '/screener/asx-dividend-yield', label: 'Screen ASX Stocks by Dividend Yield' },
            { href: '/sectors/materials', label: 'ASX Materials Sector Overview' },
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
          <strong>Not financial advice.</strong> Sector overviews are for educational purposes only. Bank stocks and A-REITs involve specific regulatory, interest rate, and credit risks. Always conduct your own research and consider advice from a licensed financial adviser.
        </p>
      </div>

    </div>
  )
}
