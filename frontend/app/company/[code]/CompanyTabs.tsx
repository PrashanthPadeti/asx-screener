'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  getCompanyOverview, getCompanyFinancials, getCompanyPrices,
  getCompanyDividends, getCompanyPeers, getCompanyHalfYearly,
  type CompanyOverview, type FinancialsResponse, type PricesResponse,
  type DividendsResponse, type PeersResponse, type HalfYearlyResponse,
} from '@/lib/api'
import {
  formatPrice, formatMarketCap, formatVolume,
  formatRatio, formatRatioChange, formatPctRaw, formatNumber,
} from '@/lib/utils'
import { TrendingUp, TrendingDown, Minus, TrendingUp as TrendUp } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────

type Tab = 'overview' | 'financials' | 'technicals' | 'dividends' | 'peers' | 'ai' | 'documents'
type FinancialPeriod = 'annual' | 'halfyearly'

interface MetricRowProps {
  label: string
  value: string
  sub?: string
  highlight?: 'green' | 'red' | 'neutral'
}

// ── Helpers ───────────────────────────────────────────────────

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

function fmtX(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'   // 0 means not computed, not a real 0x ratio
  return `${v.toFixed(1)}x`
}

function fmtM(v: number | null | undefined): string {
  // v is in AUD millions (financials.annual_pnl, balance_sheet, screener.universe financial cols)
  // Examples: 50 → "$50M", 50_000 → "$50.0B", 5_000_000 → "$5.00T"
  if (v == null) return '—'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}T`
  if (abs >= 1_000)     return `${sign}$${(abs / 1_000).toFixed(1)}B`
  if (abs >= 1)         return `${sign}$${abs.toFixed(0)}M`
  return `${sign}$${(abs * 1_000).toFixed(0)}K`
}

function signClass(v: number | null | undefined): string {
  if (v == null) return 'text-gray-500'
  return v >= 0 ? 'text-green-600' : 'text-red-600'
}

function signedPct(v: number | null | undefined, decimals = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(decimals)}%`
}

// ── Sub-components ────────────────────────────────────────────

function MetricRow({ label, value, sub, highlight }: MetricRowProps) {
  const valueClass =
    highlight === 'green' ? 'text-green-700 font-semibold' :
    highlight === 'red'   ? 'text-red-600 font-semibold' :
    'text-gray-900 font-medium'

  return (
    <div className="flex items-baseline justify-between py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className={`text-sm text-right ${valueClass}`}>
        {value}
        {sub && <span className="text-xs text-gray-400 ml-1">{sub}</span>}
      </span>
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">{title}</h3>
      {children}
    </div>
  )
}

function LoadingCard() {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 animate-pulse">
      <div className="h-3 bg-gray-100 rounded w-1/3 mb-4" />
      {[1, 2, 3, 4].map(i => (
        <div key={i} className="flex justify-between py-1.5">
          <div className="h-3 bg-gray-100 rounded w-2/5" />
          <div className="h-3 bg-gray-100 rounded w-1/4" />
        </div>
      ))}
    </div>
  )
}

// ── Composite Score Meter ─────────────────────────────────────

interface FactorScore {
  label: string
  key: keyof CompanyOverview
  color: string
}

const FACTOR_SCORES: FactorScore[] = [
  { label: 'Value',    key: 'value_score',    color: 'bg-blue-500'   },
  { label: 'Quality',  key: 'quality_score',  color: 'bg-purple-500' },
  { label: 'Growth',   key: 'growth_score',   color: 'bg-emerald-500'},
  { label: 'Momentum', key: 'momentum_score', color: 'bg-orange-500' },
  { label: 'Income',   key: 'income_score',   color: 'bg-yellow-500' },
]

function scoreColor(score: number): string {
  if (score >= 75) return 'text-green-600'
  if (score >= 50) return 'text-blue-600'
  if (score >= 25) return 'text-orange-500'
  return 'text-red-500'
}

function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 75 ? 'bg-green-500' :
    score >= 50 ? 'bg-blue-500'  :
    score >= 25 ? 'bg-orange-400': 'bg-red-400'
  return (
    <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
      <div className={`h-1.5 rounded-full transition-all ${color}`} style={{ width: `${score}%` }} />
    </div>
  )
}

