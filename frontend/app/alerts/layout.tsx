import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Price Alerts',
  description: 'Set price and volume alerts for ASX stocks. Get notified by email or SMS when your targets are hit.',
  alternates: { canonical: 'https://asxscreener.com.au/alerts' },
  robots: { index: false, follow: false },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
