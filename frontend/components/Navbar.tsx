'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useState, useRef, useEffect } from 'react'
import SearchBar from './SearchBar'
import { cn } from '@/lib/utils'
import { BarChart2, Star, TrendingUp, Menu, X, LogIn, UserPlus, ChevronDown, LogOut, User, Bell, Globe, PieChart, Layers, Building2, Newspaper, Settings, BookOpen, DollarSign, Pickaxe, ScanLine, Zap, Shield, Activity, LifeBuoy, Trophy, LayoutDashboard, Users, Mail } from 'lucide-react'
import { useAuth } from '@/lib/auth'

const NAV_LINKS = [
  { href: '/',          label: 'Home',      icon: TrendingUp },
  { href: '/screener',  label: 'Screener',  icon: BarChart2 },
  { href: '/market',    label: 'Market',    icon: Globe },
  { href: '/scans',     label: 'Scans',     icon: ScanLine },
  { href: '/news',      label: 'News',      icon: Newspaper },
  { href: '/watchlist', label: 'Watchlist', icon: Star },
  { href: '/portfolio', label: 'Portfolio', icon: PieChart },
  { href: '/alerts',    label: 'Alerts',    icon: Bell },
]

const MARKET_DATA_LINKS = [
  { href: '/indices',        label: 'ASX Indices',    icon: TrendingUp, desc: 'S&P/ASX benchmark & sector indices',     premium: true },
  { href: '/funds',          label: 'ETFs & Funds',   icon: Layers,     desc: 'ETFs, LICs & managed funds',             premium: true },
  { href: '/global-markets', label: 'Global Markets', icon: Globe,      desc: 'US, Europe & Asia indices + AUD FX',     premium: true },
  { href: '/commodities',    label: 'Commodities',    icon: Pickaxe,    desc: 'Gold, oil, copper, iron ore & more',     premium: true },
  { href: '/top5',           label: 'AlphaFive',       icon: Trophy,     desc: 'Weekly algo-ranked top 5 from ASX 200',  premium: true },
]

const RESOURCES_LINKS = [
  { href: '/glossary', label: 'Metrics Glossary', icon: BookOpen,   desc: 'Definitions, formulas & benchmarks for all metrics', premium: true },
  { href: '/learn',    label: 'Education Hub',    icon: BookOpen,   desc: 'Guides, tutorials & courses',                        premium: true },
  { href: '/brokers',  label: 'Broker Compare',   icon: DollarSign, desc: 'Best ASX trading platforms 2026',                    premium: true },
  { href: '/contact',  label: 'Contact Support',  icon: Bell,       desc: 'Get help or report an issue',                       premium: false },
]

const PLAN_BADGE: Record<string, string> = {
  free:       'bg-gray-100 text-gray-600',
  pro:        'bg-blue-100 text-blue-700',
  premium:    'bg-purple-100 text-purple-700',
  enterprise: 'bg-amber-100 text-amber-700',
}

const ADMIN_LINKS = [
  { href: '/admin',          label: 'Dashboard',        icon: LayoutDashboard, desc: 'Platform overview & key stats' },
  { href: '/admin/users',    label: 'User Management',  icon: Users,           desc: 'Search, filter & manage users' },
  { href: '/admin/pipeline', label: 'Pipeline Monitor', icon: Activity,        desc: 'Daily job health & last-run status' },
  { href: '/admin/comms',    label: 'Communications',   icon: Mail,            desc: 'Notifications, alerts & announcements' },
  { href: '/admin/support',  label: 'Support Tickets',  icon: LifeBuoy,        desc: 'User support requests & inquiries' },
]

// Paths that activate the Premium Data dropdown as "active"
const PREMIUM_DATA_PATHS = ['/indices', '/funds', '/global-markets', '/commodities', '/top5']
// Paths that activate the Resources dropdown as "active"
const RESOURCES_PATHS = ['/learn', '/brokers', '/glossary', '/contact']

