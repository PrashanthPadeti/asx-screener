import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Watchlist | Track Australian Stocks in One Place | ASX Screener',
  description: 'Create ASX watchlists, monitor price moves, compare key metrics, and follow stocks before making investment decisions.',
  alternates: { canonical: 'https://asxscreener.com.au/watchlist' },
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
