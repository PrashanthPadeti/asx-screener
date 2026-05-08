'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Shield, Zap, Award, RotateCcw, DollarSign, Search,
  TrendingUp, BarChart2, ArrowUp, Star, Activity, Lock,
} from 'lucide-react'
import { getScreenerPresets, type ScreenerPreset } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

// ── Icon map ──────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  'shield':      Shield,
  'zap':         Zap,
  'award':       Award,
  'rotate-ccw':  RotateCcw,
  'dollar-sign': DollarSign,
  'search':      Search,
  'trending-up': TrendingUp,
  'bar-chart-2': BarChart2,
  'arrow-up':    ArrowUp,
  'star':        Star,
  'activity':    Activity,
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
    description: 'Chart-based breakout and trend-following signals',
    ids: ['ma_crossover', 'new_52w_highs', 'turnaround'],
  },
]

// ── Scan card ─────────────────────────────────────────────────────────────────

function ScanCard({ preset, isPro }: { preset: ScreenerPreset; isPro: boolean }) {
  const Icon = ICON_MAP[preset.icon] ?? Zap
  const locked = preset.premium && !isPro

  return (
    <Link
      href={locked ? '/pricing' : `/screener?preset=${preset.id}`}
      className={cn(
        'group relative flex flex-col gap-3 p-5 rounded-xl border transition-all duration-150',
        locked
          ? 'bg-gray-50 border-gray-200 cursor-pointer hover:border-gray-300'
          : 'bg-white border-gray-200 hover:border-blue-300 hover:shadow-md hover:-translate-y-0.5',
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className={cn(
          'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0',
          locked ? 'bg-gray-100' : 'bg-blue-50 group-hover:bg-blue-100 transition-colors',
        )}>
          <Icon className={cn('w-5 h-5', locked ? 'text-gray-400' : 'text-blue-600')} />
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {preset.premium ? (
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
  const isPro = ['pro', 'premium', 'enterprise_pro', 'enterprise_premium'].includes(user?.plan ?? 'free')
  const [presets, setPresets] = useState<ScreenerPreset[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getScreenerPresets()
      .then(d => setPresets(d.presets))
      .finally(() => setLoading(false))
  }, [])

  const presetMap = Object.fromEntries(presets.map(p => [p.id, p]))

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 mb-1">Market Scans</h1>
              <p className="text-gray-500 text-sm">
                Pre-built screens to surface stocks matching proven investment strategies.
                Click any scan to run it in the full screener.
              </p>
            </div>
            <Link
              href="/screener"
              className="flex-shrink-0 text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
            >
              Custom Screener →
            </Link>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-6 mt-5">
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900">{presets.length}</p>
              <p className="text-xs text-gray-500">Total Scans</p>
            </div>
            <div className="w-px h-8 bg-gray-200" />
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900">{presets.filter(p => !p.premium).length}</p>
              <p className="text-xs text-gray-500">Free Scans</p>
            </div>
            <div className="w-px h-8 bg-gray-200" />
            <div className="text-center">
              <p className="text-2xl font-bold text-gray-900">{presets.filter(p => p.premium).length}</p>
              <p className="text-xs text-gray-500">Pro Scans</p>
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
          CATEGORIES.map(cat => {
            const catPresets = cat.ids.map(id => presetMap[id]).filter(Boolean)
            if (!catPresets.length) return null
            return (
              <section key={cat.key}>
                <div className="mb-4">
                  <h2 className="text-base font-bold text-gray-900">{cat.label}</h2>
                  <p className="text-xs text-gray-500 mt-0.5">{cat.description}</p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {catPresets.map(p => (
                    <ScanCard key={p.id} preset={p} isPro={isPro} />
                  ))}
                </div>
              </section>
            )
          })
        )}
      </div>
    </div>
  )
}
