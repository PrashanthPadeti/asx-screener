import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Market Scans',
  description: 'Pre-built ASX stock screens for value investing, dividend income, growth, momentum and more. Run any scan instantly in the full screener.',
  alternates: { canonical: 'https://asxscreener.com.au/scans' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
