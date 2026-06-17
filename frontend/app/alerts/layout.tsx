import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Price Alerts | Monitor Australian Stocks Automatically | ASX Screener',
  description: 'Set price alerts for ASX stocks and get notified when important price levels are reached. Stay on top of your watchlist without watching the market all day.',
  alternates: { canonical: 'https://asxscreener.com.au/alerts' },
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
