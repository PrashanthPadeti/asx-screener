'use client'

import { Star } from 'lucide-react'
import { useWatchlist } from '@/lib/watchlist'
import { cn } from '@/lib/utils'

interface Props {
  code:  string
  size?: 'sm' | 'md'
  className?: string
}

/**
 * Star button that toggles a stock in/out of the localStorage watchlist.
 * Renders as "not watched" during SSR; updates after hydration.
 */
export default function WatchlistButton({ code, size = 'md', className }: Props) {
  const { isWatched, toggle, mounted } = useWatchlist()

  // Don't show until hydrated to avoid flash of wrong state
  if (!mounted) {
    return (
      <div className={cn(
        'rounded-full opacity-0',
        size === 'sm' ? 'w-6 h-6' : 'w-8 h-8',
        className,
      )} />
    )
  }

  const watched = isWatched(code)

  return (
    <button
      onClick={e => { e.preventDefault(); e.stopPropagation(); toggle(code) }}
      title={watched ? `Remove ${code} from watchlist` : `Add ${code} to watchlist`}
      aria-label={watched ? `Remove ${code} from watchlist` : `Add ${code} to watchlist`}
      aria-pressed={watched}
      className={cn(
        'rounded-full flex items-center justify-center transition-all',
        size === 'sm'
          ? 'w-6 h-6 hover:bg-yellow-50'
          : 'w-8 h-8 hover:bg-yellow-50',
        watched
          ? 'text-yellow-400'
          : 'text-gray-300 hover:text-yellow-400',
        className,
      )}
    >
      <Star
        className={cn(
          size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4',
          watched ? 'fill-yellow-400' : '',
        )}
      />
    </button>
  )
}
