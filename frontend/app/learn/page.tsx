'use client'
import { useState, useCallback } from 'react'
import Link from 'next/link'
import {
  ExternalLink, BookOpen, TrendingUp, PieChart, DollarSign,
  BarChart2, Zap, ChevronRight, Play, Bell, CheckCircle2,
  Clock, Lock, ArrowRight,
} from 'lucide-react'

// ── Analytics helper ─────────────────────────────────────────────────────────
// Fires to GA4 (gtag) and/or Segment (analytics.track) if either is loaded.
// Silently no-ops when neither is present (dev / SSR).

type EventProps = Record<string, string | number | boolean | undefined>

function trackEvent(name: string, props?: EventProps) {
  if (typeof window === 'undefined') return
  try {
    const w = window as Window & {
      gtag?: (...args: unknown[]) => void
      analytics?: { track: (name: string, props?: EventProps) => void }
    }
    w.gtag?.('event', name, props)
    w.analytics?.track(name, props)
  } catch {
    // never let tracking errors surface to users
  }
}

// ── Types ────────────────────────────────────────────────────────────────────

type Level = 'Beginner' | 'Intermediate' | 'Advanced'

interface Guide {
  title: string
  description: string
  readTime: string
  level: Level
  href?: string          // omit for comingSoon guides — prevents accidental navigation
  buttonLabel?: string   // "Read guide" | "Try this screen" | "Open tool"
  comingSoon?: boolean
  internal?: boolean     // true → links to an interactive tool (screener, brokers, etc.)
}

interface Course {
  title: string
  provider: string
  description: string
  price: string
  rating: number
  students: string
  affiliateUrl: string
  tag?: string
}

interface BeginnerStep {
  n: number
  title: string
  desc: string
  href: string
  icon: React.ElementType
}

// ── Beginner pathway ─────────────────────────────────────────────────────────
// All 6 steps link to real pages — no coming-soon items in the pathway.

const BEGINNER_STEPS: BeginnerStep[] = [
  { n: 1, title: 'What Is a Stock Screener?',  desc: 'How investors use screeners to filter the ASX market.',  href: '/learn/what-is-an-asx-stock-screener',     icon: BookOpen    },
  { n: 2, title: 'Franking Credits',           desc: 'Australia\'s unique dividend tax system explained.',      href: '/learn/franking-credits-explained',         icon: Zap         },
  { n: 3, title: 'Company Announcements',      desc: 'How to read and interpret ASX company updates.',         href: '/learn/how-to-read-company-announcements',  icon: TrendingUp  },
  { n: 4, title: 'Key Financial Ratios',       desc: 'P/E, ROE, D/E — the metrics every investor needs.',      href: '/learn/key-financial-ratios',               icon: BarChart2   },
  { n: 5, title: 'Build Your First Watchlist', desc: 'How to build and maintain an ASX watchlist.',            href: '/learn/how-to-build-an-asx-watchlist',     icon: CheckCircle2 },
  { n: 6, title: 'Run Your First Screen',      desc: 'Filter 200+ ASX stocks using real fundamental data.',    href: '/screener',                                icon: ArrowRight  },
]

// ── Guide catalogue ──────────────────────────────────────────────────────────

