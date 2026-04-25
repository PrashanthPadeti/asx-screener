'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import SearchBar from './SearchBar'
import { cn } from '@/lib/utils'
import { BarChart2, Search, Star, TrendingUp, Menu, X } from 'lucide-react'

const NAV_LINKS = [
  { href: '/',          label: 'Home',     icon: TrendingUp },
  { href: '/screener',  label: 'Screener', icon: BarChart2 },
  { href: '/watchlist', label: 'Watchlist',icon: Star },
]

export default function Navbar() {
  const pathname = usePathname()
  const [menuOpen, setMenuOpen] = useState(false)

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
          </div>
        )}
      </div>
    </nav>
  )
}
