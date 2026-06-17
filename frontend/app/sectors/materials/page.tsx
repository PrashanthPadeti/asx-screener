import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, AlertTriangle, ChevronLeft, Zap, BookOpen, TrendingUp, Filter } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: 'ASX Materials Sector — Stocks, Metrics & Screen | ASX Screener',
  description: 'Overview of the ASX Materials sector. Key metrics for mining and resources stocks, how to screen ASX materials companies, and what to watch when researching mining investments.',
  alternates: { canonical: 'https://asxscreener.com.au/sectors/materials' },
}

const KEY_METRICS = [
  { metric: 'EV/EBITDA', why: 'Preferred over PE for miners — accounts for capital intensity and depreciation. Compare within sub-sector (gold vs iron ore vs lithium).' },
  { metric: 'Net Cash / Net Debt', why: 'Mining is cyclical. Companies with net cash can survive commodity downturns; highly leveraged miners can be destroyed by them.' },
  { metric: 'All-In Sustaining Cost (AISC)', why: 'For gold miners: the true cost of producing one ounce. The gap between AISC and gold price = margin. Look for low-cost producers.' },
  { metric: 'JORC Resource Size', why: 'Defines how much ore the company has. Larger, higher-grade resources command premium valuations.' },
  { metric: 'Production Volume', why: 'Year-on-year production growth (or decline) drives revenue independent of commodity prices.' },
  { metric: 'Dividend Yield', why: 'Large diversified miners (BHP, RIO, FMG) can pay significant dividends. Franking varies. Dividends are typically tied to earnings — cyclical.' },
]

const SUB_SECTORS = [
  { name: 'Diversified Miners', desc: 'Multi-commodity producers. Revenue comes from iron ore, copper, coal, nickel, and other metals across multiple geographies.', examples: 'BHP, RIO, South32 (S32)' },
  { name: 'Gold Miners', desc: 'Pure-play or primary gold producers. Revenue is tightly correlated with the USD gold price. AISC is the key cost metric.', examples: 'NST, EVN, NCM, GOR, SFR' },
  { name: 'Iron Ore Producers', desc: 'Australia is the world\'s largest iron ore exporter. These stocks are tightly linked to Chinese steel demand and the 62% Fe iron ore price.', examples: 'FMG, CIA, MIN' },
  { name: 'Lithium & Battery Metals', desc: 'Supply chain for electric vehicles and battery storage. High growth potential but highly volatile with commodity price cycles.', examples: 'PLS, LTR, IGO, AKE' },
  { name: 'Copper Producers', desc: 'Copper is a key indicator for global industrial activity. Used in construction, EVs, and electrification broadly.', examples: 'SFR, OZL (acquired), 29M' },
  { name: 'Explorers & Developers', desc: 'Pre-production or early-stage companies. Speculative — value depends on resource definition, feasibility studies, and funding.', examples: 'Various small/micro caps' },
]

export default function MaterialsSectorPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Sectors', href: '/sectors' }, { label: 'Materials', href: '/sectors/materials' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-orange-100 text-orange-700">GICS Sector</span>
          <span className="text-xs text-slate-400">ASX 200 weight: ~20–24%</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          ASX Materials Sector
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          The Materials sector is the backbone of the ASX — comprising miners, metal producers, and chemical companies. Australia is one of the world's top resources exporters, making this sector uniquely important for ASX investors.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-orange-500 to-amber-600 text-white rounded-2xl p-5 hover:from-orange-600 hover:to-amber-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Materials Stocks</p>
          <p className="text-orange-100 text-sm">Filter by Sector = Materials, then apply EV/EBITDA, net debt, production, and resource metrics</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Sector characteristics
        </h2>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'Highly cyclical — earnings and valuations move with commodity prices, not just company performance.',
            'Currency sensitive — most commodities are priced in USD; a weaker AUD boosts Australian miners\' revenues.',
            'Capital intensive — large upfront capex for mines and processing plants; depreciation is significant.',
            'China exposure — Australia exports ~80% of iron ore to China; Chinese stimulus and property sector matter.',
            'ESG and energy transition — lithium, copper, and nickel benefit from electrification tailwinds.',
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
          Key metrics for materials stocks
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
        <h2 className="text-xl font-bold text-slate-900 mb-4">Sub-sectors within ASX Materials</h2>
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
        <h2 className="text-xl font-bold text-slate-900 mb-4">Example screens for Materials</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Profitable large-cap miners',
              filters: ['Sector = Materials', 'Market Cap > $2B', 'EV / EBITDA < 8', 'Net Debt / EBITDA < 1.5'],
            },
            {
              name: 'Cash-generative miners with dividends',
              filters: ['Sector = Materials', 'Dividend Yield > 3%', 'Free Cash Flow Yield > 5%', 'Net Cash (positive)'],
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
            { href: '/learn/how-to-research-asx-stocks-dyor', label: 'How to Research ASX Stocks: A DYOR Workflow' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/sectors/financials', label: 'ASX Financials Sector Overview' },
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
          <strong>Not financial advice.</strong> Sector overviews and example screens are for educational purposes only. Mining stocks involve additional risks including commodity price volatility, operational risk, and geopolitical exposure. Always conduct your own research.
        </p>
      </div>

    </div>
  )
}
