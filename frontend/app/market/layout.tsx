import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Market Overview',
  description: 'Live ASX market overview — sector heatmap, top movers, ASX 200 & 300 summary, and market breadth data.',
  alternates: { canonical: 'https://asxscreener.com.au/market' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
