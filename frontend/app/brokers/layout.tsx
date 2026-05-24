import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Best ASX Brokers 2026',
  description: 'Compare the best ASX share trading platforms in 2026. Side-by-side comparison of brokerage fees, features, and platforms for Australian investors.',
  alternates: { canonical: 'https://asxscreener.com.au/brokers' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
