'use client'
import { useState } from 'react'
import { ExternalLink, Check, X, Minus, Shield, Zap, DollarSign, Globe, Star, Users, BookOpen, TrendingUp, BarChart2, Info } from 'lucide-react'
import { PlanGate } from '@/components/PlanGate'

// ── Types ────────────────────────────────────────────────────────────────────

type Research   = 'basic' | 'good' | 'excellent'
type FilterKey  = 'chess' | 'zero_brokerage' | 'international' | 'etf' | 'beginner' | 'research' | 'no_platform_fee'

interface Broker {
  name: string
  logo: string
  tagline: string
  brokerage: string
  platformFee: string
  minDeposit: string
  chess: boolean | null   // null = partial / unclear
  international: boolean
  fractional: boolean
  research: Research
  bestFor: string
  pros: string[]
  cons: string[]
  promoText?: string
  affiliateUrl: string
  highlight?: boolean
  // filter helpers
  zeroBrokerage: boolean
  etfFriendly:   boolean
  beginnerFriendly: boolean
}

// ── Broker data ───────────────────────────────────────────────────────────────

const BROKERS: Broker[] = [
  {
    name: 'CommSec',
    logo: 'CS',
    tagline: "Australia's largest online broker",
    brokerage: '$10 – $19.95',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: true, international: true, fractional: false, research: 'excellent',
    bestFor: 'Full-service investing with deep research',
    pros: ['Deep research & analysis tools', 'CHESS-sponsored', 'Strong brand & customer support'],
    cons: ['Higher brokerage ($10–$19.95)', 'No fractional shares'],
    affiliateUrl: 'https://www.commsec.com.au',
    zeroBrokerage: false, etfFriendly: false, beginnerFriendly: true,
  },
  {
    name: 'SelfWealth',
    logo: 'SW',
    tagline: 'Flat $9.50 brokerage, always',
    brokerage: '$9.50 flat',
    platformFee: 'Free (Premium $20/mo)',
    minDeposit: '$0',
    chess: true, international: true, fractional: false, research: 'good',
    bestFor: 'Cost-conscious investors who buy regularly',
    pros: ['Flat $9.50 regardless of trade size', 'CHESS-sponsored', 'Community peer benchmarking'],
    cons: ['No fractional shares', 'Premium features require $20/mo plan'],
    promoText: 'Get 5 free trades for new accounts',
    affiliateUrl: 'https://www.selfwealth.com.au',
    highlight: true,
    zeroBrokerage: false, etfFriendly: false, beginnerFriendly: false,
  },
  {
    name: 'Superhero',
    logo: 'SH',
    tagline: 'Simple investing from $5',
    brokerage: '$5 ASX · $0 US',
    platformFee: 'Free',
    minDeposit: '$100',
    chess: false, international: true, fractional: true, research: 'basic',
    bestFor: 'Beginners and US stock investors',
    pros: ['Low $5 ASX brokerage', '$0 US trades', 'Zero brokerage on ETF purchases'],
    cons: ['Custodial (not CHESS-sponsored)', 'Limited research & charting'],
    promoText: 'No brokerage on ETF purchases',
    affiliateUrl: 'https://www.superhero.com.au',
    zeroBrokerage: true, etfFriendly: true, beginnerFriendly: true,
  },
  {
    name: 'Pearler',
    logo: 'PL',
    tagline: 'Built for long-term investors',
    brokerage: '$6.50',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: true, international: true, fractional: false, research: 'basic',
    bestFor: 'Passive investors and ETF accumulators',
    pros: ['Auto-invest scheduling', 'CHESS-sponsored', 'Built for set-and-forget investing'],
    cons: ['No fractional shares', 'Limited charting & analysis tools'],
    promoText: 'Auto-invest on a schedule',
    affiliateUrl: 'https://www.pearler.com',
    zeroBrokerage: false, etfFriendly: true, beginnerFriendly: true,
  },
  {
    name: 'CMC Invest',
    logo: 'CMC',
    tagline: 'Zero brokerage on small trades',
    brokerage: '$0 (under $1k) · $11+',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: true, international: false, fractional: false, research: 'good',
    bestFor: 'Active traders who want low costs on smaller trades',
    pros: ['$0 brokerage on trades under $1,000', 'CHESS-sponsored', 'Good research tools'],
    cons: ['Brokerage rises on larger trades', 'No international shares access'],
    affiliateUrl: 'https://www.cmcinvest.com.au',
    zeroBrokerage: true, etfFriendly: true, beginnerFriendly: false,
  },
  {
    name: 'nabtrade',
    logo: 'NT',
    tagline: 'Premium research for serious investors',
    brokerage: '$14.95 – $19.95',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: true, international: true, fractional: false, research: 'excellent',
    bestFor: 'NAB customers seeking premium research & ASX depth',
    pros: ['Excellent research & data', 'CHESS-sponsored', 'Deep ASX market data'],
    cons: ['Higher brokerage ($14.95–$19.95)', 'No fractional shares'],
    affiliateUrl: 'https://www.nabtrade.com.au',
    zeroBrokerage: false, etfFriendly: false, beginnerFriendly: false,
  },
  {
    name: 'Stake',
    logo: 'SK',
    tagline: 'Modern investing — ASX & US',
    brokerage: '$3 AUS · $0 US',
    platformFee: 'Free (Stake Black $9/mo)',
    minDeposit: '$0',
    chess: false, international: true, fractional: true, research: 'basic',
    bestFor: 'Investors who want both ASX and US share exposure',
    pros: ['Low $3 ASX brokerage', '$0 US trades & fractional shares', 'Clean modern interface'],
    cons: ['Custodial (not CHESS-sponsored)', 'Basic research tools'],
    affiliateUrl: 'https://www.stake.com.au',
    zeroBrokerage: true, etfFriendly: false, beginnerFriendly: true,
  },
  {
    name: 'moomoo',
    logo: 'MM',
    tagline: 'Advanced tools, low fees',
    brokerage: '$0.99 – $3.99',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: false, international: true, fractional: false, research: 'good',
    bestFor: 'Active traders who want advanced charting',
    pros: ['Very low brokerage from $0.99', 'Advanced charting & Level 2 data', 'International markets access'],
    cons: ['Custodial (not CHESS-sponsored)', 'Can feel complex for beginners'],
    promoText: 'Up to 180 days free brokerage for new users',
    affiliateUrl: 'https://www.moomoo.com/au',
    highlight: true,
    zeroBrokerage: false, etfFriendly: false, beginnerFriendly: false,
  },
]

