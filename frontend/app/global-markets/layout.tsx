import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Global Markets — US, Europe & Asia Indices and AUD Exchange Rates',
  description: 'Global market data for Australian investors — US, European, and Asian index performance, AUD exchange rates, and international market context.',
  alternates: { canonical: 'https://asxscreener.com.au/global-markets' },
  openGraph: {
    title: 'Global Markets — US, Europe & Asia Indices and AUD Exchange Rates',
    description: 'Global market data for Australian investors — US, European, and Asian index performance plus AUD exchange rates.',
    url: 'https://asxscreener.com.au/global-markets',
  },
}

export default function GlobalMarketsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
