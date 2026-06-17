import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Alpha Screens | Ready-Made Stock Screens for Australian Investors',
  description: 'Explore ready-made ASX stock screens for dividend income, growth, value, momentum, quality, and sector strategies. Run any screen instantly in the ASX Screener.',
  alternates: { canonical: 'https://asxscreener.com.au/scans' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
