import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Indices — S&P/ASX Benchmark & Sector Performance',
  description: 'Track S&P/ASX 200, ASX 300, sector indices, and constituent performance. Live price data and historical returns for all major Australian benchmark indices.',
  alternates: { canonical: 'https://asxscreener.com.au/indices' },
  openGraph: {
    title: 'ASX Indices — S&P/ASX Benchmark & Sector Performance',
    description: 'Track S&P/ASX 200, ASX 300, sector indices, and constituent performance. Live price data for all major Australian benchmark indices.',
    url: 'https://asxscreener.com.au/indices',
  },
}

export default function IndicesLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
