/**
 * useWatchlist — localStorage-based watchlist hook.
 *
 * Stores a simple ordered list of ASX codes.  No auth required.
 * State starts empty on SSR; populated from localStorage after hydration.
 */
import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'asx_watchlist_v1'
const MAX_ITEMS   = 50

export interface WatchlistState {
  codes:     string[]
  count:     number
  mounted:   boolean                     // false during SSR / before hydration
  isWatched: (code: string) => boolean
  toggle:    (code: string) => void
  remove:    (code: string) => void
  clear:     () => void
}

export function useWatchlist(): WatchlistState {
  const [codes,   setCodes]   = useState<string[]>([])
  const [mounted, setMounted] = useState(false)

  // Hydrate from localStorage once on client mount
  useEffect(() => {
    setMounted(true)
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) setCodes(parsed.filter(c => typeof c === 'string'))
      }
    } catch {
      // ignore parse errors
    }
  }, [])

  // Persist to localStorage on every change (skip the initial SSR empty state)
  useEffect(() => {
    if (!mounted) return
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(codes))
    } catch {
      // ignore quota errors
    }
  }, [codes, mounted])

  const toggle = useCallback((code: string) => {
    setCodes(prev =>
      prev.includes(code)
        ? prev.filter(c => c !== code)
        : prev.length >= MAX_ITEMS ? prev : [...prev, code]
    )
  }, [])

  const remove = useCallback((code: string) => {
    setCodes(prev => prev.filter(c => c !== code))
  }, [])

  const clear = useCallback(() => setCodes([]), [])

  const isWatched = useCallback((code: string) => codes.includes(code), [codes])

  return { codes, count: codes.length, mounted, isWatched, toggle, remove, clear }
}
