/**
 * Help drawer content for every page.
 * Each page imports its own SECTIONS array and passes it to <HelpDrawer sections={...} />.
 */
import type { SectionDef } from '@/components/HelpDrawer'

// ─────────────────────────────────────────────────────────────────────────────
// MARKET PAGE  (/market)
// ─────────────────────────────────────────────────────────────────────────────

export const MARKET_SECTIONS: SectionDef[] = [
  {
    id: 'index-snapshots',
    icon: '📈', iconBg: 'bg-blue-50', iconText: 'text-blue-600',
    title: 'Index Snapshots',
    badge: 'ASX 200 · ASX 300',
    summary: 'Live overview of the two main ASX index baskets — shows how the broad market is moving at a glance.',
    howToUse: 'Use this to quickly gauge overall market direction before diving into individual sections. Green trend icon = index average is up for the week; red = down.',
    columns: [
      { name: 'Stocks',          desc: 'Number of constituent stocks in the index.' },
      { name: 'Avg 1W Return',   desc: 'Mean price return across all index stocks over the past week.' },
      { name: 'Gainers / Losers',desc: 'Count of stocks with positive vs negative 1-week returns.' },
      { name: 'Market Cap',      desc: 'Total combined market capitalisation of all index constituents.' },
    ],
  },
  {
    id: 'sector-heatmap',
    icon: '🔲', iconBg: 'bg-violet-50', iconText: 'text-violet-600',
    title: 'Sector Heatmap',
    badge: '1W Performance',
    summary: 'Colour-coded grid showing the average 1-week price return for every GICS sector on the ASX.',
    howToUse: 'Darker green = stronger sector momentum. Darker red = sector selling off. Useful for sector rotation — move into strong sectors, out of weak ones.',
    columns: [
      { name: 'Sector name', desc: 'GICS (Global Industry Classification Standard) sector label.' },
      { name: '% figure',    desc: 'Average 1-week return across all stocks in that sector.' },
      { name: 'Stock count', desc: 'Number of ASX-listed stocks in this sector.' },
    ],
  },
  {
    id: 'top-movers',
    icon: '🚀', iconBg: 'bg-emerald-50', iconText: 'text-emerald-600',
    title: 'Top Movers',
    summary: 'The biggest percentage gainers and losers over your chosen period, filterable by market cap tier.',
    howToUse: 'Select a period and a cap tier. "All" shows the whole market. Narrow to a tier to find movers within your risk profile — e.g. Large cap only for blue-chip momentum plays.',
    filters: [
      { name: 'All',              desc: 'Every ASX-listed stock regardless of size.' },
      { name: 'Mega ≥$50B',       desc: 'Mega-cap — the largest companies on the ASX (e.g. BHP, CBA, CSL).' },
      { name: 'Large $10B–$50B',  desc: 'Large-cap — well-established, significant market presence.' },
      { name: 'Mid $2B–$10B',     desc: 'Mid-cap — growth companies with meaningful size but more volatility.' },
      { name: 'Small $300M–$2B',  desc: 'Small-cap — smaller companies, higher risk/reward.' },
      { name: 'Micro $50M–$300M', desc: 'Micro-cap — early-stage or niche, illiquid, volatile.' },
      { name: 'Nano <$50M',       desc: 'Nano-cap — very small speculative stocks, proceed with caution.' },
      { name: '1D / 1W / 1M / 3M',desc: 'Price change over 1 day, 1 week, 1 month, or 3 months.' },
    ],
    columns: [
      { name: '#',           desc: 'Rank by absolute % move (largest first).' },
      { name: 'Stock',       desc: 'ASX ticker and company name. Click to open the full company page.' },
      { name: 'Price',       desc: 'Latest closing price.' },
      { name: 'Period High', desc: 'Highest price reached during the selected period.' },
      { name: 'Period Low',  desc: 'Lowest price reached during the selected period.' },
      { name: '% Chg',       desc: 'Total price return over the selected period.' },
    ],
  },
  {
    id: 'market-signals',
    icon: '⚡', iconBg: 'bg-amber-50', iconText: 'text-amber-600',
    title: 'Market Signals',
    summary: 'Stocks triggering notable technical price events — near multi-period highs/lows or showing unusual volume. A momentum and breakout scanner.',
    howToUse: '"↑ Highs" finds breakout candidates near new highs. "↓ Lows" spots oversold stocks. "⚡ Volume" detects unusual activity — often precedes big moves. 52W is the most widely watched period.',
    filters: [
      { name: '↑ Highs',            desc: 'Stocks within 5% of their period high — potential breakout.' },
      { name: '↓ Lows',             desc: 'Stocks within 5% of their period low — oversold or in downtrend.' },
      { name: '⚡ Volume',           desc: 'Stocks trading significantly above their 20-day average volume.' },
      { name: '1D/1W/1M/3M/52W',    desc: 'Lookback window for the high/low calculation.' },
    ],
    columns: [
      { name: 'Stock',          desc: 'ASX ticker and company name.' },
      { name: 'Price',          desc: 'Latest closing price.' },
      { name: 'Period High/Low',desc: 'The actual high or low price for the selected period.' },
      { name: 'From High/Low',  desc: '% distance from current price to the period high or low.' },
      { name: 'Return',         desc: 'Recent price return — confirms whether momentum backs the signal.' },
      { name: 'vs 20D Avg',     desc: 'Volume ratio vs 20-day average. 3× = 3× normal volume.' },
    ],
  },
  {
    id: 'most-active',
    icon: '📊', iconBg: 'bg-blue-50', iconText: 'text-blue-600',
    title: 'Most Active by Volume',
    summary: 'Top stocks by raw share trading volume today. High volume means market participants are taking action.',
    howToUse: 'Compare "Volume" to "vs 20D" — a stock with high raw volume but a low ratio is just a normally busy stock. 5× or more vs average is where the real action is.',
    columns: [
      { name: '#',      desc: 'Rank by total volume traded today.' },
      { name: 'Stock',  desc: 'ASX ticker and company name.' },
      { name: 'Price',  desc: 'Latest closing price.' },
      { name: 'Volume', desc: 'Total shares traded today (M = millions, K = thousands).' },
      { name: 'vs 20D', desc: "Today's volume ÷ 20-day average. ≥2× notable; ≥3× highlighted orange." },
    ],
  },
  {
    id: 'heavy-buying',
    icon: '🟢', iconBg: 'bg-emerald-50', iconText: 'text-emerald-600',
    title: 'Heavy Buying',
    summary: 'Stocks with a simultaneous volume surge AND rising price — a sign of aggressive accumulation. Buyers are in control.',
    howToUse: 'Combine with "↑ Highs" in Market Signals for confluence. Note: high volume + price up can also mean overbought short-term.',
    columns: [
      { name: 'Vol Ratio', desc: "Today's volume ÷ 20-day average. Higher = more unusual the buying activity." },
      { name: '1W',        desc: '1-week price return — confirms whether buying is sustained.' },
    ],
  },
  {
    id: 'heavy-selling',
    icon: '🔴', iconBg: 'bg-red-50', iconText: 'text-red-600',
    title: 'Heavy Selling',
    summary: 'Stocks with a simultaneous volume surge AND falling price — distribution or panic selling. Sellers are in control.',
    howToUse: 'Warning signal — stocks here may continue to fall. Can also be used as a contrarian oversold bounce screen when combined with "↓ Lows" in Market Signals.',
    columns: [
      { name: 'Vol Ratio', desc: "Today's volume ÷ 20-day average. Higher = more significant selling pressure." },
      { name: '1W',        desc: '1-week return — deeply negative confirms strong selling.' },
    ],
  },
  {
    id: 'market-anomalies',
    icon: '⚠️', iconBg: 'bg-amber-50', iconText: 'text-amber-600',
    title: 'Market Anomalies',
    badge: 'Algorithm-detected',
    summary: 'Algorithmically detected unusual market behaviours — price spikes, gaps, volume extremes, 52-week extremes, and reversals. Flags scored by severity.',
    howToUse: 'Filter by anomaly type to focus on what matters. "High" severity = most statistically unusual. Use as an early-warning radar for stocks about to move significantly.',
    filters: [
      { name: 'Price Spike',  desc: 'Abnormally large price move relative to recent volatility.' },
      { name: 'Volume Spike', desc: 'Volume that is statistically extreme vs the stock\'s own history.' },
      { name: 'Gap Up',       desc: 'Stock opened significantly above the prior close — usually on news.' },
      { name: 'Gap Down',     desc: 'Stock opened significantly below the prior close.' },
      { name: '52W High',     desc: 'Stock touched or broke its 52-week high today.' },
      { name: '52W Low',      desc: 'Stock touched or broke its 52-week low today.' },
      { name: 'Reversal',     desc: 'Price reversed sharply after an extended trend — potential turning point.' },
    ],
    columns: [
      { name: 'Type',        desc: 'The anomaly category detected.' },
      { name: 'Description', desc: 'Plain-English explanation of what was detected for this stock.' },
      { name: 'Severity',    desc: 'High / Medium / Low — based on how statistically unusual the event is.' },
    ],
  },
  {
    id: 'ex-dividend',
    icon: '💰', iconBg: 'bg-indigo-50', iconText: 'text-indigo-600',
    title: 'Upcoming Ex-Dividend Dates',
    badge: 'Next 14 days',
    summary: 'Stocks going ex-dividend within the next 14 days. You must own the stock BEFORE the ex-dividend date to receive the dividend.',
    howToUse: 'Franking credits add significant value for Australian tax residents — 100% franked is worth more than an unfranked dividend of the same cash amount. Prices typically drop by ~dividend amount on the ex-div date.',
    columns: [
      { name: 'Ex-Div Date', desc: 'You must own the stock on or before this date.' },
      { name: 'Pay Date',    desc: 'When the dividend cash is credited to your account.' },
      { name: 'DPS',         desc: 'Dividend Per Share — cash amount paid per share held.' },
      { name: 'Yield',       desc: 'Annual dividend yield = total annual DPS ÷ current price × 100.' },
      { name: 'Franking',    desc: '% of the dividend that carries attached tax credits. 100% = fully franked.' },
    ],
  },
]


