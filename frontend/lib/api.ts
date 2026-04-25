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

export interface ScreenerRow {
  asx_code: string
  company_name: string
  gics_sector: string | null
  is_reit: boolean
  is_miner: boolean
  is_asx200: boolean
  close: number | null
  open: number | null
  high: number | null
  low: number | null
  volume: number | null
  change_pct: number | null
  high_52w: number | null
  low_52w: number | null
  market_cap: number | null
  pe_ratio: number | null
  pb_ratio: number | null
  dividend_yield: number | null
  grossed_up_yield: number | null
  roe: number | null
  debt_to_equity: number | null
  revenue_growth_1y: number | null
  piotroski_score: number | null
}

export interface ScreenerResponse {
  data: ScreenerRow[]
  total: number
  page: number
  page_size: number
  total_pages: number
  filters_applied: number
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

export const getScreenerFields = async () => {
  const { data } = await api.get('/api/v1/screener/fields')
  return data
}
