'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Trophy, TrendingUp, Shield, Star, DollarSign, BarChart2,
  ChevronRight, Info, Calendar, ArrowUpRight, Bell,
  Briefcase, AlertTriangle, ChevronDown, ChevronUp,
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
  pct:       (v: number | null) => v == null ? null : `${(v * 100).toFixed(1)}%`,
  pctSigned: (v: number | null) => v == null ? null : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`,
  score:     (v: number | null) => v == null ? null : v.toFixed(1),
  price:     (v: number | null) => v == null ? null : `$${v.toFixed(2)}`,
  cap:       (v: number | null) => v == null ? null : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`,
  pe:        (v: number | null) => v == null ? null : `${v.toFixed(1)}x`,
  month:     (iso: string) => new Date(iso + 'T00:00:00').toLocaleString('en-AU', { month: 'long', year: 'numeric' }),
  monthShort:(iso: string) => new Date(iso + 'T00:00:00').toLocaleString('en-AU', { month: 'short', year: '2-digit' }),
}

function retColor(v: number | null): string {
  if (v == null) return 'text-gray-400'
  return v >= 0 ? 'text-emerald-600' : 'text-red-500'
}

/** Determine the top 2 scoring factors and generate a plain-English "why selected" reason */
function whySelected(pick: Pick): { summary: string; details: string } {
  const scored = [
    { label: 'Momentum', score: pick.momentum_score, desc: 'strong recent price trend and technical strength' },
    { label: 'Quality',  score: pick.quality_score,  desc: 'high Piotroski F-Score, solid ROE and low financial risk' },
    { label: 'Value',    score: pick.value_score,    desc: 'attractive valuation relative to earnings and book value' },
    { label: 'Income',   score: pick.income_score,   desc: 'above-average dividend yield with good franking credits' },
    { label: 'Growth',   score: pick.growth_score,   desc: 'accelerating revenue and earnings growth trajectory' },
  ]
    .filter(f => f.score != null)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))

  if (scored.length === 0) return { summary: 'Top composite scorer this month', details: 'Ranked #' + pick.rank + ' across all factors in the ASX 200.' }

  const top = scored.slice(0, 2)
  const summary = top.length === 2
    ? `Leads on ${top[0].label} & ${top[1].label}`
    : `Leads on ${top[0].label}`

  const details = top.length === 2
    ? `Selected for ${top[0].desc}, combined with ${top[1].desc}. Ranks #${pick.rank} overall in the ASX 200 this month.`
    : `Selected for ${top[0].desc}. Ranks #${pick.rank} overall in the ASX 200 this month.`

  return { summary, details }
}

