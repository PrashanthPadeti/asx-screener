'use client'
import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Search } from 'lucide-react'
import { searchCompanies, type SearchResult } from '@/lib/api'
import { cn, SECTOR_COLORS } from '@/lib/utils'

export default function SearchBar() {
  const [query, setQuery]       = useState('')
  const [results, setResults]   = useState<SearchResult[]>([])
  const [loading, setLoading]   = useState(false)
  const [open, setOpen]         = useState(false)
  const router  = useRouter()
  const ref     = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounced search
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (query.length < 1) { setResults([]); setOpen(false); return }

    timerRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const data = await searchCompanies(query)
        setResults(data)
        setOpen(true)
      } catch { setResults([]) }
      finally { setLoading(false) }
    }, 250)
  }, [query])

  // Click outside to close
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const handleSelect = (code: string) => {
    setQuery('')
    setOpen(false)
    router.push(`/company/${code}`)
  }

  return (
    <div ref={ref} className="relative w-full">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search stocks... (BHP, Commonwealth Bank)"
          className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                     bg-gray-50 placeholder:text-gray-400"
        />
        {loading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 w-3 h-3
                          border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute top-full mt-1 w-full bg-white border border-gray-200
                        rounded-lg shadow-lg z-50 overflow-hidden max-h-72 overflow-y-auto">
          {results.map(r => (
            <button
              key={r.asx_code}
              onClick={() => handleSelect(r.asx_code)}
              className="w-full flex items-center justify-between px-4 py-2.5
                         hover:bg-blue-50 transition-colors text-left"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono font-bold text-blue-700 text-sm w-14">{r.asx_code}</span>
                <span className="text-sm text-gray-800 truncate max-w-[180px]">{r.company_name}</span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {r.is_reit  && <span className="text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">REIT</span>}
                {r.is_miner && <span className="text-xs bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded">Miner</span>}
                {r.gics_sector && (
                  <span className={cn('text-xs px-1.5 py-0.5 rounded', SECTOR_COLORS[r.gics_sector] || SECTOR_COLORS['Other'])}>
                    {r.gics_sector}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {open && query.length > 0 && results.length === 0 && !loading && (
        <div className="absolute top-full mt-1 w-full bg-white border border-gray-200
                        rounded-lg shadow-lg z-50 px-4 py-3 text-sm text-gray-500">
          No results for "{query}"
        </div>
      )}
    </div>
  )
}