// ─────────────────────────────────────────────────────────────────────────────
// SCREENER PAGE  (/screener)
// ─────────────────────────────────────────────────────────────────────────────

export const SCREENER_SECTIONS: SectionDef[] = [
  {
    id: 'screener-modes',
    icon: '🔀', iconBg: 'bg-slate-50', iconText: 'text-slate-600',
    title: 'Three Modes',
    summary: 'The screener has three entry points: Filter Screen (visual dropdowns), AI Query (natural language), and Query Mode (SQL-like expressions). All three search the same live ASX universe.',
    howToUse: 'Filter Screen: know exactly what you want — P/E < 15 AND yield > 4%. AI Query: describe a concept — "cheap miners with growing revenue". Query Mode: write precise multi-condition logic with AND/OR/parentheses, e.g. roe > 15 AND (roce > 12 OR roic > 12).',
    filters: [
      { name: 'Filter Screen', desc: 'Visual dropdowns — best for simple AND-only filters. Available to all users.' },
      { name: 'AI Query',      desc: 'Natural language powered by Claude AI. Premium plan required.' },
      { name: 'Query Mode',    desc: 'SQL-like WHERE expressions with AND/OR/parentheses. Pro or Premium plan required.' },
    ],
    columns: [],
  },
  {
    id: 'filter-screen',
    icon: '🎛️', iconBg: 'bg-blue-50', iconText: 'text-blue-600',
    title: 'Filter Screen',
    summary: 'Build a screen by adding one or more filter rules. Each rule is a field, operator, and value. Combine as many as you like — all rules are ANDed together.',
    howToUse: 'Click "+ Add Filter", choose a field from the dropdown, pick an operator (greater than, less than, equals, between), and enter a value. Results update when you click "Run Screen".',
    filters: [
      { name: 'Field',      desc: 'The metric to filter on — e.g. P/E Ratio, Market Cap, Dividend Yield.' },
      { name: 'Operator',   desc: '> (greater than), < (less than), = (equals), between (range).' },
      { name: 'Value',      desc: 'The threshold — e.g. for Yield > 4, enter 4.' },
    ],
    columns: [
      { name: 'Code',          desc: 'ASX ticker. Click to open the full company page.' },
      { name: 'Company',       desc: 'Full company name.' },
      { name: 'Price',         desc: 'Latest closing price.' },
      { name: 'Mkt Cap',       desc: 'Market capitalisation in AUD.' },
      { name: 'P/E',           desc: 'Price-to-Earnings ratio — how much you pay per $1 of earnings.' },
      { name: 'EV/EBITDA',     desc: 'Enterprise value divided by EBITDA — a debt-adjusted valuation metric.' },
      { name: 'Yield',         desc: 'Dividend yield — annual dividends as % of current price.' },
      { name: 'Franking',      desc: '% of dividend that is tax-franked.' },
      { name: 'Revenue Gr.',   desc: 'Year-on-year revenue growth %.' },
      { name: 'EBITDA Margin', desc: 'EBITDA as % of revenue — operating profitability.' },
      { name: 'Net Debt/EBITDA',desc: 'Leverage ratio — higher = more debt relative to earnings.' },
      { name: 'ROE',           desc: 'Return on Equity — how effectively management uses shareholder capital.' },
      { name: '1W / 1M / 3M', desc: 'Price returns over 1 week, 1 month, 3 months.' },
    ],
  },
  {
    id: 'presets',
    icon: '📋', iconBg: 'bg-emerald-50', iconText: 'text-emerald-600',
    title: 'Preset Screens',
    badge: 'Quick-start',
    summary: 'Ready-made filter combinations based on proven investment strategies. Click a preset to instantly load its filters into the screener.',
    howToUse: 'Presets are a great starting point — load one, then tweak the individual filters to suit your own criteria. Pro presets require a Pro plan or higher.',
    filters: [
      { name: 'Free presets', desc: 'Available to all users — value, income, quality basics.' },
      { name: 'Pro presets',  desc: 'Advanced strategies (Piotroski, deep value, momentum) — Pro plan required.' },
    ],
    columns: [],
  },
  {
    id: 'ai-query',
    icon: '🤖', iconBg: 'bg-indigo-50', iconText: 'text-indigo-600',
    title: 'AI Natural Language Query',
    badge: 'Pro',
    summary: 'Type a plain-English question and Claude AI converts it to structured screener filters and runs it instantly against the ASX database.',
    howToUse: 'Be descriptive — "profitable small cap miners with low debt" works better than "small miners". You can see exactly how Claude interpreted your query in the "Interpreted as:" banner. Click any example chip to try a pre-built query.',
    filters: [
      { name: 'Example chips', desc: 'Pre-built queries you can click to run instantly — great for exploring what the AI can do.' },
    ],
    columns: [
      { name: 'Interpreted as', desc: 'How the AI understood your query in plain English.' },
      { name: 'Filter chips',   desc: 'The actual field/operator/value filters the AI generated.' },
      { name: 'Results table',  desc: 'Same columns as the manual screener — fully sortable.' },
    ],
  },
  {
    id: 'query-mode',
    icon: '💻', iconBg: 'bg-orange-50', iconText: 'text-orange-600',
    title: 'Query Mode',
    badge: 'Pro · Premium',
    summary: 'Write SQL-like WHERE conditions directly against the ASX database. Supports AND, OR, and parenthesised grouping — letting you express complex logic that the visual filter builder cannot.',
    howToUse: 'Type field names, an operator (>, <, >=, <=, =, !=), and a value. Use AND/OR to chain conditions. Wrap groups in parentheses. Ctrl+Enter runs the query. Use the Field Reference panel on the right to browse and insert field names.',
    filters: [
      { name: 'roe > 15',                            desc: 'Single condition — Return on Equity above 15%.' },
      { name: 'roe > 15 AND roce > 12',              desc: 'AND logic — both conditions must be true.' },
      { name: 'roe > 15 AND (roce > 12 OR roic > 12)', desc: 'Parenthesised OR — ROE must be > 15, plus either ROCE or ROIC > 12.' },
      { name: 'market_cap > 1000 AND pe_ratio < 15', desc: 'Market cap above $1B AUD AND P/E ratio below 15.' },
    ],
    columns: [
      { name: 'Field Reference',  desc: 'Right sidebar listing all 195 available fields. Click any field to insert it at your cursor.' },
      { name: 'Search fields',    desc: 'Filter the field list by name, label, or alias.' },
      { name: 'CSV download',     desc: 'Download the full field reference as a CSV.' },
      { name: 'Save Query',       desc: 'Save your query with a name — reload it any time from My Queries.' },
      { name: 'Export CSV',       desc: 'Download the filtered results (up to 5,000 rows) as a CSV file.' },
      { name: '% fields',         desc: 'Enter human-readable % values — e.g. "roe > 15" means ROE > 15%, not 0.15.' },
    ],
  },
  {
    id: 'saved-screens',
    icon: '🔖', iconBg: 'bg-amber-50', iconText: 'text-amber-600',
    title: 'Saved Screens',
    summary: 'Save any combination of filters as a named screen. Screens can be private (only you) or public (visible to all users in the community).',
    howToUse: 'After building a filter set you like, click "Save Screen", give it a name and optional description. Reload it any time from "My Screens". Public screens appear in the Scans page for other users.',
    columns: [
      { name: 'My Screens',      desc: 'Your private and public saved screens.' },
      { name: 'Community',       desc: 'Screens shared publicly by all users — sorted by most-used.' },
      { name: 'Public / Private',desc: 'Toggle visibility. Public screens are discoverable by other users.' },
    ],
  },
  {
    id: 'csv-export',
    icon: '📥', iconBg: 'bg-slate-50', iconText: 'text-slate-600',
    title: 'CSV Export',
    badge: 'Pro',
    summary: 'Download up to 5,000 rows of screener results as a CSV file for use in Excel or Google Sheets.',
    howToUse: 'Run a screen first, then click the download icon next to the result count. The CSV includes all visible columns. Pro plan required.',
    columns: [],
  },
]


