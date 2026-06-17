import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, CheckSquare, TrendingUp, Clock, ArrowRight } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Free ASX Investor Resources | ASX Screener',
  description: 'Free checklists, guides, and routines for ASX investors. Download or print our stock screening checklist, dividend research checklist, and daily market review routine.',
  alternates: { canonical: 'https://asxscreener.com.au/resources' },
}

const RESOURCES = [
  {
    href: '/resources/asx-stock-screening-checklist',
    icon: CheckSquare,
    title: 'ASX Stock Screening Checklist',
    desc: 'A step-by-step checklist for running a disciplined screen — from setting your criteria to reviewing the shortlist before adding stocks to your watchlist.',
    badge: 'Checklist',
    badgeColor: 'bg-blue-100 text-blue-700',
    time: '5 min read',
  },
  {
    href: '/resources/dividend-research-checklist',
    icon: TrendingUp,
    title: 'Dividend Research Checklist',
    desc: 'Before you add an income stock to your portfolio, run through this checklist. Covers yield, franking, payout ratio, sustainability, and yield trap warning signs.',
    badge: 'Checklist',
    badgeColor: 'bg-emerald-100 text-emerald-700',
    time: '5 min read',
  },
  {
    href: '/resources/15-minute-asx-market-review-routine',
    icon: Clock,
    title: '15-Minute ASX Market Review Routine',
    desc: 'A structured daily or weekly routine for staying on top of the ASX without spending hours on market monitoring. Covers indices, announcements, watchlist, and alerts.',
    badge: 'Routine',
    badgeColor: 'bg-amber-100 text-amber-700',
    time: '4 min read',
  },
]

export default function ResourcesPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12 space-y-10">

      <div>
        <h1 className="text-3xl font-bold text-slate-900 mb-3 leading-tight">Free ASX Investor Resources</h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Practical checklists and routines for disciplined ASX investors. Free to use, print, or save.
        </p>
      </div>

      <div className="space-y-4">
        {RESOURCES.map(({ href, icon: Icon, title, desc, badge, badgeColor, time }) => (
          <Link
            key={href}
            href={href}
            className="block bg-white border border-slate-200 rounded-2xl p-6 hover:border-blue-300 hover:shadow-md transition-all group"
          >
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center shrink-0 group-hover:bg-blue-50 transition-colors">
                <Icon className="w-5 h-5 text-slate-600 group-hover:text-blue-600" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1.5">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${badgeColor}`}>{badge}</span>
                  <span className="text-xs text-slate-400">{time}</span>
                </div>
                <h2 className="font-bold text-slate-900 mb-1.5 group-hover:text-blue-700 transition-colors">{title}</h2>
                <p className="text-sm text-slate-600 leading-relaxed">{desc}</p>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-blue-500 shrink-0 mt-1 transition-colors" />
            </div>
          </Link>
        ))}
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Ready to screen ASX stocks?</h2>
        <p className="text-blue-100 mb-5 text-sm">Use our free screener to apply your criteria across 2,000+ ASX stocks.</p>
        <Link
          href="/screener"
          className="inline-flex items-center gap-2 bg-white text-blue-700 font-semibold px-5 py-2.5 rounded-xl hover:bg-blue-50 transition-colors"
        >
          <BarChart2 className="w-4 h-4" />
          Open the Screener
        </Link>
      </div>

    </div>
  )
}
