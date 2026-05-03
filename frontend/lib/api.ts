import axios from 'axios'
import { getStoredAccessToken } from './auth'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://209.38.84.102:8000'

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

/**
 * Trigger a CSV export download of the current screen (max 5,000 rows).
 * Uses window.location / fetch + blob to trigger browser download.
 */
export const exportScreener = async (
  filters: ScreenerFilter[],
  options: { sort_by?: string; sort_dir?: string } = {}
): Promise<void> => {
  const response = await fetch(`${API_BASE}/api/v1/screener/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filters,
      sort_by: options.sort_by || 'market_cap',
      sort_dir: options.sort_dir || 'desc',
      page: 1,
      page_size: 50,  // ignored server-side for export
    }),
  })
  if (!response.ok) throw new Error(`Export failed: ${response.statusText}`)
  const blob = await response.blob()
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  const cd   = response.headers.get('content-disposition') || ''
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
  return_1w: number | null   // decimal ratio
  return_1m: number | null   // decimal ratio
  market_cap: number | null  // AUD millions
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

export const getMarketMovers = async (): Promise<MoversResponse> => {
  const { data } = await api.get('/api/v1/market/movers')
  return data
}

export const getMarketSectors = async (): Promise<SectorsResponse> => {
  const { data } = await api.get('/api/v1/market/sectors')
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