// ─────────────────────────────────────────────────────────────────────────────
// SCANS PAGE  (/scans)
// ─────────────────────────────────────────────────────────────────────────────

export const SCANS_SECTIONS: SectionDef[] = [
  {
    id: 'what-are-scans',
    icon: '🔍', iconBg: 'bg-blue-50', iconText: 'text-blue-600',
    title: 'What are Scans?',
    summary: 'Pre-built screener templates based on proven investment strategies. Each scan is a curated set of filters — click any card to instantly run it in the full screener.',
    howToUse: 'Browse by category (Dividend, Value, Growth, Technical). Click a scan card to run it. Free scans are available to all users; Pro scans require an upgrade. After running, you can tweak the filters in the screener.',
    columns: [],
  },
  {
    id: 'scan-categories',
    icon: '🗂️', iconBg: 'bg-violet-50', iconText: 'text-violet-600',
    title: 'Scan Categories',
    summary: 'Scans are organised into four strategic categories to match different investing styles.',
    howToUse: 'Income investors → Dividend & Income. Long-term investors → Value & Quality. Growth investors → Growth & Momentum. Chart traders → Technical Signals.',
    filters: [
      { name: 'Dividend & Income',    desc: 'High-yield and franked dividend strategies for income-focused investors.' },
      { name: 'Value & Quality',      desc: 'Undervalued stocks with strong fundamentals and financial health.' },
      { name: 'Growth & Momentum',    desc: 'Companies accelerating revenue, earnings and price momentum.' },
      { name: 'Technical Signals',    desc: 'Chart-based breakout, trend-following and mean-reversion signals.' },
    ],
    columns: [],
  },
  {
    id: 'scan-cards',
    icon: '🃏', iconBg: 'bg-emerald-50', iconText: 'text-emerald-600',
    title: 'Scan Cards',
    summary: 'Each card shows the strategy name, description, and a "Free" or "Pro" badge. Pro scans are locked for free users.',
    howToUse: 'Click a free card to run it immediately. Click a Pro card to see the strategy and upgrade if interested. Community screens (created by other users) show a usage count.',
    columns: [
      { name: 'Name',        desc: 'The strategy name.' },
      { name: 'Description', desc: 'What the screen looks for and why it might work.' },
      { name: 'Free / Pro',  desc: 'Whether the scan requires a paid plan.' },
      { name: 'Used X times',desc: 'Community screens — how many times this screen has been run by users.' },
    ],
  },
  {
    id: 'community-screens',
    icon: '👥', iconBg: 'bg-amber-50', iconText: 'text-amber-600',
    title: 'Community Screens',
    summary: 'Screens shared publicly by other users. Sorted by usage — the most popular appear first.',
    howToUse: 'Great for discovering new ideas. Click to run any community screen, then customise it for your own criteria in the full screener.',
    columns: [
      { name: 'Author',   desc: 'The user who created and shared this screen.' },
      { name: 'Filters',  desc: 'Number of filter rules in the screen.' },
      { name: 'Used',     desc: 'Total number of times this screen has been run.' },
    ],
  },
]


