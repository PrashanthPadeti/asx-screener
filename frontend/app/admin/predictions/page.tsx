'use client'
/**
 * ASX Price Predictions — Admin-only ML forecast page
 *
 * Models: XGBoost · Random Forest · SVM · LSTM · Ensemble
 * Horizons: 5 / 10 / 20 / 30 / 50 trading days
 *
 * DISCLAIMER: Statistical models only. Not investment advice.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '@/lib/api'
import {
  BrainCircuit, Play, RefreshCw, AlertTriangle, TrendingUp,
  TrendingDown, Minus, ChevronDown, ChevronUp, X, Search, Info,
} from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────────────────

type Direction = 'bullish' | 'neutral' | 'bearish'

type PredRow = {
  asx_code:             string
  company_name:         string
  sector:               string | null
  current_price:        number | null
  predicted_price:      number | null
  predicted_change_pct: number | null
  lower_bound:          number | null
  upper_bound:          number | null
  direction:            Direction
  confidence_score:     number | null
  r2_score:             number | null
  data_points:          number | null
}

type LatestResp = {
  prediction_date:   string
  model:             string
  horizon_days:      number
  total:             number
  direction_summary: Record<string, number>
  results:           PredRow[]
}

type StatusResp = {
  running:       boolean
  started_at:    string | null
  completed_at:  string | null
  stocks_done:   number
  total_stocks:  number
  progress_pct:  number
  last_summary:  Record<string, unknown> | null
  error:         string | null
}

type StockDetail = {
  asx_code:        string
  company_name:    string
  prediction_date: string
  horizons:        number[]
  by_model:        Record<string, Record<number, {
    predicted_change_pct: number | null
    predicted_price:      number | null
    direction:            Direction
    confidence_score:     number | null
    r2_score:             number | null
  }>>
  current_price: number | null
}

// ── Constants ─────────────────────────────────────────────────────────────────

const MODELS = [
  { key: 'ensemble', label: 'Ensemble',      desc: 'Confidence-weighted average of all models' },
  { key: 'xgboost',  label: 'XGBoost',       desc: 'Gradient boosting regression' },
  { key: 'rf',       label: 'Random Forest', desc: 'Ensemble of decision trees' },
  { key: 'svm',      label: 'SVM',           desc: 'Support Vector classifier (direction)' },
  { key: 'lstm',     label: 'LSTM',          desc: 'Deep learning (top 200 stocks only)' },
]

const HORIZONS = [5, 10, 20, 30, 50]

const MODEL_COLORS: Record<string, string> = {
  ensemble: 'bg-indigo-100 text-indigo-700',
  xgboost:  'bg-orange-100 text-orange-700',
  rf:       'bg-emerald-100 text-emerald-700',
  svm:      'bg-purple-100 text-purple-700',
  lstm:     'bg-blue-100 text-blue-700',
}

const HORIZON_RELIABILITY: Record<number, { label: string; color: string }> = {
  5:  { label: 'High reliability',   color: 'text-emerald-600' },
  10: { label: 'Good reliability',   color: 'text-emerald-500' },
  20: { label: 'Moderate',           color: 'text-amber-500'   },
  30: { label: 'Lower reliability',  color: 'text-orange-500'  },
  50: { label: 'Speculative',        color: 'text-red-500'     },
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function dirIcon(d: Direction, size = 'w-4 h-4') {
  if (d === 'bullish') return <TrendingUp  className={`${size} text-emerald-500`} />
  if (d === 'bearish') return <TrendingDown className={`${size} text-red-500`} />
  return <Minus className={`${size} text-gray-400`} />
}

function dirBadge(d: Direction) {
  const cls = d === 'bullish'
    ? 'bg-emerald-100 text-emerald-700'
    : d === 'bearish'
    ? 'bg-red-100 text-red-700'
    : 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${cls}`}>
      {dirIcon(d, 'w-3 h-3')}
      {d.charAt(0).toUpperCase() + d.slice(1)}
    </span>
  )
}

function fmtPct(v: number | null, decimals = 2) {
  if (v == null) return '—'
  const s = v.toFixed(decimals)
  return v > 0 ? `+${s}%` : `${s}%`
}

function pctColor(v: number | null) {
  if (v == null) return 'text-gray-400'
  if (v >  2) return 'text-emerald-600 font-semibold'
  if (v < -2) return 'text-red-600 font-semibold'
  return 'text-gray-700'
}

function ConfBar({ v }: { v: number | null }) {
  if (v == null) return <span className="text-gray-400 text-xs">—</span>
  const pct  = Math.round(v * 100)
  const color = pct >= 70 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 bg-gray-200 rounded-full h-1.5">
        <div className={`${color} h-1.5 rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] text-gray-500">{pct}%</span>
    </div>
  )
}

// ── Stock Detail Modal ────────────────────────────────────────────────────────

function StockModal({ code, onClose }: { code: string; onClose: () => void }) {
  const [detail, setDetail] = useState<StockDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/api/v1/predictions/${code}`)
      .then(r => setDetail(r.data))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [code])

  const allModels = detail ? Object.keys(detail.by_model) : []
  const horizons  = detail?.horizons ?? HORIZONS

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] overflow-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 sticky top-0 bg-white z-10">
          <div>
            <h3 className="font-bold text-slate-900 text-lg">{code}</h3>
            <p className="text-xs text-slate-500">{detail?.company_name}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {loading && (
          <div className="flex justify-center py-12">
            <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {detail && (
          <div className="p-6">
            <p className="text-xs text-slate-500 mb-4">
              Current price: <strong>${detail.current_price?.toFixed(3)}</strong>
              &nbsp;·&nbsp;Prediction date: {detail.prediction_date}
            </p>

            {/* Model × Horizon grid */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50">
                    <th className="text-left px-3 py-2 font-semibold text-slate-600 text-xs">Model</th>
                    {horizons.map(h => (
                      <th key={h} className="text-center px-3 py-2 font-semibold text-slate-600 text-xs">
                        {h}d
                        <div className={`text-[10px] font-normal ${HORIZON_RELIABILITY[h]?.color}`}>
                          {HORIZON_RELIABILITY[h]?.label}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {allModels.map(model => (
                    <tr key={model} className="border-t border-gray-100 hover:bg-slate-50/50">
                      <td className="px-3 py-2.5">
                        <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${MODEL_COLORS[model] ?? 'bg-gray-100 text-gray-600'}`}>
                          {MODELS.find(m => m.key === model)?.label ?? model}
                        </span>
                      </td>
                      {horizons.map(h => {
                        const p = detail.by_model[model]?.[h]
                        if (!p) return <td key={h} className="text-center px-3 py-2.5 text-gray-300">—</td>
                        return (
                          <td key={h} className="text-center px-3 py-2.5">
                            <div className={`font-semibold ${pctColor(p.predicted_change_pct)}`}>
                              {fmtPct(p.predicted_change_pct)}
                            </div>
                            <div className="text-[11px] text-slate-400">
                              ${p.predicted_price?.toFixed(3) ?? '—'}
                            </div>
                            <div className="mt-0.5">{dirBadge(p.direction)}</div>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
              <strong>Statistical models only.</strong> Past performance is not indicative of future returns.
              These predictions are for analysis only and are not investment recommendations.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// Main Page
// ══════════════════════════════════════════════════════════════════════════════

export default function PredictionsPage() {
  // ── State ──────────────────────────────────────────────────────────────────
  const [status,    setStatus]    = useState<StatusResp | null>(null)
  const [data,      setData]      = useState<LatestResp | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState<string | null>(null)
  const [triggering, setTriggering] = useState(false)

  // Filters
  const [model,     setModel]     = useState('ensemble')
  const [horizon,   setHorizon]   = useState(10)
  const [direction, setDirection] = useState('')
  const [sector,    setSector]    = useState('')
  const [search,    setSearch]    = useState('')

  // UI
  const [modalCode, setModalCode] = useState<string | null>(null)
  const [sortCol,   setSortCol]   = useState<'pct' | 'conf' | 'price'>('pct')
  const [sortAsc,   setSortAsc]   = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Fetch predictions ──────────────────────────────────────────────────────
  const fetchPredictions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string | number> = {
        model, horizon, limit: 200, offset: 0,
      }
      if (direction) params.direction = direction
      if (sector)    params.sector    = sector
      if (search)    params.search    = search

      const r = await api.get('/api/v1/predictions/latest', { params })
      setData(r.data)
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } }; message?: string }
      const status = err?.response?.status
      const detail = err?.response?.data?.detail ?? ''
      // 404 = no predictions table or no runs yet — show empty state, not error
      if (status === 404 || detail.includes('No predictions found')) {
        setData(null)
        setError(null)
      } else {
        setError(detail || err?.message || 'Failed to load predictions')
      }
    } finally {
      setLoading(false)
    }
  }, [model, horizon, direction, sector, search])

  // ── Fetch status ───────────────────────────────────────────────────────────
  const fetchStatus = useCallback(async () => {
    try {
      const r = await api.get('/api/v1/predictions/status')
      setStatus(r.data)
      // If job just completed, refresh predictions
      if (!r.data.running && r.data.last_summary) {
        fetchPredictions()
      }
    } catch { /* silent */ }
  }, [fetchPredictions])

  // Poll while a job is running
  useEffect(() => {
    fetchStatus()
    fetchPredictions()
  }, [])  // eslint-disable-line

  useEffect(() => {
    if (status?.running) {
      pollRef.current = setInterval(fetchStatus, 4000)
    } else {
      if (pollRef.current) clearInterval(pollRef.current)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [status?.running, fetchStatus])

  // Re-fetch when filters change
  useEffect(() => {
    fetchPredictions()
  }, [fetchPredictions])

  // ── Trigger a run ──────────────────────────────────────────────────────────
  async function triggerRun(force = false) {
    if (status?.running || triggering) return
    setTriggering(true)
    try {
      await api.post('/api/v1/predictions/trigger', null, { params: { force, top_n: 1000 } })
      await fetchStatus()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setError(err?.response?.data?.detail || err?.message || 'Failed to start prediction run')
    } finally {
      setTriggering(false)
    }
  }

  // ── Sort predictions ───────────────────────────────────────────────────────
  const sorted = (data?.results ?? []).slice().sort((a, b) => {
    const av = sortCol === 'pct'  ? (a.predicted_change_pct ?? -999)
             : sortCol === 'conf' ? (a.confidence_score ?? 0)
             : (a.current_price ?? 0)
    const bv = sortCol === 'pct'  ? (b.predicted_change_pct ?? -999)
             : sortCol === 'conf' ? (b.confidence_score ?? 0)
             : (b.current_price ?? 0)
    return sortAsc ? av - bv : bv - av
  })

  function toggleSort(col: typeof sortCol) {
    if (sortCol === col) setSortAsc(!sortAsc)
    else { setSortCol(col); setSortAsc(false) }
  }

  const isRunning  = status?.running ?? false
  const hasResults = (data?.results?.length ?? 0) > 0
  const dirSum     = data?.direction_summary ?? {}
  const totalStks  = (dirSum.bullish ?? 0) + (dirSum.neutral ?? 0) + (dirSum.bearish ?? 0)

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-900 px-6 py-5">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-500/20 rounded-xl">
                <BrainCircuit className="w-6 h-6 text-indigo-300" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">Price Predictions</h1>
                <p className="text-slate-400 text-xs mt-0.5">
                  ML-powered forecasting · XGBoost · Random Forest · SVM · LSTM
                </p>
              </div>
              <span className="ml-2 px-2 py-0.5 bg-red-500/20 text-red-300 text-[10px] font-bold rounded-full border border-red-500/30">
                ADMIN ONLY
              </span>
            </div>

            {/* Run button + status */}
            <div className="flex flex-col items-end gap-2">
              <button
                onClick={() => triggerRun(false)}
                disabled={isRunning || triggering}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500
                           disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm
                           font-semibold rounded-xl transition-colors"
              >
                {isRunning || triggering
                  ? <RefreshCw className="w-4 h-4 animate-spin" />
                  : <Play className="w-4 h-4" />}
                {isRunning ? 'Running…' : triggering ? 'Starting…' : 'Run Predictions'}
              </button>

              {status && (
                <div className="text-right text-[11px] text-slate-400">
                  {isRunning
                    ? <span className="text-indigo-300">
                        {status.stocks_done}/{status.total_stocks} stocks · {status.progress_pct}%
                      </span>
                    : status.completed_at
                    ? <span>Last run: {new Date(status.completed_at).toLocaleString('en-AU')}</span>
                    : <span>No runs yet</span>}
                  {data?.prediction_date && !isRunning && (
                    <div className="text-slate-500">
                      Showing predictions from {data.prediction_date}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Progress bar */}
          {isRunning && (
            <div className="mt-3 bg-slate-700/50 rounded-full h-1.5">
              <div
                className="bg-indigo-400 h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${status?.progress_pct ?? 0}%` }}
              />
            </div>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-5">

        {/* Disclaimer */}
        <div className="flex items-start gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
          <span>
            <strong>Statistical models only — not investment advice.</strong> These predictions are
            based on historical price patterns and technical indicators. Past performance is not
            indicative of future results. Prediction accuracy decreases significantly at longer
            horizons. Always consult a licensed financial adviser (AFSL holder) before trading.
          </span>
        </div>

        {/* Error */}
        {(error || status?.error) && (
          <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
            {error || status?.error}
          </div>
        )}

        {/* No predictions yet */}
        {!hasResults && !loading && !isRunning && !error && (
          <div className="text-center py-16 bg-white rounded-2xl border border-slate-200">
            <BrainCircuit className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="font-semibold text-slate-700 mb-1">No predictions yet</h3>
            <p className="text-sm text-slate-500 mb-4">
              Click <strong>Run Predictions</strong> to generate ML forecasts for the top 1,000 ASX stocks.
              <br />
              First run takes ~20–30 minutes (LSTM for top 200, XGBoost/RF/SVM for all 1,000).
            </p>
            <button
              onClick={() => triggerRun(false)}
              className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              <Play className="w-4 h-4 inline mr-1.5" />Run Now
            </button>
          </div>
        )}

        {/* Running state */}
        {isRunning && (
          <div className="bg-white rounded-2xl border border-indigo-200 p-6">
            <div className="flex items-center gap-3 mb-4">
              <RefreshCw className="w-5 h-5 text-indigo-500 animate-spin" />
              <div>
                <div className="font-semibold text-slate-800">Prediction job running…</div>
                <div className="text-xs text-slate-500">
                  Processing {status?.stocks_done ?? 0} of {status?.total_stocks ?? 1000} stocks
                  &nbsp;·&nbsp;LSTM runs on top 200 stocks
                </div>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-3 text-sm">
              {[
                { label: 'XGBoost',       desc: 'Gradient boosting' },
                { label: 'Random Forest', desc: 'Ensemble trees' },
                { label: 'SVM',           desc: 'Classification' },
                { label: 'LSTM',          desc: 'Top 200 only' },
              ].map(m => (
                <div key={m.label} className="bg-slate-50 rounded-lg p-3 text-center">
                  <div className="font-semibold text-slate-700">{m.label}</div>
                  <div className="text-[11px] text-slate-400">{m.desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Results */}
        {hasResults && (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-white rounded-xl border border-slate-200 p-4">
                <div className="text-xs text-slate-500 mb-0.5">Total Stocks</div>
                <div className="text-2xl font-bold text-slate-800">{totalStks.toLocaleString()}</div>
                <div className="text-[11px] text-slate-400 mt-0.5">
                  {MODELS.find(m => m.key === model)?.label} · {horizon}d horizon
                </div>
              </div>
              <div className="bg-emerald-50 rounded-xl border border-emerald-200 p-4">
                <div className="text-xs text-emerald-600 mb-0.5">Bullish</div>
                <div className="text-2xl font-bold text-emerald-700">
                  {(dirSum.bullish ?? 0).toLocaleString()}
                </div>
                <div className="text-[11px] text-emerald-500 mt-0.5">
                  {totalStks > 0 ? Math.round((dirSum.bullish ?? 0) / totalStks * 100) : 0}% of stocks
                </div>
              </div>
              <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
                <div className="text-xs text-gray-500 mb-0.5">Neutral</div>
                <div className="text-2xl font-bold text-gray-700">
                  {(dirSum.neutral ?? 0).toLocaleString()}
                </div>
                <div className="text-[11px] text-gray-400 mt-0.5">
                  {totalStks > 0 ? Math.round((dirSum.neutral ?? 0) / totalStks * 100) : 0}% of stocks
                </div>
              </div>
              <div className="bg-red-50 rounded-xl border border-red-200 p-4">
                <div className="text-xs text-red-500 mb-0.5">Bearish</div>
                <div className="text-2xl font-bold text-red-700">
                  {(dirSum.bearish ?? 0).toLocaleString()}
                </div>
                <div className="text-[11px] text-red-400 mt-0.5">
                  {totalStks > 0 ? Math.round((dirSum.bearish ?? 0) / totalStks * 100) : 0}% of stocks
                </div>
              </div>
            </div>

            {/* Filters */}
            <div className="bg-white rounded-xl border border-slate-200 px-4 py-3">
              <div className="flex flex-wrap gap-3 items-center">
                {/* Model */}
                <div className="flex gap-1">
                  {MODELS.map(m => (
                    <button
                      key={m.key}
                      onClick={() => setModel(m.key)}
                      title={m.desc}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                        model === m.key
                          ? (MODEL_COLORS[m.key] ?? 'bg-indigo-100 text-indigo-700') + ' ring-1 ring-inset ring-current'
                          : 'text-slate-500 hover:bg-slate-100'
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>

                <div className="h-5 border-l border-slate-200" />

                {/* Horizon */}
                <div className="flex gap-1">
                  {HORIZONS.map(h => (
                    <button
                      key={h}
                      onClick={() => setHorizon(h)}
                      className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                        horizon === h
                          ? `bg-slate-800 text-white`
                          : 'text-slate-500 hover:bg-slate-100'
                      }`}
                    >
                      {h}d
                    </button>
                  ))}
                </div>

                <div className="h-5 border-l border-slate-200" />

                {/* Direction */}
                <select
                  value={direction}
                  onChange={e => setDirection(e.target.value)}
                  className="text-xs border border-slate-200 rounded-lg px-2 py-1.5 text-slate-600"
                >
                  <option value="">All directions</option>
                  <option value="bullish">Bullish only</option>
                  <option value="neutral">Neutral only</option>
                  <option value="bearish">Bearish only</option>
                </select>

                {/* Search */}
                <div className="relative ml-auto">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                  <input
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="Search code or company…"
                    className="pl-7 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg text-slate-700 w-48"
                  />
                </div>

                <button
                  onClick={fetchPredictions}
                  disabled={loading}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
              </div>

              {/* Horizon reliability note */}
              <div className={`mt-2 text-[11px] flex items-center gap-1 ${HORIZON_RELIABILITY[horizon]?.color}`}>
                <Info className="w-3 h-3" />
                {horizon}d horizon — {HORIZON_RELIABILITY[horizon]?.label}.
                {horizon >= 30 && ' Treat with caution — longer horizons have significantly lower accuracy.'}
              </div>
            </div>

            {/* Table */}
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-900 text-slate-300 text-[11px] uppercase tracking-wide">
                      <th className="text-left px-4 py-3 font-semibold">#</th>
                      <th className="text-left px-4 py-3 font-semibold">Stock</th>
                      <th className="text-left px-4 py-3 font-semibold hidden md:table-cell">Sector</th>
                      <th
                        className="text-right px-4 py-3 font-semibold cursor-pointer hover:text-white"
                        onClick={() => toggleSort('price')}
                      >
                        Current {sortCol === 'price' && (sortAsc ? '↑' : '↓')}
                      </th>
                      <th
                        className="text-right px-4 py-3 font-semibold cursor-pointer hover:text-white"
                        onClick={() => toggleSort('pct')}
                      >
                        Predicted {horizon}d {sortCol === 'pct' && (sortAsc ? '↑' : '↓')}
                      </th>
                      <th className="text-right px-4 py-3 font-semibold hidden lg:table-cell">
                        Pred. Price
                      </th>
                      <th className="text-center px-4 py-3 font-semibold">Direction</th>
                      <th
                        className="text-left px-4 py-3 font-semibold cursor-pointer hover:text-white hidden md:table-cell"
                        onClick={() => toggleSort('conf')}
                      >
                        Confidence {sortCol === 'conf' && (sortAsc ? '↑' : '↓')}
                      </th>
                      <th className="text-center px-4 py-3 font-semibold hidden xl:table-cell">R²</th>
                      <th className="text-center px-4 py-3 font-semibold">Models</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((row, i) => (
                      <tr
                        key={row.asx_code}
                        className="border-t border-slate-100 hover:bg-slate-50/60 transition-colors cursor-pointer"
                        onClick={() => setModalCode(row.asx_code)}
                      >
                        <td className="px-4 py-3 text-slate-400 text-xs">{i + 1}</td>
                        <td className="px-4 py-3">
                          <div className="font-bold text-slate-800">{row.asx_code}</div>
                          <div className="text-[11px] text-slate-500 truncate max-w-[140px]">
                            {row.company_name}
                          </div>
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell">
                          <span className="text-[11px] text-slate-500">{row.sector ?? '—'}</span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-slate-700">
                          {row.current_price != null ? `$${row.current_price.toFixed(3)}` : '—'}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className={`font-mono text-base ${pctColor(row.predicted_change_pct)}`}>
                            {fmtPct(row.predicted_change_pct)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right hidden lg:table-cell font-mono text-slate-600 text-xs">
                          {row.predicted_price != null ? `$${row.predicted_price.toFixed(3)}` : '—'}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {dirBadge(row.direction)}
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell">
                          <ConfBar v={row.confidence_score} />
                        </td>
                        <td className="px-4 py-3 text-center hidden xl:table-cell text-xs text-slate-500">
                          {row.r2_score != null ? row.r2_score.toFixed(2) : '—'}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={e => { e.stopPropagation(); setModalCode(row.asx_code) }}
                            className="text-[11px] text-indigo-600 hover:text-indigo-800 font-semibold underline"
                          >
                            All models
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {sorted.length === 0 && !loading && (
                <div className="text-center py-10 text-slate-400 text-sm">
                  No predictions match your filters.
                </div>
              )}

              {loading && (
                <div className="flex justify-center py-8">
                  <div className="w-6 h-6 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                </div>
              )}

              <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50 text-[11px] text-slate-400 flex items-center justify-between">
                <span>Showing {sorted.length} of {data?.total ?? 0} stocks</span>
                {data?.prediction_date && (
                  <span>Predictions from {data.prediction_date}</span>
                )}
              </div>
            </div>

            {/* Model legend */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {MODELS.map(m => (
                <div key={m.key} className="bg-white rounded-lg border border-slate-200 px-3 py-2">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${MODEL_COLORS[m.key]}`}>
                      {m.label}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-500">{m.desc}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Stock detail modal */}
      {modalCode && (
        <StockModal code={modalCode} onClose={() => setModalCode(null)} />
      )}
    </div>
  )
}
