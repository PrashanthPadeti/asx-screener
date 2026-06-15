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

// ── Alpha Screens manual ──────────────────────────────────────────────────────
const ATOC = [
  ['a-overview', '1. Page Overview'],
  ['a-benefits', '2. User Benefits'],
  ['a-sections', '3. Sections Covered'],
  ['a-data', '4. How It Works & the Data'],
  ['a-cards', '5. What Each Screen Card Shows'],
  ['a-features', '6. Functional Features'],
  ['a-technical', '7. Technical Details'],
  ['a-examples', '8. Usage Examples'],
  ['a-support', '9. Quick Reference (Support)'],
  ['a-future', '10. Future Improvements'],
]
function AlphaScreensManual() {
  return (
    <div>
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-6">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">On this page</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1">
          {ATOC.map(([id, label]) => <a key={id} href={`#${id}`} className="text-sm text-blue-600 hover:underline">{label}</a>)}
        </div>
      </div>

      {/* 1 */}
      <H2 id="a-overview">1. Page Overview</H2>
      <H3>What is the Alpha Screens page?</H3>
      <P>The <strong>Alpha Screens</strong> page (<Code>/scans</Code>) is a library of <strong>ready-made, one-click stock screens</strong> — “institutional-grade screens built on proven quant strategies.” Instead of building filters by hand in the Screener, the user picks a pre-built strategy (e.g. “Fully Franked Value”, “ROIC Compounder”, “RSI Oversold”) and instantly sees the ASX stocks that match it.</P>
      <H3>Purpose</H3>
      <P>To give users <strong>expert-designed screens out of the box</strong>. It answers “<strong>I don’t know which filters to use — just show me good income / value / growth / momentum stocks.</strong>” Each card is a named strategy with its filter logic already set.</P>
      <H3>What problem it solves</H3>
      <UL items={[
        <><strong>Blank-page problem</strong> — many users don’t know which metrics or thresholds to combine. Alpha Screens packages proven combinations for them.</>,
        <><strong>Speed</strong> — a curated strategy is one click away, versus minutes of manual filter-building.</>,
        <><strong>Idea generation</strong> — browsing the categories surfaces strategies users hadn’t thought to run.</>,
      ]} />
      <H3>How it fits into the platform</H3>
      <P>Alpha Screens is the <strong>guided entry point to screening</strong>. Picking a screen opens the full <strong>Screener</strong> with that strategy pre-loaded and run, where the user can tweak it, sort, export, or save it. It sits in the top nav next to the Screener and Market Overview.</P>

      {/* 2 */}
      <H2 id="a-benefits">2. User Benefits</H2>
      <Table head={['User type', 'How they use Alpha Screens']} rows={[
        ['Beginners', 'Run a proven strategy without knowing any metrics — a safe, guided way to discover stocks.'],
        ['Income investors', 'Use the Dividend & Income screens (high yield, fully franked, dividend aristocrats) to build an income shortlist.'],
        ['Value & quality investors', 'Use value + financial-health screens (low P/E + Piotroski, Altman safety, ROIC compounders).'],
        ['Growth & momentum traders', 'Use accelerating-revenue/earnings and price-momentum screens for trend ideas.'],
        ['Technical traders', 'Use chart-based screens (breakouts, golden cross, RSI oversold/overbought).'],
        ['All users', 'Generate a fresh shortlist in seconds, then deep-dive any result on its Company page.'],
      ]} />

      {/* 3 */}
      <H2 id="a-sections">3. Sections Covered</H2>
      <H3>Pre-built screen categories</H3>
      <P>Screens are grouped into themed categories, each a grid of strategy cards:</P>
      <UL items={[
        <><strong>Dividend &amp; Income</strong> — high-yield and franked-dividend strategies for income investors.</>,
        <><strong>Value &amp; Quality</strong> — undervalued stocks with strong fundamentals and financial health.</>,
        <><strong>Growth &amp; Momentum</strong> — companies accelerating revenue, earnings and price momentum.</>,
        <><strong>Technical Signals</strong> — chart-based breakout, trend-following and mean-reversion signals.</>,
        <>(plus specialist / ASX-specific strategies such as miners, A-REITs and franking optimisers.)</>,
      ]} />
      <H3>Screen tiers (Free / Pro / Premium)</H3>
      <P>Each card carries a tier badge. <strong>Free</strong> screens (e.g. Value + Fully Franked, Price Momentum, Piotroski Strong, Potential Turnaround) are open to everyone. <strong>Pro</strong> screens unlock more advanced multi-factor strategies. <strong>Premium</strong> screens are the most sophisticated (AI-ranked Top 5, mining value, A-REIT income, franking optimiser, dividend aristocrats, quality compounders, Altman safety, etc.). Locked cards show a badge and link to pricing.</P>
      <H3>Sector Screens</H3>
      <P>Browse the market by <strong>GICS sector</strong> — one click filters the Screener to that sector (with a stock count per sector).</P>
      <H3>Community Picks</H3>
      <P>Screens <strong>shared by other users</strong> (saved as public/community). These include both visual filter screens and SQL-style Query Mode screens. <strong>Gated to Pro/Premium</strong>: free users see an upgrade card; Pro users see free/Pro-created screens; Premium/admin see all (Premium-created screens are hidden from Pro).</P>
      <H3>Stats bar</H3>
      <P>A header summary counts the total screens available and breaks them down by Premium / Pro / Free / Sector / Community.</P>

      {/* 4 */}
      <H2 id="a-data">4. How It Works &amp; the Data</H2>
      <UL items={[
        <><strong>What a screen is:</strong> a named, predefined set of filter conditions (e.g. <Code>dividend_yield ≥ 4 AND franking_pct ≥ 70 AND net_margin &gt; 0</Code>) plus a default sort.</>,
        <><strong>What clicking does:</strong> it opens the Screener with that strategy applied and runs it against the live <Code>screener.universe</Code> — so results always reflect the latest end-of-day data, not a frozen list.</>,
        <><strong>Where the data comes from:</strong> the same nightly pipeline that powers the Screener (EODHD end-of-day prices + statements, ASIC shorts) → <Code>screener.universe</Code>.</>,
        <><strong>How often it updates:</strong> results refresh whenever you run a screen, against data rebuilt nightly after the ASX close. It is end-of-day, not intraday.</>,
        <><strong>Be careful:</strong> a screen is a <em>shortlist generator</em>, not a buy list. A strategy that fit the market last cycle may not this cycle. Always research each result before acting.</>,
      ]} />
      <Callout tone="red" title="Not financial advice">
        Alpha Screens surface stocks that match a strategy’s rules — they are a <strong>research starting point</strong>, never a recommendation to buy or sell.
      </Callout>

      {/* 5 */}
      <H2 id="a-cards">5. What Each Screen Card Shows</H2>
      <Table head={['Element', 'Meaning']} rows={[
        ['Strategy name', 'The screen’s title (e.g. “Dividend Income Portfolio”).'],
        ['Description', 'One line on what the screen looks for.'],
        ['Filter chips', 'The first few filter conditions, with “+N more” if there are others.'],
        ['Tier badge', 'Free / Pro / Premium access level for the screen.'],
        ['Lock state', 'Premium/Pro screens appear locked for lower tiers and link to pricing.'],
        ['Click target', 'Opens /screener?preset=<id> (runs the strategy) or /pricing if locked.'],
      ]} />

      {/* 6 */}
      <H2 id="a-features">6. Functional Features</H2>
      <UL items={[
        <><strong>Category sections</strong> — Dividend &amp; Income, Value &amp; Quality, Growth &amp; Momentum, Technical Signals (+ specialist).</>,
        <><strong>Strategy cards</strong> — themed, icon-coded, with name, description and filter chips.</>,
        <><strong>Tier badges &amp; locking</strong> — Free/Pro/Premium; locked cards route to pricing.</>,
        <><strong>One-click run</strong> — opens the Screener with the strategy applied.</>,
        <><strong>Sector Screens</strong> — jump straight into a single GICS sector.</>,
        <><strong>Community Picks</strong> — run screens shared by other users (Pro/Premium); save your own as public from the Screener.</>,
        <><strong>Stats summary</strong> — total and per-tier/sector/community counts.</>,
        <><strong>Help drawer</strong> — an in-page “Scans Guide” explaining how the screens and categories work.</>,
      ]} />
      <H3>Step-by-step: using a screen</H3>
      <OL items={[
        'Open /scans (Alpha Screens).',
        'Pick a category that matches your goal (e.g. Dividend & Income).',
        'Read the cards; note the tier badge and the filter chips.',
        'Click a screen — the Screener opens with it applied and the results listed.',
        'Sort, tweak thresholds, add columns or export as needed.',
        'Click any result to open its Company page, or save the (tweaked) screen as your own.',
      ]} />

      {/* 7 */}
      <H2 id="a-technical">7. Technical Details</H2>
      <H3>Frontend</H3>
      <UL items={[
        <>Page: <Code>frontend/app/scans/page.tsx</Code>; each strategy renders via the <Code>ScanCard</Code> component (icon, theme, tier badge, lock).</>,
        <>Plan flags: <Code>isPro</Code> / <Code>isPremium</Code> / <Code>isAdmin</Code> drive lock state and Community Picks visibility; <Code>presetTier()</Code> maps each preset id to free/pro/premium.</>,
        <>Categories are defined in a <Code>CATEGORIES</Code> array that groups preset ids into themes.</>,
      ]} />
      <H3>Backend &amp; data flow</H3>
      <Table head={['Endpoint', 'Feeds', 'Source']} rows={[
        [<Code>GET /screener/presets</Code>, 'The pre-built strategy definitions (name, description, filters, tier).', 'Defined in get_screener_presets()'],
        [<Code>GET /screener community</Code>, 'Community Picks (public saved screens), gated by plan rank.', <Code>screener.saved_screens</Code>],
        [<Code>GET /market/sectors</Code>, 'Sector list + stock counts for Sector Screens.', <Code>screener.universe</Code>],
        [<span><Code>POST /screener</Code> + <Code>/screener/query</Code></span>, 'Runs the applied strategy when the Screener opens.', <Code>screener.universe</Code>],
      ]} />
      <UL items={[
        <><strong>Presets</strong> are server-defined filter sets (id, name, description, <Code>filters[]</Code>, sort, <Code>premium</Code>/<Code>min_plan</Code>). They are <em>not</em> stored results — clicking re-runs them live, so results stay current.</>,
        <><strong>Community Picks</strong> come from <Code>screener.saved_screens</Code> with a <Code>creator_plan</Code> column; the API filters by <Code>PLAN_RANK</Code> so Pro users don’t see Premium-created screens, and free users get a 403 (the UI shows an upgrade card).</>,
        <><strong>Access:</strong> enforced on both the frontend (locked cards) and backend (plan checks) — locking is never client-only.</>,
        <><strong>Caching / performance:</strong> the presets list is small and cached; running a screen reuses the standard, indexed Screener query path. Loading/error states are handled per section.</>,
      ]} />

      {/* 8 */}
      <H2 id="a-examples">8. Usage Examples</H2>
      <UL items={[
        <><strong>Run a strategy:</strong> click “Value + Fully Franked” → the Screener opens showing low-P/E, 100%-franked, profitable ASX stocks, sorted by grossed-up yield.</>,
        <><strong>Read a tier badge:</strong> a “Premium” badge on “AI Ranked Top 5” means you need Premium; clicking on a lower plan routes you to pricing.</>,
        <><strong>Sector screen:</strong> click “Materials” to instantly list every Materials stock in the Screener, ready to refine.</>,
        <><strong>Community pick:</strong> open a shared “High Yield Franked Miners” screen, run it, then tweak the franking threshold to taste.</>,
        <><strong>Make it your own:</strong> after tweaking a preset in the Screener, Save it (optionally Public) so it appears in Community Picks for others.</>,
        <><strong>Screen → research:</strong> from any result, click the ticker to open its Company page and validate the idea.</>,
      ]} />

      {/* 9 */}
      <H2 id="a-support">9. Quick Reference (Support)</H2>
      <Table head={['Question / issue', 'Answer']} rows={[
        ['“A screen is locked.”', 'It’s a Pro or Premium strategy. Free users can run the Free screens; upgrade to unlock the rest.'],
        ['“Community Picks shows an upgrade card.”', 'Community Picks are Pro/Premium. Pro users see free/Pro screens; Premium sees all.'],
        ['“I clicked a screen and it opened the Screener.”', 'That’s by design — the screen runs in the full Screener so you can tweak, sort and export.'],
        ['“Results changed since last time.”', 'Screens run live against nightly-rebuilt data, so results update as the market/data does.'],
        ['“A Query Mode community screen won’t open for me.”', 'Query Mode is Pro/Premium; free users get an upgrade prompt for those.'],
      ]} />

      {/* 10 */}
      <H2 id="a-future">10. Future Improvements</H2>
      <UL items={[
        <><strong>Backtest preview</strong> — show how each strategy would have performed historically.</>,
        <><strong>Result counts on cards</strong> — “matches 42 stocks today” before you click.</>,
        <><strong>Favourite / pin screens</strong> and a “recently run” list.</>,
        <><strong>Alerts on a screen</strong> — notify when a new stock enters/leaves a saved strategy.</>,
        <><strong>More categories &amp; ASX-specific strategies</strong> (e.g. capital-raise plays, short-squeeze candidates).</>,
        <><strong>Community ratings</strong> — upvote/sort the most useful shared screens.</>,
        <><strong>One-click compare</strong> — run two strategies side by side.</>,
        <><strong>Scheduled emails</strong> — “your weekly Dividend Aristocrats shortlist”.</>,
        <><strong>Mobile improvements</strong> — swipeable category carousels and condensed cards.</>,
      ]} />

      <div className="mt-10 pt-4 border-t border-slate-200 text-xs text-slate-400">
        Internal documentation — Admin only. Reflects the Alpha Screens page as built. Update this manual when the page changes.
      </div>
    </div>
  )
}

