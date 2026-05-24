import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Stock Screener',
  description: 'Screen every ASX stock by PE ratio, dividend yield, franking credits, ROE, debt, cash flow and 80+ more metrics. Free to start.',
  alternates: { canonical: 'https://asxscreener.com.au/screener' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
