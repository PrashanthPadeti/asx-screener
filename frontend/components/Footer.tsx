'use client'
import Link from 'next/link'

function CookieSettingsButton() {
  return (
    <button
      onClick={() => window.dispatchEvent(new Event('open-cookie-settings'))}
      className="hover:text-slate-300 transition-colors text-left"
    >
      Cookie Settings
    </button>
  )
}

const FOOTER_COLUMNS = [
  {
    heading: 'Product',
    links: [
      { href: '/screener',  label: 'Screener' },
      { href: '/scans',     label: 'Alpha Screens' },
      { href: '/watchlist', label: 'Watchlist' },
      { href: '/portfolio', label: 'Portfolio' },
      { href: '/alerts',    label: 'Alerts' },
      { href: '/pricing',   label: 'Pricing' },
    ],
  },
  {
    heading: 'Market Data',
    links: [
      { href: '/market',          label: 'Market Overview' },
      { href: '/news',            label: 'News' },
      { href: '/indices',         label: 'ASX Indices' },
      { href: '/funds',           label: 'ETFs & Funds' },
      { href: '/commodities',     label: 'Commodities' },
      { href: '/global-markets',  label: 'Global Markets' },
      { href: '/sectors',         label: 'Sectors' },
    ],
  },
  {
    heading: 'Education',
    links: [
      { href: '/learn',     label: 'Education Hub' },
      { href: '/glossary',  label: 'Glossary' },
      { href: '/resources', label: 'Resources' },
      { href: '/brokers',   label: 'Broker Compare' },
    ],
  },
  {
    heading: 'Trust',
    links: [
      { href: '/data-freshness',          label: 'Data Freshness' },
      { href: '/ai-insights-limitations', label: 'AI Insights Limitations' },
      { href: '/disclaimer',              label: 'Disclaimer' },
    ],
  },
]

export default function Footer() {
  const year = new Date().getFullYear()

  return (
    <footer className="mt-16 border-t border-slate-200 bg-white">
      {/* Disclaimer bar */}
      <div className="bg-amber-50 border-b border-amber-100 px-4 py-3">
        <p className="max-w-screen-2xl mx-auto text-xs text-amber-800 leading-relaxed">
          <span className="font-semibold">Disclaimer:</span> The information provided on ASX
          Screener is for informational and educational purposes only. It does not constitute
          financial advice, a recommendation to buy or sell any security, or an offer of any kind.
          Past performance is not indicative of future results. All data is sourced from publicly
          available information and may contain errors or omissions. You should seek independent
          financial advice before making any investment decision.{' '}
          <span className="font-medium">Always do your own research (DYOR).</span>
        </p>
      </div>

      {/* Main footer columns */}
      <div className="max-w-screen-2xl mx-auto px-4 py-10">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
          {FOOTER_COLUMNS.map(({ heading, links }) => (
            <div key={heading}>
              <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3">
                {heading}
              </h3>
              <ul className="space-y-2">
                {links.map(({ href, label }) => (
                  <li key={href}>
                    <Link
                      href={href}
                      className="text-sm text-slate-500 hover:text-slate-800 transition-colors"
                    >
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="mt-10 pt-6 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-1.5">
            <span className="text-blue-600 font-bold text-sm">ASX Screener</span>
            <span className="text-slate-300">·</span>
            <span className="text-xs text-slate-400">Australian Stock Analysis</span>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-slate-400">
            <Link href="/terms"   className="hover:text-slate-600 transition-colors">Terms of Service</Link>
            <Link href="/privacy" className="hover:text-slate-600 transition-colors">Privacy Policy</Link>
            <CookieSettingsButton />
          </div>

          <span className="text-xs text-slate-400">© {year} ASX Screener. Data for informational use only.</span>
        </div>
      </div>
    </footer>
  )
}