function CompositeScoreMeter({ o }: { o: CompanyOverview }) {
  const composite = o.composite_score
  if (composite == null) return null

  const radius = 40
  const circumference = 2 * Math.PI * radius
  const dash = (composite / 100) * circumference
  const gap  = circumference - dash

  const strokeColor =
    composite >= 75 ? '#16a34a' :  // green-600
    composite >= 50 ? '#2563eb' :  // blue-600
    composite >= 25 ? '#ea580c' :  // orange-600
    '#dc2626'                       // red-600

  const label =
    composite >= 75 ? 'Strong' :
    composite >= 50 ? 'Moderate' :
    composite >= 25 ? 'Weak' :
    'Poor'

  return (
    <Card title="Composite Factor Score">
      <div className="flex items-center gap-6">
        {/* Donut gauge */}
        <div className="relative shrink-0">
          <svg width="100" height="100" viewBox="0 0 100 100" className="-rotate-90">
            <circle cx="50" cy="50" r={radius} fill="none" stroke="#f3f4f6" strokeWidth="10" />
            <circle
              cx="50" cy="50" r={radius}
              fill="none"
              stroke={strokeColor}
              strokeWidth="10"
              strokeDasharray={`${dash} ${gap}`}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-2xl font-bold ${scoreColor(composite)}`}>{composite}</span>
            <span className="text-xs text-gray-400">{label}</span>
          </div>
        </div>

        {/* Factor breakdown */}
        <div className="flex-1 space-y-2">
          {FACTOR_SCORES.map(({ label: fl, key }) => {
            const val = o[key] as number | null
            if (val == null) return null
            return (
              <div key={key}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-500">{fl}</span>
                  <span className={`font-medium ${scoreColor(val)}`}>{val}</span>
                </div>
                <ScoreBar score={val} />
              </div>
            )
          })}
        </div>
      </div>
      <p className="text-xs text-gray-400 mt-3">
        Percentile rank 0–100 vs all ASX stocks. Higher = better relative standing.
      </p>
    </Card>
  )
}

// ── Pros / Cons Engine ────────────────────────────────────────

function buildSignals(o: CompanyOverview): { pros: string[]; cons: string[] } {
  const pros: string[] = []
  const cons: string[] = []

  // Dividends
  if (o.dividend_yield != null && o.dividend_yield > 0.04)
    pros.push(`Dividend yield ${formatRatio(o.dividend_yield)} — above market average`)
  if (o.franking_pct === 100)
    pros.push('Fully franked dividends — 100% tax credit for Australian investors')
  else if (o.franking_pct != null && o.franking_pct > 50)
    pros.push(`${formatPctRaw(o.franking_pct, 0)} franked dividends — partial tax credit`)
  if (o.grossed_up_yield != null && o.grossed_up_yield > 0.06)
    pros.push(`Grossed-up yield ${formatRatio(o.grossed_up_yield)} — attractive after-tax income`)
  if (o.dividend_consecutive_yrs != null && o.dividend_consecutive_yrs >= 5)
    pros.push(`${o.dividend_consecutive_yrs} consecutive years of dividends`)

  // Quality
  if (o.piotroski_f_score != null && o.piotroski_f_score >= 7)
    pros.push(`Strong Piotroski F-Score ${o.piotroski_f_score}/9 — financially healthy`)
  if (o.piotroski_f_score != null && o.piotroski_f_score <= 2)
    cons.push(`Weak Piotroski F-Score ${o.piotroski_f_score}/9 — financial health concerns`)

  // Profitability
  if (o.roe != null && o.roe > 0.15)
    pros.push(`ROE ${formatRatio(o.roe)} — strong return on equity`)
  if (o.net_margin != null && o.net_margin > 0.15)
    pros.push(`Net margin ${formatRatio(o.net_margin)} — highly profitable`)
  if (o.net_margin != null && o.net_margin < 0)
    cons.push('Company is currently operating at a net loss')

  // Balance sheet
  if (o.debt_to_equity != null && o.debt_to_equity >= 0 && o.debt_to_equity < 0.3)
    pros.push(`Low debt-to-equity ${fmtX(o.debt_to_equity)} — strong balance sheet`)
  if (o.debt_to_equity != null && o.debt_to_equity > 2)
    cons.push(`High debt-to-equity ${fmtX(o.debt_to_equity)} — elevated leverage risk`)
  if (o.current_ratio != null && o.current_ratio > 2)
    pros.push(`Strong current ratio ${fmtX(o.current_ratio)} — good short-term liquidity`)
  if (o.current_ratio != null && o.current_ratio < 1)
    cons.push(`Current ratio ${fmtX(o.current_ratio)} below 1 — near-term liquidity risk`)

  // Valuation
  if (o.pe_ratio != null && o.pe_ratio > 0 && o.pe_ratio > 40)
    cons.push(`High P/E ${fmtX(o.pe_ratio)} — premium valuation`)
  if (o.analyst_upside != null && o.analyst_upside > 0.15)
    pros.push(`Analyst consensus target ${signedPct(o.analyst_upside)} above current price`)
  if (o.analyst_upside != null && o.analyst_upside < -0.10)
    cons.push(`Analyst consensus target ${signedPct(o.analyst_upside)} below current price`)

  // Returns
  if (o.return_1y != null && o.return_1y > 0.25)
    pros.push(`Up ${(o.return_1y * 100).toFixed(0)}% in the past year`)
  if (o.return_1y != null && o.return_1y < -0.20)
    cons.push(`Down ${Math.abs(o.return_1y * 100).toFixed(0)}% in the past year`)

  // Technicals
  if (o.rsi_14 != null && o.rsi_14 < 35)
    pros.push(`RSI ${o.rsi_14.toFixed(0)} — potentially oversold / good entry point`)
  if (o.rsi_14 != null && o.rsi_14 > 70)
    cons.push(`RSI ${o.rsi_14.toFixed(0)} — potentially overbought / extended`)

  // Short interest
  if (o.short_pct != null && o.short_pct > 5)
    cons.push(`${formatPctRaw(o.short_pct)} short interest — elevated bearish bets`)

  // Growth
  if (o.revenue_growth_1y != null && o.revenue_growth_1y > 0.1)
    pros.push(`Revenue grew ${(o.revenue_growth_1y * 100).toFixed(0)}% last year`)
  if (o.revenue_growth_1y != null && o.revenue_growth_1y < -0.05)
    cons.push(`Revenue declined ${Math.abs(o.revenue_growth_1y * 100).toFixed(0)}% last year`)

  return { pros, cons }
}

// ── Overview Tab ──────────────────────────────────────────────

function OverviewTab({ o }: { o: CompanyOverview }) {
  // Use DB-computed pros/cons when available; fall back to client-side engine
  const hasDatabaseSignals = (o.pros?.length ?? 0) > 0 || (o.cons?.length ?? 0) > 0
  const { pros, cons } = hasDatabaseSignals
    ? { pros: o.pros ?? [], cons: o.cons ?? [] }
    : buildSignals(o)

  const pos52w = o.high_52w != null && o.low_52w != null && o.price != null
    ? ((o.price - o.low_52w) / (o.high_52w - o.low_52w)) * 100
    : null

  return (
    <div className="space-y-4">

      {/* Price summary */}
      <Card title="Price Summary">
        <div className="flex flex-wrap gap-6 mb-3">
          <div>
            <span className="text-3xl font-bold text-gray-900">
              {o.price != null ? `$${o.price.toFixed(3)}` : '—'}
            </span>
          </div>
          <div className="flex flex-col justify-center gap-0.5">
            <span className="text-xs text-gray-400">Market Cap</span>
            <span className="font-semibold">{formatMarketCap(o.market_cap)}</span>
          </div>
          <div className="flex flex-col justify-center gap-0.5">
            <span className="text-xs text-gray-400">Volume</span>
            <span className="font-semibold">{formatVolume(o.volume)}</span>
          </div>
          <div className="flex flex-col justify-center gap-0.5">
            <span className="text-xs text-gray-400">Avg Vol (20D)</span>
            <span className="font-semibold">{formatVolume(o.avg_volume_20d)}</span>
          </div>
          {o.price_date && (
            <div className="flex flex-col justify-center gap-0.5">
              <span className="text-xs text-gray-400">As at</span>
              <span className="font-semibold">{o.price_date}</span>
            </div>
          )}
        </div>

        {/* 52-week range */}
        {o.high_52w != null && o.low_52w != null && (
          <div>
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>52W Low: ${o.low_52w.toFixed(2)}</span>
              <span>52W High: ${o.high_52w.toFixed(2)}</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2 relative">
              <div
                className="absolute h-4 w-1 bg-blue-600 rounded-full -top-1"
                style={{ left: `${Math.max(0, Math.min(100, pos52w ?? 50))}%` }}
              />
              <div className="h-2 bg-gradient-to-r from-red-200 via-yellow-200 to-green-200 rounded-full" />
            </div>
          </div>
        )}
      </Card>

      {/* Composite Score Meter */}
      {o.composite_score != null && <CompositeScoreMeter o={o} />}

      {/* 3-column metrics grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Valuation */}
        <Card title="Valuation">
          <MetricRow label="P/E Ratio"        value={fmtX(o.pe_ratio)} />
          <MetricRow label="Forward P/E"      value={fmtX(o.forward_pe)} />
          <MetricRow label="Price / Book"     value={fmtX(o.price_to_book)} />
          <MetricRow label="Price / Sales"    value={fmtX(o.price_to_sales)} />
          <MetricRow label="EV / EBITDA"      value={fmtX(o.ev_to_ebitda)} />
          <MetricRow label="PEG Ratio"        value={fmtX(o.peg_ratio)} />
          <MetricRow label="Price / FCF"      value={fmtX(o.price_to_fcf)} />
          <MetricRow label="FCF Yield"        value={formatRatio(o.fcf_yield)} />
          {o.graham_number != null && (
            <MetricRow label="Graham Number" value={`$${o.graham_number.toFixed(2)}`} />
          )}
        </Card>

        {/* Dividends */}
        <Card title="Dividends">
          <MetricRow
            label="Dividend Yield"
            value={formatRatio(o.dividend_yield)}
            highlight={o.dividend_yield != null && o.dividend_yield > 0.04 ? 'green' : 'neutral'}
          />
          <MetricRow
            label="Grossed-Up Yield"
            value={formatRatio(o.grossed_up_yield)}
            highlight={o.grossed_up_yield != null && o.grossed_up_yield > 0.06 ? 'green' : 'neutral'}
          />
          <MetricRow
            label="Franking"
            value={o.franking_pct != null ? `${o.franking_pct.toFixed(0)}%` : '—'}
            highlight={
              o.franking_pct === 100 ? 'green' :
              o.franking_pct != null && o.franking_pct > 0 ? 'neutral' : 'neutral'
            }
          />
          <MetricRow label="DPS (TTM)"          value={o.dps_ttm != null ? `$${o.dps_ttm.toFixed(3)}` : '—'} />
          <MetricRow label="Payout Ratio"        value={formatRatio(o.payout_ratio)} />
          <MetricRow label="Ex-Dividend Date"    value={o.ex_div_date ?? '—'} />
          <MetricRow label="Consec. Div. Years"  value={o.dividend_consecutive_yrs != null ? String(o.dividend_consecutive_yrs) : '—'} />
          <MetricRow label="Div. CAGR (3Y)"      value={formatRatio(o.dividend_cagr_3y)} />
        </Card>

        {/* Profitability */}
        <Card title="Profitability">
          <MetricRow label="Gross Margin"     value={formatRatio(o.gross_margin)} />
          <MetricRow label="EBITDA Margin"    value={formatRatio(o.ebitda_margin)} />
          <MetricRow label="Net Margin"       value={formatRatio(o.net_margin)}
            highlight={o.net_margin != null ? (o.net_margin > 0 ? 'neutral' : 'red') : 'neutral'} />
          <MetricRow label="Operating Margin" value={formatRatio(o.operating_margin)} />
          <MetricRow label="ROE"              value={formatRatio(o.roe)}
            highlight={o.roe != null && o.roe > 0.15 ? 'green' : 'neutral'} />
          <MetricRow label="ROA"              value={formatRatio(o.roa)} />
          <MetricRow label="ROCE"             value={formatRatio(o.roce)} />
          <MetricRow label="Avg ROE (3Y)"     value={formatRatio(o.avg_roe_3y)} />
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Growth */}
        <Card title="Growth">
          <MetricRow label="Revenue (1Y)"     value={signedPct(o.revenue_growth_1y)}
            highlight={o.revenue_growth_1y != null ? (o.revenue_growth_1y > 0 ? 'green' : 'red') : 'neutral'} />
          <MetricRow label="Revenue CAGR (3Y)" value={signedPct(o.revenue_growth_3y_cagr)} />
          <MetricRow label="Revenue CAGR (5Y)" value={signedPct(o.revenue_cagr_5y)} />
          <MetricRow label="Earnings (1Y)"    value={signedPct(o.earnings_growth_1y)}
            highlight={o.earnings_growth_1y != null ? (o.earnings_growth_1y > 0 ? 'green' : 'red') : 'neutral'} />
          <MetricRow label="EPS CAGR (3Y)"    value={signedPct(o.eps_growth_3y_cagr)} />
          {o.revenue_growth_hoh != null && (
            <MetricRow label="Revenue HoH ★"  value={signedPct(o.revenue_growth_hoh)}
              highlight={o.revenue_growth_hoh > 0 ? 'green' : 'red'} />
          )}
          {o.net_income_growth_hoh != null && (
            <MetricRow label="Net Income HoH ★" value={signedPct(o.net_income_growth_hoh)}
              highlight={o.net_income_growth_hoh > 0 ? 'green' : 'red'} />
          )}
          {o.eps_growth_hoh != null && (
            <MetricRow label="EPS HoH ★"      value={signedPct(o.eps_growth_hoh)}
              highlight={o.eps_growth_hoh > 0 ? 'green' : 'red'} />
          )}
        </Card>

        {/* Balance Sheet */}
        <Card title="Balance Sheet">
          <MetricRow label="Debt / Equity"     value={fmtX(o.debt_to_equity)}
            highlight={
              o.debt_to_equity == null ? 'neutral' :
              o.debt_to_equity < 0.3 ? 'green' :
              o.debt_to_equity > 2 ? 'red' : 'neutral'
            } />
          <MetricRow label="Current Ratio"     value={fmtX(o.current_ratio)}
            highlight={
              o.current_ratio == null ? 'neutral' :
              o.current_ratio > 2 ? 'green' :
              o.current_ratio < 1 ? 'red' : 'neutral'
            } />
          <MetricRow label="Net Debt"          value={fmtM(o.net_debt)} />
          <MetricRow label="Total Debt"        value={fmtM(o.total_debt)} />
          <MetricRow label="Total Assets"      value={fmtM(o.total_assets)} />
          <MetricRow label="Total Equity"      value={fmtM(o.total_equity)} />
          <MetricRow label="Book Value / Sh"   value={o.book_value_per_share != null ? `$${o.book_value_per_share.toFixed(2)}` : '—'} />
          <MetricRow label="Cash"              value={fmtM(o.cash)} />
        </Card>

        {/* Quality */}
        <Card title="Quality & Ownership">
          {o.piotroski_f_score != null && (
            <MetricRow
              label="Piotroski F-Score"
              value={`${o.piotroski_f_score} / 9`}
              highlight={o.piotroski_f_score >= 7 ? 'green' : o.piotroski_f_score <= 2 ? 'red' : 'neutral'}
            />
          )}
          {o.altman_z_score != null && (
            <MetricRow
              label="Altman Z-Score"
              value={o.altman_z_score.toFixed(2)}
              highlight={o.altman_z_score > 2.99 ? 'green' : o.altman_z_score < 1.81 ? 'red' : 'neutral'}
              sub={o.altman_z_score > 2.99 ? 'safe' : o.altman_z_score < 1.81 ? 'distress' : 'grey'}
            />
          )}
          <MetricRow
            label="Short Interest"
            value={o.short_pct != null ? `${o.short_pct.toFixed(1)}%` : '—'}
            sub={
              o.short_interest_chg_1w != null
                ? `${o.short_interest_chg_1w >= 0 ? '+' : ''}${o.short_interest_chg_1w.toFixed(2)}pp WoW`
                : undefined
            }
            highlight={o.short_pct != null && o.short_pct > 5 ? 'red' : 'neutral'}
          />
          <MetricRow label="Insiders"          value={o.percent_insiders != null ? `${o.percent_insiders.toFixed(1)}%` : '—'} />
          <MetricRow label="Institutions"      value={o.percent_institutions != null ? `${o.percent_institutions.toFixed(1)}%` : '—'} />
          {o.cfo_fy0 != null && <MetricRow label="CFO (FY0)"    value={fmtM(o.cfo_fy0)} />}
          {o.capex_fy0 != null && <MetricRow label="Capex (FY0)" value={fmtM(o.capex_fy0)} />}
          {o.fcf_fy0 != null && (
            <MetricRow label="FCF (FY0)"       value={fmtM(o.fcf_fy0)}
              highlight={o.fcf_fy0 > 0 ? 'green' : 'red'} />
          )}
        </Card>
      </div>

      {/* Returns */}
      <Card title="Price Returns">
        <div className="grid grid-cols-4 md:grid-cols-8 gap-3">
          {([
            ['1W',  o.return_1w],
            ['1M',  o.return_1m],
            ['3M',  o.return_3m],
            ['6M',  o.return_6m],
            ['YTD', o.return_ytd],
            ['1Y',  o.return_1y],
            ['3Y',  o.return_3y],
            ['5Y',  o.return_5y],
          ] as [string, number | null][]).map(([label, val]) => (
            <div key={label} className="text-center">
              <div className="text-xs text-gray-400 mb-1">{label}</div>
              <div className={`text-sm font-semibold ${signClass(val)}`}>
                {signedPct(val)}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Analyst */}
      {o.analyst_rating && (
        <Card title="Analyst Consensus">
          <div className="flex items-center gap-6 flex-wrap">
            <div>
              <span className="text-xs text-gray-400 block mb-0.5">Rating</span>
              <span className="font-bold text-gray-900 text-lg uppercase">{o.analyst_rating}</span>
            </div>
            {o.analyst_target_price && (
              <div>
                <span className="text-xs text-gray-400 block mb-0.5">Target Price</span>
                <span className="font-semibold text-gray-900">${o.analyst_target_price.toFixed(2)}</span>
              </div>
            )}
            {o.analyst_upside != null && (
              <div>
                <span className="text-xs text-gray-400 block mb-0.5">Upside</span>
                <span className={`font-semibold ${signClass(o.analyst_upside)}`}>
                  {signedPct(o.analyst_upside)}
                </span>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Pros & Cons */}
      {(pros.length > 0 || cons.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {pros.length > 0 && (
            <Card title="Strengths">
              <ul className="space-y-2">
                {pros.map((p, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-green-500 mt-0.5 shrink-0">✓</span>
                    {p}
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {cons.length > 0 && (
            <Card title="Risks">
              <ul className="space-y-2">
                {cons.map((c, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-red-500 mt-0.5 shrink-0">✕</span>
                    {c}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

// ── Financials Tab ────────────────────────────────────────────

function AnnualTable({ financials }: { financials: FinancialsResponse }) {
  const years = [...financials.years].reverse()

  type ARow = { label: string; key: string; fmt: (v: number | null) => string }

  const pnlRows: ARow[] = [
    { label: 'Revenue',       key: 'revenue',      fmt: fmtM },
    { label: 'Gross Profit',  key: 'gross_profit', fmt: fmtM },
    { label: 'EBITDA',        key: 'ebitda',       fmt: fmtM },
    { label: 'EBIT',          key: 'ebit',         fmt: fmtM },
    { label: 'Net Profit',    key: 'net_profit',   fmt: fmtM },
    { label: 'EPS',           key: 'eps',          fmt: v => v != null ? `$${v.toFixed(3)}` : '—' },
    { label: 'DPS',           key: 'dps',          fmt: v => v != null ? `$${v.toFixed(3)}` : '—' },
  ]
  const marginRows: ARow[] = [
    { label: 'Gross Margin',  key: 'gpm',          fmt: formatRatio },
    { label: 'EBITDA Margin', key: 'ebitda_margin',fmt: formatRatio },
    { label: 'Net Margin',    key: 'npm',          fmt: formatRatio },
  ]
  const bsRows: ARow[] = [
    { label: 'Total Assets',    key: 'total_assets',        fmt: fmtM },
    { label: 'Total Equity',    key: 'total_equity',        fmt: fmtM },
    { label: 'Total Debt',      key: 'total_debt',          fmt: fmtM },
    { label: 'Net Debt',        key: 'net_debt',            fmt: fmtM },
    { label: 'Cash',            key: 'cash_equivalents',    fmt: fmtM },
    { label: 'Book Value / Sh', key: 'book_value_per_share',fmt: v => v != null ? `$${v.toFixed(2)}` : '—' },
    { label: 'Debt / Equity',   key: 'debt_to_equity',      fmt: fmtX },
  ]
  const cfRows: ARow[] = [
    { label: 'Cash From Ops',  key: 'cfo',   fmt: fmtM },
    { label: 'Capex',          key: 'capex', fmt: fmtM },
    { label: 'Free Cash Flow', key: 'fcf',   fmt: fmtM },
  ]

  const TableSection = ({ title, rows }: { title: string; rows: ARow[] }) => (
    <>
      <tr>
        <td colSpan={years.length + 1} className="pt-4 pb-1">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{title}</span>
        </td>
      </tr>
      {rows.map(row => (
        <tr key={row.label} className="hover:bg-gray-50">
          <td className="py-1.5 pr-4 text-sm text-gray-600 whitespace-nowrap">{row.label}</td>
          {years.map(yr => (
            <td key={yr.fiscal_year} className="py-1.5 text-sm text-right font-medium text-gray-900 pl-4">
              {row.fmt((yr as unknown as Record<string, number | null>)[row.key])}
            </td>
          ))}
        </tr>
      ))}
    </>
  )

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left min-w-[500px]">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-xs text-gray-400 font-medium pb-2 pr-4">Metric</th>
            {years.map(yr => (
              <th key={yr.fiscal_year} className="text-xs text-gray-700 font-semibold pb-2 pl-4 text-right">
                FY{yr.fiscal_year}
                {yr.period_end_date && (
                  <span className="block font-normal text-gray-400">
                    {yr.period_end_date.slice(0, 7)}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          <TableSection title="Income Statement (AUD)" rows={pnlRows} />
          <TableSection title="Margins" rows={marginRows} />
          <TableSection title="Balance Sheet (AUD)" rows={bsRows} />
          <TableSection title="Cash Flow (AUD)" rows={cfRows} />
        </tbody>
      </table>
    </div>
  )
}

function HalfYearlyTable({ halfYearly }: { halfYearly: HalfYearlyResponse }) {
  const periods = [...halfYearly.periods].reverse()  // chronological

  type HRow = { label: string; key: string; fmt: (v: number | null) => string }
  const pnlRows: HRow[] = [
    { label: 'Revenue',       key: 'revenue',      fmt: fmtM },
    { label: 'Gross Profit',  key: 'gross_profit', fmt: fmtM },
    { label: 'EBITDA',        key: 'ebitda',       fmt: fmtM },
    { label: 'EBIT',          key: 'ebit',         fmt: fmtM },
    { label: 'Net Profit',    key: 'net_profit',   fmt: fmtM },
    { label: 'EPS',           key: 'eps',          fmt: v => v != null ? `$${v.toFixed(3)}` : '—' },
    { label: 'DPS',           key: 'dps',          fmt: v => v != null ? `$${v.toFixed(3)}` : '—' },
    { label: 'DPS Franking',  key: 'dps_franking_pct', fmt: v => v != null ? `${v.toFixed(0)}%` : '—' },
  ]
  const marginRows: HRow[] = [
    { label: 'Gross Margin',  key: 'gpm',          fmt: formatRatio },
    { label: 'EBIT Margin',   key: 'ebitda_margin',fmt: formatRatio },
    { label: 'Net Margin',    key: 'npm',          fmt: formatRatio },
  ]
  const signedPctFmt = (v: number | null) => {
    if (v == null) return '—'
    const pct = v * 100
    return <span className={pct >= 0 ? 'text-green-600' : 'text-red-600'}>{pct >= 0 ? '+' : ''}{pct.toFixed(1)}%</span>
  }
  const growthRows: HRow[] = [
    { label: 'Revenue HoH',     key: 'revenue_growth_hoh',      fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
    { label: 'Revenue YoY',     key: 'revenue_growth_yoy',      fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
    { label: 'Net Profit HoH',  key: 'net_profit_growth_hoh',   fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
    { label: 'EPS HoH',         key: 'eps_growth_hoh',          fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
    { label: 'EPS YoY',         key: 'eps_growth_yoy',          fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
  ]
  void signedPctFmt // suppress unused warning

  const TableSection = ({ title, rows }: { title: string; rows: HRow[] }) => (
    <>
      <tr>
        <td colSpan={periods.length + 1} className="pt-4 pb-1">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{title}</span>
        </td>
      </tr>
      {rows.map(row => (
        <tr key={row.label} className="hover:bg-gray-50">
          <td className="py-1.5 pr-4 text-sm text-gray-600 whitespace-nowrap">{row.label}</td>
          {periods.map(p => (
            <td key={p.period_label} className="py-1.5 text-sm text-right font-medium text-gray-900 pl-4">
              {row.fmt((p as unknown as Record<string, number | null>)[row.key])}
            </td>
          ))}
        </tr>
      ))}
    </>
  )

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left min-w-[500px]">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-xs text-gray-400 font-medium pb-2 pr-4">Metric</th>
            {periods.map(p => (
              <th key={p.period_label} className="text-xs text-gray-700 font-semibold pb-2 pl-4 text-right">
                {p.period_label}
                {p.period_end_date && (
                  <span className="block font-normal text-gray-400">
                    {p.period_end_date.slice(0, 7)}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          <TableSection title="Income Statement (AUD)" rows={pnlRows} />
          <TableSection title="Margins" rows={marginRows} />
          <TableSection title="Growth Rates" rows={growthRows} />
        </tbody>
      </table>
    </div>
  )
}

function FinancialsTab({
  financials,
  halfYearly,
  period,
  onPeriodChange,
}: {
  financials: FinancialsResponse | null
  halfYearly: HalfYearlyResponse | null
  period: FinancialPeriod
  onPeriodChange: (p: FinancialPeriod) => void
}) {
  const empty = period === 'annual'
    ? (!financials || financials.years.length === 0)
    : (!halfYearly || halfYearly.periods.length === 0)

  return (
    <div className="space-y-3">
      {/* Period toggle */}
      <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5 w-fit">
        {([
          { id: 'annual',     label: 'Annual' },
          { id: 'halfyearly', label: 'Half-Yearly ★' },
        ] as { id: FinancialPeriod; label: string }[]).map(opt => (
          <button
            key={opt.id}
            onClick={() => onPeriodChange(opt.id)}
            className={[
              'px-3 py-1.5 text-xs font-medium rounded-md transition-colors',
              period === opt.id
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700',
            ].join(' ')}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {empty ? (
        <div className="text-center py-12 text-gray-400 text-sm">
          <p className="font-medium text-gray-500 mb-1">
            {period === 'annual'
              ? 'Annual financial statements not yet loaded'
              : 'Half-yearly data not available for this company'}
          </p>
          <p>Financial statements are sourced from company filings and loaded periodically.</p>
        </div>
      ) : period === 'annual' && financials ? (
        <AnnualTable financials={financials} />
      ) : halfYearly ? (
        <HalfYearlyTable halfYearly={halfYearly} />
      ) : null}
    </div>
  )
}

// ── Technicals Tab ────────────────────────────────────────────

function TechnicalsTab({
  o,
  prices,
  pricesLoading,
}: {
  o: CompanyOverview
  prices: PricesResponse | null
  pricesLoading: boolean
}) {
  const rsiClass =
    o.rsi_14 == null ? 'text-gray-400' :
    o.rsi_14 < 35    ? 'text-green-600' :
    o.rsi_14 > 70    ? 'text-red-600'   : 'text-gray-900'

  const rsiLabel =
    o.rsi_14 == null ? '' :
    o.rsi_14 < 30    ? 'Oversold' :
    o.rsi_14 > 70    ? 'Overbought' : 'Neutral'

  const adxLabel =
    o.adx_14 == null ? '' :
    o.adx_14 < 20    ? 'Weak trend' :
    o.adx_14 < 40    ? 'Moderate' : 'Strong trend'

  const macdBullish = o.macd != null && o.macd_signal != null && o.macd > o.macd_signal
  const priceVsSma = (sma: number | null) => {
    if (sma == null || o.price == null) return null
    return ((o.price - sma) / sma) * 100
  }

  // ── Signal badges ───────────────────────────────────────────
  const signals: { label: string; type: 'bull' | 'bear' | 'neutral' }[] = []

  if (o.rsi_14 != null) {
    if (o.rsi_14 < 30)
      signals.push({ label: `RSI Oversold (${o.rsi_14.toFixed(0)})`, type: 'bull' })
    else if (o.rsi_14 > 70)
      signals.push({ label: `RSI Overbought (${o.rsi_14.toFixed(0)})`, type: 'bear' })
  }
  if (o.price != null && o.sma_200 != null) {
    if (o.price > o.sma_200)
      signals.push({ label: 'Above 200-MA', type: 'bull' })
    else
      signals.push({ label: 'Below 200-MA', type: 'bear' })
  }
  if (o.price != null && o.sma_50 != null) {
    if (o.price > o.sma_50)
      signals.push({ label: 'Above 50-MA', type: 'bull' })
    else
      signals.push({ label: 'Below 50-MA', type: 'bear' })
  }
  if (o.macd != null && o.macd_signal != null) {
    if (o.macd > o.macd_signal)
      signals.push({ label: 'MACD Bullish Cross', type: 'bull' })
    else
      signals.push({ label: 'MACD Bearish Cross', type: 'bear' })
  }
  if (o.adx_14 != null && o.adx_14 > 25)
    signals.push({ label: `ADX Trending (${o.adx_14.toFixed(0)})`, type: 'neutral' })

  return (
    <div className="space-y-4">

      {/* Signal badges */}
      {signals.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {signals.map(s => (
            <span
              key={s.label}
              className={[
                'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium',
                s.type === 'bull'    ? 'bg-green-100 text-green-700' :
                s.type === 'bear'    ? 'bg-red-100 text-red-700' :
                                       'bg-yellow-100 text-yellow-700',
              ].join(' ')}
            >
              {s.type === 'bull' ? '▲' : s.type === 'bear' ? '▼' : '◆'} {s.label}
            </span>
          ))}
        </div>
      )}

      {/* Price chart */}
      <Card title="Price History (1 Year)">
        {pricesLoading ? (
          <div className="h-48 flex items-center justify-center text-sm text-gray-400">Loading chart…</div>
        ) : prices && prices.data.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={prices.data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickFormatter={d => d.slice(5)} // "MM-DD"
                interval="preserveStartEnd"
              />
              <YAxis
                domain={['auto', 'auto']}
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickFormatter={v => `$${v.toFixed(2)}`}
                width={60}
              />
              <Tooltip
                formatter={(v) => [`$${Number(v).toFixed(3)}`, 'Close']}
                labelFormatter={l => `Date: ${l}`}
              />
              <Line
                type="monotone"
                dataKey="close"
                stroke="#2563eb"
                dot={false}
                strokeWidth={1.5}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-48 flex items-center justify-center text-sm text-gray-400">
            Price chart data not available
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* Moving averages */}
        <Card title="Price vs Moving Averages">
          {o.price != null ? (
            <>
              {([
                ['SMA 20',  o.sma_20],
                ['SMA 50',  o.sma_50],
                ['SMA 200', o.sma_200],
                ['EMA 20',  o.ema_20],
              ] as [string, number | null][]).map(([label, sma]) => {
                const pct = priceVsSma(sma)
                return (
                  <div key={label} className="flex justify-between items-center py-1.5 border-b border-gray-50 last:border-0">
                    <span className="text-sm text-gray-500">{label}</span>
                    <div className="text-right">
                      <span className="text-sm font-medium text-gray-900 block">
                        {sma != null ? `$${sma.toFixed(3)}` : '—'}
                      </span>
                      {pct != null && (
                        <span className={`text-xs ${pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {pct >= 0 ? '+' : ''}{pct.toFixed(1)}% vs price
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}
            </>
          ) : (
            <p className="text-sm text-gray-400">Price data unavailable</p>
          )}
        </Card>

        {/* Oscillators */}
        <Card title="Oscillators">
          <div className="py-1.5 border-b border-gray-50">
            <div className="flex justify-between mb-1">
              <span className="text-sm text-gray-500">RSI (14)</span>
              <span className={`text-sm font-medium ${rsiClass}`}>
                {o.rsi_14 != null ? o.rsi_14.toFixed(1) : '—'}
                {rsiLabel && <span className="text-xs ml-1 text-gray-400">({rsiLabel})</span>}
              </span>
            </div>
            {o.rsi_14 != null && (
              <div className="w-full bg-gray-100 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full ${o.rsi_14 < 35 ? 'bg-green-400' : o.rsi_14 > 70 ? 'bg-red-400' : 'bg-blue-400'}`}
                  style={{ width: `${Math.min(100, o.rsi_14)}%` }}
                />
              </div>
            )}
          </div>
          <MetricRow
            label="ADX (14)"
            value={o.adx_14 != null ? `${o.adx_14.toFixed(1)}` : '—'}
            sub={adxLabel}
          />
          <div className="flex justify-between items-center py-1.5 border-b border-gray-50">
            <span className="text-sm text-gray-500">MACD</span>
            <div className="text-right">
              <span className="text-sm font-medium text-gray-900 block">
                {o.macd != null ? o.macd.toFixed(4) : '—'}
              </span>
              {o.macd != null && o.macd_signal != null && (
                <span className={`text-xs ${macdBullish ? 'text-green-600' : 'text-red-600'}`}>
                  {macdBullish ? '▲ Bullish' : '▼ Bearish'} (sig {o.macd_signal.toFixed(4)})
                </span>
              )}
            </div>
          </div>
          {o.bb_upper != null && o.bb_lower != null && (
            <>
              <MetricRow label="BB Upper" value={`$${o.bb_upper.toFixed(3)}`} />
              <MetricRow label="BB Lower" value={`$${o.bb_lower.toFixed(3)}`} />
              {o.price != null && (
                <MetricRow
                  label="BB Position"
                  value={`${(((o.price - o.bb_lower) / (o.bb_upper - o.bb_lower)) * 100).toFixed(0)}%`}
                  sub="of band"
                />
              )}
            </>
          )}
          {o.atr_14 != null && <MetricRow label="ATR (14)" value={`$${o.atr_14.toFixed(3)}`} />}
        </Card>

        {/* Risk metrics */}
        <Card title="Risk & Returns">
          <MetricRow label="Beta (1Y)"          value={fmt(o.beta_1y)} />
          <MetricRow label="Volatility (20D)"   value={formatRatio(o.volatility_20d)} />
          <MetricRow label="Volatility (60D)"   value={formatRatio(o.volatility_60d)} />
          <MetricRow label="Sharpe (1Y)"        value={fmt(o.sharpe_1y)} />
          <MetricRow
            label="ATH Drawdown"
            value={signedPct(o.drawdown_from_ath)}
            highlight={o.drawdown_from_ath != null && o.drawdown_from_ath < -0.3 ? 'red' : 'neutral'}
          />
          <MetricRow
            label="Short Interest"
            value={o.short_pct != null ? `${o.short_pct.toFixed(1)}%` : '—'}
            highlight={o.short_pct != null && o.short_pct > 5 ? 'red' : 'neutral'}
          />
          <MetricRow label="Momentum (3M)"      value={signedPct(o.momentum_3m)} />
          <MetricRow label="Momentum (6M)"      value={signedPct(o.momentum_6m)} />
        </Card>
      </div>
    </div>
  )
}

