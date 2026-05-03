import { formatNumber, cn, SECTOR_COLORS } from '@/lib/utils'
import { Globe, Building2, Users, Calendar, ArrowLeft, ExternalLink } from 'lucide-react'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import CompanyTabs from './CompanyTabs'
import WatchlistButton from '@/components/WatchlistButton'

// Server-side fetch uses internal URL (avoids routing through public IP)
const INTERNAL_API = process.env.INTERNAL_API_URL || 'http://localhost:8000'

export default async function CompanyPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  let company
  try {
    const res = await fetch(`${INTERNAL_API}/api/v1/companies/${code.toUpperCase()}`, {
      cache: 'no-store',
    })
    if (!res.ok) notFound()
    company = await res.json()
  } catch {
    notFound()
  }

  return (
    <div className="space-y-4 max-w-5xl">

      {/* Back */}
      <Link href="/screener"
        className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-600 transition-colors group">
        <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-0.5 transition-transform" />
        Back to Screener
      </Link>

      {/* ── Hero Header ───────────────────────────────────────── */}
      <div className="relative bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 rounded-2xl overflow-hidden border border-white/10">
        {/* Decorative glows */}
        <div className="absolute -top-32 -right-32 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-96 h-96 bg-indigo-600/8 rounded-full blur-3xl pointer-events-none" />

        <div className="relative p-6">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex-1 min-w-0">

              {/* Code + badges */}
              <div className="flex items-center gap-3 mb-2 flex-wrap">
                <span className="font-mono font-black text-3xl bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent tracking-tight">
                  {company.asx_code}
                </span>
                <WatchlistButton code={company.asx_code} size="md" />
                {company.is_reit && (
                  <span className="text-xs bg-indigo-500/20 text-indigo-300 border border-indigo-400/30 px-2.5 py-0.5 rounded-full font-semibold tracking-wide">
                    REIT
                  </span>
                )}
                {company.is_miner && (
                  <span className="text-xs bg-amber-500/20 text-amber-300 border border-amber-400/30 px-2.5 py-0.5 rounded-full font-semibold tracking-wide">
                    MINER
                  </span>
                )}
                {company.is_asx200 && (
                  <span className="text-xs bg-blue-500/20 text-blue-300 border border-blue-400/30 px-2.5 py-0.5 rounded-full font-semibold tracking-wide">
                    ASX 200
                  </span>
                )}
              </div>

              {/* Company name */}
              <h1 className="text-xl font-bold text-white mb-2 leading-tight">
                {company.company_name}
              </h1>

              {/* Sector / Industry */}
              <div className="flex items-center gap-2 flex-wrap">
                {company.gics_sector && (
                  <span className="text-xs bg-white/10 text-slate-300 border border-white/10 px-2.5 py-1 rounded-full font-medium">
                    {company.gics_sector}
                  </span>
                )}
                {company.gics_industry_group && (
                  <span className="text-xs text-slate-400">{company.gics_industry_group}</span>
                )}
              </div>
            </div>

            {company.website && (
              <a href={company.website} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300
                           border border-blue-500/30 hover:border-blue-400/50
                           bg-blue-500/10 hover:bg-blue-500/20
                           px-3 py-1.5 rounded-lg transition-all shrink-0">
                <Globe className="w-3.5 h-3.5" />
                Website
                <ExternalLink className="w-3 h-3 opacity-60" />
              </a>
            )}
          </div>

          {company.description && (
            <p className="mt-4 text-sm text-slate-400 leading-relaxed border-t border-white/10 pt-4 line-clamp-2">
              {company.description}
            </p>
          )}
        </div>
      </div>

      {/* ── Key Info Grid ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'ASX Code',  value: company.asx_code,                                             icon: Building2 },
          { label: 'Domicile',  value: company.domicile || 'Australia',                              icon: Globe },
          { label: 'Employees', value: company.employee_count ? formatNumber(company.employee_count, 0) : '—', icon: Users },
          { label: 'Listed',    value: company.listing_date || '—',                                  icon: Calendar },
        ].map(item => (
          <div key={item.label}
            className="bg-white border border-gray-100 rounded-xl p-4 hover:border-blue-200 hover:shadow-sm transition-all duration-200">
            <div className="flex items-center gap-1.5 text-gray-400 mb-1.5">
              <item.icon className="w-3 h-3" />
              <span className="text-xs uppercase tracking-widest font-semibold">{item.label}</span>
            </div>
            <div className="font-bold text-gray-900 text-sm">{item.value}</div>
          </div>
        ))}
      </div>

      {/* ── Share Structure ───────────────────────────────────── */}
      {(company.shares_outstanding || company.abn) && (
        <div className="bg-white border border-gray-100 rounded-xl p-5">
          <h2 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Share Structure</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {company.shares_outstanding && (
              <div>
                <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Shares Outstanding</div>
                <div className="font-bold text-gray-900">{formatNumber(company.shares_outstanding)}</div>
              </div>
            )}
            {company.abn && (
              <div>
                <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">ABN</div>
                <div className="font-bold text-gray-900">{company.abn}</div>
              </div>
            )}
            {company.primary_commodity && (
              <div>
                <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Primary Commodity</div>
                <div className="font-bold text-gray-900">{company.primary_commodity}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tabs ──────────────────────────────────────────────── */}
      <CompanyTabs code={code} />

    </div>
  )
}
