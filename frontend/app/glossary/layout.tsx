import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX Investing Glossary | Stock Market Terms Explained | ASX Screener',
  description: 'Plain-English definitions for every ASX stock market metric — P/E ratio, ROE, ROIC, dividend yield, franking credits, EV/EBITDA, debt-to-equity and 200+ more terms explained simply.',
  alternates: { canonical: 'https://asxscreener.com.au/glossary' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
