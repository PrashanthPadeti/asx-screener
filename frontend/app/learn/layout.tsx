import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Education Hub',
  description: 'Free investing guides for Australian investors — how to read financial statements, understand franking credits, use stock screeners and more.',
  alternates: { canonical: 'https://asxscreener.com.au/learn' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
