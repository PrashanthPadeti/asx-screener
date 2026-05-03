'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, useRef, useEffect } from 'react'
import SearchBar from './SearchBar'
import { cn } from '@/lib/utils'
import { BarChart2, Star, TrendingUp, Menu, X, LogIn, UserPlus, ChevronDown, LogOut, User } from 'lucide-react'
import { useAuth } from '@/lib/auth'

const NAV_LINKS = [
  { href: '/',          label: 'Home',      icon: TrendingUp },
  { href: '/screener',  label: 'Screener',  icon: BarChart2 },
  { href: '/watchlist', label: 'Watchlist', icon: Star },
]

const PLAN_BADGE: Record<string, string> = {
  free:       'bg-gray-100 text-gray-600',
  pro:        'bg-blue-100 text-blue-700',
  premium:    'bg-purple-100 text-purple-700',
  enterprise: 'bg-amber-100 text-amber-700',
}

export default function Navbar() {
  const pathname = usePathname()
  const router   = useRouter()
  const { user, loading, logout } = useAuth()

  const [menuOpen,    setMenuOpen]    = useState(false)
  const [userDropOpen, setUserDropOpen] = useState(false)
  const dropRef = useRef<HTMLDivElement>(null)

  // Close user dropdown on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) {
        setUserDropOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  async function handleLogout() {
    setUserDropOpen(false)
    await logout()
    router.push('/')
  }

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-screen-2xl mx-auto px-4">
        <div className="flex items-center h-14 gap-4">

          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 font-bold text-blue-600 text-lg shrink-0">
            <BarChart2 className="w-5 h-5" />
            ASX Screener
          </Link>

          {/* Desktop nav links */}
          <div className="hidden md:flex items-center gap-1 ml-4">
            {NAV_LINKS.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                  pathname === href
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                )}
              >
                {label}
              </Link>
            ))}
          </div>

          {/* Search bar */}
          <div className="flex-1 max-w-md ml-auto">
            <SearchBar />
          </div>

          {/* Auth buttons / user menu — desktop */}
          <div className="hidden md:flex items-center gap-2 shrink-0">
            {loading ? (
              /* Skeleton */
              <div className="w-20 h-8 bg-gray-100 rounded-lg animate-pulse" />
            ) : user ? (
              /* Logged-in user dropdown */
              <div className="relative" ref={dropRef}>
                <button
                  onClick={() => setUserDropOpen(v => !v)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm
                             text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  <div className="w-7 h-7 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-semibold">
                    {(user.name || user.email)[0].toUpperCase()}
                  </div>
                  <span className="max-w-[120px] truncate">
                    {user.name || user.email}
                  </span>
                  <span className={cn(
                    'text-xs px-1.5 py-0.5 rounded font-medium capitalize',
                    PLAN_BADGE[user.plan] ?? PLAN_BADGE.free
                  )}>
                    {user.plan}
                  </span>
                  <ChevronDown className={cn('w-3.5 h-3.5 transition-transform', userDropOpen && 'rotate-180')} />
                </button>

                {userDropOpen && (
                  <div className="absolute right-0 mt-1 w-48 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-50">
                    <div className="px-3 py-2 border-b border-gray-100">
                      <p className="text-xs font-medium text-gray-900 truncate">{user.email}</p>
                    </div>
                    <Link
                      href="/account"
                      onClick={() => setUserDropOpen(false)}
                      className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <User className="w-4 h-4" />
                      Account settings
                    </Link>
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                    >
                      <LogOut className="w-4 h-4" />
                      Sign out
                    </button>
                  </div>
                )}
              </div>
            ) : (
              /* Logged-out buttons */
              <>
                <Link
                  href="/auth/login"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium
                             text-gray-700 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <LogIn className="w-4 h-4" />
                  Sign in
                </Link>
                <Link
                  href="/auth/register"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium
                             bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                >
                  <UserPlus className="w-4 h-4" />
                  Sign up free
                </Link>
              </>
            )}
          </div>

          {/* Mobile menu button */}
          <button
            className="md:hidden p-2 rounded-md text-gray-600 hover:bg-gray-100"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* Mobile menu */}
        {menuOpen && (
          <div className="md:hidden py-2 border-t border-gray-100">
            {NAV_LINKS.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                onClick={() => setMenuOpen(false)}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 text-sm',
                  pathname === href ? 'text-blue-700 font-medium' : 'text-gray-700'
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            ))}

            {/* Mobile auth */}
            <div className="border-t border-gray-100 mt-2 pt-2">
              {!loading && !user && (
                <>
                  <Link
                    href="/auth/login"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700"
                  >
                    <LogIn className="w-4 h-4" />
                    Sign in
                  </Link>
                  <Link
                    href="/auth/register"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-blue-600 font-medium"
                  >
                    <UserPlus className="w-4 h-4" />
                    Sign up free
                  </Link>
                </>
              )}
              {!loading && user && (
                <>
                  <div className="px-4 py-2">
                    <p className="text-xs text-gray-500">Signed in as</p>
                    <p className="text-sm font-medium text-gray-900 truncate">{user.email}</p>
                  </div>
                  <button
                    onClick={() => { setMenuOpen(false); handleLogout() }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign out
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </nav>
  )
}
