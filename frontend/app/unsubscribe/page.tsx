'use client'
/**
 * /unsubscribe
 *
 * Spam Act 2003 (Cth) compliance — one-click email unsubscribe.
 *
 * Called via the link embedded in every marketing/alert email footer:
 *   https://asxscreener.com.au/unsubscribe?token=<HMAC_TOKEN>&type=all_marketing
 *
 * Supported types:
 *   all_marketing  — product updates, newsletters (default)
 *   alerts         — price alert emails
 *   digest         — weekly digest emails
 *
 * The token is single-use and stored in users.unsubscribe_tokens.
 * Processing is immediate — Spam Act requires action within 5 business days;
 * we process instantly.
 */

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { MailX, CheckCircle2, AlertTriangle, Loader2, Bell } from 'lucide-react'
import { api } from '@/lib/api'

type Status = 'loading' | 'success' | 'already_done' | 'error' | 'idle'

const TYPE_LABELS: Record<string, string> = {
  all_marketing: 'all marketing and product update emails',
  alerts:        'price alert emails',
  digest:        'weekly digest emails',
}

function UnsubscribeContent() {
  const params = useSearchParams()
  const token  = params.get('token')
  const type   = params.get('type') ?? 'all_marketing'

  const [status, setStatus] = useState<Status>(token ? 'loading' : 'idle')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!token) return

    api.post('/api/v1/notifications/unsubscribe', { token, type })
      .then(() => {
        setStatus('success')
      })
      .catch(err => {
        const detail = err?.response?.data?.detail ?? ''
        if (detail.includes('already') || detail.includes('used')) {
          setStatus('already_done')
        } else if (err?.response?.status === 404) {
          setStatus('error')
          setMessage('This unsubscribe link is invalid or has expired.')
        } else {
          setStatus('error')
          setMessage('Something went wrong. Please try again or contact support.')
        }
      })
  }, [token, type])

  const typeLabel = TYPE_LABELS[type] ?? type

  /* ── No token — manual unsubscribe instructions ── */
  if (!token) {
    return (
      <div className="text-center space-y-4">
        <div className="w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center mx-auto">
          <MailX className="w-7 h-7 text-slate-400" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Unsubscribe</h1>
        <p className="text-slate-500 max-w-sm mx-auto text-sm leading-relaxed">
          To unsubscribe from emails, use the unsubscribe link at the bottom of any
          email we&apos;ve sent you, or manage your preferences from your account settings.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
          <Link
            href="/account"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5
                       bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold
                       rounded-xl transition-colors"
          >
            <Bell className="w-4 h-4" />
            Manage preferences
          </Link>
          <Link
            href="/contact"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5
                       border border-slate-200 hover:border-slate-300 text-slate-600
                       text-sm font-semibold rounded-xl transition-colors"
          >
            Contact support
          </Link>
        </div>
      </div>
    )
  }

  /* ── Processing ── */
  if (status === 'loading') {
    return (
      <div className="text-center space-y-4">
        <Loader2 className="w-10 h-10 text-blue-600 animate-spin mx-auto" />
        <p className="text-slate-500 text-sm">Processing your unsubscribe request…</p>
      </div>
    )
  }

  /* ── Success ── */
  if (status === 'success') {
    return (
      <div className="text-center space-y-4">
        <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mx-auto">
          <CheckCircle2 className="w-7 h-7 text-green-600" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900">You&apos;re unsubscribed</h1>
        <p className="text-slate-600 max-w-sm mx-auto text-sm leading-relaxed">
          You&apos;ve been unsubscribed from <strong>{typeLabel}</strong>.
          You will no longer receive these emails from ASX Screener.
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-600 max-w-sm mx-auto text-left space-y-1.5">
          <p className="font-semibold text-slate-700">What you&apos;ll still receive</p>
          <p className="text-xs leading-relaxed">
            Transactional emails — password resets, subscription receipts, and account
            security alerts — cannot be unsubscribed from as they are essential to your
            account. These are not marketing messages.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
          <Link
            href="/account"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5
                       bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold
                       rounded-xl transition-colors"
          >
            <Bell className="w-4 h-4" />
            Review all preferences
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center px-5 py-2.5
                       border border-slate-200 hover:border-slate-300 text-slate-600
                       text-sm font-semibold rounded-xl transition-colors"
          >
            Back to ASX Screener
          </Link>
        </div>
        <p className="text-xs text-slate-400 max-w-xs mx-auto">
          Changed your mind?{' '}
          <Link href="/account" className="text-blue-600 hover:underline">
            Re-enable emails in account settings
          </Link>.
        </p>
      </div>
    )
  }

  /* ── Already done ── */
  if (status === 'already_done') {
    return (
      <div className="text-center space-y-4">
        <div className="w-14 h-14 rounded-full bg-blue-50 flex items-center justify-center mx-auto">
          <CheckCircle2 className="w-7 h-7 text-blue-600" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Already unsubscribed</h1>
        <p className="text-slate-500 max-w-sm mx-auto text-sm leading-relaxed">
          You have already unsubscribed from {typeLabel}.
          No further action is needed.
        </p>
        <Link
          href="/account"
          className="inline-flex items-center justify-center gap-2 px-5 py-2.5
                     bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold
                     rounded-xl transition-colors"
        >
          Manage email preferences
        </Link>
      </div>
    )
  }

  /* ── Error ── */
  return (
    <div className="text-center space-y-4">
      <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center mx-auto">
        <AlertTriangle className="w-7 h-7 text-red-500" />
      </div>
      <h1 className="text-2xl font-bold text-slate-900">Unsubscribe failed</h1>
      <p className="text-slate-500 max-w-sm mx-auto text-sm leading-relaxed">
        {message}
      </p>
      <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
        <Link
          href="/account"
          className="inline-flex items-center justify-center gap-2 px-5 py-2.5
                     bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold
                     rounded-xl transition-colors"
        >
          Manage in account settings
        </Link>
        <Link
          href="/contact"
          className="inline-flex items-center justify-center px-5 py-2.5
                     border border-slate-200 hover:border-slate-300 text-slate-600
                     text-sm font-semibold rounded-xl transition-colors"
        >
          Contact support
        </Link>
      </div>
    </div>
  )
}

export default function UnsubscribePage() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4">
      <div className="w-full max-w-md py-16">
        <Suspense fallback={
          <div className="text-center">
            <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
          </div>
        }>
          <UnsubscribeContent />
        </Suspense>

        {/* Spam Act notice */}
        <p className="mt-12 text-center text-xs text-slate-300 leading-relaxed">
          ASX Screener processes unsubscribe requests immediately in compliance with the{' '}
          <em>Spam Act 2003 (Cth)</em>. For questions about our email practices,
          contact{' '}
          <a href="mailto:asxscreener@gmail.com" className="hover:text-slate-500 transition-colors">
            asxscreener@gmail.com
          </a>.
        </p>
      </div>
    </div>
  )
}
