'use client'
import { useState, FormEvent, Suspense } from 'react'
import Link from 'next/link'
import { useSearchParams, useRouter } from 'next/navigation'
import { BarChart2, Eye, EyeOff, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { api } from '@/lib/api'

function ResetPasswordForm() {
  const router       = useRouter()
  const searchParams = useSearchParams()
  const token        = searchParams.get('token') ?? ''

  const [password,  setPassword]  = useState('')
  const [password2, setPassword2] = useState('')
  const [showPw,    setShowPw]    = useState(false)
  const [loading,   setLoading]   = useState(false)
  const [done,      setDone]      = useState(false)
  const [error,     setError]     = useState<string | null>(null)

  if (!token) {
    return (
      <div className="text-center py-6">
        <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-3" />
        <p className="text-sm text-gray-600 mb-4">Invalid or missing reset link.</p>
        <Link href="/auth/forgot-password" className="text-sm text-blue-600 hover:underline">
          Request a new one
        </Link>
      </div>
    )
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (password !== password2) {
      setError("Passwords don't match")
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    setError(null)
    setLoading(true)
    try {
      await api.post('/api/v1/auth/reset-password', { token, new_password: password })
      setDone(true)
      setTimeout(() => router.push('/auth/login'), 3000)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Something went wrong. The link may have expired.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {done ? (
        <div className="text-center py-4">
          <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
          <h2 className="text-base font-semibold text-gray-900 mb-2">Password updated!</h2>
          <p className="text-sm text-gray-500 mb-1">
            Your password has been changed successfully.
          </p>
          <p className="text-xs text-gray-400">Redirecting to sign in…</p>
        </div>
      ) : (
        <>
          <h1 className="text-lg font-semibold text-gray-900 mb-1">Set new password</h1>
          <p className="text-sm text-gray-500 mb-6">Choose a strong password — at least 8 characters.</p>

          {error && (
            <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">New password</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  required
                  autoComplete="new-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg text-sm
                             focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Confirm password</label>
              <input
                type={showPw ? 'text' : 'password'}
                required
                autoComplete="new-password"
                value={password2}
                onChange={e => setPassword2(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                           focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400
                         text-white text-sm font-medium rounded-lg transition-colors
                         flex items-center justify-center gap-2"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? 'Updating…' : 'Update password'}
            </button>
          </form>
        </>
      )}
    </>
  )
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        <div className="flex items-center justify-center gap-2 mb-8">
          <BarChart2 className="w-7 h-7 text-blue-600" />
          <span className="text-xl font-bold text-gray-900">ASX Screener</span>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <Suspense fallback={
            <div className="flex items-center justify-center py-8">
              <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            </div>
          }>
            <ResetPasswordForm />
          </Suspense>
        </div>

        <div className="mt-4 text-center">
          <Link href="/auth/login" className="text-sm text-gray-500 hover:text-gray-700">
            Back to sign in
          </Link>
        </div>

      </div>
    </div>
  )
}
