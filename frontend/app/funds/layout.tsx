import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX ETFs & Funds — ETFs, LICs & Managed Funds',
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
