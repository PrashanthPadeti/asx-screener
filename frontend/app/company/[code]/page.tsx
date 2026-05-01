import { getCompany } from '@/lib/api'
import { formatNumber, cn, SECTOR_COLORS } from '@/lib/utils'
import { Globe, Building2, Users, Calendar, ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import CompanyTabs from './CompanyTabs'

export default async function CompanyPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  let company
  try {
    company = await getCompany(code.toUpperCase())
  } catch {
    notFound()
  }

  const sectorColor = company.gics_sector
    ? SECTOR_COLORS[company.gics_sector] || SECTOR_COLORS['Other']
    : SECTOR_COLORS['Other']

  return (
    <div className="space-y-5 max-w-5xl">

      {/* Back */}
      <Link href="/screener" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800">
        <ArrowLeft className="w-4 h-4" /> Back to Screener
      </Link>

      {/* Header card */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="font-mono font-bold text-2xl text-blue-600">{company.asx_code}</span>
              {company.is_reit  && <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-medium">REIT</span>}
              {company.is_miner && <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full font-medium">Miner</span>}
              {company.is_asx200 && <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">ASX 200</span>}
            </div>
            <h1 className="text-2xl font-bold text-gray-900">{company.company_name}</h1>
            <div className="flex items-center gap-3 mt-2 flex-wrap">
              {company.gics_sector && (
                <span className={cn('text-sm px-2.5 py-1 rounded-full font-medium', sectorColor)}>
                  {company.gics_sector}
                </span>
              )}
              {company.gics_industry_group && (
                <span className="text-sm text-gray-500">{company.gics_industry_group}</span>
              )}
            </div>
          </div>

          {company.website && (
            <a href={company.website} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800 border border-blue-200 px-3 py-1.5 rounded-lg hover:bg-blue-50">
              <Globe className="w-4 h-4" />
              Website
            </a>
          )}
        </div>

        {company.description && (
          <p className="mt-4 text-sm text-gray-600 leading-relaxed border-t border-gray-100 pt-4">
            {company.description}
          </p>
        )}
      </div>

      {/* Key info grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'ASX Code',     value: company.asx_code,     icon: Building2 },
          { label: 'Domicile',     value: company.domicile || 'Australia', icon: Globe },
          { label: 'Employees',    value: company.employee_count ? formatNumber(company.employee_count, 0) : '—', icon: Users },
          { label: 'Listed',       value: company.listing_date || '—', icon: Calendar },
        ].map(item => (
          <div key={item.label} className="bg-white border border-gray-200 rounded-xl p-4">
            <div className="flex items-center gap-2 text-gray-400 mb-1">
              <item.icon className="w-3.5 h-3.5" />
              <span className="text-xs uppercase tracking-wide font-medium">{item.label}</span>
            </div>
            <div className="font-semibold text-gray-900">{item.value}</div>
          </div>
        ))}
      </div>

      {/* Share structure */}
      {(company.shares_outstanding || company.abn) && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h2 className="font-semibold text-gray-900 mb-4">Share Structure</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {company.shares_outstanding && (
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Shares Outstanding</div>
                <div className="font-semibold text-gray-900">{formatNumber(company.shares_outstanding)}</div>
              </div>
            )}
            {company.abn && (
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">ABN</div>
                <div className="font-semibold text-gray-900">{company.abn}</div>
              </div>
            )}
            {company.primary_commodity && (
              <div>
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Primary Commodity</div>
                <div className="font-semibold text-gray-900">{company.primary_commodity}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Live tabs — Overview, Financials, Technicals */}
      <CompanyTabs code={code} />

    </div>
  )
}