// ─────────────────────────────────────────────────────────────────────────────
// WATCHLIST PAGE  (/watchlist)
// ─────────────────────────────────────────────────────────────────────────────

export const WATCHLIST_SECTIONS: SectionDef[] = [
  {
    id: 'watchlist-overview',
    icon: '⭐', iconBg: 'bg-amber-50', iconText: 'text-amber-600',
    title: 'Watchlists',
    summary: 'Organise ASX stocks you want to monitor into named lists. Each watchlist shows live price data, returns, and key metrics for all your tracked stocks.',
    howToUse: 'Create multiple watchlists for different purposes (e.g. "Dividend stocks", "Speculative ideas", "Short list"). Add stocks by searching for their ticker or company name. Click any stock to go to its full company page.',
    columns: [],
  },
  {
    id: 'watchlist-columns',
    icon: '📊', iconBg: 'bg-blue-50', iconText: 'text-blue-600',
    title: 'Stock Data Columns',
    summary: 'Each watchlist shows live key metrics for every stock, updated with the latest available data.',
    howToUse: 'Use the columns to quickly compare stocks in your list. Green = positive return; red = negative. Click column headers to sort.',
    columns: [
      { name: 'Code',     desc: 'ASX ticker. Click to open the full company page.' },
      { name: 'Company',  desc: 'Full company name.' },
      { name: 'Price',    desc: 'Latest closing price.' },
      { name: 'Mkt Cap',  desc: 'Market capitalisation — total market value of all shares.' },
      { name: 'P/E',      desc: 'Price-to-Earnings — how much you pay per $1 of earnings. Lower = cheaper.' },
      { name: 'EV/EBITDA',desc: 'Debt-adjusted valuation. More useful than P/E when comparing leveraged companies.' },
      { name: 'Yield',    desc: 'Dividend yield — annual dividends as % of current price.' },
      { name: 'Franking', desc: '% of dividend that carries franking (tax) credits. 100% = fully franked.' },
      { name: '1W',       desc: '1-week price return.' },
      { name: '1M',       desc: '1-month price return.' },
      { name: '3M',       desc: '3-month price return.' },
    ],
  },
  {
    id: 'watchlist-management',
    icon: '⚙️', iconBg: 'bg-slate-50', iconText: 'text-slate-600',
    title: 'Managing Watchlists',
    summary: 'Create, rename, and delete watchlists. Add or remove stocks at any time.',
    howToUse: 'Click "+ New Watchlist" to create one. Click the pencil icon to rename. Use the trash icon to delete (this is irreversible). Add stocks via the search bar — type a ticker or company name.',
    columns: [
      { name: '+ New Watchlist',   desc: 'Create a fresh empty watchlist.' },
      { name: 'Rename (pencil)',   desc: 'Edit the watchlist name.' },
      { name: 'Remove (trash)',    desc: 'Remove a stock from the current watchlist.' },
      { name: 'Search bar',        desc: 'Find a stock by ticker (e.g. CBA) or company name and add it.' },
    ],
  },
  {
    id: 'plan-limits',
    icon: '🔒', iconBg: 'bg-slate-50', iconText: 'text-slate-600',
    title: 'Plan Limits',
    summary: 'The number of watchlists and stocks per list depends on your plan.',
    howToUse: 'Free plan: 1 watchlist, 50 stocks. Pro: 20 watchlists, 500 stocks. Premium: 50 watchlists, 500 stocks. Upgrade via the Account page.',
    columns: [
      { name: 'Free',    desc: '1 watchlist · 50 stocks per list.' },
      { name: 'Pro',     desc: '20 watchlists · 500 stocks per list.' },
      { name: 'Premium', desc: '50 watchlists · 500 stocks per list.' },
    ],
  },
]


