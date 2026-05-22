import axios from 'axios'
import { getStoredAccessToken } from './auth'

// Server-side (build / SSR): use internal localhost so firewall on port 8000
// doesn't block the fetch. Client-side (browser): use the public API URL.
const isServer = typeof window === 'undefined'
const API_BASE = isServer
  ? (process.env.API_INTERNAL_URL || 'http://localhost:8000')
  : (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
})

// Inject Bearer token on every request when one is available
api.interceptors.request.use(config => {
  const token = getStoredAccessToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
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
  is_capped?: boolean   // true when free-tier 500-row limit is applied
  free_limit?: number   // 500 for free users
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
  premium?: boolean
  min_plan?: string   // 'pro' | 'premium'
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

/**
 * Trigger a CSV export download of the current screen (max 5,000 rows).
 * Uses window.location / fetch + blob to trigger browser download.
 */
export const exportScreener = async (
  filters: ScreenerFilter[],
  options: { sort_by?: string; sort_dir?: string } = {}
): Promise<void> => {
  const response = await api.post('/api/v1/screener/export', {
    filters,
    sort_by: options.sort_by || 'market_cap',
    sort_dir: options.sort_dir || 'desc',
    page: 1,
    page_size: 50,  // ignored server-side for export
  }, { responseType: 'blob' })
  const blob  = new Blob([response.data], { type: 'text/csv' })
  const url   = URL.createObjectURL(blob)
  const a     = document.createElement('a')
  const cd    = (response.headers['content-disposition'] as string) || ''
  const match = cd.match(/filename="([^"]+)"/)
  a.href     = url
  a.download = match ? match[1] : 'asx_screener_export.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/**
 * Fetch live screener data for a specific list of ASX codes.
 * Used by the watchlist page. Input order is preserved.
 */
export const getScreenerBatch = async (codes: string[]): Promise<ScreenerRow[]> => {
  if (codes.length === 0) return []
  const { data } = await api.post('/api/v1/screener/batch', { codes })
  return data
}

// ── Company detail sub-resources ──────────────────────────────

/**
 * All pre-computed screener.universe metrics for one company.
 *
 * Decimal ratio fields (stored as 0.15 = 15%):
 *   dividend_yield, grossed_up_yield, payout_ratio, dividend_cagr_3y,
 *   gross_margin, ebitda_margin, net_margin, operating_margin,
 *   roe, roa, roce, avg_roe_3y, fcf_yield,
 *   revenue_growth_*, earnings_growth_*, eps_growth_*,
 *   return_*, drawdown_from_ath, volatility_*, momentum_*,
 *   analyst_upside
 *
 * Already 0-100 fields:
 *   franking_pct, short_pct, percent_insiders, percent_institutions,
 *   rsi_14, adx_14
 */
export interface CompanyOverview {
  // Price
  price: number | null
  price_date: string | null
  market_cap: number | null
  volume: number | null
  avg_volume_20d: number | null
  high_52w: number | null
  low_52w: number | null

  // Valuation
  pe_ratio: number | null
  forward_pe: number | null
  peg_ratio: number | null
  price_to_book: number | null
  price_to_sales: number | null
  price_to_fcf: number | null
  ev: number | null
  ev_to_ebitda: number | null
  ev_to_ebit: number | null
  ev_to_revenue: number | null
  graham_number: number | null
  fcf_yield: number | null           // ratio

  // Dividends
  dividend_yield: number | null      // ratio
  grossed_up_yield: number | null    // ratio
  franking_pct: number | null        // 0-100
  dps_ttm: number | null
  dps_fy0: number | null
  payout_ratio: number | null        // ratio
  ex_div_date: string | null
  dividend_consecutive_yrs: number | null
  dividend_cagr_3y: number | null    // ratio

  // Profitability (all ratios)
  gross_margin: number | null
  ebitda_margin: number | null
  net_margin: number | null
  operating_margin: number | null
  roe: number | null
  roa: number | null
  roce: number | null
  avg_roe_3y: number | null

  // Income Statement snapshot
  revenue_ttm: number | null
  ebitda_ttm: number | null
  net_profit_ttm: number | null
  revenue_fy0: number | null
  revenue_fy1: number | null
  revenue_fy2: number | null
  net_profit_fy0: number | null
  net_profit_fy1: number | null
  eps_fy0: number | null
  eps_fy1: number | null

  // Balance Sheet
  total_assets: number | null
  total_equity: number | null
  total_debt: number | null
  net_debt: number | null
  cash: number | null
  book_value_per_share: number | null
  debt_to_equity: number | null
  current_ratio: number | null

  // Cash Flow
  cfo_fy0: number | null
  capex_fy0: number | null
  fcf_fy0: number | null

  // Growth (all ratios)
  revenue_growth_1y: number | null
  revenue_growth_3y_cagr: number | null
  revenue_cagr_5y: number | null
  earnings_growth_1y: number | null
  eps_growth_3y_cagr: number | null
  revenue_growth_yoy_q: number | null
  eps_growth_yoy_q: number | null
  revenue_growth_hoh: number | null
  net_income_growth_hoh: number | null
  eps_growth_hoh: number | null

  // Quality
  piotroski_f_score: number | null   // 0-9
  altman_z_score: number | null
  short_pct: number | null           // 0-100
  percent_insiders: number | null    // 0-100
  percent_institutions: number | null // 0-100

  // Analyst
  analyst_rating: string | null
  analyst_target_price: number | null
  analyst_upside: number | null      // ratio

  // Returns (all ratios)
  return_1w: number | null
  return_1m: number | null
  return_3m: number | null
  return_6m: number | null
  return_1y: number | null
  return_ytd: number | null
  return_3y: number | null
  return_5y: number | null
  drawdown_from_ath: number | null

  // Technicals
  rsi_14: number | null              // 0-100
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
  volatility_20d: number | null      // ratio
  volatility_60d: number | null      // ratio
  beta_1y: number | null
  sharpe_1y: number | null
  momentum_3m: number | null
  momentum_6m: number | null

  // Short interest
  short_interest_chg_1w: number | null  // pp change WoW (absolute)

  // Composite factor scores (0-100 percentile ranks)
  composite_score: number | null
  value_score:     number | null
  quality_score:   number | null
  growth_score:    number | null
  momentum_score:  number | null
  income_score:    number | null

  // DB-computed pros/cons signal lists
  pros: string[]
  cons: string[]
}

export interface AnnualFinancialsRow {
  fiscal_year: number
  period_end_date: string | null
  // P&L (AUD millions)
  revenue: number | null
  gross_profit: number | null
  ebitda: number | null
  ebit: number | null
  net_profit: number | null
  eps: number | null
  dps: number | null
  // Margins (decimal ratios)
  gpm: number | null
  ebitda_margin: number | null
  npm: number | null
  // Balance Sheet (AUD millions)
  total_assets: number | null
  total_equity: number | null
  total_debt: number | null
  net_debt: number | null
  cash_equivalents: number | null
  book_value_per_share: number | null
  debt_to_equity: number | null
  // Cash Flow (AUD millions)
  cfo: number | null
  capex: number | null
  fcf: number | null
}

export interface FinancialsResponse {
  asx_code: string
  years: AnnualFinancialsRow[]
}

export interface PricePoint {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number
  volume: number | null
}

export interface PricesResponse {
  asx_code: string
  period: string
  data: PricePoint[]
}

// ── Market summary types ──────────────────────────────────────

export interface MarketSummary {
  total_stocks: number
  asx200_stocks: number
  stocks_with_dividends: number
  avg_dividend_yield: number | null   // decimal ratio
  median_pe: number | null
  total_market_cap_bn: number | null  // AUD billions
  universe_built_at: string | null
}

export interface MoverStock {
  asx_code: string
  company_name: string
  sector: string | null
  price: number | null
  return_1d: number | null   // decimal ratio
  return_1w: number | null   // decimal ratio
  return_1m: number | null   // decimal ratio
  return_3m: number | null   // decimal ratio
  market_cap: number | null  // AUD millions
  period_high: number | null
  period_low: number | null
}

export interface MoversResponse {
  gainers: MoverStock[]
  losers: MoverStock[]
  period: string
}

export interface SectorStat {
  sector: string
  stock_count: number
  avg_pe: number | null
  avg_dividend_yield: number | null   // decimal ratio
  avg_return_1y: number | null        // decimal ratio
  total_market_cap_bn: number | null  // AUD billions
}

export interface SectorsResponse {
  sectors: SectorStat[]
}

export const getMarketSummary = async (): Promise<MarketSummary> => {
  const { data } = await api.get('/api/v1/market/summary')
  return data
}

export const getMarketSectors = async (): Promise<SectorsResponse> => {
  const { data } = await api.get('/api/v1/market/sectors')
  return data
}

// ── Market Dashboard ──────────────────────────────────────────

export interface IndexSnapshot {
  stock_count: number
  gainers: number
  losers: number
  unchanged: number
  avg_return_1w: number | null
  total_market_cap_bn: number | null
}

export interface DashboardStock {
  asx_code: string
  company_name: string
  sector: string | null
  price: number | null
  return_1w: number | null
  market_cap: number | null
}

export interface ActiveStock extends DashboardStock {
  volume: number | null
  avg_volume_20d: number | null
}

export interface VolumePressureStock extends DashboardStock {
  volume: number | null
  avg_volume_20d: number | null
  volume_ratio: number | null
}

export interface SectorHeatmapItem {
  sector: string
  stock_count: number
  avg_return_1w: number | null
  total_market_cap_bn: number | null
}

export interface ExDivStock {
  asx_code: string
  company_name: string
  ex_div_date: string | null
  pay_date: string | null
  dps_ttm: number | null
  dividend_yield: number | null
  franking_pct: number | null
}

export interface MarketDashboard {
  asx200: IndexSnapshot
  asx300: IndexSnapshot
  sector_heatmap: SectorHeatmapItem[]
  top_gainers: DashboardStock[]
  top_losers: DashboardStock[]
  most_active: ActiveStock[]
  heavy_buying: VolumePressureStock[]
  heavy_selling: VolumePressureStock[]
  upcoming_exdiv: ExDivStock[]
  period: string
  universe_built_at: string | null
}

export const getMarketDashboard = async (): Promise<MarketDashboard> => {
  const { data } = await api.get('/api/v1/market/dashboard')
  return data
}

export interface VolumeActivityResponse {
  most_active:   ActiveStock[]
  heavy_buying:  VolumePressureStock[]
  heavy_selling: VolumePressureStock[]
  cap_tier:      string | null
}

export const getVolumeActivity = async (
  cap_tier?: 'mega' | 'large' | 'mid' | 'small' | 'micro' | 'nano' | 'asx300',
): Promise<VolumeActivityResponse> => {
  const { data } = await api.get('/api/v1/market/volume-activity', {
    params: cap_tier ? { cap_tier } : {},
  })
  return data
}

export interface SignalStock {
  asx_code: string
  company_name: string | null
  sector: string | null
  price: number | null
  market_cap: number | null
  period_high: number | null
  period_low: number | null
  volume: number | null
  avg_volume_20d: number | null
  return_1w: number | null
  return_1m: number | null
  pct_from_high?: number
  pct_from_low?: number
  vol_ratio?: number
}

export interface MarketSignals {
  near_period_high: SignalStock[]
  near_period_low:  SignalStock[]
  volume_surge:     SignalStock[]
}

export const getMarketMovers = async (
  period: '1d' | '1w' | '1m' | '3m',
  limit = 10,
  cap_tier?: 'mega' | 'large' | 'mid' | 'small' | 'micro' | 'nano' | 'asx300',
): Promise<{ gainers: MoverStock[]; losers: MoverStock[]; period: string }> => {
  const { data } = await api.get('/api/v1/market/movers', {
    params: { period, limit, ...(cap_tier ? { cap_tier } : {}) }
  })
  return data
}

export const getMarketSignals = async (period: '1d' | '1w' | '1m' | '3m' | '52w' = '1w'): Promise<MarketSignals> => {
  const { data } = await api.get('/api/v1/market/signals', { params: { period } })
  return data
}

export const getCompanyOverview = async (asxCode: string): Promise<CompanyOverview> => {
  const { data } = await api.get(`/api/v1/companies/${asxCode}/overview`)
  return data
}

export const getCompanyFinancials = async (asxCode: string, years = 7): Promise<FinancialsResponse> => {
  const { data } = await api.get(`/api/v1/companies/${asxCode}/financials`, { params: { years } })
  return data
}

export const getCompanyPrices = async (asxCode: string, period = '1y'): Promise<PricesResponse> => {
  const { data } = await api.get(`/api/v1/companies/${asxCode}/prices`, { params: { period } })
  return data
}

// ── Dividends ─────────────────────────────────────────────────

export interface DividendRecord {
  ex_date: string             // ISO date
  payment_date: string | null
  record_date: string | null
  amount: number | null       // AUD per share
  unadjusted_value: number | null
  franking_pct: number | null // 0-100
  div_type: string | null
  currency: string | null
}

export interface DividendsSummary {
  dividend_yield: number | null      // decimal ratio
  grossed_up_yield: number | null    // decimal ratio
  franking_pct: number | null        // 0-100
  dps_ttm: number | null
  dps_fy0: number | null
  payout_ratio: number | null        // decimal ratio
  ex_div_date: string | null
  dividend_consecutive_yrs: number | null
  dividend_cagr_3y: number | null    // decimal ratio
}

export interface DividendsResponse {
  asx_code: string
  summary: DividendsSummary
  history: DividendRecord[]
}

export const getCompanyDividends = async (asxCode: string, limit = 40): Promise<DividendsResponse> => {
  const { data } = await api.get(`/api/v1/companies/${asxCode}/dividends`, { params: { limit } })
  return data
}

// ── Peers ─────────────────────────────────────────────────────

export interface PeerStock {
  asx_code: string
  company_name: string
  market_cap: number | null      // AUD millions
  price: number | null
  pe_ratio: number | null
  forward_pe: number | null
  price_to_book: number | null
  ev_to_ebitda: number | null
  dividend_yield: number | null  // decimal ratio
  grossed_up_yield: number | null
  franking_pct: number | null    // 0-100
  roe: number | null             // decimal ratio
  net_margin: number | null      // decimal ratio
  revenue_growth_1y: number | null
  return_1y: number | null       // decimal ratio
  return_ytd: number | null
  piotroski_f_score: number | null
  debt_to_equity: number | null
}

export interface PeersResponse {
  asx_code: string
  gics_industry: string | null
  peers: PeerStock[]
}

export const getCompanyPeers = async (asxCode: string, limit = 15): Promise<PeersResponse> => {
  const { data } = await api.get(`/api/v1/companies/${asxCode}/peers`, { params: { limit } })
  return data
}

// ── Half-Yearly Financials ────────────────────────────────────

export interface HalfYearlyRow {
  period_label: string           // e.g. '1H FY2024'
  period_end_date: string | null
  revenue: number | null         // AUD millions
  gross_profit: number | null
  ebitda: number | null
  ebit: number | null
  net_profit: number | null
  eps: number | null
  dps: number | null
  dps_franking_pct: number | null  // 0-100
  gpm: number | null             // gross_margin decimal ratio
  ebitda_margin: number | null   // ebit_margin decimal ratio
  npm: number | null             // net_margin decimal ratio
  // Growth rates (decimal ratios)
  revenue_growth_hoh: number | null
  net_profit_growth_hoh: number | null
  eps_growth_hoh: number | null
  revenue_growth_yoy: number | null
  eps_growth_yoy: number | null
}

export interface HalfYearlyResponse {
  asx_code: string
  periods: HalfYearlyRow[]
}

export const getCompanyHalfYearly = async (asxCode: string, periods = 8): Promise<HalfYearlyResponse> => {
  const { data } = await api.get(`/api/v1/companies/${asxCode}/halfyearly`, { params: { periods } })
  return data
}

// ── Announcements ─────────────────────────────────────────────

export interface Announcement {
  id:               number
  asx_code:         string
  announcement_id:  string
  released_at:      string | null   // ISO datetime
  document_date:    string | null   // ISO date
  title:            string | null
  document_type:    string | null
  url:              string | null
  market_sensitive: boolean
  price_sensitive:  boolean
  num_pages:        number | null
  file_size_kb:     number | null
}

export interface AnnouncementsResponse {
  asx_code: string
  total:    number
  data:     Announcement[]
  source:   'db' | 'live'
}

export const getCompanyAnnouncements = async (
  asxCode: string,
  limit = 30,
): Promise<AnnouncementsResponse> => {
  const { data } = await api.get(
    `/api/v1/companies/${asxCode}/announcements`,
    { params: { limit } },
  )
  return data
}

// ── AI Summary ───────────────────────────────────────────────

export interface AISummary {
  asx_code:      string
  verdict:       string
  sentiment:     'bullish' | 'bearish' | 'neutral'
  bull_case:     string[]
  bear_case:     string[]
  key_catalysts: string[]
  key_risks:     string[]
  generated_at:  string
  model_used:    string
  cached:        boolean
}

export const getAISummary = async (
  asxCode: string,
  refresh = false,
): Promise<AISummary> => {
  const { data } = await api.get(
    `/api/v1/companies/${asxCode}/ai-summary`,
    { params: refresh ? { refresh: true } : {} },
  )
  return data
}

// ── NL Screener ──────────────────────────────────────────────

export interface NLScreenerResponse {
  query:          string
  interpretation: string
  filters:        ScreenerFilter[]
  sort_by:        string
  sort_dir:       string
  total:          number
  total_pages:    number
  data:           ScreenerRow[]
}

export const nlScreener = async (query: string, page = 1): Promise<NLScreenerResponse> => {
  const { data } = await api.post('/api/v1/ai/nl-screener', { query, page })
  return data
}

// ── Anomaly Flags ─────────────────────────────────────────────

// Anomaly flag for a single company (company detail page)
export interface CompanyAnomalyFlag {
  flag_type:   string
  description: string
  severity:    'low' | 'medium' | 'high'
  detected_at: string
}

export interface AnomaliesResponse {
  asx_code: string
  flags:    CompanyAnomalyFlag[]
}

export const getAnomalyFlags = async (asxCode: string): Promise<AnomaliesResponse> => {
  const { data } = await api.get(`/api/v1/ai/anomalies/${asxCode}`)
  return data
}

// ── Watchlists ────────────────────────────────────────────────

export interface WatchlistSummary {
  id:          string
  name:        string
  description: string | null
  item_count:  number
  created_at:  string | null
}

export interface WatchlistDetail extends WatchlistSummary {
  codes: string[]
}

export interface WatchlistsResponse {
  watchlists: WatchlistSummary[]
}

export const getWatchlists = async (): Promise<WatchlistsResponse> => {
  const { data } = await api.get('/api/v1/watchlist')
  return data
}

export const createWatchlist = async (name: string, description?: string): Promise<WatchlistSummary> => {
  const { data } = await api.post('/api/v1/watchlist', { name, description })
  return data
}

export const getWatchlist = async (id: string): Promise<WatchlistDetail> => {
  const { data } = await api.get(`/api/v1/watchlist/${id}`)
  return data
}

export const updateWatchlist = async (id: string, name: string, description?: string): Promise<WatchlistSummary> => {
  const { data } = await api.patch(`/api/v1/watchlist/${id}`, { name, description })
  return data
}

export const deleteWatchlist = async (id: string): Promise<void> => {
  await api.delete(`/api/v1/watchlist/${id}`)
}

export const addToWatchlist = async (watchlistId: string, asxCode: string): Promise<void> => {
  await api.post(`/api/v1/watchlist/${watchlistId}/stocks`, { asx_code: asxCode })
}

export const removeFromWatchlist = async (watchlistId: string, asxCode: string): Promise<void> => {
  await api.delete(`/api/v1/watchlist/${watchlistId}/stocks/${asxCode}`)
}

// ── Portfolio ─────────────────────────────────────────────────

export interface PortfolioOut {
  id: string
  name: string
  description: string | null
  is_smsf: boolean
  created_at: string
}

export interface PortfoliosResponse {
  portfolios: PortfolioOut[]
}

export interface HoldingRow {
  asx_code: string
  company_name: string | null
  sector: string | null
  quantity: number
  avg_cost: number
  cost_basis: number
  current_price: number | null
  current_value: number | null
  gain_loss: number | null
  gain_loss_pct: number | null
  dividend_yield: number | null
  annual_income: number | null
  franking_pct: number | null
}

export interface PortfolioPerformance {
  portfolio_id: string
  portfolio_name: string
  total_cost: number
  total_value: number | null
  total_gain_loss: number | null
  total_gain_loss_pct: number | null
  annual_income: number | null
  portfolio_yield: number | null
  holdings: HoldingRow[]
}

export interface TransactionOut {
  id: number
  asx_code: string
  transaction_type: string
  transaction_date: string
  shares: number
  price_per_share: number
  brokerage: number
  total_cost: number | null
  notes: string | null
}

export interface TransactionsResponse {
  transactions: TransactionOut[]
}

export interface ImportResult {
  imported: number
  skipped: number
  errors: string[]
}

export const listPortfolios = async (): Promise<PortfoliosResponse> => {
  const { data } = await api.get('/api/v1/portfolio')
  return data
}

export const createPortfolio = async (name: string, description?: string, is_smsf = false): Promise<PortfolioOut> => {
  const { data } = await api.post('/api/v1/portfolio', { name, description, is_smsf })
  return data
}

export const updatePortfolio = async (id: string, name: string, description?: string, is_smsf?: boolean): Promise<PortfolioOut> => {
  const { data } = await api.patch(`/api/v1/portfolio/${id}`, { name, description, is_smsf })
  return data
}

export const deletePortfolio = async (id: string): Promise<void> => {
  await api.delete(`/api/v1/portfolio/${id}`)
}

export const getPortfolioPerformance = async (id: string): Promise<PortfolioPerformance> => {
  const { data } = await api.get(`/api/v1/portfolio/${id}/performance`)
  return data
}

export const listTransactions = async (portfolioId: string): Promise<TransactionsResponse> => {
  const { data } = await api.get(`/api/v1/portfolio/${portfolioId}/transactions`)
  return data
}

export const addTransaction = async (
  portfolioId: string,
  payload: {
    asx_code: string
    transaction_type: string
    transaction_date: string
    shares: number
    price_per_share: number
    brokerage?: number
    notes?: string
  }
): Promise<TransactionOut> => {
  const { data } = await api.post(`/api/v1/portfolio/${portfolioId}/transactions`, payload)
  return data
}

export const deleteTransaction = async (portfolioId: string, txnId: number): Promise<void> => {
  await api.delete(`/api/v1/portfolio/${portfolioId}/transactions/${txnId}`)
}

export const importHoldingsCsv = async (portfolioId: string, file: File): Promise<ImportResult> => {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post(`/api/v1/portfolio/${portfolioId}/import/holdings`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const importTransactionsCsv = async (portfolioId: string, file: File): Promise<ImportResult> => {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post(`/api/v1/portfolio/${portfolioId}/import/transactions`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ── Indices ───────────────────────────────────────────────────

export interface IndexPrice {
  index_code: string
  display_name: string
  price_date: string | null
  close_price: number | null
  return_1d: number | null
  return_1w: number | null
  return_1m: number | null
  return_3m: number | null
  return_6m: number | null
  return_1y: number | null
  return_ytd: number | null
  high_52w: number | null
  low_52w: number | null
}

export interface IndicesResponse {
  indices: IndexPrice[]
  as_of: string | null
}

export const getIndices = async (): Promise<IndicesResponse> => {
  const { data } = await api.get('/api/v1/market-data/indices')
  return data
}

export const getIndexHistory = async (indexCode: string, days = 365): Promise<{ index_code: string; history: { date: string; close: number | null; return_1d: number | null }[] }> => {
  const { data } = await api.get(`/api/v1/market-data/indices/${indexCode}/history`, { params: { days } })
  return data
}

// ── ETF / Managed Funds ───────────────────────────────────────

export interface FundRow {
  asx_code: string
  fund_name: string
  fund_type: 'ETF' | 'LIC' | 'MANAGED'
  asset_class: string | null
  index_tracked: string | null
  fund_manager: string | null
  mer_pct: number | null
  funds_under_mgmt_bn: number | null
  distribution_freq: string | null
  is_hedged: boolean | null
  close_price: number | null
  return_1d: number | null
  return_1w: number | null
  return_1m: number | null
  return_1y: number | null
  return_ytd: number | null
  distribution_yield: number | null
  nav_discount_pct: number | null
  high_52w: number | null
  low_52w: number | null
  price_date: string | null
}

export interface FundsResponse {
  funds: FundRow[]
  total: number
  as_of: string | null
}

export const getFunds = async (params?: {
  fund_type?: 'ETF' | 'LIC' | 'MANAGED'
  asset_class?: string
  sort?: string
  order?: 'asc' | 'desc'
  limit?: number
}): Promise<FundsResponse> => {
  const { data } = await api.get('/api/v1/market-data/funds', { params })
  return data
}

// ── Index Detail ──────────────────────────────────────────────

export interface IndexConstituent {
  asx_code: string
  company_name: string
  sector: string | null
  market_cap: number | null
  weight_pct: number | null
  price: number | null
  return_1d: number | null
  return_1y: number | null
  pe_ratio: number | null
  dividend_yield: number | null
  franking_pct: number | null
}

export interface IndexSectorBreakdown {
  sector: string
  count: number
  weight_pct: number
  market_cap_bn: number
}

export interface IndexPrimaryETF {
  asx_code: string | null
  name: string | null
  mer_pct: number | null
}

export interface IndexDetail {
  index_code: string
  display_name: string
  description: string | null
  eligibility: string | null
  methodology: string | null
  rebalance_freq: string | null
  market_coverage: string | null
  primary_etf: IndexPrimaryETF | null
  price: IndexPrice | null
  constituents: IndexConstituent[]
  total_market_cap_bn: number | null
  constituent_count: number
  sector_breakdown: IndexSectorBreakdown[]
}

export const getIndexDetail = async (indexCode: string): Promise<IndexDetail> => {
  const { data } = await api.get(`/api/v1/market-data/indices/${indexCode}`)
  return data
}

// ── Fund Detail ───────────────────────────────────────────────

export interface FundHistoryPoint {
  date: string
  close: number | null
  return_1d: number | null
  distribution_yield: number | null
  nav_discount_pct: number | null
}

export interface FundLatest {
  price_date: string | null
  close_price: number | null
  return_1d: number | null
  return_1w: number | null
  return_1m: number | null
  return_1y: number | null
  return_ytd: number | null
  return_3y_pa: number | null
  return_5y_pa: number | null
  distribution_yield: number | null
  nav_discount_pct: number | null
  high_52w: number | null
  low_52w: number | null
}

export interface FundDetail {
  asx_code: string
  fund_name: string
  fund_type: 'ETF' | 'LIC' | 'MANAGED'
  asset_class: string | null
  index_tracked: string | null
  fund_manager: string | null
  mer_pct: number | null
  funds_under_mgmt_bn: number | null
  distribution_freq: string | null
  is_hedged: boolean | null
  inception_date: string | null
  asx_url: string | null
  latest: FundLatest | null
  history: FundHistoryPoint[]
}

export const getFundDetail = async (asxCode: string, days = 365): Promise<FundDetail> => {
  const { data } = await api.get(`/api/v1/market-data/funds/${asxCode}`, { params: { days } })
  return data
}

export const getSimilarFunds = async (asxCode: string): Promise<{ similar: FundRow[] }> => {
  const { data } = await api.get(`/api/v1/market-data/funds/${asxCode}/similar`)
  return data
}

export interface FundConstituent {
  asx_code: string
  company_name: string
  sector: string | null
  market_cap: number | null
  weight_pct: number | null
  price: number | null
  return_1d: number | null
  return_1y: number | null
  pe_ratio: number | null
  dividend_yield: number | null
  franking_pct: number | null
}

export const getFundConstituents = async (asxCode: string): Promise<{ asx_code: string; source: string | null; constituents: FundConstituent[] }> => {
  const { data } = await api.get(`/api/v1/market-data/funds/${asxCode}/constituents`)
  return data
}

// ── Portfolio History & Dividends ─────────────────────────────

export interface PortfolioHistoryPoint {
  date: string
  value: number
  cost: number
  gain_loss: number
}

export interface PortfolioHistory {
  portfolio_id: string
  period: string
  history: PortfolioHistoryPoint[]
}

export interface DividendEvent {
  asx_code: string
  company_name: string | null
  ex_date: string | null
  payment_date: string | null
  amount: number
  franking_pct: number
  div_type: string | null
  quantity: number
  est_income: number | null
  gross_income: number | null
}

export interface PortfolioDividends {
  portfolio_id: string
  upcoming: DividendEvent[]
  received: DividendEvent[]
}

export const getPortfolioHistory = async (
  portfolioId: string,
  period = '1y',
): Promise<PortfolioHistory> => {
  const { data } = await api.get(`/api/v1/portfolio/${portfolioId}/history`, { params: { period } })
  return data
}

export const getPortfolioDividends = async (
  portfolioId: string,
  monthsAhead = 6,
): Promise<PortfolioDividends> => {
  const { data } = await api.get(`/api/v1/portfolio/${portfolioId}/dividends`, { params: { months_ahead: monthsAhead } })
  return data
}

export interface CgtDisposal {
  asx_code:          string
  sell_date:         string
  buy_date:          string
  quantity:          number
  proceeds:          number
  cost_base:         number
  capital_gain:      number
  held_days:         number
  discount_eligible: boolean
  discounted_gain:   number
  in_fy:             boolean
}

export interface CgtSummary {
  total_proceeds:  number
  total_cost_base: number
  gross_gain:      number
  discount_amount: number
  net_gain:        number
  total_gains:     number
  total_losses:    number
  disposal_count:  number
}

export interface TaxReport {
  portfolio_id: string
  tax_year:     number
  fy_label:     string
  fy_start:     string
  fy_end:       string
  summary:      CgtSummary
  disposals:    CgtDisposal[]
}

export const getTaxReport = async (portfolioId: string, taxYear?: number): Promise<TaxReport> => {
  const params = taxYear ? { tax_year: taxYear } : {}
  const { data } = await api.get(`/api/v1/portfolio/${portfolioId}/tax-report`, { params })
  return data
}

// ── AI & Anomalies ────────────────────────────────────────────────────────────

// Anomaly flag for market-wide feed (market page)
export interface AnomalyFlag {
  asx_code:     string
  company_name: string | null
  sector:       string | null
  flag_type:    string
  description:  string
  severity:     'low' | 'medium' | 'high'
  detected_at:  string
  price:        number | null
  return_1w:    number | null
  volume:       number | null
}

export interface AnomalyFeed {
  flags: AnomalyFlag[]
  total: number
}

export const getMarketAnomalies = async (
  limit = 50,
  flagType?: string,
): Promise<AnomalyFeed> => {
  const params: Record<string, unknown> = { limit }
  if (flagType) params.flag_type = flagType
  const { data } = await api.get('/api/v1/ai/anomalies', { params })
  return data
}

export interface PortfolioHoldingInsight {
  code:         string
  name:         string
  sector:       string
  quantity:     number
  avg_cost:     number
  cur_price:    number
  cur_value:    number
  gain_pct:     number
  weight_pct:   number
  div_yield:    number
  franking_pct: number
}

export interface PortfolioAiInsights {
  summary: string
  concentration_risk: { level: 'low' | 'medium' | 'high'; comment: string }
  sector_analysis:    { dominant_sector: string; comment: string }
  income_analysis:    { comment: string }
  key_risks:          string[]
  opportunities:      string[]
  recommendations:    string[]
}

export interface PortfolioInsightsResult {
  portfolio_id:       string
  portfolio_name:     string
  total_value:        number
  total_return_pct:   number
  portfolio_yield:    number
  annual_income:      number
  num_holdings:       number
  top3_concentration: number
  sector_allocation:  Record<string, number>
  holdings:           PortfolioHoldingInsight[]
  insights:           PortfolioAiInsights
  cached:             boolean
  generated_at:       string
  expires_at:         string
}

export const getPortfolioInsights = async (
  portfolioId: string,
  refresh = false,
): Promise<PortfolioInsightsResult> => {
  const params = refresh ? { refresh: true } : {}
  const { data } = await api.get(`/api/v1/ai/portfolio-insights/${portfolioId}`, { params })
  return data
}

// ── Notifications ─────────────────────────────────────────────────────────────

export interface NotificationPreferences {
  portfolio_weekly_email:    boolean
  portfolio_threshold_email: boolean
  portfolio_threshold_sms:   boolean
  portfolio_threshold_pct:   number
  alerts_email:              boolean
  alerts_sms:                boolean
  announcements_email:       boolean
  announcements_sms:         boolean
  phone_number:              string | null
  weekly_report_day:         number
  weekly_report_hour:        number
  timezone:                  string
}

export interface NotificationHistoryItem {
  id:                number
  channel:           string
  notification_type: string
  subject:           string | null
  recipient:         string | null
  status:            string
  error_message:     string | null
  attempt_count:     number
  sent_at:           string | null
  created_at:        string
}

export interface NotificationHistory {
  total: number
  items: NotificationHistoryItem[]
}

export const getNotificationPreferences = async (): Promise<NotificationPreferences> => {
  const { data } = await api.get('/api/v1/notifications/preferences')
  return data
}

export const updateNotificationPreferences = async (prefs: NotificationPreferences): Promise<NotificationPreferences> => {
  const { data } = await api.put('/api/v1/notifications/preferences', prefs)
  return data
}

export const getNotificationHistory = async (params?: {
  channel?: string
  notification_type?: string
  limit?: number
  offset?: number
}): Promise<NotificationHistory> => {
  const { data } = await api.get('/api/v1/notifications/history', { params })
  return data
}

export const sendTestNotification = async (channel: 'email' | 'sms'): Promise<{ ok: boolean; channel: string; recipient: string }> => {
  const { data } = await api.post('/api/v1/notifications/test', { channel })
  return data
}

// ── Announcements Feed ────────────────────────────────────────────────────────

export interface AnnouncementFeedItem {
  id:               number
  asx_code:         string
  company_name:     string | null
  title:            string
  document_type:    string | null
  url:              string | null
  market_sensitive: boolean
  price_sensitive:  boolean
  released_at:      string | null
  num_pages:        number | null
  source_type:      'asx_filing' | 'company_filing' | 'market_news'
  source_label:     string
}

export interface AnnouncementFeed {
  total:          number
  limit:          number
  offset:         number
  announcements:  AnnouncementFeedItem[]
  document_types: string[]
}

export const getAnnouncements = async (params?: {
  asx_code?: string
  sector?: string
  document_type?: string
  sensitive_only?: boolean
  search?: string
  tab?: string
  date_from?: string
  date_to?: string
  watchlist_only?: boolean
  limit?: number
  offset?: number
}): Promise<AnnouncementFeed> => {
  const { data } = await api.get('/api/v1/announcements', { params })
  return data
}

export const getLatestAnnouncements = async (limit = 20): Promise<{ announcements: AnnouncementFeedItem[] }> => {
  const { data } = await api.get('/api/v1/announcements/latest', { params: { limit } })
  return data
}

export const getCompanyAnnouncementsFeed = async (
  code: string,
  limit = 30,
  offset = 0,
): Promise<{ asx_code: string; total: number; announcements: AnnouncementFeedItem[] }> => {
  const { data } = await api.get(`/api/v1/announcements/${code}`, { params: { limit, offset } })
  return data
}

// ── Global Markets ────────────────────────────────────────────

export interface GlobalIndexPrice {
  index_code:  string
  index_name:  string
  region:      string
  country:     string
  currency:    string
  price_date:  string | null
  close_price: number | null
  open_price:  number | null
  high_price:  number | null
  low_price:   number | null
  return_1d:   number | null
  return_1w:   number | null
  return_1m:   number | null
  return_3m:   number | null
  return_6m:   number | null
  return_1y:   number | null
  return_ytd:  number | null
  high_52w:    number | null
  low_52w:     number | null
}

export interface GlobalFxRate {
  fx_pair:    string
  name:       string
  rate_date:  string | null
  rate:       number | null
  open_rate:  number | null
  high_rate:  number | null
  low_rate:   number | null
  return_1d:  number | null
  return_1w:  number | null
  return_1m:  number | null
  return_ytd: number | null
}

export interface GlobalMarketsResponse {
  as_of:    string | null
  regions:  { region: string; indices: GlobalIndexPrice[] }[]
  fx_rates: GlobalFxRate[]
}

export const getGlobalMarkets = async (): Promise<GlobalMarketsResponse> => {
  const { data } = await api.get('/api/v1/global-markets/')
  return data
}

export interface GlobalIndexDetail extends GlobalIndexPrice {
  history: { date: string; close: number | null }[]
}

export const getGlobalIndexDetail = async (code: string, days = 365): Promise<GlobalIndexDetail> => {
  const { data } = await api.get(`/api/v1/global-markets/${code}?days=${days}`)
  return data
}

// ── Commodities ───────────────────────────────────────────────

export interface CommodityPrice {
  commodity_code: string
  commodity_name: string
  category:       string
  unit:           string | null
  price_date:     string | null
  close_price:    number | null
  open_price:     number | null
  high_price:     number | null
  low_price:      number | null
  return_1d:      number | null
  return_1w:      number | null
  return_1m:      number | null
  return_3m:      number | null
  return_6m:      number | null
  return_1y:      number | null
  return_ytd:     number | null
  high_52w:       number | null
  low_52w:        number | null
}

export interface CommoditiesResponse {
  as_of:      string | null
  categories: { category: string; commodities: CommodityPrice[] }[]
}

export const getCommodities = async (): Promise<CommoditiesResponse> => {
  const { data } = await api.get('/api/v1/commodities/')
  return data
}

export interface CommodityDetail extends CommodityPrice {
  history: { date: string; close: number | null }[]
}

export const getCommodityDetail = async (code: string, days = 365): Promise<CommodityDetail> => {
  const { data } = await api.get(`/api/v1/commodities/${code}?days=${days}`)
  return data
}

// ── Saved Screens ─────────────────────────────────────────────────────────────

export interface SavedScreen {
  id:          string
  user_id:     string
  user_name:   string
  name:        string
  description: string | null
  filters:     ScreenerFilter[]
  sort_by:     string
  sort_dir:    string
  is_public:   boolean
  use_count:   number
  created_at:  string | null
  updated_at:  string | null
}

export const getCommunityScreens = async (): Promise<{ screens: SavedScreen[] }> => {
  const { data } = await api.get('/api/v1/screens/community')
  return data
}

export const getMyScreens = async (): Promise<{ screens: SavedScreen[] }> => {
  const { data } = await api.get('/api/v1/screens/mine')
  return data
}

export const saveScreen = async (payload: {
  name: string
  description?: string
  filters: ScreenerFilter[]
  sort_by: string
  sort_dir: string
  is_public: boolean
}): Promise<SavedScreen> => {
  const { data } = await api.post('/api/v1/screens', payload)
  return data
}

export const updateScreen = async (id: string, payload: Partial<{
  name: string
  description: string
  filters: ScreenerFilter[]
  sort_by: string
  sort_dir: string
  is_public: boolean
}>): Promise<SavedScreen> => {
  const { data } = await api.put(`/api/v1/screens/${id}`, payload)
  return data
}

export const deleteScreen = async (id: string): Promise<void> => {
  await api.delete(`/api/v1/screens/${id}`)
}

export const incrementScreenUse = async (id: string): Promise<void> => {
  await api.post(`/api/v1/screens/${id}/use`).catch(() => {})
}

// ── Billing ───────────────────────────────────────────────────────────────────

export interface PlanFeatures {
  portfolios:    number
  watchlists:    number
  stocks_per_wl: number
  alerts:        number
  nl_screener:   boolean
  csv_export:    boolean
  seat_limit:    number
}

export interface SeatOption {
  seats:             number
  monthly_aud:       number
  yearly_aud:        number
  price_id_monthly:  string | null
  price_id_yearly:   string | null
}

export interface BillingPlan {
  id:                string
  name:              string
  monthly_aud:       number | null
  yearly_aud:        number | null
  price_id_monthly:  string | null
  price_id_yearly:   string | null
  seats?:            number
  seats_options?:    SeatOption[]
  features:          PlanFeatures
  highlight:         boolean
}

export const getBillingPlans = async (): Promise<{ plans: BillingPlan[] }> => {
  const { data } = await api.get('/api/v1/billing/plans')
  return data
}

export const createCheckoutSession = async (
  plan: string,
  interval: 'monthly' | 'yearly',
  seats = 1,
): Promise<{ url: string }> => {
  const { data } = await api.post('/api/v1/billing/checkout', { plan, interval, seats })
  return data
}

export const createBillingPortal = async (): Promise<{ url: string }> => {
  const { data } = await api.post('/api/v1/billing/portal')
  return data
}

// ── Mining Metrics ────────────────────────────────────────────────────────────

export interface MiningMetrics {
  asx_code:                  string
  is_miner:                  boolean
  has_data:                  boolean
  primary_commodity:         string | null
  aisc_per_oz:               number | null
  cash_cost_per_oz:          number | null
  aisc_per_tonne:            number | null
  ore_reserves_mt:           number | null
  mineral_resources_mt:      number | null
  reserve_grade:             number | null
  reserve_life_yrs:          number | null
  production_oz_ttm:         number | null
  production_kt_ttm:         number | null
  production_guidance_low:   number | null
  production_guidance_high:  number | null
  sustaining_capex_m:        number | null
  growth_capex_m:            number | null
  commodity_price_ref:       number | null
  report_period:             string | null
  updated_at:                string | null
}

export const getMiningMetrics = async (code: string): Promise<MiningMetrics> => {
  const { data } = await api.get(`/api/v1/companies/${code}/mining-metrics`)
  return data
}

// ── REIT Metrics ──────────────────────────────────────────────────────────────

export interface ReitMetrics {
  asx_code:               string
  is_reit:                boolean
  has_data:               boolean
  reit_sector:            string | null
  ffo_per_unit:           number | null
  affo_per_unit:          number | null
  price_to_ffo:           number | null
  nta_per_unit:           number | null
  premium_to_nta:         number | null
  wale_yrs:               number | null
  occupancy_pct:          number | null
  total_assets_bn:        number | null
  gla_sqm:                number | null
  num_properties:         number | null
  distribution_per_unit:  number | null
  distribution_yield:     number | null
  payout_of_ffo:          number | null
  gearing_pct:            number | null
  interest_cover:         number | null
  report_period:          string | null
  updated_at:             string | null
}

export const getReitMetrics = async (code: string): Promise<ReitMetrics> => {
  const { data } = await api.get(`/api/v1/companies/${code}/reit-metrics`)
  return data
}

// ── Capital Raises ────────────────────────────────────────────────────────────

export interface CapitalRaiseEvent {
  raise_type:          string
  amount_m:            number | null
  price_per_share:     number | null
  shares_issued:       number | null
  discount_pct:        number | null
  announcement_date:   string
  record_date:         string | null
  settlement_date:     string | null
  title:               string | null
  url:                 string | null
}

export interface CapitalRaisesResponse {
  asx_code: string
  raises:   CapitalRaiseEvent[]
  total:    number
}

export const getCapitalRaises = async (code: string): Promise<CapitalRaisesResponse> => {
  const { data } = await api.get(`/api/v1/companies/${code}/capital-raises`)
  return data
}

