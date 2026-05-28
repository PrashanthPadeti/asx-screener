'use client'
import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard, Users, Activity, LifeBuoy,
  ChevronRight, Shield, Menu, X, Mail, FlaskConical, BrainCircuit, History,
} from 'lucide-react'

const NAV = [
  { href: '/admin',                     label: 'Dashboard',          icon: LayoutDashboard },
  { href: '/admin/users',               label: 'User Management',    icon: Users },
  { href: '/admin/pipeline',            label: 'Pipeline Monitor',   icon: Activity },
  { href: '/admin/comms',               label: 'Communications',     icon: Mail },
  { href: '/admin/support',             label: 'Support Tickets',    icon: LifeBuoy },
  { href: '/admin/research',            label: 'Research Assistant', icon: FlaskConical },
  { href: '/admin/predictions',         label: 'Price Predictions',  icon: BrainCircuit },
  { href: '/admin/predictions/history', label: 'Prediction History', icon: History },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    if (!loading && (!user || !user.is_admin)) {
      router.replace('/')
    }
  }, [user, loading, router])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!user?.is_admin) return null

  const Sidebar = ({ mobile = false }: { mobile?: boolean }) => (
    <nav className={cn(
      'flex flex-col h-full',
      mobile ? 'p-4' : 'p-4'
    )}>
      {/* Brand */}
      <div className="flex items-center gap-2 px-2 py-3 mb-4 border-b border-slate-200">
        <Shield className="w-5 h-5 text-red-600 shrink-0" />
        <div>
          <p className="text-sm font-bold text-slate-800">Admin Console</p>
          <p className="text-[10px] text-slate-400 truncate max-w-[140px]">{user.email}</p>
        </div>
      </div>

      {/* Nav links */}
      <div className="flex-1 space-y-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === '/admin'
            ? pathname === '/admin'
            : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              onClick={() => setSidebarOpen(false)}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                active
                  ? 'bg-red-50 text-red-700 border border-red-100'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              )}
            >
              <Icon className={cn('w-4 h-4 shrink-0', active ? 'text-red-600' : 'text-slate-400')} />
              {label}
              {active && <ChevronRight className="w-3 h-3 ml-auto text-red-400" />}
            </Link>
          )
        })}
      </div>

      {/* Footer */}
      <div className="border-t border-slate-200 pt-3 mt-3">
        <Link
          href="/"
          className="flex items-center gap-2 px-3 py-2 text-xs text-slate-500 hover:text-slate-700 rounded-lg hover:bg-slate-100"
        >
          ← Back to ASX Screener
        </Link>
      </div>
    </nav>
  )

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-56 bg-white border-r border-slate-200 shrink-0 sticky top-0 h-screen">
        <Sidebar />
      </aside>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setSidebarOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-56 bg-white border-r border-slate-200">
            <Sidebar mobile />
          </aside>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <div className="md:hidden flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200">
          <button onClick={() => setSidebarOpen(true)} className="p-1 rounded text-slate-600">
            <Menu className="w-5 h-5" />
          </button>
          <Shield className="w-4 h-4 text-red-600" />
          <span className="text-sm font-bold text-slate-800">Admin Console</span>
        </div>

        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
