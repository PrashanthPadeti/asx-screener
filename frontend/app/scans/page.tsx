'use client'
import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import {
  Shield, Zap, Award, RotateCcw, DollarSign, Search,
  TrendingUp, TrendingDown, BarChart2, ArrowUp, ArrowDown,
  Star, Activity, Flame, Lock,
  Globe, Users, Play, Code2,
} from 'lucide-react'
import { getScreenerPresets, getCommunityScreens, incrementScreenUse, getMarketSectors, type ScreenerPreset, type SavedScreen } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { HelpDrawer } from '@/components/HelpDrawer'
import { SCANS_SECTIONS } from '@/lib/helpContent'

// ── Icon map ──────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  'shield':        Shield,
  'zap':           Zap,
  'award':         Award,
  'rotate-ccw':    RotateCcw,
  'dollar-sign':   DollarSign,
  'search':        Search,
  'trending-up':   TrendingUp,
  'trending-down': TrendingDown,
  'bar-chart-2':   BarChart2,
  'arrow-up':      ArrowUp,
  'arrow-down':    ArrowDown,
  'star':          Star,
  'activity':      Activity,
  'flame':         Flame,
}

function presetTier(p: ScreenerPreset): 'free' | 'pro' | 'premium' {
  if (!p.premium) return 'free'
  const premiumIds = ['ai_top5','mining_value','areit_income','franking_optimiser','short_interest_risk','multi_factor_qm','asx_dividend_aristocrats','quality_elite_compounder','altman_safety_screen','low_beta_income_shield','small_cap_hidden_gems']
  if (premiumIds.includes(p.id)) return 'premium'
  return 'pro'
}

// ── Category config ───────────────────────────────────────────────────────────

const CATEGORIES: { key: string; label: string; description: string; ids: string[] }[] = [
  {
    key: 'dividend',
    label: 'Dividend & Income',
    description: 'High-yield and franked dividend strategies for income investors',
    ids: ['value_franked', 'dividend_income'],
  },
  {
    key: 'value',
    label: 'Value & Quality',
    description: 'Undervalued stocks with strong fundamentals and financial health',
    ids: ['quality_undervalued', 'piotroski_strong', 'deep_value_growth'],
  },
  {
    key: 'growth',
    label: 'Growth & Momentum',
    description: 'Companies accelerating revenue, earnings and price momentum',
    ids: ['high_growth', 'momentum', 'halfyearly_acceleration'],
  },
  {
    key: 'technical',
    label: 'Technical Signals',
    description: 'Chart-based breakout, trend-following and mean-reversion signals',
    ids: ['ma_crossover', 'new_52w_highs', 'new_52w_lows', 'volume_breakout', 'rsi_oversold', 'rsi_overbought', 'turnaround'],
  },
]



// ── Sector color themes ───────────────────────────────────────────────────────
const SECTOR_THEME: Record<string, { bg: string; accent: string; badge: string; dot: string }> = {
  'Communication Services': { bg: 'bg-blue-50',   accent: 'border-blue-400',   badge: 'bg-blue-100 text-blue-700',   dot: 'bg-blue-500' },
  'Consumer Discretionary': { bg: 'bg-orange-50', accent: 'border-orange-400', badge: 'bg-orange-100 text-orange-700', dot: 'bg-orange-500' },
  'Consumer Staples':       { bg: 'bg-green-50',  accent: 'border-green-400',  badge: 'bg-green-100 text-green-700',  dot: 'bg-green-500' },
  'Energy':                 { bg: 'bg-yellow-50', accent: 'border-yellow-400', badge: 'bg-yellow-100 text-yellow-700', dot: 'bg-yellow-500' },
  'Financials':             { bg: 'bg-indigo-50', accent: 'border-indigo-400', badge: 'bg-indigo-100 text-indigo-700', dot: 'bg-indigo-500' },
  'Health Care':            { bg: 'bg-rose-50',   accent: 'border-rose-400',   badge: 'bg-rose-100 text-rose-700',   dot: 'bg-rose-500' },
  'Industrials':            { bg: 'bg-slate-50',  accent: 'border-slate-400',  badge: 'bg-slate-100 text-slate-600',  dot: 'bg-slate-500' },
  'Information Technology': { bg: 'bg-sky-50',    accent: 'border-sky-400',    badge: 'bg-sky-100 text-sky-700',     dot: 'bg-sky-500' },
  'Materials':              { bg: 'bg-amber-50',  accent: 'border-amber-400',  badge: 'bg-amber-100 text-amber-700', dot: 'bg-amber-500' },
  'Real Estate':            { bg: 'bg-purple-50', accent: 'border-purple-400', badge: 'bg-purple-100 text-purple-700', dot: 'bg-purple-500' },
  'Utilities':              { bg: 'bg-teal-50',   accent: 'border-teal-400',   badge: 'bg-teal-100 text-teal-700',   dot: 'bg-teal-500' },
}
const DEFAULT_SECTOR_THEME = { bg: 'bg-gray-50', accent: 'border-gray-400', badge: 'bg-gray-100 text-gray-600', dot: 'bg-gray-400' }

