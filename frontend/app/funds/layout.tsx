import type { Metadata } from 'next'

export const metadata: Metadata = {
  // A plain `title` string resolves to an absolute title and clears the
  // inherited template, so pages under this segment received no site
  // suffix and had hardcoded their own. Only `template` propagates.
  title: {
    default:  'ASX ETFs & Funds — ETFs, LICs & Managed Funds',
    template: '%s | ASX Screener',
  },
  description: 'Research ASX-listed ETFs, LICs, and managed funds. Filter by asset class, management style, fees, and performance. Data for Australian investors.',
  alternates: { canonical: 'https://asxscreener.com.au/funds' },
  openGraph: {
    title: 'ASX ETFs & Funds — ETFs, LICs & Managed Funds',
    description: 'Research ASX-listed ETFs, LICs, and managed funds. Filter by asset class, management style, fees, and performance.',
    url: 'https://asxscreener.com.au/funds',
  },
}

export default function FundsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
