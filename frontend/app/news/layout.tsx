import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'ASX News & Announcements',
  description: 'Latest ASX company announcements, earnings results and market news in one place.',
  alternates: { canonical: 'https://asxscreener.com.au/news' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