// ── Card color themes by screen type ─────────────────────────────────────────
const CARD_THEME: Record<string, { bg: string; border: string; iconBg: string; iconColor: string }> = {
  // Dividend / Income  →  Amber
  value_franked:             { bg: 'bg-amber-50',   border: 'border-amber-200',   iconBg: 'bg-amber-100',   iconColor: 'text-amber-600' },
  dividend_income:           { bg: 'bg-amber-50',   border: 'border-amber-200',   iconBg: 'bg-amber-100',   iconColor: 'text-amber-600' },
  dividend_growth_machine:   { bg: 'bg-amber-50',   border: 'border-amber-200',   iconBg: 'bg-amber-100',   iconColor: 'text-amber-600' },
  franking_optimiser:        { bg: 'bg-yellow-50',  border: 'border-yellow-200',  iconBg: 'bg-yellow-100',  iconColor: 'text-yellow-600' },
  asx_dividend_aristocrats:  { bg: 'bg-yellow-50',  border: 'border-yellow-200',  iconBg: 'bg-yellow-100',  iconColor: 'text-yellow-600' },
  low_beta_income_shield:    { bg: 'bg-amber-50',   border: 'border-amber-200',   iconBg: 'bg-amber-100',   iconColor: 'text-amber-600' },
  areit_income:              { bg: 'bg-teal-50',    border: 'border-teal-200',    iconBg: 'bg-teal-100',    iconColor: 'text-teal-600' },

  // Value / Quality  →  Green / Emerald
  quality_undervalued:       { bg: 'bg-green-50',   border: 'border-green-200',   iconBg: 'bg-green-100',   iconColor: 'text-green-600' },
  piotroski_strong:          { bg: 'bg-green-50',   border: 'border-green-200',   iconBg: 'bg-green-100',   iconColor: 'text-green-600' },
  deep_value_growth:         { bg: 'bg-green-50',   border: 'border-green-200',   iconBg: 'bg-green-100',   iconColor: 'text-green-600' },
  quality_elite_compounder:  { bg: 'bg-emerald-50', border: 'border-emerald-200', iconBg: 'bg-emerald-100', iconColor: 'text-emerald-600' },
  altman_safety_screen:      { bg: 'bg-teal-50',    border: 'border-teal-200',    iconBg: 'bg-teal-100',    iconColor: 'text-teal-600' },
  small_cap_hidden_gems:     { bg: 'bg-indigo-50',  border: 'border-indigo-200',  iconBg: 'bg-indigo-100',  iconColor: 'text-indigo-600' },

  // Growth / Momentum  →  Blue
  momentum:                  { bg: 'bg-blue-50',    border: 'border-blue-200',    iconBg: 'bg-blue-100',    iconColor: 'text-blue-600' },
  high_growth:               { bg: 'bg-blue-50',    border: 'border-blue-200',    iconBg: 'bg-blue-100',    iconColor: 'text-blue-600' },
  halfyearly_acceleration:   { bg: 'bg-blue-50',    border: 'border-blue-200',    iconBg: 'bg-blue-100',    iconColor: 'text-blue-600' },
  earnings_momentum_surge:   { bg: 'bg-blue-50',    border: 'border-blue-200',    iconBg: 'bg-blue-100',    iconColor: 'text-blue-600' },

  // Technical / Trading  →  Orange
  ma_crossover:              { bg: 'bg-orange-50',  border: 'border-orange-200',  iconBg: 'bg-orange-100',  iconColor: 'text-orange-600' },
  new_52w_highs:             { bg: 'bg-orange-50',  border: 'border-orange-200',  iconBg: 'bg-orange-100',  iconColor: 'text-orange-600' },
  new_52w_lows:              { bg: 'bg-orange-50',  border: 'border-orange-200',  iconBg: 'bg-orange-100',  iconColor: 'text-orange-600' },
  volume_breakout:           { bg: 'bg-orange-50',  border: 'border-orange-200',  iconBg: 'bg-orange-100',  iconColor: 'text-orange-600' },
  rsi_oversold:              { bg: 'bg-red-50',     border: 'border-red-200',     iconBg: 'bg-red-100',     iconColor: 'text-red-500' },
  rsi_overbought:            { bg: 'bg-red-50',     border: 'border-red-200',     iconBg: 'bg-red-100',     iconColor: 'text-red-500' },
  turnaround:                { bg: 'bg-orange-50',  border: 'border-orange-200',  iconBg: 'bg-orange-100',  iconColor: 'text-orange-600' },
  short_interest_risk:       { bg: 'bg-red-50',     border: 'border-red-200',     iconBg: 'bg-red-100',     iconColor: 'text-red-500' },

  // AI / Multi-Factor  →  Purple / Indigo
  ai_top5:                   { bg: 'bg-purple-50',  border: 'border-purple-200',  iconBg: 'bg-purple-100',  iconColor: 'text-purple-600' },
  multi_factor_qm:           { bg: 'bg-indigo-50',  border: 'border-indigo-200',  iconBg: 'bg-indigo-100',  iconColor: 'text-indigo-600' },

  // Mining  →  Amber/Brown
  mining_value:              { bg: 'bg-amber-50',   border: 'border-amber-200',   iconBg: 'bg-amber-100',   iconColor: 'text-amber-700' },

  // Cash Flow / ROIC  →  Emerald
  cash_flow_champion:        { bg: 'bg-emerald-50', border: 'border-emerald-200', iconBg: 'bg-emerald-100', iconColor: 'text-emerald-600' },
  roic_compounder:           { bg: 'bg-emerald-50', border: 'border-emerald-200', iconBg: 'bg-emerald-100', iconColor: 'text-emerald-600' },
  gross_margin_fortress:     { bg: 'bg-emerald-50', border: 'border-emerald-200', iconBg: 'bg-emerald-100', iconColor: 'text-emerald-600' },
}
const DEFAULT_THEME = { bg: 'bg-white', border: 'border-gray-200', iconBg: 'bg-blue-50', iconColor: 'text-blue-600' }

