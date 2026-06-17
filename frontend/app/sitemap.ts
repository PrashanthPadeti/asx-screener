import { MetadataRoute } from 'next'

export default function sitemap(): MetadataRoute.Sitemap {
  const base = 'https://asxscreener.com.au'
  const now  = new Date()

  return [
    // ── Core pages ────────────────────────────────────────────────────────────
    { url: `${base}/`,          lastModified: now, changeFrequency: 'daily',   priority: 1.0 },
    { url: `${base}/screener`,  lastModified: now, changeFrequency: 'daily',   priority: 0.9 },
    { url: `${base}/market`,    lastModified: now, changeFrequency: 'daily',   priority: 0.8 },
    { url: `${base}/scans`,     lastModified: now, changeFrequency: 'weekly',  priority: 0.8 },
    { url: `${base}/news`,      lastModified: now, changeFrequency: 'daily',   priority: 0.7 },

    // ── Resources ─────────────────────────────────────────────────────────────
    { url: `${base}/glossary`,  lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/learn`,     lastModified: now, changeFrequency: 'weekly',  priority: 0.7 },
    { url: `${base}/learn/what-is-an-asx-stock-screener`,       lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/learn/how-to-research-asx-stocks-dyor`,     lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/asx-stock-research-checklist`,        lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-build-an-asx-watchlist`,       lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/dividend-yield-explained`,            lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/franking-credits-explained`,          lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/key-financial-ratios`,                lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-read-company-announcements`,   lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-screen-asx-stocks-for-beginners`, lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/learn/roe-explained`,                          lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/asx-screener-three-ways-to-search`,      lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/roic-explained`,                          lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-find-asx-growth-stocks`,          lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-use-asx-volume-and-momentum`,     lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-check-asx-dividend-sustainability`, lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/building-an-asx-dividend-portfolio`,             lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-find-asx-dividend-stocks-with-franking`, lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-find-quality-asx-companies`,             lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-screen-for-strong-cash-flow-stocks`,     lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-find-undervalued-asx-stocks`,            lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-asx-screener-ai-query-works`,               lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-use-asx-alpha-screens`,                  lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/dividend-yield-vs-grossed-up-yield`,            lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/best-metrics-for-asx-dividend-investors`,       lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-asx-screener-watchlists-and-alerts-work`,   lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/brokers`,   lastModified: now, changeFrequency: 'monthly', priority: 0.6 },

    // ── Premium Data ──────────────────────────────────────────────────────────
    { url: `${base}/indices`,        lastModified: now, changeFrequency: 'daily',   priority: 0.6 },
    { url: `${base}/funds`,          lastModified: now, changeFrequency: 'daily',   priority: 0.6 },
    { url: `${base}/global-markets`, lastModified: now, changeFrequency: 'daily',   priority: 0.6 },
    { url: `${base}/commodities`,    lastModified: now, changeFrequency: 'daily',   priority: 0.6 },
    { url: `${base}/top5`,           lastModified: now, changeFrequency: 'weekly',  priority: 0.5 },

    // ── Resources ─────────────────────────────────────────────────────────────
    { url: `${base}/resources`,                                      lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/resources/asx-stock-screening-checklist`,        lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/resources/dividend-research-checklist`,          lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/resources/15-minute-asx-market-review-routine`,  lastModified: now, changeFrequency: 'monthly', priority: 0.6 },

    // ── Curated screener pages ────────────────────────────────────────────────
    { url: `${base}/screener/asx-dividend-yield`,  lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/screener/asx-market-cap`,      lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/screener/asx-moving-average`,  lastModified: now, changeFrequency: 'monthly', priority: 0.6 },

    // ── Sector pages ──────────────────────────────────────────────────────────
    { url: `${base}/sectors/materials`,   lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/sectors/financials`,  lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/sectors/healthcare`,  lastModified: now, changeFrequency: 'monthly', priority: 0.7 },

    // ── Trust & transparency ──────────────────────────────────────────────────
    { url: `${base}/disclaimer`,              lastModified: now, changeFrequency: 'monthly', priority: 0.5 },
    { url: `${base}/data-freshness`,          lastModified: now, changeFrequency: 'monthly', priority: 0.5 },
    { url: `${base}/ai-insights-limitations`, lastModified: now, changeFrequency: 'monthly', priority: 0.5 },

    // ── Legal & support ───────────────────────────────────────────────────────
    { url: `${base}/pricing`,  lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/contact`,  lastModified: now, changeFrequency: 'monthly', priority: 0.5 },
    { url: `${base}/terms`,    lastModified: now, changeFrequency: 'monthly', priority: 0.4 },
    { url: `${base}/privacy`,  lastModified: now, changeFrequency: 'monthly', priority: 0.4 },
  ]
}