const GUIDES: { category: string; icon: React.ElementType; color: string; guides: Guide[] }[] = [
  {
    category: 'Getting Started',
    icon: BookOpen,
    color: 'blue',
    guides: [
      {
        title: 'What Is an ASX Stock Screener?',
        description: 'How investors use a stock screener to filter 2,000+ ASX stocks down to a shortlist worth researching.',
        readTime: '7 min', level: 'Beginner',
        href: '/learn/what-is-an-asx-stock-screener', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Screen ASX Stocks for Beginners',
        description: 'Step-by-step guide to your first ASX screen — which filters to start with, how to research results, and common mistakes to avoid.',
        readTime: '10 min', level: 'Beginner',
        href: '/learn/how-to-screen-asx-stocks-for-beginners', buttonLabel: 'Read guide',
      },
      {
        title: 'One ASX Screener, Three Ways to Search',
        description: 'Filter mode, AI Query, and Query Mode explained — which approach suits your investing style and when to use each one.',
        readTime: '8 min', level: 'Beginner',
        href: '/learn/asx-screener-three-ways-to-search', buttonLabel: 'Read guide',
      },
      {
        title: 'Understanding Franking Credits',
        description: 'Australia\'s unique dividend imputation system explained — and how to calculate your grossed-up yield.',
        readTime: '8 min', level: 'Beginner',
        href: '/learn/franking-credits-explained', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Read ASX Company Announcements',
        description: 'The different announcement types on the ASX and what to look for in each one.',
        readTime: '6 min', level: 'Beginner',
        href: '/learn/how-to-read-company-announcements', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Research ASX Stocks — DYOR Workflow',
        description: 'A step-by-step process for researching any ASX company before adding it to your watchlist.',
        readTime: '10 min', level: 'Beginner',
        href: '/learn/how-to-research-asx-stocks-dyor', buttonLabel: 'Read guide',
      },
      {
        title: 'ASX Stock Research Checklist',
        description: 'Six-section due diligence checklist: business, financials, valuation, management, announcements, and risks.',
        readTime: '6 min', level: 'Beginner',
        href: '/learn/asx-stock-research-checklist', buttonLabel: 'Read guide',
      },
    ],
  },
  {
    category: 'Fundamental Analysis',
    icon: BarChart2,
    color: 'purple',
    guides: [
      {
        title: 'Key Financial Ratios for ASX Investors',
        description: 'P/E, P/B, EV/EBITDA, ROE — which ratios matter most for Australian stocks and how to use them.',
        readTime: '10 min', level: 'Intermediate',
        href: '/learn/key-financial-ratios', buttonLabel: 'Read guide',
      },
      {
        title: 'ROE Explained: How Investors Use Return on Equity',
        description: 'What ROE is, how to calculate it, what counts as a good ROE by sector, and how to use it with ROCE and ROIC.',
        readTime: '9 min', level: 'Intermediate',
        href: '/learn/roe-explained', buttonLabel: 'Read guide',
      },
      {
        title: 'ROIC Explained: Return on Invested Capital',
        description: 'What ROIC is, the WACC test, why it beats ROE for comparing companies, and how to screen for high-ROIC ASX stocks.',
        readTime: '9 min', level: 'Intermediate',
        href: '/learn/roic-explained', buttonLabel: 'Read guide',
      },
      {
        title: 'Analysing ASX Mining Stocks',
        description: 'How to read AISC, ore reserves, JORC resources, and interpret mining feasibility studies.',
        readTime: '12 min', level: 'Intermediate', comingSoon: true,
      },
      {
        title: 'How to Value ASX REITs (A-REITs)',
        description: 'FFO, NTA, WALE, cap rates — the key metrics unique to real estate investment trusts on the ASX.',
        readTime: '10 min', level: 'Intermediate', comingSoon: true,
      },
    ],
  },
  {
    category: 'Portfolio & Dividends',
    icon: PieChart,
    color: 'emerald',
    guides: [
      {
        title: 'Dividend Yield Explained for ASX Investors',
        description: 'How to calculate dividend yield, what counts as a good yield, how to spot yield traps, and why payout ratio matters.',
        readTime: '8 min', level: 'Beginner',
        href: '/learn/dividend-yield-explained', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Build and Maintain an ASX Watchlist',
        description: 'Screen for candidates, research them, set price alerts, and maintain a live watchlist of stocks worth monitoring.',
        readTime: '7 min', level: 'Beginner',
        href: '/learn/how-to-build-an-asx-watchlist', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Check If an ASX Dividend Is Sustainable',
        description: 'Payout ratio, FCF cover, dividend cover, debt, earnings trend, and franking history — six metrics to avoid yield traps.',
        readTime: '10 min', level: 'Intermediate',
        href: '/learn/how-to-check-asx-dividend-sustainability', buttonLabel: 'Read guide',
      },
      {
        title: 'Building a Dividend Portfolio on the ASX',
        description: 'Sector allocation, stock selection criteria, franking credits, reinvestment, and common mistakes — how to construct a diversified ASX income portfolio.',
        readTime: '12 min', level: 'Intermediate',
        href: '/learn/building-an-asx-dividend-portfolio', buttonLabel: 'Read guide',
      },
      {
        title: 'Understanding the ASX Dividend Calendar',
        description: 'Ex-dividend dates, record dates, payment dates — what they mean and how to plan around them.',
        readTime: '7 min', level: 'Beginner', comingSoon: true,
      },
      {
        title: 'CGT and Tax Planning for Share Investors',
        description: 'Capital gains tax fundamentals for Australian share investors, the 12-month discount, and tax loss harvesting.',
        readTime: '12 min', level: 'Intermediate', comingSoon: true,
      },
    ],
  },
  {
    category: 'Screening Strategies',
    icon: TrendingUp,
    color: 'amber',
    guides: [
      {
        title: 'The High Dividend Yield Screen',
        description: 'How to screen for ASX stocks with sustainable high yields — what to include and what to avoid.',
        readTime: '8 min', level: 'Intermediate',
        href: '/screener', internal: true, buttonLabel: 'Try this screen',
      },
      {
        title: 'Finding Value Stocks on the ASX',
        description: 'A step-by-step value investing screen using P/E, P/B, and debt ratios for the Australian market.',
        readTime: '10 min', level: 'Intermediate',
        href: '/screener', internal: true, buttonLabel: 'Try this screen',
      },
      {
        title: 'How to Find ASX Growth Stocks Using Revenue Growth',
        description: 'Revenue growth, earnings momentum, operating leverage, and PEG ratio — how to screen for quality ASX growth companies.',
        readTime: '10 min', level: 'Intermediate',
        href: '/learn/how-to-find-asx-growth-stocks', buttonLabel: 'Read guide',
      },
      {
        title: 'How ASX Traders Use Volume and Momentum',
        description: 'RSI, moving averages, ADX, volume breakouts — practical technical screens for active ASX traders.',
        readTime: '9 min', level: 'Intermediate',
        href: '/learn/how-to-use-asx-volume-and-momentum', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Find Undervalued ASX Stocks',
        description: 'Value investing metrics explained — P/E, P/B, EV/EBITDA, FCF yield, and how to avoid value traps when screening the ASX.',
        readTime: '10 min', level: 'Intermediate',
        href: '/learn/how-to-find-undervalued-asx-stocks', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Find Quality ASX Companies',
        description: 'Six pillars of quality investing — ROIC, gross margins, earnings consistency, FCF conversion, balance sheet strength, and F-Score.',
        readTime: '10 min', level: 'Intermediate',
        href: '/learn/how-to-find-quality-asx-companies', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Screen for Strong Cash Flow ASX Stocks',
        description: 'Why free cash flow matters more than earnings, and how to screen for FCF margin, FCF yield, and cash conversion on the ASX.',
        readTime: '9 min', level: 'Intermediate',
        href: '/learn/how-to-screen-for-strong-cash-flow-stocks', buttonLabel: 'Read guide',
      },
    ],
  },
  {
    category: 'Dividend Deep Dive',
    icon: DollarSign,
    color: 'emerald',
    guides: [
      {
        title: 'How to Find ASX Dividend Stocks with Franking Credits',
        description: 'A 6-step screening process to find high-quality ASX dividend stocks with strong franking — including grossed-up yield tables by tax bracket.',
        readTime: '10 min', level: 'Intermediate',
        href: '/learn/how-to-find-asx-dividend-stocks-with-franking', buttonLabel: 'Read guide',
      },
      {
        title: 'Dividend Yield vs Grossed-Up Yield Explained',
        description: 'What grossed-up yield means, how franking credits increase effective income, and how to compare franked and unfranked dividends on equal terms.',
        readTime: '8 min', level: 'Beginner',
        href: '/learn/dividend-yield-vs-grossed-up-yield', buttonLabel: 'Read guide',
      },
      {
        title: 'Best Metrics for ASX Dividend Investors',
        description: 'Eight metrics every income investor should track — grossed-up yield, payout ratio, FCF cover, franking, dividend growth, earnings trend, debt, and history.',
        readTime: '10 min', level: 'Intermediate',
        href: '/learn/best-metrics-for-asx-dividend-investors', buttonLabel: 'Read guide',
      },
    ],
  },
  {
    category: 'ASX Screener Product Guides',
    icon: Zap,
    color: 'blue',
    guides: [
      {
        title: 'How ASX Screener AI Query Helps Investors Search in Plain English',
        description: 'Type your investment idea in plain English — AI Query converts it to structured filters instantly. Includes example queries and tips for better results.',
        readTime: '6 min', level: 'Beginner',
        href: '/learn/how-asx-screener-ai-query-works', buttonLabel: 'Read guide',
      },
      {
        title: 'How to Use ASX Screener Alpha Screens',
        description: 'Ready-made screens for dividend, value, growth, quality, momentum, and sector strategies — run any in one click, then customise.',
        readTime: '6 min', level: 'Beginner',
        href: '/learn/how-to-use-asx-alpha-screens', buttonLabel: 'Read guide',
      },
      {
        title: 'How Watchlists and Alerts Help Investors Stay Organised',
        description: 'Track your shortlisted stocks in one place and get notified at your target prices — the screening-to-watchlist workflow explained.',
        readTime: '6 min', level: 'Beginner',
        href: '/learn/how-asx-screener-watchlists-and-alerts-work', buttonLabel: 'Read guide',
      },
    ],
  },
]

