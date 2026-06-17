import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, DollarSign, TrendingDown } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata = {
  title: 'How to Check If an ASX Dividend Is Sustainable | ASX Screener',
  description:
    'Five metrics ASX investors use to check whether a dividend is sustainable — payout ratio, free cash flow cover, debt, earnings trend, and franking history.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/how-to-check-asx-dividend-sustainability' },
}

const METRICS = [
  {
    n: 1,
    metric: 'Payout Ratio',
    key: 'payout_ratio',
    what: 'Dividends paid as a percentage of earnings (EPS). The most commonly cited sustainability check.',
    safe: 'Below 75% for most sectors. Below 90% for REITs and utilities (which have more predictable earnings).',
    warning: 'Above 100% means the company is paying out more than it earns — it is funding the dividend from cash reserves or debt. This is unsustainable unless earnings recover.',
  },
  {
    n: 2,
    metric: 'Free Cash Flow Payout Ratio',
    key: 'fcf_payout_ratio',
    what: 'Dividends paid as a percentage of free cash flow (operating cash flow minus capex). More reliable than earnings-based payout ratio because earnings can include non-cash items.',
    safe: 'Below 80%. A company generating $1 in FCF and paying out $0.70 in dividends has comfortable cover.',
    warning: 'Companies with high earnings but low FCF (e.g. heavy depreciation, high capex) often look safer on the earnings payout ratio than they really are. Always check FCF cover too.',
  },
  {
    n: 3,
    metric: 'Dividend Cover',
    key: 'dividend_cover',
    what: 'The inverse of payout ratio: earnings ÷ dividend per share. Shows how many times over the dividend is covered by earnings.',
    safe: '1.5× or above is considered comfortable. 2× or above is strong.',
    warning: 'Cover below 1.0× means the dividend exceeds earnings — a red flag. Cover between 1.0–1.3× provides little buffer if earnings dip.',
  },
  {
    n: 4,
    metric: 'Earnings Trend',
    key: 'earnings_growth_1y',
    what: 'Whether earnings are growing, flat, or declining. A dividend is only sustainable if the earnings base supporting it is stable or growing.',
    safe: 'Flat to growing earnings alongside a reasonable payout ratio.',
    warning: 'Declining earnings + high payout ratio = dividend cut risk. Companies often hold the dividend steady while earnings fall, creating an increasingly stretched payout ratio — until a cut becomes unavoidable.',
  },
  {
    n: 5,
    metric: 'Net Debt / EBITDA',
    key: 'net_debt_to_ebitda',
    what: 'How leveraged the company is relative to its operating earnings. Highly indebted companies face pressure to use cash flow for debt repayment rather than dividends.',
    safe: 'Below 2.0× for most sectors. Some REITs and infrastructure stocks can sustain higher leverage safely.',
    warning: 'Above 3.5× becomes concerning for dividend sustainability — especially when interest rates are rising or earnings are under pressure.',
  },
  {
    n: 6,
    metric: 'Franking History',
    key: 'franking_pct',
    what: 'For Australian investors, the consistency of franking credits matters. A fully franked dividend (100%) delivers significant after-tax value; losing franking credits often signals a business change.',
    safe: 'Stable franking percentage over 3–5 years. Fully franked or consistently partially franked.',
    warning: 'A sudden drop in franking credits — from 100% to 0% — often signals the company is earning less profit in Australia, paying more tax overseas, or restructuring. Worth investigating before buying.',
  },
]

const YIELD_TRAPS = [
  { trap: 'Yield is high because the share price has fallen sharply', why: 'A falling share price may be pricing in an upcoming cut. Always check why the price has dropped before buying on a high yield.' },
  { trap: 'Payout ratio above 100%', why: 'The company is paying more than it earns. This can persist for a year or two but rarely for longer without a cut or capital raise.' },
  { trap: 'Dividend has been flat or grown very slowly while earnings have risen', why: 'May signal management is conserving cash for a reason — could be investment, or could be flagging earnings risk.' },
  { trap: 'High yield in a cyclical industry at peak earnings', why: 'Mining, energy, and agricultural stocks sometimes pay large special dividends at peak commodity prices. These are not recurring.' },
  { trap: 'Yield above 10% with no extraordinary reason', why: 'Yields above 10% on the ASX are extremely rare for sustainable businesses. The market is usually pricing in an impending cut.' },
]

