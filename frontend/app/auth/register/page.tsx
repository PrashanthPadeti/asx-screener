'use client'
import { useState, FormEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { BarChart2, Eye, EyeOff, Loader2, CheckCircle2 } from 'lucide-react'
import { useAuth } from '@/lib/auth'

const PLAN_PERKS = [
  'Screen all ~1,800 ASX companies',
  'Franking credit gross-up yields',
  'Mining & REIT depth filters',
  'Composite quality scores',
  'ASX announcements feed',
]

export default function RegisterPage() {
  const router = useRouter()
  const { register } = useAuth()

  const [name,      setName]      = useState('')
  const [email,     setEmail]     = useState('')
  const [password,  setPassword]  = useState('')
  const [showPw,    setShowPw]    = useState(false)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState<string | null>(null)
  // Set when the account was created but must be verified before signing in.
  const [notice,    setNotice]    = useState<{ email: string; email_sent: boolean;
                                               message: string } | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const pending = await register(email, password, name || undefined)
      // No tokens are issued when verification is required, so there is no
      // session to land in — show what to do next instead of redirecting to
      // a page that would bounce them straight back to sign-in.
      if (pending) setNotice(pending)
      else router.push('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  if (notice) {
    return (
      <div className="min-h-[80vh] flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-md bg-white border border-slate-200 rounded-xl p-8 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-50 border border-emerald-200
                          flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 className="w-6 h-6 text-emerald-600" />
          </div>
          <h1 className="text-xl font-bold text-slate-800">Check your email</h1>
          <p className="mt-2 text-sm text-slate-600">{notice.message}</p>
          <p className="mt-3 text-sm text-slate-700 font-medium break-all">{notice.email}</p>
          <div className="mt-5 p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900 text-left">
            <strong>Not arrived?</strong> It can take a minute, and it often
            lands in the <strong>spam or junk folder</strong> — please check
            there before trying again. You can resend the link from the
            sign-in page.
          </div>
          <Link href="/auth/login"
                className="mt-5 inline-block text-sm text-blue-600 hover:underline">
            Go to sign in
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-4xl grid md:grid-cols-2 gap-8 items-start">

        {/* Left — feature list */}
        <div className="hidden md:block pt-4">
          <div className="flex items-center gap-2 mb-6">
            <BarChart2 className="w-7 h-7 text-blue-600" />
            <span className="text-xl font-bold text-gray-900">ASX Screener</span>
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Australia&apos;s smartest stock screener
          </h2>
          <p className="text-gray-500 text-sm mb-6">
            Free forever. No credit card required.
          </p>
          <ul className="space-y-3">
            {PLAN_PERKS.map(perk => (
              <li key={perk} className="flex items-start gap-2 text-sm text-gray-700">
                <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
                {perk}
              </li>
            ))}
          </ul>
        </div>

        {/* Right — form */}
        <div>
          {/* Mobile logo */}
          <div className="flex items-center justify-center gap-2 mb-6 md:hidden">
            <BarChart2 className="w-7 h-7 text-blue-600" />
            <span className="text-xl font-bold text-gray-900">ASX Screener</span>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <h1 className="text-lg font-semibold text-gray-900 mb-1">Create your account</h1>
            <p className="text-sm text-gray-500 mb-6">
              Already have one?{' '}
              <Link href="/auth/login" className="text-blue-600 hover:underline font-medium">
                Sign in
              </Link>
            </p>

            {error && (
              <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Name (optional) */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Name <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  autoComplete="name"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                             focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Jane Smith"
                />
              </div>

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
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPw ? 'text' : 'password'}
                    required
                    minLength={8}
                    autoComplete="new-password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-lg text-sm
                               focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    placeholder="Min. 8 characters"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(!showPw)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="mt-1 text-xs text-gray-400">Minimum 8 characters</p>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400
                           text-white text-sm font-medium rounded-lg transition-colors
                           flex items-center justify-center gap-2"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {loading ? 'Creating account…' : 'Create free account'}
              </button>
            </form>
          </div>

          <p className="mt-4 text-center text-xs text-gray-400">
            By registering you agree to our{' '}
            <Link href="/terms" className="hover:underline">Terms</Link>
            {' '}and{' '}
            <Link href="/privacy" className="hover:underline">Privacy Policy</Link>.
          </p>
        </div>
      </div>
    </div>
  )
}
