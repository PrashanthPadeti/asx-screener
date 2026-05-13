'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { RefreshCw, CheckCircle, AlertTriangle, Clock, XCircle, Activity, Play, Loader2 } from 'lucide-react'

interface JobStatus {
  job: string
  job_id: string
  schedule: string
  type: 'apscheduler' | 'cron' | 'interval'
  last_run: string | null
  row_count: number | null
  table: string
  description: string
}

// Heavy cron jobs that can't be triggered via button
const HEAVY_JOBS = new Set(['universe_build', 'weekly_fundamentals', 'eod_price_download', 'daily_metrics'])

function staleness(lastRun: string | null, scheduleType: string): 'ok' | 'warn' | 'stale' | 'never' {
  if (!lastRun) return 'never'
  const diff = Date.now() - new Date(lastRun).getTime()
  const hours = diff / 1000 / 3600
  if (scheduleType === 'interval') return hours < 1 ? 'ok' : hours < 4 ? 'warn' : 'stale'
  return hours < 26 ? 'ok' : hours < 50 ? 'warn' : 'stale'
}

function StatusBadge({ status }: { status: ReturnType<typeof staleness> }) {
  const cfg = {
    ok:    { icon: CheckCircle,    cls: 'text-emerald-600 bg-emerald-50 border-emerald-200',  label: 'OK' },
    warn:  { icon: AlertTriangle,  cls: 'text-amber-600  bg-amber-50  border-amber-200',      label: 'Stale' },
    stale: { icon: XCircle,        cls: 'text-red-600    bg-red-50    border-red-200',         label: 'Overdue' },
    never: { icon: Clock,          cls: 'text-slate-500  bg-slate-50  border-slate-200',       label: 'Never run' },
  }[status]
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-semibold ${cfg.cls}`}>
      <Icon className="w-3 h-3" />{cfg.label}
    </span>
  )
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-AU', { dateStyle: 'short', timeStyle: 'short' })
}

function fmtAge(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3600000)
  const m = Math.floor((diff % 3600000) / 60000)
  if (h >= 48) return `${Math.floor(h / 24)}d ago`
  if (h >= 1)  return `${h}h ${m}m ago`
  return `${m}m ago`
}

const TYPE_COLORS: Record<string, string> = {
  apscheduler: 'bg-blue-100 text-blue-700',
  cron:        'bg-purple-100 text-purple-700',
  interval:    'bg-slate-100 text-slate-600',
}

// ── Run sequence reference (order pipelines should run each day) ──────────────
const RUN_ORDER: Record<string, number> = {
  eod_price_download:  1,
  daily_metrics:       2,
  universe_build:      3,
  index_prices:        4,
  fund_prices:         5,
  global_markets:      6,
  commodities:         7,
  asx_index_flags:     8,
  short_positions:     9,
  market_snapshot:     10,
  anomaly_detection:   11,
  asx_announcements:   12,
  price_alerts:        13,
  weekly_fundamentals: 14,
}

export default function PipelinePage() {
  const [jobs, setJobs]             = useState<JobStatus[]>([])
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [running, setRunning]       = useState<Record<string, 'running' | 'done' | 'error'>>({})
  const [toast, setToast]           = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)

  const load = async () => {
    setLoading(true); setError(null)
    try {
      const { data } = await api.get('/api/v1/admin/pipeline-status')
      setJobs(data.jobs)
      setLastRefresh(new Date())
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load pipeline status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // Auto-dismiss toast after 4s
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(t)
  }, [toast])

  const triggerJob = async (jobId: string, jobName: string) => {
    setRunning(prev => ({ ...prev, [jobId]: 'running' }))
    try {
      await api.post(`/api/v1/admin/run-job/${jobId}`)
      setRunning(prev => ({ ...prev, [jobId]: 'done' }))
      setToast({ msg: `${jobName} started — refresh in ~30s to see updated status`, type: 'ok' })
      // Auto-refresh after 35s
      setTimeout(() => load(), 35000)
    } catch (e: any) {
      setRunning(prev => ({ ...prev, [jobId]: 'error' }))
      setToast({ msg: e?.response?.data?.detail || `Failed to start ${jobName}`, type: 'err' })
    }
    // Reset button state after 8s
    setTimeout(() => setRunning(prev => { const n = { ...prev }; delete n[jobId]; return n }), 8000)
  }

  const ok    = jobs.filter(j => staleness(j.last_run, j.type) === 'ok').length
  const warn  = jobs.filter(j => staleness(j.last_run, j.type) === 'warn').length
  const stale = jobs.filter(j => staleness(j.last_run, j.type) === 'stale').length
  const never = jobs.filter(j => staleness(j.last_run, j.type) === 'never').length

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">

      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2 transition-all
          ${toast.type === 'ok' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'}`}>
          {toast.type === 'ok' ? <CheckCircle className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Activity className="w-6 h-6 text-blue-600" />
            Pipeline Monitor
          </h1>
          {lastRefresh && (
            <p className="text-xs text-slate-400 mt-0.5">
              Last refreshed: {lastRefresh.toLocaleTimeString('en-AU')}
            </p>
          )}
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Summary cards */}
      {!loading && jobs.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Healthy',   count: ok,    cls: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
            { label: 'Stale',     count: warn,  cls: 'border-amber-200  bg-amber-50  text-amber-700'  },
            { label: 'Overdue',   count: stale, cls: 'border-red-200    bg-red-50    text-red-700'    },
            { label: 'Never run', count: never, cls: 'border-slate-200  bg-slate-50  text-slate-600' },
          ].map(s => (
            <div key={s.label} className={`rounded-xl border p-4 text-center ${s.cls}`}>
              <div className="text-3xl font-bold">{s.count}</div>
              <div className="text-xs font-medium mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Run sequence guide */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
        <p className="text-xs font-semibold text-blue-700 mb-1.5 uppercase tracking-wide">Daily Run Sequence</p>
        <p className="text-xs text-blue-600 leading-relaxed">
          <strong>1.</strong> EOD Price Download &nbsp;→&nbsp;
          <strong>2.</strong> Daily Metrics Compute &nbsp;→&nbsp;
          <strong>3.</strong> Universe Build &nbsp;→&nbsp;
          <strong>4.</strong> Index Prices &nbsp;→&nbsp;
          <strong>5.</strong> Fund Prices &nbsp;→&nbsp;
          <strong>6.</strong> Global Markets &nbsp;→&nbsp;
          <strong>7.</strong> Commodities &nbsp;→&nbsp;
          <strong>8.</strong> ASX Index Flags &nbsp;→&nbsp;
          <strong>9.</strong> Short Positions &nbsp;→&nbsp;
          <strong>10.</strong> Market Snapshot &nbsp;→&nbsp;
          <strong>11.</strong> Anomaly Detection &nbsp;→&nbsp;
          <strong>12.</strong> Announcements &nbsp;→&nbsp;
          <strong>13.</strong> Price Alerts
          <br />
          <span className="text-blue-500">Steps 1–3 and Weekly Fundamentals are heavy cron jobs — run via server CLI:&nbsp;
            <code className="bg-blue-100 px-1 rounded">python scripts/eodhd/v2/jobs/daily_pipeline.py</code>
          </span>
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Job table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500 bg-slate-50 border-b border-slate-100">
              <th className="py-3 px-4 text-left font-semibold w-6">#</th>
              <th className="py-3 px-4 text-left font-semibold">Job</th>
              <th className="py-3 px-4 text-left font-semibold hidden md:table-cell">Schedule</th>
              <th className="py-3 px-4 text-left font-semibold hidden lg:table-cell">Type</th>
              <th className="py-3 px-4 text-right font-semibold">Last Run</th>
              <th className="py-3 px-4 text-right font-semibold hidden sm:table-cell">Age</th>
              <th className="py-3 px-4 text-right font-semibold hidden md:table-cell">Rows</th>
              <th className="py-3 px-4 text-center font-semibold">Status</th>
              <th className="py-3 px-4 text-center font-semibold">Run</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-t border-slate-100">
                  {Array.from({ length: 9 }).map((_, j) => (
                    <td key={j} className="py-3 px-4">
                      <div className="h-4 bg-slate-100 rounded animate-pulse w-3/4" />
                    </td>
                  ))}
                </tr>
              ))
            ) : jobs.map(j => {
              const status    = staleness(j.last_run, j.type)
              const rowCls    = status === 'stale' ? 'bg-red-50/40' : status === 'warn' ? 'bg-amber-50/30' : ''
              const runState  = running[j.job_id]
              const isHeavy   = HEAVY_JOBS.has(j.job_id)
              const seqNum    = RUN_ORDER[j.job_id]

              return (
                <tr key={j.job} className={`border-t border-slate-100 hover:bg-slate-50 transition-colors ${rowCls}`}>
                  {/* Sequence number */}
                  <td className="py-3 px-4 text-xs text-slate-400 font-mono">
                    {seqNum ? `${seqNum}` : '—'}
                  </td>
                  <td className="py-3 px-4">
                    <div className="font-semibold text-slate-800">{j.job}</div>
                    <div className="text-xs text-slate-400 truncate max-w-[200px] hidden sm:block">{j.description}</div>
                  </td>
                  <td className="py-3 px-4 text-slate-500 hidden md:table-cell text-xs">{j.schedule}</td>
                  <td className="py-3 px-4 hidden lg:table-cell">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[j.type]}`}>
                      {j.type}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right text-xs text-slate-600 whitespace-nowrap">{fmtDate(j.last_run)}</td>
                  <td className="py-3 px-4 text-right text-xs text-slate-500 hidden sm:table-cell whitespace-nowrap">{fmtAge(j.last_run)}</td>
                  <td className="py-3 px-4 text-right text-xs text-slate-600 hidden md:table-cell">
                    {j.row_count != null ? j.row_count.toLocaleString() : '—'}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <StatusBadge status={status} />
                  </td>
                  {/* Run Now button */}
                  <td className="py-3 px-4 text-center">
                    {isHeavy ? (
                      <span className="text-xs text-slate-300 italic">CLI only</span>
                    ) : (
                      <button
                        onClick={() => triggerJob(j.job_id, j.job)}
                        disabled={!!runState}
                        title={runState === 'running' ? 'Running…' : `Run ${j.job} now`}
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all
                          ${runState === 'running' ? 'bg-blue-100 text-blue-500 cursor-not-allowed' :
                            runState === 'done'    ? 'bg-emerald-100 text-emerald-600 cursor-default' :
                            runState === 'error'   ? 'bg-red-100 text-red-600 cursor-default' :
                            'bg-slate-100 text-slate-600 hover:bg-blue-100 hover:text-blue-700 cursor-pointer'
                          }`}
                      >
                        {runState === 'running' ? (
                          <><Loader2 className="w-3 h-3 animate-spin" /> Running</>
                        ) : runState === 'done' ? (
                          <><CheckCircle className="w-3 h-3" /> Started</>
                        ) : runState === 'error' ? (
                          <><XCircle className="w-3 h-3" /> Failed</>
                        ) : (
                          <><Play className="w-3 h-3" /> Run</>
                        )}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {!loading && jobs.length === 0 && !error && (
          <div className="py-12 text-center text-slate-400 text-sm">No job data available</div>
        )}
      </div>

      {/* Legend */}
      <div className="bg-slate-50 rounded-xl border border-slate-200 p-4">
        <p className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">Status Legend</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-slate-600">
          <div className="flex items-center gap-1.5"><CheckCircle className="w-3.5 h-3.5 text-emerald-600" /> <span><strong>OK</strong> — ran within expected window</span></div>
          <div className="flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> <span><strong>Stale</strong> — missed 1 run cycle</span></div>
          <div className="flex items-center gap-1.5"><XCircle className="w-3.5 h-3.5 text-red-600" /> <span><strong>Overdue</strong> — missed 2+ cycles, investigate</span></div>
          <div className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-slate-500" /> <span><strong>Never run</strong> — not yet executed</span></div>
        </div>
      </div>

    </div>
  )
}