// ── Course catalogue ─────────────────────────────────────────────────────────

const COURSES: Course[] = [
  {
    title: 'ASX Share Market for Beginners',
    provider: 'Udemy',
    description: 'A comprehensive introduction to investing on the ASX — from opening a brokerage account to analysing your first stock.',
    price: 'from ~$20', rating: 4.6, students: '10,000+', tag: 'Most Popular',
    affiliateUrl: 'https://www.udemy.com',
  },
  {
    title: 'Dividend Investing Masterclass',
    provider: 'Udemy',
    description: 'Deep dive into building income portfolios, understanding franking credits, and optimising dividend reinvestment.',
    price: 'from ~$25', rating: 4.7, students: '8,000+',
    affiliateUrl: 'https://www.udemy.com',
  },
  {
    title: 'Financial Statement Analysis',
    provider: 'Coursera',
    description: 'Understand balance sheets, income statements, and cash flow statements to make better investment decisions.',
    price: 'Free to audit', rating: 4.8, students: '40,000+',
    affiliateUrl: 'https://www.coursera.org',
  },
  {
    title: 'Technical Analysis for Stocks',
    provider: 'Udemy',
    description: 'Chart patterns, RSI, MACD, moving averages — practical technical analysis for ASX and global markets.',
    price: 'from ~$18', rating: 4.5, students: '20,000+',
    affiliateUrl: 'https://www.udemy.com',
  },
]

