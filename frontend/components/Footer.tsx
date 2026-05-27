'use client'
import Link from 'next/link'

function CookieSettingsButton() {
  return (
    <button
      onClick={() => window.dispatchEvent(new Event('open-cookie-settings'))}
      className="hover:text-slate-600 transition-colors cursor-pointer"
    >
      Cookie Settings
    </button>
  )
}

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

      {/* Footer links */}
      <div className="max-w-screen-2xl mx-auto px-4 py-5">
        {/* Top row */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-1.5 font-medium text-slate-500">
            <span className="text-blue-600 font-bold">ASX Screener</span>
            <span>·</span>
            <span>Australian Stock Analysis</span>
          </div>

          {/* Product links */}
          <div className="flex flex-wrap items-center justify-center gap-4">
            <Link href="/market"    className="hover:text-slate-600 transition-colors">Market</Link>
            <Link href="/screener"  className="hover:text-slate-600 transition-colors">Screener</Link>
            <Link href="/watchlist" className="hover:text-slate-600 transition-colors">Watchlist</Link>
            <Link href="/portfolio" className="hover:text-slate-600 transition-colors">Portfolio</Link>
            <Link href="/alerts"    className="hover:text-slate-600 transition-colors">Alerts</Link>
          </div>

          <span>© {year} ASX Screener. Data for informational use only.</span>
        </div>

        {/* Bottom row — legal links */}
        <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-slate-400">
          <Link href="/terms"   className="hover:text-slate-600 transition-colors">Terms of Service</Link>
          <Link href="/privacy" className="hover:text-slate-600 transition-colors">Privacy Policy</Link>
          <CookieSettingsButton />
          <Link href="/learn"   className="hover:text-slate-600 transition-colors">Education Hub</Link>
          <Link href="/brokers" className="hover:text-slate-600 transition-colors">Broker Compare</Link>
          <Link href="/glossary" className="hover:text-slate-600 transition-colors">Glossary</Link>
          <Link href="/contact" className="hover:text-slate-600 transition-colors">Contact Support</Link>
          <Link href="/pricing" className="hover:text-slate-600 transition-colors">Pricing</Link>
        </div>
      </div>
    </footer>
  )
}
