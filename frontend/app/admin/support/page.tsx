'use client'
import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  BarChart2, RefreshCw, ChevronDown, ChevronUp, CheckCircle,
  Clock, AlertTriangle, XCircle, Paperclip, ExternalLink,
} from 'lucide-react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

interface Ticket {
  id:               string
  ticket_number:    number
  user_id:          string | null
  name:             string
  email:            string
  phone:            string | null
  category:         string
  subject:          string
  description:      string
  attachments:      string[]
  status:           string
  priority:         string
  resolution_notes: string | null
  resolved_by:      string | null
  created_at:       string
  updated_at:       string
  resolved_at:      string | null
}

const STATUS_COLORS: Record<string, string> = {
  open:        'bg-amber-100 text-amber-700',
  in_progress: 'bg-blue-100 text-blue-700',
  resolved:    'bg-emerald-100 text-emerald-700',
  closed:      'bg-gray-100 text-gray-600',
}

const STATUS_ICONS: Record<string, React.ElementType> = {
  open:        AlertTriangle,
  in_progress: Clock,
  resolved:    CheckCircle,
  closed:      XCircle,
}

const PRIORITY_COLORS: Record<string, string> = {
  low:    'text-gray-500',
  normal: 'text-blue-600',
  high:   'text-orange-600 font-bold',
  urgent: 'text-red-600 font-bold',
}

const STATUSES = ['all', 'open', 'in_progress', 'resolved', 'closed']
const CATEGORIES = ['all', 'bug', 'billing', 'data', 'data_incorrect', 'feature', 'account', 'broker', 'portfolio', 'general']

