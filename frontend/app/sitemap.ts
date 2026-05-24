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
    { url: `${base}/learn/franking-credits-explained`,          lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/key-financial-ratios`,                lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/learn/how-to-read-company-announcements`,   lastModified: now, changeFrequency: 'monthly', priority: 0.6 },
    { url: `${base}/brokers`,   lastModified: now, changeFrequency: 'monthly', priority: 0.6 },

    // ── Premium Data ──────────────────────────────────────────────────────────
    { url: `${base}/indices`,        lastModified: now, changeFrequency: 'daily',   priority: 0.6 },
    { url: `${base}/funds`,          lastModified: now, changeFrequency: 'daily',   priority: 0.6 },
    { url: `${base}/global-markets`, lastModified: now, changeFrequency: 'daily',   priority: 0.6 },
    { url: `${base}/commodities`,    lastModified: now, changeFrequency: 'daily',   priority: 0.6 },
    { url: `${base}/top5`,           lastModified: now, changeFrequency: 'weekly',  priority: 0.5 },

    // ── Legal & support ───────────────────────────────────────────────────────
    { url: `${base}/pricing`,  lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    { url: `${base}/contact`,  lastModified: now, changeFrequency: 'monthly', priority: 0.5 },
    { url: `${base}/terms`,    lastModified: now, changeFrequency: 'monthly', priority: 0.4 },
    { url: `${base}/privacy`,  lastModified: now, changeFrequency: 'monthly', priority: 0.4 },
  ]
}
