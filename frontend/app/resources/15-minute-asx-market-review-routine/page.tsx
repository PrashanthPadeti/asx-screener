import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, AlertTriangle, ChevronLeft, Zap, BookOpen, Clock, Bell, Eye, TrendingUp, FileText, CheckCircle2 } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: '15-Minute ASX Market Review Routine | ASX Screener',
  description: 'A structured 15-minute routine for ASX investors to stay on top of the market without spending hours monitoring prices. Covers index check, announcements, watchlist, and alerts.',
  alternates: { canonical: 'https://asxscreener.com.au/resources/15-minute-asx-market-review-routine' },
}

const ROUTINE = [
  {
    minutes: '0–2 min',
    icon: TrendingUp,
    title: 'Index snapshot',
    color: 'blue',
    steps: [
      'Check ASX 200 open or close — up, down, or flat?',
      'Note the sector moves: which sectors are leading or lagging?',
      'Check the AUD/USD — relevant if you hold resources or export-heavy stocks.',
      'Any overnight Wall Street or major index moves that set the tone?',
    ],
  },
  {
    minutes: '2–6 min',
    icon: FileText,
    title: 'Announcements scan',
    color: 'purple',
    steps: [
      'Open the ASX announcements feed and filter for "Price Sensitive" only.',
      'Scan for announcements from companies on your watchlist or portfolio.',
      'Flag any capital raises, trading halts, results, or guidance updates for deeper reading.',
      'Read in full any announcement that directly affects stocks you hold.',
    ],
  },
  {
    minutes: '6–10 min',
    icon: Eye,
    title: 'Watchlist review',
    color: 'emerald',
    steps: [
      'Open your watchlist and scan current prices vs your target levels.',
      'Has anything moved significantly without a clear announcement reason? Investigate.',
      'Are any stocks approaching your price alert thresholds?',
      'Review thesis for any stock that has had a material announcement since your last review.',
      'Remove any stocks where the thesis has materially changed.',
    ],
  },
  {
    minutes: '10–13 min',
    icon: Bell,
    title: 'Alerts & action items',
    color: 'amber',
    steps: [
      'Check any price alerts that triggered since your last session.',
      'Review alerts on stocks approaching results dates — are you prepared?',
      'Update any stale price targets based on recent price or earnings changes.',
      'Note any stocks that warrant deeper research before the next results period.',
    ],
  },
  {
    minutes: '13–15 min',
    icon: CheckCircle2,
    title: 'Weekly add-on (once per week)',
    color: 'rose',
    steps: [
      'Run a quick screen on your preferred strategy to check for new candidates.',
      'Review any upcoming results dates in the next 2 weeks.',
      'Check ASIC short interest for any watchlist stocks with high short positions.',
      'Read one learn article or piece of market commentary relevant to your holdings.',
    ],
  },
]