export default function AdminSupportPage() {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()

  const [tickets,        setTickets]        = useState<Ticket[]>([])
  const [total,          setTotal]          = useState(0)
  const [loading,        setLoading]        = useState(true)
  const [accessDenied,   setAccessDenied]   = useState(false)
  const [statusFilter,   setStatusFilter]   = useState('open')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [expanded,       setExpanded]       = useState<string | null>(null)
  const [saving,         setSaving]         = useState<string | null>(null)

  // Per-ticket edit state
  const [editStatus, setEditStatus] = useState<Record<string, string>>({})
  const [editNotes,  setEditNotes]  = useState<Record<string, string>>({})

  const loadTickets = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (statusFilter   !== 'all') params.status_filter = statusFilter
      if (categoryFilter !== 'all') params.category = categoryFilter
      const res = await api.get('/api/v1/support/tickets', { params })
      setTickets(res.data.tickets)
      setTotal(res.data.total)
    } catch (err: unknown) {
      if ((err as { response?: { status?: number } })?.response?.status === 403) {
        setAccessDenied(true)
      }
    } finally {
      setLoading(false)
    }
  }, [statusFilter, categoryFilter])

  useEffect(() => {
    if (!authLoading && !user) { router.push('/auth/login?next=/admin/support'); return }
    if (!authLoading) loadTickets()
  }, [authLoading, user, router, loadTickets])

  async function saveTicket(ticket: Ticket) {
    setSaving(ticket.id)
    try {
      const patch: Record<string, string> = {}
      if (editStatus[ticket.id]) patch.status = editStatus[ticket.id]
      if (editNotes[ticket.id] !== undefined) patch.resolution_notes = editNotes[ticket.id]
      await api.put(`/api/v1/support/tickets/${ticket.id}`, patch)
      await loadTickets()
      setExpanded(null)
    } catch { /* keep open */ }
    finally { setSaving(null) }
  }

  if (accessDenied) {
    return (
      <div className="min-h-[80vh] flex items-center justify-center">
        <div className="text-center">
          <XCircle className="w-10 h-10 text-red-500 mx-auto mb-3" />
          <p className="text-gray-700 font-medium">Admin access required</p>
          <Link href="/" className="text-sm text-blue-600 hover:underline mt-2 block">Go home</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-5 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <BarChart2 className="w-5 h-5 text-blue-600" />
            <div>
              <h1 className="text-lg font-bold text-gray-900">Support Tickets</h1>
              <p className="text-xs text-gray-400">{total} ticket{total !== 1 ? 's' : ''} · Admin view</p>
            </div>
          </div>
          <button onClick={loadTickets} className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>

        {/* Filters */}
        <div className="max-w-6xl mx-auto px-4 sm:px-6 pb-3 flex flex-wrap gap-2">
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
            {STATUSES.map(s => (
              <button key={s} onClick={() => setStatusFilter(s)}
                className={cn('px-2.5 py-1 text-xs font-semibold rounded-md capitalize transition-colors',
                  statusFilter === s ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                )}>
                {s === 'all' ? 'All' : s.replace('_', ' ')}
              </button>
            ))}
          </div>
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
            {CATEGORIES.map(c => (
              <button key={c} onClick={() => setCategoryFilter(c)}
                className={cn('px-2.5 py-1 text-xs font-semibold rounded-md capitalize transition-colors',
                  categoryFilter === c ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                )}>
                {c}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Ticket list */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-3">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : tickets.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-400 text-sm">
            No tickets found
          </div>
        ) : tickets.map(ticket => {
          const isOpen    = expanded === ticket.id
          const StatusIcon = STATUS_ICONS[ticket.status] ?? AlertTriangle
          return (
            <div key={ticket.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              {/* Row */}
              <div
                className="flex items-center gap-3 px-5 py-4 cursor-pointer hover:bg-gray-50"
                onClick={() => setExpanded(isOpen ? null : ticket.id)}
              >
                <StatusIcon className={cn('w-4 h-4 shrink-0', ticket.status === 'open' ? 'text-amber-500' : ticket.status === 'in_progress' ? 'text-blue-500' : ticket.status === 'resolved' ? 'text-emerald-500' : 'text-gray-400')} />
                <span className="text-xs text-gray-400 shrink-0">#{ticket.ticket_number}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate">{ticket.subject}</p>
                  <p className="text-xs text-gray-500 truncate">{ticket.name} · {ticket.email}{ticket.phone ? ` · ${ticket.phone}` : ''}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-bold uppercase', STATUS_COLORS[ticket.status] ?? 'bg-gray-100 text-gray-600')}>
                    {ticket.status.replace('_', ' ')}
                  </span>
                  <span className="text-[10px] capitalize text-gray-400">{ticket.category}</span>
                  <span className={cn('text-[10px] capitalize', PRIORITY_COLORS[ticket.priority])}>{ticket.priority}</span>
                  <span className="text-[10px] text-gray-400">{new Date(ticket.created_at).toLocaleDateString('en-AU')}</span>
                  {isOpen ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </div>
              </div>

              {/* Expanded detail */}
              {isOpen && (
                <div className="border-t border-gray-100 px-5 py-5 space-y-4">
                  {/* Info grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div><p className="text-gray-400 mb-0.5">User ID</p><p className="font-mono text-gray-600 truncate">{ticket.user_id ?? 'Anonymous'}</p></div>
                    <div><p className="text-gray-400 mb-0.5">Created</p><p className="text-gray-700">{new Date(ticket.created_at).toLocaleString('en-AU')}</p></div>
                    <div><p className="text-gray-400 mb-0.5">Updated</p><p className="text-gray-700">{new Date(ticket.updated_at).toLocaleString('en-AU')}</p></div>
                    {ticket.resolved_at && <div><p className="text-gray-400 mb-0.5">Resolved</p><p className="text-gray-700">{new Date(ticket.resolved_at).toLocaleString('en-AU')}</p></div>}
                  </div>

                  {/* Description */}
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Description</p>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-lg px-4 py-3">{ticket.description}</p>
                  </div>

                  {/* Attachments */}
                  {ticket.attachments.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Attachments</p>
                      <div className="flex flex-wrap gap-2">
                        {ticket.attachments.map((path, i) => (
                          <a key={i}
                            href={`/api/v1/support/uploads/${path}`}
                            target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100"
                          >
                            <Paperclip className="w-3.5 h-3.5" />
                            {path.split('/').pop()}
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Update form */}
                  <div className="bg-gray-50 rounded-xl p-4 space-y-3">
                    <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Update Ticket</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                        <select
                          value={editStatus[ticket.id] ?? ticket.status}
                          onChange={e => setEditStatus(prev => ({ ...prev, [ticket.id]: e.target.value }))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                          <option value="open">Open</option>
                          <option value="in_progress">In Progress</option>
                          <option value="resolved">Resolved</option>
                          <option value="closed">Closed</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Priority</label>
                        <select
                          value={editStatus[`${ticket.id}_priority`] ?? ticket.priority}
                          onChange={e => setEditStatus(prev => ({ ...prev, [`${ticket.id}_priority`]: e.target.value }))}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                          <option value="low">Low</option>
                          <option value="normal">Normal</option>
                          <option value="high">High</option>
                          <option value="urgent">Urgent</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-600 mb-1">Resolution notes</label>
                      <textarea
                        rows={3}
                        value={editNotes[ticket.id] ?? (ticket.resolution_notes ?? '')}
                        onChange={e => setEditNotes(prev => ({ ...prev, [ticket.id]: e.target.value }))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
                        placeholder="Add notes visible to the support team…"
                      />
                    </div>
                    <button
                      onClick={() => saveTicket(ticket)}
                      disabled={saving === ticket.id}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-semibold rounded-lg transition-colors flex items-center gap-2"
                    >
                      {saving === ticket.id && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                      Save changes
                    </button>
                  </div>

                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