// ── Stock Screener manual ─────────────────────────────────────────────────────
const STOC = [
  ['s-overview',   '1. Page Overview'],
  ['s-benefits',   '2. User Benefits'],
  ['s-sections',   '3. Sections Covered'],
  ['s-modes',      '4. Screener Modes'],
  ['s-results',    '5. Results Table'],
  ['s-features',   '6. Functional Features'],
  ['s-technical',  '7. Technical Details'],
  ['s-examples',   '8. Usage Examples'],
  ['s-support',    '9. Quick Reference (Support)'],
  ['s-future',     '10. Future Improvements'],
]
function ScreenerManual() {
  return (
    <div>
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-6">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">On this page</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1">
          {STOC.map(([id, label]) => <a key={id} href={`#${id}`} className="text-sm text-blue-600 hover:underline">{label}</a>)}
        </div>
      </div>

      {/* 1 */}
      <H2 id="s-overview">1. Page Overview</H2>
      <H3>What is the Stock Screener?</H3>
      <P>The <strong>Stock Screener</strong> (<Code>/screener</Code>) is the core research tool of ASX Screener — a fully customisable filter engine that lets users build any combination of conditions across <strong>263+ financial, technical, and quality metrics</strong> and instantly see every ASX-listed stock that matches. Results are sorted, paginated, exportable, and link directly to Company Detail pages.</P>
      <H3>Purpose</H3>
      <P>To answer: <strong>"Which ASX stocks meet my exact criteria right now?"</strong> The Screener replaces hours of spreadsheet work with a real-time, data-driven shortlist generator — useful for stock discovery, strategy validation, and research workflow.</P>
      <H3>How it fits into the platform</H3>
      <P>The Screener is the <strong>execution layer</strong>: Alpha Screens provides curated one-click strategies that open <em>here</em>; the Market Overview surfaces themes that link <em>here</em>; the Heatmap's sector clicks land <em>here</em>. The Screener is where ideas become filtered shortlists.</P>

      {/* 2 */}
      <H2 id="s-benefits">2. User Benefits</H2>
      <Table head={['User type', 'How they use the Screener']} rows={[
        ['Value investors', 'Filter by low P/E, P/B and high F-Score + profitable → shortlist of undervalued quality stocks.'],
        ['Income investors', 'Filter by dividend yield ≥ 5%, franking = 100%, net margin > 0 → fully franked income list.'],
        ['Growth investors', 'Filter by revenue growth 3Y CAGR > 20%, ROE > 15% → growing quality companies.'],
        ['Technical traders', 'Filter by RSI ≤ 30, price above 200-day MA → oversold stocks in uptrends.'],
        ['Power users (admin/Pro)', 'Use Query Mode or AI Mode to express complex multi-condition logic.'],
        ['All users', 'Load a community screen or Alpha Screen preset, then refine it to taste.'],
      ]} />

      {/* 3 */}
      <H2 id="s-sections">3. Sections Covered</H2>
      <H3>Filter panel (top)</H3>
      <P>The primary workspace where users add, edit, and remove filter rows. Each row has: field selector (263+ fields in category groups), operator, and value. Multiple filters always AND together. A "stale" banner appears when filters have changed but results haven't been re-run.</P>
      <H3>Mode toggle bar</H3>
      <P>Three modes: <strong>Manual</strong> (visual filter builder), <strong>AI Mode</strong> (natural-language input, Pro/Premium), <strong>Query Mode</strong> (SQL-like syntax, admin/Pro/Premium). The mode toggle is visible at the top of the filter panel.</P>
      <H3>Market cap quick-filter</H3>
      <P>Seven one-click size tiers above the filter rows: All / Mega ≥$50B / Large $10B–$50B / Mid $2B–$10B / Small $300M–$2B / Micro $50M–$300M / Nano &lt;$50M. Clicking adds a market_cap range filter automatically.</P>
      <H3>Sector browser</H3>
      <P>Browse by GICS sector — one click adds a sector filter. Also reached from the Market Overview heatmap or sector screens on Alpha Screens.</P>
      <H3>Alpha Screens presets</H3>
      <P>A dropdown of all pre-built strategies. Selecting one replaces the current filters with that strategy's filter set and runs it. The active preset name is shown; editing a filter clears the preset label.</P>
      <H3>My Screens / Community Picks</H3>
      <P>Saved personal screens and community-shared screens. "My Screens" panel lists your saves with edit/delete options. Community screens are run via <Code>?screen=id</Code> URL param or from the Alpha Screens page.</P>
      <H3>Results table</H3>
      <P>Paginated results (default 50 per page) with sortable columns, colour-coded value cells, watchlist button per row, and links to each company's detail page.</P>
      <H3>Column picker</H3>
      <P>Customise which columns appear. Choices persist to <Code>localStorage</Code> across sessions. Code and Company Name are always visible; all others are toggleable.</P>
      <H3>Export</H3>
      <P>Download all results as CSV (not just the current page). Available in all modes.</P>

      {/* 4 */}
      <H2 id="s-modes">4. Screener Modes</H2>
      <H3>Manual Mode (default — all plans)</H3>
      <P>A structured filter-builder UI. Each row is: field → operator → value. Fields are grouped by category (Valuation, Profitability, Growth, Dividends, Financial Health, Technicals, etc.). Operators: ≥, ≤, &gt;, &lt;, =, ≠ for numbers; is true/false for booleans; = / ≠ for text. All filters are ANDed.</P>
      <Callout tone="blue" title="How filter values work">
        Values are entered in user-facing units. Percentage fields: type <Code>15</Code> for 15%. Dollar fields: type in AUD. The backend applies scale factors automatically.
      </Callout>
      <H3>AI Mode (Pro / Premium)</H3>
      <P>Type a plain-English description of what you want, e.g. <em>"Profitable miners under $1B market cap"</em> or <em>"REITs with low debt and positive earnings."</em> Claude parses the request and generates a set of filters, which are shown to the user for review before running. Powered by <Code>POST /api/v1/screener/nl</Code>.</P>
      <H3>Query Mode (Admin / Pro / Premium)</H3>
      <P>A monospace textarea for SQL-WHERE-style expressions, e.g. <Code>roe &gt; 15 AND (roce &gt; 12 OR roic &gt; 12)</Code>. Supports OR logic and nested parentheses — something Manual Mode's AND-only builder cannot express. A searchable <strong>Field Reference</strong> panel sits below with all 263 fields, their aliases, units and categories; click any field to insert it at the cursor. Keyboard shortcut: Ctrl+Enter to run. Powered by <Code>POST /api/v1/screener/query</Code> with a safe parser that whitelists field names and parameterises all values.</P>
      <Callout tone="amber" title="Security in Query Mode">
        No raw SQL reaches the database. The backend parser maps field names through the ALLOWED_FIELDS whitelist and parameterises every value — SQL injection is structurally impossible.
      </Callout>

      {/* 5 */}
      <H2 id="s-results">5. Results Table</H2>
      <H3>Default columns</H3>
      <P>Code, Company, Sector, Price, Mkt Cap, P/E, ROE %, Div Yield, Grossed-Up Yield, Franking, F-Score, 1Y Return.</P>
      <H3>Optional columns (toggle via Column Picker)</H3>
      <P>Forward P/E, P/B, EV/EBITDA, Net Margin, EBITDA Margin, Gross Margin, Rev Growth 1Y, Rev HoH ★, EPS HoH ★, D/E, Current Ratio, Altman Z, RSI 14, YTD Return, 3M Return, Short %, Volume.</P>
      <H3>Colour-coding</H3>
      <UL items={[
        <><strong>ROE</strong>: green when ≥ 15%.</>,
        <><strong>Grossed-Up Yield</strong>: green when ≥ 6%.</>,
        <><strong>Franking</strong>: green badge (100%), yellow (&gt;0%), grey (0%).</>,
        <><strong>F-Score</strong>: green badge (7–9), yellow (4–6), red (0–3).</>,
        <><strong>1Y / YTD / 3M Return</strong>: green positive, red negative.</>,
        <><strong>Altman Z</strong>: green ≥ 2.99, yellow 1.81–2.99, red &lt; 1.81.</>,
        <><strong>RSI 14</strong>: red ≥ 70 (overbought), green ≤ 30 (oversold).</>,
        <><strong>D/E</strong>: red when &gt; 2×.</>,
        <><strong>Current Ratio</strong>: green ≥ 1.5, red &lt; 1.</>,
        <><strong>Short %</strong>: red when ≥ 5%.</>,
      ]} />
      <H3>Sorting</H3>
      <P>Click any column header to sort ascending; click again for descending. Sort persists between pages. Default sort: Market Cap descending.</P>
      <H3>Pagination</H3>
      <P>50 results per page, with prev/next controls and a total-count display. Export always downloads all pages (not just current).</P>
      <H3>Cap warning</H3>
      <P>If the server returns a capped result set (e.g. free-tier export limits), a banner explains the cap and suggests upgrading.</P>

      {/* 6 */}
      <H2 id="s-features">6. Functional Features</H2>
      <UL items={[
        <><strong>263+ filter fields</strong> — grouped by category; searchable in the field dropdown.</>,
        <><strong>Three modes</strong> — Manual (all), AI (Pro/Premium), Query (admin/Pro/Premium).</>,
        <><strong>Market cap quick-filter</strong> — one click for 7 size tiers.</>,
        <><strong>Sector browser</strong> — filter to a GICS sector instantly.</>,
        <><strong>Preset library</strong> — load any Alpha Screen strategy; active preset name shown in toolbar.</>,
        <><strong>Save screens</strong> — save your filter set with a name and description; optionally make it public (Community Picks).</>,
        <><strong>My Screens</strong> — view, run, edit and delete your saved screens.</>,
        <><strong>URL params</strong> — <Code>?preset=id</Code>, <Code>?sector=X</Code>, <Code>?index=ASX200</Code>, <Code>?screen=id</Code> all auto-apply on load; shareable links.</>,
        <><strong>Column picker</strong> — toggle optional columns; persists to localStorage.</>,
        <><strong>Watchlist button</strong> — add any result to your watchlist (star icon per row).</>,
        <><strong>CSV export</strong> — download all matched results.</>,
        <><strong>Help drawer</strong> — in-page guide for the Screener (via <Code>SCREENER_SECTIONS</Code>).</>,
        <><strong>Stale indicator</strong> — a banner prompts re-run when filters change after a run.</>,
      ]} />
      <H3>Step-by-step: building a screen</H3>
      <OL items={[
        'Open /screener.',
        'Click "+ Add Filter" to add a filter row.',
        'Select a field from the grouped dropdown (e.g. Dividend & Income → Dividend Yield).',
        'Choose an operator (≥) and enter a value (e.g. 5).',
        'Repeat for additional conditions (e.g. Franking % = 100, Net Margin ≥ 0).',
        'Click "Run Screen" — results appear in the table below.',
        'Sort by any column; toggle optional columns via the Columns button.',
        'Click a ticker to open its Company Detail page.',
        'Optionally save the screen (name, description, public/private) or export to CSV.',
      ]} />

      {/* 7 */}
      <H2 id="s-technical">7. Technical Details</H2>
      <H3>Frontend</H3>
      <UL items={[
        <>Page: <Code>frontend/app/screener/page.tsx</Code> — a single large client-side page (~1000+ lines). State: filters, mode, results, sort, pagination, column visibility, AI result, query text, saved screens.</>,
        <><Code>ALL_COLUMNS</Code>: typed array of column definitions with key, label, sortKey, default flag, always flag, and render function.</>,
        <>Column visibility persisted in <Code>localStorage</Code> under <Code>screener_visible_columns_v1</Code>.</>,
        <>Market cap tiers defined in <Code>CAP_TIER_RANGES</Code> (values in AUD millions — backend multiplies by 1,000,000).</>,
        <>URL params handled in a <Code>useEffect</Code> on mount: preset, sector, index, screen.</>,
        <>Sector component: <Code>frontend/app/screener/components/BrowseSectors.tsx</Code>.</>,
      ]} />
      <H3>API endpoints</H3>
      <Table head={['Endpoint', 'Mode', 'What it does']} rows={[
        [<Code>GET /api/v1/screener/fields</Code>, 'All', 'Returns all 263 fields with metadata (key, label, type, category, unit, scale) for the filter builder.'],
        [<Code>GET /api/v1/screener/presets</Code>, 'All', 'Returns preset strategy definitions (id, name, description, filters, min_plan).'],
        [<Code>POST /api/v1/screener</Code>, 'Manual', 'Runs the filter array against screener.universe; returns paginated ScreenerRow list.'],
        [<Code>POST /api/v1/screener/nl</Code>, 'AI', 'Sends natural-language query to Claude; returns parsed filters + results.'],
        [<Code>POST /api/v1/screener/query</Code>, 'Query', 'Parses SQL-like text, maps to ALLOWED_FIELDS, runs safe parameterised query.'],
        [<Code>GET /api/v1/screener/query/fields</Code>, 'Query', 'Returns field reference list for the Field Reference panel.'],
        [<Code>POST /api/v1/screener/export</Code>, 'Manual', 'Returns CSV of all matched results.'],
        [<Code>POST /api/v1/screens</Code> + <Code>GET</Code> + <Code>PUT</Code> + <Code>DELETE</Code>, 'All', 'Save/load/edit/delete personal screens.'],
        [<Code>GET /api/v1/screens/community</Code>, 'All', 'Returns community-shared screens (plan-gated).'],
      ]} />
      <H3>Data source</H3>
      <P>All screener results come from <Code>screener.universe</Code> — a wide PostgreSQL table rebuilt nightly from EODHD prices, financial statements, ASIC short data, and computed ratios. It covers all listed ASX stocks with an active trading status. Data is end-of-day; the nightly build typically completes between 8–10pm AEST.</P>

      {/* 8 */}
      <H2 id="s-examples">8. Usage Examples</H2>
      <UL items={[
        <><strong>Fully franked income screen:</strong> Dividend Yield ≥ 5%, Franking % = 100, Net Margin ≥ 0 → profitable, 100%-franked, high-yield stocks.</>,
        <><strong>Value + quality screen:</strong> P/E ≤ 15, P/B ≤ 1.5, F-Score ≥ 7 → cheap stocks with strong accounting signals.</>,
        <><strong>Momentum screen:</strong> 1Y Return ≥ 20%, RSI 14 ≥ 50, Price / 200-Day MA ≥ 1 → stocks in uptrends with momentum.</>,
        <><strong>AI Mode:</strong> type "small cap healthcare companies with no debt and positive earnings" → AI generates filters automatically.</>,
        <><strong>Query Mode:</strong> <Code>roe &gt; 20 AND (revenue_cagr_3y &gt; 0.15 OR revenue_growth_1y &gt; 0.20)</Code> → high-ROE companies with accelerating revenue, using OR logic impossible in Manual Mode.</>,
        <><strong>Index membership:</strong> open <Code>/screener?index=ASX200</Code> to auto-filter to ASX 200 constituents.</>,
        <><strong>Save and share:</strong> after building a screen, click Save → toggle "Public" → the screen appears in Community Picks for other users.</>,
      ]} />

      {/* 9 */}
      <H2 id="s-support">9. Quick Reference (Support)</H2>
      <Table head={['Question / issue', 'Answer']} rows={[
        ['"Run Screen does nothing."', 'Check that at least one filter has a valid value, or that no filter value is blank. A blank value is skipped by the builder.'],
        ['"I can\'t see AI Mode / Query Mode."', 'AI Mode is Pro/Premium. Query Mode is Admin/Pro/Premium. Upgrade or check login plan.'],
        ['"Results show a \'capped\' banner."', 'The result set is capped — usually a plan limit on export or result size. Upgrade or narrow the filters.'],
        ['"My saved screen disappeared."', 'Saved screens are per-user in the backend. If the user is logged in on a different account, their screens won\'t show. Also check My Screens panel is open.'],
        ['"Filters say \'stale\' but I haven\'t changed anything."', 'The stale banner appears after any filter edit. Click Run Screen to refresh results.'],
        ['"How do I filter to the ASX 200?"', 'Add a filter: Is ASX 200 = true. Or open /screener?index=ASX200.'],
        ['"Column choices don\'t persist."', 'Column visibility is saved to localStorage. If the user cleared their browser storage, choices reset. They must re-select.'],
      ]} />

      {/* 10 */}
      <H2 id="s-future">10. Future Improvements</H2>
      <UL items={[
        <><strong>OR logic in Manual Mode</strong> — currently only Query Mode supports OR. A visual OR toggle between filter groups would help non-technical users.</>,
        <><strong>Screener alerts</strong> — notify when a stock enters or exits the results of a saved screen.</>,
        <><strong>More preset strategies</strong> — additional built-in screens for Mining, A-REIT, short-squeeze, capital-raise plays.</>,
        <><strong>Analyst consensus data</strong> — forward EPS, revenue forecasts and price targets as filterable fields (pending EODHD plan upgrade).</>,
        <><strong>Beta 1Y field</strong> — computed beta relative to the ASX 200, planned.</>,
        <><strong>Saved column presets</strong> — name and save a column configuration (e.g. "Income view", "Technical view").</>,
        <><strong>Result charts inline</strong> — mini sparkline per row for price trend without leaving the table.</>,
        <><strong>Screener history</strong> — replay a past screen run to see how results have changed over time.</>,
      ]} />

      <div className="mt-10 pt-4 border-t border-slate-200 text-xs text-slate-400">
        Internal documentation — Admin only. Reflects the Stock Screener as built. Update this manual when modes, fields, or features change.
      </div>
    </div>
  )
}

