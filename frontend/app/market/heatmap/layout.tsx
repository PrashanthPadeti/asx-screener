import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Performance Heatmap — ASX Screener',
  description:
    'Rolling 5-day and 5-week price performance heatmap for all ASX-listed stocks. ' +
    'Instantly spot momentum, sector rotations and outlier moves across the entire market.',
}

export default function HeatmapLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
