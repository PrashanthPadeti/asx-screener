'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import {
  RefreshCw, AlertCircle, CheckCircle, AlertTriangle, TrendingUp,
  HardDrive, Cpu, BarChart3, Zap, Clock, Target,
} from 'lucide-react'

interface SystemHealthData {
  timestamp: string
  metrics: {
    memory?: {
      total_gb: number
      used_gb: number
      available_gb: number
      percent_used: number
    }
    cpu?: {
      load_1min: number
      load_5min: number
      load_15min: number
      vcpu_count: number
      load_percent: number
    }
    disk?: {
      total_gb: number
      used_gb: number
      available_gb: number
      percent_used: number
    }
    database_size?: string
  }
  status: {
    memory?: 'green' | 'amber' | 'red'
    cpu?: 'green' | 'amber' | 'red'
    disk?: 'green' | 'amber' | 'red'
    overall: 'green' | 'amber' | 'red'
  }
  projections: {
    memory_growth_per_month_mb: number
    disk_growth_per_month_mb: number
    months_until_memory_upgrade?: number
    months_until_disk_upgrade?: number
    current_concurrent_users_estimate: number
    safe_concurrent_users_current: number
    safe_concurrent_users_after_8gb: number
    safe_concurrent_users_after_16gb: number
  }
  phases: Array<{
    phase: string
    config: string
    monthly_cost: string
    suitable_for: string
    duration: string
    features: string[]
  }>
  watch_list: Array<{
    metric: string
    alert_threshold: string
    action: string
  }>
  optimization_tips: string[]
}