// ── Metrics Glossary manual ───────────────────────────────────────────────────
const GTOC = [
  ['g-overview',   '1. Page Overview'],
  ['g-benefits',   '2. User Benefits'],
  ['g-sections',   '3. Sections Covered'],
  ['g-data',       '4. How to Read a Metric Card'],
  ['g-categories', '5. Metric Categories'],
  ['g-features',   '6. Functional Features'],
  ['g-technical',  '7. Technical Details'],
  ['g-examples',   '8. Usage Examples'],
  ['g-support',    '9. Quick Reference (Support)'],
  ['g-future',     '10. Future Improvements'],
]
function GlossaryManual() {
  return (
    <div>
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-6">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">On this page</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1">
          {GTOC.map(([id, label]) => <a key={id} href={`#${id}`} className="text-sm text-blue-600 hover:underline">{label}</a>)}
        </div>
      </div>

      {/* 1 */}
      <H2 id="g-overview">1. Page Overview</H2>
      <H3>What is the Metrics Glossary?</H3>
      <P>The <strong>Metrics Glossary</strong> (<Code>/glossary</Code>) is an <strong>investment education library</strong> — a searchable, categorised reference for every financial and technical metric used across the ASX Screener platform. It currently covers <strong>283 metrics</strong> across <strong>9 categories</strong>, with plain-English definitions, calculation formulas, real-world worked examples, industry benchmarks, and beginner explanations for many entries.</P>
      <H3>Purpose</H3>
      <P>To make <em>every number visible in the platform</em> fully understandable. When a user sees "Altman Z-Score" or "FCF Yield" in the Screener and wonders what it means, the Glossary gives them the complete picture — not just a one-liner tooltip, but a full definition, formula, interpretation guide, and example.</P>
      <H3>What problem it solves</H3>
      <UL items={[
        <><strong>Knowledge gap</strong> — most investors can't name 50 financial ratios. The Glossary makes professional-level analysis accessible to everyone.</>,
        <><strong>Interpretation uncertainty</strong> — knowing a P/E is 22× is useless without knowing whether that's cheap or expensive for the sector. The Glossary provides context.</>,
        <><strong>Confidence in the Screener</strong> — users who understand their filters make better decisions; the Glossary turns passive users into active analysts.</>,
      ]} />
      <H3>Plan gating</H3>
      <P>The Glossary is a <strong>Pro &amp; Premium</strong> feature (shown with a badge in the page header). Free users see an upgrade prompt via <Code>PlanGate</Code>. The full content is available to Pro and above.</P>

      {/* 2 */}
      <H2 id="g-benefits">2. User Benefits</H2>
      <Table head={['User type', 'How they use the Glossary']} rows={[
        ['Beginners', 'Learn the fundamentals with plain-English "Simple Explanation" tips and worked numerical examples.'],
        ['Intermediate investors', 'Look up formulas, benchmarks and sector norms to calibrate their Screener filter thresholds correctly.'],
        ['Experienced analysts', 'Quick-reference for ASX-specific nuances (franking, REIT metrics, mining metrics) not covered elsewhere.'],
        ['Support team', 'Point users to the Glossary to answer "what does X mean?" without needing a manual response.'],
        ['Product & engineering', 'Authoritative source of metric definitions, formulas, and tags — useful when adding new fields to the Screener.'],
      ]} />

      {/* 3 */}
      <H2 id="g-sections">3. Sections Covered</H2>
      <H3>Page header</H3>
      <P>Shows the total metric count, number of categories, how many have formulas, how many have benchmarks, and how many have beginner tips — giving users an instant sense of depth.</P>
      <H3>Category sidebar (desktop) / pill bar (mobile)</H3>
      <P>9 colour-coded category buttons, each with a live count. Clicking one filters the metric list to that category. On mobile these become horizontally scrollable pill chips.</P>
      <H3>Search bar</H3>
      <P>Free-text search across metric name, short description, full definition, tags and where-used labels. Results update instantly as you type.</P>
      <H3>Quick-filter chips</H3>
      <P>Five one-click filter chips to narrow by attribute:</P>
      <UL items={[
        <><strong>∑ Has Formula</strong> — only metrics that include a calculation formula.</>,
        <><strong>⬡ Has Benchmark</strong> — metrics with sector or market benchmarks / ranges.</>,
        <><strong>🔍 Used in Screener</strong> — metrics that appear as filter fields in the Screener.</>,
        <><strong>🏆 Used in AlphaFive</strong> — metrics that power the AI-ranked AlphaFive Top 5 screen.</>,
        <><strong>✦ Beginner Friendly</strong> — metrics with a plain-English "Simple Explanation" box.</>,
      ]} />
      <H3>Metric cards list</H3>
      <P>The main content area: one card per metric, collapsed by default and expandable on click. An <strong>Expand All / Collapse All</strong> button lets you open every card at once (useful for printing or in-depth review).</P>
      <H3>Results bar</H3>
      <P>Shows "<em>N</em> of 283 metrics in [Category]" so the user always knows how many results match the current filters.</P>

      {/* 4 */}
      <H2 id="g-data">4. How to Read a Metric Card</H2>
      <P>Each card has a collapsed header (always visible) and an expanded details panel (click to reveal):</P>
      <H3>Card header (always visible)</H3>
      <Table head={['Element', 'What it shows']} rows={[
        ['Category badge', 'Colour-coded category (e.g. blue = Valuation, green = Profitability).'],
        ['Beginner Friendly badge', 'Green ✦ badge when a plain-English tip exists for this metric.'],
        ['Metric name', 'Full formal name (e.g. "P/E Ratio (Price-to-Earnings)").'],
        ['Short description', 'One-line plain-English summary (e.g. "How much investors pay for each dollar of earnings").'],
        ['∑ formula chip', 'Appears when a calculation formula is defined.'],
        ['⬡ benchmark chip', 'Appears when sector benchmarks or ranges are defined.'],
        ['Expand arrow', 'Click anywhere on the header to toggle the details panel.'],
      ]} />
      <H3>Expanded card — detail sections</H3>
      <Table head={['Section', 'What it shows']} rows={[
        ['💡 Simple Explanation', 'Amber callout: a plain-English analogy for beginners (shown only on beginner-tagged metrics).'],
        ['What it measures', 'Full definition in clear, precise language.'],
        ['∑ Formula / Calculation', 'Dark code block with the exact formula (e.g. P/E = Share Price ÷ EPS).'],
        ['Real-World Example', 'Blue callout: a worked numerical example so the user can see the maths in action.'],
        ['How to Interpret It', 'Guidance on what high/low values mean, red flags, comparisons to make.'],
        ['⬡ Benchmarks & Ranges', 'Purple callout: sector-specific typical ranges so the user knows if a value is cheap/expensive.'],
        ['Related Metrics', 'Clickable chips linking to other metrics in the same theme.'],
        ["Where you'll see this", 'Blue chips: which platform areas use this metric (Screener, Company Detail, Financials Tab, etc.).'],
        ['Tags', 'Grey hashtag chips for search keywords associated with this metric.'],
      ]} />

      {/* 5 */}
      <H2 id="g-categories">5. Metric Categories</H2>
      <Table head={['Category', 'Colour', 'What it covers']} rows={[
        ['Valuation', 'Blue', 'P/E, P/B, P/S, EV/EBITDA, PEG, Graham Number, FCF Yield — how cheap or expensive a stock is.'],
        ['Profitability', 'Emerald', 'Gross margin, EBITDA margin, net margin, ROE, ROIC, ROCE, efficiency ratios — how well the company earns.'],
        ['Growth', 'Violet', 'Revenue/earnings/EBITDA CAGRs over 1Y/3Y/5Y/7Y/10Y, BVPS CAGR — how fast the business is expanding.'],
        ['Dividends & Income', 'Amber', 'Dividend yield, franking, payout ratio, DPS, dividend CAGR — income-focused metrics.'],
        ['Financial Health', 'Rose', 'Debt ratios, current ratio, Altman Z-Score, interest cover, working capital, cash flow — balance sheet strength.'],
        ['Technical Indicators', 'Cyan', 'RSI, MACD, Bollinger Bands, moving averages, ATR, momentum signals — price and volume analysis.'],
        ['Price & Returns', 'Orange', 'Price changes, total return, 52-week high/low, beta, performance periods — market price data.'],
        ['Quality Scores', 'Purple', 'Piotroski F-Score, Altman Z-Score, composite quality scores, capital efficiency score — composite ratings.'],
        ['ASX-Specific', 'Green', 'Franking credits, grossed-up yield, mining metrics, REIT metrics — metrics unique to the Australian market.'],
      ]} />

      {/* 6 */}
      <H2 id="g-features">6. Functional Features</H2>
      <UL items={[
        <><strong>Full-text search</strong> — searches name, description, definition, tags and where-used simultaneously.</>,
        <><strong>Category filtering</strong> — sidebar (desktop) and pill bar (mobile); click "All Metrics" to reset.</>,
        <><strong>Quick filters</strong> — multi-select chips for Formula, Benchmark, Screener, AlphaFive, Beginner Friendly. Multiple chips AND together (e.g. "has formula AND used in Screener").</>,
        <><strong>Combinable filters</strong> — search, category, and quick filters all apply simultaneously.</>,
        <><strong>Expand All / Collapse All</strong> — global toggle to open or close every card at once.</>,
        <><strong>Beginner Friendly highlights</strong> — amber tip boxes and green badges surface approachable content for new investors.</>,
        <><strong>Related metrics</strong> — cards cross-link to related entries, guiding deeper exploration.</>,
        <><strong>Where-used tags</strong> — users can see which platform screens or tabs reference each metric.</>,
        <><strong>Colour-coded category accents</strong> — each card's top border matches its category colour for quick visual scanning.</>,
        <><strong>Plan gate</strong> — free users see an upgrade prompt; Pro/Premium get full access.</>,
      ]} />
      <H3>Step-by-step: looking up a metric</H3>
      <OL items={[
        'Open /glossary.',
        'Type the metric name (e.g. "Altman Z") in the search bar — results filter instantly.',
        'Click the card to expand it.',
        'Read the definition, formula, example and benchmarks.',
        'Check "Where you\'ll see this" to know which Screener fields or Company tabs use it.',
        'Follow Related Metrics chips to explore connected concepts.',
      ]} />

      {/* 7 */}
      <H2 id="g-technical">7. Technical Details</H2>
      <H3>Frontend architecture</H3>
      <UL items={[
        <>Page: <Code>frontend/app/glossary/page.tsx</Code> — a <strong>fully client-side</strong> page; all 283 metric objects are bundled statically (no API calls at runtime).</>,
        <><Code>METRICS</Code>: a typed <Code>Metric[]</Code> array of objects. Each object has: <Code>id</Code>, <Code>name</Code>, <Code>category</Code>, <Code>shortDesc</Code>, <Code>definition</Code>, optional <Code>formula</Code>, <Code>interpretation</Code>, <Code>benchmark</Code>, <Code>example</Code>, <Code>beginnerTip</Code>, <Code>beginner</Code>, <Code>relatedMetrics</Code>, <Code>usedIn[]</Code>, <Code>tags[]</Code>.</>,
        <><Code>CATEGORIES</Code>: 9 category config objects with <Code>key</Code>, <Code>label</Code>, <Code>colour</Code> (Tailwind badge class), and <Code>bar</Code> (Tailwind accent bar class).</>,
        <>State: <Code>search</Code>, <Code>activeCat</Code>, <Code>activeQF</Code> (Set), <Code>expandAll</Code> (<Code>boolean | null</Code>).</>,
        <><Code>filtered</Code> is a <Code>useMemo</Code> — category filter → quick filter → search, applied in order. No debounce needed (in-memory, instantaneous).</>,
        <><Code>MetricCard</Code> component: its <Code>open</Code> state is managed locally (per card); it listens to the <Code>expandAll</Code> prop via <Code>useEffect</Code> to sync with the global toggle.</>,
        <>Plan gate: <Code>&lt;PlanGate minPlan="pro"&gt;</Code> wraps the full <Code>GlossaryContent</Code>. Free users see the upgrade prompt; the metric data is still bundled but the UI is not rendered.</>,
      ]} />
      <H3>Data management</H3>
      <UL items={[
        <>All 283 metrics are <strong>statically defined in the source file</strong>. There is no database or API for the Glossary. This means changes to metric content require a code change and redeploy.</>,
        <>Adding a new metric: add a new object to the <Code>METRICS</Code> array in <Code>frontend/app/glossary/page.tsx</Code> with the correct category key matching one of the 9 values in <Code>CATEGORIES</Code>.</>,
        <>Counts displayed in the page header (total metrics, with formulas, with benchmarks, with beginner tips) are computed dynamically from the <Code>METRICS</Code> array at render time — no manual maintenance needed.</>,
      ]} />
      <Callout tone="amber" title="Adding or updating metrics">
        Since the Glossary is statically bundled, any new Screener field should have a corresponding Glossary entry added at the same time. Match the <Code>id</Code> to the screener field key and list <Code>usedIn: ['Screener', ...]</Code>.
      </Callout>

      {/* 8 */}
      <H2 id="g-examples">8. Usage Examples</H2>
      <UL items={[
        <><strong>Finding a metric:</strong> type "piotroski" → the F-Score card appears instantly; click to expand and read all 9 signals, the formula and an example.</>,
        <><strong>Learning before screening:</strong> user is about to filter on EV/EBITDA for the first time → opens Glossary, reads the definition and benchmark (10–14× global average), then sets a threshold with confidence.</>,
        <><strong>Sector comparison:</strong> user sees gross margin of 78% and wonders if that's good → opens the Gross Margin card → Benchmarks say "Software: 65–90%" → confirms the stock is well within sector norms.</>,
        <><strong>Beginner path:</strong> filter by "✦ Beginner Friendly" to see only the ~40 most approachable metrics, read the amber Simple Explanation boxes to build foundational knowledge.</>,
        <><strong>Auditing a screen:</strong> before publishing a Community Pick, a power user opens the Glossary to verify their understanding of each filter field they used.</>,
        <><strong>Support deflection:</strong> user emails asking "what is ROIC?" — support team links them to <Code>/glossary</Code> and they find a full definition, formula, example and benchmark.</>,
      ]} />

      {/* 9 */}
      <H2 id="g-support">9. Quick Reference (Support)</H2>
      <Table head={['Question / issue', 'Answer']} rows={[
        ['"I can\'t see the Glossary."', 'The Glossary is Pro & Premium only. Free users see an upgrade prompt. Upgrade at /pricing.'],
        ['"The metric I\'m looking for isn\'t there."', 'Search by abbreviation, keyword or tag (e.g. search "roce" or "capital employed"). If still not found, it may be a new field not yet in the Glossary — log it for the product team.'],
        ['"The formula looks wrong."', 'All formulas are manually maintained in page.tsx. If a formula is incorrect, it needs a code fix and redeploy. Log it as a bug.'],
        ['"How do I find only beginner-friendly metrics?"', 'Click the "✦ Beginner Friendly" quick-filter chip to show only the metrics that have plain-English tip boxes.'],
        ['"How do I print the Glossary?"', 'Click Expand All, then use the browser print function. All cards will be fully expanded for printing.'],
        ['"Can I export the Glossary?"', 'Not yet — export is a planned future feature. For now, print or screenshot.'],
      ]} />

      {/* 10 */}
      <H2 id="g-future">10. Future Improvements</H2>
      <UL items={[
        <><strong>Deep-link to a specific metric</strong> — e.g. <Code>/glossary#pe_ratio</Code> auto-opens that card (useful for tooltips linking out).</>,
        <><strong>In-app tooltip integration</strong> — hover any metric name in the Screener or Company page and see the Glossary definition inline, without leaving the page.</>,
        <><strong>CSV / PDF export</strong> — download the full Glossary as a reference PDF or spreadsheet.</>,
        <><strong>User-contributed notes</strong> — allow Pro/Premium users to add personal notes or annotations to metric cards.</>,
        <><strong>Video explainers</strong> — short 60-second video clips for complex metrics (e.g. Altman Z-Score, Piotroski F-Score).</>,
        <><strong>Comparative benchmarking</strong> — show where a specific company falls on a metric's benchmark scale directly within the card.</>,
        <><strong>Recently viewed history</strong> — remember which metrics a user last opened for quick re-access.</>,
        <><strong>ASX sector norms update</strong> — benchmarks currently reflect global averages; update to ASX-specific norms per GICS sector.</>,
        <><strong>Auto-sync with Screener fields</strong> — when a new field is added to <Code>ALLOWED_FIELDS</Code>, flag it as missing in the Glossary via a CI check.</>,
      ]} />

      <div className="mt-10 pt-4 border-t border-slate-200 text-xs text-slate-400">
        Internal documentation — Admin only. Reflects the Metrics Glossary as built. Update this manual when metric definitions, categories or features change.
      </div>
    </div>
  )
}