export default function DividendSustainabilityPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'How to Check If an ASX Dividend Is Sustainable', href: '/learn/how-to-check-asx-dividend-sustainability' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Intermediate</span>
          <span className="text-xs text-slate-400">10 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          How to Check If an ASX Dividend Is Sustainable
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          A high dividend yield is only valuable if the dividend keeps getting paid. This guide covers the six metrics ASX income investors use to assess dividend sustainability — and how to spot a yield trap before it catches you.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-2xl p-5 hover:from-emerald-700 hover:to-teal-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Dividend Stocks</p>
          <p className="text-emerald-200 text-sm">Filter by payout ratio, dividend cover, FCF cover, franking and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Why dividend sustainability matters</h2>
        <p className="text-slate-600 leading-relaxed mb-3">
          A dividend cut is one of the most painful events for an income investor. It typically comes with two blows at once: the dividend income drops, and the share price usually falls sharply on the announcement — because a cut signals weaker-than-expected earnings.
        </p>
        <p className="text-slate-600 leading-relaxed">
          The good news is that dividend cuts are rarely a surprise to those paying attention. In most cases, the metrics below will show stress building for one, two, or even three years before a cut is announced.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-slate-500" />
          Six metrics to check before buying for income
        </h2>
        <div className="space-y-4">
          {METRICS.map(({ n, metric, key, what, safe, warning }) => (
            <div key={key} className="bg-white border border-slate-200 rounded-2xl p-5">
              <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-emerald-600 text-white text-xs font-bold flex items-center justify-center shrink-0">{n}</span>
                  <p className="font-bold text-slate-900">{metric}</p>
                </div>
                <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{key}</code>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed mb-3">{what}</p>
              <div className="space-y-2">
                <div className="flex items-start gap-2 bg-emerald-50 rounded-lg p-2.5">
                  <span className="text-emerald-600 font-bold text-sm shrink-0">✓</span>
                  <p className="text-xs text-emerald-900 leading-relaxed"><strong>Safe zone:</strong> {safe}</p>
                </div>
                <div className="flex items-start gap-2 bg-red-50 rounded-lg p-2.5">
                  <span className="text-red-500 font-bold text-sm shrink-0">✗</span>
                  <p className="text-xs text-red-900 leading-relaxed"><strong>Warning sign:</strong> {warning}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3">The 3-year trend check</h2>
        <p className="text-sm text-blue-900 leading-relaxed mb-3">
          Single-year metrics can be misleading. What you really want to see is <strong>3–5 years of consistent data</strong>:
        </p>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'Dividend per share flat or growing over 3–5 years',
            'Payout ratio stable or declining (improving cover as earnings grow)',
            'Free cash flow consistently above dividends paid',
            'Earnings trend flat or rising — not falling toward the dividend',
            'Franking credits stable at the same percentage',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-blue-500 shrink-0">→</span>
              {item}
            </li>
          ))}
        </ul>
        <p className="text-sm text-blue-900 leading-relaxed mt-3">
          ASX Screener shows 5-year dividend history and payout trend so you can spot any deterioration at a glance.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3 flex items-center gap-2">
          <TrendingDown className="w-5 h-5 text-red-500" />
          How to spot a yield trap
        </h2>
        <p className="text-slate-500 text-sm mb-4">A yield trap is a stock that looks attractively priced for income but is about to cut its dividend. Common patterns:</p>
        <div className="space-y-3">
          {YIELD_TRAPS.map(({ trap, why }) => (
            <div key={trap} className="bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="font-semibold text-red-900 text-sm mb-1">{trap}</p>
              <p className="text-xs text-red-700 leading-relaxed">{why}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Sustainable dividend screens</h2>
        <div className="space-y-4">
          {[
            {
              name: 'Conservative income screen',
              desc: 'High yield with strong coverage and low debt — prioritises safety over maximising yield.',
              filters: [
                'dividend_yield > 4',
                'payout_ratio < 70',
                'dividend_cover > 1.5',
                'net_debt_to_ebitda < 2',
                'market_cap > 500',
              ],
            },
            {
              name: 'Fully franked quality income',
              desc: 'Fully franked dividends with earnings growth and manageable payout ratio.',
              filters: [
                'franking_pct = 100',
                'dividend_yield > 3',
                'payout_ratio < 75',
                'earnings_growth_1y > 0',
                'roe > 10',
              ],
            },
            {
              name: 'Dividend growth screen',
              desc: 'Stocks growing their dividend over time — sustainable and increasing income.',
              filters: [
                'dividend_growth_3y > 5',
                'payout_ratio < 65',
                'fcf_payout_ratio < 70',
                'debt_to_equity < 0.5',
                'market_cap > 300',
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
        <h2 className="text-xl font-bold text-slate-900 mb-3">Sector differences to keep in mind</h2>
        <div className="space-y-2">
          {[
            { sector: 'Banks', note: 'Payout ratios of 70–80% are normal. Focus on cash earnings cover and tier 1 capital ratios rather than GAAP payout ratio.' },
            { sector: 'A-REITs', note: 'Payout ratios above 90% are standard — REITs distribute most of their FFO. Use FCF cover and LVR (loan-to-value ratio) instead.' },
            { sector: 'Miners', note: 'Dividends are inherently cyclical and tied to commodity prices. Avoid projecting current yields forward in a commodity boom.' },
            { sector: 'Utilities / Infrastructure', note: 'Capital-intensive but highly predictable cash flows. Higher payout ratios (80–90%) can be sustained due to regulated income.' },
            { sector: 'Technology / Growth', note: 'Few ASX tech companies pay meaningful dividends. If they do, check whether reinvestment in growth is being sacrificed.' },
          ].map(({ sector, note }) => (
            <div key={sector} className="flex items-start gap-3 bg-white border border-slate-200 rounded-xl p-3">
              <span className="text-xs font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded shrink-0">{sector}</span>
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
            { href: '/learn/dividend-yield-explained', label: 'Dividend Yield Explained for ASX Investors' },
            { href: '/learn/franking-credits-explained', label: 'Understanding Franking Credits' },
            { href: '/learn/roe-explained', label: 'ROE Explained: How Investors Use Return on Equity' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/learn/how-to-build-an-asx-watchlist', label: 'How to Build and Maintain an ASX Watchlist' },
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
          <strong>Not financial advice.</strong> Dividend sustainability metrics are research tools only. Past dividend history does not guarantee future payments. Always conduct your own research and consider advice from a licensed financial adviser before making investment decisions.
        </p>
      </div>

    </div>
  )
}
