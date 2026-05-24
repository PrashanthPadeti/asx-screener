import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Contact Support',
  description: 'Get help with ASX Screener — report bugs, ask questions, or contact us about billing and data issues.',
  alternates: { canonical: 'https://asxscreener.com.au/contact' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
