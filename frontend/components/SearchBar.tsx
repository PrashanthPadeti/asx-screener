'use client'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Search } from 'lucide-react'
import { searchCompanies, type SearchResult } from '@/lib/api'
import { cn, SECTOR_COLORS } from '@/lib/utils'

export default function SearchBar() {
  const [query,     setQuery]     = useState('')
  const [results,   setResults]   = useState<SearchResult[]>([])
  const [loading,   setLoading]   = useState(false)
  const [open,      setOpen]      = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)   // keyboard-highlighted row

  const router    = useRouter()
  const wrapRef   = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLInputElement>(null)
  const timerRef  = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounced search
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (query.length < 1) { setResults([]); setOpen(false); setActiveIdx(-1); return }

    timerRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const data = await searchCompanies(query)
        setResults(data)
        setOpen(true)
        setActiveIdx(-1)
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 200)
  }, [query])

  // Click outside → close
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false)
        setActiveIdx(-1)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = useCallback((code: string) => {
    setQuery('')
    setOpen(false)
    setActiveIdx(-1)
    router.push(`/company/${code}`)
  }, [router])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || results.length === 0) {
      if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur() }
      return
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setActiveIdx(i => Math.min(i + 1, results.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setActiveIdx(i => Math.max(i - 1, -1))
        break
      case 'Enter':
        e.preventDefault()
        if (activeIdx >= 0 && results[activeIdx]) {
          handleSelect(results[activeIdx].asx_code)
        } else if (results[0]) {
          handleSelect(results[0].asx_code)
        }
        break
      case 'Escape':
        setOpen(false)
        setActiveIdx(-1)
        inputRef.current?.blur()
        break
    }
  }, [open, results, activeIdx, handleSelect])

  return (
    <div ref={wrapRef} className="relative w-full">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search stocks… (BHP, Commonwealth Bank)"
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          aria-activedescendant={activeIdx >= 0 ? `search-result-${activeIdx}` : undefined}
          className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                     bg-gray-50 placeholder:text-gray-400"
        />
        {loading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 w-3 h-3
                          border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        )}
      </div>

      {/* Dropdown */}
      {open && results.length > 0 && (
        <div
          role="listbox"
          className="absolute top-full mt-1 w-full bg-white border border-gray-200
                     rounded-lg shadow-lg z-50 overflow-hidden max-h-72 overflow-y-auto"
        >
          {results.map((r, idx) => (
            <button
              key={r.asx_code}
              id={`search-result-${idx}`}
              role="option"
              aria-selected={idx === activeIdx}
              onMouseEnter={() => setActiveIdx(idx)}
              onClick={() => handleSelect(r.asx_code)}
              className={cn(
                'w-full flex items-center justify-between px-4 py-2.5 transition-colors text-left',
                idx === activeIdx ? 'bg-blue-50' : 'hover:bg-gray-50',
              )}
            >
              <div className="flex items-center gap-3">
                <span className="font-mono font-bold text-blue-700 text-sm w-14 shrink-0">
                  {r.asx_code}
                </span>
                <span className="text-sm text-gray-800 truncate max-w-[180px]">
                  {r.company_name}
                </span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0 ml-2">
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
          <div className="px-4 py-1.5 text-xs text-gray-400 border-t border-gray-100 bg-gray-50">
            ↑↓ navigate · Enter select · Esc close
          </div>
        </div>
      )}

      {/* No results */}
      {open && query.length > 0 && results.length === 0 && !loading && (
        <div className="absolute top-full mt-1 w-full bg-white border border-gray-200
                        rounded-lg shadow-lg z-50 px-4 py-3 text-sm text-gray-500">
          No results for &ldquo;{query}&rdquo;
        </div>
      )}
    </div>
  )
}
