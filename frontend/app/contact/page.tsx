'use client'
import { useState, FormEvent, useRef } from 'react'
import { BarChart2, Loader2, CheckCircle, Paperclip, X, AlertCircle } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const CATEGORIES = [
  { value: 'bug',            label: 'Bug Report' },
  { value: 'feature',        label: 'Feature Request' },
  { value: 'data',           label: 'Data Issue' },
  { value: 'billing',        label: 'Billing Issue' },
  { value: 'account',        label: 'Account Issue' },
  { value: 'general',        label: 'General Question' },
]

export default function ContactPage() {
  const { user } = useAuth()
  const fileRef  = useRef<HTMLInputElement>(null)

  const [name,        setName]        = useState(user?.name  ?? '')
  const [email,       setEmail]       = useState(user?.email ?? '')
  const [phone,       setPhone]       = useState('')
  const [category,    setCategory]    = useState('general')
  const [subject,     setSubject]     = useState('')
  const [description, setDescription] = useState('')
  const [files,       setFiles]       = useState<File[]>([])
  const [loading,     setLoading]     = useState(false)
  const [done,        setDone]        = useState(false)
  const [ticketNum,   setTicketNum]   = useState<number | null>(null)
  const [error,       setError]       = useState<string | null>(null)

  // Pre-fill from auth when user loads
  if (user && !name  && user.name)  setName(user.name)
  if (user && !email && user.email) setEmail(user.email)

  function addFiles(newFiles: FileList | null) {
    if (!newFiles) return
    const valid = Array.from(newFiles).filter(f => {
      const ext = f.name.split('.').pop()?.toLowerCase()
      return ['jpg','jpeg','png','gif','webp','pdf'].includes(ext ?? '') && f.size <= 5 * 1024 * 1024
    })
    setFiles(prev => [...prev, ...valid].slice(0, 5))
  }

  function removeFile(i: number) {
    setFiles(prev => prev.filter((_, idx) => idx !== i))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('name',        name)
      fd.append('email',       email)
      fd.append('phone',       phone)
      fd.append('category',    category)
      fd.append('subject',     subject)
      fd.append('description', description)
      files.forEach(f => fd.append('files', f))

      const res = await api.post('/api/v1/support/tickets', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setTicketNum(res.data.ticket.ticket_number)
      setDone(true)
    } catch {
      setError('Failed to submit. Please try again or email asxscreener@gmail.com directly.')
    } finally {
      setLoading(false)
    }
  }

  if (done) {
    return (
      <div className="min-h-[80vh] flex items-center justify-center px-4">
        <div className="w-full max-w-md text-center">
          <CheckCircle className="w-14 h-14 text-emerald-500 mx-auto mb-4" />
          <h1 className="text-xl font-bold text-gray-900 mb-2">Ticket submitted!</h1>
          <p className="text-gray-500 mb-1">
            Your support request has been logged as{' '}
            <span className="font-semibold text-gray-800">Ticket #{ticketNum}</span>.
          </p>
          <p className="text-gray-400 text-sm">
            We&apos;ll respond to <span className="font-medium">{email}</span> as soon as possible.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-center gap-2 mb-1">
            <BarChart2 className="w-5 h-5 text-blue-600" />
            <span className="text-sm text-blue-600 font-medium">ASX Screener</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Contact Support</h1>
          <p className="text-gray-500 text-sm mt-1">
            Report a bug, request a feature, or get help with your account.
            We aim to respond within 1 business day.
          </p>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
        <div className="bg-white rounded-xl border border-gray-200 p-6">

          {error && (
            <div className="mb-5 flex items-start gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">

            {/* Name + Email */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Full name <span className="text-red-500">*</span></label>
                <input
                  required
                  value={name}
                  onChange={e => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Your name"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email <span className="text-red-500">*</span></label>
                <input
                  required
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="you@example.com"
                />
              </div>
            </div>

            {/* Phone + Category */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Phone <span className="text-gray-400 font-normal">(optional)</span></label>
                <input
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="+61 4xx xxx xxx"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Category <span className="text-red-500">*</span></label>
                <select
                  value={category}
                  onChange={e => setCategory(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  {CATEGORIES.map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* User ID (if logged in) */}
            {user && (
              <div className="px-3 py-2 bg-blue-50 border border-blue-100 rounded-lg text-xs text-blue-700">
                Logged in as <span className="font-semibold">{user.email}</span>
                {' '}· User ID: <span className="font-mono">{user.id}</span>
              </div>
            )}

            {/* Subject */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Subject <span className="text-red-500">*</span></label>
              <input
                required
                value={subject}
                onChange={e => setSubject(e.target.value)}
                maxLength={300}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Brief description of your issue"
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Details <span className="text-red-500">*</span>
              </label>
              <textarea
                required
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={6}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
                placeholder="Please describe the issue in detail — include steps to reproduce, what you expected vs what happened, browser/device info, etc."
              />
            </div>

            {/* File attachments */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Screenshots / Attachments <span className="text-gray-400 font-normal">(optional, max 5 files, 5MB each)</span>
              </label>
              <div
                onClick={() => fileRef.current?.click()}
                className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/30 transition-colors"
              >
                <Paperclip className="w-5 h-5 text-gray-400 mx-auto mb-1" />
                <p className="text-sm text-gray-500">Click to attach files</p>
                <p className="text-xs text-gray-400 mt-0.5">PNG, JPG, GIF, WebP, PDF</p>
              </div>
              <input
                ref={fileRef}
                type="file"
                multiple
                accept=".jpg,.jpeg,.png,.gif,.webp,.pdf"
                className="hidden"
                onChange={e => addFiles(e.target.files)}
              />
              {files.length > 0 && (
                <div className="mt-2 space-y-1.5">
                  {files.map((f, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 bg-gray-50 rounded-lg border border-gray-200">
                      <span className="text-sm text-gray-700 truncate max-w-[80%]">{f.name}</span>
                      <button type="button" onClick={() => removeFile(i)} className="text-gray-400 hover:text-red-500 ml-2">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400
                         text-white text-sm font-semibold rounded-lg transition-colors
                         flex items-center justify-center gap-2"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? 'Submitting…' : 'Submit Support Request'}
            </button>

          </form>
        </div>

        <p className="mt-4 text-center text-xs text-gray-400">
          You can also email us directly at{' '}
          <a href="mailto:asxscreener@gmail.com" className="text-blue-500 hover:underline">
            asxscreener@gmail.com
          </a>
        </p>
      </div>
    </div>
  )
}
