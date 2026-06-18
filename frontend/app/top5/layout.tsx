import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'AlphaFive — Weekly Algo-Ranked Top 5 ASX Stocks',
  description: 'ASX Screener\'s weekly algo-ranked AlphaFive — five ASX 200 stocks selected by quantitative strategy each week. Research tool, not financial advice.',
  alternates: { canonical: 'https://asxscreener.com.au/top5' },
  openGraph: {
    title: 'AlphaFive — Weekly Algo-Ranked Top 5 ASX Stocks',
    description: 'ASX Screener\'s weekly algo-ranked AlphaFive — five ASX 200 stocks selected by quantitative strategy each week.',
    url: 'https://asxscreener.com.au/top5',
  },
}

export default function Top5Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
