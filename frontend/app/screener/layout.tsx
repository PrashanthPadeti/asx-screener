import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Stock Screener | Filter Australian Shares by Dividends, Growth, ROE and More',
  description: 'Use ASX Screener to filter ASX stocks by market cap, P/E, ROE, ROIC, dividend yield, franking credits, revenue growth, returns, sector, and 80+ more metrics. Free to start.',
  alternates: { canonical: 'https://asxscreener.com.au/screener' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
