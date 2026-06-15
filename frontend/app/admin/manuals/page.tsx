'use client'
import { useState } from 'react'
import { BookOpen, ChevronRight, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Reusable content primitives ───────────────────────────────────────────────
const H2 = ({ id, children }: { id: string; children: React.ReactNode }) => (
  <h2 id={id} className="text-lg font-bold text-slate-900 mt-10 mb-3 pb-2 border-b border-slate-200 scroll-mt-24">{children}</h2>
)
const H3 = ({ children }: { children: React.ReactNode }) => (
  <h3 className="text-sm font-semibold text-slate-800 mt-5 mb-2">{children}</h3>
)
const P = ({ children }: { children: React.ReactNode }) => (
  <p className="text-sm text-slate-600 leading-relaxed mb-3">{children}</p>
)
const UL = ({ items }: { items: React.ReactNode[] }) => (
  <ul className="list-disc pl-5 space-y-1.5 text-sm text-slate-600 mb-3">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
)
const OL = ({ items }: { items: React.ReactNode[] }) => (
  <ol className="list-decimal pl-5 space-y-1.5 text-sm text-slate-600 mb-3">{items.map((x, i) => <li key={i}>{x}</li>)}</ol>
)
const Callout = ({ tone = 'blue', title, children }: { tone?: 'blue' | 'amber' | 'green' | 'red'; title?: string; children: React.ReactNode }) => {
  const map = { blue: 'bg-blue-50 border-blue-200 text-blue-900', amber: 'bg-amber-50 border-amber-200 text-amber-900', green: 'bg-green-50 border-green-200 text-green-900', red: 'bg-red-50 border-red-200 text-red-900' }
  return <div className={cn('border rounded-lg p-3 text-sm mb-3', map[tone])}>{title && <p className="font-semibold mb-1">{title}</p>}<div className="leading-relaxed">{children}</div></div>
}
const Table = ({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) => (
  <div className="overflow-x-auto mb-4 border border-slate-200 rounded-lg">
    <table className="w-full text-sm">
      <thead className="bg-slate-50"><tr>{head.map((h, i) => <th key={i} className="text-left font-semibold text-slate-700 px-3 py-2 border-b border-slate-200">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className={i % 2 ? 'bg-slate-50/50' : ''}>{r.map((c, j) => <td key={j} className="px-3 py-2 align-top text-slate-600 border-b border-slate-100">{c}</td>)}</tr>)}</tbody>
    </table>
  </div>
)
const Code = ({ children }: { children: React.ReactNode }) => <code className="text-[12px] font-mono bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded">{children}</code>

// ── Table of contents ─────────────────────────────────────────────────────────
const TOC = [
  ['overview', '1. Page Overview'],
  ['benefits', '2. User Benefits'],
  ['sections', '3. Sections Covered'],
  ['data', '4. How to Understand the Data'],
  ['metrics', '5. Metrics & Data Shown'],
  ['features', '6. Functional Features'],
  ['technical', '7. Technical Details'],
  ['examples', '8. Data Interpretation Examples'],
  ['support', '9. Quick Reference (Support)'],
  ['future', '10. Future Improvements'],
]

// ── Market Overview manual ────────────────────────────────────────────────────
function MarketOverviewManual() {
  return (
    <div>
      {/* TOC */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-6">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">On this page</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1">
          {TOC.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="text-sm text-blue-600 hover:underline">{label}</a>
          ))}
        </div>
      </div>

      {/* 1. OVERVIEW */}
      <H2 id="overview">1. Page Overview</H2>
      <H3>What is the Market Overview Page?</H3>
      <P>The <strong>Market Overview</strong> page (<Code>/market</Code>) is the “front door” to the whole ASX. Instead of looking at one stock at a time, it gives a single bird’s-eye view of how the entire market is behaving <em>today</em> — which sectors are up or down, which stocks are moving the most, where money is flowing, and which stocks are doing something unusual.</P>
      <H3>Purpose</H3>
      <P>To answer the question every trader and investor asks first: <strong>“What’s happening in the market right now, and what should I look at?”</strong> It surfaces the most interesting stocks and sectors automatically, so the user doesn’t have to manually scan 2,500 ASX names.</P>
      <H3>What problem it solves</H3>
      <UL items={[
        <><strong>Information overload</strong> — the ASX has ~2,500 listed stocks. This page distils that into a handful of ranked, colour-coded views.</>,
        <><strong>Missed moves</strong> — top gainers/losers, volume surges and 52-week breakouts are flagged automatically so nothing big slips past.</>,
        <><strong>Slow research start</strong> — every item links straight into the Screener or Company page, turning “something’s moving” into deeper research in one click.</>,
      ]} />
      <H3>How it fits into the platform</H3>
      <P>Market Overview is the <strong>discovery</strong> layer. The typical flow is: <strong>Market Overview</strong> (spot something interesting) → <strong>Screener</strong> (find similar stocks with filters) → <strong>Company Detail</strong> (deep-dive one stock) → <strong>Watchlist / Alerts</strong> (track it). It sits alongside the Screener and Alpha Screens in the top navigation.</P>

      {/* 2. BENEFITS */}
      <H2 id="benefits">2. User Benefits</H2>
      <Table head={['User type', 'How they use the Market Overview']} rows={[
        ['Active traders', 'Spot the day’s biggest movers and volume surges, read buying vs selling pressure, and jump on momentum or reversals quickly.'],
        ['Long-term investors', 'Watch sector rotation on the heatmap, find quality names near 52-week lows for value entries, and monitor whether the broad market is risk-on or risk-off.'],
        ['Researchers / analysts', 'Use anomalies and signals as a daily idea-generation feed, compare sector performance, and export/screen for further analysis.'],
        ['New users', 'Get oriented fast — a single page that explains, in colour and ranking, what the market is doing without needing to know any tickers.'],
      ]} />
      <P>In short, the page helps with the four things every market participant does: <strong>stock discovery</strong>, <strong>market monitoring</strong>, <strong>comparison</strong> (sector vs sector, stock vs stock), and <strong>decision-making</strong> (where to dig deeper).</P>

      {/* 3. SECTIONS */}
      <H2 id="sections">3. Sections Covered</H2>

      <H3>Sector Heatmap</H3>
      <P><strong>What it shows:</strong> every GICS sector as a coloured tile sized by market weight. Green = the sector is up, red = down, deeper colour = bigger move. A separate full <Code>/market/heatmap</Code> page shows every individual stock as a tile over 5 days or 5 weeks.</P>
      <P><strong>How to read it:</strong> scan for the colour pattern. A sea of green = broad rally; mixed = stock-pickers’ market; red clustered in one sector = sector-specific weakness.</P>
      <P><strong>Why it matters / real use:</strong> shows <em>sector rotation</em> — where money is moving into and out of. If Materials is deep green while everything else is flat, commodities are in favour; an investor might then screen miners.</P>

      <H3>Top Movers</H3>
      <P><strong>What it shows:</strong> the biggest <strong>gainers</strong> and <strong>losers</strong> ranked by percent change, with a <strong>time-period selector</strong> (e.g. 1D / 1W / 1M / 3M) and a <strong>market-cap filter</strong> (all caps, or large/mid/small).</P>
      <P><strong>How to read it:</strong> a big % move on a large-cap is significant (lots of capital moved); the same % on a nano-cap can be noise. Always check volume alongside the move.</P>
      <P><strong>Why it matters / real use:</strong> momentum traders chase strength in gainers; contrarians hunt oversold names in losers; the cap filter lets you ignore illiquid micro-caps.</P>

      <H3>Volume Activity (Buying vs Selling Pressure)</H3>
      <P><strong>What it shows:</strong> stocks trading on unusually heavy volume, split into <strong>buying pressure</strong> (volume + rising price) and <strong>selling pressure</strong> (volume + falling price), filterable by market-cap tier.</P>
      <P><strong>How to read it:</strong> heavy volume confirms conviction. A price rise on big volume is stronger than the same rise on thin volume; heavy selling volume can mark distribution or capitulation.</P>
      <P><strong>Why it matters / real use:</strong> volume often precedes or confirms a move. Institutional accumulation/distribution shows up here before it shows up in the price trend.</P>

      <H3>Market Signals</H3>
      <P><strong>What it shows:</strong> rule-based technical events with a <strong>period selector</strong> — typically <strong>near period high</strong>, <strong>near period low</strong>, and <strong>volume surge</strong> (default window 52-week).</P>
      <P><strong>How to read it:</strong> “near high” = breakout/strength candidates; “near low” = potential value or falling-knife candidates; “volume surge” = something is happening, go find out why.</P>
      <P><strong>Why it matters / real use:</strong> a fast, objective filter for momentum and mean-reversion setups without manually charting hundreds of stocks.</P>

      <H3>Market Anomalies</H3>
      <P><strong>What it shows:</strong> stocks flagged as statistically or behaviourally unusual — e.g. high short interest, unusual volume, large price gaps — with a <strong>filter by anomaly type</strong> and an <strong>“Open in Screener”</strong> link that maps each anomaly to the closest screener preset.</P>
      <P><strong>How to read it:</strong> an anomaly is a <em>flag to investigate</em>, not a buy/sell call. A high short-interest flag, for example, can mean elevated risk <em>or</em> a potential short squeeze.</P>
      <P><strong>Why it matters / real use:</strong> a daily idea feed of “what’s out of the ordinary,” turning unusual behaviour into a research shortlist.</P>

      <Callout tone="amber" title="Access tiers">
        Free users see the Sector Heatmap and Top Movers. <strong>Volume Activity, Market Signals and Market Anomalies are Pro/Premium</strong> — free users see an upgrade prompt in those panels.
      </Callout>

      {/* 4. DATA */}
      <H2 id="data">4. How to Understand the Data</H2>
      <UL items={[
        <><strong>Where it comes from:</strong> all figures are pre-computed into the <Code>screener.universe</Code> golden record and supporting tables (sector snapshots, anomalies, heatmap cache) by the nightly data pipeline, sourced from the EODHD end-of-day feed and ASIC short-position data.</>,
        <><strong>How often it updates:</strong> the underlying data refreshes once per trading day after the ASX close (the nightly pipeline ~6:30pm AEST). It is <strong>end-of-day data, not live intraday</strong>. The page also caches responses in Redis for a few minutes for speed.</>,
        <><strong>What the numbers mean:</strong> percentages are price changes over the stated window; volume figures are share counts vs their averages; market cap is share price × shares on issue.</>,
        <><strong>Interpreting movement:</strong> always read <em>price move + volume + market cap</em> together. A move means more when it’s on heavy volume and a larger company.</>,
        <><strong>52-week highs/lows:</strong> “near the high” signals strength/breakout potential; “near the low” signals weakness or a possible value setup — context decides which.</>,
        <><strong>Be careful:</strong> small/micro-caps can show extreme percentages on tiny dollar volume (noise). End-of-day data won’t reflect moves that happened today. Anomalies and signals are rules, not judgements.</>,
      ]} />
      <Callout tone="red" title="Not financial advice">
        Everything on this page is <strong>filtered data and a research starting point</strong>. It highlights <em>where to look</em>, never <em>what to buy or sell</em>. Always verify independently before acting.
      </Callout>

      {/* 5. METRICS */}
      <H2 id="metrics">5. Metrics &amp; Data Shown</H2>
      <Table head={['Metric', 'What it means', 'How to use it / watch out for']} rows={[
        [<Code>ASX code</Code>, 'The stock’s ticker (e.g. BHP).', 'Click through to the company page. Codes are unique per listing.'],
        ['Company name', 'Full registered company name.', '—'],
        ['Sector', 'GICS sector classification.', 'Compare a stock against its sector; group/filter by it.'],
        ['Price', 'Latest end-of-day close (AUD).', 'A level, not a value judgement — pair with fundamentals.'],
        ['% change', 'Price change over the selected window.', 'Big % on a nano-cap can be noise; confirm with volume.'],
        ['1D / 1W / 1M / 3M return', 'Return over 1 day / week / month / 3 months.', 'Multiple windows separate a one-day pop from a real trend.'],
        ['52-week high / low', 'Highest / lowest price in the past year.', 'Reference points for breakouts and value setups.'],
        ['Distance from high/low', 'How far price sits below the 52w high or above the 52w low (%).', 'Near 0% from high = momentum; deep below = out of favour.'],
        ['Volume', 'Shares traded in the session.', 'Compare to average — raw volume alone says little.'],
        ['Volume ratio', 'Today’s volume ÷ average volume.', '>2× = unusual interest; confirm the price move with it.'],
        ['Market cap', 'Share price × shares on issue.', 'Filters out illiquid micro-caps; weights heatmap tiles.'],
        ['Anomaly type', 'The kind of unusual behaviour flagged (e.g. high short interest, volume spike).', 'A flag to investigate, not a signal to trade.'],
        ['Signal type', 'The rule that fired (near high/low, volume surge).', 'Objective momentum / mean-reversion filter.'],
        ['Severity', 'How extreme the anomaly/signal is.', 'Higher = more unusual, but not necessarily more profitable.'],
        ['Buying / selling pressure', 'Heavy volume with rising (buying) or falling (selling) price.', 'Confirms conviction; watch for accumulation/distribution.'],
      ]} />

      {/* 6. FEATURES */}
      <H2 id="features">6. Functional Features</H2>
      <UL items={[
        <><strong>Sector heatmap tiles</strong> — colour-coded, sized by weight; the full heatmap page adds a 5-day / 5-week toggle, sector + market-cap filters, and Excel export.</>,
        <><strong>Time-period selectors</strong> — on Top Movers and Market Signals, switch the window (1D/1W/1M/3M, 52-week).</>,
        <><strong>Market-cap filters</strong> — on Top Movers and Volume Activity, restrict to all / large / mid / small caps.</>,
        <><strong>Anomaly type filter</strong> — narrow the anomalies list to one category.</>,
        <><strong>Ranked tables &amp; cards</strong> — gainers, losers, buying/selling pressure, signals, anomalies, each ranked.</>,
        <><strong>Refresh</strong> — re-pull the latest cached data; a “last updated” timestamp shows freshness.</>,
        <><strong>“Open in Screener” links</strong> — each anomaly maps to the nearest screener preset to find similar stocks.</>,
        <><strong>Click-through navigation</strong> — every stock row links to its Company Detail page; the heatmap and excel export are one click away.</>,
      ]} />
      <H3>Step-by-step: a typical session</H3>
      <OL items={[
        'Open /market. Scan the Sector Heatmap for the day’s red/green pattern.',
        'Switch Top Movers to the 1W window and filter to large caps to ignore micro-cap noise.',
        'Open Volume Activity → Buying Pressure to see where heavy money is flowing in.',
        'Check Market Signals → “near period high” for breakout candidates.',
        'Scan Market Anomalies, filter to “high short interest”, and click “Open in Screener” to find peers.',
        'Click any interesting ticker to open its Company Detail page for the deep-dive.',
      ]} />

      {/* 7. TECHNICAL */}
      <H2 id="technical">7. Technical Details</H2>
      <H3>Frontend</H3>
      <UL items={[
        <>Page: <Code>frontend/app/market/page.tsx</Code> (client component) + <Code>app/market/heatmap/page.tsx</Code> for the full heatmap.</>,
        <>State per section (dashboard, movers, signals, anomalies, volumeActivity) with independent loading flags; reusable row/card components (e.g. <Code>VolumePressureRow</Code>).</>,
        <>Free vs Pro gating renders an upgrade prompt in the Pro-only panels.</>,
      ]} />
      <H3>Backend API endpoints (<Code>/api/v1/market/*</Code>)</H3>
      <Table head={['Endpoint', 'Feeds']} rows={[
        [<Code>GET /dashboard</Code>, 'Headline summary + sector heatmap data for the page header.'],
        [<Code>GET /movers</Code>, 'Top gainers/losers (params: period, limit, cap tier).'],
        [<Code>GET /volume-activity</Code>, 'Buying/selling pressure lists (param: cap tier).'],
        [<Code>GET /signals</Code>, 'near_period_high / near_period_low / volume_surge (param: period).'],
        [<Code>GET /anomalies</Code>, 'Flagged anomalies (params: limit, flag type).'],
        [<Code>GET /sectors</Code>, 'Sector performance breakdown.'],
        [<span><Code>GET /heatmap</Code> &amp; <Code>/heatmap/export</Code></span>, 'Per-stock 5-day/5-week heatmap + Excel export.'],
      ]} />
      <H3>Data sources, flow &amp; refresh</H3>
      <UL items={[
        <><strong>Source → backend:</strong> EODHD EOD prices + ASIC shorts → staging → transforms → <Code>screener.universe</Code>, <Code>market.sector_snapshots</Code>, <Code>market.anomalies</Code>, <Code>market.heatmap_cache</Code> (built nightly by <Code>daily_pipeline.py</Code> + compute engines).</>,
        <><strong>Backend → frontend:</strong> endpoints read those pre-computed tables (mostly simple ranked SELECTs — no heavy compute at request time) and return JSON.</>,
        <><strong>Aggregation:</strong> sector snapshots aggregate per-stock returns into sector averages; the heatmap is pre-aggregated into <Code>heatmap_cache</Code> so reads are sub-100ms.</>,
        <><strong>Caching:</strong> responses cached in Redis with short TTLs (market data changes only once a day); the heatmap has its own cache + a “last updated” label.</>,
        <><strong>Loading / errors:</strong> each panel shows its own skeleton/spinner and fails independently — one slow section never blocks the rest.</>,
        <><strong>Performance:</strong> heavy lifting happens nightly, not per request; reads are indexed, paginated and capped (e.g. top-N), keeping the page fast.</>,
      ]} />

      {/* 8. EXAMPLES */}
      <H2 id="examples">8. Data Interpretation Examples</H2>
      <UL items={[
        <><strong>Stock near a 52-week high:</strong> distance-from-high ≈ −2% and rising on volume → momentum/breakout candidate. Check it isn’t a one-day spike (look at 1W/1M too).</>,
        <><strong>Heavy buying:</strong> a stock up 4% on 3× average volume in the Buying Pressure list → strong conviction; institutions may be accumulating.</>,
        <><strong>Heavy selling:</strong> down 6% on 4× volume in Selling Pressure → distribution or capitulation; avoid catching the falling knife until volume calms.</>,
        <><strong>Heatmap colours:</strong> deep green Materials tile + red Tech tiles → money rotating from growth into commodities; consider screening miners.</>,
        <><strong>High short-interest anomaly:</strong> 12% of shares shorted → elevated downside risk, but also potential squeeze fuel if news turns positive. Investigate the “why”.</>,
        <><strong>Top Gainers vs Losers:</strong> gainers for momentum/trend ideas; losers for contrarian/value or “what broke today” research.</>,
        <><strong>Signal → research:</strong> a “volume surge” signal fires on a small-cap → open its Company page, check news/announcements, then decide if it’s worth a watchlist slot.</>,
      ]} />

      {/* 9. SUPPORT */}
      <H2 id="support">9. Quick Reference (Support)</H2>
      <Table head={['Question / issue', 'Answer']} rows={[
        ['“The data looks a day old.”', 'Correct — it’s end-of-day data, refreshed after the ASX close (~6:30pm AEST nightly). It is not live intraday.'],
        ['“Volume Activity / Signals / Anomalies are locked.”', 'Those panels are Pro/Premium. Free users see the heatmap and Top Movers.'],
        ['“A tiny stock shows a huge % move.”', 'Expected for micro/nano-caps on thin volume. Use the market-cap filter to exclude them.'],
        ['“Heatmap dates look stale.”', 'The heatmap reads a nightly cache; if a build was skipped the dates can lag. Re-running the heatmap compute refreshes it.'],
        ['“Numbers differ from another site.”', 'We use end-of-day EODHD data + our own derived metrics; intraday sites will differ during the trading day.'],
      ]} />

      {/* 10. FUTURE */}
      <H2 id="future">10. Future Improvements</H2>
      <UL items={[
        <><strong>Intraday / near-real-time data</strong> (requires a live feed) for true “right now” movers.</>,
        <><strong>AI market summary</strong> — a daily plain-English “what happened today and why” paragraph at the top.</>,
        <><strong>Watchlist integration</strong> — add any mover/signal/anomaly to a watchlist in one click; highlight watchlist names on the page.</>,
        <><strong>Alerts</strong> — “notify me when my sector turns red” or “when a stock enters the volume-surge list”.</>,
        <><strong>Mini charts / sparklines</strong> on each row for instant trend context.</>,
        <><strong>Saved views &amp; personalised dashboards</strong> — remember preferred cap tier, period and section order per user.</>,
        <><strong>Sector drill-down pages</strong> — click a heatmap tile to see that sector’s constituents, leaders and laggards.</>,
        <><strong>Better filters</strong> — combine cap tier + sector + signal type; multi-select anomaly types.</>,
        <><strong>Export</strong> — CSV/Excel of any table (movers, signals, anomalies), not just the heatmap.</>,
        <><strong>Mobile improvements</strong> — condensed cards and swipeable sections for small screens.</>,
      ]} />

      <div className="mt-10 pt-4 border-t border-slate-200 text-xs text-slate-400">
        Internal documentation — Admin only. Reflects the Market Overview page as built. Update this manual when the page changes.
      </div>
    </div>
  )
}

// ── Company Detail manual ─────────────────────────────────────────────────────
const CTOC = [
  ['c-overview', '1. Page Overview'],
  ['c-benefits', '2. User Benefits'],
  ['c-sections', '3. Sections (Tabs) Covered'],
  ['c-data', '4. How to Understand the Data'],
  ['c-metrics', '5. Metrics & Data Shown'],
  ['c-features', '6. Functional Features'],
  ['c-technical', '7. Technical Details'],
  ['c-examples', '8. Data Interpretation Examples'],
  ['c-support', '9. Quick Reference (Support)'],
  ['c-future', '10. Future Improvements'],
]
function CompanyDetailManual() {
  return (
    <div>
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-6">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">On this page</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1">
          {CTOC.map(([id, label]) => <a key={id} href={`#${id}`} className="text-sm text-blue-600 hover:underline">{label}</a>)}
        </div>
      </div>

      {/* 1 */}
      <H2 id="c-overview">1. Page Overview</H2>
      <H3>What is the Company Details Page?</H3>
      <P>The <strong>Company Details</strong> page (<Code>/company/[CODE]</Code>, e.g. <Code>/company/BHP</Code>) is the single-stock deep-dive. Where the Screener and Market Overview help you <em>find</em> stocks, this page is where you <em>study one</em> — its price, full fundamentals, dividends, technicals, peers, ASX announcements and an AI bull/bear summary, all on one screen split into tabs.</P>
      <H3>Purpose</H3>
      <P>To answer “<strong>Is this company any good, and what’s the story?</strong>” in one place — without the user needing a spreadsheet or a paid terminal. It turns ~300 data points per stock into readable cards, charts and plain-English verdicts.</P>
      <H3>What problem it solves</H3>
      <UL items={[
        <><strong>Scattered data</strong> — price, financials, dividends, franking, technicals and news normally live on five different sites. This consolidates them.</>,
        <><strong>Raw-number overwhelm</strong> — colour-coded cards, a quality checklist and factor scores translate numbers into “good / watch / bad”.</>,
        <><strong>ASX-specific gaps</strong> — franking credits, grossed-up yield and ASIC short data are first-class here, unlike generic global tools.</>,
      ]} />
      <H3>How it fits into the platform</H3>
      <P>It is the <strong>research destination</strong>. Users arrive from the Screener, Market Overview, search, watchlist or alerts, study the stock here, then add it to a <strong>watchlist</strong>, set an <strong>alert</strong>, or add it to a <strong>portfolio</strong>.</P>

      {/* 2 */}
      <H2 id="c-benefits">2. User Benefits</H2>
      <Table head={['User type', 'How they use Company Details']} rows={[
        ['Retail / new investors', 'Read the quality checklist and factor scores for a fast “is this healthy?” read, plus the AI bull/bear case in plain English.'],
        ['Long-term investors', 'Study multi-year financials, ROE/ROIC quality, dividend & franking history, balance-sheet strength and valuation before buying to hold.'],
        ['Active / professional traders', 'Check technicals (RSI, MACD, moving averages), 52-week positioning, volume and recent announcements for timing.'],
        ['Researchers / analysts', 'Use the full statements, per-share metrics, efficiency ratios and peer comparison as a one-stop fundamental workbench.'],
      ]} />
      <P>It supports the full research loop: <strong>company research</strong> (fundamentals + statements), <strong>comparison</strong> (peers tab), <strong>monitoring</strong> (watchlist/alerts), and <strong>decision-making</strong> (valuation, quality, AI summary).</P>

      {/* 3 */}
      <H2 id="c-sections">3. Sections (Tabs) Covered</H2>
      <P>The page has a sticky <strong>header</strong> (code, name, sector, latest price, % change, market cap, a <strong>Watchlist</strong> star and an <strong>Add to Portfolio</strong> action) and <strong>seven tabs</strong>:</P>

      <H3>Overview tab</H3>
      <P>The summary screen. It contains, top to bottom:</P>
      <UL items={[
        <><strong>Factor scores</strong> — Value, Quality, Growth, Momentum, Income and a blended Composite score (0–100), for an instant profile.</>,
        <><strong>Quality checklist</strong> — pass/watch/fail checks: Profitable, Revenue Growth, Cash Earnings, Liquidity, Low Leverage, Gross Margin — each with the actual figure.</>,
        <><strong>Metric cards</strong> — Valuation, Dividends, Profitability, Growth, Balance Sheet, Quality &amp; Ownership, plus <strong>Liquidity &amp; Leverage, Efficiency, Per-Share Values, Balance Sheet Detail, Income Statement and Cash Flow Detail</strong>.</>,
        <><strong>Price Returns</strong> — a row of 1W / 1M / 3M / 6M / YTD / 1Y / 3Y / 5Y returns, green/red.</>,
        <><strong>Trend charts</strong> — multi-year revenue/earnings and other trend visuals.</>,
      ]} />
      <P><em>Why it matters / real use:</em> a 30-second health read (scores + checklist) backed by the full metric detail right below it.</P>

      <H3>Financials tab</H3>
      <P><strong>Shows:</strong> the multi-year income statement, balance sheet and cash flow (revenue, gross profit, EBITDA, EBIT, net profit, EPS, DPS, margins; assets, equity, debt, cash, BVPS; CFO, capex, FCF) by fiscal year, plus half-yearly figures. <em>Read it</em> for the trajectory — are revenue, margins and cash flow rising or fading? <em>Use it</em> to verify the headline metrics with the underlying statements.</P>

      <H3>Technicals tab</H3>
      <P><strong>Shows:</strong> RSI, MACD, moving averages (SMA/EMA), Bollinger Bands, ATR, volume and the returns ladder. <em>Read it</em> for trend and timing — price vs 200-day, RSI overbought/oversold, MACD crosses. <em>Use it</em> to time an entry/exit, not to judge company quality.</P>

      <H3>Dividends tab</H3>
      <P><strong>Shows:</strong> dividend history, yield, <strong>franking %</strong>, <strong>grossed-up yield</strong>, payout ratio, consecutive years and ex-dividend dates. <em>Why it matters:</em> for Australian investors franking credits materially lift the after-tax return — the grossed-up yield is the number income investors actually care about.</P>

      <H3>Peers tab</H3>
      <P><strong>Shows:</strong> companies in the same GICS industry group with side-by-side key metrics. <em>Use it</em> to judge whether the stock is cheap/expensive or strong/weak <em>relative to its actual competitors</em> — a P/E of 20 means nothing until you see peers at 12 or 35.</P>

      <H3>AI Insights tab (Pro/Premium)</H3>
      <P><strong>Shows:</strong> a Claude-generated <strong>bull case</strong> and <strong>bear case</strong> — the strongest arguments for and against, derived from the company’s own metrics. <em>Use it</em> as a balanced starting narrative; it’s a research aid, never a recommendation. Results are cached and can be refreshed.</P>

      <H3>Documents tab</H3>
      <P><strong>Shows:</strong> recent ASX announcements (earnings, dividends, trading halts, market-sensitive filings) and capital raises. <em>Use it</em> to find the “why” behind a price or volume move.</P>

      <Callout tone="amber" title="Conditional & gated content">
        Mining stocks show extra <strong>mining metrics</strong> and REITs show <strong>A-REIT metrics</strong> where data exists. The <strong>AI Insights</strong> tab is Pro/Premium; some deeper data may show an upgrade prompt for free users.
      </Callout>

      {/* 4 */}
      <H2 id="c-data">4. How to Understand the Data</H2>
      <UL items={[
        <><strong>Where it comes from:</strong> fundamentals from the EODHD financial statements feed (income statement, balance sheet, cash flow), prices from the EODHD end-of-day price feed, short data from ASIC, dividends/announcements from market data — all loaded nightly into <Code>financials.*</Code>, <Code>market.*</Code> and the <Code>screener.universe</Code> golden record.</>,
        <><strong>How often it updates:</strong> prices and derived metrics refresh once per trading day after the ASX close; fundamentals update when companies report (half-yearly/annually). It is <strong>end-of-day, not live intraday</strong>.</>,
        <><strong>What the numbers mean:</strong> dollar figures are usually AUD millions on cards (formatted M/B/T); margins, growth and yields are percentages; ratios are shown with an “×”.</>,
        <><strong>How to interpret:</strong> read <em>valuation with growth and quality</em> (a high P/E needs growth to justify it); <em>dividends with payout and franking</em> (a fat yield is only safe if the payout is covered); <em>debt with cash flow</em> (leverage is fine if interest is well covered); <em>technicals separately from fundamentals</em> (timing vs quality).</>,
        <><strong>Be careful:</strong> a single great or terrible year can distort ratios — check the multi-year statements. Loss-making companies have no meaningful P/E. Tiny/illiquid stocks have noisy data. Some fields are blank where the data simply isn’t in the feed.</>,
      ]} />
      <Callout tone="red" title="Not financial advice">
        Every figure, score and AI summary is <strong>research data, not a recommendation</strong>. It tells you <em>what the numbers say</em> and <em>where to dig</em> — the decision is always yours. Verify independently.
      </Callout>

      {/* 5 */}
      <H2 id="c-metrics">5. Metrics &amp; Data Shown</H2>
      <Table head={['Metric', 'What it means', 'How to use it / watch out for']} rows={[
        ['Code / Name / Sector / Industry', 'Identity & GICS classification.', 'Sector/industry set the right comparison group.'],
        ['Price / Market cap', 'Latest close; price × shares on issue.', 'Cap tells you the size/liquidity class.'],
        ['P/E ratio', 'Price ÷ earnings per share.', 'Compare within sector; negative/none = loss-making. High P/E needs growth.'],
        ['EPS', 'Profit per share.', 'The engine of P/E; watch the multi-year trend & dilution.'],
        ['Revenue / Profit', 'Top line and bottom line.', 'Rising revenue + falling profit = margin pressure — investigate.'],
        ['Revenue / Profit growth', 'Year-on-year & multi-year CAGR.', 'CAGRs smooth out one-off years; positive & steady is best.'],
        ['ROE / ROA / ROCE / ROIC', 'Returns on equity / assets / capital employed / invested capital.', 'High & stable = quality. ROIC above cost of capital = value creation.'],
        ['Dividend yield', 'Dividend ÷ price.', 'Very high yield can signal risk (a falling price). Check coverage.'],
        ['Grossed-up yield ★', 'Yield including franking credits.', 'The real after-tax income for Australian investors.'],
        ['Franking %', 'Share of the dividend that carries tax credits.', '100% fully franked is most tax-effective onshore.'],
        ['Payout ratio', 'Dividends ÷ earnings.', '>100% means paying more than it earns — often unsustainable.'],
        ['Debt-to-equity', 'Total debt ÷ equity.', 'Higher = more leverage/risk; read with interest coverage.'],
        ['Cash flow / Free cash flow', 'Operating cash; cash after capex.', 'Positive FCF = self-funding. Compare to net profit for earnings quality.'],
        ['Operating / Net margin', 'Profit per dollar of sales.', 'Durable high margins suggest pricing power / a moat.'],
        ['1W / 1M / 6M / 1Y returns', 'Price returns over each window.', 'Multiple windows separate a pop from a trend.'],
        ['52-week high / low', 'Yearly price range.', 'Near high = momentum; near low = value or weakness.'],
        ['Volume / Avg volume', 'Shares traded vs the average.', 'Confirms moves; low average volume = thin liquidity.'],
        ['Piotroski F-Score / Quality score', 'Financial-health score (0–9) / composite quality.', 'High = financially solid; a screen, not a buy signal.'],
        ['Peer metrics', 'Same-industry comparison set.', 'Context turns a raw ratio into “cheap” or “expensive”.'],
      ]} />

      {/* 6 */}
      <H2 id="c-features">6. Functional Features</H2>
      <UL items={[
        <><strong>Tabbed navigation</strong> — Overview / Financials / Technicals / Dividends / Peers / AI Insights / Documents.</>,
        <><strong>Watchlist star</strong> — add/remove the stock from a watchlist in one click (header).</>,
        <><strong>Add to Portfolio</strong> — record a holding for portfolio tracking.</>,
        <><strong>Alerts</strong> — set price/percentage alerts (links to the Alerts page).</>,
        <><strong>Metric cards &amp; checklist</strong> — colour-coded pass/watch/fail and green/red values.</>,
        <><strong>Charts</strong> — interactive multi-year trend and price charts (recharts).</>,
        <><strong>Peer comparison table</strong> — sortable side-by-side metrics.</>,
        <><strong>AI summary</strong> — generate / refresh the bull &amp; bear case.</>,
        <><strong>Click-through</strong> — peers link to their own company pages; announcements open the source filing.</>,
      ]} />
      <H3>Step-by-step: researching a stock</H3>
      <OL items={[
        'Open the stock (search, or click any ticker from the Screener / Market Overview).',
        'On Overview, read the factor scores + quality checklist for a fast health read.',
        'Scan the Valuation, Profitability and Balance Sheet cards; note anything red.',
        'Open Financials to confirm the multi-year trend behind the headline numbers.',
        'Open Dividends (income) or Technicals (timing) depending on your goal.',
        'Open Peers to see if it’s cheap/strong relative to competitors.',
        'Read the AI bull/bear case for a balanced narrative.',
        'Check Documents for recent announcements, then add to a Watchlist / set an Alert.',
      ]} />

      {/* 7 */}
      <H2 id="c-technical">7. Technical Details</H2>
      <H3>Frontend</H3>
      <UL items={[
        <>Route: <Code>frontend/app/company/[code]/page.tsx</Code> (server wrapper) → <Code>CompanyTabs.tsx</Code> (the tabbed client component, ~3,100 lines).</>,
        <>Reusable <Code>MetricRow</Code> / <Code>Card</Code> components; formatters <Code>fmtM</Code> (AUD millions → M/B/T), <Code>fmtX</Code> (× ratios), <Code>formatRatio</Code> (decimal → %), <Code>signedPct</Code> (signed %); charts via <strong>recharts</strong>.</>,
        <>Each tab lazy-loads its data on first open; independent loading states.</>,
      ]} />
      <H3>Backend API endpoints (<Code>/api/v1/companies/{'{code}'}/*</Code>)</H3>
      <Table head={['Endpoint', 'Feeds', 'Source']} rows={[
        [<Code>/overview</Code>, 'All Overview-tab metrics (~150 fields).', <Code>screener.universe</Code>],
        [<Code>/financials</Code>, 'Multi-year income / balance / cash-flow statements.', <Code>financials.annual_*</Code>],
        [<Code>/halfyearly</Code>, 'Half-yearly statement figures.', <Code>market.halfyearly_metrics</Code>],
        [<Code>/prices</Code>, 'Price history for charts.', <Code>market.daily_prices</Code>],
        [<Code>/dividends</Code>, 'Dividend history + summary.', <Code>market.dividends</Code>],
        [<Code>/peers</Code>, 'Same-industry comparison set.', <Code>screener.universe</Code>],
        [<span><Code>/announcements</Code> + <Code>/capital-raises</Code></span>, 'Documents tab.', <Code>market.asx_announcements</Code>],
        [<Code>/ai-summary</Code>, 'Bull/bear case (Pro/Premium).', 'Claude API + universe metrics'],
        [<span><Code>/mining-metrics</Code> + <Code>/reit-metrics</Code></span>, 'Sector-specific cards.', 'sector metric tables'],
      ]} />
      <H3>Flow, calculation, caching &amp; access</H3>
      <UL items={[
        <><strong>Source → backend:</strong> EODHD (prices + statements) + ASIC (shorts) → staging → transforms → <Code>financials.*</Code> / <Code>market.*</Code> → nightly compute engines derive ratios, scores, CAGRs and the quality checklist into <Code>screener.universe</Code>.</>,
        <><strong>Backend → frontend:</strong> endpoints read the pre-computed tables (little request-time compute) and return typed JSON matching the <Code>CompanyOverview</Code> / financials interfaces.</>,
        <><strong>Calculation logic:</strong> ratios/scores are computed nightly, not per request, so every user sees the same vetted numbers; the F-Score, Altman Z, factor scores and per-share/efficiency ratios are produced by the compute engines.</>,
        <><strong>Caching:</strong> responses cached in Redis (<Code>COMPANY_TTL</Code>); the AI summary is cached per stock and only regenerated on demand.</>,
        <><strong>Loading / errors:</strong> per-tab spinners; a missing stock returns 404 (“not in the active universe”); one failing tab doesn’t break the others.</>,
        <><strong>Access &amp; performance:</strong> AI Insights is plan-gated (Pro/Premium); reads are indexed single-row/peer lookups, keeping the page fast.</>,
      ]} />

      {/* 8 */}
      <H2 id="c-examples">8. Data Interpretation Examples</H2>
      <UL items={[
        <><strong>High P/E (e.g. 40×):</strong> only justified by fast growth — check revenue/EPS CAGR and the peer P/E. High P/E + slow growth = expensive.</>,
        <><strong>Strong ROE (e.g. 22%):</strong> efficient use of shareholder capital — confirm it isn’t just high leverage by checking debt/equity and ROIC.</>,
        <><strong>Yield &amp; franking:</strong> 5% yield, 100% franked → grossed-up ≈ 7.1% — the real onshore return; but check the payout ratio is under ~80%.</>,
        <><strong>Rising revenue, falling profit:</strong> margin compression — costs growing faster than sales. Open Financials and watch the margin trend.</>,
        <><strong>Debt metrics:</strong> D/E 1.5× looks high, but if interest coverage is 6× and net-debt/EBITDA is under 2×, it’s manageable.</>,
        <><strong>Peer comparison:</strong> the stock at P/E 12 while peers average 18 → potentially cheap (or lower quality) — dig into why.</>,
        <><strong>52-week range:</strong> price 3% off the 52-week high on rising volume = momentum/breakout; at the 52-week low = value or falling knife.</>,
        <><strong>Technicals:</strong> price above the 200-day SMA with RSI ~55 = healthy uptrend, not overbought — a reasonable timing backdrop.</>,
        <><strong>Data → deeper research:</strong> a red “Cash Earnings” check → open Cash Flow Detail and the Documents tab to find out why FCF turned negative.</>,
      ]} />

      {/* 9 */}
      <H2 id="c-support">9. Quick Reference (Support)</H2>
      <Table head={['Question / issue', 'Answer']} rows={[
        ['“Some metrics are blank.”', 'The feed doesn’t supply every field for every stock (e.g. analyst data, some per-share fields). Blank ≠ error.'],
        ['“P/E shows a dash.”', 'The company is loss-making (no positive EPS), so P/E is undefined — expected.'],
        ['“AI Insights is locked.”', 'The AI bull/bear summary is Pro/Premium. Other tabs are available to all.'],
        ['“Prices look a day behind.”', 'End-of-day data, refreshed after the ASX close. Not live intraday.'],
        ['“Numbers differ from the company’s report.”', 'We standardise EODHD-fed statements to AUD millions; presentation/adjustments can differ slightly from the annual report.'],
        ['“404 / not found.”', 'The stock isn’t in the active universe (delisted, suspended, or not covered).'],
      ]} />

      {/* 10 */}
      <H2 id="c-future">10. Future Improvements</H2>
      <UL items={[
        <><strong>Interactive price charts</strong> with overlays (MAs, volume, events) and selectable ranges.</>,
        <><strong>Richer peer comparison</strong> — user-chosen peer sets, percentile ranks, radar charts.</>,
        <><strong>AI company summary</strong> beyond bull/bear — a plain-English “what this company does &amp; how it’s tracking”.</>,
        <><strong>Full dividend history</strong> chart with franking and a forward-income estimate.</>,
        <><strong>Risk alerts</strong> — flag high leverage, negative FCF, going-concern or covenant risk.</>,
        <><strong>Valuation tools</strong> — DCF / reverse-DCF / dividend-discount calculators with user inputs.</>,
        <><strong>Downloadable one-page PDF report</strong> per company.</>,
        <><strong>Deeper watchlist / portfolio integration</strong> — show your holding, cost base and P&amp;L inline.</>,
        <><strong>Custom dashboards</strong> — let users pin their preferred metric cards and tab order.</>,
        <><strong>“Learn this metric” links</strong> — each metric links to its Glossary definition + worked example.</>,
        <><strong>Mobile improvements</strong> — condensed cards, swipeable tabs, sticky price header.</>,
      ]} />

      <div className="mt-10 pt-4 border-t border-slate-200 text-xs text-slate-400">
        Internal documentation — Admin only. Reflects the Company Details page as built. Update this manual when the page changes.
      </div>
    </div>
  )
}

// ── Manual registry (add a page manual here, then a render case below) ─────────
const MANUALS = [
  { slug: 'market-overview', title: 'Market Overview', page: '/market', status: 'ready' as const },
  { slug: 'screener',        title: 'Stock Screener',  page: '/screener', status: 'soon' as const },
  { slug: 'company-detail',  title: 'Company Detail',  page: '/company/[code]', status: 'ready' as const },
  { slug: 'alpha-screens',   title: 'Alpha Screens',   page: '/scans', status: 'soon' as const },
  { slug: 'glossary',        title: 'Metrics Glossary', page: '/glossary', status: 'soon' as const },
  { slug: 'portfolio',       title: 'Portfolio',       page: '/portfolio', status: 'soon' as const },
]

export default function AdminManualsPage() {
  const [active, setActive] = useState('market-overview')
  const current = MANUALS.find(m => m.slug === active)!

  return (
    <div>
      {/* Header */}
      <div className="flex items-start gap-3 mb-6">
        <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0">
          <BookOpen className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Page Manuals</h1>
          <p className="text-sm text-slate-500 mt-0.5">Functional &amp; technical documentation for each page — for support, onboarding, product and engineering.</p>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Left nav */}
        <aside className="lg:w-60 shrink-0">
          <div className="bg-white border border-slate-200 rounded-xl p-2 sticky top-6">
            {MANUALS.map(m => (
              <button
                key={m.slug}
                onClick={() => m.status === 'ready' && setActive(m.slug)}
                disabled={m.status !== 'ready'}
                className={cn(
                  'w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm text-left transition-colors',
                  active === m.slug ? 'bg-blue-50 text-blue-700 font-semibold' : 'text-slate-600 hover:bg-slate-50',
                  m.status !== 'ready' && 'opacity-50 cursor-not-allowed',
                )}
              >
                <span>{m.title}</span>
                {m.status === 'ready'
                  ? <ChevronRight className="w-4 h-4" />
                  : <span className="text-[10px] uppercase text-slate-400">soon</span>}
              </button>
            ))}
          </div>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0 bg-white border border-slate-200 rounded-xl p-6">
          <div className="flex items-center gap-2 text-xs text-slate-400 mb-1">
            <Check className="w-3.5 h-3.5 text-green-500" /> Live page: <Code>{current.page}</Code>
          </div>
          {active === 'market-overview' && <MarketOverviewManual />}
          {active === 'company-detail' && <CompanyDetailManual />}
        </main>
      </div>
    </div>
  )
}