// ── Scan card ─────────────────────────────────────────────────────────────────

function ScanCard({ preset, isPro, tier }: { preset: ScreenerPreset; isPro: boolean; tier?: 'free' | 'pro' | 'premium' }) {
  const Icon = ICON_MAP[preset.icon] ?? Zap
  const locked = preset.premium && !isPro
  const theme = CARD_THEME[preset.id] ?? DEFAULT_THEME

  return (
    <Link
      href={locked ? '/pricing' : `/screener?preset=${preset.id}`}
      className={cn(
        'group relative flex flex-col gap-3 p-5 rounded-xl border transition-all duration-150',
        locked
          ? 'bg-gray-50 border-gray-200 cursor-pointer hover:border-gray-300'
          : theme.bg + ' ' + theme.border + ' hover:shadow-md hover:-translate-y-0.5 hover:brightness-95',
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className={cn(
          'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0',
          locked ? 'bg-gray-100' : theme.iconBg + ' transition-colors',
        )}>
          <Icon className={cn('w-5 h-5', locked ? 'text-gray-400' : theme.iconColor)} />
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {tier === 'premium' ? (
            <span className={cn(
              'inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide',
              locked ? 'bg-amber-100 text-amber-700' : 'bg-purple-100 text-purple-700',
            )}>
              {locked && <Lock className="w-2.5 h-2.5" />}
              Premium
            </span>
          ) : tier === 'pro' ? (
            <span className={cn(
              'inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide',
              locked ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700',
            )}>
              {locked && <Lock className="w-2.5 h-2.5" />}
              Pro
            </span>
          ) : (
            <span className="inline-flex text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide bg-emerald-100 text-emerald-700">
              Free
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div>
        <h3 className={cn('font-semibold text-sm mb-1', locked ? 'text-gray-500' : 'text-gray-900')}>
          {preset.name}
        </h3>
        <p className={cn('text-xs leading-relaxed', locked ? 'text-gray-400' : 'text-gray-500')}>
          {preset.description}
        </p>
      </div>

      {/* Filter pills */}
      <div className="flex flex-wrap gap-1 mt-auto pt-1">
        {preset.filters.slice(0, 3).map((f, i) => (
          <span key={i} className={cn(
            'text-[10px] px-2 py-0.5 rounded-full',
            locked ? 'bg-gray-100 text-gray-400' : 'bg-slate-100 text-slate-600',
          )}>
            {f.field.replace(/_/g, ' ')}
          </span>
        ))}
        {preset.filters.length > 3 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
            +{preset.filters.length - 3} more
          </span>
        )}
      </div>

      {/* Run arrow */}
      {!locked && (
        <div className="absolute bottom-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </div>
      )}
    </Link>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ScansPage() {
  const { user } = useAuth()
  const isPro    = ['pro', 'premium', 'enterprise_pro', 'enterprise_premium'].includes(user?.plan ?? 'free')
  const isPremium = ['premium', 'enterprise_premium'].includes(user?.plan ?? 'free')
  const isAdmin  = user?.is_admin ?? false
  const hasQueryAccess = isAdmin || isPro
  const [presets, setPresets] = useState<ScreenerPreset[]>([])
  const [loading, setLoading] = useState(true)
  const [community, setCommunity] = useState<SavedScreen[]>([])
  const [communityLocked, setCommunityLocked] = useState(false)
  const [sectors, setSectors] = useState<{sector: string; stock_count: number}[]>([])

  useEffect(() => {
    getScreenerPresets()
      .then(d => setPresets(d.presets))
      .finally(() => setLoading(false))
    getCommunityScreens()
      .then(d => setCommunity(d.screens))
      .catch((err) => {
        if (err?.response?.status === 403 || err?.response?.status === 401) {
          setCommunityLocked(true)
        }
      })
    getMarketSectors()
      .then(d => setSectors(d.sectors))
      .catch(() => {})
  }, [])

  // Scroll to anchor section after page loads
  useEffect(() => {
    if (typeof window === 'undefined') return
    const hash = window.location.hash
    if (!hash) return
    const scrollToHash = () => {
      const el = document.querySelector(hash)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }
    // Wait for content to render
    const t1 = setTimeout(scrollToHash, 400)
    const t2 = setTimeout(scrollToHash, 900)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [loading])

  const presetMap = Object.fromEntries(presets.map(p => [p.id, p]))

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 mb-1">Alpha Screens</h1>
              <p className="text-gray-500 text-sm">
                Institutional-grade screens built on proven quant strategies.
                Click any screen to run it instantly in the full screener.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <HelpDrawer sections={SCANS_SECTIONS} title="Scans Guide" subtitle="How pre-built screens and categories work" />
              <Link
                href="/screener"
                className="text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
              >
                Custom Screener →
              </Link>
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-6 mt-5">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900">{presets.length}</p>
              <p className="text-xs text-gray-500">Total Screens</p>
            </div>
            <div className="w-px h-8 bg-gray-200" />
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900">{presets.filter(p => !p.premium).length}</p>
              <p className="text-xs text-gray-500">Free</p>
            </div>
            <div className="w-px h-8 bg-gray-200" />
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900">{presets.filter(p => p.premium).length}</p>
              <p className="text-xs text-gray-500">Pro + Premium</p>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-10">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* ── 1. Premium Screens ── */}
            <section id="premium-screens">
              <div className="mb-5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-purple-100 rounded-xl flex items-center justify-center">
                    <Award className="w-5 h-5 text-purple-600" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-gray-900">Premium Screens</h2>
                    <p className="text-xs text-gray-500 mt-0.5">Exclusive AI-powered &amp; specialist strategies for elite investors</p>
                  </div>
                </div>
                {!isPremium && (
                  <Link href="/pricing" className="flex-shrink-0 flex items-center gap-1.5 text-xs bg-purple-600 text-white px-3 py-1.5 rounded-full font-semibold hover:bg-purple-700 transition-colors">
                    <Lock className="w-3 h-3" /> Unlock Premium
                  </Link>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {presets.filter(p => presetTier(p) === 'premium').map(p => (
                  <ScanCard key={p.id} preset={p} isPro={isPremium} tier="premium" />
                ))}
              </div>
            </section>

            {/* ── 2. Pro Strategies ── */}
            <section id="pro-strategies">
              <div className="mb-5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-blue-100 rounded-xl flex items-center justify-center">
                    <TrendingUp className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-gray-900">Pro Strategies</h2>
                    <p className="text-xs text-gray-500 mt-0.5">Advanced quantitative screens for serious investors</p>
                  </div>
                </div>
                {!isPro && (
                  <Link href="/pricing" className="flex-shrink-0 flex items-center gap-1.5 text-xs bg-blue-600 text-white px-3 py-1.5 rounded-full font-semibold hover:bg-blue-700 transition-colors">
                    <Lock className="w-3 h-3" /> Unlock Pro
                  </Link>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {presets.filter(p => presetTier(p) === 'pro').map(p => (
                  <ScanCard key={p.id} preset={p} isPro={isPro} tier="pro" />
                ))}
              </div>
            </section>

            {/* ── 3. Quick Screens ── */}
            <section id="quick-screens">
              <div className="mb-5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-yellow-100 rounded-xl flex items-center justify-center">
                    <Zap className="w-5 h-5 text-yellow-500" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-gray-900">Quick Screens</h2>
                    <p className="text-xs text-gray-500 mt-0.5">Essential free screens to discover ASX opportunities instantly</p>
                  </div>
                </div>
                <span className="flex-shrink-0 text-xs bg-emerald-100 text-emerald-700 px-3 py-1.5 rounded-full font-semibold">Free</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {presets.filter(p => presetTier(p) === 'free').map(p => (
                  <ScanCard key={p.id} preset={p} isPro={true} tier="free" />
                ))}
              </div>
            </section>

            
            {/* ── Sector Screens ── */}
            {sectors.length > 0 && (
              <section id="sector-screens">
                <div className="mb-5 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 bg-slate-100 rounded-xl flex items-center justify-center">
                      <Globe className="w-5 h-5 text-slate-600" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-gray-900">Sector Screens</h2>
                      <p className="text-xs text-gray-500 mt-0.5">Browse all ASX stocks by GICS sector — live stock counts</p>
                    </div>
                  </div>
                  <span className="flex-shrink-0 text-xs bg-slate-100 text-slate-600 px-3 py-1.5 rounded-full font-semibold">Free</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                  {sectors.map(s => {
                    const t = SECTOR_THEME[s.sector] ?? DEFAULT_SECTOR_THEME
                    return (
                      <Link
                        key={s.sector}
                        href={"/screener?sector=" + encodeURIComponent(s.sector)}
                        className={"group flex items-center gap-3 p-4 rounded-xl border-2 " + t.bg + " " + t.accent + " hover:shadow-md hover:-translate-y-0.5 transition-all duration-150"}
                      >
                        <div className={"w-2.5 h-2.5 rounded-full flex-shrink-0 " + t.dot} />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-gray-900 truncate leading-tight">{s.sector}</p>
                          <span className={"text-[11px] font-bold px-1.5 py-0.5 rounded-full mt-1 inline-block " + t.badge}>
                            {s.stock_count} stocks
                          </span>
                        </div>
                      </Link>
                    )
                  })}
                </div>
              </section>
            )}

{/* ── 4. Community Picks ── */}
            <section id="community-picks">
              <div className="mb-5 flex items-center gap-3">
                <div className="w-9 h-9 bg-green-100 rounded-xl flex items-center justify-center">
                  <Users className="w-5 h-5 text-green-600" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-gray-900">Community Picks</h2>
                  <p className="text-xs text-gray-500 mt-0.5">Screens created and shared by ASX Screener users</p>
                </div>
              </div>
              {communityLocked ? (
                <div className="bg-gradient-to-br from-orange-50 to-amber-50 border border-orange-200 rounded-xl p-8 text-center">
                  <div className="w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center mx-auto mb-3">
                    <Lock className="w-6 h-6 text-orange-500" />
                  </div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">Pro &amp; Premium Feature</h3>
                  <p className="text-sm text-gray-600 mb-4">Community Picks are shared screens created by Pro and Premium subscribers. Upgrade to discover and use them.</p>
                  <Link href="/pricing" className="inline-flex items-center gap-1.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
                    <Lock className="w-3.5 h-3.5" /> Upgrade to Pro
                  </Link>
                </div>
              ) : community.length === 0 ? (
                <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
                  <Globe className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                  <p className="text-sm text-gray-500">No community screens yet.</p>
                  <p className="text-xs text-gray-400 mt-1">Save a screen in the Screener and make it public to share with others.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {community.map(s => {
                    const isQueryScreen = !!s.query_text
                    const locked = isQueryScreen && !hasQueryAccess
                    const cardContent = (
                      <>
                        <div className="flex items-start justify-between gap-3">
                          <div className={cn(
                            'w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-colors',
                            isQueryScreen
                              ? 'bg-orange-50 group-hover:bg-orange-100'
                              : 'bg-green-50 group-hover:bg-green-100'
                          )}>
                            {isQueryScreen
                              ? <Code2 className="w-5 h-5 text-orange-500" />
                              : <Globe className="w-5 h-5 text-green-600" />}
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {isQueryScreen && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-100 text-orange-600 font-semibold">Query Mode</span>
                            )}
                            <span className="text-xs text-gray-400">{s.use_count > 0 ? s.use_count + " runs" : ""}</span>
                          </div>
                        </div>
                        <div>
                          <h3 className="font-semibold text-sm text-gray-900 mb-0.5">{s.name}</h3>
                          {s.description && <p className="text-xs text-gray-500 leading-relaxed">{s.description}</p>}
                          <p className="text-[11px] text-gray-400 mt-1">by {s.user_name}</p>
                        </div>
                        <div className="flex flex-wrap gap-1 mt-auto pt-1">
                          {isQueryScreen ? (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-orange-50 text-orange-500 font-mono">SQL-like query</span>
                          ) : (
                            <>
                              {s.filters.slice(0, 3).map((f, i) => (
                                <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{(f.field as string).replace(/_/g, " ")}</span>
                              ))}
                              {s.filters.length > 3 && <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">+{s.filters.length - 3} more</span>}
                            </>
                          )}
                        </div>
                        {locked ? (
                          <div className="absolute inset-0 rounded-xl bg-white/70 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                            <div className="flex items-center gap-1.5 bg-orange-500 text-white text-xs font-semibold px-3 py-1.5 rounded-full shadow">
                              <Lock className="w-3 h-3" /> Pro / Premium required
                            </div>
                          </div>
                        ) : (
                          <div className="absolute bottom-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
                            <div className={cn('w-6 h-6 rounded-full flex items-center justify-center', isQueryScreen ? 'bg-orange-500' : 'bg-blue-600')}>
                              <Play className="w-3 h-3 text-white" />
                            </div>
                          </div>
                        )}
                      </>
                    )
                    return locked ? (
                      <div key={s.id} className="group relative flex flex-col gap-3 p-5 rounded-xl border border-gray-200 bg-white cursor-not-allowed opacity-80">
                        {cardContent}
                      </div>
                    ) : (
                      <Link key={s.id} href={"/screener?screen=" + s.id} onClick={() => incrementScreenUse(s.id)}
                        className="group relative flex flex-col gap-3 p-5 rounded-xl border border-gray-200 bg-white hover:border-orange-300 hover:shadow-md hover:-translate-y-0.5 transition-all duration-150">
                        {cardContent}
                      </Link>
                    )
                  })}
                </div>
              )}
            </section>
            </>
        )}
      </div>
    </div>
  )
}