// ── Shared style maps ─────────────────────────────────────────────────────────

const LEVEL_BADGE: Record<Level, string> = {
  Beginner:     'bg-emerald-100 text-emerald-700',
  Intermediate: 'bg-blue-100 text-blue-700',
  Advanced:     'bg-purple-100 text-purple-700',
}

const CATEGORY_BG: Record<string, string> = {
  blue:    'bg-blue-50 text-blue-700',
  purple:  'bg-purple-50 text-purple-700',
  emerald: 'bg-emerald-50 text-emerald-700',
  amber:   'bg-amber-50 text-amber-700',
}

const CATEGORY_BORDER: Record<string, string> = {
  blue:    'border-blue-200',
  purple:  'border-purple-200',
  emerald: 'border-emerald-200',
  amber:   'border-amber-200',
}

// ── StarRating ────────────────────────────────────────────────────────────────

function StarRating({ rating }: { rating: number }) {
  return (
    <span className="flex items-center gap-0.5" aria-label={`${rating} out of 5 stars`}>
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} className={`text-xs ${i <= Math.round(rating) ? 'text-amber-400' : 'text-slate-200'}`} aria-hidden>★</span>
      ))}
      <span className="text-xs text-slate-600 ml-1">{rating.toFixed(1)}</span>
    </span>
  )
}

// ── GuideCard ─────────────────────────────────────────────────────────────────