// ── Dividends Tab ─────────────────────────────────────────────

function DividendsTab({ data }: { data: DividendsResponse | null }) {
  if (!data) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        <p className="font-medium text-gray-500 mb-1">Loading dividend data…</p>
      </div>
    )
  }

  const { summary, history } = data

  if (history.length === 0 && summary.dps_ttm == null) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        <p className="font-medium text-gray-500 mb-1">No dividend history available</p>
        <p>This company has not paid dividends or data is not yet loaded.</p>
      </div>
    )
  }

  // Build bar chart data from history (most recent 10, oldest first for chart)
  const chartData = [...history]
    .slice(0, 16)
    .reverse()
    .map(d => ({
      label: d.ex_date.slice(0, 7),
      amount: d.amount ?? 0,
      franking: d.franking_pct ?? 0,
    }))

  // Max for scaling bars
  const maxAmount = Math.max(...chartData.map(d => d.amount), 0.001)

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">Dividend Yield</div>
          <div className="text-lg font-bold text-gray-900">
            {summary.dividend_yield != null ? formatRatio(summary.dividend_yield) : '—'}
          </div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">Grossed-Up Yield</div>
          <div className="text-lg font-bold text-green-700">
            {summary.grossed_up_yield != null ? formatRatio(summary.grossed_up_yield) : '—'}
          </div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">Franking</div>
          <div className={`text-lg font-bold ${summary.franking_pct === 100 ? 'text-green-700' : 'text-gray-900'}`}>
            {summary.franking_pct != null ? `${summary.franking_pct.toFixed(0)}%` : '—'}
          </div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">DPS (TTM)</div>
          <div className="text-lg font-bold text-gray-900">
            {summary.dps_ttm != null ? `$${summary.dps_ttm.toFixed(3)}` : '—'}
          </div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">Payout Ratio</div>
          <div className="text-lg font-bold text-gray-900">
            {summary.payout_ratio != null ? formatRatio(summary.payout_ratio) : '—'}
          </div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">Consec. Div. Years</div>
          <div className="text-lg font-bold text-gray-900">
            {summary.dividend_consecutive_yrs != null && summary.dividend_consecutive_yrs > 0 ? summary.dividend_consecutive_yrs : '—'}
          </div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">Div CAGR (3Y)</div>
          <div className="text-lg font-bold text-gray-900">
            {summary.dividend_cagr_3y != null ? formatRatio(summary.dividend_cagr_3y) : '—'}
          </div>
        </div>
        <div className="bg-gray-50 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">Ex-Div Date</div>
          <div className="text-base font-bold text-gray-900">
            {summary.ex_div_date ?? '—'}
          </div>
        </div>
      </div>

      {/* DPS bar chart */}
      {chartData.length > 0 && (
        <Card title="Dividend Per Share History (AUD)">
          <div className="flex items-end gap-1 h-32 mt-2">
            {chartData.map(d => (
              <div key={d.label} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                <div className="text-xs text-gray-500 font-medium" style={{ fontSize: '10px' }}>
                  {d.amount > 0 ? `$${d.amount.toFixed(3)}` : ''}
                </div>
                <div className="w-full relative">
                  <div
                    className="w-full rounded-t transition-all"
                    style={{
                      height: `${Math.max(4, (d.amount / maxAmount) * 80)}px`,
                      background: d.franking >= 100 ? '#16a34a' : d.franking > 0 ? '#ca8a04' : '#6b7280',
                    }}
                  />
                </div>
                <div className="text-gray-400 whitespace-nowrap overflow-hidden text-center"
                  style={{ fontSize: '9px', maxWidth: '100%' }}>
                  {d.label.slice(2)}
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-4 mt-3 text-xs text-gray-500">
            <span><span className="inline-block w-2.5 h-2.5 rounded-sm bg-green-600 mr-1" />Fully Franked</span>
            <span><span className="inline-block w-2.5 h-2.5 rounded-sm bg-yellow-600 mr-1" />Partially Franked</span>
            <span><span className="inline-block w-2.5 h-2.5 rounded-sm bg-gray-500 mr-1" />Unfranked</span>
          </div>
        </Card>
      )}

      {/* Dividend history table */}
      {history.length > 0 && (
        <Card title="Payment History">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-xs text-gray-400 font-medium pb-2 text-left">Ex-Date</th>
                  <th className="text-xs text-gray-400 font-medium pb-2 text-left">Pay Date</th>
                  <th className="text-xs text-gray-400 font-medium pb-2 text-right">Amount</th>
                  <th className="text-xs text-gray-400 font-medium pb-2 text-right">Franking</th>
                  <th className="text-xs text-gray-400 font-medium pb-2 text-left">Type</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {history.slice(0, 20).map(d => (
                  <tr key={d.ex_date} className="hover:bg-gray-50">
                    <td className="py-1.5 text-gray-900 font-medium">{d.ex_date}</td>
                    <td className="py-1.5 text-gray-500">{d.payment_date ?? '—'}</td>
                    <td className="py-1.5 text-right font-medium text-gray-900">
                      {d.amount != null ? `$${d.amount.toFixed(4)}` : '—'}
                    </td>
                    <td className="py-1.5 text-right">
                      {d.franking_pct != null ? (
                        <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                          d.franking_pct === 100 ? 'bg-green-100 text-green-700' :
                          d.franking_pct > 0 ? 'bg-yellow-100 text-yellow-700' :
                          'bg-gray-100 text-gray-500'
                        }`}>
                          {d.franking_pct.toFixed(0)}%
                        </span>
                      ) : '—'}
                    </td>
                    <td className="py-1.5 text-gray-400 text-xs">{d.div_type ?? 'Dividend'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}


// ── Peers Tab ─────────────────────────────────────────────────

function PeersTab({
  data,
  currentCode,
}: {
  data: PeersResponse | null
  currentCode: string
}) {
  if (!data) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        <p className="font-medium text-gray-500 mb-1">Loading peer data…</p>
      </div>
    )
  }

  if (data.peers.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        <p className="font-medium text-gray-500 mb-1">No peer data available</p>
        <p>No other companies found in the same industry group.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {data.gics_industry && (
        <p className="text-sm text-gray-500">
          Showing {data.peers.length} peers in <span className="font-medium text-gray-700">{data.gics_industry}</span>
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[700px]">
          <thead className="border-b border-gray-200">
            <tr>
              <th className="text-xs text-gray-400 font-medium pb-2 pr-4 text-left">Company</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">Mkt Cap</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">P/E</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">P/B</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">Div Yld</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">Gross-Up</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">Frank</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">ROE</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">1Y Rtn</th>
              <th className="text-xs text-gray-400 font-medium pb-2 pl-3 text-right">F-Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {data.peers.map(p => {
              const isSelected = p.asx_code === currentCode
              return (
                <tr
                  key={p.asx_code}
                  className={isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'}
                >
                  <td className="py-2 pr-4">
                    <div className="flex items-center gap-2">
                      {isSelected && (
                        <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-600 shrink-0" />
                      )}
                      <a
                        href={`/company/${p.asx_code}`}
                        className={`font-mono font-bold ${isSelected ? 'text-blue-600' : 'text-blue-500 hover:text-blue-700 hover:underline'}`}
                      >
                        {p.asx_code}
                      </a>
                      <span className="text-gray-600 text-xs truncate max-w-[120px]">{p.company_name}</span>
                    </div>
                  </td>
                  <td className="py-2 pl-3 text-right text-gray-700">{formatMarketCap(p.market_cap)}</td>
                  <td className="py-2 pl-3 text-right text-gray-700">{p.pe_ratio != null ? `${p.pe_ratio.toFixed(1)}x` : '—'}</td>
                  <td className="py-2 pl-3 text-right text-gray-700">{p.price_to_book != null ? `${p.price_to_book.toFixed(2)}x` : '—'}</td>
                  <td className="py-2 pl-3 text-right text-gray-700">{formatRatio(p.dividend_yield)}</td>
                  <td className="py-2 pl-3 text-right">
                    <span className={p.grossed_up_yield != null && p.grossed_up_yield >= 0.06 ? 'text-green-600 font-medium' : 'text-gray-700'}>
                      {formatRatio(p.grossed_up_yield)}
                    </span>
                  </td>
                  <td className="py-2 pl-3 text-right">
                    {p.franking_pct != null ? (
                      <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                        p.franking_pct === 100 ? 'bg-green-100 text-green-700' :
                        p.franking_pct > 0    ? 'bg-yellow-100 text-yellow-700' :
                                                'bg-gray-100 text-gray-500'
                      }`}>
                        {p.franking_pct.toFixed(0)}%
                      </span>
                    ) : '—'}
                  </td>
                  <td className="py-2 pl-3 text-right">
                    <span className={p.roe != null && p.roe >= 0.15 ? 'text-green-600 font-medium' : 'text-gray-700'}>
                      {formatRatio(p.roe)}
                    </span>
                  </td>
                  <td className="py-2 pl-3 text-right">
                    <span className={p.return_1y != null ? (p.return_1y >= 0 ? 'text-green-600 font-medium' : 'text-red-600') : 'text-gray-300'}>
                      {p.return_1y != null ? `${p.return_1y >= 0 ? '+' : ''}${(p.return_1y * 100).toFixed(1)}%` : '—'}
                    </span>
                  </td>
                  <td className="py-2 pl-3 text-right">
                    {p.piotroski_f_score != null ? (
                      <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                        p.piotroski_f_score >= 7 ? 'bg-green-100 text-green-700' :
                        p.piotroski_f_score >= 4 ? 'bg-yellow-100 text-yellow-700' :
                                                    'bg-red-100 text-red-700'
                      }`}>
                        {p.piotroski_f_score}/9
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}


// ── Coming Soon Tab ───────────────────────────────────────────

function ComingSoonTab({ title, description }: { title: string; description: string }) {
  return (
    <div className="text-center py-16">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-blue-50 mb-4">
        <span className="text-2xl">🚀</span>
      </div>
      <h3 className="text-base font-semibold text-gray-700 mb-2">{title}</h3>
      <p className="text-sm text-gray-400 max-w-xs mx-auto">{description}</p>
      <span className="inline-block mt-3 px-3 py-1 bg-blue-50 text-blue-600 text-xs font-medium rounded-full">
        Coming Soon
      </span>
    </div>
  )
}


// ── Main Component ────────────────────────────────────────────

export default function CompanyTabs({ code }: { code: string }) {
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [overview, setOverview]   = useState<CompanyOverview | null>(null)
  const [financials, setFinancials] = useState<FinancialsResponse | null>(null)
  const [halfYearly, setHalfYearly] = useState<HalfYearlyResponse | null>(null)
  const [prices, setPrices]         = useState<PricesResponse | null>(null)
  const [dividends, setDividends]   = useState<DividendsResponse | null>(null)
  const [peers, setPeers]           = useState<PeersResponse | null>(null)

  const [loading, setLoading]               = useState(true)
  const [financialsLoading, setFinancialsLoading] = useState(false)
  const [halfYearlyLoading, setHalfYearlyLoading] = useState(false)
  const [pricesLoading, setPricesLoading]   = useState(false)
  const [dividendsLoading, setDividendsLoading] = useState(false)
  const [peersLoading, setPeersLoading]     = useState(false)
  const [error, setError]                   = useState<string | null>(null)

  // Financial period toggle (annual vs half-yearly)
  const [financialPeriod, setFinancialPeriod] = useState<FinancialPeriod>('annual')

  // Fetch overview immediately on mount
  useEffect(() => {
    setLoading(true)
    setError(null)
    getCompanyOverview(code)
      .then(setOverview)
      .catch(e => setError(e?.response?.data?.detail ?? e.message))
      .finally(() => setLoading(false))
  }, [code])

  // Lazy-load per tab
  useEffect(() => {
    if (activeTab === 'technicals' && !prices) {
      setPricesLoading(true)
      getCompanyPrices(code, '1y')
        .then(setPrices)
        .catch(() => setPrices({ asx_code: code, period: '1y', data: [] }))
        .finally(() => setPricesLoading(false))
    }
  }, [activeTab, code, prices])

  useEffect(() => {
    if (activeTab === 'financials' && !financials) {
      setFinancialsLoading(true)
      getCompanyFinancials(code)
        .then(setFinancials)
        .catch(() => setFinancials({ asx_code: code, years: [] }))
        .finally(() => setFinancialsLoading(false))
    }
  }, [activeTab, code, financials])

  // Fetch half-yearly when period toggle changes to halfyearly
  useEffect(() => {
    if (activeTab === 'financials' && financialPeriod === 'halfyearly' && !halfYearly) {
      setHalfYearlyLoading(true)
      getCompanyHalfYearly(code)
        .then(setHalfYearly)
        .catch(() => setHalfYearly({ asx_code: code, periods: [] }))
        .finally(() => setHalfYearlyLoading(false))
    }
  }, [activeTab, financialPeriod, code, halfYearly])

  useEffect(() => {
    if (activeTab === 'dividends' && !dividends) {
      setDividendsLoading(true)
      getCompanyDividends(code)
        .then(setDividends)
        .catch(() => setDividends({ asx_code: code, summary: {
          dividend_yield: null, grossed_up_yield: null, franking_pct: null,
          dps_ttm: null, dps_fy0: null, payout_ratio: null,
          ex_div_date: null, dividend_consecutive_yrs: null, dividend_cagr_3y: null,
        }, history: [] }))
        .finally(() => setDividendsLoading(false))
    }
  }, [activeTab, code, dividends])

  useEffect(() => {
    if (activeTab === 'peers' && !peers) {
      setPeersLoading(true)
      getCompanyPeers(code)
        .then(setPeers)
        .catch(() => setPeers({ asx_code: code, gics_industry: null, peers: [] }))
        .finally(() => setPeersLoading(false))
    }
  }, [activeTab, code, peers])

  // Tab definitions
  const tabs: { id: Tab; label: string; comingSoon?: boolean }[] = [
    { id: 'overview',   label: 'Overview'    },
    { id: 'financials', label: 'Financials'  },
    { id: 'technicals', label: 'Technicals'  },
    { id: 'dividends',  label: 'Dividends'   },
    { id: 'peers',      label: 'Peers'       },
    { id: 'ai',         label: 'AI Insights', comingSoon: true },
    { id: 'documents',  label: 'Documents',   comingSoon: true },
  ]

  const isLoading = (tab: Tab) => {
    if (tab === 'financials') return financialsLoading || (financialPeriod === 'halfyearly' && halfYearlyLoading)
    if (tab === 'technicals') return pricesLoading
    if (tab === 'dividends')  return dividendsLoading
    if (tab === 'peers')      return peersLoading
    return false
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      {/* Tab bar */}
      <div className="flex gap-0.5 border-b border-gray-200 mb-5 -mx-5 px-5 overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => !t.comingSoon && setActiveTab(t.id)}
            className={[
              'pb-3 px-3 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
              t.comingSoon
                ? 'border-transparent text-gray-300 cursor-not-allowed'
                : activeTab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700',
            ].join(' ')}
          >
            {t.label}
            {t.comingSoon && (
              <span className="ml-1 text-xs text-gray-300">(soon)</span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => <LoadingCard key={i} />)}
        </div>
      ) : error ? (
        <div className="text-center py-10">
          <p className="text-red-500 font-medium mb-1">Could not load market data</p>
          <p className="text-sm text-gray-400">{error}</p>
        </div>
      ) : overview ? (
        <>
          {activeTab === 'overview' && <OverviewTab o={overview} />}

          {activeTab === 'financials' && (
            isLoading('financials')
              ? <div className="grid grid-cols-1 gap-4">{[1,2,3].map(i=><LoadingCard key={i}/>)}</div>
              : <FinancialsTab
                  financials={financials}
                  halfYearly={halfYearly}
                  period={financialPeriod}
                  onPeriodChange={setFinancialPeriod}
                />
          )}

          {activeTab === 'technicals' && (
            <TechnicalsTab o={overview} prices={prices} pricesLoading={pricesLoading} />
          )}

          {activeTab === 'dividends' && (
            isLoading('dividends')
              ? <div className="grid grid-cols-1 gap-4">{[1,2].map(i=><LoadingCard key={i}/>)}</div>
              : <DividendsTab data={dividends} />
          )}

          {activeTab === 'peers' && (
            isLoading('peers')
              ? <div className="grid grid-cols-1 gap-4">{[1,2].map(i=><LoadingCard key={i}/>)}</div>
              : <PeersTab data={peers} currentCode={code} />
          )}

          {activeTab === 'ai' && (
            <ComingSoonTab
              title="AI Insights"
              description="AI-powered analysis of fundamentals, news sentiment, and earnings call transcripts. Powered by Claude."
            />
          )}

          {activeTab === 'documents' && (
            <ComingSoonTab
              title="Company Documents"
              description="ASX announcements, annual reports, investor presentations, and half-year results in one place."
            />
          )}
        </>
      ) : null}
    </div>
  )
}