// ─────────────────────────────────────────────────────────────────────────────
// PORTFOLIO PAGE  (/portfolio)
// ─────────────────────────────────────────────────────────────────────────────

export const PORTFOLIO_SECTIONS: SectionDef[] = [
  {
    id: 'portfolio-overview',
    icon: '💼', iconBg: 'bg-blue-50', iconText: 'text-blue-600',
    title: 'Portfolio Tracker',
    summary: 'Track your real ASX holdings, cost basis, P&L, dividends received, and overall portfolio performance over time.',
    howToUse: 'Create a portfolio, add transactions (buys/sells), and the system calculates your current holdings, unrealised gains/losses, and dividend income automatically. Import from CSV for bulk entry.',
    columns: [],
  },
  {
    id: 'transactions',
    icon: '📝', iconBg: 'bg-slate-50', iconText: 'text-slate-600',
    title: 'Transactions',
    summary: 'Record every buy and sell transaction. Each transaction tracks the stock, date, quantity, price paid, and brokerage fees.',
    howToUse: 'Click "+ Add Transaction" to log a trade. Be accurate with brokerage — it affects your cost basis and tax calculations. Use "Import CSV" to bulk-upload from your broker\'s export.',
    columns: [
      { name: 'Type',      desc: 'Buy or Sell.' },
      { name: 'Date',      desc: 'Settlement or trade date.' },
      { name: 'Qty',       desc: 'Number of shares bought or sold.' },
      { name: 'Price',     desc: 'Price per share at time of trade.' },
      { name: 'Brokerage', desc: 'Commission paid to broker — included in cost basis.' },
      { name: 'Value',     desc: 'Total value of the transaction (Qty × Price + Brokerage).' },
    ],
  },
  {
    id: 'performance',
    icon: '📈', iconBg: 'bg-emerald-50', iconText: 'text-emerald-600',
    title: 'Performance Summary',
    summary: 'Live portfolio metrics calculated from your transaction history and current market prices.',
    howToUse: 'The performance chart shows your portfolio value over time. Green = above your cost basis; red = below. Use the allocation pie chart to check concentration risk.',
    columns: [
      { name: 'Market Value',    desc: 'Current total value of all holdings at latest prices.' },
      { name: 'Cost Basis',      desc: 'Total amount invested (sum of all buy transactions).' },
      { name: 'Unrealised P&L',  desc: 'Market Value − Cost Basis. Green = profit; red = loss.' },
      { name: 'Unrealised %',    desc: 'Unrealised P&L as % of cost basis.' },
      { name: 'Total Return',    desc: 'Unrealised gains + realised gains + dividends received.' },
    ],
  },
  {
    id: 'dividends',
    icon: '💰', iconBg: 'bg-indigo-50', iconText: 'text-indigo-600',
    title: 'Dividend Income',
    summary: 'Tracks all dividends paid on your held stocks, including franking credits.',
    howToUse: 'Dividends are calculated based on your holdings on each ex-dividend date. Franking credit value is shown separately — important for your tax return as a gross-up.',
    columns: [
      { name: 'DPS',            desc: 'Dividend Per Share paid.' },
      { name: 'Total received', desc: 'DPS × shares held on ex-div date.' },
      { name: 'Franking credit',desc: 'Tax credit attached to the dividend. Reduces your tax payable.' },
      { name: 'Yield on Cost',  desc: 'Dividend ÷ your cost basis — shows actual return on what you paid.' },
    ],
  },
  {
    id: 'tax-report',
    icon: '🧾', iconBg: 'bg-amber-50', iconText: 'text-amber-600',
    title: 'Tax Report',
    summary: 'CGT (Capital Gains Tax) summary for a financial year, showing short-term and long-term gains/losses on closed positions.',
    howToUse: 'Export at tax time. Holdings sold within 12 months are short-term (full CGT). Holdings sold after 12 months qualify for the 50% CGT discount. Always consult your accountant for final figures.',
    columns: [
      { name: 'Realised Gain/Loss', desc: 'Profit or loss on sold positions — taxable event.' },
      { name: 'Short-term',         desc: 'Positions held < 12 months — no CGT discount.' },
      { name: 'Long-term',          desc: 'Positions held ≥ 12 months — 50% CGT discount applies.' },
      { name: 'Net gain',           desc: 'Short-term gains + long-term gains after discount.' },
    ],
  },
  {
    id: 'ai-insights',
    icon: '🤖', iconBg: 'bg-violet-50', iconText: 'text-violet-600',
    title: 'AI Portfolio Insights',
    badge: 'Premium',
    summary: 'Claude AI analyses your portfolio and provides personalised observations on concentration, sector exposure, dividend health, valuation, and risk.',
    howToUse: 'Click "Generate Insights" on the Insights tab. AI reads your current holdings and generates a structured analysis. Results are educational, not financial advice — always do your own research.',
    columns: [
      { name: 'Concentration',  desc: 'Flags if any single stock or sector is an outsized portion of the portfolio.' },
      { name: 'Sector exposure',desc: 'Breakdown of how your holdings are spread across GICS sectors.' },
      { name: 'Dividend health',desc: 'Average yield, franking, and income sustainability across holdings.' },
      { name: 'Valuation',      desc: 'Weighted average P/E and other multiples vs ASX benchmarks.' },
      { name: 'Risk flags',     desc: 'Alerts for highly leveraged, loss-making, or illiquid holdings.' },
    ],
  },
]


