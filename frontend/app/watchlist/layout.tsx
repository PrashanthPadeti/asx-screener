import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Watchlist',
  description: 'Track your favourite ASX stocks in one place. Get alerts when they hit your targets.',
  alternates: { canonical: 'https://asxscreener.com.au/watchlist' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
