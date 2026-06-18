import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Commodities — Gold, Iron Ore, Oil & Base Metals Prices',
  description: 'Live commodity prices relevant to ASX investors — gold, iron ore, oil, copper, nickel, and more. Understand how commodity moves affect ASX mining and energy stocks.',
  alternates: { canonical: 'https://asxscreener.com.au/commodities' },
  openGraph: {
    title: 'Commodities — Gold, Iron Ore, Oil & Base Metals Prices',
    description: 'Live commodity prices relevant to ASX investors — gold, iron ore, oil, copper, nickel, and more.',
    url: 'https://asxscreener.com.au/commodities',
  },
}

export default function CommoditiesLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