// ─────────────────────────────────────────────────────────────────────────────
// ALERTS PAGE  (/alerts)
// ─────────────────────────────────────────────────────────────────────────────

export const ALERTS_SECTIONS: SectionDef[] = [
  {
    id: 'alerts-overview',
    icon: '🔔', iconBg: 'bg-blue-50', iconText: 'text-blue-600',
    title: 'Price Alerts',
    summary: 'Set automated price alerts on any ASX stock. When the condition is met, you receive an email notification.',
    howToUse: 'Enter an ASX code, choose a condition, set your threshold price, and choose how often to be notified. Alerts are checked every 15 minutes during ASX trading hours.',
    columns: [],
  },
  {
    id: 'alert-types',
    icon: '⚙️', iconBg: 'bg-slate-50', iconText: 'text-slate-600',
    title: 'Alert Conditions',
    summary: 'Four condition types let you catch price breakouts, breakdowns, and weekly momentum moves.',
    howToUse: 'For a breakout alert: "Price rises above $X". For a stop-loss alert: "Price falls below $X". For momentum: "1W change above/below X%".',
    filters: [
      { name: 'Price rises above', desc: 'Triggers when the stock price crosses above your threshold — breakout alert.' },
      { name: 'Price falls below', desc: 'Triggers when price drops below your threshold — stop-loss or dip alert.' },
      { name: '1W change above',   desc: 'Triggers when the 1-week % change exceeds your threshold — momentum alert.' },
      { name: '1W change below',   desc: 'Triggers when the 1-week % change falls below your threshold — drawdown alert.' },
    ],
    columns: [],
  },
  {
    id: 'repeat-mode',
    icon: '🔁', iconBg: 'bg-emerald-50', iconText: 'text-emerald-600',
    title: 'Repeat Mode',
    summary: 'Controls whether an alert fires once or every time the condition is met.',
    howToUse: 'Use "Once" for a one-time notification (e.g. when a price crosses a key level). Use "Every time" to be notified on every data check the condition is met — useful for sustained momentum.',
    filters: [
      { name: 'Once',       desc: 'Alert fires one time only, then deactivates automatically.' },
      { name: 'Every time', desc: 'Alert fires every 15 minutes for as long as the condition holds.' },
      { name: 'Daily',      desc: 'Alert fires once per trading day if the condition is met.' },
    ],
    columns: [],
  },
  {
    id: 'alert-table',
    icon: '📋', iconBg: 'bg-amber-50', iconText: 'text-amber-600',
    title: 'Active Alerts Table',
    summary: 'Shows all your current alerts, their status, and firing history.',
    howToUse: 'Use the eye icon to activate/deactivate an alert without deleting it. Use the trash icon to permanently delete. "Fired" count shows how many times the alert has triggered.',
    columns: [
      { name: 'Code',           desc: 'ASX ticker the alert is watching.' },
      { name: 'Condition',      desc: 'The alert type and direction.' },
      { name: 'Threshold',      desc: 'The price or % level that triggers the alert.' },
      { name: 'Status',         desc: 'Active (monitoring) or Inactive (paused).' },
      { name: 'Fired',          desc: 'Number of times this alert has triggered.' },
      { name: 'Last Triggered', desc: 'Date and time the alert last fired.' },
    ],
  },
  {
    id: 'plan-limits-alerts',
    icon: '🔒', iconBg: 'bg-slate-50', iconText: 'text-slate-600',
    title: 'Alert Limits by Plan',
    summary: 'Maximum number of active alerts depends on your subscription plan.',
    howToUse: 'Free plan supports 5 alerts. Upgrade to Pro or Premium for up to 100 active alerts.',
    columns: [
      { name: 'Free',    desc: '5 active alerts.' },
      { name: 'Pro',     desc: '50 active alerts.' },
      { name: 'Premium', desc: '100 active alerts.' },
    ],
  },
]