// ── Filter config ─────────────────────────────────────────────────────────────

const FILTERS: { key: FilterKey; label: string; icon: React.ElementType }[] = [
  { key: 'chess',           label: 'CHESS-sponsored',  icon: Shield     },
  { key: 'zero_brokerage',  label: '$0 brokerage',     icon: DollarSign },
  { key: 'international',   label: 'US shares',        icon: Globe      },
  { key: 'etf',             label: 'Best for ETFs',    icon: TrendingUp },
  { key: 'beginner',        label: 'Beginner-friendly',icon: Users      },
  { key: 'research',        label: 'Best for research',icon: BookOpen   },
  { key: 'no_platform_fee', label: 'No platform fee',  icon: Zap        },
]

function matchesFilters(broker: Broker, active: Set<FilterKey>): boolean {
  if (active.size === 0) return true
  if (active.has('chess')           && broker.chess !== true)             return false
  if (active.has('zero_brokerage')  && !broker.zeroBrokerage)             return false
  if (active.has('international')   && !broker.international)             return false
  if (active.has('etf')             && !broker.etfFriendly)               return false
  if (active.has('beginner')        && !broker.beginnerFriendly)          return false
  if (active.has('research')        && broker.research !== 'excellent')   return false
  if (active.has('no_platform_fee') && broker.platformFee !== 'Free')     return false
  return true
}

