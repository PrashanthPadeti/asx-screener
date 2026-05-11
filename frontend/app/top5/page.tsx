'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Trophy, TrendingUp, Shield, Star, DollarSign, BarChart2,
  ChevronRight, Info, Calendar, ArrowUpRight, Lock,
} from 'lucide-react'
import { PlanGate } from '@/components/PlanGate'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Pick {
  rank: number
  asx_code: string
  company_name: string | null
  sector: string | null
  composite_score: number | null
  momentum_score: number | null
  quality_score: number | null
  value_score: number | null
  income_score: number | null
  growth_score: number | null
  price: number | null
  market_cap: number | null
  pe_ratio: number | null
  dividend_yield: number | null
  grossed_up_yield: number | null
  franking_pct: number | null
  return_3m: number | null
  return_1y: number | null
  roe: number | null
  piotroski_f_score: number | null
}

interface CurrentResponse {
  pick_month: string | null
  picks: Pick[]
  total_months: number
}

interface HistoryMonth {
  pick_month: string
  picks: Pick[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt = {
  pct:    (v: number | null) => v == null ? '—' : `${(v * 100).toFixed(1)}%`,
  score:  (v: number | null) => v == null ? '—' : v.toFixed(1),
  price:  (v: number | null) => v == null ? '—' : `$${v.toFixed(2)}`,
  cap:    (v: number | null) => v == null ? '—' : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`,
  pe:     (v: number | null) => v == null ? '—' : `${v.toFixed(1)}x`,
  month:  (iso: string) => {
    const d = new Date(iso + 'T00:00:00')
    return d.toLocaleString('en-AU', { month: 'long', year: 'numeric' })
  },
  monthShort: (iso: string) => {
    const d = new Date(iso + 'T00:00:00')
    return d.toLocaleString('en-AU', { month: 'short', year: '2-digit' })
  },
}

const RANK_COLOURS = [
  'from-yellow-400 to-amber-500',   // #1 gold
  'from-gray-300 to-gray-400',      // #2 silver
  'from-orange-400 to-orange-500',  // #3 bronze
  'from-blue-400 to-blue-500',      // #4
  'from-violet-400 to-violet-500',  // #5
]

const RANK_RING = [
  'ring-amber-400',
  'ring-gray-400',
  'ring-orange-400',
  'ring-blue-400',
  'ring-violet-400',
]

const FACTORS = [
  { key: 'momentum_score', label: 'Momentum', icon: TrendingUp,  colour: 'bg-blue-500'   },
  { key: 'quality_score',  label: 'Quality',  icon: Shield,      colour: 'bg-emerald-500' },
  { key: 'value_score',    label: 'Value',    icon: Star,        colour: 'bg-amber-500'  },
  { key: 'income_score',   label: 'Income',   icon: DollarSign,  colour: 'bg-purple-500'  },
  { key: 'growth_score',   label: 'Growth',   icon: BarChart2,   colour: 'bg-rose-500'   },
] as const

// ── Score bar ─────────────────────────────────────────────────────────────────

function ScoreBar({
  label, score, colour, icon: Icon,
}: {
  label: string; score: number | null; colour: string; icon: React.ComponentType<{ className?: string }>
}) {
  const pct = score ?? 0
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="flex items-center gap-1 text-gray-500">
          <Icon className="w-3 h-3" />
          {label}
        </span>
        <span className="font-semibold text-gray-700">{fmt.score(score)}</span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-500', colour)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ── Pick card ─────────────────────────────────────────────────────────────────

function PickCard({ pick }: { pick: Pick }) {
  const idx = pick.rank - 1
  const gradClass  = RANK_COLOURS[idx] ?? 'from-blue-400 to-blue-500'
  const ringClass  = RANK_RING[idx]    ?? 'ring-blue-400'
  const score      = pick.composite_score ?? 0

  return (
    <Link
      href={`/company/${pick.asx_code}`}
      className="group bg-white rounded-2xl border border-gray-200 hover:border-blue-300
                 hover:shadow-lg transition-all duration-150 overflow-hidden flex flex-col"
    >
      {/* Rank banner */}
      <div className={cn('h-1.5 bg-gradient-to-r', gradClass)} />

      <div className="p-5 flex flex-col gap-4 flex-1">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            {/* Rank badge */}
            <div className={cn(
              'w-9 h-9 rounded-xl bg-gradient-to-br flex items-center justify-center',
              'ring-2 flex-shrink-0 shadow-sm',
              gradClass, ringClass,
            )}>
              <span className="text-white font-bold text-sm">#{pick.rank}</span>
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-gray-900 text-base">{pick.asx_code}</span>
                <ArrowUpRight className="w-3.5 h-3.5 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <p className="text-xs text-gray-500 line-clamp-1 max-w-[140px]">
                {pick.company_name || pick.asx_code}
              </p>
            </div>
          </div>
          {/* Composite score circle */}
          <div className="text-center flex-shrink-0">
            <div className={cn(
              'w-12 h-12 rounded-full bg-gradient-to-br flex items-center justify-center shadow-sm',
              gradClass,
            )}>
              <span className="text-white font-bold text-sm">{score.toFixed(0)}</span>
            </div>
            <p className="text-[9px] text-gray-400 mt-0.5">score</p>
          </div>
        </div>

        {/* Sector pill */}
        {pick.sector && (
          <span className="self-start text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
            {pick.sector}
          </span>
        )}

        {/* Factor scores */}
        <div className="space-y-2">
          {FACTORS.map(f => (
            <ScoreBar
              key={f.key}
              label={f.label}
              score={pick[f.key]}
              colour={f.colour}
              icon={f.icon}
            />
          ))}
        </div>

        {/* Key metrics strip */}
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-gray-100">
          <div className="text-center">
            <p className="text-xs font-semibold text-gray-800">{fmt.price(pick.price)}</p>
            <p className="text-[9px] text-gray-400">Price</p>
          </div>
          <div className="text-center">
            <p className={cn(
              'text-xs font-semibold',
              pick.return_3m == null ? 'text-gray-800'
                : pick.return_3m >= 0 ? 'text-emerald-600' : 'text-red-500',
            )}>
              {fmt.pct(pick.return_3m)}
            </p>
            <p className="text-[9px] text-gray-400">3M Ret</p>
          </div>
          <div className="text-center">
            <p className="text-xs font-semibold text-gray-800">{fmt.pct(pick.grossed_up_yield)}</p>
            <p className="text-[9px] text-gray-400">Gr. Yield</p>
          </div>
        </div>
      </div>
    </Link>
  )
}

// ── History table ─────────────────────────────────────────────────────────────

function HistoryTable({ history }: { history: HistoryMonth[] }) {
  if (!history.length) return null
  return (
    <section>
      <div className="flex items-center gap-2 mb-4">
        <Calendar className="w-4 h-4 text-blue-500" />
        <h2 className="text-base font-bold text-gray-900">Historical Picks</h2>
      </div>
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-3 font-semibold text-gray-700 text-xs">Month</th>
                {[1,2,3,4,5].map(r => (
                  <th key={r} className="text-left px-3 py-3 font-semibold text-gray-700 text-xs">#{r}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {history.map(({ pick_month, picks }) => (
                <tr key={pick_month} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-700 text-xs whitespace-nowrap">
                    {fmt.monthShort(pick_month)}
                  </td>
                  {[1,2,3,4,5].map(rank => {
                    const p = picks.find(x => x.rank === rank)
                    return (
                      <td key={rank} className="px-3 py-3">
                        {p ? (
                          <Link
                            href={`/company/${p.asx_code}`}
                            className="group flex flex-col"
                          >
                            <span className="font-semibold text-gray-900 group-hover:text-blue-600 text-xs">
                              {p.asx_code}
                            </span>
                            <span className="text-[10px] text-gray-400">
                              {fmt.score(p.composite_score)}
                            </span>
                          </Link>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

// ── How it works ──────────────────────────────────────────────────────────────

function HowItWorks() {
  const factors = [
    { icon: TrendingUp,  colour: 'text-blue-600 bg-blue-50',    label: 'Momentum',  desc: 'Price returns (1M, 3M, 6M), RSI and ADX trend strength' },
    { icon: Shield,      colour: 'text-emerald-600 bg-emerald-50', label: 'Quality', desc: 'Piotroski F-Score, ROE, ROCE, Altman Z-Score, margins' },
    { icon: Star,        colour: 'text-amber-600 bg-amber-50',   label: 'Value',     desc: 'P/E, P/B, EV/EBITDA, FCF yield, Price-to-Sales' },
    { icon: DollarSign,  colour: 'text-purple-600 bg-purple-50', label: 'Income',    desc: 'Grossed-up yield, franking %, dividend consistency' },
    { icon: BarChart2,   colour: 'text-rose-600 bg-rose-50',     label: 'Growth',    desc: 'Revenue & EPS growth (1Y, 3Y CAGR, half-yearly acceleration)' },
  ]
  return (
    <section className="bg-white border border-gray-200 rounded-2xl p-6">
      <div className="flex items-start gap-2 mb-5">
        <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
        <div>
          <h2 className="text-base font-bold text-gray-900">How the ranking works</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Each ASX200 stock is scored on 5 equal-weighted factors using percentile ranks (0–100) within the index.
            The composite score is the average of all 5 factors. Higher = better across all dimensions.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
        {factors.map(({ icon: Icon, colour, label, desc }) => (
          <div key={label} className="flex flex-col gap-2">
            <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center', colour)}>
              <Icon className="w-4 h-4" />
            </div>
            <p className="font-semibold text-xs text-gray-800">{label} (20%)</p>
            <p className="text-[11px] text-gray-500 leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 pt-4 border-t border-gray-100 flex flex-wrap gap-4 text-[11px] text-gray-500">
        <span>📊 Universe: ASX 200</span>
        <span>📅 Refreshed: Monthly</span>
        <span>⚖️ Weighting: Equal (5 × 20%)</span>
        <span>📐 Method: Percentile rank within index</span>
      </div>
    </section>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

function Top5Content() {
  const [current, setCurrent]   = useState<CurrentResponse | null>(null)
  const [history, setHistory]   = useState<HistoryMonth[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get('/api/v1/top5/current'),
      api.get('/api/v1/top5/history?months=12'),
    ])
      .then(([cur, hist]) => {
        setCurrent(cur.data)
        setHistory(hist.data.history ?? [])
      })
      .catch(() => setError('Failed to load strategy data.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-7 h-7 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (error || !current?.picks.length) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <Trophy className="w-12 h-12 text-gray-200 mb-3" />
        <p className="text-gray-500 font-medium">No picks available yet</p>
        <p className="text-sm text-gray-400 mt-1">
          The strategy runs on the 1st of each month. Check back soon.
        </p>
      </div>
    )
  }

  const { pick_month, picks, total_months } = current

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-10">

      {/* Current month picks */}
      <section>
        <div className="flex items-center justify-between mb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-700 uppercase tracking-wide">
                {pick_month ? fmt.month(pick_month) : 'Latest'}
              </span>
              {total_months > 1 && (
                <span className="text-xs text-gray-400">{total_months} months of history</span>
              )}
            </div>
            <h2 className="text-xl font-bold text-gray-900">This Month's Top 5</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Highest composite-scored ASX200 stocks across all 5 factors
            </p>
          </div>
          <Link
            href="/screener"
            className="hidden sm:flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            Full Screener <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {picks.map(p => <PickCard key={p.asx_code} pick={p} />)}
        </div>
      </section>

      {/* How it works */}
      <HowItWorks />

      {/* History */}
      <HistoryTable history={history} />

    </div>
  )
}

export default function Top5Page() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Page header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500
                            flex items-center justify-center shadow-sm flex-shrink-0">
              <Trophy className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">ASX Top 5 Strategy</h1>
              <p className="text-gray-500 text-sm mt-0.5">
                Monthly algo-ranked top 5 from the ASX200 — scored across momentum, quality,
                value, income and growth. Refreshed on the 1st of each month.
              </p>
            </div>
          </div>
        </div>
      </div>

      <PlanGate required="premium" feature="Top 5 Strategy">
        <Top5Content />
      </PlanGate>
    </div>
  )
}
