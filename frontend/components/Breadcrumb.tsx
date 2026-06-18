import Link from 'next/link'
import { ChevronRight } from 'lucide-react'

interface Crumb {
  label: string
  href: string
}

interface BreadcrumbProps {
  crumbs: Crumb[]
  theme?: 'light' | 'dark'
}

export default function Breadcrumb({ crumbs, theme = 'light' }: BreadcrumbProps) {
  const all = [{ label: 'Home', href: '/' }, ...crumbs]
  const isDark = theme === 'dark'

  const schema = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: all.map((c, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: c.label,
      item: `https://asxscreener.com.au${c.href}`,
    })),
  }

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />
      <nav aria-label="Breadcrumb">
        <ol className="flex flex-wrap items-center gap-1 text-sm text-slate-500">
          {all.map((crumb, i) => {
            const isLast = i === all.length - 1
            return (
              <li key={crumb.href} className="flex items-center gap-1">
                {i > 0 && <ChevronRight className={`w-3.5 h-3.5 shrink-0 ${isDark ? 'text-slate-600' : 'text-slate-300'}`} />}
                {isLast ? (
                  <span className={`font-medium ${isDark ? 'text-slate-200' : 'text-slate-700'}`} aria-current="page">{crumb.label}</span>
                ) : (
                  <Link href={crumb.href} className={`transition-colors ${isDark ? 'hover:text-blue-400' : 'hover:text-blue-600'}`}>
                    {crumb.label}
                  </Link>
                )}
              </li>
            )
          })}
        </ol>
      </nav>
    </>
  )
}
