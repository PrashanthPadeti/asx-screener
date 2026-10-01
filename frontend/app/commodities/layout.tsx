import type { Metadata } from 'next'

export const metadata: Metadata = {
  // A plain `title` string resolves to an absolute title and clears the
  // inherited template, so pages under this segment received no site
  // suffix and had hardcoded their own. Only `template` propagates.
  title: {
    default:  'Commodities — Gold, Iron Ore, Oil & Base Metals Prices',
    template: '%s | ASX Screener',
  },
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
