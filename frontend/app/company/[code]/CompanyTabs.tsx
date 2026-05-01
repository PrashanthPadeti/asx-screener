'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  getCompanyOverview, getCompanyFinancials, getCompanyPrices,
  type CompanyOverview, type FinancialsResponse, type PricesResponse,
} from '@/lib/api'
import {
  formatPrice, formatMarketCap, formatVolume,
  formatRatio, formatRatioChange, formatPctRaw, formatNumber,
} from '@/lib/utils'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────

type Tab = 'overview' | 'financials' | 'technicals'

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
  const { pros, cons } = buildSignals(o)

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
          <MetricRow label="Short Interest"    value={o.short_pct != null ? `${o.short_pct.toFixed(1)}%` : '—'}
            highlight={o.short_pct != null && o.short_pct > 5 ? 'red' : 'neutral'} />
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

function FinancialsTab({ financials }: { financials: FinancialsResponse | null; loading: boolean }) {
  if (!financials || financials.years.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400 text-sm">
        <p className="font-medium text-gray-500 mb-1">Detailed historical financials not yet loaded</p>
        <p>Annual financial statements are sourced from company filings and loaded periodically.</p>
      </div>
    )
  }

  const years = [...financials.years].reverse() // chronological order for table

  const pnlRows: { label: string; key: keyof typeof years[0]; fmt: (v: number | null) => string }[] = [
    { label: 'Revenue',       key: 'revenue',      fmt: fmtM },
    { label: 'Gross Profit',  key: 'gross_profit', fmt: fmtM },
    { label: 'EBITDA',        key: 'ebitda',       fmt: fmtM },
    { label: 'EBIT',          key: 'ebit',         fmt: fmtM },
    { label: 'Net Profit',    key: 'net_profit',   fmt: fmtM },
    { label: 'EPS',           key: 'eps',          fmt: v => v != null ? `$${v.toFixed(3)}` : '—' },
    { label: 'DPS',           key: 'dps',          fmt: v => v != null ? `$${v.toFixed(3)}` : '—' },
  ]

  const marginRows: { label: string; key: keyof typeof years[0]; fmt: (v: number | null) => string }[] = [
    { label: 'Gross Margin',  key: 'gpm',          fmt: v => formatRatio(v) },
    { label: 'EBITDA Margin', key: 'ebitda_margin',fmt: v => formatRatio(v) },
    { label: 'Net Margin',    key: 'npm',          fmt: v => formatRatio(v) },
  ]

  const bsRows: { label: string; key: keyof typeof years[0]; fmt: (v: number | null) => string }[] = [
    { label: 'Total Assets',       key: 'total_assets',        fmt: fmtM },
    { label: 'Total Equity',       key: 'total_equity',        fmt: fmtM },
    { label: 'Total Debt',         key: 'total_debt',          fmt: fmtM },
    { label: 'Net Debt',           key: 'net_debt',            fmt: fmtM },
    { label: 'Cash',               key: 'cash_equivalents',    fmt: fmtM },
    { label: 'Book Value / Sh',    key: 'book_value_per_share',fmt: v => v != null ? `$${v.toFixed(2)}` : '—' },
    { label: 'Debt / Equity',      key: 'debt_to_equity',      fmt: fmtX },
  ]

  const cfRows: { label: string; key: keyof typeof years[0]; fmt: (v: number | null) => string }[] = [
    { label: 'Cash From Ops',  key: 'cfo',   fmt: fmtM },
    { label: 'Capex',          key: 'capex', fmt: fmtM },
    { label: 'Free Cash Flow', key: 'fcf',   fmt: fmtM },
  ]

  const TableSection = ({
    title,
    rows,
  }: {
    title: string
    rows: { label: string; key: string; fmt: (v: number | null) => string }[]
  }) => (
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

  return (
    <div className="space-y-4">

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

// ── Main Component ────────────────────────────────────────────

export default function CompanyTabs({ code }: { code: string }) {
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [overview, setOverview] = useState<CompanyOverview | null>(null)
  const [financials, setFinancials] = useState<FinancialsResponse | null>(null)
  const [prices, setPrices] = useState<PricesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [financialsLoading, setFinancialsLoading] = useState(false)
  const [pricesLoading, setPricesLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch overview immediately
  useEffect(() => {
    setLoading(true)
    setError(null)
    getCompanyOverview(code)
      .then(setOverview)
      .catch(e => setError(e?.response?.data?.detail ?? e.message))
      .finally(() => setLoading(false))
  }, [code])

  // Fetch prices for the chart when technicals tab is active
  useEffect(() => {
    if (activeTab === 'technicals' && !prices) {
      setPricesLoading(true)
      getCompanyPrices(code, '1y')
        .then(setPrices)
        .catch(() => setPrices({ asx_code: code, period: '1y', data: [] }))
        .finally(() => setPricesLoading(false))
    }
  }, [activeTab, code, prices])

  // Fetch financials lazily
  useEffect(() => {
    if (activeTab === 'financials' && !financials) {
      setFinancialsLoading(true)
      getCompanyFinancials(code)
        .then(setFinancials)
        .catch(() => setFinancials({ asx_code: code, years: [] }))
        .finally(() => setFinancialsLoading(false))
    }
  }, [activeTab, code, financials])

  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview',    label: 'Overview' },
    { id: 'financials',  label: 'Financials' },
    { id: 'technicals',  label: 'Technicals' },
  ]

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-200 mb-5 -mx-5 px-5 overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={[
              'pb-3 px-3 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
              activeTab === t.id
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            ].join(' ')}
          >
            {t.label}
          </button>
        ))}
        <button className="pb-3 px-3 text-sm font-medium border-b-2 -mb-px border-transparent text-gray-300 cursor-not-allowed whitespace-nowrap">
          Announcements
        </button>
        <button className="pb-3 px-3 text-sm font-medium border-b-2 -mb-px border-transparent text-gray-300 cursor-not-allowed whitespace-nowrap">
          AI Insights
        </button>
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
            financialsLoading
              ? <div className="grid grid-cols-1 gap-4">{[1,2,3].map(i=><LoadingCard key={i}/>)}</div>
              : <FinancialsTab financials={financials} loading={financialsLoading} />
          )}
          {activeTab === 'technicals' && (
            <TechnicalsTab o={overview} prices={prices} pricesLoading={pricesLoading} />
          )}
        </>
      ) : null}
    </div>
  )
}
