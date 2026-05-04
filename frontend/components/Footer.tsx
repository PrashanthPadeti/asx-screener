import Link from 'next/link'

export default function Footer() {
  const year = new Date().getFullYear()

  return (
    <footer className="mt-16 border-t border-slate-200 bg-white">
      {/* Disclaimer bar */}
      <div className="bg-amber-50 border-b border-amber-100 px-4 py-3">
        <p className="max-w-screen-2xl mx-auto text-xs text-amber-800 leading-relaxed">
          <span className="font-semibold">Disclaimer:</span> The information provided on ASX Screener is for informational and educational purposes only. It does not constitute financial advice, a recommendation to buy or sell any security, or an offer of any kind. Past performance is not indicative of future results. All data is sourced from publicly available information and may contain errors or omissions. You should seek independent financial advice before making any investment decision.{' '}
          <span className="font-medium">Always do your own research (DYOR).</span>
        </p>
      </div>

      {/* Footer links */}
      <div className="max-w-screen-2xl mx-auto px-4 py-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-400">
        <div className="flex items-center gap-1.5 font-medium text-slate-500">
          <span className="text-blue-600 font-bold">ASX Screener</span>
          <span>·</span>
          <span>Australian Stock Analysis</span>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-4">
          <Link href="/market"    className="hover:text-slate-600 transition-colors">Market</Link>
          <Link href="/screener"  className="hover:text-slate-600 transition-colors">Screener</Link>
          <Link href="/watchlist" className="hover:text-slate-600 transition-colors">Watchlist</Link>
          <Link href="/alerts"    className="hover:text-slate-600 transition-colors">Alerts</Link>
        </div>

        <span>© {year} ASX Screener. Data for informational use only.</span>
      </div>
    </footer>
  )
}