function GuideCard({
  guide,
  color,
  notified,
  onNotify,
}: {
  guide: Guide
  color: string
  notified: Set<string>
  onNotify: (title: string) => void
}) {
  const isNotified = notified.has(guide.title)

  // Decide which tracking event to fire for live guides
  function handleCtaClick() {
    if (!guide.href) return
    if (guide.buttonLabel === 'Try this screen') {
      trackEvent('screen_strategy_clicked', { title: guide.title })
    } else if (guide.buttonLabel === 'Open tool' || guide.internal) {
      trackEvent('guide_opened', { title: guide.title, type: 'tool' })
    } else {
      trackEvent('guide_opened', { title: guide.title, type: 'article' })
    }
  }

  // Coming-soon: visually muted, no pointer events on the card title/content area
  const cardBase = guide.comingSoon
    ? 'bg-white rounded-xl border border-slate-200 p-5 flex flex-col select-none'
    : `bg-white rounded-xl border ${CATEGORY_BORDER[color]} p-5 flex flex-col hover:shadow-sm transition-shadow`

  return (
    <div className={cardBase} aria-disabled={guide.comingSoon}>
      {/* Level badge + read-time row */}
      <div className="flex items-center justify-between mb-3">
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${LEVEL_BADGE[guide.level]} ${guide.comingSoon ? 'opacity-50' : ''}`}>
          {guide.level}
        </span>
        <div className="flex items-center gap-1.5">
          {guide.comingSoon && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-400 border border-slate-200">
              Coming soon
            </span>
          )}
          <span className={`text-xs flex items-center gap-0.5 ${guide.comingSoon ? 'text-slate-300' : 'text-slate-400'}`}>
            <Clock className="w-3 h-3" />{guide.readTime}
          </span>
        </div>
      </div>

      <h3 className={`font-semibold mb-2 leading-snug ${guide.comingSoon ? 'text-slate-400' : 'text-slate-900'}`}>
        {guide.title}
      </h3>
      <p className={`text-sm flex-1 leading-relaxed ${guide.comingSoon ? 'text-slate-300' : 'text-slate-500'}`}>
        {guide.description}
      </p>

      {/* CTA */}
      <div className="mt-4">
        {guide.comingSoon ? (
          /* ── Coming soon: notify button only — no navigation ── */
          <button
            type="button"
            onClick={() => onNotify(guide.title)}
            className={`flex items-center gap-1.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded ${
              isNotified
                ? 'text-emerald-600 cursor-default'
                : 'text-slate-400 hover:text-slate-600 cursor-pointer'
            }`}
            aria-pressed={isNotified}
            aria-label={isNotified ? `Notification registered for ${guide.title}` : `Notify me when ${guide.title} is live`}
          >
            {isNotified
              ? <><CheckCircle2 className="w-3.5 h-3.5 shrink-0" /> You&apos;ll be notified</>
              : <><Bell className="w-3.5 h-3.5 shrink-0" /> Notify me when live</>
            }
          </button>
        ) : (
          /* ── Live guide: navigate + track ── */
          <Link
            href={guide.href!}
            onClick={handleCtaClick}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded"
          >
            {guide.buttonLabel ?? 'Read guide'} <ChevronRight className="w-3.5 h-3.5 shrink-0" />
          </Link>
        )}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LearnPage() {
  const [notified, setNotified] = useState<Set<string>>(new Set())

  const handleNotify = useCallback((title: string) => {
    setNotified(prev => new Set([...prev, title]))
  }, [])

  // Live guides first within each category, coming-soon at the bottom
  const sortedGuides = GUIDES.map(cat => ({
    ...cat,
    guides: [
      ...cat.guides.filter(g => !g.comingSoon),
      ...cat.guides.filter(g =>  g.comingSoon),
    ],
  }))

  const liveCount   = GUIDES.flatMap(c => c.guides).filter(g => !g.comingSoon).length
  const comingCount = GUIDES.flatMap(c => c.guides).filter(g =>  g.comingSoon).length

  return (
    <div className="max-w-5xl mx-auto space-y-10 pb-8 px-4 sm:px-6 lg:px-0">

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-6 sm:p-8 text-white">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-3">
          <BookOpen className="w-4 h-4 shrink-0" />
          Free guides · Curated courses · Practical strategies
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold mb-3">ASX Investing Education Hub</h1>
        <p className="text-slate-300 max-w-2xl text-base sm:text-lg leading-relaxed">
          Everything you need to become a more confident ASX investor — from screening basics to advanced fundamental analysis.
        </p>
        <div className="mt-5 flex flex-wrap gap-4 text-sm text-slate-400">
          <span className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            {liveCount} guides live
          </span>
          <span className="flex items-center gap-1.5">
            <Lock className="w-3.5 h-3.5 text-slate-500 shrink-0" />
            {comingCount} coming soon
          </span>
          <span className="flex items-center gap-1.5">
            <Play className="w-3.5 h-3.5 text-rose-400 shrink-0" />
            {COURSES.length} curated courses
          </span>
        </div>
      </div>

      {/* ── Beginner pathway ──────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center bg-emerald-50 text-emerald-700 shrink-0">
            <Zap className="w-4 h-4" />
          </div>
          <h2 className="text-lg font-semibold text-slate-800">New to ASX investing? Start here</h2>
        </div>
        <div className="bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-200 rounded-2xl p-4 sm:p-6">
          {/* 2 cols on mobile → 3 on tablet → 6 on desktop */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {BEGINNER_STEPS.map(({ n, title, desc, href, icon: Icon }) => (
              <Link
                key={n}
                href={href}
                onClick={() => trackEvent('guide_opened', { title, source: 'beginner_path', step: n })}
                className="group bg-white rounded-xl border border-emerald-100 hover:border-emerald-300 p-3 sm:p-4 flex flex-col items-start transition-all hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="w-5 h-5 rounded-full bg-emerald-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0">
                    {n}
                  </span>
                  <Icon className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                </div>
                <p className="text-xs font-semibold text-slate-800 leading-snug mb-1">{title}</p>
                <p className="text-[11px] text-slate-500 leading-snug">{desc}</p>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* ── Guide categories ──────────────────────────────────────────────── */}
      {sortedGuides.map(({ category, icon: Icon, color, guides }) => (
        <section key={category} id={category.toLowerCase().replace(/\s+/g, '-')}>
          <div className="flex items-center gap-2 mb-4">
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${CATEGORY_BG[color]}`}>
              <Icon className="w-4 h-4" />
            </div>
            <h2 className="text-lg font-semibold text-slate-800">{category}</h2>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {guides.map(guide => (
              <GuideCard
                key={guide.title}
                guide={guide}
                color={color}
                notified={notified}
                onNotify={handleNotify}
              />
            ))}
          </div>
        </section>
      ))}

      {/* ── Recommended courses ───────────────────────────────────────────── */}
      <section>
        {/* Section header */}
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
            <Play className="w-4 h-4 text-rose-500 shrink-0" />
            Recommended Courses
          </h2>
          <span className="text-xs text-slate-500 bg-amber-50 border border-amber-200 rounded px-2 py-1 whitespace-nowrap">
            Affiliate links — we may earn a commission
          </span>
        </div>

        {/* Price / rating disclaimer */}
        <p className="text-xs text-slate-400 mb-4 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 leading-relaxed">
          Prices, ratings, and student numbers are approximate and may change. Please confirm current details on the
          provider&apos;s website before purchasing.
        </p>

        <div className="grid sm:grid-cols-2 gap-4">
          {COURSES.map(course => (
            <div
              key={course.title}
              className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col hover:shadow-sm transition-shadow"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                    {course.provider}
                  </span>
                  {course.tag && (
                    <span className="ml-2 text-[10px] font-bold bg-rose-100 text-rose-700 px-1.5 py-0.5 rounded">
                      {course.tag}
                    </span>
                  )}
                </div>
                <span className="text-sm font-bold text-slate-800 whitespace-nowrap ml-2">{course.price}</span>
              </div>

              <h3 className="font-semibold text-slate-900 mb-2">{course.title}</h3>
              <p className="text-sm text-slate-500 flex-1 leading-relaxed">{course.description}</p>

              <div className="mt-3 flex items-center justify-between gap-3">
                <div className="flex flex-col gap-0.5 min-w-0">
                  <StarRating rating={course.rating} />
                  <span className="text-xs text-slate-400 truncate">{course.students} students (approx.)</span>
                </div>
                {/* External course link — new tab, full rel attributes, click tracking */}
                <a
                  href={course.affiliateUrl}
                  target="_blank"
                  rel="noopener noreferrer sponsored"
                  onClick={() => trackEvent('affiliate_course_clicked', { title: course.title, provider: course.provider })}
                  className="flex items-center gap-1.5 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded-lg transition-colors shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
                  aria-label={`View ${course.title} on ${course.provider} (opens in new tab)`}
                >
                  View course <ExternalLink className="w-3 h-3 shrink-0" />
                </a>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ────────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl p-6 sm:p-7 text-center">
        <h2 className="text-lg sm:text-xl font-bold text-slate-900 mb-2">
          Ready to put your knowledge to work?
        </h2>
        <p className="text-slate-600 mb-5 max-w-lg mx-auto text-sm sm:text-base">
          Use the ASX Screener to find stocks matching your investment criteria — dividend yield, P/E ratio, sector, and more.
        </p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link
            href="/screener"
            onClick={() => trackEvent('screen_strategy_clicked', { source: 'learn_cta' })}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold px-5 py-2.5 rounded-xl transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
          >
            <BarChart2 className="w-4 h-4 shrink-0" />
            Open the Screener
          </Link>
          <Link
            href="/brokers"
            onClick={() => trackEvent('broker_compare_clicked', { source: 'learn_cta' })}
            className="flex items-center gap-2 bg-white hover:bg-slate-50 text-slate-700 font-semibold px-5 py-2.5 rounded-xl border border-slate-200 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
          >
            <DollarSign className="w-4 h-4 shrink-0" />
            Compare Brokers
          </Link>
        </div>
      </div>

    </div>
  )
}