// ─────────────────────────────────────────────────────────────────────────────
// NEWS PAGE  (/news)
// ─────────────────────────────────────────────────────────────────────────────

export const NEWS_SECTIONS: SectionDef[] = [
  {
    id: 'news-overview',
    icon: '📰', iconBg: 'bg-blue-50', iconText: 'text-blue-600',
    title: 'ASX News & Announcements',
    summary: 'Official company filings and market announcements from ASX, updated every 10 minutes. Covers all listed companies.',
    howToUse: 'Use the search bar to filter by ticker or company name. Use the type filter to focus on a specific category (e.g. financial results, capital raises). Click any announcement to read the full document on ASX.',
    columns: [],
  },
  {
    id: 'announcement-types',
    icon: '🏷️', iconBg: 'bg-violet-50', iconText: 'text-violet-600',
    title: 'Announcement Types',
    summary: 'ASX announcements are categorised by the type of information disclosed.',
    howToUse: 'Filter by type to reduce noise. "Results" (half-year and full-year financials) and "Capital raise" announcements typically cause the largest price moves.',
    filters: [
      { name: 'All',                desc: 'Every announcement type.' },
      { name: 'Results',            desc: 'Half-year and full-year financial results.' },
      { name: 'Capital raise',      desc: 'Placements, rights issues, SPPs — new shares being issued.' },
      { name: 'Quarterly report',   desc: 'Quarterly cash flow and activity reports (common in mining/resources).' },
      { name: 'AGM / EGM',         desc: 'Annual or Extraordinary General Meetings — resolutions, voting results.' },
      { name: 'Appendix 3B',       desc: 'New share issuance notification — always check for dilution.' },
      { name: 'Director notice',   desc: 'Director buying or selling shares (Appendix 3Y) — insider activity signal.' },
      { name: 'Investor update',   desc: 'Company presentations, investor days, strategy updates.' },
    ],
    columns: [],
  },
  {
    id: 'announcement-table',
    icon: '📋', iconBg: 'bg-slate-50', iconText: 'text-slate-600',
    title: 'Announcement Feed',
    summary: 'A chronological list of all ASX announcements, newest first. Pagination loads earlier announcements.',
    howToUse: 'The "Price Sensitive" badge means the company declared the announcement may affect its share price — these are the most important to read quickly. The live ticker at the top shows the latest announcements in real time.',
    columns: [
      { name: 'Time',             desc: 'How long ago the announcement was lodged.' },
      { name: 'Code',             desc: 'ASX ticker. Click to go to the company page.' },
      { name: 'Headline',         desc: 'The announcement title as lodged on ASX. Click to read the full document.' },
      { name: 'Type',             desc: 'Category of announcement.' },
      { name: 'Price Sensitive',  desc: 'Company declared this announcement may materially affect its share price.' },
    ],
  },
  {
    id: 'live-ticker',
    icon: '📡', iconBg: 'bg-emerald-50', iconText: 'text-emerald-600',
    title: 'Live Ticker',
    summary: 'Scrolling banner across the top of the page showing the most recent announcements in real time.',
    howToUse: 'Click any item in the ticker to jump to that announcement in the feed below.',
    columns: [],
  },
]
