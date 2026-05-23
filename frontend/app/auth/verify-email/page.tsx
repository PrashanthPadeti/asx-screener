'use client'
import { useEffect, useState, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'
import { CheckCircle, XCircle, Loader2, Mail } from 'lucide-react'

function VerifyEmailContent() {
  const searchParams = useSearchParams()
  const token = searchParams.get('token')

  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setMessage('No verification token found in the link. Please check your email and try again.')
      return
    }

    const verify = async () => {
      try {
        const { data } = await api.get(`/api/v1/auth/verify-email?token=${encodeURIComponent(token)}`)
        setStatus('success')
        setMessage(data.message || 'Email verified successfully!')
      } catch (e: any) {
        setStatus('error')
        setMessage(e?.response?.data?.detail || 'This verification link is invalid or has expired.')
      }
    }

    verify()
  }, [token])

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 max-w-md w-full text-center">

        {status === 'loading' && (
          <>
            <div className="w-14 h-14 bg-blue-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <Loader2 className="w-7 h-7 text-blue-600 animate-spin" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 mb-2">Verifying your email…</h1>
            <p className="text-slate-500 text-sm">Just a moment while we confirm your address.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-14 h-14 bg-emerald-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="w-7 h-7 text-emerald-600" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 mb-2">Email Verified!</h1>
            <p className="text-slate-500 text-sm mb-6">{message}</p>
            <Link
              href="/screener"
              className="inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl transition-colors text-sm"
            >
              Go to Screener
            </Link>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="w-14 h-14 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-4">
              <XCircle className="w-7 h-7 text-red-500" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 mb-2">Verification Failed</h1>
            <p className="text-slate-500 text-sm mb-6">{message}</p>
            <div className="flex flex-col gap-2">
              <p className="text-xs text-slate-400">
                Need a new link? Ask an admin or contact{' '}
                <a href="mailto:support@asxscreener.com.au" className="text-blue-600 hover:underline">
                  support@asxscreener.com.au
                </a>
              </p>
              <Link
                href="/auth/login"
                className="inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-xl transition-colors text-sm mt-2"
              >
                Back to Login
              </Link>
            </div>
          </>
        )}

        <div className="mt-8 pt-6 border-t border-slate-100 flex items-center justify-center gap-2 text-xs text-slate-400">
          <Mail className="w-3.5 h-3.5" />
          ASX Screener · asxscreener.com.au
        </div>
      </div>
    </div>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
      </div>
    }>
      <VerifyEmailContent />
    </Suspense>
  )
}
