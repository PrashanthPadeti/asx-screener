import type { Metadata } from 'next'
import { SCREENER_FIELDS_CLAIM } from '@/lib/claims'

export const metadata: Metadata = {
  // A plain `title` string resolves to an absolute title and clears the
  // inherited template, so pages under this segment received no site
  // suffix and had hardcoded their own. Only `template` propagates.
  title: {
    default:  'ASX Stock Screener | Filter Australian Shares by Dividends, Growth, ROE and More',
    template: '%s | ASX Screener',
  },
  description: `Use ASX Screener to filter ASX stocks by market cap, P/E, ROE, ROIC, dividend yield, franking credits, revenue growth, returns, sector, and ${SCREENER_FIELDS_CLAIM} filterable fields. Free to start.`,
  alternates: { canonical: 'https://asxscreener.com.au/screener' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
