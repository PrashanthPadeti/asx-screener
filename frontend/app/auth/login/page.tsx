'use client'
import { useState, FormEvent, Suspense } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { BarChart2, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuth } from '@/lib/auth'

function LoginForm() {
  const router       = useRouter()
  const searchParams = useSearchParams()
  const { login }    = useAuth()

  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [showPw,   setShowPw]   = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)
  // The credentials were right; the account just isn't verified. A different
  // state from `error`, because the answer is "check your inbox", not
  // "try again".
  const [unverified, setUnverified] = useState<string | null>(null)
  const [resend, setResend] = useState<'idle' | 'sending' | 'sent'>('idle')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setUnverified(null)
    setResend('idle')
    setLoading(true)
    try {
      await login(email, password)
      const redirect = searchParams.get('redirect')
      router.push(redirect && redirect.startsWith('/') ? redirect : '/')
    } catch (err: unknown) {
      const e = err as { code?: string; message?: string }
      if (e?.code === 'email_not_verified') {
        setUnverified(e.message || 'Your email address has not been verified yet.')
      } else {
        setError(err instanceof Error ? err.message : 'Login failed')
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    setResend('sending')
    try {
      await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ''}/api/v1/auth/resend-verification`,
        { method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email }) })
    } catch { /* the endpoint answers the same either way; never block the UI */ }
    // Always reports sent: the endpoint deliberately gives the same answer
    // whether or not the address exists, so claiming anything more specific
    // here would leak what it is designed not to.
    setResend('sent')
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <BarChart2 className="w-7 h-7 text-blue-600" />
          <span className="text-xl font-bold text-gray-900">ASX Screener</span>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h1 className="text-lg font-semibold text-gray-900 mb-1">Sign in</h1>
          <p className="text-sm text-gray-500 mb-6">
            Don&apos;t have an account?{' '}
            <Link href="/auth/register" className="text-blue-600 hover:underline font-medium">
              Sign up free
            </Link>
          </p>

          {error && (
            <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
              {error}
            </div>
          )}

          {unverified && (
            <div className="mb-4 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg">
              <p className="text-sm font-semibold text-amber-900">
                Please verify your email address
              </p>
              <p className="mt-1 text-sm text-amber-900">{unverified}</p>
              <p className="mt-2 text-xs text-amber-800">
                Tip: search your inbox <em>and</em> your spam or junk folder
                for an email from ASX Screener.
              </p>

              {resend === 'sent' ? (
                <p className="mt-3 text-sm text-emerald-700">
                  Verification link sent to <strong>{email}</strong>. It can
                  take a minute to arrive — remember to check spam.
                </p>
              ) : (
                <button type="button" onClick={handleResend}
                        disabled={resend === 'sending' || !email}
                        className="mt-3 text-sm font-medium text-blue-700 hover:underline
                                   disabled:opacity-50">
                  {resend === 'sending' ? 'Sending…' : 'Resend verification email'}
                </button>
              )}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email address
              </label>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                           focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="you@example.com"
              />
            </div>

            {/* Password */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium text-gray-700">
                  Password
                </label>
                <Link href="/auth/forgot-password" className="text-xs text-blue-600 hover:underline">
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  required
                  autoComplete="current-password"
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

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400
                         text-white text-sm font-medium rounded-lg transition-colors
                         flex items-center justify-center gap-2"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-gray-400">
          By signing in you agree to our{' '}
          <Link href="/terms" className="hover:underline">Terms</Link>
          {' '}and{' '}
          <Link href="/privacy" className="hover:underline">Privacy Policy</Link>.
        </p>
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-[80vh]">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <LoginForm />
    </Suspense>
  )
}
