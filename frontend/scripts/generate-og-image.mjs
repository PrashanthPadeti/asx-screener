import sharp from 'sharp'
import { writeFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const outPath = join(__dirname, '..', 'public', 'og-image.png')

const svg = `<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1200" y2="630" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e3a5f"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="300" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#6366f1"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="630" fill="url(#bg)"/>

  <!-- Subtle grid lines -->
  <g opacity="0.04" stroke="#ffffff" stroke-width="1">
    <line x1="0" y1="105" x2="1200" y2="105"/>
    <line x1="0" y1="210" x2="1200" y2="210"/>
    <line x1="0" y1="315" x2="1200" y2="315"/>
    <line x1="0" y1="420" x2="1200" y2="420"/>
    <line x1="0" y1="525" x2="1200" y2="525"/>
    <line x1="200" y1="0" x2="200" y2="630"/>
    <line x1="400" y1="0" x2="400" y2="630"/>
    <line x1="600" y1="0" x2="600" y2="630"/>
    <line x1="800" y1="0" x2="800" y2="630"/>
    <line x1="1000" y1="0" x2="1000" y2="630"/>
  </g>

  <!-- Left accent bar -->
  <rect x="72" y="160" width="5" height="200" rx="3" fill="url(#accent)"/>

  <!-- Brand name -->
  <text x="100" y="248" font-family="'Helvetica Neue', Arial, sans-serif" font-size="72" font-weight="700" fill="#ffffff" letter-spacing="-2">ASX Screener</text>

  <!-- Tagline -->
  <text x="100" y="308" font-family="'Helvetica Neue', Arial, sans-serif" font-size="30" font-weight="400" fill="#94a3b8">Australian Stock Screener &amp; Research Platform</text>

  <!-- Feature pills -->
  <g transform="translate(100, 355)">
    <!-- Pill 1 -->
    <rect x="0" y="0" width="220" height="42" rx="21" fill="#1e40af" opacity="0.6"/>
    <text x="110" y="27" font-family="'Helvetica Neue', Arial, sans-serif" font-size="16" font-weight="500" fill="#93c5fd" text-anchor="middle">80+ Metrics</text>
    <!-- Pill 2 -->
    <rect x="236" y="0" width="230" height="42" rx="21" fill="#1e40af" opacity="0.6"/>
    <text x="351" y="27" font-family="'Helvetica Neue', Arial, sans-serif" font-size="16" font-weight="500" fill="#93c5fd" text-anchor="middle">Franking Credits</text>
    <!-- Pill 3 -->
    <rect x="482" y="0" width="200" height="42" rx="21" fill="#1e40af" opacity="0.6"/>
    <text x="582" y="27" font-family="'Helvetica Neue', Arial, sans-serif" font-size="16" font-weight="500" fill="#93c5fd" text-anchor="middle">AI Insights</text>
  </g>

  <!-- Right panel — metric cards -->
  <g transform="translate(820, 120)">
    <!-- Card bg -->
    <rect x="0" y="0" width="320" height="390" rx="16" fill="#ffffff" opacity="0.05"/>
    <rect x="0" y="0" width="320" height="390" rx="16" fill="none" stroke="#334155" stroke-width="1"/>

    <!-- Card header -->
    <text x="20" y="35" font-family="'Helvetica Neue', Arial, sans-serif" font-size="13" font-weight="500" fill="#64748b">SAMPLE SCREEN RESULTS</text>

    <!-- Row 1 -->
    <rect x="12" y="48" width="296" height="56" rx="8" fill="#0f172a" opacity="0.5"/>
    <text x="28" y="73" font-family="'Helvetica Neue', Arial, sans-serif" font-size="15" font-weight="600" fill="#f1f5f9">CBA</text>
    <text x="28" y="93" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b">Commonwealth Bank</text>
    <text x="255" y="73" font-family="'Helvetica Neue', Arial, sans-serif" font-size="14" font-weight="600" fill="#34d399" text-anchor="end">5.4%</text>
    <text x="308" y="73" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b" text-anchor="end">yield</text>

    <!-- Row 2 -->
    <rect x="12" y="112" width="296" height="56" rx="8" fill="#0f172a" opacity="0.5"/>
    <text x="28" y="137" font-family="'Helvetica Neue', Arial, sans-serif" font-size="15" font-weight="600" fill="#f1f5f9">BHP</text>
    <text x="28" y="157" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b">BHP Group</text>
    <text x="255" y="137" font-family="'Helvetica Neue', Arial, sans-serif" font-size="14" font-weight="600" fill="#34d399" text-anchor="end">6.1%</text>
    <text x="308" y="137" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b" text-anchor="end">yield</text>

    <!-- Row 3 -->
    <rect x="12" y="176" width="296" height="56" rx="8" fill="#0f172a" opacity="0.5"/>
    <text x="28" y="201" font-family="'Helvetica Neue', Arial, sans-serif" font-size="15" font-weight="600" fill="#f1f5f9">ANZ</text>
    <text x="28" y="221" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b">ANZ Banking Group</text>
    <text x="255" y="201" font-family="'Helvetica Neue', Arial, sans-serif" font-size="14" font-weight="600" fill="#34d399" text-anchor="end">6.8%</text>
    <text x="308" y="201" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b" text-anchor="end">yield</text>

    <!-- Row 4 -->
    <rect x="12" y="240" width="296" height="56" rx="8" fill="#0f172a" opacity="0.5"/>
    <text x="28" y="265" font-family="'Helvetica Neue', Arial, sans-serif" font-size="15" font-weight="600" fill="#f1f5f9">WBC</text>
    <text x="28" y="285" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b">Westpac Banking</text>
    <text x="255" y="265" font-family="'Helvetica Neue', Arial, sans-serif" font-size="14" font-weight="600" fill="#34d399" text-anchor="end">7.2%</text>
    <text x="308" y="265" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b" text-anchor="end">yield</text>

    <!-- Divider -->
    <line x1="12" y1="312" x2="308" y2="312" stroke="#1e293b" stroke-width="1"/>

    <!-- Stats row -->
    <text x="28" y="340" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b">Filters active</text>
    <text x="28" y="360" font-family="'Helvetica Neue', Arial, sans-serif" font-size="16" font-weight="600" fill="#60a5fa">4</text>
    <text x="130" y="340" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b">Stocks matched</text>
    <text x="130" y="360" font-family="'Helvetica Neue', Arial, sans-serif" font-size="16" font-weight="600" fill="#60a5fa">18</text>
    <text x="232" y="340" font-family="'Helvetica Neue', Arial, sans-serif" font-size="12" fill="#64748b">100% franked</text>
    <text x="232" y="360" font-family="'Helvetica Neue', Arial, sans-serif" font-size="16" font-weight="600" fill="#60a5fa">14</text>
  </g>

  <!-- Bottom bar -->
  <rect x="0" y="568" width="1200" height="62" fill="#0f172a" opacity="0.6"/>
  <text x="100" y="606" font-family="'Helvetica Neue', Arial, sans-serif" font-size="18" fill="#475569">asxscreener.com.au</text>
  <text x="1100" y="606" font-family="'Helvetica Neue', Arial, sans-serif" font-size="16" fill="#3b82f6" text-anchor="end">Free to use · No signup required</text>
</svg>`

const buf = await sharp(Buffer.from(svg)).png({ quality: 95 }).toBuffer()
writeFileSync(outPath, buf)
console.log(`og-image.png written → ${outPath} (${(buf.length / 1024).toFixed(1)} KB)`)
