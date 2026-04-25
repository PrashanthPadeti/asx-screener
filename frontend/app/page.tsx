import Link from 'next/link'
import { BarChart2, Search, TrendingUp, Star, Zap, Shield } from 'lucide-react'

const FEATURES = [
  {
    icon: BarChart2,
    title: 'Powerful Screener',
    desc: 'Filter 1,978 ASX stocks by price, sector, PE ratio, ROE, dividend yield, franking credits, and 40+ more metrics.',
  },
  {
    icon: TrendingUp,
    title: 'Franking Credit Yield',
    desc: 'Unique to Australia — see grossed-up dividend yields with full franking credit calculations for every stock.',
  },
  {
    icon: Shield,
    title: 'Mining & REIT Depth',
    desc: 'AISC, reserve life, NTA per unit, WALE, and occupancy — metrics built specifically for ASX miners and A-REITs.',
  },
  {
    icon: Zap,
    title: 'AI Insights',
    desc: 'Ask questions about any stock in plain English. Powered by Claude AI with access to annual reports and earnings calls.',
  },
  {
    icon: Star,
    title: 'Watchlists & Alerts',
    desc: 'Track your favourite stocks and get alerted when they hit your target price or match your screen criteria.',
  },
  {
    icon: Search,
    title: 'ASIC Short Data',
    desc: 'Live ASIC short-selling positions updated daily — see which stocks are most heavily shorted on the ASX.',
  },
]

const QUICK_SCREENS = [
  { label: 'High Franking Yield',    href: '/screener?preset=high_franking',    color: 'bg-green-50 text-green-700 border-green-200' },
  { label: 'ASX200 Value Stocks',    href: '/screener?preset=asx200_value',     color: 'bg-blue-50 text-blue-700 border-blue-200' },
  { label: 'High Piotroski Score',   href: '/screener?preset=piotroski',        color: 'bg-purple-50 text-purple-700 border-purple-200' },
  { label: 'Materials > $1',         href: '/screener?preset=materials',        color: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
  { label: 'Low Debt, High ROE',     href: '/screener?preset=quality',          color: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
  { label: 'A-REITs',                href: '/screener?preset=reits',            color: 'bg-pink-50 text-pink-700 border-pink-200' },
]

export default function HomePage() {
  return (
    <div className="space-y-12">

      {/* Hero */}
      <section className="text-center py-12 px-4">
        <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 text-sm font-medium px-3 py-1 rounded-full mb-4">
          <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
          1,839 stocks · 870K+ price rows · Live data
        </div>
        <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
          ASX Stock Screener
        </h1>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto mb-8">
          The most comprehensive ASX screener — franking credits, mining metrics,
          A-REIT depth, and AI insights. Built for Australian investors.
        </p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link
            href="/screener"
            className="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg
                       hover:bg-blue-700 transition-colors shadow-sm"
          >
            Open Screener
          </Link>
          <Link
            href="/company/BHP"
            className="px-6 py-3 bg-white text-gray-700 font-semibold rounded-lg
                       border border-gray-300 hover:bg-gray-50 transition-colors"
          >
            View BHP Example →
          </Link>
        </div>
      </section>

      {/* Quick screens */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Quick Screens</h2>
        <div className="flex flex-wrap gap-2">
          {QUICK_SCREENS.map(s => (
            <Link
              key={s.label}
              href={s.href}
              className={`px-4 py-2 rounded-lg border text-sm font-medium transition-all
                          hover:shadow-sm ${s.color}`}
            >
              {s.label}
            </Link>
          ))}
        </div>
      </section>

      {/* Features */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Everything you need</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map(f => (
            <div key={f.title} className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow">
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 bg-blue-50 rounded-lg">
                  <f.icon className="w-5 h-5 text-blue-600" />
                </div>
                <h3 className="font-semibold text-gray-900">{f.title}</h3>
              </div>
              <p className="text-sm text-gray-600 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Stats bar */}
      <section className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          {[
            { val: '1,978', label: 'ASX Listed Companies' },
            { val: '870K+', label: 'Price Data Points' },
            { val: '40+',   label: 'Screener Metrics' },
            { val: '2 Yrs', label: 'Historical Data' },
          ].map(s => (
            <div key={s.label}>
              <div className="text-2xl font-bold text-blue-600">{s.val}</div>
              <div className="text-sm text-gray-500 mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

    </div>
  )
}
