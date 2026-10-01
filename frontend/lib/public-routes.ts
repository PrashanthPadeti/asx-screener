/**
 * Which routes are reachable without an account — declared once.
 *
 * Two consumers must agree about this and previously did not:
 *
 *   components/ClientGuard.tsx  decides who is redirected to the login form
 *   app/sitemap.ts              tells search engines which URLs to index
 *
 * Until 2 Oct 2026 ClientGuard treated everything except '/' and '/auth/' as
 * private while the sitemap advertised 58 URLs, so a visitor arriving from
 * Google on "what is an asx stock screener" met a password prompt. Opening the
 * content pages fixed most of that; the remaining contradiction was the nine
 * product routes still listed as indexable targets that gate on arrival.
 *
 * This module is the single source. The sitemap stays an explicit list rather
 * than being generated from this one, because a derived sitemap would make a
 * route silently vanish from search when someone gated it — the failure would
 * be invisible, which is the shape of defect this codebase keeps finding. A
 * test asserts the two agree instead, so divergence fails loudly.
 *
 * Product surfaces stay gated by decision: /screener, /market, /scans, /news,
 * /top5, /indices, /funds, /commodities, /global-markets.
 */
export const PUBLIC_PREFIXES = [
  '/auth/',
  '/learn',
  '/resources',
  '/pricing',
  '/data-freshness',
  '/ai-insights-limitations',
  '/brokers',
  '/glossary',
  '/terms',
  '/privacy',
  '/disclaimer',
  '/unsubscribe',
  '/contact',
  '/sectors',

  // SEO landing pages that live under /screener but are not the screener.
  // Each is a server component with its own metadata and canonical URL.
  // Named individually so the product route /screener stays gated.
  '/screener/asx-dividend-yield',
  '/screener/asx-market-cap',
  '/screener/asx-moving-average',
]

export function isPublic(pathname: string): boolean {
  if (pathname === '/') return true
  return PUBLIC_PREFIXES.some(prefix => pathname.startsWith(prefix))
}