export default function SystemHealthPage() {
  const [data, setData] = useState<SystemHealthData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<string>('')

  const fetchSystemHealth = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.get('/admin/system-health')
      setData(response.data)
      setLastRefresh(new Date().toLocaleTimeString())
    } catch (err) {
      setError('Failed to load system health data')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSystemHealth()
    const interval = setInterval(fetchSystemHealth, 60000) // Refresh every minute
    return () => clearInterval(interval)
  }, [])

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'green': return 'text-green-600'
      case 'amber': return 'text-amber-600'
      case 'red': return 'text-red-600'
      default: return 'text-gray-600'
    }
  }

  const getStatusBg = (status?: string) => {
    switch (status) {
      case 'green': return 'bg-green-50 border-green-200'
      case 'amber': return 'bg-amber-50 border-amber-200'
      case 'red': return 'bg-red-50 border-red-200'
      default: return 'bg-gray-50 border-gray-200'
    }
  }

  const getProgressColor = (percent: number) => {
    if (percent < 50) return 'bg-green-500'
    if (percent < 70) return 'bg-amber-500'
    return 'bg-red-500'
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">System Health & Capacity Planning</h1>
            <p className="text-sm text-gray-600 mt-1">
              Real-time droplet metrics, growth projections, and upgrade recommendations
            </p>
          </div>
          <button
            onClick={fetchSystemHealth}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-start gap-3">
            <AlertCircle size={20} className="text-red-600 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold text-red-900">Error</h3>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        {loading && !data ? (
          <div className="text-center py-12">
            <Zap className="animate-spin inline-block mb-2" size={32} />
            <p className="text-gray-600">Loading system health data...</p>
          </div>
        ) : data ? (
          <>
            {/* Overall Status & Last Updated */}
            <div className="mb-8">
              <div className={`border rounded-lg p-6 ${getStatusBg(data.status.overall)}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    {data.status.overall === 'green' && (
                      <CheckCircle size={32} className="text-green-600" />
                    )}
                    {data.status.overall === 'amber' && (
                      <AlertTriangle size={32} className="text-amber-600" />
                    )}
                    {data.status.overall === 'red' && (
                      <AlertCircle size={32} className="text-red-600" />
                    )}
                    <div>
                      <h2 className="text-xl font-bold capitalize">
                        Overall Status: {data.status.overall}
                      </h2>
                      <p className="text-sm text-gray-600 mt-1">
                        Last updated: {lastRefresh || 'Now'}
                      </p>
                    </div>
                  </div>
                  {data.status.overall === 'green' && (
                    <p className="text-sm font-semibold text-green-700">All systems healthy ✓</p>
                  )}
                  {data.status.overall === 'amber' && (
                    <p className="text-sm font-semibold text-amber-700">Monitor closely</p>
                  )}
                  {data.status.overall === 'red' && (
                    <p className="text-sm font-semibold text-red-700">Action required</p>
                  )}
                </div>
              </div>
            </div>

            {/* Current Metrics Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              {/* Memory */}
              {data.metrics.memory && (
                <div className={`border rounded-lg p-6 ${getStatusBg(data.status.memory)}`}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-gray-900">Memory Usage</h3>
                    <Zap size={20} className={getStatusColor(data.status.memory)} />
                  </div>
                  <div className="space-y-3">
                    <div>
                      <div className="flex justify-between mb-2">
                        <span className="text-sm text-gray-600">
                          {data.metrics.memory.used_gb.toFixed(1)} GB / {data.metrics.memory.total_gb.toFixed(1)} GB
                        </span>
                        <span className="font-semibold">{data.metrics.memory.percent_used}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${getProgressColor(data.metrics.memory.percent_used)}`}
                          style={{ width: `${data.metrics.memory.percent_used}%` }}
                        />
                      </div>
                    </div>
                    <div className="text-xs text-gray-600">
                      Available: {data.metrics.memory.available_gb.toFixed(1)} GB
                    </div>
                    <div className="pt-2 border-t border-gray-300">
                      <p className="text-xs font-semibold text-gray-700">
                        {data.status.memory === 'green' && '✓ Healthy headroom'}
                        {data.status.memory === 'amber' && '⚠ Monitor closely'}
                        {data.status.memory === 'red' && '🔴 Plan upgrade'}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* CPU */}
              {data.metrics.cpu && (
                <div className={`border rounded-lg p-6 ${getStatusBg(data.status.cpu)}`}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-gray-900">CPU Load</h3>
                    <Cpu size={20} className={getStatusColor(data.status.cpu)} />
                  </div>
                  <div className="space-y-3">
                    <div>
                      <div className="flex justify-between mb-2">
                        <span className="text-sm text-gray-600">1-min average</span>
                        <span className="font-semibold">{data.metrics.cpu.load_1min.toFixed(2)}</span>
                      </div>
                      <div className="text-xs text-gray-600">
                        {data.metrics.cpu.load_percent}% of {data.metrics.cpu.vcpu_count} vCPU
                      </div>
                    </div>
                    <div className="flex gap-2 text-xs text-gray-600">
                      <span>5-min: {data.metrics.cpu.load_5min.toFixed(2)}</span>
                      <span>15-min: {data.metrics.cpu.load_15min.toFixed(2)}</span>
                    </div>
                    <div className="pt-2 border-t border-gray-300">
                      <p className="text-xs font-semibold text-gray-700">
                        {data.status.cpu === 'green' && '✓ Very light load'}
                        {data.status.cpu === 'amber' && '⚠ Moderate load'}
                        {data.status.cpu === 'red' && '🔴 High load'}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Disk */}
              {data.metrics.disk && (
                <div className={`border rounded-lg p-6 ${getStatusBg(data.status.disk)}`}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-gray-900">Disk Space</h3>
                    <HardDrive size={20} className={getStatusColor(data.status.disk)} />
                  </div>
                  <div className="space-y-3">
                    <div>
                      <div className="flex justify-between mb-2">
                        <span className="text-sm text-gray-600">
                          {data.metrics.disk.used_gb.toFixed(0)} GB / {data.metrics.disk.total_gb.toFixed(0)} GB
                        </span>
                        <span className="font-semibold">{data.metrics.disk.percent_used}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${getProgressColor(data.metrics.disk.percent_used)}`}
                          style={{ width: `${data.metrics.disk.percent_used}%` }}
                        />
                      </div>
                    </div>
                    <div className="text-xs text-gray-600">
                      Available: {data.metrics.disk.available_gb.toFixed(0)} GB
                    </div>
                    <div className="pt-2 border-t border-gray-300">
                      <p className="text-xs font-semibold text-gray-700">
                        {data.status.disk === 'green' && '✓ Plenty of space'}
                        {data.status.disk === 'amber' && '⚠ Plan expansion'}
                        {data.status.disk === 'red' && '🔴 Expand now'}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Database Size & Concurrent Users */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
              {data.metrics.database_size && (
                <div className="border border-gray-200 rounded-lg p-6 bg-white">
                  <div className="flex items-center gap-2 mb-4">
                    <BarChart3 size={20} className="text-blue-600" />
                    <h3 className="font-semibold text-gray-900">Database</h3>
                  </div>
                  <div className="text-2xl font-bold text-gray-900 mb-2">
                    {data.metrics.database_size}
                  </div>
                  <p className="text-sm text-gray-600">Current size (includes indices & table structure)</p>
                </div>
              )}

              <div className="border border-gray-200 rounded-lg p-6 bg-white">
                <div className="flex items-center gap-2 mb-4">
                  <Target size={20} className="text-purple-600" />
                  <h3 className="font-semibold text-gray-900">Concurrent Users</h3>
                </div>
                <div>
                  <div className="text-lg font-semibold text-gray-900 mb-1">
                    {data.projections.current_concurrent_users_estimate} (estimated)
                  </div>
                  <p className="text-sm text-gray-600 mb-3">
                    Safe limit: <span className="font-semibold">{data.projections.safe_concurrent_users_current}</span> users
                  </p>
                  <div className="text-xs text-gray-700 space-y-1 bg-blue-50 p-2 rounded">
                    <p>• 8GB RAM: {data.projections.safe_concurrent_users_after_8gb} users</p>
                    <p>• 16GB RAM: {data.projections.safe_concurrent_users_after_16gb} users</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Growth Projections & Timeline */}
            <div className="border border-gray-200 rounded-lg p-6 bg-white mb-8">
              <div className="flex items-center gap-2 mb-6">
                <TrendingUp size={20} className="text-green-600" />
                <h2 className="text-xl font-bold text-gray-900">Growth Projections</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <p className="text-sm text-gray-600 mb-2">Memory Growth</p>
                  <p className="text-2xl font-bold text-gray-900">
                    ~{data.projections.memory_growth_per_month_mb}MB/month
                  </p>
                  <p className="text-xs text-gray-600 mt-2">
                    {data.projections.months_until_memory_upgrade
                      ? `Upgrade needed in ~${data.projections.months_until_memory_upgrade} months`
                      : 'At current growth rate'}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Disk Growth</p>
                  <p className="text-2xl font-bold text-gray-900">
                    ~{data.projections.disk_growth_per_month_mb}MB/month
                  </p>
                  <p className="text-xs text-gray-600 mt-2">
                    {data.projections.months_until_disk_upgrade
                      ? `Expansion needed in ~${data.projections.months_until_disk_upgrade} months`
                      : 'At current growth rate'}
                  </p>
                </div>
                <div className="bg-blue-50 rounded-lg p-4">
                  <p className="text-sm text-blue-900 font-semibold mb-2">⏰ Recommendation</p>
                  <p className="text-xs text-blue-800">
                    No immediate upgrade needed. Monitor monthly and plan Phase 2 upgrade for 6-12 months.
                  </p>
                </div>
              </div>
            </div>

            {/* Upgrade Phases */}
            <div className="mb-8">
              <h2 className="text-xl font-bold text-gray-900 mb-4">Upgrade Phases</h2>
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {data.phases.map((phase, idx) => (
                  <div
                    key={idx}
                    className={`border rounded-lg p-6 ${
                      idx === 0 ? 'bg-blue-50 border-blue-300 ring-2 ring-blue-500' : 'bg-white border-gray-200'
                    }`}
                  >
                    <div className="mb-4">
                      <h3 className="font-bold text-gray-900">{phase.phase}</h3>
                      <p className="text-sm text-gray-600 mt-1">{phase.duration}</p>
                    </div>
                    <div className="bg-gray-100 rounded p-3 mb-4">
                      <p className="text-sm font-mono text-gray-900">{phase.config}</p>
                      <p className="text-sm font-semibold text-gray-700 mt-2">{phase.monthly_cost}/month</p>
                    </div>
                    <div className="space-y-3 mb-4">
                      <div>
                        <p className="text-xs font-semibold text-gray-700 mb-1">Suitable for:</p>
                        <p className="text-sm text-gray-600">{phase.suitable_for}</p>
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-gray-700 mb-2">Features:</p>
                        <ul className="text-xs text-gray-600 space-y-1">
                          {phase.features.map((feat, i) => (
                            <li key={i}>• {feat}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                    {idx === 0 && (
                      <div className="bg-blue-200 text-blue-900 text-xs font-semibold px-2 py-1 rounded text-center">
                        Current
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Watch List */}
            <div className="border border-gray-200 rounded-lg p-6 bg-white mb-8">
              <div className="flex items-center gap-2 mb-6">
                <AlertTriangle size={20} className="text-amber-600" />
                <h2 className="text-xl font-bold text-gray-900">Monitoring Watch List</h2>
              </div>
              <div className="space-y-4">
                {data.watch_list.map((item, idx) => (
                  <div key={idx} className="border border-gray-200 rounded p-4">
                    <div className="flex justify-between items-start mb-2">
                      <p className="font-semibold text-gray-900">{item.metric}</p>
                      <span className="text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded">
                        Alert: {item.alert_threshold}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600">Action: {item.action}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Optimization Tips */}
            <div className="border border-gray-200 rounded-lg p-6 bg-white">
              <div className="flex items-center gap-2 mb-6">
                <Zap size={20} className="text-yellow-600" />
                <h2 className="text-xl font-bold text-gray-900">Optimization Tips (Before Upgrading)</h2>
              </div>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {data.optimization_tips.map((tip, idx) => (
                  <li key={idx} className="flex items-start gap-3">
                    <span className="text-lg">💡</span>
                    <span className="text-sm text-gray-700">{tip}</span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}
