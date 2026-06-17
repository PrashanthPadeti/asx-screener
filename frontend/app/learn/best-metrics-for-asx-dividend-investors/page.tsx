import Link from 'next/link'
import { ChevronLeft, BarChart2, AlertTriangle, BookOpen, DollarSign } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'
import ArticleSchema from '@/components/ArticleSchema'

export const metadata = {
  title: 'Best Metrics for ASX Dividend Investors | ASX Screener',
  description:
    'The eight metrics every ASX dividend investor should track — from grossed-up yield and payout ratio to dividend CAGR, FCF cover, and balance sheet strength.',
  alternates: { canonical: 'https://asxscreener.com.au/learn/best-metrics-for-asx-dividend-investors' },
}

const METRICS = [
  {
    n: 1,
    name: 'Grossed-Up Yield',
    field: 'grossed_up_yield',
    target: '> 5% for income investors',
    why: 'The true income yield after accounting for franking credits — not just the cash dividend. A 5% fully franked dividend has a grossed-up yield of 7.14%. This is the metric to use when comparing stocks across different franking levels.',
    warning: 'Very high grossed-up yields (>10%) can signal unsustainable dividends — investigate payout ratio and earnings trend before acting on high-yield stocks.',
  },
  {
    n: 2,
    name: 'Payout Ratio',
    field: 'payout_ratio',
    target: '30–70% is the sustainable zone',
    why: 'Percentage of net earnings paid as dividends. Too high (>80%) and there is little room for earnings to fall before the dividend gets cut. Too low (<15%) on a profitable company may indicate a culture of not returning capital to shareholders.',
    warning: 'Payout ratios above 100% mean dividends are being funded from reserves or borrowings — a strong warning sign unless justified by temporary earnings weakness.',
  },
  {
    n: 3,
    name: 'FCF Payout Ratio',
    field: 'fcf_payout_ratio',
    target: '< 70% (stricter than earnings payout)',
    why: 'Dividends paid as a percentage of free cash flow — arguably more important than the earnings-based payout ratio. A company can report profit but have negative FCF. FCF cover below 1× means the dividend cannot be sustained from operations.',
    warning: 'A company with FCF payout ratio > 100% is paying more in dividends than it generates in free cash flow. This is not sustainable long-term without raising debt or cutting the dividend.',
  },
  {
    n: 4,
    name: 'Dividend Growth (CAGR 3–5Y)',
    field: 'dividend_growth_3y',
    target: '> 5% annually over 3–5 years',
    why: 'A company that has consistently grown its dividend demonstrates earnings confidence from management. Dividend growth compounds your effective yield on cost over time — a stock bought at 4% yield with 8% annual dividend growth will yield 8%+ on cost in 9 years.',
    warning: 'Check that dividend growth is funded by earnings growth — not from a rising payout ratio. Sustainable dividend growth requires the underlying business to generate more profit over time.',
  },
  {
    n: 5,
    name: 'Franking Percentage',
    field: 'franking_pct',
    target: '> 75% for Australian tax residents',
    why: 'For Australian investors, fully franked dividends are worth 43% more than unfranked dividends at the 30% corporate tax rate. Franking percentage tells you how much of each dividend carries a franking credit — critical for comparing income stocks on a like-for-like basis.',
    warning: 'International companies and some Australian financial products (ETFs, hybrids) often pay unfranked dividends. Compare using grossed-up yield to avoid overpaying for lower-quality income.',
  },
  {
    n: 6,
    name: 'Earnings Per Share Growth (1Y and 3Y)',
    field: 'eps_growth_1y',
    target: '> 0% over 1Y; > 3% over 3Y CAGR',
    why: 'Dividends are paid from earnings. A company with flat or declining EPS has limited capacity to maintain — let alone grow — its dividend. Positive EPS trend is a precondition for dividend sustainability. Negative EPS growth while maintaining the same dividend shrinks the margin of safety.',
    warning: 'Always look at normalised earnings — exclude one-off asset sales, accounting releases, or tax benefits that inflate a single year\'s result and make the EPS trend look better than it is.',
  },
  {
    n: 7,
    name: 'Net Debt / EBITDA',
    field: 'net_debt_to_ebitda',
    target: '< 2× for most sectors; < 3× for REITs',
    why: 'Highly leveraged companies are vulnerable to dividend cuts in a downturn. Rising interest costs reduce the cash available for dividends. A company with net debt/EBITDA of 4× paying a 6% dividend is taking on significant risk — one earnings shock away from a cut.',
    warning: 'In rising rate environments, high-debt companies face double pressure: interest costs rise AND growth multiples compress. Favour dividend payers with conservative balance sheets.',
  },
  {
    n: 8,
    name: 'Dividend History (5–10 Year Track Record)',
    field: 'dividend_paid_10y',
    target: 'Paid and maintained or grown dividend in 7+ of last 10 years',
    why: 'Historical dividend consistency is one of the best predictors of future dividend reliability. Companies that maintained or grew dividends through multiple cycles (GFC, COVID) have demonstrated management\'s commitment to the income component. Consistency matters more than the current yield.',
    warning: 'A long dividend history does not guarantee the dividend is safe today. Always combine history checks with current payout ratio, FCF cover, and balance sheet analysis.',
  },
]

export default function BestMetricsForDividendInvestorsPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <ArticleSchema
        headline="Best Metrics for ASX Dividend Investors"
        description="The eight metrics every ASX dividend investor should track — from grossed-up yield and payout ratio to dividend CAGR, FCF cover, and balance sheet strength."
        url="https://asxscreener.com.au/learn/best-metrics-for-asx-dividend-investors"
      />

      <Breadcrumb crumbs={[
        { label: 'Education Hub', href: '/learn' },
        { label: 'Best Metrics for ASX Dividend Investors', href: '/learn/best-metrics-for-asx-dividend-investors' },
      ]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Intermediate</span>
          <span className="text-xs text-slate-400">10 min read</span>
          <span className="text-xs text-slate-400">· Last updated Jun 2026</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          Best Metrics for ASX Dividend Investors
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Most income investors start with dividend yield. But yield alone is not enough — a 9% yield can be a great opportunity or an imminent cut. These eight metrics tell the complete story: how sustainable the dividend is, how much it is really worth to you after tax, and whether it is likely to grow.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-2xl p-5 hover:from-emerald-700 hover:to-teal-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Dividend Stocks</p>
          <p className="text-emerald-200 text-sm">Filter by all 8 metrics — yield, payout ratio, FCF cover, franking, dividend growth and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4 flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-slate-500" />
          The 8 essential dividend metrics
        </h2>
        <div className="space-y-4">
          {METRICS.map(({ n, name, field, target, why, warning }) => (
            <div key={field} className="bg-white border border-slate-200 rounded-2xl p-5">
              <div className="flex items-start gap-3 mb-3">
                <span className="w-7 h-7 rounded-full bg-emerald-600 text-white text-sm font-bold flex items-center justify-center shrink-0">{n}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <p className="font-bold text-slate-900">{name}</p>
                    <code className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{field}</code>
                  </div>
                  <p className="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full inline-block">{target}</p>
                </div>
              </div>
              <p className="text-sm text-slate-600 leading-relaxed mb-3">{why}</p>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                <p className="text-xs text-amber-800 leading-relaxed">{warning}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Combining the metrics — a scoring approach</h2>
        <p className="text-slate-600 leading-relaxed text-sm mb-3">
          No single metric is sufficient on its own. A practical approach is to require stocks to pass a minimum number of the following criteria:
        </p>
        <div className="bg-slate-900 rounded-xl p-4">
          <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{`// Dividend quality screening — require at least 5 of these 6:
grossed_up_yield > 5
payout_ratio < 70
fcf_payout_ratio < 70
dividend_growth_3y > 5
franking_pct > 50
eps_growth_1y > 0

// Plus balance sheet stability:
net_debt_to_ebitda < 2.5
market_cap > 300`}</code>
        </div>
        <Link href="/screener" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800">
          Apply this screen <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
        </Link>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related articles
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/dividend-yield-vs-grossed-up-yield', label: 'Dividend Yield vs Grossed-Up Yield Explained' },
            { href: '/learn/how-to-check-asx-dividend-sustainability', label: 'How to Check If an ASX Dividend Is Sustainable' },
            { href: '/learn/building-an-asx-dividend-portfolio', label: 'Building a Dividend Portfolio on the ASX' },
            { href: '/learn/franking-credits-explained', label: 'Franking Credits Explained' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />{label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p><strong>Not financial advice.</strong> Dividend metrics are research tools only. Past dividend payment is not a guarantee of future dividends. Always conduct your own due diligence.</p>
      </div>
    </div>
  )
}
