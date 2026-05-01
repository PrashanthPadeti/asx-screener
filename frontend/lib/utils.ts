import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function formatPrice(val: number | null | undefined): string {
  if (val == null) return '—'
  return `$${val.toFixed(2)}`
}

export function formatNumber(val: number | null | undefined, decimals = 2): string {
  if (val == null) return '—'
  if (Math.abs(val) >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`
  if (Math.abs(val) >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`
  if (Math.abs(val) >= 1_000) return `${(val / 1_000).toFixed(1)}K`
  return val.toFixed(decimals)
}

export function formatMarketCap(val: number | null | undefined): string {
  if (val == null) return '—'
  // val is in AUD millions
  if (val >= 1_000) return `$${(val / 1_000).toFixed(2)}B`
  return `$${val.toFixed(0)}M`
}

export function formatPct(val: number | null | undefined, decimals = 2): string {
  if (val == null) return '—'
  // Check if value is already a percentage (>1) or a decimal (<1)
  const pct = Math.abs(val) < 2 && Math.abs(val) > 0 ? val * 100 : val
  return `${pct.toFixed(decimals)}%`
}

export function formatChangePct(val: number | null | undefined): string {
  if (val == null) return '—'
  const sign = val >= 0 ? '+' : ''
  return `${sign}${val.toFixed(2)}%`
}

export function formatVolume(val: number | null | undefined): string {
  if (val == null) return '—'
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`
  if (val >= 1_000) return `${(val / 1_000).toFixed(0)}K`
  return val.toString()
}

/**
 * Format a decimal ratio as a percentage string (0.15 → "15.00%").
 * Use this for DB fields stored as ratios: ROE, margins, yields, returns, growth rates.
 */
export function formatRatio(val: number | null | undefined, decimals = 2): string {
  if (val == null) return '—'
  return `${(val * 100).toFixed(decimals)}%`
}

/**
 * Format a decimal ratio as a signed percentage change (0.15 → "+15.0%").
 */
export function formatRatioChange(val: number | null | undefined, decimals = 1): string {
  if (val == null) return '—'
  const pct = val * 100
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(decimals)}%`
}

/**
 * Format a value already in 0-100 % range (e.g. franking_pct = 100 → "100%").
 */
export function formatPctRaw(val: number | null | undefined, decimals = 1): string {
  if (val == null) return '—'
  return `${val.toFixed(decimals)}%`
}

export const SECTORS = [
  'Materials',
  'Energy',
  'Financials',
  'Healthcare',
  'Industrials',
  'Technology',
  'Consumer Discretionary',
  'Consumer Staples',
  'Communication Services',
  'Utilities',
  'Real Estate',
  'Other',
]

export const SECTOR_COLORS: Record<string, string> = {
  Materials:                'bg-yellow-100 text-yellow-800',
  Energy:                   'bg-orange-100 text-orange-800',
  Financials:               'bg-blue-100 text-blue-800',
  Healthcare:               'bg-green-100 text-green-800',
  Industrials:              'bg-gray-100 text-gray-800',
  Technology:               'bg-purple-100 text-purple-800',
  'Consumer Discretionary': 'bg-pink-100 text-pink-800',
  'Consumer Staples':       'bg-lime-100 text-lime-800',
  'Communication Services': 'bg-cyan-100 text-cyan-800',
  Utilities:                'bg-teal-100 text-teal-800',
  'Real Estate':            'bg-indigo-100 text-indigo-800',
  Other:                    'bg-slate-100 text-slate-600',
}