const COLOR_MAP: Record<string, { bg: string; text: string; border: string; icon: string }> = {
  blue:    { bg: 'bg-blue-50',    text: 'text-blue-800',    border: 'border-blue-200',    icon: 'text-blue-600' },
  purple:  { bg: 'bg-purple-50',  text: 'text-purple-800',  border: 'border-purple-200',  icon: 'text-purple-600' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-800', border: 'border-emerald-200', icon: 'text-emerald-600' },
  amber:   { bg: 'bg-amber-50',   text: 'text-amber-800',   border: 'border-amber-200',   icon: 'text-amber-600' },
  rose:    { bg: 'bg-rose-50',    text: 'text-rose-800',    border: 'border-rose-200',    icon: 'text-rose-600' },
}

export default function MarketReviewRoutinePage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Resources', href: '/resources' }, { label: '15-Minute Market Review Routine', href: '/resources/15-minute-asx-market-review-routine' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">Routine</span>
          <span className="text-xs text-slate-400">4 min read · Daily or weekly</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          The 15-Minute ASX Market Review Routine
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Staying informed about the ASX does not require hours of monitoring. This structured 15-minute routine gives you everything you need to stay on top of your watchlist and portfolio — without the noise.
        </p>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> How to use this routine
        </h2>
        <ul className="space-y-1.5 text-sm text-blue-900">
          {[
            'Run the first 4 steps daily (or on trading days when you check in).',
            'Step 5 is a weekly add-on — do it once at the weekend or Monday morning.',
            'Use price alerts so you do not need to check prices every day. Let the alerts come to you.',
            'The goal is informed awareness, not constant monitoring. Once through = done.',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-0.5 w-4 h-4 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-4">
        {ROUTINE.map(({ minutes, icon: Icon, title, color, steps }) => {
          const c = COLOR_MAP[color]
          return (
            <div key={title} className={`${c.bg} border ${c.border} rounded-2xl p-6`}>
              <div className="flex items-start gap-4">
                <div className="shrink-0">
                  <div className={`w-10 h-10 rounded-xl bg-white border ${c.border} flex items-center justify-center`}>
                    <Icon className={`w-5 h-5 ${c.icon}`} />
                  </div>
                </div>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-3 mb-2">
                    <h2 className={`font-bold ${c.text}`}>{title}</h2>
                    <span className={`flex items-center gap-1 text-xs font-medium ${c.text} opacity-70`}>
                      <Clock className="w-3 h-3" /> {minutes}
                    </span>
                  </div>
                  <ul className="space-y-2">
                    {steps.map(step => (
                      <li key={step} className="flex items-start gap-2 text-sm text-slate-700">
                        <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${c.icon.replace('text-', 'bg-')}`} />
                        {step}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="bg-slate-900 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide mb-4">Tools for this routine</h2>
        <div className="space-y-3">
          {[
            { tool: 'ASX Screener', use: 'Weekly screen for new candidates; watchlist monitoring', href: '/screener' },
            { tool: 'My Watchlist', use: 'Track researched stocks with price levels and thesis notes', href: '/watchlist' },
            { tool: 'Price Alerts', use: 'Get notified when stocks hit your target — no daily checking needed', href: '/alerts' },
            { tool: 'ASX Market Data', use: 'Index levels, sector performance, and market breadth', href: '/market' },
          ].map(({ tool, use, href }) => (
            <Link key={tool} href={href} className="flex items-start gap-3 bg-slate-800 rounded-xl p-3 hover:bg-slate-700 transition-colors">
              <div className="flex-1">
                <p className="text-sm font-semibold text-white">{tool}</p>
                <p className="text-xs text-slate-400 mt-0.5">{use}</p>
              </div>
              <ChevronLeft className="w-4 h-4 text-slate-400 rotate-180 shrink-0 mt-0.5" />
            </Link>
          ))}
        </div>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related Resources
        </h2>
        <div className="space-y-2">
          {[
            { href: '/learn/how-to-build-an-asx-watchlist', label: 'How to Build an ASX Watchlist' },
            { href: '/learn/how-to-read-company-announcements', label: 'How to Read ASX Company Announcements' },
            { href: '/resources/asx-stock-screening-checklist', label: 'ASX Stock Screening Checklist' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />
              {label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p>
          <strong>Not financial advice.</strong> This routine is a general educational framework only. Nothing here constitutes a recommendation to buy or sell any security.
        </p>
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-7 text-white text-center">
        <h2 className="text-xl font-bold mb-2">Set up your watchlist and alerts</h2>
        <p className="text-blue-100 mb-5 text-sm">Let price alerts do the monitoring for you. Add stocks to your watchlist and get notified when they move.</p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link href="/watchlist" className="inline-flex items-center gap-2 bg-white text-blue-700 font-semibold px-5 py-2.5 rounded-xl hover:bg-blue-50 transition-colors">
            <Eye className="w-4 h-4" /> My Watchlist
          </Link>
          <Link href="/alerts" className="inline-flex items-center gap-2 bg-blue-500 hover:bg-blue-400 text-white font-semibold px-5 py-2.5 rounded-xl transition-colors">
            <Bell className="w-4 h-4" /> Set Alerts
          </Link>
        </div>
      </div>

    </div>
  )
}
