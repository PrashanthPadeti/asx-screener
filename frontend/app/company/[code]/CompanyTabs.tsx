'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  ComposedChart, Line, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  getCompanyOverview, getCompanyFinancials, getCompanyPrices,
  getCompanyDividends, getCompanyPeers, getCompanyHalfYearly,
  getCompanyAnnouncements, getAISummary, getAnomalyFlags,
  getMiningMetrics, getReitMetrics, getCapitalRaises,
  type CompanyOverview, type FinancialsResponse, type AnnualFinancialsRow,
  type PricesResponse, type DividendsResponse, type PeersResponse,
  type HalfYearlyResponse, type Announcement, type AnnouncementsResponse,
  type AISummary, type CompanyAnomalyFlag,
  type MiningMetrics, type ReitMetrics, type CapitalRaiseEvent,
} from '@/lib/api'
import {
  formatPrice, formatMarketCap, formatVolume,
  formatRatio, formatRatioChange, formatPctRaw, formatNumber,
} from '@/lib/utils'
import { TrendingUp, TrendingDown, Minus, FileText, ExternalLink, AlertTriangle, Tag } from 'lucide-react'
import { PlanGate } from '@/components/PlanGate'

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
    highlight === 'green' ? 'text-emerald-600 font-semibold' :
    highlight === 'red'   ? 'text-red-500 font-semibold' :
    'text-gray-800 font-semibold'

  return (
    <div className="flex items-baseline justify-between py-1.5 border-b border-gray-50/80 last:border-0 group hover:bg-blue-50/30 -mx-1 px-1 rounded transition-colors">
      <span className="text-xs text-gray-400 font-medium">{label}</span>
      <span className={`text-sm text-right ${valueClass}`}>
        {value}
        {sub && <span className="text-xs text-gray-400 ml-1 font-normal">{sub}</span>}
      </span>
    </div>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow duration-200">
      <div className="bg-gradient-to-r from-slate-50 to-gray-50/50 px-4 py-2.5 border-b border-gray-100">
        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest">{title}</h3>
      </div>
      <div className="p-4">
        {children}
      </div>
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
  const gradient =
    score >= 75 ? 'from-emerald-400 to-green-500' :
    score >= 50 ? 'from-blue-400 to-indigo-500'   :
    score >= 25 ? 'from-amber-400 to-orange-500'  : 'from-red-400 to-rose-500'
  return (
    <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
      <div
        className={`h-1.5 rounded-full bg-gradient-to-r ${gradient} transition-all duration-500`}
        style={{ width: `${score}%` }}
      />
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

// ── Anomaly Meta ──────────────────────────────────────────────
// Maps flag_type → rich contextual explanation shown in Overview tab

const ANOMALY_META: Record<string, {
  title:  string
  icon:   string
  what:   string
  why:    string
  action: string
}> = {
  high_pe: {
    title:  'Elevated P/E Ratio',
    icon:   '📈',
    what:   'The price-to-earnings ratio is significantly above the market or sector average.',
    why:    'A very high P/E suggests the market is pricing in exceptional future growth. If that growth fails to materialise, the share price can correct sharply. This becomes an anomaly when the P/E diverges substantially from peers without a clear earnings catalyst.',
    action: 'Compare against sector peers and check forward P/E. Investigate what growth assumptions justify the current multiple.',
  },
  low_pe: {
    title:  'Unusually Low P/E Ratio',
    icon:   '📉',
    what:   'The price-to-earnings ratio is well below sector norms.',
    why:    'A very low P/E can indicate a value opportunity — or it can signal the market expects earnings to deteriorate. It becomes an anomaly when the discount is unexplained by visible risks, often preceding earnings downgrades.',
    action: 'Investigate whether the low P/E reflects genuine value or an anticipated earnings decline.',
  },
  revenue_decline: {
    title:  'Revenue Declining',
    icon:   '⬇️',
    what:   'Year-on-year revenue has contracted meaningfully.',
    why:    'Sustained revenue decline is one of the strongest leading indicators of future earnings pressure and potential capital raises. It becomes anomalous when paired with management guidance that appears optimistic, or when the decline accelerates.',
    action: 'Review the last 2–3 earnings reports for trend direction and management commentary on root cause.',
  },
  high_debt: {
    title:  'High Leverage',
    icon:   '🏦',
    what:   'The debt-to-equity ratio is significantly above sector norms.',
    why:    'Elevated debt amplifies risk — particularly when interest rates rise or earnings disappoint. It is flagged as anomalous when debt levels exceed a threshold that could strain interest coverage or trigger covenant reviews.',
    action: 'Check the interest coverage ratio and any upcoming debt maturity dates in the annual report.',
  },
  negative_fcf: {
    title:  'Negative Free Cash Flow',
    icon:   '🔴',
    what:   'The company is consuming more cash than its operations generate.',
    why:    'Persistent negative FCF forces companies to either raise capital (diluting shareholders) or take on more debt. This is anomalous when it occurs alongside reported accounting profits, which may suggest earnings quality issues.',
    action: 'Look at the cash flow statement — distinguish between investment-heavy growth (capex) vs. operational losses.',
  },
  high_short_interest: {
    title:  'Elevated Short Interest',
    icon:   '🎯',
    what:   'A significant proportion of the float is being shorted by institutional investors.',
    why:    'High short interest signals that sophisticated investors are betting against the stock. While it can create a short squeeze opportunity, it more commonly reflects institutional research uncovering fundamental concerns not yet visible in public data.',
    action: 'Check ASIC short-selling data for trend direction. Rising short interest over several weeks is a stronger warning signal than a one-off reading.',
  },
  insider_selling: {
    title:  'Insider Selling Activity',
    icon:   '👔',
    what:   'Company directors or executives have recently sold material quantities of their shareholding.',
    why:    'Insiders know more about the business than external investors. While selling can be benign (diversification, tax), a cluster of insider sales — particularly at the same time — often precedes negative news. It is flagged when the volume or timing is unusual.',
    action: 'Cross-reference with ASX Appendix 3Y filings to see who sold and when relative to recent news or reporting dates.',
  },
  going_concern: {
    title:  'Auditor Going Concern Note',
    icon:   '⚠️',
    what:   "The company's auditor has included a going concern qualification in its audit report.",
    why:    'Auditors only include going concern notes when they have substantial doubt about whether a company can continue operating for the next 12 months. It indicates potential insolvency risk, likely capital raise requirements, or restructuring.',
    action: 'Read the full auditor notes and any board commentary. Assess cash runway, upcoming liabilities, and whether a capital raise is likely.',
  },
  low_liquidity: {
    title:  'Low Trading Liquidity',
    icon:   '💧',
    what:   'Average daily trading volume is very low relative to market capitalisation.',
    why:    'Illiquid stocks carry hidden risks: large bid-ask spreads, inability to exit quickly, and susceptibility to price manipulation. They are flagged when volume falls below a threshold where institutional investors cannot build or exit positions at scale.',
    action: 'Be aware that any position may be difficult to exit at the quoted price. Use limit orders rather than market orders.',
  },
  dilution_risk: {
    title:  'Share Dilution Risk',
    icon:   '📊',
    what:   'The company has issued, or appears likely to issue, a significant number of new shares.',
    why:    'Dilution directly reduces earnings per share and the value of existing holdings. It is flagged when capital raises are frequent, share count growth is high, or when cash burn suggests an imminent equity raise.',
    action: 'Review recent placement history in the ASX announcements tab and check the cash position vs. quarterly burn rate.',
  },
  negative_equity: {
    title:  'Negative Shareholder Equity',
    icon:   '🚨',
    what:   'Total liabilities exceed total assets — book value is negative.',
    why:    'Negative equity signals the company has consumed all its contributed capital. This significantly increases solvency risk and limits access to debt financing. It may also breach banking covenants.',
    action: 'Review the balance sheet for the source of negative equity — accumulated losses vs. intangible write-downs have different implications.',
  },
  price_spike: {
    title:  'Unusual Price Movement',
    icon:   '⚡',
    what:   'The stock has made an abnormal short-term price move relative to its historical volatility.',
    why:    'Sharp price spikes without a corresponding announcement can indicate information leakage, speculative activity, or thin liquidity being exploited. They sometimes precede material ASX announcements.',
    action: "Check recent ASX announcements for any trading halt requests or 'aware' queries from ASX. Monitor for any pending corporate actions.",
  },
  volume_spike: {
    title:  'Unusual Trading Volume',
    icon:   '📶',
    what:   'Trading volume has exceeded normal levels by a significant multiple.',
    why:    'Abnormal volume without a matching announcement may indicate institutional accumulation, information leakage ahead of a news release, or a large holder exiting. It is anomalous when volume is 3× or more above the 20-day average.',
    action: 'Review ASX announcements for the same period. Unusual volume + price movement together is a stronger signal than either alone.',
  },
  earnings_miss: {
    title:  'Earnings Disappointment',
    icon:   '📋',
    what:   'Reported earnings came in meaningfully below consensus analyst estimates.',
    why:    "Earnings misses often reflect structural issues rather than one-off events. When a company repeatedly misses, it erodes market confidence in management guidance and can trigger re-rating to a lower P/E multiple.",
    action: "Compare the magnitude of the miss and management's explanation. Check if guidance for the next period has also been revised down.",
  },
  guidance_cut: {
    title:  'Forward Guidance Reduced',
    icon:   '✂️',
    what:   'Management has materially downgraded their forward earnings or revenue guidance.',
    why:    "Guidance cuts reveal management's own reduced confidence in the business outlook. Multiple guidance cuts — sometimes called 'profit warnings' — are strongly correlated with further downward earnings revisions.",
    action: 'Assess whether this is the first guidance cut or part of a pattern. First cuts tend to be understated.',
  },
  low_coverage: {
    title:  'Minimal Analyst Coverage',
    icon:   '🔭',
    what:   'The stock is covered by very few or no sell-side analysts.',
    why:    'Low analyst coverage creates information asymmetry — pricing may be less efficient, news may be delayed reaching the market, and there are fewer external checks on management claims.',
    action: 'Rely more heavily on primary research — reading annual reports, Appendix 4C/4D filings, and management briefings directly.',
  },
  cash_burn: {
    title:  'High Cash Burn Rate',
    icon:   '🔥',
    what:   'The company is consuming cash at a rate that raises runway concerns.',
    why:    'For pre-revenue or early-stage companies, cash runway is existential. It is flagged when Appendix 4C data indicates less than 6 months of cash remaining, as this typically requires a capital raise that will dilute shareholders.',
    action: 'Review the most recent Appendix 4C filing for cash position and estimated quarterly expenditure. Calculate runway: cash ÷ quarterly cash used.',
  },
  high_book_discount: {
    title:  'Significant Discount to Book Value',
    icon:   '💰',
    what:   'The stock is trading well below its reported net asset value (book value per share).',
    why:    "A large book discount either represents genuine value or signals the market believes assets are overstated (e.g. goodwill that will be written down). It is anomalous when the discount persists across market cycles without a clear explanation.",
    action: 'Scrutinise the balance sheet for asset quality — intangibles, goodwill, and deferred tax assets should be assessed critically.',
  },
}

function getAnomalyMeta(flagType: string) {
  return ANOMALY_META[flagType] ?? {
    title:  flagType.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
    icon:   '⚠️',
    what:   'An unusual data pattern has been detected for this stock.',
    why:    'Our screening system has identified a metric or pattern that falls outside normal parameters for this company or its peer group. This warrants further investigation before making an investment decision.',
    action: 'Review recent announcements and financial reports to understand the context behind this flag.',
  }
}

// ── Overview Tab ──────────────────────────────────────────────

function OverviewTab({ o, code, anomalyFlags }: { o: CompanyOverview; code: string; anomalyFlags: CompanyAnomalyFlag[] }) {
  // Use DB-computed pros/cons when available; fall back to client-side engine
  const hasDatabaseSignals = (o.pros?.length ?? 0) > 0 || (o.cons?.length ?? 0) > 0
  const { pros, cons } = hasDatabaseSignals
    ? { pros: o.pros ?? [], cons: o.cons ?? [] }
    : buildSignals(o)

  // AI Analysis state (Week 12)
  const [aiData, setAiData]     = useState<AISummary | null>(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError]   = useState<string | null>(null)
  const [aiLoaded, setAiLoaded] = useState(false)

  // Anomaly expansion state
  const [expandedAnomalyIdx, setExpandedAnomalyIdx] = useState<number | null>(null)

  // force=true bypasses the guard — needed on retry because setState is async
  const loadAI = (force = false) => {
    if (aiLoaded && !force) return
    setAiLoading(true)
    setAiError(null)
    getAISummary(code)
      .then(d => { setAiData(d); setAiLoaded(true) })
      .catch(e => setAiError(e?.response?.data?.detail || e.message || 'Failed'))
      .finally(() => setAiLoading(false))
  }

  const pos52w = o.high_52w != null && o.low_52w != null && o.price != null
    ? ((o.price - o.low_52w) / (o.high_52w - o.low_52w)) * 100
    : null

  return (
    <div className="space-y-4">

      {/* Price summary — dark hero */}
      <div className="relative bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 rounded-xl overflow-hidden border border-white/10">
        <div className="absolute -top-16 -right-16 w-48 h-48 bg-blue-500/10 rounded-full blur-2xl pointer-events-none" />
        <div className="relative p-5">
          <div className="flex flex-wrap gap-6 mb-4">
            <div>
              <p className="text-xs text-slate-500 font-semibold uppercase tracking-widest mb-1">Last Price</p>
              <span className="text-4xl font-black text-white tracking-tight">
                {o.price != null ? `$${o.price.toFixed(3)}` : '—'}
              </span>
            </div>
            <div className="flex flex-wrap gap-5 items-center">
              {[
                { label: 'Market Cap',   value: formatMarketCap(o.market_cap) },
                { label: 'Volume',       value: formatVolume(o.volume) },
                { label: 'Avg Vol (20D)',value: formatVolume(o.avg_volume_20d) },
                ...(o.price_date ? [{ label: 'As at', value: o.price_date }] : []),
              ].map(item => (
                <div key={item.label} className="flex flex-col justify-center">
                  <span className="text-xs text-slate-500 font-medium mb-0.5">{item.label}</span>
                  <span className="font-bold text-slate-200 text-sm">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 52-week range */}
          {o.high_52w != null && o.low_52w != null && (
            <div>
              <div className="flex justify-between text-xs text-slate-500 mb-1.5">
                <span>52W Low: ${o.low_52w.toFixed(2)}</span>
                <span>52W High: ${o.high_52w.toFixed(2)}</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-1.5 relative">
                <div className="h-1.5 bg-gradient-to-r from-red-400 via-amber-400 to-emerald-400 rounded-full" />
                <div
                  className="absolute w-3 h-3 bg-white rounded-full -top-[3px] shadow-lg ring-2 ring-blue-400/50"
                  style={{ left: `calc(${Math.max(1, Math.min(97, pos52w ?? 50))}% - 6px)` }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Composite Score Meter */}
      {o.composite_score != null && <CompositeScoreMeter o={o} />}

      {/* Key Statistics Strip */}
      <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden">
        <div className="bg-gradient-to-r from-slate-50 to-gray-50/50 px-4 py-2.5 border-b border-gray-100">
          <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest">Key Statistics</h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 divide-x divide-y divide-gray-50">
          {[
            { label: 'EPS (FY0)',     value: o.eps_fy0 != null ? `$${o.eps_fy0.toFixed(2)}` : '—' },
            { label: 'EPS (FY1)',     value: o.eps_fy1 != null ? `$${o.eps_fy1.toFixed(2)}` : '—' },
            { label: 'P/E Ratio',     value: fmtX(o.pe_ratio) },
            { label: 'P/B Ratio',     value: fmtX(o.price_to_book) },
            { label: 'EV/EBITDA',     value: fmtX(o.ev_to_ebitda) },
            { label: 'PEG Ratio',     value: fmtX(o.peg_ratio) },
            { label: 'Div Yield',     value: formatRatio(o.dividend_yield) },
            { label: 'Grossed-Up',    value: formatRatio(o.grossed_up_yield) },
            { label: 'D/E Ratio',     value: fmtX(o.debt_to_equity) },
            { label: 'FCF Yield',     value: formatRatio(o.fcf_yield) },
            { label: 'Rev Growth 1Y', value: signedPct(o.revenue_growth_1y) },
            { label: 'Net Margin',    value: formatRatio(o.net_margin) },
            { label: 'ROE',           value: formatRatio(o.roe) },
            { label: 'EV/Revenue',    value: fmtX(o.ev_to_revenue) },
            { label: 'Book Val/Sh',   value: o.book_value_per_share != null ? `$${o.book_value_per_share.toFixed(2)}` : '—' },
            { label: 'DPS (TTM)',     value: o.dps_ttm != null ? `$${o.dps_ttm.toFixed(3)}` : '—' },
          ].map(({ label, value }) => (
            <div key={label} className="px-4 py-3 flex flex-col gap-0.5">
              <span className="text-[10px] text-gray-400 font-medium uppercase tracking-wide">{label}</span>
              <span className="text-sm font-bold text-gray-800">{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Fundamental Health Checklist */}
      {(() => {
        type CheckResult = { label: string; detail: string; status: 'pass' | 'warn' | 'fail' | 'na' }
        const checks: CheckResult[] = []

        // 1. Has the company ever been profitable?
        if (o.net_margin != null) {
          checks.push(o.net_margin > 0
            ? { label: 'Profitable', detail: `Net margin ${formatRatio(o.net_margin)}`, status: 'pass' }
            : { label: 'Profitable', detail: `Net margin ${formatRatio(o.net_margin)} — loss-making`, status: 'fail' })
        } else {
          checks.push({ label: 'Profitable', detail: 'No earnings data', status: 'na' })
        }

        // 2. Revenue growing?
        if (o.revenue_growth_1y != null) {
          checks.push(o.revenue_growth_1y > 0.05
            ? { label: 'Revenue Growth', detail: `+${(o.revenue_growth_1y*100).toFixed(1)}% YoY`, status: 'pass' }
            : o.revenue_growth_1y >= 0
            ? { label: 'Revenue Growth', detail: `+${(o.revenue_growth_1y*100).toFixed(1)}% YoY — flat`, status: 'warn' }
            : { label: 'Revenue Growth', detail: `${(o.revenue_growth_1y*100).toFixed(1)}% YoY — declining`, status: 'fail' })
        } else {
          checks.push({ label: 'Revenue Growth', detail: 'No data', status: 'na' })
        }

        // 3. Earnings quality (FCF > 0)
        if (o.fcf_fy0 != null) {
          checks.push(o.fcf_fy0 > 0
            ? { label: 'Cash Earnings', detail: `FCF $${(o.fcf_fy0).toFixed(0)}M — positive`, status: 'pass' }
            : { label: 'Cash Earnings', detail: `FCF $${(o.fcf_fy0).toFixed(0)}M — negative`, status: 'fail' })
        } else if (o.cfo_fy0 != null) {
          checks.push(o.cfo_fy0 > 0
            ? { label: 'Cash Earnings', detail: `CFO $${(o.cfo_fy0).toFixed(0)}M — positive`, status: 'pass' }
            : { label: 'Cash Earnings', detail: `CFO $${(o.cfo_fy0).toFixed(0)}M — negative`, status: 'fail' })
        } else {
          checks.push({ label: 'Cash Earnings', detail: 'No cash flow data', status: 'na' })
        }

        // 4. Liquidity — Current Ratio
        if (o.current_ratio != null) {
          checks.push(o.current_ratio >= 1.5
            ? { label: 'Liquidity', detail: `Current ratio ${o.current_ratio.toFixed(1)}x — healthy`, status: 'pass' }
            : o.current_ratio >= 1.0
            ? { label: 'Liquidity', detail: `Current ratio ${o.current_ratio.toFixed(1)}x — acceptable`, status: 'warn' }
            : { label: 'Liquidity', detail: `Current ratio ${o.current_ratio.toFixed(1)}x — at risk`, status: 'fail' })
        } else {
          checks.push({ label: 'Liquidity', detail: 'No balance sheet data', status: 'na' })
        }

        // 5. Leverage — D/E Ratio
        if (o.debt_to_equity != null) {
          checks.push(o.debt_to_equity < 1.0
            ? { label: 'Low Leverage', detail: `D/E ${o.debt_to_equity.toFixed(1)}x — conservative`, status: 'pass' }
            : o.debt_to_equity < 2.5
            ? { label: 'Low Leverage', detail: `D/E ${o.debt_to_equity.toFixed(1)}x — moderate`, status: 'warn' }
            : { label: 'Low Leverage', detail: `D/E ${o.debt_to_equity.toFixed(1)}x — high leverage`, status: 'fail' })
        } else {
          checks.push({ label: 'Low Leverage', detail: 'No debt data', status: 'na' })
        }

        // 6. Competitive moat — Gross Margin > 20%
        if (o.gross_margin != null) {
          checks.push(o.gross_margin > 0.20
            ? { label: 'Gross Margin', detail: `${(o.gross_margin*100).toFixed(1)}% — indicates moat`, status: 'pass' }
            : o.gross_margin > 0
            ? { label: 'Gross Margin', detail: `${(o.gross_margin*100).toFixed(1)}% — low margin`, status: 'warn' }
            : { label: 'Gross Margin', detail: `${(o.gross_margin*100).toFixed(1)}% — negative margin`, status: 'fail' })
        } else {
          checks.push({ label: 'Gross Margin', detail: 'No margin data', status: 'na' })
        }

        // 7. ROE > 15%
        if (o.roe != null) {
          checks.push(o.roe > 0.15
            ? { label: 'ROE', detail: `${(o.roe*100).toFixed(1)}% — strong returns`, status: 'pass' }
            : o.roe > 0
            ? { label: 'ROE', detail: `${(o.roe*100).toFixed(1)}% — below benchmark`, status: 'warn' }
            : { label: 'ROE', detail: `${(o.roe*100).toFixed(1)}% — negative`, status: 'fail' })
        } else {
          checks.push({ label: 'ROE', detail: 'No data', status: 'na' })
        }

        // 8. Valuation — P/E not extreme
        if (o.pe_ratio != null && o.pe_ratio > 0) {
          checks.push(o.pe_ratio < 20
            ? { label: 'Valuation (P/E)', detail: `${o.pe_ratio.toFixed(1)}x — reasonable`, status: 'pass' }
            : o.pe_ratio < 40
            ? { label: 'Valuation (P/E)', detail: `${o.pe_ratio.toFixed(1)}x — elevated`, status: 'warn' }
            : { label: 'Valuation (P/E)', detail: `${o.pe_ratio.toFixed(1)}x — very high`, status: 'fail' })
        } else {
          checks.push({ label: 'Valuation (P/E)', detail: o.pe_ratio == null ? 'No P/E data' : 'Negative earnings', status: 'na' })
        }

        const passCount = checks.filter(c => c.status === 'pass').length
        const failCount = checks.filter(c => c.status === 'fail').length
        const overallStatus = failCount >= 3 ? 'fail' : failCount >= 1 || passCount < 4 ? 'warn' : 'pass'

        return (
          <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden">
            <div className="bg-gradient-to-r from-slate-50 to-gray-50/50 px-4 py-2.5 border-b border-gray-100 flex items-center justify-between">
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest">Fundamental Health Checklist</h3>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                overallStatus === 'pass' ? 'bg-green-100 text-green-700' :
                overallStatus === 'warn' ? 'bg-yellow-100 text-yellow-700' :
                'bg-red-100 text-red-700'
              }`}>
                {passCount}/{checks.filter(c => c.status !== 'na').length} checks passed
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 divide-x divide-y divide-gray-50">
              {checks.map(c => (
                <div key={c.label} className="px-3 py-3 flex flex-col gap-1">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-sm ${
                      c.status === 'pass' ? 'text-green-500' :
                      c.status === 'fail' ? 'text-red-500' :
                      c.status === 'warn' ? 'text-amber-500' : 'text-gray-300'
                    }`}>
                      {c.status === 'pass' ? '✓' : c.status === 'fail' ? '✗' : c.status === 'warn' ? '!' : '–'}
                    </span>
                    <span className="text-[10px] font-bold text-gray-600 uppercase tracking-wide">{c.label}</span>
                  </div>
                  <span className={`text-[10px] leading-tight ${
                    c.status === 'pass' ? 'text-green-600' :
                    c.status === 'fail' ? 'text-red-500' :
                    c.status === 'warn' ? 'text-amber-600' : 'text-gray-400'
                  }`}>{c.detail}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })()}

      {/* 3-column metrics grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Valuation */}
        <Card title="Valuation">
          <MetricRow label="EPS (FY0)"        value={o.eps_fy0 != null ? `$${o.eps_fy0.toFixed(2)}` : '—'} />
          <MetricRow label="EPS (FY1 est.)"   value={o.eps_fy1 != null ? `$${o.eps_fy1.toFixed(2)}` : '—'} />
          <MetricRow label="P/E Ratio"        value={fmtX(o.pe_ratio)} />
          <MetricRow label="Forward P/E"      value={fmtX(o.forward_pe)} />
          <MetricRow label="PEG Ratio"        value={fmtX(o.peg_ratio)} />
          <MetricRow label="Price / Book"     value={fmtX(o.price_to_book)} />
          <MetricRow label="Price / Sales"    value={fmtX(o.price_to_sales)} />
          <MetricRow label="EV / EBITDA"      value={fmtX(o.ev_to_ebitda)} />
          <MetricRow label="EV / Revenue"     value={fmtX(o.ev_to_revenue)} />
          <MetricRow label="EV / EBIT"        value={fmtX(o.ev_to_ebit)} />
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
        <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
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
            <div key={label} className={[
              'text-center rounded-lg py-2 px-1',
              val == null ? 'bg-gray-50' : val >= 0 ? 'bg-emerald-50' : 'bg-red-50',
            ].join(' ')}>
              <div className="text-xs text-gray-400 font-semibold mb-1 uppercase tracking-wide">{label}</div>
              <div className={`text-sm font-bold ${signClass(val)}`}>
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

      {/* ── Detected Anomalies ──────────────────────────────────── */}
      {anomalyFlags.length > 0 && (
        <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden">
          <div className="bg-gradient-to-r from-red-50 to-amber-50/40 px-4 py-2.5 border-b border-amber-100 flex items-center gap-2">
            <span className="text-base">🔍</span>
            <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest flex-1">
              Data Anomalies Detected
            </h3>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
              anomalyFlags.some(f => f.severity === 'high')
                ? 'bg-red-100 text-red-700'
                : anomalyFlags.some(f => f.severity === 'medium')
                ? 'bg-amber-100 text-amber-700'
                : 'bg-slate-100 text-slate-600'
            }`}>
              {anomalyFlags.length} flag{anomalyFlags.length !== 1 ? 's' : ''}
            </span>
          </div>

          <div className="divide-y divide-gray-50">
            {anomalyFlags.map((flag, idx) => {
              const meta     = getAnomalyMeta(flag.flag_type)
              const isOpen   = expandedAnomalyIdx === idx
              const detected = flag.detected_at
                ? new Date(flag.detected_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
                : null

              const severityStyle =
                flag.severity === 'high'   ? { badge: 'bg-red-100 text-red-700 border-red-200',   bar: 'bg-red-400',   bg: 'bg-red-50/30'   } :
                flag.severity === 'medium' ? { badge: 'bg-amber-100 text-amber-700 border-amber-200', bar: 'bg-amber-400', bg: 'bg-amber-50/20' } :
                                             { badge: 'bg-slate-100 text-slate-600 border-slate-200', bar: 'bg-slate-300', bg: 'bg-slate-50/20'  }

              return (
                <div key={idx} className={`transition-colors ${isOpen ? severityStyle.bg : 'hover:bg-gray-50/60'}`}>
                  {/* Header row — always visible */}
                  <button
                    className="w-full flex items-start gap-3 px-4 py-3.5 text-left"
                    onClick={() => setExpandedAnomalyIdx(isOpen ? null : idx)}
                  >
                    {/* Severity bar */}
                    <div className={`w-1 self-stretch rounded-full shrink-0 ${severityStyle.bar}`} />

                    {/* Icon + title */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-base leading-none">{meta.icon}</span>
                        <span className="text-sm font-bold text-gray-800">{meta.title}</span>
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wide ${severityStyle.badge}`}>
                          {flag.severity}
                        </span>
                        {detected && (
                          <span className="text-[10px] text-gray-400 ml-auto shrink-0">
                            Detected {detected}
                          </span>
                        )}
                      </div>
                      {/* Short description always shown */}
                      <p className="text-xs text-gray-500 mt-1 leading-relaxed">{flag.description}</p>
                    </div>

                    {/* Chevron */}
                    <span className={`text-gray-400 text-sm shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}>
                      ▾
                    </span>
                  </button>

                  {/* Expanded detail */}
                  {isOpen && (
                    <div className="px-4 pb-4 ml-4 space-y-3">
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="bg-white border border-gray-100 rounded-lg p-3 shadow-sm">
                          <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">What It Is</p>
                          <p className="text-xs text-gray-700 leading-relaxed">{meta.what}</p>
                        </div>
                        <div className={`border rounded-lg p-3 shadow-sm ${
                          flag.severity === 'high'   ? 'bg-red-50 border-red-100' :
                          flag.severity === 'medium' ? 'bg-amber-50 border-amber-100' :
                                                       'bg-slate-50 border-slate-100'
                        }`}>
                          <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1.5">Why It&apos;s an Anomaly</p>
                          <p className="text-xs text-gray-700 leading-relaxed">{meta.why}</p>
                        </div>
                        <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 shadow-sm">
                          <p className="text-[10px] font-bold text-blue-400 uppercase tracking-widest mb-1.5">What To Check</p>
                          <p className="text-xs text-gray-700 leading-relaxed">{meta.action}</p>
                        </div>
                      </div>
                      <p className="text-[10px] text-gray-400 italic">
                        ⚠️ This flag is generated by automated screening and does not constitute financial advice. Always conduct your own research.
                      </p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* AI Deep Analysis (Week 12) */}
      {!aiLoaded && !aiLoading && (
        <div className="border border-dashed border-blue-200 rounded-xl p-5 text-center bg-blue-50/30">
          <p className="text-sm font-semibold text-gray-700 mb-1">AI Deep Analysis</p>
          <p className="text-xs text-gray-400 mb-3">Get Claude{"'"}s bull/bear case, key catalysts, and risks</p>
          <button onClick={() => loadAI()}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500
                       text-white text-sm font-semibold rounded-lg transition-colors">
            ⚡ Generate AI Analysis
          </button>
        </div>
      )}

      {aiLoading && (
        <div className="border border-blue-100 rounded-xl p-5 text-center animate-pulse bg-blue-50/20">
          <p className="text-sm text-blue-600 font-medium">Claude is analysing {code}…</p>
        </div>
      )}

      {aiError && (
        <div className="border border-red-100 rounded-xl p-4 text-center">
          <p className="text-sm text-red-600">{aiError}</p>
          <button onClick={() => { setAiLoaded(false); loadAI(true) }}
            className="text-xs text-blue-600 hover:underline mt-1">Retry</button>
        </div>
      )}

      {aiData && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">AI Deep Analysis</span>
            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-semibold">⚡ Claude</span>
            {aiData.cached && <span className="text-xs text-gray-400">cached</span>}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Bull Case">
              <ul className="space-y-2">
                {aiData.bull_case.map((p, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-emerald-500 mt-0.5 shrink-0 font-bold">↑</span>{p}
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Bear Case">
              <ul className="space-y-2">
                {aiData.bear_case.map((p, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-red-500 mt-0.5 shrink-0 font-bold">↓</span>{p}
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}

      {/* ── Mining Metrics (miners only) ────────────────────────── */}
      <MiningMetricsPanel code={code} />

      {/* ── REIT Metrics (REITs only) ───────────────────────────── */}
      <ReitMetricsPanel code={code} />

      {/* ── Capital Raises ──────────────────────────────────────── */}
      <CapitalRaisesPanel code={code} />

    </div>
  )
}

// ── Financials Tab ────────────────────────────────────────────

function AnnualTable({ financials }: { financials: FinancialsResponse }) {
  const years = [...financials.years].reverse()   // oldest → newest

  // ── YoY growth helper ────────────────────────────────────────
  const yoyGrowth = (key: keyof AnnualFinancialsRow): (number | null)[] =>
    years.map((yr, i) => {
      if (i === 0) return null
      const curr = yr[key] as number | null
      const prev = years[i - 1][key] as number | null
      if (curr == null || prev == null || prev === 0) return null
      return (curr - prev) / Math.abs(prev)
    })

  const fmtGrowth = (v: number | null) => {
    if (v == null) return '—'
    const pct = v * 100
    const cls = pct >= 0 ? 'text-green-600' : 'text-red-500'
    return <span className={cls}>{pct >= 0 ? '+' : ''}{pct.toFixed(1)}%</span>
  }

  const revenueGrowth    = yoyGrowth('revenue')
  const netProfitGrowth  = yoyGrowth('net_profit')
  const epsGrowth        = yoyGrowth('eps')

  // ── Earnings Quality (CFO / Net Profit) ──────────────────────
  const earningsQuality: (number | null)[] = years.map(yr => {
    if (yr.cfo == null || yr.net_profit == null || yr.net_profit === 0) return null
    return yr.cfo / Math.abs(yr.net_profit)
  })

  const fmtEQ = (v: number | null) => {
    if (v == null) return '—'
    const cls = v >= 1.0 ? 'text-green-600 font-semibold' : v >= 0.5 ? 'text-amber-600' : 'text-red-500'
    return <span className={cls}>{v.toFixed(2)}x{v >= 1 ? ' ✓' : ''}</span>
  }

  // ── Operating margin (EBIT / Revenue) ────────────────────────
  const operatingMargins: (number | null)[] = years.map(yr =>
    yr.ebit != null && yr.revenue != null && yr.revenue > 0
      ? yr.ebit / yr.revenue : null
  )

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
    { label: 'Gross Margin',     key: 'gpm',          fmt: formatRatio },
    { label: 'EBITDA Margin',    key: 'ebitda_margin', fmt: formatRatio },
    { label: 'Net Margin',       key: 'npm',           fmt: formatRatio },
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

  // ── Trend chart data ─────────────────────────────────────────
  const chartData = years.map(yr => ({
    year: `FY${yr.fiscal_year}`,
    revenue: yr.revenue,
    net_profit: yr.net_profit,
    eps: yr.eps,
    gross_margin: yr.gpm != null ? yr.gpm * 100 : null,
    net_margin: yr.npm != null ? yr.npm * 100 : null,
  }))

  const hasRevenue    = years.some(y => y.revenue != null)
  const hasEPS        = years.some(y => y.eps != null)
  const hasMargins    = years.some(y => y.gpm != null || y.npm != null)

  return (
    <div className="space-y-4">
      {/* ── Trend Charts ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* Revenue & Net Profit */}
        {hasRevenue && (
          <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden md:col-span-2">
            <div className="bg-gradient-to-r from-slate-50 to-gray-50/50 px-4 py-2.5 border-b border-gray-100">
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest">Revenue &amp; Net Profit Trend (AUD)</h3>
            </div>
            <div className="p-3">
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="year" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickFormatter={v => { const n = v as number; return Math.abs(n) >= 1000 ? `$${(n/1000).toFixed(0)}B` : `$${n.toFixed(0)}M` }}
                    width={52} />
                  <Tooltip
                    formatter={(v: unknown, name: unknown) => [
                      (() => { const n = v as number; return Math.abs(n) >= 1000 ? `$${(n/1000).toFixed(1)}B` : `$${n.toFixed(0)}M` })(),
                      name === 'revenue' ? 'Revenue' : 'Net Profit'
                    ]}
                  />
                  <Bar dataKey="revenue"    name="revenue"    fill="#3b82f6" fillOpacity={0.8} radius={[2,2,0,0]} maxBarSize={28} />
                  <Bar dataKey="net_profit" name="net_profit" fill="#10b981" fillOpacity={0.8} radius={[2,2,0,0]} maxBarSize={28} />
                </ComposedChart>
              </ResponsiveContainer>
              <div className="flex gap-4 mt-1 text-[10px] text-gray-400">
                <span><span className="inline-block w-2.5 h-2.5 rounded-sm bg-blue-500 mr-1" />Revenue</span>
                <span><span className="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-500 mr-1" />Net Profit</span>
              </div>
            </div>
          </div>
        )}

        {/* EPS Trend */}
        {hasEPS && (
          <div className="bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden">
            <div className="bg-gradient-to-r from-slate-50 to-gray-50/50 px-4 py-2.5 border-b border-gray-100">
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest">EPS Trend</h3>
            </div>
            <div className="p-3">
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="year" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickFormatter={v => `$${(v as number).toFixed(2)}`}
                    width={44} />
                  <Tooltip formatter={(v: unknown) => [`$${(v as number).toFixed(3)}`, 'EPS']} />
                  <Bar dataKey="eps" fill="#8b5cf6" fillOpacity={0.85} radius={[2,2,0,0]} maxBarSize={28} />
                  <Line type="monotone" dataKey="eps" stroke="#8b5cf6" dot={false} strokeWidth={2} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Margins Trend */}
        {hasMargins && (
          <div className={`bg-white border border-gray-100 rounded-xl shadow-sm overflow-hidden ${!hasEPS ? 'md:col-span-1' : 'md:col-span-3'}`}>
            <div className="bg-gradient-to-r from-slate-50 to-gray-50/50 px-4 py-2.5 border-b border-gray-100">
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest">Profit Margins Trend (%)</h3>
            </div>
            <div className="p-3">
              <ResponsiveContainer width="100%" height={hasEPS ? 100 : 160}>
                <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="year" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickFormatter={v => `${(v as number).toFixed(0)}%`}
                    width={36} />
                  <Tooltip formatter={(v: unknown, name: unknown) => [`${(v as number).toFixed(1)}%`, name === 'gross_margin' ? 'Gross Margin' : 'Net Margin']} />
                  <Line type="monotone" dataKey="gross_margin" stroke="#3b82f6" dot={false} strokeWidth={2} name="gross_margin" />
                  <Line type="monotone" dataKey="net_margin"   stroke="#10b981" dot={false} strokeWidth={2} name="net_margin" />
                </ComposedChart>
              </ResponsiveContainer>
              <div className="flex gap-4 mt-1 text-[10px] text-gray-400">
                <span><span className="inline-block w-2.5 h-2 bg-blue-500 mr-1" />Gross</span>
                <span><span className="inline-block w-2.5 h-2 bg-emerald-500 mr-1" />Net</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Financials Table ────────────────────────────────────── */}
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

            {/* YoY growth rates */}
            <tr>
              <td colSpan={years.length + 1} className="pt-3 pb-1">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">YoY Growth</span>
              </td>
            </tr>
            {[
              { label: 'Revenue Growth',    data: revenueGrowth },
              { label: 'Net Profit Growth', data: netProfitGrowth },
              { label: 'EPS Growth',        data: epsGrowth },
            ].map(({ label, data }) => (
              <tr key={label} className="hover:bg-gray-50">
                <td className="py-1.5 pr-4 text-sm text-gray-500 whitespace-nowrap">{label}</td>
                {years.map((yr, i) => (
                  <td key={yr.fiscal_year} className="py-1.5 text-sm text-right pl-4">
                    {fmtGrowth(data[i])}
                  </td>
                ))}
              </tr>
            ))}

            <TableSection title="Margins" rows={marginRows} />

            {/* Operating Margin (computed) */}
            <tr className="hover:bg-gray-50">
              <td className="py-1.5 pr-4 text-sm text-gray-600 whitespace-nowrap">Operating Margin</td>
              {years.map((yr, i) => (
                <td key={yr.fiscal_year} className="py-1.5 text-sm text-right font-medium text-gray-900 pl-4">
                  {formatRatio(operatingMargins[i])}
                </td>
              ))}
            </tr>

            <TableSection title="Balance Sheet (AUD)" rows={bsRows} />
            <TableSection title="Cash Flow (AUD)" rows={cfRows} />

            {/* Earnings Quality */}
            <tr className="hover:bg-gray-50">
              <td className="py-1.5 pr-4 text-sm text-gray-600 whitespace-nowrap">
                <span>Earnings Quality</span>
                <span className="block text-[10px] text-gray-400">CFO / Net Profit (≥1 = real cash)</span>
              </td>
              {years.map((yr, i) => (
                <td key={yr.fiscal_year} className="py-1.5 text-sm text-right pl-4">
                  {fmtEQ(earningsQuality[i])}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
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
  const growthRows: HRow[] = [
    { label: 'Revenue HoH',     key: 'revenue_growth_hoh',      fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
    { label: 'Revenue YoY',     key: 'revenue_growth_yoy',      fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
    { label: 'Net Profit HoH',  key: 'net_profit_growth_hoh',   fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
    { label: 'EPS HoH',         key: 'eps_growth_hoh',          fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
    { label: 'EPS YoY',         key: 'eps_growth_yoy',          fmt: v => v != null ? `${v >= 0 ? '+' : ''}${(v*100).toFixed(1)}%` : '—' },
  ]

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

// ── Key Metrics Snapshot ──────────────────────────────────────

function KeyMetricsPanel({ o }: { o: CompanyOverview }) {
  type KMRow = { label: string; value: string; highlight?: 'green' | 'red' | 'neutral' }

  const valuation: KMRow[] = [
    { label: 'P/E Ratio',     value: fmtX(o.pe_ratio),
      highlight: o.pe_ratio == null ? 'neutral' : o.pe_ratio > 0 && o.pe_ratio < 20 ? 'green' : o.pe_ratio > 40 ? 'red' : 'neutral' },
    { label: 'Forward P/E',   value: fmtX(o.forward_pe),
      highlight: o.forward_pe == null ? 'neutral' : o.forward_pe > 0 && o.forward_pe < 18 ? 'green' : o.forward_pe > 35 ? 'red' : 'neutral' },
    { label: 'PEG Ratio',     value: fmtX(o.peg_ratio),
      highlight: o.peg_ratio == null ? 'neutral' : o.peg_ratio < 1 ? 'green' : o.peg_ratio > 2 ? 'red' : 'neutral' },
    { label: 'P/B Ratio',     value: fmtX(o.price_to_book),
      highlight: o.price_to_book == null ? 'neutral' : o.price_to_book < 1.5 ? 'green' : o.price_to_book > 5 ? 'red' : 'neutral' },
    { label: 'EV / EBITDA',   value: fmtX(o.ev_to_ebitda),
      highlight: o.ev_to_ebitda == null ? 'neutral' : o.ev_to_ebitda < 10 ? 'green' : o.ev_to_ebitda > 25 ? 'red' : 'neutral' },
    { label: 'EV / Revenue',  value: fmtX(o.ev_to_revenue) },
  ]

  const earnings: KMRow[] = [
    { label: 'EPS (FY0 actual)',  value: o.eps_fy0 != null ? `$${o.eps_fy0.toFixed(2)}` : '—',
      highlight: o.eps_fy0 == null ? 'neutral' : o.eps_fy0 > 0 ? 'green' : 'red' },
    { label: 'EPS (FY1 est.)',    value: o.eps_fy1 != null ? `$${o.eps_fy1.toFixed(2)}` : '—',
      highlight: o.eps_fy1 == null ? 'neutral' : o.eps_fy1 > 0 ? 'green' : 'red' },
    { label: 'Dividend Yield',    value: o.dividend_yield != null ? `${(o.dividend_yield * 100).toFixed(2)}%` : '—',
      highlight: o.dividend_yield != null && o.dividend_yield > 0.04 ? 'green' : 'neutral' },
    { label: 'Grossed-Up Yield ★', value: o.grossed_up_yield != null ? `${(o.grossed_up_yield * 100).toFixed(2)}%` : '—',
      highlight: o.grossed_up_yield != null && o.grossed_up_yield > 0.06 ? 'green' : 'neutral' },
    { label: 'Franking',          value: o.franking_pct != null ? `${o.franking_pct.toFixed(0)}%` : '—',
      highlight: o.franking_pct === 100 ? 'green' : 'neutral' },
    { label: 'FCF Yield',         value: o.fcf_yield != null ? `${(o.fcf_yield * 100).toFixed(2)}%` : '—',
      highlight: o.fcf_yield != null && o.fcf_yield > 0.04 ? 'green' : o.fcf_yield != null && o.fcf_yield < 0 ? 'red' : 'neutral' },
  ]

  const growth: KMRow[] = [
    { label: 'Revenue Growth (1Y)', value: signedPct(o.revenue_growth_1y),
      highlight: o.revenue_growth_1y == null ? 'neutral' : o.revenue_growth_1y > 0 ? 'green' : 'red' },
    { label: 'Earnings Growth (1Y)', value: signedPct(o.earnings_growth_1y),
      highlight: o.earnings_growth_1y == null ? 'neutral' : o.earnings_growth_1y > 0 ? 'green' : 'red' },
    ...(o.revenue_growth_hoh != null ? [{
      label: 'Revenue Growth HoH ★', value: signedPct(o.revenue_growth_hoh),
      highlight: (o.revenue_growth_hoh > 0 ? 'green' : 'red') as 'green' | 'red',
    }] : []),
    { label: 'D/E Ratio',           value: fmtX(o.debt_to_equity),
      highlight: o.debt_to_equity == null ? 'neutral' : o.debt_to_equity < 0.3 ? 'green' : o.debt_to_equity > 2 ? 'red' : 'neutral' },
    { label: 'Free Cash Flow (FY0)', value: fmtM(o.fcf_fy0),
      highlight: o.fcf_fy0 == null ? 'neutral' : o.fcf_fy0 > 0 ? 'green' : 'red' },
    { label: 'CFO (FY0)',            value: fmtM(o.cfo_fy0) },
  ]

  const col = (rows: KMRow[]) => (
    <div className="divide-y divide-gray-50">
      {rows.map(r => (
        <div key={r.label} className="flex items-baseline justify-between py-1.5 group hover:bg-blue-50/30 -mx-1 px-1 rounded transition-colors">
          <span className="text-xs text-gray-400 font-medium mr-2">{r.label}</span>
          <span className={`text-sm font-semibold whitespace-nowrap ${
            r.highlight === 'green' ? 'text-emerald-600' :
            r.highlight === 'red'   ? 'text-red-500' :
            'text-gray-800'
          }`}>{r.value}</span>
        </div>
      ))}
    </div>
  )

  return (
    <div className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm">
      <div className="bg-gradient-to-r from-slate-50 to-gray-50/50 px-4 py-2.5 border-b border-gray-100">
        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest">Fundamental Snapshot</h3>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-gray-100 p-4 gap-0">
        <div className="sm:pr-4 pb-4 sm:pb-0">
          <p className="text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-2">Valuation</p>
          {col(valuation)}
        </div>
        <div className="sm:px-4 py-4 sm:py-0">
          <p className="text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-2">Earnings &amp; Income</p>
          {col(earnings)}
        </div>
        <div className="sm:pl-4 pt-4 sm:pt-0">
          <p className="text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-2">Growth &amp; Cash Flow</p>
          {col(growth)}
        </div>
      </div>
    </div>
  )
}

// ── Mining Metrics Panel ──────────────────────────────────────

function MiningMetricsPanel({ code }: { code: string }) {
  const [data, setData] = useState<MiningMetrics | null>(null)

  useEffect(() => {
    getMiningMetrics(code).then(setData).catch(() => {})
  }, [code])

  if (!data || !data.is_miner) return null

  const fmt = (v: number | null, prefix = '', suffix = '', dp = 2) =>
    v != null ? `${prefix}${v.toFixed(dp)}${suffix}` : '—'

  const metrics = [
    ...(data.primary_commodity ? [{ label: 'Primary Commodity', value: data.primary_commodity }] : []),
    { label: 'AISC', value: data.aisc_per_oz != null ? `US$${data.aisc_per_oz.toFixed(0)}/oz` : data.aisc_per_tonne != null ? `US$${data.aisc_per_tonne.toFixed(0)}/t` : '—' },
    { label: 'Cash Cost', value: data.cash_cost_per_oz != null ? `US$${data.cash_cost_per_oz.toFixed(0)}/oz` : '—' },
    { label: 'Ore Reserves', value: data.ore_reserves_mt != null ? `${data.ore_reserves_mt.toFixed(1)} Mt` : '—' },
    { label: 'Mineral Resources', value: data.mineral_resources_mt != null ? `${data.mineral_resources_mt.toFixed(1)} Mt` : '—' },
    { label: 'Reserve Grade', value: data.reserve_grade != null ? `${data.reserve_grade.toFixed(2)} g/t` : '—' },
    { label: 'Reserve Life', value: data.reserve_life_yrs != null ? `${data.reserve_life_yrs.toFixed(1)} yrs` : '—' },
    { label: 'Production (TTM)', value: data.production_oz_ttm != null ? `${(data.production_oz_ttm / 1000).toFixed(0)}k oz` : data.production_kt_ttm != null ? `${data.production_kt_ttm.toFixed(0)} kt` : '—' },
    { label: 'Sustaining CapEx', value: data.sustaining_capex_m != null ? `A$${data.sustaining_capex_m.toFixed(0)}M` : '—' },
    { label: 'Growth CapEx', value: data.growth_capex_m != null ? `A$${data.growth_capex_m.toFixed(0)}M` : '—' },
  ]

  const hasDetailedData = data.has_data && (data.aisc_per_oz != null || data.ore_reserves_mt != null)

  return (
    <div className="bg-white border border-amber-100 rounded-xl overflow-hidden shadow-sm">
      <div className="bg-gradient-to-r from-amber-50 to-yellow-50/50 px-4 py-2.5 border-b border-amber-100 flex items-center gap-2">
        <span className="text-base">⛏️</span>
        <h3 className="text-xs font-bold text-amber-700 uppercase tracking-widest">Mining Metrics</h3>
        {data.primary_commodity && (
          <span className="ml-auto text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-semibold">
            {data.primary_commodity}
          </span>
        )}
      </div>
      {!hasDetailedData ? (
        <div className="px-4 py-6 text-center text-sm text-gray-400">
          <p>Detailed mining metrics (AISC, reserves, production) not yet available.</p>
          <p className="mt-1 text-xs">Data is added from quarterly reports as it becomes available.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-0 divide-x divide-y divide-gray-50 p-4">
          {metrics.filter(m => m.value !== '—').map(m => (
            <div key={m.label} className="px-3 py-2">
              <p className="text-[10px] text-gray-400 font-semibold uppercase tracking-wide">{m.label}</p>
              <p className="text-sm font-bold text-gray-800 mt-0.5">{m.value}</p>
            </div>
          ))}
        </div>
      )}
      {data.report_period && (
        <div className="px-4 pb-2 text-right">
          <span className="text-[10px] text-gray-300">As at {data.report_period}</span>
        </div>
      )}
    </div>
  )
}


// ── REIT Metrics Panel ────────────────────────────────────────

function ReitMetricsPanel({ code }: { code: string }) {
  const [data, setData] = useState<ReitMetrics | null>(null)

  useEffect(() => {
    getReitMetrics(code).then(setData).catch(() => {})
  }, [code])

  if (!data || !data.is_reit) return null

  const fmtPct  = (v: number | null) => v != null ? `${(v * 100).toFixed(2)}%` : '—'
  const fmtX    = (v: number | null) => v != null ? `${v.toFixed(1)}x` : '—'
  const fmtDollar = (v: number | null, dp = 4) => v != null ? `$${v.toFixed(dp)}` : '—'

  const premium = data.premium_to_nta
  const premiumLabel = premium != null
    ? premium >= 0
      ? `+${(premium * 100).toFixed(1)}% premium`
      : `${(premium * 100).toFixed(1)}% discount`
    : '—'
  const premiumColor = premium != null
    ? premium >= 0.05 ? 'text-red-500' : premium <= -0.05 ? 'text-emerald-600' : 'text-gray-700'
    : 'text-gray-400'

  const metrics = [
    { label: 'REIT Sector',      value: data.reit_sector ?? '—' },
    { label: 'NTA/Unit',         value: fmtDollar(data.nta_per_unit) },
    { label: 'Premium / Discount', value: premiumLabel, color: premiumColor },
    { label: 'FFO/Unit',         value: fmtDollar(data.ffo_per_unit) },
    { label: 'P/FFO',            value: fmtX(data.price_to_ffo) },
    { label: 'WALE',             value: data.wale_yrs != null ? `${data.wale_yrs.toFixed(1)} yrs` : '—' },
    { label: 'Occupancy',        value: data.occupancy_pct != null ? `${data.occupancy_pct.toFixed(1)}%` : '—' },
    { label: 'Gearing',          value: data.gearing_pct != null ? `${data.gearing_pct.toFixed(1)}%` : '—' },
    { label: 'Interest Cover',   value: fmtX(data.interest_cover) },
    { label: 'Dist. Yield',      value: fmtPct(data.distribution_yield) },
  ]

  const hasDetailedData = data.has_data && (data.nta_per_unit != null || data.wale_yrs != null)

  return (
    <div className="bg-white border border-sky-100 rounded-xl overflow-hidden shadow-sm">
      <div className="bg-gradient-to-r from-sky-50 to-blue-50/50 px-4 py-2.5 border-b border-sky-100 flex items-center gap-2">
        <span className="text-base">🏢</span>
        <h3 className="text-xs font-bold text-sky-700 uppercase tracking-widest">REIT Metrics</h3>
        {data.reit_sector && (
          <span className="ml-auto text-xs bg-sky-100 text-sky-700 px-2 py-0.5 rounded-full font-semibold">
            {data.reit_sector}
          </span>
        )}
      </div>
      {!hasDetailedData ? (
        <div className="px-4 py-6 text-center text-sm text-gray-400">
          <p>Detailed REIT metrics (FFO, NTA, WALE, occupancy) not yet available.</p>
          <p className="mt-1 text-xs">Data is added from half-year and annual results as it becomes available.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-0 divide-x divide-y divide-gray-50 p-4">
          {metrics.filter(m => m.value !== '—').map(m => (
            <div key={m.label} className="px-3 py-2">
              <p className="text-[10px] text-gray-400 font-semibold uppercase tracking-wide">{m.label}</p>
              <p className={`text-sm font-bold mt-0.5 ${(m as any).color ?? 'text-gray-800'}`}>{m.value}</p>
            </div>
          ))}
        </div>
      )}
      {data.report_period && (
        <div className="px-4 pb-2 text-right">
          <span className="text-[10px] text-gray-300">As at {data.report_period}</span>
        </div>
      )}
    </div>
  )
}


// ── Capital Raises Panel ──────────────────────────────────────

const RAISE_LABELS: Record<string, string> = {
  placement:         'Placement',
  spp:               'SPP',
  rights_issue:      'Rights Issue',
  entitlement_offer: 'Entitlement Offer',
  ipo:               'IPO',
  drp:               'DRP',
}

const RAISE_COLORS: Record<string, string> = {
  placement:         'bg-purple-100 text-purple-700',
  spp:               'bg-blue-100 text-blue-700',
  rights_issue:      'bg-orange-100 text-orange-700',
  entitlement_offer: 'bg-orange-100 text-orange-700',
  ipo:               'bg-emerald-100 text-emerald-700',
  drp:               'bg-slate-100 text-slate-600',
}

function CapitalRaisesPanel({ code }: { code: string }) {
  const [raises, setRaises] = useState<CapitalRaiseEvent[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    getCapitalRaises(code)
      .then(r => { setRaises(r.raises); setLoaded(true) })
      .catch(() => setLoaded(true))
  }, [code])

  if (!loaded || raises.length === 0) return null

  return (
    <div className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm">
      <div className="bg-gradient-to-r from-slate-50 to-gray-50/50 px-4 py-2.5 border-b border-gray-100 flex items-center gap-2">
        <span className="text-base">💰</span>
        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest">Capital Raises</h3>
        <span className="ml-auto text-xs text-gray-300">{raises.length} event{raises.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="divide-y divide-gray-50">
        {raises.map((r, i) => (
          <div key={i} className="flex items-start gap-3 px-4 py-3">
            <span className={`shrink-0 text-xs font-bold px-2 py-0.5 rounded-full mt-0.5 ${RAISE_COLORS[r.raise_type] ?? 'bg-gray-100 text-gray-600'}`}>
              {RAISE_LABELS[r.raise_type] ?? r.raise_type}
            </span>
            <div className="flex-1 min-w-0">
              {r.title && (
                <p className="text-xs text-gray-600 leading-snug truncate" title={r.title ?? undefined}>{r.title}</p>
              )}
              <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1">
                {r.amount_m != null && (
                  <span className="text-xs font-semibold text-gray-800">A${r.amount_m.toFixed(0)}M</span>
                )}
                {r.price_per_share != null && (
                  <span className="text-xs text-gray-500">@ ${r.price_per_share.toFixed(3)}/share</span>
                )}
                {r.discount_pct != null && (
                  <span className={`text-xs font-medium ${r.discount_pct > 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                    {r.discount_pct > 0 ? `-${r.discount_pct.toFixed(1)}% discount` : `+${Math.abs(r.discount_pct).toFixed(1)}% premium`}
                  </span>
                )}
                <span className="text-xs text-gray-400">{r.announcement_date}</span>
              </div>
            </div>
            {r.url && (
              <a href={r.url} target="_blank" rel="noopener noreferrer"
                 className="shrink-0 text-blue-400 hover:text-blue-600 mt-0.5">
                <ExternalLink size={13} />
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}


function FinancialsTab({
  overview,
  financials,
  halfYearly,
  period,
  onPeriodChange,
}: {
  overview: CompanyOverview | null
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
      {/* Key Metrics Snapshot */}
      {overview && <KeyMetricsPanel o={overview} />}

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

const PRICE_PERIODS = ['1W', '1M', '3M', '6M', '1Y', '3Y', '5Y'] as const
type PricePeriod = typeof PRICE_PERIODS[number]

function TechnicalsTab({
  o,
  prices,
  pricesLoading,
  pricePeriod,
  onPeriodChange,
}: {
  o: CompanyOverview
  prices: PricesResponse | null
  pricesLoading: boolean
  pricePeriod: PricePeriod
  onPeriodChange: (p: PricePeriod) => void
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

      {/* Price + Volume chart */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {/* Header with period selector */}
        <div className="px-4 pt-4 pb-2 flex items-center justify-between flex-wrap gap-2">
          <span className="text-sm font-semibold text-slate-700">Price &amp; Volume</span>
          <div className="flex items-center gap-1">
            {PRICE_PERIODS.map(p => (
              <button
                key={p}
                onClick={() => onPeriodChange(p)}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                  pricePeriod === p
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-500 hover:bg-slate-100'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {pricesLoading ? (
          <div className="h-56 flex items-center justify-center text-sm text-slate-400">Loading chart…</div>
        ) : prices && prices.data.length > 0 ? (
          <div className="px-2 pb-3">
            {/* Price line chart */}
            <ResponsiveContainer width="100%" height={180}>
              <ComposedChart data={prices.data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  tickFormatter={d => d.slice(5)}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="price"
                  domain={['auto', 'auto']}
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  tickFormatter={v => `$${Number(v).toFixed(2)}`}
                  width={58}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null
                    const close = payload.find(p => p.dataKey === 'close')
                    const vol   = payload.find(p => p.dataKey === 'volume')
                    return (
                      <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-xs">
                        <div className="font-semibold text-slate-600 mb-1">{label}</div>
                        {close && <div className="text-blue-600">Close: ${Number(close.value).toFixed(3)}</div>}
                        {vol   && <div className="text-slate-500">Vol: {Number(vol.value) >= 1_000_000 ? (Number(vol.value)/1_000_000).toFixed(1)+'M' : Number(vol.value) >= 1_000 ? (Number(vol.value)/1_000).toFixed(0)+'K' : vol.value}</div>}
                      </div>
                    )
                  }}
                />
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="close"
                  stroke="#2563eb"
                  dot={false}
                  strokeWidth={1.5}
                />
              </ComposedChart>
            </ResponsiveContainer>

            {/* Volume bar chart */}
            <ResponsiveContainer width="100%" height={70}>
              <ComposedChart data={prices.data} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                <XAxis dataKey="date" hide />
                <YAxis
                  tick={{ fontSize: 9, fill: '#94a3b8' }}
                  tickFormatter={v => Number(v) >= 1_000_000 ? (Number(v)/1_000_000).toFixed(0)+'M' : Number(v) >= 1_000 ? (Number(v)/1_000).toFixed(0)+'K' : String(v)}
                  width={58}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null
                    const vol = payload[0]
                    return (
                      <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-xs">
                        <div className="font-semibold text-slate-600 mb-1">{label}</div>
                        <div className="text-slate-500">Vol: {Number(vol.value) >= 1_000_000 ? (Number(vol.value)/1_000_000).toFixed(1)+'M' : Number(vol.value) >= 1_000 ? (Number(vol.value)/1_000).toFixed(0)+'K' : vol.value}</div>
                      </div>
                    )
                  }}
                />
                <Bar dataKey="volume" fill="#cbd5e1" radius={[1,1,0,0]} maxBarSize={8} />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="text-center text-xs text-slate-400 mt-1">Volume</div>
          </div>
        ) : (
          <div className="h-56 flex items-center justify-center text-sm text-slate-400">
            Price chart data not available
          </div>
        )}
      </div>

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

      {/* Upcoming Dividend */}
      {(() => {
        if (history.length === 0) return null
        const today = new Date().toISOString().slice(0, 10)

        // Check for a confirmed future record already in the data
        const confirmed = history.find(d => d.ex_date >= today)

        // Frequency analysis: compute median gap between ex-dates (days)
        const sortedDates = [...history].map(d => d.ex_date).sort()
        let freqDays = 182 // default semi-annual
        if (sortedDates.length >= 2) {
          const gaps: number[] = []
          for (let i = 1; i < Math.min(sortedDates.length, 8); i++) {
            const gap = Math.round(
              (new Date(sortedDates[i]).getTime() - new Date(sortedDates[i - 1]).getTime()) / 86400000
            )
            if (gap > 0) gaps.push(gap)
          }
          if (gaps.length) freqDays = Math.round(gaps.reduce((a, b) => a + b) / gaps.length)
        }

        const freqLabel =
          freqDays <= 45  ? 'Monthly' :
          freqDays <= 100 ? 'Quarterly' :
          freqDays <= 200 ? 'Semi-Annual' : 'Annual'

        // Estimate next ex-div = last ex-date + frequency (if no confirmed future date)
        const lastDiv = history[0]
        let exDate: string | null = null
        let isEstimated = false

        if (confirmed) {
          exDate = confirmed.ex_date
        } else if (lastDiv?.ex_date) {
          const lastMs = new Date(lastDiv.ex_date).getTime()
          const nextMs = lastMs + freqDays * 86400000
          exDate = new Date(nextMs).toISOString().slice(0, 10)
          isEstimated = true
        }

        if (!exDate) return null

        // Estimate payment date = ex-date + avg historical ex→pay lag
        let payDate: string | null = confirmed?.payment_date ?? null
        if (!payDate && !confirmed) {
          const lags = history
            .filter(d => d.ex_date && d.payment_date)
            .slice(0, 6)
            .map(d => Math.round((new Date(d.payment_date!).getTime() - new Date(d.ex_date).getTime()) / 86400000))
            .filter(l => l > 0 && l < 120)
          if (lags.length) {
            const avgLag = Math.round(lags.reduce((a, b) => a + b) / lags.length)
            const payMs = new Date(exDate).getTime() + avgLag * 86400000
            payDate = new Date(payMs).toISOString().slice(0, 10)
          }
        }

        const amount = confirmed?.amount ?? lastDiv?.amount ?? null
        const franking = confirmed?.franking_pct ?? lastDiv?.franking_pct ?? null
        const grossedUp = amount != null && franking != null
          ? amount * (1 + (franking / 100) * (30 / 70))
          : null

        const daysToEx = Math.ceil((new Date(exDate).getTime() - new Date(today).getTime()) / 86400000)
        const isPast = daysToEx < 0

        return (
          <div className={`border rounded-xl overflow-hidden ${
            isPast ? 'bg-gray-50 border-gray-200' : 'bg-gradient-to-br from-emerald-50 to-green-50 border-emerald-100'
          }`}>
            <div className={`px-4 py-2.5 border-b flex items-center gap-2 ${
              isPast ? 'border-gray-200' : 'border-emerald-100'
            }`}>
              {!isPast && <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />}
              <h3 className={`text-xs font-bold uppercase tracking-widest ${
                isPast ? 'text-gray-400' : 'text-emerald-700'
              }`}>
                {isPast ? 'Last Dividend' : 'Upcoming Dividend'}
              </h3>
              <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ml-1 ${
                isEstimated
                  ? 'bg-amber-100 text-amber-600'
                  : 'bg-emerald-100 text-emerald-600'
              }`}>
                {isEstimated ? `Est. · ${freqLabel}` : 'Confirmed'}
              </span>
              {!isPast && daysToEx <= 90 && (
                <span className="ml-auto text-xs font-semibold text-emerald-600 bg-emerald-100 px-2 py-0.5 rounded-full">
                  {daysToEx === 0 ? 'Today' : daysToEx === 1 ? 'Tomorrow' : `In ${daysToEx} days`}
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-emerald-100/60 p-0">
              <div className="px-4 py-3 flex flex-col gap-0.5">
                <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wide">Ex-Dividend Date</span>
                <span className="text-sm font-bold text-gray-800">{exDate}</span>
                {isEstimated && <span className="text-[10px] text-amber-500">estimated</span>}
              </div>
              <div className="px-4 py-3 flex flex-col gap-0.5">
                <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wide">Payment Date</span>
                <span className="text-sm font-bold text-gray-800">{payDate ?? '—'}</span>
                {isEstimated && payDate && <span className="text-[10px] text-amber-500">estimated</span>}
              </div>
              <div className="px-4 py-3 flex flex-col gap-0.5">
                <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wide">Est. DPS</span>
                <span className="text-sm font-bold text-gray-800">
                  {amount != null ? `$${amount.toFixed(4)}` : '—'}
                  {franking != null && (
                    <span className={`ml-1.5 text-xs font-medium px-1 py-0.5 rounded ${
                      franking === 100 ? 'bg-green-100 text-green-700' :
                      franking > 0 ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-500'
                    }`}>{franking.toFixed(0)}% franked</span>
                  )}
                </span>
              </div>
              <div className="px-4 py-3 flex flex-col gap-0.5">
                <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wide">Grossed-Up DPS</span>
                <span className={`text-sm font-bold ${isPast ? 'text-gray-700' : 'text-emerald-700'}`}>
                  {grossedUp != null ? `$${grossedUp.toFixed(4)}` : '—'}
                </span>
              </div>
            </div>
            {isEstimated && (
              <div className="px-4 pb-2.5 text-[10px] text-amber-500">
                * Next ex-date estimated based on {freqLabel.toLowerCase()} payment frequency. Confirm via company announcements.
              </div>
            )}
          </div>
        )
      })()}

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


// ── Documents Tab ─────────────────────────────────────────────

type AnnFilter = 'all' | 'sensitive' | 'type'

function formatFileSize(kb: number | null): string {
  if (kb == null) return ''
  if (kb < 1024) return `${kb} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

function formatAnnDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' })
}

function formatAnnTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function DocumentsTab({ code }: { code: string }) {
  const [data, setData]       = useState<AnnouncementsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [filter, setFilter]   = useState<'all' | 'sensitive'>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  useEffect(() => {
    setLoading(true)
    getCompanyAnnouncements(code, 50)
      .then(r => { setData(r); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [code])

  if (loading) return (
    <div className="space-y-3 animate-pulse">
      {[1,2,3,4,5].map(i => (
        <div key={i} className="flex gap-3 py-3 border-b border-gray-100">
          <div className="h-4 bg-gray-100 rounded w-24 shrink-0" />
          <div className="h-4 bg-gray-100 rounded flex-1" />
        </div>
      ))}
    </div>
  )

  if (error) return (
    <div className="text-center py-12">
      <p className="text-red-500 font-medium">Could not load announcements</p>
      <p className="text-sm text-gray-400 mt-1">{error}</p>
    </div>
  )

  if (!data || data.data.length === 0) return (
    <div className="text-center py-16">
      <FileText className="w-8 h-8 text-gray-300 mx-auto mb-3" />
      <p className="text-gray-500 font-medium">No announcements available</p>
      <p className="text-sm text-gray-400 mt-1 mb-4">ASX announcement data is not currently available via API.</p>
      <a
        href={`https://www.asx.com.au/markets/company/${code}.html`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
      >
        <ExternalLink className="w-4 h-4" />
        View on ASX website
      </a>
    </div>
  )

  // Derive unique document types for the type filter
  const types = Array.from(new Set(
    data.data.map(a => a.document_type).filter(Boolean)
  )).sort() as string[]

  // Apply filters
  const filtered = data.data.filter(a => {
    if (filter === 'sensitive' && !a.market_sensitive) return false
    if (typeFilter !== 'all' && a.document_type !== typeFilter) return false
    return true
  })

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm">
          {(['all', 'sensitive'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={[
                'px-3 py-1.5 font-medium transition-colors',
                filter === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-600 hover:bg-gray-50',
              ].join(' ')}
            >
              {f === 'all' ? 'All' : '🔔 Market Sensitive'}
            </button>
          ))}
        </div>

        {types.length > 0 && (
          <select
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600
                       bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="all">All types</option>
            {types.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        )}

        <span className="text-xs text-gray-400 ml-auto">
          {filtered.length} of {data.total} announcements
          {data.source === 'live' && (
            <span className="ml-1 text-blue-400">· live</span>
          )}
        </span>
      </div>

      {/* Announcement list */}
      {filtered.length === 0 ? (
        <p className="text-center py-8 text-gray-400 text-sm">No announcements match the filter.</p>
      ) : (
        <div className="divide-y divide-gray-100">
          {filtered.map(a => (
            <div key={a.id} className="py-3 flex items-start gap-3 group hover:bg-gray-50 -mx-1 px-1 rounded-lg">
              {/* Date column */}
              <div className="w-28 shrink-0 text-right">
                <div className="text-xs font-medium text-gray-700">{formatAnnDate(a.released_at)}</div>
                <div className="text-xs text-gray-400">{formatAnnTime(a.released_at)}</div>
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-2 flex-wrap">
                  {/* Sensitive badges */}
                  {a.price_sensitive && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium
                                     bg-red-50 text-red-600 border border-red-200 shrink-0">
                      <AlertTriangle className="w-3 h-3" /> Price Sensitive
                    </span>
                  )}
                  {a.market_sensitive && !a.price_sensitive && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium
                                     bg-orange-50 text-orange-600 border border-orange-200 shrink-0">
                      🔔 Market Sensitive
                    </span>
                  )}
                </div>

                {/* Title / link */}
                {a.url ? (
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-gray-800 hover:text-blue-600 font-medium flex items-start gap-1
                               group-hover:underline mt-1"
                  >
                    <span className="leading-snug">{a.title || 'Untitled announcement'}</span>
                    <ExternalLink className="w-3 h-3 mt-0.5 shrink-0 text-gray-400 group-hover:text-blue-500" />
                  </a>
                ) : (
                  <p className="text-sm text-gray-800 font-medium mt-1">
                    {a.title || 'Untitled announcement'}
                  </p>
                )}

                {/* Meta row */}
                <div className="flex items-center gap-3 mt-1 flex-wrap">
                  {a.document_type && (
                    <span className="inline-flex items-center gap-1 text-xs text-gray-400">
                      <Tag className="w-3 h-3" />
                      {a.document_type}
                    </span>
                  )}
                  {a.num_pages != null && (
                    <span className="text-xs text-gray-400">{a.num_pages}p</span>
                  )}
                  {a.file_size_kb != null && (
                    <span className="text-xs text-gray-400">{formatFileSize(a.file_size_kb)}</span>
                  )}
                </div>
              </div>

              {/* PDF icon */}
              {a.url && (
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-gray-300 hover:text-red-500 transition-colors"
                  title="Open PDF"
                >
                  <FileText className="w-5 h-5" />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// ── AI Insights Tab ───────────────────────────────────────────

function AIInsightsTab({ code }: { code: string }) {
  const [data,    setData]    = useState<AISummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  const load = (refresh = false) => {
    setLoading(true)
    setError(null)
    getAISummary(code, refresh)
      .then(setData)
      .catch(e => {
        const msg = e?.response?.data?.detail || e.message || 'Failed to generate AI summary'
        setError(msg)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [code]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return (
    <div className="space-y-4 animate-pulse">
      <div className="h-20 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl" />
      <div className="grid grid-cols-2 gap-4">
        <div className="h-40 bg-gray-50 rounded-xl" />
        <div className="h-40 bg-gray-50 rounded-xl" />
      </div>
      <div className="h-8 bg-gray-50 rounded w-1/3 mx-auto mt-6" />
      <p className="text-center text-sm text-gray-400 -mt-2">Claude is analysing {code}…</p>
    </div>
  )

  if (error) return (
    <div className="text-center py-16">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-50 mb-4">
        <span className="text-2xl">⚠️</span>
      </div>
      <p className="text-gray-700 font-medium mb-1">AI Insights unavailable</p>
      <p className="text-sm text-gray-400 max-w-sm mx-auto mb-4">{error}</p>
      <button onClick={() => load()} className="text-sm text-blue-600 hover:underline">Try again</button>
    </div>
  )

  if (!data) return null

  const sentimentConfig = {
    bullish: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', badge: 'bg-emerald-100 text-emerald-700', icon: '▲' },
    bearish: { bg: 'bg-red-50',     border: 'border-red-200',     text: 'text-red-700',     badge: 'bg-red-100 text-red-700',         icon: '▼' },
    neutral: { bg: 'bg-blue-50',    border: 'border-blue-200',    text: 'text-blue-700',    badge: 'bg-blue-100 text-blue-700',        icon: '◆' },
  }
  const s = sentimentConfig[data.sentiment] ?? sentimentConfig.neutral

  return (
    <div className="space-y-4">

      {/* Verdict banner */}
      <div className={`rounded-xl p-4 border ${s.bg} ${s.border} flex items-start gap-3`}>
        <span className={`text-lg mt-0.5 ${s.text}`}>{s.icon}</span>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full uppercase tracking-wide ${s.badge}`}>
              {data.sentiment}
            </span>
          </div>
          <p className={`text-sm font-semibold leading-snug ${s.text}`}>{data.verdict}</p>
        </div>
      </div>

      {/* Bull / Bear */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title="Bull Case">
          <ul className="space-y-2">
            {data.bull_case.map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="text-emerald-500 mt-0.5 shrink-0 font-bold">↑</span>
                {p}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Bear Case">
          <ul className="space-y-2">
            {data.bear_case.map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="text-red-500 mt-0.5 shrink-0 font-bold">↓</span>
                {p}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* Catalysts / Risks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {data.key_catalysts.length > 0 && (
          <Card title="Key Catalysts">
            <ul className="space-y-2">
              {data.key_catalysts.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="text-blue-500 mt-0.5 shrink-0">✦</span>
                  {c}
                </li>
              ))}
            </ul>
          </Card>
        )}
        {data.key_risks.length > 0 && (
          <Card title="Key Risks">
            <ul className="space-y-2">
              {data.key_risks.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="text-amber-500 mt-0.5 shrink-0">⚑</span>
                  {r}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-100">
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 rounded-full font-medium text-slate-500">
            ⚡ Powered by Claude
          </span>
          <span>{data.cached ? 'Cached' : 'Generated'} {new Date(data.generated_at).toLocaleString('en-AU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
        </div>
        <button
          onClick={() => load(true)}
          className="text-xs text-blue-500 hover:text-blue-700 hover:underline transition-colors"
        >
          Regenerate ↻
        </button>
      </div>

      <p className="text-xs text-gray-300 text-center">
        AI-generated analysis for informational purposes only. Not financial advice.
      </p>
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

  // Price chart period
  const [pricePeriod, setPricePeriod] = useState<PricePeriod>('1Y')

  // Anomaly flags (Week 13)
  const [anomalyFlags, setAnomalyFlags] = useState<CompanyAnomalyFlag[]>([])

  // Fetch overview + anomaly flags on mount
  useEffect(() => {
    setLoading(true)
    setError(null)
    getCompanyOverview(code)
      .then(setOverview)
      .catch(e => setError(e?.response?.data?.detail ?? e.message))
      .finally(() => setLoading(false))
    getAnomalyFlags(code)
      .then(r => setAnomalyFlags(r.flags))
      .catch(() => {}) // silently ignore — table may not exist yet
  }, [code])

  // Lazy-load per tab — re-fetch prices when period changes
  useEffect(() => {
    if (activeTab === 'technicals') {
      setPricesLoading(true)
      const apiPeriod = pricePeriod.toLowerCase()
      getCompanyPrices(code, apiPeriod)
        .then(setPrices)
        .catch(() => setPrices({ asx_code: code, period: apiPeriod, data: [] }))
        .finally(() => setPricesLoading(false))
    }
  }, [activeTab, code, pricePeriod])

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
    { id: 'ai',         label: 'AI Insights' },
    { id: 'documents',  label: 'Documents' },
  ]

  const isLoading = (tab: Tab) => {
    if (tab === 'financials') return financialsLoading || (financialPeriod === 'halfyearly' && halfYearlyLoading)
    if (tab === 'technicals') return pricesLoading
    if (tab === 'dividends')  return dividendsLoading
    if (tab === 'peers')      return peersLoading
    return false
  }

  return (
    <div className="bg-white border border-gray-100 rounded-2xl shadow-sm overflow-hidden">

      {/* ── Tab bar — dark slate ─────────────────────────────── */}
      <div className="flex bg-slate-900 overflow-x-auto">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => !t.comingSoon && setActiveTab(t.id)}
            className={[
              'py-3.5 px-5 text-sm font-semibold whitespace-nowrap transition-all duration-200 relative',
              t.comingSoon
                ? 'text-slate-600 cursor-not-allowed'
                : activeTab === t.id
                  ? 'text-white bg-gradient-to-b from-blue-600 to-blue-700 shadow-inner'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5',
            ].join(' ')}
          >
            {t.label}
            {t.comingSoon && (
              <span className="ml-1.5 text-xs text-slate-600 font-normal">soon</span>
            )}
          </button>
        ))}
      </div>


      {/* ── Tab content ──────────────────────────────────────── */}
      <div className="p-5">
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
            {activeTab === 'overview' && <OverviewTab o={overview} code={code} anomalyFlags={anomalyFlags} />}

            {activeTab === 'financials' && (
              isLoading('financials')
                ? <div className="grid grid-cols-1 gap-4">{[1,2,3].map(i=><LoadingCard key={i}/>)}</div>
                : <FinancialsTab
                    overview={overview}
                    financials={financials}
                    halfYearly={halfYearly}
                    period={financialPeriod}
                    onPeriodChange={setFinancialPeriod}
                  />
            )}

            {activeTab === 'technicals' && (
              <TechnicalsTab
                o={overview}
                prices={prices}
                pricesLoading={pricesLoading}
                pricePeriod={pricePeriod}
                onPeriodChange={setPricePeriod}
              />
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
              <PlanGate required="premium" feature="AI Insights">
                <AIInsightsTab code={code} />
              </PlanGate>
            )}

            {activeTab === 'documents' && (
              <DocumentsTab code={code} />
            )}
          </>
        ) : null}
      </div>
    </div>
  )
}
