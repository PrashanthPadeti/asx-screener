import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Portfolio Tracker | Track Holdings, Dividends & Franking | ASX Screener',
  description: 'Track your ASX holdings, gains, dividend income, franking credits, and portfolio performance in one place. Built for Australian investors.',
  alternates: { canonical: 'https://asxscreener.com.au/portfolio' },
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
