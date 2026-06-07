'use client'
import { useEffect, useState } from 'react'
import { getMarketSectors, SectorStat } from '@/lib/api'
import { SECTORS, SECTOR_COLORS } from '@/lib/utils'
import { BarChart3, AlertCircle, Loader2 } from 'lucide-react'

interface BrowseSectorsProps {
  onSectorSelect: (sector: string) => void
  selectedSector?: string
}

export default function BrowseSectors({ onSectorSelect, selectedSector }: BrowseSectorsProps) {
  const [sectors, setSectors] = useState<SectorStat[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchSectors = async () => {
      try {
        setLoading(true)
        setError(null)
        const response = await getMarketSectors()
        setSectors(response.sectors || [])
      } catch (err) {
        setError('Failed to load sectors')
        console.error('Sector fetch error:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchSectors()
  }, [])

  if (loading) {
    return (
      <div className="w-64 bg-white border-l border-gray-200 p-4 flex items-center justify-center min-h-screen">
        <Loader2 className="animate-spin text-gray-400" size={24} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="w-64 bg-white border-l border-gray-200 p-4">
        <div className="flex items-start gap-2 text-sm text-red-600 bg-red-50 p-3 rounded">
          <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
          <p>{error}</p>
        </div>
      </div>
    )
  }

  // Create a map of sector -> stats for quick lookup
  const sectorMap = new Map(sectors.map(s => [s.sector, s]))

  return (
    <div className="w-64 bg-white border-l border-gray-200 sticky top-0 h-screen overflow-y-auto">
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 size={20} className="text-blue-600" />
          <h2 className="font-bold text-gray-900">Browse Sectors</h2>
        </div>

        {/* Sectors Grid */}
        <div className="space-y-2">
          {SECTORS.map((sector) => {
            const stats = sectorMap.get(sector)
            const count = stats?.stock_count || 0
            const isSelected = selectedSector === sector
            const bgColor = SECTOR_COLORS[sector as keyof typeof SECTOR_COLORS] || 'bg-gray-100'

            return (
              <button
                key={sector}
                onClick={() => onSectorSelect(sector)}
                className={`w-full text-left p-3 rounded-lg transition-all ${
                  isSelected
                    ? 'ring-2 ring-blue-500 bg-blue-50 border border-blue-200'
                    : 'bg-gray-50 hover:bg-gray-100 border border-gray-200'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-semibold ${isSelected ? 'text-blue-900' : 'text-gray-900'}`}>
                      {sector}
                    </p>
                    <p className="text-xs text-gray-600 mt-0.5">
                      {count.toLocaleString()} stock{count !== 1 ? 's' : ''}
                    </p>
                  </div>
                  {isSelected && (
                    <div className={`${bgColor} w-2 h-2 rounded-full flex-shrink-0 mt-1.5`} />
                  )}
                </div>

                {/* Optional: Show market cap if available */}
                {stats?.total_market_cap_bn !== undefined && stats.total_market_cap_bn !== null && stats.total_market_cap_bn > 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    AUD ${stats.total_market_cap_bn.toFixed(0)}B
                  </p>
                )}
              </button>
            )
          })}
        </div>

        {/* Info Footer */}
        <div className="mt-6 pt-4 border-t border-gray-200 text-xs text-gray-500">
          Click a sector to filter the screener
        </div>
      </div>
    </div>
  )
}
