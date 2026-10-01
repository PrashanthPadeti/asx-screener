import type { Metadata } from 'next'

export const metadata: Metadata = {
  // A plain `title` string resolves to an absolute title and clears the
  // inherited template, so pages under this segment received no site
  // suffix and had hardcoded their own. Only `template` propagates.
  title: {
    default:  'Education Hub',
    template: '%s | ASX Screener',
  },
  description: 'Free investing guides for Australian investors — how to read financial statements, understand franking credits, use stock screeners and more.',
  alternates: { canonical: 'https://asxscreener.com.au/learn' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