// ── Style maps ────────────────────────────────────────────────────────────────

const RESEARCH_LABEL: Record<Research, { label: string; cls: string }> = {
  basic:     { label: 'Basic',     cls: 'bg-slate-100 text-slate-600'   },
  good:      { label: 'Good',      cls: 'bg-blue-100 text-blue-700'     },
  excellent: { label: 'Excellent', cls: 'bg-emerald-100 text-emerald-700'},
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TrileanIcon({ value }: { value: boolean | null }) {
  if (value === true)  return <Check className="w-4 h-4 text-emerald-500 mx-auto" />
  if (value === false) return <X     className="w-4 h-4 text-red-400    mx-auto" />
  return <Minus className="w-4 h-4 text-slate-300 mx-auto" />
}

function BrokerCard({ broker }: { broker: Broker }) {
  return (
    <div className={`bg-white rounded-2xl border flex flex-col ${broker.highlight ? 'border-blue-200 shadow-sm' : 'border-slate-200'} p-5`}>
      {/* Header */}
      <div className="flex items-start gap-3 mb-3">
        <div className="w-10 h-10 rounded-xl bg-blue-600 text-white font-bold text-xs flex items-center justify-center shrink-0">
          {broker.logo}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-bold text-slate-900 text-sm">{broker.name}</h3>
            {broker.highlight && (
              <span className="text-[10px] font-bold bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full">Featured</span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 leading-snug">{broker.tagline}</p>
        </div>
      </div>

      {/* Best for */}
      <div className="text-xs bg-slate-50 rounded-lg px-2.5 py-1.5 mb-3">
        <span className="font-semibold text-slate-600">Best for: </span>
        <span className="text-slate-600">{broker.bestFor}</span>
      </div>

      {/* Key stats */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="text-center bg-slate-50 rounded-lg p-2">
          <div className="text-xs font-bold text-slate-800 leading-snug">{broker.brokerage}</div>
          <div className="text-[10px] text-slate-400 mt-0.5">Brokerage</div>
        </div>
        <div className="text-center bg-slate-50 rounded-lg p-2">
          <div className={`text-xs font-bold leading-snug ${broker.chess === true ? 'text-emerald-700' : 'text-amber-600'}`}>
            {broker.chess === true ? 'CHESS' : 'Custodial'}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">Holding type</div>
        </div>
      </div>

      {/* Pros */}
      <div className="space-y-1 mb-2 flex-1">
        {broker.pros.map(pro => (
          <div key={pro} className="flex items-start gap-1.5 text-xs text-slate-600">
            <Check className="w-3 h-3 text-emerald-500 shrink-0 mt-0.5" />
            {pro}
          </div>
        ))}
      </div>

      {/* Cons */}
      <div className="space-y-1 mb-4">
        {broker.cons.map(con => (
          <div key={con} className="flex items-start gap-1.5 text-xs text-slate-400">
            <X className="w-3 h-3 text-red-300 shrink-0 mt-0.5" />
            {con}
          </div>
        ))}
      </div>

      {/* Promo */}
      {broker.promoText && (
        <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-2.5 py-1.5 mb-3">
          🎁 {broker.promoText}
        </p>
      )}

      {/* CTA */}
      <a
        href={broker.affiliateUrl}
        target="_blank"
        rel="noopener noreferrer sponsored"
        className="flex items-center justify-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold py-2 rounded-xl transition-colors"
        aria-label={`Open account with ${broker.name} (opens in new tab)`}
      >
        Open account <ExternalLink className="w-3.5 h-3.5 shrink-0" />
      </a>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function BrokersPage() {
  const [activeFilters, setActiveFilters] = useState<Set<FilterKey>>(new Set())

  function toggleFilter(key: FilterKey) {
    setActiveFilters(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const filtered = BROKERS.filter(b => matchesFilters(b, activeFilters))

  return (
    <PlanGate required="pro" feature="Broker Compare">
    <div className="max-w-6xl mx-auto space-y-10 pb-10 px-4 sm:px-6 lg:px-0">

      {/* ── 1. Hero ──────────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-2xl p-6 sm:p-8 text-white">
        <div className="flex items-center gap-2 text-blue-200 text-sm mb-3">
          <Shield className="w-4 h-4 shrink-0" />
          Independent comparison · Fees last reviewed: May 2026
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold mb-3">Best ASX Brokers in Australia</h1>
        <p className="text-blue-100 max-w-2xl text-base sm:text-lg leading-relaxed">
          Compare Australia&apos;s top share trading platforms on fees, features, and CHESS sponsorship.
          Find the right broker for your investing style.
        </p>
        <div className="mt-5 flex flex-wrap gap-2 sm:gap-3 text-sm">
          <span className="flex items-center gap-1.5 bg-blue-700/60 rounded-full px-3 py-1 text-xs sm:text-sm">
            <DollarSign className="w-3.5 h-3.5 shrink-0" /> Low-cost options from $0/trade
          </span>
          <span className="flex items-center gap-1.5 bg-blue-700/60 rounded-full px-3 py-1 text-xs sm:text-sm">
            <Shield className="w-3.5 h-3.5 shrink-0" /> CHESS-sponsored options
          </span>
          <span className="flex items-center gap-1.5 bg-blue-700/60 rounded-full px-3 py-1 text-xs sm:text-sm">
            <Globe className="w-3.5 h-3.5 shrink-0" /> International market access
          </span>
        </div>
      </div>

      {/* ── 2. Affiliate disclosure ───────────────────────────────────────── */}
      <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-xs text-slate-600 leading-relaxed">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p>
          <strong>Affiliate disclosure:</strong> Some links on this page are affiliate links. We may receive a commission if you open an account through our link, at no extra cost to you.{' '}
          <strong>This does not affect our comparison order or editorial opinion.</strong>{' '}
          Fees and features change regularly — always verify current details with the broker before opening an account. This is not financial advice.
        </p>
      </div>

      {/* ── 3. Editor's Picks ────────────────────────────────────────────── */}
      <div>
        <h2 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
          <Star className="w-4 h-4 text-amber-500 shrink-0" />
          Editor&apos;s Picks
        </h2>
        <div className="grid sm:grid-cols-2 gap-4">
          {BROKERS.filter(b => b.highlight).map(broker => (
            <div key={broker.name} className="bg-white border-2 border-blue-200 rounded-2xl p-6 relative overflow-hidden">
              <div className="absolute top-3 right-3 text-[10px] font-bold bg-blue-600 text-white px-2 py-0.5 rounded-full">
                FEATURED
              </div>
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-blue-600 text-white font-bold text-sm flex items-center justify-center shrink-0">
                  {broker.logo}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-slate-900">{broker.name}</h3>
                  <p className="text-sm text-slate-500">{broker.tagline}</p>
                  {broker.promoText && (
                    <p className="text-xs text-emerald-700 bg-emerald-50 rounded px-2 py-0.5 mt-1.5 inline-block">
                      🎁 {broker.promoText}
                    </p>
                  )}
                </div>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3 text-center text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-bold text-slate-800 leading-snug">{broker.brokerage}</div>
                  <div className="text-slate-500 mt-0.5">Brokerage</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className={`font-bold leading-snug ${broker.chess === true ? 'text-emerald-700' : 'text-amber-600'}`}>
                    {broker.chess === true ? 'CHESS' : 'Custodial'}
                  </div>
                  <div className="text-slate-500 mt-0.5">Holding</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <span className={`text-xs font-semibold px-1.5 py-0.5 rounded inline-block ${RESEARCH_LABEL[broker.research].cls}`}>
                    {RESEARCH_LABEL[broker.research].label}
                  </span>
                  <div className="text-slate-500 mt-1">Research</div>
                </div>
              </div>
              <a
                href={broker.affiliateUrl}
                target="_blank"
                rel="noopener noreferrer sponsored"
                className="mt-4 w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold py-2.5 rounded-xl transition-colors"
                aria-label={`Open account with ${broker.name} (opens in new tab)`}
              >
                Open account <ExternalLink className="w-3.5 h-3.5 shrink-0" />
              </a>
            </div>
          ))}
        </div>
      </div>

      {/* ── 4. Quick filters ─────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <BarChart2 className="w-4 h-4 text-slate-500 shrink-0" />
          <h2 className="text-lg font-semibold text-slate-800">All Brokers</h2>
          {activeFilters.size > 0 && (
            <span className="text-xs text-slate-500 bg-slate-100 rounded-full px-2 py-0.5">
              {filtered.length} of {BROKERS.length} shown
            </span>
          )}
        </div>

        {/* Filter chips */}
        <div className="flex flex-wrap gap-2 mb-5">
          {FILTERS.map(({ key, label, icon: Icon }) => {
            const active = activeFilters.has(key)
            return (
              <button
                key={key}
                type="button"
                onClick={() => toggleFilter(key)}
                className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full border transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${
                  active
                    ? 'bg-blue-600 border-blue-600 text-white shadow-sm'
                    : 'bg-white border-slate-200 text-slate-600 hover:border-blue-300 hover:text-blue-700'
                }`}
                aria-pressed={active}
              >
                <Icon className="w-3 h-3 shrink-0" />
                {label}
              </button>
            )
          })}
          {activeFilters.size > 0 && (
            <button
              type="button"
              onClick={() => setActiveFilters(new Set())}
              className="text-xs text-slate-400 hover:text-slate-600 px-2 py-1.5 underline underline-offset-2 transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Broker cards grid */}
        {filtered.length === 0 ? (
          <div className="bg-slate-50 border border-slate-200 rounded-2xl p-10 text-center text-slate-400 text-sm">
            No brokers match all selected filters. Try removing one.
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map(broker => (
              <BrokerCard key={broker.name} broker={broker} />
            ))}
          </div>
        )}
      </div>

      {/* ── 5. Full comparison table ─────────────────────────────────────── */}
      <div>
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Full Comparison Table</h2>
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="text-left px-4 py-3 font-semibold text-slate-700 w-36 whitespace-nowrap">Broker</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700 whitespace-nowrap">Brokerage</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700 whitespace-nowrap">Platform fee</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700 whitespace-nowrap">Min. deposit</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">CHESS</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">Intl.</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">Fractional</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">Research</th>
                  <th className="text-left px-3 py-3 font-semibold text-slate-700 whitespace-nowrap">Best for</th>
                  <th className="px-3 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {BROKERS.map(broker => {
                  const inFilter = matchesFilters(broker, activeFilters)
                  return (
                    <tr
                      key={broker.name}
                      className={`transition-colors ${
                        !inFilter && activeFilters.size > 0
                          ? 'opacity-30'
                          : broker.highlight
                          ? 'bg-blue-50/40 hover:bg-blue-50'
                          : 'hover:bg-slate-50'
                      }`}
                    >
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-lg bg-blue-600 text-white font-bold text-[10px] flex items-center justify-center shrink-0">
                            {broker.logo}
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900 text-xs whitespace-nowrap">{broker.name}</div>
                            {broker.promoText && (
                              <div className="text-[10px] text-emerald-700 mt-0.5 leading-snug max-w-[110px]">{broker.promoText}</div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-3.5 text-center font-medium text-slate-800 text-xs whitespace-nowrap">{broker.brokerage}</td>
                      <td className="px-3 py-3.5 text-center text-slate-600 text-xs">{broker.platformFee}</td>
                      <td className="px-3 py-3.5 text-center text-slate-600 text-xs">{broker.minDeposit}</td>
                      <td className="px-3 py-3.5 text-center"><TrileanIcon value={broker.chess} /></td>
                      <td className="px-3 py-3.5 text-center"><TrileanIcon value={broker.international} /></td>
                      <td className="px-3 py-3.5 text-center"><TrileanIcon value={broker.fractional} /></td>
                      <td className="px-3 py-3.5 text-center">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${RESEARCH_LABEL[broker.research].cls}`}>
                          {RESEARCH_LABEL[broker.research].label}
                        </span>
                      </td>
                      <td className="px-3 py-3.5 text-slate-500 text-xs max-w-[140px] leading-snug">{broker.bestFor}</td>
                      <td className="px-3 py-3.5">
                        <a
                          href={broker.affiliateUrl}
                          target="_blank"
                          rel="noopener noreferrer sponsored"
                          className="flex items-center gap-1 text-blue-600 hover:text-blue-800 font-medium whitespace-nowrap text-xs"
                          aria-label={`Open account with ${broker.name}`}
                        >
                          Open <ExternalLink className="w-3 h-3 shrink-0" />
                        </a>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
        <p className="text-[11px] text-slate-400 mt-2 px-1">
          Fees are checked regularly. Last reviewed: May 2026. Always verify current fees with the broker before opening an account.
        </p>
      </div>

      {/* ── 6. CHESS vs Custodial ────────────────────────────────────────── */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <h3 className="font-bold text-slate-900 mb-3 flex items-center gap-2">
            <Shield className="w-5 h-5 text-blue-600 shrink-0" />
            CHESS vs Custodial — what&apos;s the difference?
          </h3>
          <p className="text-sm text-slate-600 leading-relaxed mb-3">
            <strong>CHESS-sponsored</strong> brokers register shares directly in your name on the ASX CHESS subregister. You hold a Holder Identification Number (HIN) and are the legal owner of the shares.
          </p>
          <p className="text-sm text-slate-600 leading-relaxed mb-3">
            <strong>Custodial</strong> brokers hold shares through a nominee/custody structure on your behalf. Generally cheaper to operate, but recovery processes may differ if a broker fails.
          </p>
          <p className="text-xs text-slate-400 bg-slate-50 rounded-lg p-2.5 leading-relaxed">
            Cash protections depend on where funds are held. Investors should review each broker&apos;s terms and seek independent advice if unsure about the custody arrangements.
          </p>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <h3 className="font-bold text-slate-900 mb-3 flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-500 shrink-0" />
            How to choose the right broker
          </h3>
          <ul className="space-y-2.5 text-sm text-slate-600">
            {[
              'Consider how often you trade — flat fees suit frequent buyers; percentage-based fees suit large single trades.',
              'If you want international stocks (US, ETFs), check international access carefully.',
              'Long-term buy-and-hold? Prioritise CHESS sponsorship and low or no platform fees.',
              'Need research and analysis tools? CommSec and nabtrade lead on this.',
              'New to investing? Look for a clean app, good support, and low minimum deposit.',
            ].map((tip, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-blue-600 font-bold shrink-0">{i + 1}.</span>
                {tip}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ── 7. How we rank ───────────────────────────────────────────────── */}
      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-base font-bold text-slate-900 mb-3 flex items-center gap-2">
          <BarChart2 className="w-5 h-5 text-blue-600 shrink-0" />
          How we compare brokers
        </h2>
        <p className="text-sm text-slate-700 leading-relaxed mb-4">
          We compare brokers based on the factors that matter most to Australian investors:
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          {[
            { label: 'Brokerage fees',       desc: 'Per-trade cost on ASX and international markets' },
            { label: 'CHESS sponsorship',     desc: 'Whether shares are registered in your name on ASX' },
            { label: 'Platform fees',         desc: 'Monthly or annual account-keeping charges' },
            { label: 'Research tools',        desc: 'Quality of in-platform data, news, and analysis' },
            { label: 'International access',  desc: 'Ability to trade US and global markets' },
            { label: 'Beginner-friendliness', desc: 'App quality, minimum deposit, onboarding experience' },
            { label: 'ETF support',           desc: 'ETF-specific features like auto-invest and zero brokerage' },
            { label: 'Overall value',         desc: 'Total cost and features relative to the investor type' },
          ].map(({ label, desc }) => (
            <div key={label} className="bg-white rounded-xl border border-blue-100 p-3">
              <p className="text-xs font-semibold text-slate-800 mb-0.5">{label}</p>
              <p className="text-[11px] text-slate-500 leading-snug">{desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 leading-relaxed">
          <strong>Independence note:</strong> Affiliate partnerships do not control our rankings or editorial opinion. Featured brokers reflect promotional arrangements, clearly labelled as such.
        </p>
      </div>

      {/* ── 8. FAQ ───────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-5">Frequently Asked Questions</h2>
        <div className="space-y-5">
          {[
            {
              q: 'Is my money safe if an Australian broker collapses?',
              a: 'CHESS-sponsored brokers register shares in your name on the ASX CHESS subregister, so those holdings are generally not part of the broker\'s estate if it fails. Custodial brokers hold assets through a nominee/custody structure — recovery processes may differ in the event of insolvency. Cash protections depend on where the cash is held, so investors should review each broker\'s terms. We recommend seeking independent financial or legal advice if you have specific concerns about broker solvency arrangements.',
            },
            {
              q: 'Do I need to pay tax on share trading in Australia?',
              a: 'Yes. Capital gains and dividends are taxable in Australia. Shares held for 12+ months qualify for the 50% CGT discount. Fully-franked dividends come with franking credits that can offset your tax. We recommend speaking with a registered tax agent or accountant. ASX Screener helps you track portfolio cost basis and dividend income for record-keeping.',
            },
            {
              q: 'Which broker is best for ETF investing?',
              a: 'Pearler and Superhero are popular for passive ETF investing — Superhero offers zero brokerage on certain ETF purchases and Pearler has an auto-invest feature. CMC Invest also offers zero brokerage on trades under $1,000. Use the ETF filter above to see brokers best suited to this strategy.',
            },
            {
              q: 'Can I use multiple brokers?',
              a: 'Yes. Many investors use a low-cost broker like SelfWealth or CMC Invest for regular purchases, and CommSec or nabtrade for research tools. There is no restriction on holding multiple brokerage accounts in Australia.',
            },
            {
              q: 'What is the difference between brokerage and a platform fee?',
              a: 'Brokerage is a per-trade cost you pay each time you buy or sell shares. A platform fee (sometimes called an account-keeping fee) is charged periodically — monthly or annually — just for having an account. Most modern discount brokers have eliminated platform fees, but some charge them for premium features or research access.',
            },
          ].map(({ q, a }) => (
            <div key={q} className="border-b border-slate-100 pb-5 last:border-0 last:pb-0">
              <div className="font-semibold text-slate-800 mb-1.5 text-sm">{q}</div>
              <div className="text-sm text-slate-600 leading-relaxed">{a}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Disclaimer footer ────────────────────────────────────────────── */}
      <p className="text-xs text-slate-400 leading-relaxed pb-2">
        <strong>Disclaimer:</strong> The information on this page is for general informational and educational purposes only. It does not constitute financial advice or a recommendation to open any brokerage account. Brokerage fees, features, and promotional offers change regularly — please verify all details directly with the broker. ASX Screener may receive affiliate commissions from linked brokers at no cost to you. This does not influence our comparison methodology or editorial independence.
      </p>

    </div>
    </PlanGate>
  )
}
