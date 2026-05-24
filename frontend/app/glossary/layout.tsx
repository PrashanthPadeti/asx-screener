import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Metrics Glossary',
  description: 'Plain-English definitions for every financial metric in ASX Screener — PE ratio, ROE, dividend yield, franking credits, debt-to-equity and more.',
  alternates: { canonical: 'https://asxscreener.com.au/glossary' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
