import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Market Overview | Top Movers, Sector Heatmap and Market Signals',
  description: 'Track ASX market activity, sector performance, top gainers, top losers, volume activity, and market signals. Live ASX market overview for Australian investors.',
  alternates: { canonical: 'https://asxscreener.com.au/market' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
