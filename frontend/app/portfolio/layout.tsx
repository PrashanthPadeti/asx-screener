import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Portfolio Tracker',
  description: 'Track your ASX portfolio performance, monitor holdings, and analyse your investment returns.',
  alternates: { canonical: 'https://asxscreener.com.au/portfolio' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
