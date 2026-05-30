'use client'
import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import {
  RefreshCw, CheckCircle, AlertTriangle, Clock, XCircle,
  Activity, Play, Loader2, ChevronDown, ChevronRight,
  Calendar, BarChart2, Zap, AlertCircle, SkipForward,
} from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

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

interface PipelineRun {
  id: number
  run_date: string
  pipeline_name: string
  started_at: string | null
  completed_at: string | null
  status: 'running' | 'success' | 'failed' | 'partial'
  total_steps: number
  steps_completed: number
  failed_step: number | null
  failed_step_name: string | null
  error_message: string | null
  duration_seconds: number | null
  duration_fmt: string | null
}

interface PipelineStep {
  step_number: number
  step_name: string
  started_at: string | null
  completed_at: string | null
  status: 'running' | 'success' | 'failed' | 'skipped'
  duration_seconds: number | null
  duration_fmt: string | null
  error_message: string | null
}

interface SchedulerRun {
  id: number
  run_date: string
  job_id: string
  job_name: string
  started_at: string | null
  completed_at: string | null
  status: 'running' | 'success' | 'failed' | 'skipped'
  duration_seconds: number | null
  duration_fmt: string | null
  skip_reason: string | null
  error_message: string | null
}

interface SchedulerSummary {
  job_id: string
  job_name: string
  success_count: number
  failed_count: number
  skipped_count: number
  last_success: string | null
  avg_duration: number | null
}

// ── Constants ─────────────────────────────────────────────────────────────────

const HEAVY_JOBS = new Set(['universe_build', 'weekly_fundamentals', 'eod_price_download', 'daily_metrics'])

const RUN_ORDER: Record<string, number> = {
  eod_price_download: 1, daily_metrics: 2, universe_build: 3,
  index_prices: 4, fund_prices: 5, global_markets: 6, commodities: 7,
  asx_index_flags: 8, short_positions: 9, market_snapshot: 10,
  anomaly_detection: 11, asx_announcements: 12, price_alerts: 13,
  weekly_fundamentals: 14, price_predictions: 15,
}

const TYPE_COLORS: Record<string, string> = {
  apscheduler: 'bg-blue-100 text-blue-700',
  cron:        'bg-purple-100 text-purple-700',
  interval:    'bg-slate-100 text-slate-600',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function staleness(lastRun: string | null, scheduleType: string): 'ok' | 'warn' | 'stale' | 'never' {
  if (!lastRun) return 'never'
  const diff = Date.now() - new Date(lastRun).getTime()
  const hours = diff / 3600000
  if (scheduleType === 'interval') return hours < 1 ? 'ok' : hours < 4 ? 'warn' : 'stale'
  return hours < 26 ? 'ok' : hours < 50 ? 'warn' : 'stale'
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-AU', { dateStyle: 'short', timeStyle: 'short' })
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

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ReturnType<typeof staleness> }) {
  const cfg = {
    ok:    { icon: CheckCircle,   cls: 'text-emerald-600 bg-emerald-50 border-emerald-200', label: 'OK' },
    warn:  { icon: AlertTriangle, cls: 'text-amber-600 bg-amber-50 border-amber-200',       label: 'Stale' },
    stale: { icon: XCircle,       cls: 'text-red-600 bg-red-50 border-red-200',             label: 'Overdue' },
    never: { icon: Clock,         cls: 'text-slate-500 bg-slate-50 border-slate-200',       label: 'Never run' },
  }[status]
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-semibold ${cfg.cls}`}>
      <Icon className="w-3 h-3" />{cfg.label}
    </span>
  )
}

function RunStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { cls: string; icon: any; label: string }> = {
    success: { cls: 'text-emerald-700 bg-emerald-50 border-emerald-200', icon: CheckCircle,   label: 'Success' },
    failed:  { cls: 'text-red-700 bg-red-50 border-red-200',             icon: XCircle,       label: 'Failed'  },
    running: { cls: 'text-blue-700 bg-blue-50 border-blue-200',          icon: Loader2,       label: 'Running' },
    skipped: { cls: 'text-slate-600 bg-slate-50 border-slate-200',       icon: SkipForward,   label: 'Skipped' },
    partial: { cls: 'text-amber-700 bg-amber-50 border-amber-200',       icon: AlertTriangle, label: 'Partial' },
  }
  const c = cfg[status] || cfg.running
  const Icon = c.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-semibold ${c.cls}`}>
      <Icon className={`w-3 h-3 ${status === 'running' ? 'animate-spin' : ''}`} />{c.label}
    </span>
  )
}

