'use client'
import { useState, useEffect, useRef, useCallback, FormEvent } from 'react'
import {
  BarChart2, Loader2, CheckCircle, Paperclip, X, AlertCircle,
  Mail, Lock, FileText, Info, Clock,
} from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { api } from '@/lib/api'

// ── Support categories ────────────────────────────────────────────────────────

const CATEGORIES = [
  { value: 'general',        label: 'General Question'            },
  { value: 'bug',            label: 'Bug / Technical Issue'       },
  { value: 'billing',        label: 'Billing / Subscription'      },
  { value: 'data',           label: 'Data Issue'                  },
  { value: 'data_incorrect', label: 'Data looks incorrect'        },
  { value: 'feature',        label: 'Feature Request'             },
  { value: 'account',        label: 'Account / Login Issue'       },
  { value: 'broker',         label: 'Broker / Affiliate Query'    },
  { value: 'portfolio',      label: 'Portfolio / Watchlist Issue' },
]

// ── File helpers ──────────────────────────────────────────────────────────────

const ALLOWED_EXTS  = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf']
const MAX_FILE_SIZE = 5 * 1024 * 1024   // 5 MB
const MAX_FILES     = 5

function fmtSize(bytes: number): string {
  if (bytes < 1024)        return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// ── Collect browser / device context ─────────────────────────────────────────

function getContext(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  return {
    url:       window.location.href,
    userAgent: navigator.userAgent,
    viewport:  `${window.innerWidth}×${window.innerHeight}`,
    timestamp: new Date().toISOString(),
  }
}

// ── Confirmation screen ───────────────────────────────────────────────────────

function ConfirmationScreen({ ticketNum, email, onReset }: {
  ticketNum: number
  email: string
  onReset: () => void
}) {
  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-md text-center">
        <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-5">
          <CheckCircle className="w-9 h-9 text-emerald-600" />
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Request submitted!</h1>
        <p className="text-sm text-slate-500 mb-5">
          Support request submitted successfully. We&apos;ll respond within 1 business day.
        </p>

        <div className="bg-slate-50 border border-slate-200 rounded-xl px-5 py-4 mb-5 text-left space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-500">Reference number</span>
            <span className="font-bold text-slate-900 font-mono">#{ticketNum}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-500">Reply will be sent to</span>
            <span className="font-medium text-slate-700 truncate max-w-[60%] text-right">{email}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-500">Expected response</span>
            <span className="font-medium text-slate-700">Within 1 business day</span>
          </div>
        </div>

        <p className="text-sm text-slate-500 mb-6">
          A confirmation email has been sent to <strong>{email}</strong> with your reference number.
          Keep it handy in case you need to follow up.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <button
            onClick={onReset}
            className="px-5 py-2.5 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-xl transition-colors"
          >
            Submit another request
          </button>
          <a
            href="/"
            className="px-5 py-2.5 text-sm font-medium bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 rounded-xl transition-colors"
          >
            Back to home
          </a>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ContactPage() {
  const { user }  = useAuth()
  const fileRef   = useRef<HTMLInputElement>(null)

  // Form state
  const [name,        setName]        = useState('')
  const [email,       setEmail]       = useState('')
  const [phone,       setPhone]       = useState('')
  const [category,    setCategory]    = useState('general')
  const [subject,     setSubject]     = useState('')
  const [description, setDescription] = useState('')
  const [files,       setFiles]       = useState<File[]>([])

  // UI state
  const [fileErrors, setFileErrors] = useState<string[]>([])
  const [loading,    setLoading]    = useState(false)
  const [done,       setDone]       = useState(false)
  const [ticketNum,  setTicketNum]  = useState<number | null>(null)
  const [error,      setError]      = useState<string | null>(null)

  // Pre-fill from auth on mount / auth change
  useEffect(() => {
    if (user) {
      if (user.name)  setName(user.name)
      if (user.email) setEmail(user.email)
    }
  }, [user])

  // ── Submit guard ────────────────────────────────────────────────────────────
  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const canSubmit  = (
    name.trim().length >= 2 &&
    emailValid &&
    subject.trim().length >= 3 &&
    description.trim().length >= 10 &&
    !loading
  )

  // ── File handling ───────────────────────────────────────────────────────────
  const addFiles = useCallback((newFiles: FileList | null) => {
    if (!newFiles) return
    const errs: string[]  = []
    const valid: File[]   = []

    Array.from(newFiles).forEach(f => {
      const ext = f.name.split('.').pop()?.toLowerCase() ?? ''
      if (!ALLOWED_EXTS.includes(ext)) {
        errs.push(`"${f.name}" — unsupported file type. Allowed: PNG, JPG, GIF, WebP, PDF.`)
      } else if (f.size > MAX_FILE_SIZE) {
        errs.push(`"${f.name}" — exceeds 5 MB limit (${fmtSize(f.size)}).`)
      } else {
        valid.push(f)
      }
    })

    setFiles(prev => {
      const combined = [...prev, ...valid]
      if (combined.length > MAX_FILES) {
        const overflow = combined.length - MAX_FILES
        errs.push(`Only ${MAX_FILES} files allowed. ${overflow} file${overflow > 1 ? 's' : ''} not added.`)
        return combined.slice(0, MAX_FILES)
      }
      return combined
    })

    setFileErrors(errs)
    if (fileRef.current) fileRef.current.value = ''
  }, [])

  function removeFile(i: number) {
    setFiles(prev => prev.filter((_, idx) => idx !== i))
    setFileErrors([])
  }

  // ── Submit ──────────────────────────────────────────────────────────────────
  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setError(null)
    setLoading(true)

    try {
      const ctx = getContext()
      const fd  = new FormData()

      fd.append('name',        name.trim())
      fd.append('email',       email.trim())
      fd.append('phone',       phone.trim())
      fd.append('category',    category)
      fd.append('subject',     subject.trim())
      fd.append('description', description.trim())

      // Context fields — sent to backend, never displayed to user
      fd.append('context_url',        ctx.url        ?? '')
      fd.append('context_user_agent', ctx.userAgent  ?? '')
      fd.append('context_viewport',   ctx.viewport   ?? '')
      fd.append('context_timestamp',  ctx.timestamp  ?? '')

      // Subscription tier for logged-in users
      if (user) {
        const u = user as unknown as Record<string, unknown>
        const tier = (u.subscription_tier ?? u.tier ?? u.plan ?? 'unknown') as string
        fd.append('subscription_tier', tier)
      }

      files.forEach(f => fd.append('files', f))

      const res = await api.post('/api/v1/support/tickets', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      setTicketNum(res.data.ticket.ticket_number)
      setDone(true)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Submission failed. Please try again or email us directly at asxscreener@gmail.com.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  function resetForm() {
    setName(user?.name  ?? '')
    setEmail(user?.email ?? '')
    setPhone('')
    setCategory('general')
    setSubject('')
    setDescription('')
    setFiles([])
    setFileErrors([])
    setError(null)
    setDone(false)
    setTicketNum(null)
  }

  // ── Confirmation ────────────────────────────────────────────────────────────
  if (done && ticketNum) {
    return <ConfirmationScreen ticketNum={ticketNum} email={email} onReset={resetForm} />
  }

  // ── Input class helpers ─────────────────────────────────────────────────────
  const field         = 'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
  const fieldDisabled = 'bg-slate-50 text-slate-500 cursor-not-allowed border-slate-200'

  return (
    <div className="min-h-screen bg-gray-50">

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-center gap-2 mb-1">
            <BarChart2 className="w-5 h-5 text-blue-600 shrink-0" />
            <span className="text-sm text-blue-600 font-medium">ASX Screener</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Contact Support</h1>
          <p className="text-gray-500 text-sm mt-1">
            Report a bug, request a feature, or get help with your account.
            We aim to respond within 1 business day.
          </p>
        </div>
      </div>

      {/* ── Form ─────────────────────────────────────────────────────────── */}
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 space-y-5">

        {/* Auth context banner */}
        {user ? (
          <div className="flex items-start gap-2.5 px-4 py-3 bg-blue-50 border border-blue-100 rounded-xl text-xs text-blue-800 leading-relaxed">
            <Lock className="w-3.5 h-3.5 shrink-0 mt-0.5 text-blue-500" />
            <span>
              Logged in as <strong>{user.email}</strong>.{' '}
              Your account details (subscription tier, account ID, and browser information) will be
              attached automatically to help support investigate faster.
            </span>
          </div>
        ) : (
          <div className="flex items-start gap-2.5 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 leading-relaxed">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-slate-400" />
            <span>Not logged in. Please enter your email so we can reply.</span>
          </div>
        )}

        <div className="bg-white rounded-xl border border-gray-200 p-5 sm:p-6">

          {/* Submission error */}
          {error && (
            <div className="mb-5 flex items-start gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5" noValidate>

            {/* ── Name + Email ───────────────────────────────────────────── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Full name <span className="text-red-500">*</span>
                </label>
                <input
                  required
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Your name"
                  className={field}
                  aria-required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Email address <span className="text-red-500">*</span>
                </label>
                {user ? (
                  <div className="relative">
                    <input
                      type="email"
                      value={email}
                      readOnly
                      className={`${field} ${fieldDisabled} pr-8`}
                      aria-label="Email address (from your account)"
                    />
                    <Lock className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 shrink-0" />
                  </div>
                ) : (
                  <input
                    required
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className={field}
                    aria-required
                  />
                )}
              </div>
            </div>

            {/* ── Phone + Category ───────────────────────────────────────── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Phone <span className="text-gray-400 font-normal text-xs">(optional)</span>
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  placeholder="+61 4xx xxx xxx"
                  className={field}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Category <span className="text-red-500">*</span>
                </label>
                <select
                  value={category}
                  onChange={e => setCategory(e.target.value)}
                  className={`${field} bg-white`}
                  aria-required
                >
                  {CATEGORIES.map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                {/* Bug hint: URL will be attached automatically */}
                {(category === 'bug' || category === 'data_incorrect' || category === 'data') && (
                  <p className="text-xs text-blue-600 mt-1.5 flex items-center gap-1">
                    <Info className="w-3 h-3 shrink-0" />
                    {category === 'bug'
                      ? 'Current page URL will be attached automatically to help us reproduce the issue.'
                      : 'Current page URL will be attached so we can check the right data.'}
                  </p>
                )}
              </div>
            </div>

            {/* ── Subject ────────────────────────────────────────────────── */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Subject <span className="text-red-500">*</span>
              </label>
              <input
                required
                value={subject}
                onChange={e => setSubject(e.target.value)}
                maxLength={300}
                placeholder="Brief description of your issue"
                className={field}
                aria-required
              />
              <p className="text-xs text-gray-400 mt-1 text-right">{subject.length}/300</p>
            </div>

            {/* ── Description ────────────────────────────────────────────── */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Details <span className="text-red-500">*</span>
              </label>
              <textarea
                required
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={6}
                placeholder="Please describe the issue in detail — include steps to reproduce, what you expected vs what happened, and any relevant context."
                className={`${field} resize-y`}
                aria-required
              />
              <p className="text-xs text-gray-400 mt-1">Minimum 10 characters · {description.trim().length} entered</p>
            </div>

            {/* ── File attachments ───────────────────────────────────────── */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Screenshots / Attachments{' '}
                <span className="text-gray-400 font-normal text-xs">
                  (optional · max {MAX_FILES} files · {fmtSize(MAX_FILE_SIZE)} each)
                </span>
              </label>

              <div
                role="button"
                tabIndex={0}
                onClick={() => files.length < MAX_FILES && fileRef.current?.click()}
                onKeyDown={e => e.key === 'Enter' && files.length < MAX_FILES && fileRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-5 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${
                  files.length >= MAX_FILES
                    ? 'border-slate-100 bg-slate-50 cursor-not-allowed'
                    : 'border-gray-200 hover:border-blue-300 hover:bg-blue-50/30 cursor-pointer'
                }`}
                aria-label="Click to attach files"
              >
                <Paperclip className="w-5 h-5 text-gray-400 mx-auto mb-1.5" />
                {files.length >= MAX_FILES ? (
                  <p className="text-sm text-slate-400">Maximum files reached ({MAX_FILES}/{MAX_FILES})</p>
                ) : (
                  <>
                    <p className="text-sm text-gray-500">Click to attach files</p>
                    <p className="text-xs text-gray-400 mt-0.5">PNG, JPG, JPEG, GIF, WebP, PDF</p>
                  </>
                )}
              </div>
              <input
                ref={fileRef}
                type="file"
                multiple
                accept=".jpg,.jpeg,.png,.gif,.webp,.pdf"
                className="hidden"
                onChange={e => addFiles(e.target.files)}
                disabled={files.length >= MAX_FILES}
              />

              {fileErrors.length > 0 && (
                <div className="mt-2 space-y-1">
                  {fileErrors.map((err, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                      {err}
                    </div>
                  ))}
                </div>
              )}

              {files.length > 0 && (
                <div className="mt-2 space-y-1.5">
                  {files.map((f, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 bg-gray-50 rounded-lg border border-gray-200 group">
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="text-sm text-gray-700 truncate">{f.name}</span>
                        <span className="text-xs text-gray-400 shrink-0">{fmtSize(f.size)}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeFile(i)}
                        className="text-gray-300 hover:text-red-500 transition-colors ml-2 shrink-0"
                        aria-label={`Remove ${f.name}`}
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  <p className="text-xs text-slate-400">{files.length}/{MAX_FILES} files attached</p>
                </div>
              )}
            </div>

            {/* ── Required fields hint ───────────────────────────────────── */}
            {!canSubmit && !loading && (name || email || subject || description) && (
              <p className="text-xs text-slate-400 text-center">
                {!name.trim() && 'Full name · '}
                {!emailValid && 'Valid email · '}
                {subject.trim().length < 3 && 'Subject (min 3 chars) · '}
                {description.trim().length < 10 && 'Details (min 10 chars) · '}
                required to continue
              </p>
            )}

            {/* ── Submit button ──────────────────────────────────────────── */}
            <button
              type="submit"
              disabled={!canSubmit}
              className={`w-full py-2.5 px-4 text-white text-sm font-semibold rounded-xl transition-colors flex items-center justify-center gap-2 ${
                canSubmit
                  ? 'bg-blue-600 hover:bg-blue-700 cursor-pointer'
                  : 'bg-blue-300 cursor-not-allowed'
              }`}
              aria-disabled={!canSubmit}
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin shrink-0" />}
              {loading ? 'Submitting…' : 'Submit Support Request'}
            </button>

            {/* Estimated response time */}
            <p className="text-xs text-center text-slate-400 flex items-center justify-center gap-1 -mt-2">
              <Clock className="w-3 h-3 shrink-0" />
              We aim to respond within 1 business day
            </p>

          </form>
        </div>

        {/* ── What happens next? ────────────────────────────────────────── */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">What happens next?</h3>
          <ol className="space-y-2.5">
            {[
              "You'll receive a confirmation email with your ticket reference number.",
              "Our support team reviews your request — typically within a few hours.",
              "We reply to your email within 1 business day. Complex issues may take slightly longer.",
            ].map((step, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-slate-600">
                <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </div>

        {/* ── Backup contact ────────────────────────────────────────────── */}
        <div className="flex items-center justify-center gap-2 text-sm text-gray-500 py-2">
          <Mail className="w-4 h-4 text-slate-400 shrink-0" />
          <span>
            Prefer email?{' '}
            <a
              href="mailto:asxscreener@gmail.com"
              className="text-blue-600 hover:underline font-medium"
            >
              asxscreener@gmail.com
            </a>
          </span>
        </div>

      </div>
    </div>
  )
}
