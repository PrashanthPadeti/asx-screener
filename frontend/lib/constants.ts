/**
 * Shared constants — single source of truth for values that must match backend strings.
 * Import from here rather than hardcoding in individual pages.
 */

// ── Anomaly flag types (must match compute/engine/anomaly_detect.py) ──────────
export const ANOMALY_TYPES = [
  { value: 'all',                       label: 'All'             },
  { value: 'VALUE_GROWTH',              label: 'Value Growth'    },
  { value: 'OVERSOLD_QUALITY',          label: 'Oversold Quality'},
  { value: 'OVERBOUGHT_WEAK',           label: 'Overbought Weak' },
  { value: 'PRICE_EARNINGS_DIVERGENCE', label: 'PE Divergence'   },
  { value: 'DIVIDEND_YIELD_SPIKE',      label: 'Yield Spike'     },
] as const

export type AnomalyTypeValue = typeof ANOMALY_TYPES[number]['value']
