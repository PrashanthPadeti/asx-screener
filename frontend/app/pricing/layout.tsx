import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Pricing Plans',
  description: 'Simple, transparent pricing for ASX Screener. Free plan available. Pro and Premium plans from $19.99/month.',
  alternates: { canonical: 'https://asxscreener.com.au/pricing' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