function StepRow({ step }: { step: PipelineStep }) {
  const cls = {
    success: 'border-emerald-200 bg-emerald-50',
    failed:  'border-red-200 bg-red-50',
    running: 'border-blue-200 bg-blue-50',
    skipped: 'border-slate-200 bg-slate-50',
  }[step.status] || 'border-slate-200 bg-slate-50'

  return (
    <div className={`flex items-start gap-3 px-4 py-2.5 border-l-2 ${cls} rounded-r-lg`}>
      <span className="text-xs font-mono text-slate-400 w-5 shrink-0 mt-0.5">{step.step_number}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-800 truncate">{step.step_name}</span>
          <RunStatusBadge status={step.status} />
          {step.duration_fmt && (
            <span className="text-xs text-slate-400">{step.duration_fmt}</span>
          )}
        </div>
        {step.error_message && (
          <p className="text-xs text-red-600 mt-1 font-mono break-all">{step.error_message}</p>
        )}
      </div>
      <span className="text-xs text-slate-400 shrink-0 hidden sm:block">
        {step.started_at ? new Date(step.started_at).toLocaleTimeString('en-AU') : '—'}
      </span>
    </div>
  )
}

function PipelineRunRow({
  run,
  expanded,
  onToggle,
}: {
  run: PipelineRun
  expanded: boolean
  onToggle: () => void
}) {
  const [steps, setSteps] = useState<PipelineStep[]>([])
  const [loadingSteps, setLoadingSteps] = useState(false)

  const loadSteps = useCallback(async () => {
    if (steps.length > 0) return
    setLoadingSteps(true)
    try {
      const { data } = await api.get(`/api/v1/admin/pipeline/runs/${run.run_date}`)
      setSteps(data.steps || [])
    } catch {}
    finally { setLoadingSteps(false) }
  }, [run.run_date, steps.length])

  const handleToggle = () => {
    onToggle()
    if (!expanded) loadSteps()
  }

  const pct = run.total_steps > 0 ? Math.round((run.steps_completed / run.total_steps) * 100) : 0

  return (
    <>
      <tr
        className={`border-t border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors
          ${run.status === 'failed' ? 'bg-red-50/30' : ''}`}
        onClick={handleToggle}
      >
        <td className="py-3 px-4">
          {expanded
            ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
        </td>
        <td className="py-3 px-4 font-semibold text-slate-800 text-sm">
          {run.run_date}
        </td>
        <td className="py-3 px-4">
          <RunStatusBadge status={run.status} />
        </td>
        <td className="py-3 px-4 hidden md:table-cell">
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-slate-100 rounded-full h-1.5 w-20">
              <div
                className={`h-1.5 rounded-full ${
                  run.status === 'success' ? 'bg-emerald-500' :
                  run.status === 'failed'  ? 'bg-red-500' : 'bg-blue-500'
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs text-slate-500 whitespace-nowrap">
              {run.steps_completed}/{run.total_steps}
            </span>
          </div>
        </td>
        <td className="py-3 px-4 text-xs text-slate-600 hidden sm:table-cell">
          {fmtDate(run.started_at)}
        </td>
        <td className="py-3 px-4 text-xs text-slate-600 hidden lg:table-cell">
          {run.duration_fmt || '—'}
        </td>
        <td className="py-3 px-4 text-xs text-red-600 hidden md:table-cell max-w-[200px] truncate">
          {run.failed_step_name || ''}
        </td>
      </tr>

      {expanded && (
        <tr className="border-t border-slate-100">
          <td colSpan={7} className="px-6 py-3 bg-slate-50">
            {loadingSteps ? (
              <div className="flex items-center gap-2 text-sm text-slate-400 py-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading steps…
              </div>
            ) : steps.length === 0 ? (
              <p className="text-sm text-slate-400 py-2">No step data recorded for this run.</p>
            ) : (
              <div className="space-y-1.5 py-1">
                {steps.map(s => <StepRow key={s.step_number} step={s} />)}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type Tab = 'status' | 'history' | 'scheduler'

export default function PipelinePage() {
  const [tab, setTab]               = useState<Tab>('status')

  // Status tab
  const [jobs, setJobs]             = useState<JobStatus[]>([])
  const [jobsLoading, setJobsLoading] = useState(true)
  const [jobsError, setJobsError]   = useState<string | null>(null)
  const [running, setRunning]       = useState<Record<string, 'running' | 'done' | 'error'>>({})
  const [toast, setToast]           = useState<{ msg: string; type: 'ok' | 'err' } | null>(null)

  // History tab
  const [runs, setRuns]             = useState<PipelineRun[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [expandedRun, setExpandedRun] = useState<number | null>(null)

  // Scheduler tab
  const [schedRuns, setSchedRuns]   = useState<SchedulerRun[]>([])
  const [schedSummary, setSchedSummary] = useState<SchedulerSummary[]>([])
  const [schedLoading, setSchedLoading] = useState(false)
  const [schedJobFilter, setSchedJobFilter] = useState('')

  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  // ── Load functions ──────────────────────────────────────────────────────────

  const loadJobs = useCallback(async () => {
    setJobsLoading(true); setJobsError(null)
    try {
      const { data } = await api.get('/api/v1/admin/pipeline-status')
      setJobs(data.jobs)
      setLastRefresh(new Date())
    } catch (e: any) {
      setJobsError(e?.response?.data?.detail || 'Failed to load pipeline status')
    } finally { setJobsLoading(false) }
  }, [])

  const loadRuns = useCallback(async () => {
    setRunsLoading(true)
    try {
      const { data } = await api.get('/api/v1/admin/pipeline/runs?days=30')
      setRuns(data.runs || [])
      setLastRefresh(new Date())
    } catch {}
    finally { setRunsLoading(false) }
  }, [])

  const loadScheduler = useCallback(async (jobIdFilter = '') => {
    setSchedLoading(true)
    try {
      const qs = jobIdFilter ? `?days=14&job_id=${encodeURIComponent(jobIdFilter)}` : '?days=14'
      const { data } = await api.get(`/api/v1/admin/pipeline/scheduler${qs}`)
      setSchedRuns(data.runs || [])
      setSchedSummary(data.summary || [])
      setLastRefresh(new Date())
    } catch {}
    finally { setSchedLoading(false) }
  }, [])

  // Load on tab switch
  useEffect(() => {
    if (tab === 'status')    loadJobs()
    if (tab === 'history')   loadRuns()
    if (tab === 'scheduler') loadScheduler(schedJobFilter)
  }, [tab])

  // Initial load
  useEffect(() => { loadJobs() }, [])

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(t)
  }, [toast])

  // ── Job trigger ─────────────────────────────────────────────────────────────

  const triggerJob = async (jobId: string, jobName: string) => {
    setRunning(prev => ({ ...prev, [jobId]: 'running' }))
    try {
      await api.post(`/api/v1/admin/run-job/${jobId}`)
      setRunning(prev => ({ ...prev, [jobId]: 'done' }))
      setToast({ msg: `${jobName} started — refresh in ~30s`, type: 'ok' })
      setTimeout(() => loadJobs(), 35000)
    } catch (e: any) {
      setRunning(prev => ({ ...prev, [jobId]: 'error' }))
      setToast({ msg: e?.response?.data?.detail || `Failed to start ${jobName}`, type: 'err' })
    }
    setTimeout(() => setRunning(prev => { const n = { ...prev }; delete n[jobId]; return n }), 8000)
  }

  // ── Derived counts ──────────────────────────────────────────────────────────

  const ok    = jobs.filter(j => staleness(j.last_run, j.type) === 'ok').length
  const warn  = jobs.filter(j => staleness(j.last_run, j.type) === 'warn').length
  const stale = jobs.filter(j => staleness(j.last_run, j.type) === 'stale').length
  const never = jobs.filter(j => staleness(j.last_run, j.type) === 'never').length

  const successRuns = runs.filter(r => r.status === 'success').length
  const failedRuns  = runs.filter(r => r.status === 'failed').length

  // ── Refresh handler ─────────────────────────────────────────────────────────

  const handleRefresh = () => {
    if (tab === 'status')    loadJobs()
    if (tab === 'history')   loadRuns()
    if (tab === 'scheduler') loadScheduler(schedJobFilter)
  }

  const isLoading = tab === 'status' ? jobsLoading : tab === 'history' ? runsLoading : schedLoading

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">

      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2
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
        <button onClick={handleRefresh} disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50">
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {([
          { id: 'status',    label: 'Job Status',      icon: Zap },
          { id: 'history',   label: 'Run History',     icon: Calendar },
          { id: 'scheduler', label: 'Scheduler Jobs',  icon: BarChart2 },
        ] as const).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px
              ${tab === id
                ? 'border-blue-600 text-blue-700'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}
          >
            <Icon className="w-3.5 h-3.5" />{label}
          </button>
        ))}
      </div>

      {/* ── Tab: Job Status ─────────────────────────────────────────────────── */}
      {tab === 'status' && (
        <>
          {/* Summary cards */}
          {!jobsLoading && jobs.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Healthy',   count: ok,    cls: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
                { label: 'Stale',     count: warn,  cls: 'border-amber-200 bg-amber-50 text-amber-700'   },
                { label: 'Overdue',   count: stale, cls: 'border-red-200 bg-red-50 text-red-700'         },
                { label: 'Never run', count: never, cls: 'border-slate-200 bg-slate-50 text-slate-600'   },
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
              <strong>1.</strong> EOD Prices &nbsp;→&nbsp;
              <strong>2.</strong> ASIC Short &nbsp;→&nbsp;
              <strong>3.</strong> Staging Load &nbsp;→&nbsp;
              <strong>4-6.</strong> Transforms &nbsp;→&nbsp;
              <strong>7-10.</strong> Compute Engines &nbsp;→&nbsp;
              <strong>11-12.</strong> Index/Fund Prices &nbsp;→&nbsp;
              <strong>13.</strong> Universe Build &nbsp;→&nbsp;
              <strong>14.</strong> Market Snapshot
              <br />
              <span className="text-blue-500">APScheduler safety-net jobs fire at 7:50pm (snapshot), 8:05pm (short), 8:20pm (anomaly), 8:35pm (alerts) — after pipeline finishes ~7:30pm.</span>
            </p>
          </div>

          {jobsError && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{jobsError}</div>
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
                {jobsLoading
                  ? Array.from({ length: 8 }).map((_, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        {Array.from({ length: 9 }).map((_, j) => (
                          <td key={j} className="py-3 px-4">
                            <div className="h-4 bg-slate-100 rounded animate-pulse w-3/4" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : jobs.map(j => {
                      const status   = staleness(j.last_run, j.type)
                      const rowCls   = status === 'stale' ? 'bg-red-50/40' : status === 'warn' ? 'bg-amber-50/30' : ''
                      const runState = running[j.job_id]
                      const isHeavy  = HEAVY_JOBS.has(j.job_id)
                      return (
                        <tr key={j.job} className={`border-t border-slate-100 hover:bg-slate-50 transition-colors ${rowCls}`}>
                          <td className="py-3 px-4 text-xs text-slate-400 font-mono">
                            {RUN_ORDER[j.job_id] || '—'}
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
                          <td className="py-3 px-4 text-center"><StatusBadge status={status} /></td>
                          <td className="py-3 px-4 text-center">
                            {isHeavy ? (
                              <span className="text-xs text-slate-300 italic">CLI only</span>
                            ) : (
                              <button
                                onClick={() => triggerJob(j.job_id, j.job)}
                                disabled={!!runState}
                                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all
                                  ${runState === 'running' ? 'bg-blue-100 text-blue-500 cursor-not-allowed' :
                                    runState === 'done'    ? 'bg-emerald-100 text-emerald-600 cursor-default' :
                                    runState === 'error'   ? 'bg-red-100 text-red-600 cursor-default' :
                                    'bg-slate-100 text-slate-600 hover:bg-blue-100 hover:text-blue-700'}`}
                              >
                                {runState === 'running' ? <><Loader2 className="w-3 h-3 animate-spin" /> Running</> :
                                 runState === 'done'    ? <><CheckCircle className="w-3 h-3" /> Started</> :
                                 runState === 'error'   ? <><XCircle className="w-3 h-3" /> Failed</> :
                                                          <><Play className="w-3 h-3" /> Run</>}
                              </button>
                            )}
                          </td>
                        </tr>
                      )
                    })
                }
              </tbody>
            </table>
          </div>

          {/* Legend */}
          <div className="bg-slate-50 rounded-xl border border-slate-200 p-4">
            <p className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">Status Legend</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-slate-600">
              <div className="flex items-center gap-1.5"><CheckCircle className="w-3.5 h-3.5 text-emerald-600" /><span><strong>OK</strong> — ran within window</span></div>
              <div className="flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 text-amber-600" /><span><strong>Stale</strong> — missed 1 cycle</span></div>
              <div className="flex items-center gap-1.5"><XCircle className="w-3.5 h-3.5 text-red-600" /><span><strong>Overdue</strong> — missed 2+ cycles</span></div>
              <div className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-slate-500" /><span><strong>Never run</strong> — not yet executed</span></div>
            </div>
          </div>
        </>
      )}

      {/* ── Tab: Run History ─────────────────────────────────────────────────── */}
      {tab === 'history' && (
        <>
          {/* Summary */}
          {!runsLoading && runs.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Total Runs',  count: runs.length,  cls: 'border-slate-200 bg-slate-50 text-slate-700' },
                { label: 'Successful',  count: successRuns,  cls: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
                { label: 'Failed',      count: failedRuns,   cls: 'border-red-200 bg-red-50 text-red-700' },
                { label: 'Success Rate', count: runs.length ? `${Math.round(successRuns / runs.length * 100)}%` : '—',
                  cls: successRuns === runs.length ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700' },
              ].map(s => (
                <div key={s.label} className={`rounded-xl border p-4 text-center ${s.cls}`}>
                  <div className="text-3xl font-bold">{s.count}</div>
                  <div className="text-xs font-medium mt-0.5">{s.label}</div>
                </div>
              ))}
            </div>
          )}

          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
              <p className="text-xs text-slate-500">
                Click any row to expand step-by-step detail. Last 30 days shown.
              </p>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 bg-slate-50 border-b border-slate-100">
                  <th className="py-3 px-4 w-6" />
                  <th className="py-3 px-4 text-left font-semibold">Date</th>
                  <th className="py-3 px-4 text-left font-semibold">Status</th>
                  <th className="py-3 px-4 text-left font-semibold hidden md:table-cell">Steps</th>
                  <th className="py-3 px-4 text-left font-semibold hidden sm:table-cell">Started</th>
                  <th className="py-3 px-4 text-left font-semibold hidden lg:table-cell">Duration</th>
                  <th className="py-3 px-4 text-left font-semibold hidden md:table-cell">Failed Step</th>
                </tr>
              </thead>
              <tbody>
                {runsLoading
                  ? Array.from({ length: 5 }).map((_, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        {Array.from({ length: 7 }).map((_, j) => (
                          <td key={j} className="py-3 px-4">
                            <div className="h-4 bg-slate-100 rounded animate-pulse w-3/4" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : runs.length === 0
                  ? (
                      <tr>
                        <td colSpan={7} className="py-12 text-center text-slate-400 text-sm">
                          No pipeline run history yet. Run the daily pipeline to see data here.
                        </td>
                      </tr>
                    )
                  : runs.map(run => (
                      <PipelineRunRow
                        key={run.id}
                        run={run}
                        expanded={expandedRun === run.id}
                        onToggle={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
                      />
                    ))
                }
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Tab: Scheduler Jobs ─────────────────────────────────────────────── */}
      {tab === 'scheduler' && (
        <>
          {/* Summary cards per job */}
          {!schedLoading && schedSummary.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {schedSummary.map(s => (
                <button
                  key={s.job_id}
                  onClick={() => {
                    const next = schedJobFilter === s.job_id ? '' : s.job_id
                    setSchedJobFilter(next)
                    loadScheduler(next)
                  }}
                  className={`text-left rounded-xl border p-3.5 transition-colors
                    ${schedJobFilter === s.job_id
                      ? 'border-blue-300 bg-blue-50'
                      : 'border-slate-200 bg-white hover:bg-slate-50'}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold text-slate-800 truncate">{s.job_name}</span>
                    {s.failed_count > 0
                      ? <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />
                      : <CheckCircle className="w-3.5 h-3.5 text-emerald-500 shrink-0" />}
                  </div>
                  <div className="flex gap-3 text-xs">
                    <span className="text-emerald-600 font-medium">✓ {s.success_count}</span>
                    {s.failed_count  > 0 && <span className="text-red-600 font-medium">✗ {s.failed_count}</span>}
                    {s.skipped_count > 0 && <span className="text-slate-400">⤼ {s.skipped_count}</span>}
                    {s.avg_duration && <span className="text-slate-400 ml-auto">avg {s.avg_duration}s</span>}
                  </div>
                </button>
              ))}
            </div>
          )}

          {schedJobFilter && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Filtering by:</span>
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                {schedJobFilter}
              </span>
              <button onClick={() => { setSchedJobFilter(''); loadScheduler('') }}
                className="text-xs text-slate-400 hover:text-slate-700">✕ Clear</button>
            </div>
          )}

          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
              <p className="text-xs text-slate-500">
                Last 14 days of APScheduler job executions. Click a card above to filter by job.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 bg-slate-50 border-b border-slate-100">
                    <th className="py-3 px-4 text-left font-semibold">Job</th>
                    <th className="py-3 px-4 text-left font-semibold">Date</th>
                    <th className="py-3 px-4 text-left font-semibold">Status</th>
                    <th className="py-3 px-4 text-left font-semibold hidden sm:table-cell">Started</th>
                    <th className="py-3 px-4 text-left font-semibold hidden md:table-cell">Duration</th>
                    <th className="py-3 px-4 text-left font-semibold">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {schedLoading
                    ? Array.from({ length: 6 }).map((_, i) => (
                        <tr key={i} className="border-t border-slate-100">
                          {Array.from({ length: 6 }).map((_, j) => (
                            <td key={j} className="py-3 px-4">
                              <div className="h-4 bg-slate-100 rounded animate-pulse w-3/4" />
                            </td>
                          ))}
                        </tr>
                      ))
                    : schedRuns.length === 0
                    ? (
                        <tr>
                          <td colSpan={6} className="py-12 text-center text-slate-400 text-sm">
                            No scheduler job history yet. Workers will log here once they run.
                          </td>
                        </tr>
                      )
                    : schedRuns.map(r => (
                        <tr key={r.id}
                          className={`border-t border-slate-100 hover:bg-slate-50 transition-colors
                            ${r.status === 'failed'  ? 'bg-red-50/30' :
                              r.status === 'skipped' ? 'bg-slate-50/50' : ''}`}>
                          <td className="py-2.5 px-4 font-medium text-slate-800 text-xs">{r.job_name}</td>
                          <td className="py-2.5 px-4 text-xs text-slate-600">{r.run_date}</td>
                          <td className="py-2.5 px-4"><RunStatusBadge status={r.status} /></td>
                          <td className="py-2.5 px-4 text-xs text-slate-500 hidden sm:table-cell whitespace-nowrap">
                            {r.started_at ? new Date(r.started_at).toLocaleTimeString('en-AU') : '—'}
                          </td>
                          <td className="py-2.5 px-4 text-xs text-slate-500 hidden md:table-cell">
                            {r.duration_fmt || '—'}
                          </td>
                          <td className="py-2.5 px-4 text-xs max-w-[260px]">
                            {r.skip_reason && (
                              <span className="text-slate-400 italic truncate block">{r.skip_reason}</span>
                            )}
                            {r.error_message && (
                              <span className="text-red-600 font-mono truncate block">{r.error_message}</span>
                            )}
                          </td>
                        </tr>
                      ))
                  }
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