export default function Navbar() {
  const pathname = usePathname()
  const router   = useRouter()
  const { user, loading, logout } = useAuth()

  const [menuOpen,         setMenuOpen]         = useState(false)
  const [userDropOpen,     setUserDropOpen]     = useState(false)
  const [marketDropOpen,   setMarketDropOpen]   = useState(false)
  const [resourceDropOpen, setResourceDropOpen] = useState(false)
  const [adminDropOpen,    setAdminDropOpen]    = useState(false)
  const dropRef         = useRef<HTMLDivElement>(null)
  const marketDropRef   = useRef<HTMLDivElement>(null)
  const resourceDropRef = useRef<HTMLDivElement>(null)
  const adminDropRef    = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (dropRef.current         && !dropRef.current.contains(e.target as Node))         setUserDropOpen(false)
      if (marketDropRef.current   && !marketDropRef.current.contains(e.target as Node))   setMarketDropOpen(false)
      if (resourceDropRef.current && !resourceDropRef.current.contains(e.target as Node)) setResourceDropOpen(false)
      if (adminDropRef.current    && !adminDropRef.current.contains(e.target as Node))    setAdminDropOpen(false)
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  async function handleLogout() {
    setUserDropOpen(false)
    await logout()
    router.push('/')
  }

  // Shared styles
  const navItem = (active: boolean) => cn(
    'whitespace-nowrap px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors',
    active ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
  )
  const dropBtn = (active: boolean) => cn(
    'whitespace-nowrap flex items-center gap-1 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors',
    active ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
  )

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-screen-2xl mx-auto px-4">
        <div className="flex items-center h-14 gap-2 min-w-0">

          {/* ── Logo ─────────────────────────────────────────── */}
          <Link href="/" className="flex items-center gap-2 font-bold text-blue-600 text-lg shrink-0 mr-2">
            <BarChart2 className="w-5 h-5" />
            <span className="whitespace-nowrap">ASX Screener</span>
          </Link>

          {/* ── Desktop nav links ─────────────────────────────── */}
          <div className="hidden lg:flex items-center gap-0.5 shrink-0">

            {NAV_LINKS.map(({ href, label }) => {
              /* Screener: always solid blue pill — primary CTA */
              if (href === '/screener') {
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      'whitespace-nowrap px-3 py-1.5 rounded-full text-sm font-semibold transition-colors',
                      pathname === '/screener'
                        ? 'bg-blue-700 text-white shadow-md ring-2 ring-blue-300'
                        : 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                    )}
                  >
                    {label}
                  </Link>
                )
              }
              /* All other links — light active pill on current page */
              return (
                <Link key={href} href={href} className={navItem(pathname === href)}>
                  {label}
                </Link>
              )
            })}

            {/* Premium Data dropdown */}
            <div className="relative" ref={marketDropRef}>
              <button
                onClick={() => setMarketDropOpen(v => !v)}
                className={dropBtn(PREMIUM_DATA_PATHS.includes(pathname))}
              >
                <Building2 className="w-3.5 h-3.5 shrink-0" />
                Premium Data
                <ChevronDown className={cn('w-3.5 h-3.5 shrink-0 transition-transform', marketDropOpen && 'rotate-180')} />
              </button>
              {marketDropOpen && (
                <div className="absolute left-0 mt-1 w-64 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-50">
                  {MARKET_DATA_LINKS.map(({ href, label, icon: Icon, desc, premium }) => (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setMarketDropOpen(false)}
                      className={cn('flex items-start gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors', pathname === href && 'bg-blue-50')}
                    >
                      <Icon className={cn('w-4 h-4 mt-0.5 shrink-0', pathname === href ? 'text-blue-500' : 'text-gray-400')} />
                      <div className="flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className={cn('text-sm font-medium', pathname === href ? 'text-blue-700' : 'text-gray-800')}>{label}</span>
                          {premium && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">Premium</span>}
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>

            {/* Resources dropdown */}
            <div className="relative" ref={resourceDropRef}>
              <button
                onClick={() => setResourceDropOpen(v => !v)}
                className={dropBtn(RESOURCES_PATHS.includes(pathname))}
              >
                <BookOpen className="w-3.5 h-3.5 shrink-0" />
                Resources
                <ChevronDown className={cn('w-3.5 h-3.5 shrink-0 transition-transform', resourceDropOpen && 'rotate-180')} />
              </button>
              {resourceDropOpen && (
                <div className="absolute left-0 mt-1 w-64 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-50">
                  {RESOURCES_LINKS.map(({ href, label, icon: Icon, desc, premium }) => (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setResourceDropOpen(false)}
                      className="flex items-start gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors"
                    >
                      <Icon className="w-4 h-4 text-gray-400 mt-0.5 shrink-0" />
                      <div className="flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-medium text-gray-800">{label}</span>
                          {premium && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">Premium</span>}
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>

            {/* Admin dropdown — admin users only */}
            {user?.is_admin && (
              <div className="relative" ref={adminDropRef}>
                <button
                  onClick={() => setAdminDropOpen(v => !v)}
                  className={cn(
                    dropBtn(pathname.startsWith('/admin')),
                    'text-red-600 hover:text-red-700 hover:bg-red-50',
                    pathname.startsWith('/admin') && '!bg-red-50 !text-red-700'
                  )}
                >
                  <Shield className="w-3.5 h-3.5 shrink-0" />
                  Admin
                  <ChevronDown className={cn('w-3.5 h-3.5 shrink-0 transition-transform', adminDropOpen && 'rotate-180')} />
                </button>
                {adminDropOpen && (
                  <div className="absolute left-0 mt-1 w-60 bg-white border border-red-100 rounded-xl shadow-lg py-1 z-50">
                    <div className="px-3 py-1.5 border-b border-red-50">
                      <p className="text-[10px] font-bold text-red-400 uppercase tracking-wider">Admin Tools</p>
                    </div>
                    {ADMIN_LINKS.map(({ href, label, icon: Icon, desc }) => (
                      <Link
                        key={href}
                        href={href}
                        onClick={() => setAdminDropOpen(false)}
                        className="flex items-start gap-3 px-3 py-2.5 hover:bg-red-50 transition-colors"
                      >
                        <Icon className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                        <div className="flex-1">
                          <span className="text-sm font-medium text-gray-800">{label}</span>
                          <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                        </div>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── Search bar — grows to fill available space ─────── */}
          <div className="flex-1 min-w-[180px] max-w-[280px] ml-auto">
            <SearchBar />
          </div>

          {/* ── Auth / user menu — desktop ────────────────────── */}
          <div className="hidden lg:flex items-center gap-2 shrink-0">
            {loading ? (
              <div className="w-20 h-8 bg-gray-100 rounded-lg animate-pulse" />
            ) : user ? (
              <div className="relative" ref={dropRef}>
                <button
                  onClick={() => setUserDropOpen(v => !v)}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  <div className="w-7 h-7 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs font-semibold shrink-0">
                    {(user.name || user.email)[0].toUpperCase()}
                  </div>
                  <div className="flex flex-col items-start leading-tight">
                    <span className="max-w-[90px] truncate text-sm font-medium text-gray-700 whitespace-nowrap">
                      {user.name || user.email}
                    </span>
                    <span className={cn('text-[10px] px-1.5 py-0 rounded font-semibold capitalize', PLAN_BADGE[user.plan] ?? PLAN_BADGE.free)}>
                      {user.plan}
                    </span>
                  </div>
                  <ChevronDown className={cn('w-3.5 h-3.5 transition-transform shrink-0', userDropOpen && 'rotate-180')} />
                </button>

                {userDropOpen && (
                  <div className="absolute right-0 mt-1 w-48 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-50">
                    <div className="px-3 py-2 border-b border-gray-100">
                      <p className="text-xs font-medium text-gray-900 truncate">{user.email}</p>
                    </div>
                    <Link href="/account"       onClick={() => setUserDropOpen(false)} className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"><User className="w-4 h-4" />Account settings</Link>
                    <Link href="/pricing"        onClick={() => setUserDropOpen(false)} className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"><Zap className="w-4 h-4" />Plans &amp; Pricing</Link>
                    <Link href="/notifications"  onClick={() => setUserDropOpen(false)} className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"><Settings className="w-4 h-4" />Notifications</Link>
                    {user.is_admin && (
                      <div className="border-t border-gray-100 mt-1 pt-1">
                        <div className="px-3 py-1"><p className="text-[10px] font-bold text-red-400 uppercase tracking-wider">Admin</p></div>
                        {ADMIN_LINKS.map(({ href, label, icon: Icon }) => (
                          <Link key={href} href={href} onClick={() => setUserDropOpen(false)} className="flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50">
                            <Icon className="w-4 h-4" />{label}
                          </Link>
                        ))}
                      </div>
                    )}
                    <div className="border-t border-gray-100 mt-1 pt-1">
                      <button onClick={handleLogout} className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50">
                        <LogOut className="w-4 h-4" />Sign out
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <>
                <Link href="/pricing"      className={navItem(pathname === '/pricing')}>Pricing</Link>
                <Link href="/auth/login"   className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors whitespace-nowrap"><LogIn className="w-4 h-4" />Sign in</Link>
                <Link href="/auth/register" className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors whitespace-nowrap"><UserPlus className="w-4 h-4" />Sign up free</Link>
              </>
            )}
          </div>

          {/* ── Mobile hamburger ──────────────────────────────── */}
          <button
            className="lg:hidden p-2 rounded-md text-gray-600 hover:bg-gray-100 shrink-0"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* ── Mobile menu ────────────────────────────────────── */}
        {menuOpen && (
          <div className="lg:hidden py-2 border-t border-gray-100">
            {NAV_LINKS.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                onClick={() => setMenuOpen(false)}
                className={cn('flex items-center gap-2 px-4 py-2.5 text-sm', pathname === href ? 'text-blue-700 font-semibold bg-blue-50' : 'text-gray-700')}
              >
                <Icon className="w-4 h-4" />{label}
              </Link>
            ))}
            <div className="px-4 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider mt-2">Premium Data</div>
            {MARKET_DATA_LINKS.map(({ href, label, icon: Icon }) => (
              <Link key={href} href={href} onClick={() => setMenuOpen(false)} className={cn('flex items-center gap-2 px-4 py-2.5 text-sm', pathname === href ? 'text-blue-700 font-semibold bg-blue-50' : 'text-gray-700')}>
                <Icon className="w-4 h-4" />{label}
              </Link>
            ))}
            <div className="px-4 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider mt-2">Resources</div>
            {RESOURCES_LINKS.map(({ href, label, icon: Icon }) => (
              <Link key={href} href={href} onClick={() => setMenuOpen(false)} className={cn('flex items-center gap-2 px-4 py-2.5 text-sm', pathname === href ? 'text-blue-700 font-semibold bg-blue-50' : 'text-gray-700')}>
                <Icon className="w-4 h-4" />{label}
              </Link>
            ))}
            {user?.is_admin && (
              <>
                <div className="px-4 py-1 text-[10px] font-bold text-red-400 uppercase tracking-wider mt-2">Admin</div>
                {ADMIN_LINKS.map(({ href, label, icon: Icon }) => (
                  <Link key={href} href={href} onClick={() => setMenuOpen(false)} className={cn('flex items-center gap-2 px-4 py-2.5 text-sm', pathname === href ? 'text-red-700 font-semibold' : 'text-red-600')}>
                    <Icon className="w-4 h-4" />{label}
                  </Link>
                ))}
              </>
            )}
            <div className="border-t border-gray-100 mt-2 pt-2">
              {!loading && !user && (
                <>
                  <Link href="/pricing"      onClick={() => setMenuOpen(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm text-gray-700 font-medium">Pricing</Link>
                  <Link href="/auth/login"   onClick={() => setMenuOpen(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm text-gray-700"><LogIn className="w-4 h-4" />Sign in</Link>
                  <Link href="/auth/register" onClick={() => setMenuOpen(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm text-blue-600 font-medium"><UserPlus className="w-4 h-4" />Sign up free</Link>
                </>
              )}
              {!loading && user && (
                <>
                  <div className="px-4 py-2">
                    <p className="text-xs text-gray-500">Signed in as</p>
                    <p className="text-sm font-medium text-gray-900 truncate">{user.email}</p>
                  </div>
                  <Link href="/account"      onClick={() => setMenuOpen(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm text-gray-700"><User className="w-4 h-4" />Account settings</Link>
                  <Link href="/pricing"      onClick={() => setMenuOpen(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm text-gray-700"><Zap className="w-4 h-4" />Plans &amp; Pricing</Link>
                  <button onClick={() => { setMenuOpen(false); handleLogout() }} className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-red-600">
                    <LogOut className="w-4 h-4" />Sign out
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
