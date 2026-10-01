import type { Metadata } from 'next'

export const metadata: Metadata = {
  // A plain `title` string resolves to an absolute title and clears the
  // inherited template, so pages under this segment received no site
  // suffix and had hardcoded their own. Only `template` propagates.
  title: {
    default:  'ASX Market Overview | Top Movers, Sector Heatmap and Market Signals',
    template: '%s | ASX Screener',
  },
  description: 'Track ASX market activity, sector performance, top gainers, top losers, volume activity, and market signals. Live ASX market overview for Australian investors.',
  alternates: { canonical: 'https://asxscreener.com.au/market' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
