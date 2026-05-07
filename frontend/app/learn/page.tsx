'use client'
import Link from 'next/link'
import { ExternalLink, BookOpen, TrendingUp, PieChart, DollarSign, BarChart2, Zap, ChevronRight, Play } from 'lucide-react'
import { PlanGate } from '@/components/PlanGate'

interface Guide {
  title: string
  description: string
  readTime: string
  level: 'Beginner' | 'Intermediate' | 'Advanced'
  href: string
  internal?: boolean
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

const GUIDES: { category: string; icon: React.ElementType; color: string; guides: Guide[] }[] = [
  {
    category: 'Getting Started',
    icon: BookOpen,
    color: 'blue',
    guides: [
      {
        title: 'How to Use the ASX Screener',
        description: 'Learn how to filter ASX stocks by fundamentals, dividends, and sector to build your watchlist faster.',
        readTime: '5 min',
        level: 'Beginner',
        href: '/screener',
        internal: true,
      },
      {
        title: 'Understanding Franking Credits',
        description: 'Australia\'s unique dividend imputation system explained — and how to calculate your grossed-up yield.',
        readTime: '8 min',
        level: 'Beginner',
        href: '#franking-credits',
      },
      {
        title: 'How to Read ASX Company Announcements',
        description: 'A guide to understanding the different announcement types on the ASX and what to look for.',
        readTime: '6 min',
        level: 'Beginner',
        href: '#announcements',
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
        readTime: '10 min',
        level: 'Intermediate',
        href: '#ratios',
      },
      {
        title: 'Analysing ASX Mining Stocks',
        description: 'How to read AISC, ore reserves, JORC resources, and interpret mining feasibility studies.',
        readTime: '12 min',
        level: 'Intermediate',
        href: '#mining',
      },
      {
        title: 'How to Value ASX REITs (A-REITs)',
        description: 'FFO, NTA, WALE, cap rates — the key metrics unique to real estate investment trusts on the ASX.',
        readTime: '10 min',
        level: 'Intermediate',
        href: '#reits',
      },
    ],
  },
  {
    category: 'Portfolio & Dividends',
    icon: PieChart,
    color: 'emerald',
    guides: [
      {
        title: 'Building a Dividend Portfolio on the ASX',
        description: 'How to construct a diversified income portfolio using the ASX\'s high-yield dividend payers.',
        readTime: '15 min',
        level: 'Intermediate',
        href: '#dividend-portfolio',
      },
      {
        title: 'Understanding the ASX Dividend Calendar',
        description: 'Ex-dividend dates, record dates, payment dates — what they mean and how to plan around them.',
        readTime: '7 min',
        level: 'Beginner',
        href: '#dividend-calendar',
      },
      {
        title: 'CGT and Tax Planning for Share Investors',
        description: 'Capital gains tax fundamentals for Australian share investors, the 12-month discount, and tax loss harvesting.',
        readTime: '12 min',
        level: 'Intermediate',
        href: '#cgt',
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
        readTime: '8 min',
        level: 'Intermediate',
        href: '/screener',
        internal: true,
      },
      {
        title: 'Finding Value Stocks on the ASX',
        description: 'A step-by-step value investing screen using P/E, P/B, and debt ratios for the Australian market.',
        readTime: '10 min',
        level: 'Intermediate',
        href: '/screener',
        internal: true,
      },
      {
        title: 'Growth Stock Screening for ASX',
        description: 'Revenue growth, earnings momentum, and quality factors to filter for ASX growth companies.',
        readTime: '9 min',
        level: 'Advanced',
        href: '/screener',
        internal: true,
      },
    ],
  },
]

const COURSES: Course[] = [
  {
    title: 'ASX Share Market for Beginners',
    provider: 'Udemy',
    description: 'A comprehensive introduction to investing on the ASX — from opening a brokerage account to analysing your first stock.',
    price: 'from $20',
    rating: 4.6,
    students: '12,000+',
    tag: 'Most Popular',
    affiliateUrl: 'https://www.udemy.com',
  },
  {
    title: 'Dividend Investing Masterclass',
    provider: 'Udemy',
    description: 'Deep dive into building income portfolios, understanding franking credits, and optimising dividend reinvestment.',
    price: 'from $25',
    rating: 4.7,
    students: '8,500+',
    affiliateUrl: 'https://www.udemy.com',
  },
  {
    title: 'Financial Statement Analysis',
    provider: 'Coursera',
    description: 'Understand balance sheets, income statements, and cash flow statements to make better investment decisions.',
    price: 'Free (audit) · $60 certificate',
    rating: 4.8,
    students: '45,000+',
    affiliateUrl: 'https://www.coursera.org',
  },
  {
    title: 'Technical Analysis for Stocks',
    provider: 'Udemy',
    description: 'Chart patterns, RSI, MACD, moving averages — practical technical analysis for ASX and global markets.',
    price: 'from $18',
    rating: 4.5,
    students: '22,000+',
    affiliateUrl: 'https://www.udemy.com',
  },
]

const LEVEL_BADGE = {
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

function StarRating({ rating }: { rating: number }) {
  return (
    <span className="flex items-center gap-0.5">
      {[1,2,3,4,5].map(i => (
        <span key={i} className={`text-xs ${i <= Math.round(rating) ? 'text-amber-400' : 'text-slate-200'}`}>★</span>
      ))}
      <span className="text-xs text-slate-600 ml-1">{rating.toFixed(1)}</span>
    </span>
  )
}

export default function LearnPage() {
  return (
    <PlanGate required="premium" feature="Education Hub">
    <div className="max-w-5xl mx-auto space-y-12 pb-16">

      {/* Hero */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-8 text-white">
        <div className="flex items-center gap-2 text-slate-400 text-sm mb-3">
          <BookOpen className="w-4 h-4" />
          Free guides · Curated courses · Practical strategies
        </div>
        <h1 className="text-3xl font-bold mb-3">ASX Investing Education Hub</h1>
        <p className="text-slate-300 max-w-2xl text-lg">
          Everything you need to become a more confident ASX investor — from screening basics to advanced fundamental analysis.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          {['Beginner', 'Intermediate', 'Advanced'].map(l => (
            <span key={l} className={`text-xs font-medium px-3 py-1 rounded-full ${LEVEL_BADGE[l as keyof typeof LEVEL_BADGE]}`}>
              {l}
            </span>
          ))}
          <span className="text-xs font-medium px-3 py-1 rounded-full bg-slate-700 text-slate-300">
            + External courses
          </span>
        </div>
      </div>

      {/* Quick start */}
      <div className="grid sm:grid-cols-3 gap-4">
        {[
          { icon: Zap, color: 'blue', title: 'New to investing?', desc: 'Start with our beginner guides on the ASX basics and franking credits.', href: '#getting-started' },
          { icon: BarChart2, color: 'purple', title: 'Learn to screen stocks', desc: 'Use our filters to find value, dividend, and growth stocks.', href: '/screener', internal: true },
          { icon: DollarSign, color: 'emerald', title: 'Pick a broker', desc: 'Compare Australia\'s top ASX brokers on fees and features.', href: '/brokers', internal: true },
        ].map(({ icon: Icon, color, title, desc, href, internal }) => (
          <Link
            key={title}
            href={href}
            className={`bg-white rounded-xl border ${color === 'blue' ? 'border-blue-100 hover:border-blue-300' : color === 'purple' ? 'border-purple-100 hover:border-purple-300' : 'border-emerald-100 hover:border-emerald-300'} p-5 transition-colors group`}
          >
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center mb-3 ${CATEGORY_BG[color]}`}>
              <Icon className="w-4 h-4" />
            </div>
            <div className="font-semibold text-slate-900 mb-1 group-hover:text-blue-700 transition-colors">{title}</div>
            <div className="text-sm text-slate-500">{desc}</div>
            <div className="mt-3 flex items-center gap-1 text-xs font-medium text-blue-600">
              {internal ? 'Open tool' : 'Read guide'} <ChevronRight className="w-3 h-3" />
            </div>
          </Link>
        ))}
      </div>

      {/* Guides by category */}
      {GUIDES.map(({ category, icon: Icon, color, guides }) => (
        <div key={category} id={category.toLowerCase().replace(/\s+/g, '-')}>
          <div className="flex items-center gap-2 mb-4">
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${CATEGORY_BG[color]}`}>
              <Icon className="w-4 h-4" />
            </div>
            <h2 className="text-lg font-semibold text-slate-800">{category}</h2>
          </div>
          <div className="grid sm:grid-cols-3 gap-4">
            {guides.map(guide => (
              <div key={guide.title} className={`bg-white rounded-xl border ${CATEGORY_BORDER[color]} p-5 hover:shadow-sm transition-shadow flex flex-col`}>
                <div className="flex items-center justify-between mb-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${LEVEL_BADGE[guide.level]}`}>
                    {guide.level}
                  </span>
                  <span className="text-xs text-slate-400">{guide.readTime} read</span>
                </div>
                <h3 className="font-semibold text-slate-900 mb-2 leading-snug">{guide.title}</h3>
                <p className="text-sm text-slate-500 flex-1 leading-relaxed">{guide.description}</p>
                <div className="mt-4">
                  {guide.internal ? (
                    <Link
                      href={guide.href}
                      className="flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800"
                    >
                      Open tool <ChevronRight className="w-3.5 h-3.5" />
                    </Link>
                  ) : (
                    <span className="flex items-center gap-1.5 text-sm text-slate-400 cursor-default">
                      <BookOpen className="w-3.5 h-3.5" /> Coming soon
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Affiliate courses */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
            <Play className="w-4 h-4 text-rose-500" />
            Recommended Courses
          </h2>
          <span className="text-xs text-slate-400 bg-amber-50 border border-amber-200 rounded px-2 py-1">
            Affiliate links — we may earn a commission
          </span>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          {COURSES.map(course => (
            <div key={course.title} className="bg-white rounded-xl border border-slate-200 p-5 flex flex-col hover:shadow-sm transition-shadow">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">{course.provider}</span>
                  {course.tag && (
                    <span className="ml-2 text-[10px] font-bold bg-rose-100 text-rose-700 px-1.5 py-0.5 rounded">{course.tag}</span>
                  )}
                </div>
                <span className="text-sm font-bold text-slate-800">{course.price}</span>
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">{course.title}</h3>
              <p className="text-sm text-slate-500 flex-1 leading-relaxed">{course.description}</p>
              <div className="mt-3 flex items-center justify-between">
                <div className="flex flex-col gap-0.5">
                  <StarRating rating={course.rating} />
                  <span className="text-xs text-slate-400">{course.students} students</span>
                </div>
                <a
                  href={course.affiliateUrl}
                  target="_blank"
                  rel="noopener noreferrer sponsored"
                  className="flex items-center gap-1.5 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded-lg transition-colors"
                >
                  View course <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* CTA: Screener */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl p-8 text-center">
        <h2 className="text-xl font-bold text-slate-900 mb-2">Ready to put your knowledge to work?</h2>
        <p className="text-slate-600 mb-5 max-w-lg mx-auto">
          Use the ASX Screener to find stocks matching your investment criteria — dividend yield, P/E ratio, sector, and more.
        </p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link
            href="/screener"
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold px-5 py-2.5 rounded-xl transition-colors"
          >
            <BarChart2 className="w-4 h-4" />
            Open the Screener
          </Link>
          <Link
            href="/brokers"
            className="flex items-center gap-2 bg-white hover:bg-slate-50 text-slate-700 font-semibold px-5 py-2.5 rounded-xl border border-slate-200 transition-colors"
          >
            <DollarSign className="w-4 h-4" />
            Compare Brokers
          </Link>
        </div>
      </div>

    </div>
    </PlanGate>
  )
}