/** Average 3M return across an array of picks (ignores nulls) */
function avgReturn3m(picks: Pick[]): number | null {
  const vals = picks.map(p => p.return_3m).filter((v): v is number => v != null)
  if (!vals.length) return null
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

// ── Constants ─────────────────────────────────────────────────────────────────

const RANK_COLOURS = [
  'from-yellow-400 to-amber-500',
  'from-gray-300 to-gray-400',
  'from-orange-400 to-orange-500',
  'from-blue-400 to-blue-500',
  'from-violet-400 to-violet-500',
]

const RANK_RING = [
  'ring-amber-400', 'ring-gray-400', 'ring-orange-400', 'ring-blue-400', 'ring-violet-400',
]

const FACTORS = [
  { key: 'momentum_score' as const, label: 'Momentum', icon: TrendingUp,  colour: 'bg-blue-500'    },
  { key: 'quality_score'  as const, label: 'Quality',  icon: Shield,      colour: 'bg-emerald-500'  },
  { key: 'value_score'    as const, label: 'Value',    icon: Star,        colour: 'bg-amber-500'   },
  { key: 'income_score'   as const, label: 'Income',   icon: DollarSign,  colour: 'bg-purple-500'   },
  { key: 'growth_score'   as const, label: 'Growth',   icon: BarChart2,   colour: 'bg-rose-500'    },
]

// ── Score bar ─────────────────────────────────────────────────────────────────

function ScoreBar({ label, score, colour, icon: Icon }: {
  label: string; score: number | null; colour: string; icon: React.ComponentType<{ className?: string }>
}) {
  const pct = score ?? 0
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="flex items-center gap-1 text-gray-500">
          <Icon className="w-3 h-3" /> {label}
        </span>
        <span className={cn('font-semibold', score == null ? 'text-gray-300 italic' : 'text-gray-700')}>
          {fmt.score(score) ?? 'N/A'}
        </span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full transition-all duration-500', score == null ? 'bg-gray-200' : colour)}
          style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// ── Value display with null explanation ───────────────────────────────────────

function MetricCell({ value, label, nullReason }: { value: string | null; label: string; nullReason?: string }) {
  return (
    <div className="text-center">
      {value != null ? (
        <p className="text-xs font-semibold text-gray-800">{value}</p>
      ) : (
        <div className="group relative inline-block">
          <p className="text-xs font-semibold text-gray-300 cursor-help">—</p>
          {nullReason && (
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-40 bg-gray-800 text-white text-[10px] rounded-lg px-2 py-1.5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 text-center leading-relaxed">
              {nullReason}
            </div>
          )}
        </div>
      )}
      <p className="text-[9px] text-gray-400">{label}</p>
    </div>
  )
}

// ── Pick card ─────────────────────────────────────────────────────────────────

function PickCard({ pick }: { pick: Pick }) {
  const [expanded, setExpanded] = useState(false)
  const idx       = pick.rank - 1
  const gradClass = RANK_COLOURS[idx] ?? 'from-blue-400 to-blue-500'
  const ringClass = RANK_RING[idx]    ?? 'ring-blue-400'
  const score     = pick.composite_score ?? 0
  const { summary, details } = whySelected(pick)

  return (
    <div className="group bg-white rounded-2xl border border-gray-200 hover:border-blue-300
                    hover:shadow-lg transition-all duration-150 overflow-hidden flex flex-col">
      {/* Rank gradient banner */}
      <div className={cn('h-1.5 bg-gradient-to-r', gradClass)} />

      <div className="p-5 flex flex-col gap-4 flex-1">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className={cn('w-9 h-9 rounded-xl bg-gradient-to-br flex items-center justify-center ring-2 flex-shrink-0 shadow-sm', gradClass, ringClass)}>
              <span className="text-white font-bold text-sm">#{pick.rank}</span>
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <Link href={`/company/${pick.asx_code}`}
                  className="font-bold text-gray-900 text-base hover:text-blue-600 transition-colors">
                  {pick.asx_code}
                </Link>
                <ArrowUpRight className="w-3.5 h-3.5 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <p className="text-xs text-gray-500 line-clamp-1 max-w-[130px]">
                {pick.company_name || pick.asx_code}
              </p>
            </div>
          </div>

          {/* Actions + score */}
          <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
            {/* Composite score */}
            <div className={cn('w-11 h-11 rounded-full bg-gradient-to-br flex items-center justify-center shadow-sm', gradClass)}>
              <span className="text-white font-bold text-sm">{score.toFixed(0)}</span>
            </div>
            <p className="text-[9px] text-gray-400">score</p>
          </div>
        </div>

        {/* Action buttons row */}
        <div className="flex items-center gap-1.5 -mt-1">
          <Link href={`/watchlist?add=${pick.asx_code}`}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-gray-100 hover:bg-amber-100 text-gray-500 hover:text-amber-600 text-[10px] font-medium transition-colors"
            title="Add to watchlist">
            <Star className="w-3 h-3" /> Watch
          </Link>
          <Link href={`/alerts?stock=${pick.asx_code}`}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-gray-100 hover:bg-blue-100 text-gray-500 hover:text-blue-600 text-[10px] font-medium transition-colors"
            title="Set price alert">
            <Bell className="w-3 h-3" /> Alert
          </Link>
          <Link href={`/portfolio?add=${pick.asx_code}`}
            className="flex items-center gap-1 px-2 py-1 rounded-md bg-gray-100 hover:bg-emerald-100 text-gray-500 hover:text-emerald-600 text-[10px] font-medium transition-colors"
            title="Add to portfolio">
            <Briefcase className="w-3 h-3" /> Portfolio
          </Link>
        </div>

        {/* Sector pill */}
        {pick.sector && (
          <span className="self-start text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 -mt-1">
            {pick.sector}
          </span>
        )}

        {/* Factor scores */}
        <div className="space-y-2">
          {FACTORS.map(f => (
            <ScoreBar key={f.key} label={f.label} score={pick[f.key]} colour={f.colour} icon={f.icon} />
          ))}
        </div>

        {/* Key metrics strip */}
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-gray-100">
          <MetricCell
            value={fmt.price(pick.price)}
            label="Price"
            nullReason="Price not available"
          />
          <MetricCell
            value={pick.return_3m != null ? (
              `${pick.return_3m >= 0 ? '+' : ''}${(pick.return_3m * 100).toFixed(1)}%`
            ) : null}
            label="3M Ret"
            nullReason="Insufficient price history for 3-month return"
          />
          <MetricCell
            value={fmt.pct(pick.grossed_up_yield)}
            label="Gr. Yield"
            nullReason="Dividend or franking data not available"
          />
        </div>

        {/* Secondary metrics */}
        <div className="grid grid-cols-3 gap-2 pt-1">
          <MetricCell
            value={fmt.pe(pick.pe_ratio)}
            label="P/E"
            nullReason="P/E ratio unavailable (negative earnings or no data)"
          />
          <MetricCell
            value={pick.piotroski_f_score != null ? `${pick.piotroski_f_score}/9` : null}
            label="F-Score"
            nullReason="Piotroski F-Score requires full financial statements"
          />
          <MetricCell
            value={pick.roe != null ? `${(pick.roe * 100).toFixed(1)}%` : null}
            label="ROE"
            nullReason="Return on equity data not available"
          />
        </div>

        {/* Why selected — collapsible */}
        <div className="border-t border-gray-100 pt-3 mt-auto">
          <button
            onClick={() => setExpanded(v => !v)}
            className="w-full flex items-center justify-between text-[11px] font-semibold text-blue-600 hover:text-blue-800 transition-colors"
          >
            <span className="flex items-center gap-1">
              <Info className="w-3 h-3" />
              Why selected: {summary}
            </span>
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          {expanded && (
            <p className="text-[11px] text-gray-500 leading-relaxed mt-2 bg-blue-50 rounded-lg px-3 py-2">
              {details}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Disclaimer ────────────────────────────────────────────────────────────────

function Disclaimer() {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex gap-3">
      <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
      <div className="text-xs text-amber-800 leading-relaxed space-y-1">
        <p className="font-semibold text-amber-900">Not financial advice — algorithmic ranking only</p>
        <p>
          The Top 5 Strategy is a quantitative screening tool that ranks ASX 200 stocks by composite
          factor scores. It does <strong>not</strong> constitute investment advice, a recommendation to buy or
          sell, or a guarantee of future returns. Past rankings are not indicative of future performance.
        </p>
        <p>
          Stocks may score highly due to recent momentum that reverses quickly. Always conduct your own
          research, consider your personal financial situation, and seek professional advice before
          making any investment decisions. <strong>Always do your own research (DYOR).</strong>
        </p>
      </div>
    </div>
  )
}

// ── Monthly performance tracker ───────────────────────────────────────────────

function PerformanceTracker({ history }: { history: HistoryMonth[] }) {
  if (history.length < 2) return null

  // ASX 200 approximate monthly benchmarks (proxy — shown as reference)
  // In a real implementation these would come from the backend
  const rows = history.map(({ pick_month, picks }) => {
    const avg3m = avgReturn3m(picks)
    const avgScore = picks.reduce((s, p) => s + (p.composite_score ?? 0), 0) / Math.max(picks.length, 1)
    return { pick_month, avg3m, avgScore, picks }
  })

  return (
    <section>
      <div className="flex items-center gap-2 mb-4">
        <BarChart2 className="w-4 h-4 text-blue-500" />
        <h2 className="text-base font-bold text-gray-900">Monthly Strategy Performance</h2>
        <span className="text-xs text-gray-400 ml-1">— avg 3M return of each month's picks</span>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        {/* Bar chart */}
        <div className="p-5 border-b border-gray-100">
          <div className="flex items-end gap-1.5 h-24">
            {rows.slice(-12).map(({ pick_month, avg3m }) => {
              const pct   = avg3m != null ? avg3m * 100 : null
              const barH  = pct != null ? Math.min(100, Math.abs(pct) * 4) : 4
              const isPos = pct == null || pct >= 0
              return (
                <div key={pick_month} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                  <div className="w-full flex flex-col justify-end" style={{ height: '80px' }}>
                    <div
                      className={cn('w-full rounded-t-sm transition-all', isPos ? 'bg-emerald-400' : 'bg-red-400')}
                      style={{ height: `${Math.max(3, barH)}%` }}
                    />
                  </div>
                  <span className="text-[8px] text-gray-400 truncate w-full text-center">
                    {fmt.monthShort(pick_month)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="text-left px-4 py-2.5 font-semibold text-gray-600">Month</th>
                <th className="text-left px-3 py-2.5 font-semibold text-gray-600">Avg Score</th>
                <th className="text-left px-3 py-2.5 font-semibold text-gray-600">Avg 3M Ret</th>
                <th className="text-left px-3 py-2.5 font-semibold text-gray-600 hidden sm:table-cell">Picks</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {rows.map(({ pick_month, avg3m, avgScore, picks }) => (
                <tr key={pick_month} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 font-medium text-gray-700 whitespace-nowrap">
                    {fmt.monthShort(pick_month)}
                  </td>
                  <td className="px-3 py-2.5 text-gray-600">
                    {avgScore.toFixed(1)}
                  </td>
                  <td className={cn('px-3 py-2.5 font-semibold', retColor(avg3m))}>
                    {avg3m != null ? `${avg3m >= 0 ? '+' : ''}${(avg3m * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-3 py-2.5 hidden sm:table-cell">
                    <div className="flex gap-1 flex-wrap">
                      {picks.sort((a,b) => a.rank - b.rank).map(p => (
                        <Link key={p.asx_code} href={`/company/${p.asx_code}`}
                          className="text-[10px] font-semibold text-gray-500 hover:text-blue-600 transition-colors">
                          {p.asx_code}
                        </Link>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2.5 bg-gray-50 border-t border-gray-100">
          <p className="text-[10px] text-gray-400">
            Avg 3M Ret = average 3-month return of that month's picks as at the time of data capture.
            This is not a backtest. Past performance does not guarantee future results.
          </p>
        </div>
      </div>
    </section>
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
                  <th key={r} className="text-left px-3 py-3 font-semibold text-gray-700 text-xs">
                    <span className={cn('inline-flex items-center justify-center w-5 h-5 rounded-full text-[9px] font-bold text-white bg-gradient-to-br', RANK_COLOURS[r-1])}>
                      {r}
                    </span>
                  </th>
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
                          <Link href={`/company/${p.asx_code}`} className="group flex flex-col">
                            <span className="font-semibold text-gray-900 group-hover:text-blue-600 text-xs">
                              {p.asx_code}
                            </span>
                            <span className={cn('text-[10px]', retColor(p.return_3m))}>
                              {p.return_3m != null
                                ? `${p.return_3m >= 0 ? '+' : ''}${(p.return_3m * 100).toFixed(1)}%`
                                : fmt.score(p.composite_score) ?? '—'}
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
        <div className="px-4 py-2 bg-gray-50 border-t border-gray-100">
          <p className="text-[10px] text-gray-400">Sub-value shows 3M return where available, otherwise composite score.</p>
        </div>
      </div>
    </section>
  )
}

// ── How it works ──────────────────────────────────────────────────────────────

function HowItWorks() {
  const factors = [
    { icon: TrendingUp,  colour: 'text-blue-600 bg-blue-50',     label: 'Momentum',  desc: 'Price returns (1M, 3M, 6M), RSI and ADX trend strength'                    },
    { icon: Shield,      colour: 'text-emerald-600 bg-emerald-50',label: 'Quality',   desc: 'Piotroski F-Score, ROE, ROCE, Altman Z-Score, profit margins'              },
    { icon: Star,        colour: 'text-amber-600 bg-amber-50',    label: 'Value',     desc: 'P/E, P/B, EV/EBITDA, FCF yield, Price-to-Sales vs sector'                  },
    { icon: DollarSign,  colour: 'text-purple-600 bg-purple-50',  label: 'Income',    desc: 'Grossed-up yield, franking %, dividend consistency and payout coverage'     },
    { icon: BarChart2,   colour: 'text-rose-600 bg-rose-50',      label: 'Growth',    desc: 'Revenue & EPS growth (1Y, 3Y CAGR, half-yearly acceleration)'              },
  ]
  return (
    <section className="bg-white border border-gray-200 rounded-2xl p-6">
      <div className="flex items-start gap-2 mb-5">
        <Info className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
        <div>
          <h2 className="text-base font-bold text-gray-900">How the ranking works</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Each ASX 200 stock is scored on 5 equal-weighted factors using percentile ranks (0–100) within the index.
            The composite score is the average of all 5 factors. Higher = better across all dimensions.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-5 gap-4">
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
      <div className="mt-5 pt-4 border-t border-gray-100">
        <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-[11px] text-gray-500 mb-3">
          <span>📊 Universe: ASX 200</span>
          <span>📅 Refreshed: Monthly (1st of each month)</span>
          <span>⚖️ Weighting: Equal — 5 × 20%</span>
          <span>📐 Method: Percentile rank within index</span>
        </div>
        <p className="text-[11px] text-gray-400 leading-relaxed">
          <strong className="text-gray-500">Missing values (—):</strong> A dash means the required data
          is unavailable for that stock — typically because the company has insufficient trading history,
          negative earnings (P/E), has not paid dividends (yield), or lacks full financial statements
          (F-Score, ROE). Missing scores are treated as neutral in the composite calculation.
        </p>
      </div>
    </section>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

function Top5Content() {
  const [current, setCurrent] = useState<CurrentResponse | null>(null)
  const [history, setHistory] = useState<HistoryMonth[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

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
        <p className="text-sm text-gray-400 mt-1">The strategy runs on the 1st of each month. Check back soon.</p>
      </div>
    )
  }

  const { pick_month, picks, total_months } = current

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-10">

      {/* Current picks header */}
      <section>
        <div className="flex items-center justify-between mb-4">
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
              Highest composite-scored ASX 200 stocks across all 5 factors
            </p>
          </div>
          <Link href="/screener" className="hidden sm:flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium">
            Full Screener <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Disclaimer — prominent, above cards */}
        <Disclaimer />

        {/* Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mt-5">
          {picks.map(p => <PickCard key={p.asx_code} pick={p} />)}
        </div>
      </section>

      {/* How it works */}
      <HowItWorks />

      {/* Monthly performance tracker */}
      <PerformanceTracker history={history} />

      {/* History table */}
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
            <div className="flex-1">
              <h1 className="text-2xl font-bold text-gray-900">ASX Top 5 Strategy</h1>
              <p className="text-gray-500 text-sm mt-0.5">
                Monthly algo-ranked top 5 from the ASX 200 — scored across momentum, quality,
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
