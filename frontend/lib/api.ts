import axios from 'axios'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://209.38.84.102:8000'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
})

// ── Types ────────────────────────────────────────────────────

export interface Company {
  asx_code: string
  company_name: string
  gics_sector: string | null
  gics_industry_group: string | null
  is_reit: boolean
  is_miner: boolean
  is_asx200: boolean
  status: string
  listing_date: string | null
}

export interface CompanyDetail extends Company {
  isin: string | null
  website: string | null
  description: string | null
  employee_count: number | null
  shares_outstanding: number | null
  abn: string | null
  domicile: string | null
  state: string | null
  primary_commodity: string | null
  logo_url: string | null
}

export interface CompanyListResponse {
  data: Company[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface SearchResult {
  asx_code: string
  company_name: string
  gics_sector: string | null
  is_reit: boolean
  is_miner: boolean
}

export interface ScreenerFilter {
  field: string
  operator: string
  value: string | number | boolean | string[]
}

/**
 * One row from the screener results (sourced from screener.universe).
 *
 * Decimal ratio fields (stored as 0.15 = 15%):
 *   roe, roa, roce, avg_roe_3y, gross_margin, ebitda_margin, net_margin,
 *   operating_margin, dividend_yield, grossed_up_yield, payout_ratio, fcf_yield,
 *   return_*, revenue_growth_*, earnings_growth_*, eps_growth_*, net_income_growth_*,
 *   volatility_*, drawdown_from_ath, dividend_cagr_3y, revenue_cagr_5y, eps_growth_3y_cagr
 *
 * Already 0-100 fields:
 *   franking_pct, percent_insiders, percent_institutions, short_pct, rsi_14, adx_14
 */
export interface ScreenerRow {
  // Identity
  asx_code: string
  company_name: string
  sector: string | null
  industry: string | null
  stock_type: string | null
  status: string | null
  is_reit: boolean
  is_miner: boolean
  is_asx200: boolean
  is_asx300: boolean

  // Price
  price: number | null
  high_52w: number | null
  low_52w: number | null
  volume: number | null
  avg_volume_20d: number | null
  market_cap: number | null  // AUD millions

  // Valuation
  pe_ratio: number | null
  forward_pe: number | null
  price_to_book: number | null
  price_to_sales: number | null
  ev_to_ebitda: number | null
  peg_ratio: number | null
  price_to_fcf: number | null
  fcf_yield: number | null  // ratio

  // Dividends
  dividend_yield: number | null            // ratio
  grossed_up_yield: number | null          // ratio
  franking_pct: number | null              // 0-100
  dps_ttm: number | null
  payout_ratio: number | null              // ratio
  dividend_consecutive_yrs: number | null
  dividend_cagr_3y: number | null          // ratio

  // Profitability
  gross_margin: number | null              // ratio
  ebitda_margin: number | null             // ratio
  net_margin: number | null                // ratio
  operating_margin: number | null          // ratio
  roe: number | null                       // ratio
  roa: number | null                       // ratio
  roce: number | null                      // ratio
  avg_roe_3y: number | null                // ratio

  // Growth
  revenue_growth_1y: number | null         // ratio
  revenue_growth_3y_cagr: number | null    // ratio
  revenue_cagr_5y: number | null           // ratio
  earnings_growth_1y: number | null        // ratio
  eps_growth_3y_cagr: number | null        // ratio
  revenue_growth_yoy_q: number | null      // ratio
  eps_growth_yoy_q: number | null          // ratio
  revenue_growth_hoh: number | null        // ratio ★ ASX half-yearly
  net_income_growth_hoh: number | null     // ratio ★
  eps_growth_hoh: number | null            // ratio ★

  // Balance Sheet
  debt_to_equity: number | null
  current_ratio: number | null
  net_debt: number | null                  // AUD millions
  total_debt: number | null                // AUD millions
  book_value_per_share: number | null
  total_assets: number | null              // AUD millions
  total_equity: number | null              // AUD millions
  fcf_fy0: number | null                   // AUD millions
  cfo_fy0: number | null                   // AUD millions

  // Quality Scores
  piotroski_f_score: number | null         // 0–9
  altman_z_score: number | null
  percent_insiders: number | null          // 0-100
  percent_institutions: number | null      // 0-100
  short_pct: number | null                 // 0-100

  // Technicals
  rsi_14: number | null                    // 0-100
  adx_14: number | null
  macd: number | null
  macd_signal: number | null
  sma_20: number | null
  sma_50: number | null
  sma_200: number | null
  ema_20: number | null
  bb_upper: number | null
  bb_lower: number | null
  atr_14: number | null
  obv: number | null
  volatility_20d: number | null            // ratio
  volatility_60d: number | null            // ratio
  beta_1y: number | null
  sharpe_1y: number | null

  // Returns
  return_1w: number | null                 // ratio
  return_1m: number | null                 // ratio
  return_3m: number | null                 // ratio
  return_6m: number | null                 // ratio
  return_1y: number | null                 // ratio
  return_ytd: number | null                // ratio
  return_3y: number | null                 // ratio
  return_5y: number | null                 // ratio
  drawdown_from_ath: number | null         // ratio (negative)

  // Metadata
  price_date: string | null
  universe_built_at: string | null
}

export interface ScreenerResponse {
  data: ScreenerRow[]
  total: number
  page: number
  page_size: number
  total_pages: number
  filters_applied: number
}

export interface ScreenerFieldMeta {
  key: string
  label: string
  type: 'number' | 'boolean' | 'text'
  unit: string
  scale: number
}

export interface ScreenerFieldsResponse {
  categories: Record<string, ScreenerFieldMeta[]>
  operators: {
    number: { value: string; label: string }[]
    boolean: { value: string; label: string }[]
    text: { value: string; label: string }[]
  }
  total_fields: number
}

export interface ScreenerPreset {
  id: string
  name: string
  description: string
  icon: string
  filters: ScreenerFilter[]
  sort_by: string
  sort_dir: string
}

export interface ScreenerPresetsResponse {
  presets: ScreenerPreset[]
}

// ── API Functions ─────────────────────────────────────────────

export const getCompanies = async (params: {
  page?: number
  page_size?: number
  sector?: string
  is_reit?: boolean
  is_asx200?: boolean
  sort_by?: string
  sort_dir?: string
}): Promise<CompanyListResponse> => {
  const { data } = await api.get('/api/v1/companies', { params })
  return data
}

export const searchCompanies = async (q: string): Promise<SearchResult[]> => {
  const { data } = await api.get('/api/v1/companies/search', { params: { q, limit: 10 } })
  return data
}

export const getCompany = async (asxCode: string): Promise<CompanyDetail> => {
  const { data } = await api.get(`/api/v1/companies/${asxCode}`)
  return data
}

export const runScreener = async (
  filters: ScreenerFilter[],
  options: { sort_by?: string; sort_dir?: string; page?: number; page_size?: number } = {}
): Promise<ScreenerResponse> => {
  const { data } = await api.post('/api/v1/screener', {
    filters,
    sort_by: options.sort_by || 'market_cap',
    sort_dir: options.sort_dir || 'desc',
    page: options.page || 1,
    page_size: options.page_size || 50,
  })
  return data
}

export const getScreenerFields = async (): Promise<ScreenerFieldsResponse> => {
  const { data } = await api.get('/api/v1/screener/fields')
  return data
}

export const getScreenerPresets = async (): Promise<ScreenerPresetsResponse> => {
  const { data } = await api.get('/api/v1/screener/presets')
  return data
}
