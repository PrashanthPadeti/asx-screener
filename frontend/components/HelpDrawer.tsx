'use client'
import { useState, useMemo } from 'react'
import { X, Search, HelpCircle } from 'lucide-react'

// ── Types (exported so pages can build their own content) ─────────────────────

export interface ColumnDef  { name: string; desc: string }
export interface FilterDef  { name: string; desc: string }
export interface SectionDef {
  id:        string
  icon:      string          // emoji — simpler than importing Lucide per section
  iconBg:    string          // tailwind bg class e.g. 'bg-blue-50'
  iconText:  string          // tailwind text class e.g. 'text-blue-600'
  title:     string
  badge?:    string
  summary:   string
  howToUse:  string
  filters?:  FilterDef[]
  columns:   ColumnDef[]
}

// ── Section card ──────────────────────────────────────────────────────────────

function SectionCard({ section, defaultOpen }: { section: SectionDef; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
      >
        <div className={`w-7 h-7 rounded-lg border border-slate-200 flex items-center justify-center flex-shrink-0 ${section.iconBg}`}>
          <span className="text-sm leading-none">{section.icon}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-slate-800">{section.title}</span>
            {section.badge && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-200 text-slate-600 font-medium">
                {section.badge}
              </span>
            )}
          </div>
        </div>
        <span className={`text-slate-400 text-lg leading-none transition-transform duration-200 ${open ? 'rotate-90' : ''}`}>›</span>
      </button>

      {open && (
        <div className="px-4 py-4 space-y-4 bg-white">
          <p className="text-sm text-slate-600 leading-relaxed">{section.summary}</p>

          <div className="bg-blue-50 border border-blue-100 rounded-lg px-3 py-2.5">
            <p className="text-xs font-semibold text-blue-700 mb-1">💡 How to use</p>
            <p className="text-xs text-blue-700 leading-relaxed">{section.howToUse}</p>
          </div>

          {section.filters && section.filters.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Filters</p>
              <div className="space-y-1.5">
                {section.filters.map(f => (
                  <div key={f.name} className="flex gap-2 text-xs">
                    <span className="font-semibold text-slate-700 whitespace-nowrap min-w-[100px]">{f.name}</span>
                    <span className="text-slate-500">{f.desc}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {section.columns.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Columns / Fields</p>
              <div className="space-y-1.5">
                {section.columns.map(c => (
                  <div key={c.name} className="flex gap-2 text-xs">
                    <span className="font-semibold text-slate-700 whitespace-nowrap min-w-[100px]">{c.name}</span>
                    <span className="text-slate-500">{c.desc}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface HelpDrawerProps {
  sections:  SectionDef[]
  title?:    string
  subtitle?: string
}

export function HelpDrawer({
  sections,
  title    = 'Page Guide',
  subtitle = 'What every section and column means',
}: HelpDrawerProps) {
  const [open,  setOpen]  = useState(false)
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim()
    if (!q) return sections
    return sections.filter(s =>
      s.title.toLowerCase().includes(q) ||
      s.summary.toLowerCase().includes(q) ||
      s.columns.some(c => c.name.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q)) ||
      (s.filters ?? []).some(f => f.name.toLowerCase().includes(q) || f.desc.toLowerCase().includes(q))
    )
  }, [query, sections])

  return (
    <>
      {/* Trigger button */}
      <button
        onClick={() => setOpen(true)}
        title="Help — how to read this page"
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 border border-slate-200 rounded-lg hover:bg-amber-50 hover:border-amber-300 hover:text-amber-700 bg-white shadow-sm transition-colors"
      >
        <HelpCircle className="w-4 h-4" />
        Help
      </button>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Drawer */}
      <div
        className={`fixed top-0 right-0 h-full w-full max-w-md bg-white z-50 shadow-2xl flex flex-col transition-transform duration-300 ease-in-out ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-gradient-to-r from-amber-50 to-orange-50 flex-shrink-0">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-amber-600" />
            <div>
              <h2 className="text-base font-bold text-slate-900">{title}</h2>
              <p className="text-xs text-slate-500">{subtitle}</p>
            </div>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-200 text-slate-500 hover:text-slate-700 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-3 border-b border-slate-100 flex-shrink-0">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search sections, columns, filters…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="w-full pl-8 pr-8 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent bg-slate-50"
            />
            {query && (
              <button onClick={() => setQuery('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          {query && (
            <p className="text-xs text-slate-400 mt-1.5 px-1">
              {filtered.length === 0
                ? 'No matches found'
                : `${filtered.length} section${filtered.length !== 1 ? 's' : ''} matched`}
            </p>
          )}
        </div>

        {/* Sections */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-slate-400">
              <Search className="w-8 h-8 mb-2 opacity-40" />
              <p className="text-sm">Nothing found for &ldquo;{query}&rdquo;</p>
            </div>
          ) : (
            filtered.map(s => (
              <SectionCard key={s.id} section={s} defaultOpen={filtered.length === 1} />
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-100 bg-slate-50 flex-shrink-0">
          <p className="text-xs text-slate-400 text-center">
            Data refreshed nightly · ASX trading hours 10am–4pm AEST
          </p>
        </div>
      </div>
    </>
  )
}