// ── Portfolio manual ──────────────────────────────────────────────────────────
const PTOC = [
  ['p-overview',      '1. Page Overview'],
  ['p-benefits',      '2. User Benefits'],
  ['p-sections',      '3. Sections Covered'],
  ['p-tabs',          '4. Portfolio Tabs'],
  ['p-transactions',  '5. Transactions & Import'],
  ['p-features',      '6. Functional Features'],
  ['p-technical',     '7. Technical Details'],
  ['p-examples',      '8. Usage Examples'],
  ['p-support',       '9. Quick Reference (Support)'],
  ['p-future',        '10. Future Improvements'],
]
function PortfolioManual() {
  return (
    <div>
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-6">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">On this page</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1">
          {PTOC.map(([id, label]) => <a key={id} href={`#${id}`} className="text-sm text-blue-600 hover:underline">{label}</a>)}
        </div>
      </div>

      {/* 1 */}
      <H2 id="p-overview">1. Page Overview</H2>
      <H3>What is the Portfolio page?</H3>
      <P>The <strong>Portfolio</strong> page (<Code>/portfolio</Code>) is a <strong>personal portfolio tracker</strong> — users record their ASX holdings and transactions, and the platform calculates live performance (P&amp;L, unrealised gain/loss, total return), income (dividends received and upcoming), allocation breakdowns, estimated tax, and AI-powered portfolio insights.</P>
      <H3>Purpose</H3>
      <P>To give investors a <strong>single place to monitor their actual ASX positions</strong> alongside the screening and research tools — closing the loop between finding stocks (Screener) and tracking ownership (Portfolio).</P>
      <H3>Multiple portfolios</H3>
      <P>Users can maintain more than one portfolio (e.g. super, personal, wife's account). The number of portfolios is plan-gated: <strong>Free: 1, Pro: 10, Premium: 50</strong>. A portfolio selector (top of page) lets users switch, create, rename, or delete portfolios.</P>
      <H3>Plan gating summary</H3>
      <Table head={['Plan', 'Portfolios', 'Available tabs']} rows={[
        ['Free', '1', 'Holdings, Transactions'],
        ['Pro', '10', 'Holdings, Transactions, Chart, Allocation, Dividends, Tax'],
        ['Premium', '50', 'Holdings, Transactions, Chart, Allocation, Dividends, Tax, Insights (AI)'],
      ]} />

      {/* 2 */}
      <H2 id="p-benefits">2. User Benefits</H2>
      <UL items={[
        <><strong>Live P&amp;L</strong> — see your unrealised gain/loss and % return updated with the latest EOD prices, across every holding.</>,
        <><strong>Income planning</strong> — the Dividend Calendar shows upcoming ex-dates and estimated franked income for your specific holdings.</>,
        <><strong>Tax estimation</strong> — the Tax tab calculates estimated CGT (with 50% discount for &gt;12-month holds) and income from dividends.</>,
        <><strong>Allocation awareness</strong> — pie charts by stock and by sector show concentration risk at a glance.</>,
        <><strong>AI Insights</strong> — Premium users get an AI-generated portfolio analysis covering strengths, risks, diversification, income outlook and suggestions.</>,
        <><strong>Transaction history</strong> — a complete ledger of buys, sells and DRP events for record-keeping and cost-base tracking.</>,
        <><strong>Easy import</strong> — upload a CSV of holdings or transactions to bootstrap the portfolio instantly.</>,
      ]} />

      {/* 3 */}
      <H2 id="p-sections">3. Sections Covered</H2>
      <H3>Portfolio selector</H3>
      <P>Top of the page. Shows the active portfolio name and a dropdown to switch between portfolios, create a new one, or rename/delete the current one. Displays the plan limit (e.g. "2 of 10 portfolios").</P>
      <H3>Summary cards row</H3>
      <P>Four headline numbers for the selected portfolio: <strong>Total Value</strong> (current market value of all holdings), <strong>Total Cost</strong> (cost basis including brokerage), <strong>Gain/Loss</strong> (unrealised P&amp;L in dollars), <strong>Return %</strong> (total return %).</P>
      <H3>Tab bar</H3>
      <P>Up to 7 tabs depending on plan: Holdings, Transactions, Chart, Allocation, Dividends, Tax, Insights. Locked tabs for lower plans show an upgrade prompt.</P>
      <H3>Import / Add buttons</H3>
      <P>Two action buttons at the top right: <strong>Import CSV</strong> (bulk upload holdings or transactions) and <strong>+ Add Transaction</strong> (single-transaction modal).</P>

      {/* 4 */}
      <H2 id="p-tabs">4. Portfolio Tabs</H2>
      <H3>Holdings (Free+)</H3>
      <P>A table of current positions: ASX Code, Company, Sector, Quantity, Avg Cost, Current Price, Current Value, P&amp;L ($), P&amp;L (%), and action buttons (Add Transaction for this holding, Remove). Prices come from the nightly EOD data. Gain/loss is colour-coded green/red.</P>
      <H3>Transactions (Free+)</H3>
      <P>The full transaction ledger: date, ASX Code, type (Buy / Sell / DRP), quantity, price per share, brokerage, and a delete button. Sorted by date descending. Transactions drive holdings; adding a sell updates the P&amp;L and cost-base calculations.</P>
      <H3>Chart (Pro+)</H3>
      <P>A line chart of <strong>Portfolio Value Over Time</strong> vs the cost basis line. Period selector: 1M, 3M, 6M, 1Y, 2Y, All. Shows total unrealised gain/loss at the latest data point vs cost. Powered by end-of-day price history applied to the holding quantities.</P>
      <H3>Allocation (Pro+)</H3>
      <P>Two pie charts: <strong>By Stock</strong> (each holding's share of total value, with percentage labels) and <strong>By Sector</strong> (GICS sector concentration). Useful for identifying over-concentration and rebalancing decisions.</P>
      <H3>Dividends (Pro+)</H3>
      <P>The <strong>Dividend Calendar</strong> with two tabs:</P>
      <UL items={[
        <><strong>Upcoming</strong> — ex-dates within the next 6 months for your holdings: ex-date, pay date, DPS amount, quantity held, estimated income, and estimated grossed-up income (if franked). Total upcoming income is shown.</>,
        <><strong>Last 12M</strong> — dividends received over the past 12 months on your holdings. Total received income is shown.</>,
      ]} />
      <H3>Tax (Pro+)</H3>
      <P>An <strong>estimated tax summary</strong> for the current financial year:</P>
      <UL items={[
        <><strong>Realised gains</strong> — proceeds minus cost base for closed positions; applies 50% CGT discount for holdings over 12 months.</>,
        <><strong>Dividend income</strong> — estimated total dividends received in the FY, and estimated franking credits.</>,
        <><strong>Summary</strong> — total estimated assessable income from the portfolio for CGT and income tax purposes.</>,
      ]} />
      <Callout tone="red" title="Tax is an estimate only">
        The Tax tab provides estimates for planning purposes. It is not financial or tax advice — users must verify figures with their accountant or tax professional.
      </Callout>
      <H3>Insights (Premium only)</H3>
      <P>An <strong>AI-generated analysis</strong> of the portfolio. Covers: overall portfolio strengths, key risks or weaknesses, diversification assessment (stock and sector concentration), income and franking picture, and actionable suggestions. Generated on demand — click the "Generate Insights" button. The analysis is based on the current holdings and their fundamental/technical metrics.</P>

      {/* 5 */}
      <H2 id="p-transactions">5. Transactions &amp; Import</H2>
      <H3>Adding a single transaction (modal)</H3>
      <P>Click "+ Add Transaction" to open the modal. Fields: ASX Code, Type (Buy / Sell / DRP), Date, Quantity, Price per Share, Brokerage (optional), Notes (optional). The modal shows a calculated total (quantity × price + brokerage) before confirming.</P>
      <H3>Transaction types</H3>
      <Table head={['Type', 'What it records']} rows={[
        ['Buy', 'Purchase of shares — increases holding quantity and cost basis.'],
        ['Sell', 'Sale of shares — reduces holding quantity and realises P&L.'],
        ['DRP', 'Dividend Reinvestment Plan — shares received in lieu of a cash dividend; treated as a buy at the DRP price.'],
      ]} />
      <H3>CSV import</H3>
      <P>Two import modes — switch via the tab in the Import CSV modal:</P>
      <UL items={[
        <><strong>Holdings import</strong>: CSV with columns <Code>asx_code, quantity, avg_cost, purchase_date</Code>. Useful for a one-time snapshot upload.</>,
        <><strong>Transactions import</strong>: CSV with columns <Code>date, asx_code, type, quantity, price, brokerage</Code>. Uploads a complete transaction history.</>,
      ]} />
      <P>A <strong>Download Template</strong> button in the modal provides a correctly formatted CSV template with example rows. The importer validates, reports a count of imported vs skipped rows, and refreshes the holdings view.</P>

      {/* 6 */}
      <H2 id="p-features">6. Functional Features</H2>
      <UL items={[
        <><strong>Multiple portfolios</strong> — create, switch, rename, delete (plan-limited).</>,
        <><strong>Live portfolio value</strong> — nightly EOD prices applied to current quantities.</>,
        <><strong>Detailed holdings table</strong> — avg cost, current price, unrealised P&amp;L per holding.</>,
        <><strong>Transaction ledger</strong> — full buy/sell/DRP history with brokerage.</>,
        <><strong>Portfolio value chart</strong> — historical value vs cost line, 6 time periods (Pro+).</>,
        <><strong>Allocation pie charts</strong> — by stock and by sector (Pro+).</>,
        <><strong>Dividend Calendar</strong> — upcoming and received dividends for your holdings, with franking detail (Pro+).</>,
        <><strong>Tax summary</strong> — estimated CGT (with 50% discount) and dividend income (Pro+).</>,
        <><strong>AI Portfolio Insights</strong> — on-demand AI analysis of strengths, risks, diversification and income (Premium).</>,
        <><strong>CSV import</strong> — bulk upload holdings or transactions via template CSV.</>,
        <><strong>Company links</strong> — each holding and dividend entry links to the Company Detail page.</>,
        <><strong>Help drawer</strong> — in-page guide (<Code>PORTFOLIO_SECTIONS</Code>) accessible via the help button.</>,
      ]} />

      {/* 7 */}
      <H2 id="p-technical">7. Technical Details</H2>
      <H3>Frontend</H3>
      <UL items={[
        <>Page: <Code>frontend/app/portfolio/page.tsx</Code> — client-side; layout: <Code>frontend/app/portfolio/layout.tsx</Code>.</>,
        <>Plan gates via <Code>PORTFOLIO_LIMITS</Code> (portfolio count) and <Code>TAB_ACCESS</Code> (tab visibility by plan).</>,
        <>Charts: <Code>recharts</Code> — <Code>LineChart</Code> for value history, <Code>PieChart</Code> for allocation.</>,
        <>Formatters: <Code>fmtMoney</Code> (negative-safe "$X,XXX.XX"), <Code>fmtPct</Code> (signed percent), <Code>glColor</Code> (green/red text class).</>,
      ]} />
      <H3>API endpoints</H3>
      <Table head={['Endpoint', 'What it provides']} rows={[
        [<Code>GET /api/v1/portfolios</Code>, 'List all portfolios for the user.'],
        [<Code>POST /api/v1/portfolios</Code>, 'Create a new portfolio.'],
        [<Code>PUT /api/v1/portfolios/{'{id}'}</Code>, 'Rename a portfolio.'],
        [<Code>DELETE /api/v1/portfolios/{'{id}'}</Code>, 'Delete a portfolio.'],
        [<Code>GET /api/v1/portfolios/{'{id}'}/performance</Code>, 'Holdings with live prices, P&L, total value and cost.'],
        [<Code>GET /api/v1/portfolios/{'{id}'}/history?period=1y</Code>, 'Daily value history for the portfolio chart.'],
        [<Code>GET /api/v1/portfolios/{'{id}'}/dividends</Code>, 'Upcoming and received dividends for holdings.'],
        [<Code>GET /api/v1/portfolios/{'{id}'}/tax</Code>, 'Estimated CGT and dividend income for the current FY.'],
        [<Code>GET /api/v1/portfolios/{'{id}'}/insights</Code>, 'AI-generated portfolio analysis (Premium).'],
        [<Code>GET /api/v1/portfolios/{'{id}'}/transactions</Code>, 'Full transaction history.'],
        [<Code>POST /api/v1/portfolios/{'{id}'}/transactions</Code>, 'Add a single transaction.'],
        [<Code>DELETE /api/v1/portfolios/{'{id}'}/transactions/{'{txn_id}'}</Code>, 'Delete a transaction.'],
        [<Code>POST /api/v1/portfolios/{'{id}'}/import/holdings</Code>, 'Bulk import holdings CSV.'],
        [<Code>POST /api/v1/portfolios/{'{id}'}/import/transactions</Code>, 'Bulk import transactions CSV.'],
        [<Code>DELETE /api/v1/portfolios/{'{id}'}/holdings/{'{code}'}</Code>, 'Remove a holding (all transactions for that stock).'],
      ]} />
      <H3>Data flow</H3>
      <P>Holdings are reconstructed from transactions (buy/sell/DRP) at query time. Current prices come from <Code>screener.universe</Code> or the price history tables — the same EOD data as the rest of the platform. Tax calculations run server-side using actual transaction dates and quantities; the 50% CGT discount is applied when holding period exceeds 365 days.</P>

      {/* 8 */}
      <H2 id="p-examples">8. Usage Examples</H2>
      <UL items={[
        <><strong>First setup:</strong> click "Import CSV", download the holdings template, fill in ASX codes / quantities / avg costs, upload → portfolio populates instantly.</>,
        <><strong>Track a new buy:</strong> click "+ Add Transaction" → Buy, enter CBA, 100 shares at $145.50 + $19.95 brokerage → holding updated with new avg cost.</>,
        <><strong>Check income outlook:</strong> open Dividends tab → Upcoming — see which holdings have ex-dates in the next 6 months and estimated income. Useful before FY end.</>,
        <><strong>Check concentration:</strong> Allocation tab → By Sector pie → if Materials is 60% of portfolio, consider diversifying.</>,
        <><strong>Tax prep:</strong> Tax tab → share the CGT summary with your accountant as a starting estimate.</>,
        <><strong>AI Insights:</strong> Premium users click "Generate Insights" on the Insights tab → receive a written analysis flagging high concentration, low income diversification, or overleveraged stocks.</>,
        <><strong>Multi-portfolio:</strong> create a "Super" portfolio and a "Personal" portfolio separately; switch with the portfolio selector at the top.</>,
      ]} />

      {/* 9 */}
      <H2 id="p-support">9. Quick Reference (Support)</H2>
      <Table head={['Question / issue', 'Answer']} rows={[
        ['"I can\'t create another portfolio."', 'You\'ve hit the plan limit (Free: 1, Pro: 10, Premium: 50). Upgrade or delete an unused portfolio.'],
        ['"Tabs like Chart, Dividends, Tax are locked."', 'These are Pro/Premium tabs. Free users only get Holdings and Transactions.'],
        ['"My holdings show — for price."', 'Prices update nightly (EOD). If a stock was just listed or has no recent trade, price data may be missing.'],
        ['"Import CSV returned errors."', 'Check that: (1) the column headers exactly match the template, (2) ASX codes are valid, (3) dates are YYYY-MM-DD format, (4) quantities and prices are numbers.'],
        ['"Dividend Calendar shows nothing upcoming."', 'Holdings must have current quantities and the stocks must have announced upcoming dividends in EODHD data. Check the company page to confirm dividends exist.'],
        ['"Tax tab — the numbers look wrong."', 'Tax figures are estimates only. DRP transactions, corporate actions, and return-of-capital events may not be handled correctly. Always confirm with an accountant.'],
        ['"Insights tab says \'Generate Insights\'."', 'Insights are generated on demand — click the button. Requires Premium plan.'],
      ]} />

      {/* 10 */}
      <H2 id="p-future">10. Future Improvements</H2>
      <UL items={[
        <><strong>Corporate actions support</strong> — handle stock splits, rights issues, spin-offs correctly in cost-base calculations.</>,
        <><strong>FY income report</strong> — a printable summary of all dividends received and franking credits claimed in the financial year.</>,
        <><strong>Benchmark comparison</strong> — compare portfolio performance vs ASX 200 / ASX 300 over the same period on the Chart tab.</>,
        <><strong>Watchlist integration</strong> — show watchlist vs portfolio holdings side by side to spot opportunities.</>,
        <><strong>DRP automation</strong> — auto-generate DRP transactions based on dividend history and holding quantities.</>,
        <><strong>Real-time prices</strong> — intraday price updates (currently EOD only) for more accurate intraday P&amp;L.</>,
        <><strong>Broker integration</strong> — direct connection to CommSec, SelfWealth, Stake etc. to auto-import transactions.</>,
        <><strong>CGT parcel optimisation</strong> — show which parcel to sell first (HIFO/FIFO) to minimise CGT.</>,
        <><strong>Portfolio alerts</strong> — notify when a holding drops below a stop-loss level or dividend is announced.</>,
      ]} />

      <div className="mt-10 pt-4 border-t border-slate-200 text-xs text-slate-400">
        Internal documentation — Admin only. Reflects the Portfolio page as built. Update this manual when portfolio features, tab gating or API endpoints change.
      </div>
    </div>
  )
}

// ── Manual registry (add a page manual here, then a render case below) ─────────
const MANUALS = [
  { slug: 'market-overview', title: 'Market Overview', page: '/market', status: 'ready' as const },
  { slug: 'screener',        title: 'Stock Screener',  page: '/screener', status: 'ready' as const },
  { slug: 'company-detail',  title: 'Company Detail',  page: '/company/[code]', status: 'ready' as const },
  { slug: 'alpha-screens',   title: 'Alpha Screens',   page: '/scans', status: 'ready' as const },
  { slug: 'glossary',        title: 'Metrics Glossary', page: '/glossary', status: 'ready' as const },
  { slug: 'portfolio',       title: 'Portfolio',       page: '/portfolio', status: 'ready' as const },
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
          {active === 'alpha-screens' && <AlphaScreensManual />}
          {active === 'glossary' && <GlossaryManual />}
          {active === 'screener' && <ScreenerManual />}
          {active === 'portfolio' && <PortfolioManual />}
        </main>
      </div>
    </div>
  )
}
