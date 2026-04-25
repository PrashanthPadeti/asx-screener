import { Star } from 'lucide-react'
import Link from 'next/link'

export default function WatchlistPage() {
  return (
    <div className="max-w-2xl mx-auto text-center py-20">
      <div className="inline-flex items-center justify-center w-16 h-16 bg-yellow-50 rounded-full mb-4">
        <Star className="w-8 h-8 text-yellow-500" />
      </div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Watchlist</h1>
      <p className="text-gray-500 mb-6">
        Sign in to save stocks to your watchlist and get price alerts.
      </p>
      <div className="flex gap-3 justify-center">
        <Link href="/screener"
          className="px-5 py-2.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors">
          Open Screener
        </Link>
        <Link href="/"
          className="px-5 py-2.5 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition-colors">
          Back to Home
        </Link>
      </div>
    </div>
  )
}
