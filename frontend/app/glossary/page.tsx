'use client'
import { useState, useMemo, useEffect } from 'react'
import { Search, BookOpen, ChevronDown, ChevronUp, Tag, MapPin, Calculator, Target, Info, BarChart2, Link2, Zap, ChevronsUpDown } from 'lucide-react'
import { PlanGate } from '@/components/PlanGate'
import { cn } from '@/lib/utils'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Metric {
  id: string
  name: string
  category: string
  shortDesc: string
  definition: string
  formula?: string
  interpretation?: string
  benchmark?: string
  example?: string
  beginnerTip?: string
  beginner?: boolean
  relatedMetrics?: string[]
  usedIn: string[]
  tags: string[]
}

// ── Metrics Data ──────────────────────────────────────────────────────────────

const METRICS: Metric[] = [
  // ── VALUATION ──────────────────────────────────────────────────────────────
  {
    id: 'pe_ratio',
    name: 'P/E Ratio (Price-to-Earnings)',
    category: 'Valuation',
    shortDesc: 'How much investors pay for each dollar of earnings',
    definition: 'The Price-to-Earnings ratio divides the current share price by earnings per share (EPS). It tells you how many years of current earnings you are paying for upfront. A higher P/E means the market expects faster growth or is willing to pay a premium.',
    formula: 'P/E = Share Price ÷ Earnings Per Share (EPS)',
    interpretation: 'Lower P/E = cheaper relative to earnings. A negative P/E means the company is loss-making. Compare P/E within the same sector — a "fair" P/E differs greatly between banks (12–15×) and tech growth stocks (30–60×).',
    benchmark: 'ASX average: ~16–18×. Defensive sectors (utilities, banks): 10–15×. Growth sectors (tech, healthcare): 25–50×+',
    example: 'Stock X trades at $20.00 with EPS of $1.25 → P/E = 20÷1.25 = 16×. If the sector average is 12×, the stock is trading at a 33% premium — potentially justified by faster growth or expensive.',
    beginnerTip: 'Think of P/E like this: if a business earns $1 of profit per year, how many dollars would you pay to own it? A P/E of 16× means you\'re paying $16 for every $1 of annual profit. Lower is cheaper, higher means you\'re paying more for expected future growth.',
    beginner: true,
    relatedMetrics: ['forward_pe', 'peg_ratio', 'ev_to_ebitda', 'eps'],
    usedIn: ['Screener', 'Company Detail', 'Value Scans', 'Composite Score (Value Factor)'],
    tags: ['earnings', 'valuation', 'price'],
  },
  {
    id: 'forward_pe',
    name: 'Forward P/E',
    category: 'Valuation',
    shortDesc: 'P/E based on next 12 months estimated earnings',
    definition: 'Forward P/E uses analyst consensus EPS forecasts for the next 12 months instead of trailing earnings. It is more useful for fast-growing companies where past earnings understate future potential.',
    formula: 'Forward P/E = Share Price ÷ Estimated EPS (next 12 months)',
    interpretation: 'If Forward P/E < Trailing P/E, earnings are expected to grow. A stock with a high trailing P/E but low forward P/E may be a growth play where current earnings understate the real opportunity.',
    benchmark: 'Similar benchmarks to trailing P/E but generally 10–15% lower if earnings are growing',
    usedIn: ['Screener', 'Company Detail', 'Valuation Tab'],
    tags: ['earnings', 'valuation', 'forecast'],
  },
  {
    id: 'price_to_book',
    name: 'P/B Ratio (Price-to-Book)',
    category: 'Valuation',
    shortDesc: 'Share price relative to net asset value per share',
    definition: 'The Price-to-Book ratio compares share price to the book value (net assets) per share. Book value = total assets minus total liabilities. It is especially useful for capital-intensive businesses and financial stocks.',
    formula: 'P/B = Share Price ÷ Book Value Per Share',
    interpretation: 'P/B < 1 means the stock trades below net asset value — potentially undervalued or a sign of deteriorating assets. P/B > 3 often signals a high-quality, asset-light business or market premium. Financial stocks (banks, insurers) are best evaluated on P/B.',
    benchmark: 'Banks/financials: 1–2×. Industrials: 1.5–3×. Tech/high-quality: 3–10×+',
    example: 'A bank has total assets of $10B, total liabilities of $9B — book value = $1B. With 100M shares on issue, book value per share = $10. If the stock trades at $12, P/B = 1.2×.',
    beginnerTip: 'P/B is like asking: if this company sold everything it owned and paid all its debts, how much would be left per share? A P/B below 1× means you\'re buying $1 of assets for less than $1 — potentially a bargain, but check why it\'s so cheap.',
    beginner: true,
    relatedMetrics: ['pe_ratio', 'roe', 'nta_per_share', 'graham_number'],
    usedIn: ['Screener', 'Company Detail', 'Value Scans', 'Composite Score (Value Factor)'],
    tags: ['book value', 'assets', 'valuation'],
  },
  {
    id: 'price_to_sales',
    name: 'P/S Ratio (Price-to-Sales)',
    category: 'Valuation',
    shortDesc: 'Market cap relative to annual revenue',
    definition: 'Price-to-Sales divides market capitalisation by annual revenue. It is especially useful for loss-making companies where P/E is not applicable, and for comparing companies in the same industry regardless of profitability.',
    formula: 'P/S = Market Capitalisation ÷ Annual Revenue',
    interpretation: 'P/S < 1 is generally very cheap. High P/S (5×+) is only justified by very high growth or exceptional margins. Compare within sectors — SaaS companies often trade at 8–20× revenue; traditional retailers at 0.2–0.5×.',
    benchmark: 'Retail: 0.2–0.5×. Industrials: 0.5–2×. Tech/SaaS: 5–20×',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Value Factor)'],
    tags: ['revenue', 'sales', 'valuation'],
  },
  {
    id: 'ev_to_ebitda',
    name: 'EV/EBITDA',
    category: 'Valuation',
    shortDesc: 'Enterprise value relative to operating earnings before non-cash items',
    definition: 'EV/EBITDA compares Enterprise Value (market cap + net debt) to EBITDA (Earnings Before Interest, Tax, Depreciation & Amortisation). It is capital-structure neutral — useful for comparing companies with different debt levels.',
    formula: 'EV/EBITDA = (Market Cap + Net Debt − Cash) ÷ EBITDA',
    interpretation: 'Lower is cheaper. It ignores capex, so not ideal for capital-heavy businesses. EV/EBITDA is preferred over P/E for M&A analysis as it reflects what an acquirer would actually pay.',
    benchmark: 'Global average: 10–14×. Defensive/utilities: 8–12×. Tech growth: 20–40×+. Mining (cyclical): 4–8×',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Value Factor)'],
    tags: ['enterprise value', 'EBITDA', 'debt'],
  },
  {
    id: 'ev_to_ebit',
    name: 'EV/EBIT',
    category: 'Valuation',
    shortDesc: 'Enterprise value relative to operating profit',
    definition: 'Similar to EV/EBITDA but includes depreciation and amortisation. Better for capital-intensive businesses where D&A reflects real asset consumption.',
    formula: 'EV/EBIT = Enterprise Value ÷ EBIT',
    interpretation: 'More conservative than EV/EBITDA. Preferred for manufacturing, mining, and asset-heavy businesses where capex is significant.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['enterprise value', 'operating profit'],
  },
  {
    id: 'peg_ratio',
    name: 'PEG Ratio',
    category: 'Valuation',
    shortDesc: 'P/E adjusted for earnings growth rate',
    definition: 'The PEG ratio adjusts the P/E ratio by dividing it by the expected earnings growth rate. It accounts for the fact that a high P/E is more acceptable if earnings are growing rapidly.',
    formula: 'PEG = P/E Ratio ÷ Earnings Growth Rate (%)',
    interpretation: 'PEG < 1 = potentially undervalued for growth. PEG = 1 = fairly valued (paying exactly 1× PE for each % of growth). PEG > 2 = expensive for the growth on offer.',
    benchmark: 'PEG < 1: undervalued. PEG 1–1.5: fair. PEG > 2: expensive',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['growth', 'PE', 'valuation'],
  },
  {
    id: 'price_to_fcf',
    name: 'Price-to-FCF',
    category: 'Valuation',
    shortDesc: 'Share price relative to free cash flow per share',
    definition: 'Compares market cap to free cash flow — cash actually generated after all capital expenditures. Many investors prefer this over P/E as it is harder to manipulate than reported earnings.',
    formula: 'P/FCF = Market Cap ÷ Free Cash Flow',
    interpretation: 'Lower is better. A P/FCF of 15× or below is often considered cheap. Businesses with P/FCF consistently below P/E are turning earnings into real cash efficiently.',
    benchmark: 'Below 15×: attractive. 15–25×: fair. Above 30×: expensive',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['cash flow', 'FCF', 'valuation'],
  },
  {
    id: 'fcf_yield',
    name: 'FCF Yield',
    category: 'Valuation',
    shortDesc: 'Free cash flow as a percentage of market cap',
    definition: 'FCF Yield inverts P/FCF to express free cash flow as a percentage of market cap. It is analogous to dividend yield but based on total cash generation capacity, not just what is paid out.',
    formula: 'FCF Yield = Free Cash Flow ÷ Market Cap × 100',
    interpretation: 'Higher is better. An FCF yield above 5% is generally attractive. It shows how much cash the business generates for every dollar of market value — a measure of real shareholder returns.',
    benchmark: 'Below 2%: low. 2–5%: moderate. 5–8%: attractive. Above 8%: very high (possible value trap — check sustainability)',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Value Factor)'],
    tags: ['cash flow', 'yield', 'valuation'],
  },
  {
    id: 'graham_number',
    name: 'Graham Number',
    category: 'Valuation',
    shortDesc: 'Benjamin Graham\'s intrinsic value estimate based on EPS and book value',
    definition: 'The Graham Number is a classic intrinsic value estimate from Benjamin Graham\'s value investing framework. It calculates a fair price using both earnings and book value, suggesting a stock is cheap if its price is below the Graham Number.',
    formula: 'Graham Number = √(22.5 × EPS × Book Value Per Share)',
    interpretation: 'If current price < Graham Number, the stock may be undervalued by Graham\'s criteria. A useful quick screen but designed for stable, profitable companies — not suitable for loss-makers, high-growth, or asset-light businesses.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['intrinsic value', 'Graham', 'valuation'],
  },

  // ── PROFITABILITY ──────────────────────────────────────────────────────────
  {
    id: 'gross_margin',
    name: 'Gross Margin',
    category: 'Profitability',
    shortDesc: 'Revenue remaining after direct costs of production',
    definition: 'Gross margin is revenue minus cost of goods sold (COGS), expressed as a percentage of revenue. It reflects pricing power and the efficiency of production/delivery. High gross margins are a hallmark of competitive advantage.',
    formula: 'Gross Margin = (Revenue − COGS) ÷ Revenue × 100',
    interpretation: 'Higher is better. Software/SaaS companies often achieve 70–90%+ gross margins. Retailers and manufacturers typically show 20–40%. A declining gross margin signals pricing pressure or rising input costs.',
    benchmark: 'Retail: 20–35%. Manufacturing: 25–45%. Healthcare: 50–70%. Software: 65–90%',
    usedIn: ['Screener', 'Company Detail', 'Financials Tab'],
    tags: ['margin', 'cost', 'profitability'],
  },
  {
    id: 'ebitda_margin',
    name: 'EBITDA Margin',
    category: 'Profitability',
    shortDesc: 'Operating earnings as % of revenue before non-cash and financing items',
    definition: 'EBITDA Margin is EBITDA divided by revenue. It measures operational profitability before the effects of capital structure (interest), tax jurisdiction, and accounting policies (depreciation/amortisation). Useful for cross-company comparison.',
    formula: 'EBITDA Margin = EBITDA ÷ Revenue × 100',
    interpretation: 'Higher is better. EBITDA margin strips out the impact of debt levels and depreciation, making it ideal for comparing companies across industries and capital structures.',
    benchmark: 'Retail: 5–10%. Industrials: 15–20%. Healthcare: 20–30%. Software: 25–45%',
    usedIn: ['Screener', 'Company Detail', 'Financials Tab'],
    tags: ['margin', 'EBITDA', 'profitability'],
  },
  {
    id: 'net_margin',
    name: 'Net Profit Margin',
    category: 'Profitability',
    shortDesc: 'Final profit as % of revenue after all costs, interest, and tax',
    definition: 'Net margin is the bottom-line profitability — what percentage of every dollar in revenue actually becomes profit after paying all expenses including interest and tax. It is the most comprehensive profitability metric.',
    formula: 'Net Margin = Net Profit ÷ Revenue × 100',
    interpretation: 'Higher is better. A net margin above 10% is generally considered strong for most industries. Persistently positive net margins are critical — loss-making companies need to demonstrate a clear path to profitability.',
    benchmark: 'Banks: 20–30%. Software: 15–30%. Healthcare: 10–20%. Retail: 2–5%',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Quality Factor)', 'Value Scans'],
    tags: ['profit', 'net income', 'margin'],
  },
  {
    id: 'operating_margin',
    name: 'Operating Margin (EBIT Margin)',
    category: 'Profitability',
    shortDesc: 'Operating profit as % of revenue, before interest and tax',
    definition: 'Operating margin (also called EBIT margin) measures profitability from core business operations, excluding interest and taxes. It shows how efficiently a company runs its operations independent of how it is financed.',
    formula: 'Operating Margin = EBIT ÷ Revenue × 100',
    interpretation: 'Between gross margin and net margin. A company with high gross margin but low operating margin may have excessive operating expenses (SG&A, R&D). Stable or expanding operating margins signal operational leverage.',
    usedIn: ['Screener', 'Company Detail', 'Financials Tab'],
    tags: ['EBIT', 'margin', 'operations'],
  },
  {
    id: 'roe',
    name: 'ROE (Return on Equity)',
    category: 'Profitability',
    shortDesc: 'How efficiently a company generates profit from shareholder equity',
    definition: 'ROE measures how much profit a company generates per dollar of shareholders\' equity. It is a key indicator of management quality and business efficiency. Warren Buffett famously looks for businesses with consistently high ROE.',
    formula: 'ROE = Net Profit ÷ Shareholders\' Equity × 100',
    interpretation: 'Higher is better. ROE above 15% is generally excellent. However, very high ROE can be artificially inflated by excessive debt (leverage), so always check alongside debt-to-equity.',
    benchmark: 'Below 10%: weak. 10–15%: adequate. 15–20%: good. Above 20%: excellent',
    example: 'A company with $500M shareholders\' equity earns $100M net profit → ROE = 100÷500 = 20%. Held for 5 years with reinvested profits, this compounds the equity base significantly.',
    beginnerTip: 'ROE tells you: for every $100 shareholders have invested in this company, how much profit did it earn? An ROE of 20% means it earned $20 for every $100 invested — like getting 20% interest on a bank deposit. The higher the better, as long as it\'s not driven by excessive debt.',
    beginner: true,
    relatedMetrics: ['roa', 'roic', 'roce', 'debt_to_equity'],
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Quality Factor)', 'Quality Scans'],
    tags: ['equity', 'return', 'profitability'],
  },
  {
    id: 'roa',
    name: 'ROA (Return on Assets)',
    category: 'Profitability',
    shortDesc: 'Profit generated per dollar of total assets',
    definition: 'ROA measures how efficiently a company uses its total assets to generate profit. Unlike ROE, it is not affected by debt levels, making it a purer measure of operational efficiency.',
    formula: 'ROA = Net Profit ÷ Total Assets × 100',
    interpretation: 'Higher is better. Asset-heavy businesses (banks, utilities, manufacturers) have lower ROA than asset-light businesses (software, services). Compare within industry.',
    benchmark: 'Banks: 1–2%. Manufacturing: 5–10%. Software/services: 10–20%+',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['assets', 'return', 'efficiency'],
  },
  {
    id: 'roce',
    name: 'ROCE (Return on Capital Employed)',
    category: 'Profitability',
    shortDesc: 'Operating profit relative to all long-term capital deployed',
    definition: 'ROCE measures efficiency across all capital sources (equity + debt). It answers: "For every dollar of capital committed to this business, how much operating profit is generated?" It is favoured by many value investors as the most comprehensive capital efficiency metric.',
    formula: 'ROCE = EBIT ÷ (Total Equity + Long-term Debt) × 100',
    interpretation: 'ROCE consistently above the cost of capital (typically 8–12%) indicates value creation. ROCE below WACC destroys value. A widening gap between ROCE and WACC is a strong sign of competitive advantage.',
    benchmark: 'Below 8%: value-destroying. 8–15%: adequate. 15–25%: good. Above 25%: exceptional',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Quality Factor)'],
    tags: ['capital', 'return', 'efficiency'],
  },

  // ── DIVIDENDS ──────────────────────────────────────────────────────────────
  {
    id: 'dividend_yield',
    name: 'Dividend Yield',
    category: 'Dividends & Income',
    shortDesc: 'Annual dividends as % of current share price',
    definition: 'Dividend yield shows annual dividend income relative to current price. It is the most basic income metric — how much cash you receive per year for every dollar invested at today\'s price.',
    formula: 'Dividend Yield = Annual DPS ÷ Share Price × 100',
    interpretation: 'Higher yield sounds better but can signal a distressed business. A yield significantly above peers often means the market expects a dividend cut. Always check payout ratio and cash flow sustainability alongside yield.',
    benchmark: 'ASX average: 3.5–4.5%. Banks: 4–7%. REITs: 4–7%. Growth stocks: 0–2%',
    example: 'A stock at $10.00 pays $0.45/year in dividends → Yield = 0.45÷10 = 4.5%. If the price falls to $8.00, the yield rises to 5.6% — making it look more attractive, but check if the business is in trouble first.',
    beginnerTip: 'Dividend yield is like the annual "interest rate" you earn just for holding the stock. A 5% yield on a $10,000 investment means you\'d receive $500/year in cash without selling anything. But be careful — very high yields can mean the market expects the dividend to be cut.',
    beginner: true,
    relatedMetrics: ['grossed_up_yield', 'payout_ratio', 'franking_pct', 'dividend_cagr_3y'],
    usedIn: ['Screener', 'Company Detail', 'Dividend Scans', 'Composite Score (Income Factor)', 'Market Overview'],
    tags: ['dividends', 'income', 'yield'],
  },
  {
    id: 'grossed_up_yield',
    name: 'Grossed-Up Yield',
    category: 'Dividends & Income',
    shortDesc: 'True dividend yield including the value of franking credit tax offsets',
    definition: 'Unique to Australia, grossed-up yield adds the value of franking credits (imputation tax offsets) to the dividend yield. A fully franked dividend of 5% is worth ~7.14% to a taxpayer at the 30% corporate rate because you can claim the corporate tax back.',
    formula: 'Grossed-Up Yield = Dividend Yield × (1 + Franking% × (Corporate Tax Rate ÷ (1 − Corporate Tax Rate)))\n= Dividend Yield × (1 + Franking% × 0.4286) at 30% corporate tax',
    interpretation: 'The true income for Australian resident investors. Critical for superannuation funds and retirees who can receive franking credits as cash refunds. Always compare ASX stocks on grossed-up yield rather than raw yield.',
    benchmark: 'Fully franked 4% yield = ~5.7% grossed-up. A grossed-up yield above 6% is excellent for income investors',
    example: 'Stock pays a 5% fully franked dividend. Grossed-up yield = 5% × (1 + 1.0 × 0.4286) = 5% × 1.4286 = 7.14%. An SMSF in pension phase would receive the full 7.14% value (2.14% as a tax refund cheque).',
    beginnerTip: 'This is the "true" yield for Australian investors. Franking credits are like a bonus tax refund from the ATO. A fully franked 5% dividend is actually worth 7.14% to you — the company already paid the 30% tax and passes it on as a credit you can claim. Always compare ASX income stocks using this number, not the raw yield.',
    beginner: true,
    relatedMetrics: ['dividend_yield', 'franking_pct', 'payout_ratio'],
    usedIn: ['Screener', 'Company Detail', 'Dividend Scans', 'Composite Score (Income Factor)', 'Top 5 Strategy'],
    tags: ['franking', 'dividends', 'Australia', 'tax', 'income'],
  },
  {
    id: 'franking_pct',
    name: 'Franking Percentage',
    category: 'Dividends & Income',
    shortDesc: 'Proportion of dividends carrying attached franking credits',
    definition: 'Franking credits (also called imputation credits) represent corporate tax already paid by the company on your behalf. 100% franking means the full dividend carries corporate tax credits. Partially franked dividends carry credits proportional to the franking percentage.',
    formula: 'Franking Credit per share = DPS × Franking% × (Corporate Tax Rate ÷ (1 − Corporate Tax Rate))',
    interpretation: '100% franking is the ideal for Australian resident income investors. Offshore companies, miners with overseas earnings, and many REITs often pay unfranked dividends.',
    benchmark: 'Fully franked (100%): most ASX banks, Telstra. Partial/unfranked: miners, REITs, overseas earners',
    usedIn: ['Screener', 'Company Detail', 'Dividend Scans', 'Composite Score (Income Factor)'],
    tags: ['franking', 'tax', 'Australia', 'dividends'],
  },
  {
    id: 'payout_ratio',
    name: 'Payout Ratio',
    category: 'Dividends & Income',
    shortDesc: 'Percentage of earnings paid out as dividends',
    definition: 'Payout ratio measures dividend sustainability — how much of net profit is distributed as dividends. A low payout ratio means dividends are well-covered; a high ratio raises the risk of a dividend cut if earnings decline.',
    formula: 'Payout Ratio = Annual DPS ÷ EPS × 100',
    interpretation: 'Payout below 60% is generally sustainable. Above 80% leaves little buffer for earnings declines. Above 100% means dividends are being paid from reserves or debt — unsustainable long-term.',
    benchmark: 'Sustainable: <60%. Moderate risk: 60–80%. High risk: >80%. Unsustainable: >100%',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Income Factor)'],
    tags: ['dividends', 'sustainability', 'earnings'],
  },
  {
    id: 'dividend_consecutive_yrs',
    name: 'Consecutive Dividend Years',
    category: 'Dividends & Income',
    shortDesc: 'Number of consecutive years of uninterrupted dividend payments',
    definition: 'Tracks how many consecutive years a company has paid dividends without interruption. A long streak indicates financial stability and management commitment to returning capital. Companies that cut dividends typically suffer significant share price falls.',
    interpretation: 'Longer streaks indicate more reliable income. 10+ years of consecutive dividends is a strong quality signal for income investors. Compare against dividend history during GFC (2009) and COVID (2020) — companies that maintained payments are most reliable.',
    benchmark: '1–5 years: early stage. 5–10 years: established. 10+ years: strong track record. 20+ years: dividend aristocrat',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Income Factor)'],
    tags: ['dividends', 'history', 'reliability'],
  },
  {
    id: 'dividend_cagr_3y',
    name: 'Dividend CAGR (3 Year)',
    category: 'Dividends & Income',
    shortDesc: 'Compound annual growth rate of dividends over 3 years',
    definition: 'Measures how fast dividends have been growing on a compounded annual basis over the past 3 years. Growing dividends compound over time — a stock that starts lower-yielding but grows dividends rapidly can outperform a static high-yielder.',
    formula: 'CAGR = (Current DPS ÷ DPS 3 years ago)^(1/3) − 1',
    interpretation: 'Dividend CAGR above inflation (2–3%) is the minimum to maintain real purchasing power. CAGR of 8–12% is excellent. Negative CAGR signals dividend cuts — a red flag for income investors.',
    benchmark: 'Below 3%: stagnant. 3–7%: modest growth. 7–12%: strong. Above 12%: excellent',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Income Factor)'],
    tags: ['dividends', 'growth', 'CAGR'],
  },

  // ── GROWTH ─────────────────────────────────────────────────────────────────
  {
    id: 'revenue_growth_1y',
    name: 'Revenue Growth (1 Year)',
    category: 'Growth',
    shortDesc: 'Year-over-year change in total revenue',
    definition: 'Measures how much revenue has grown compared to the same period last year. Top-line growth is the foundation of compounding — businesses that cannot grow revenue struggle to grow earnings long-term.',
    formula: 'Revenue Growth = (Current Revenue − Prior Year Revenue) ÷ Prior Year Revenue × 100',
    interpretation: 'Consistent double-digit revenue growth is a strong signal for growth stocks. Negative revenue growth (revenue decline) is a serious red flag unless cyclical. Compare growth rates across the full business cycle.',
    benchmark: 'Flat/declining: <0%. Modest: 0–5%. Solid: 5–15%. Strong: 15–25%. Hypergrowth: 25%+',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Growth Factor)', 'Growth Scans'],
    tags: ['revenue', 'growth', 'top-line'],
  },
  {
    id: 'revenue_growth_hoh',
    name: 'Revenue Growth (Half-on-Half) ★',
    category: 'Growth',
    shortDesc: 'Revenue change from H1 to H2 — unique to ASX half-yearly reporting',
    definition: 'ASX-specific metric. Australian companies report half-yearly (H1 = July–December, H2 = January–June). Half-on-half growth compares the latest half-year to the preceding half-year, showing the most current business momentum — faster-moving than annual comparisons.',
    formula: 'HoH Growth = (Latest Half Revenue − Prior Half Revenue) ÷ Prior Half Revenue × 100',
    interpretation: 'A company showing accelerating HoH revenue growth while annual figures look modest may be rapidly improving. This metric catches inflection points earlier than annual data. Declining HoH growth is an early warning sign.',
    usedIn: ['Screener', 'Company Detail', 'Growth Scans (Half-Yearly Acceleration)', 'Composite Score (Growth Factor)'],
    tags: ['revenue', 'half-yearly', 'ASX', 'momentum', 'growth'],
  },
  {
    id: 'earnings_growth_1y',
    name: 'Earnings Growth (1 Year)',
    category: 'Growth',
    shortDesc: 'Year-over-year change in net profit',
    definition: 'Measures how much net earnings (profit after tax) have grown compared to the prior year. Earnings growth drives long-term share price appreciation — over time, share prices follow earnings.',
    formula: 'Earnings Growth = (Current Net Profit − Prior Year Net Profit) ÷ |Prior Year Net Profit| × 100',
    interpretation: 'Sustained earnings growth of 10–15%+ compounds powerfully over time. Earnings growth significantly above revenue growth suggests improving margins. Watch for earnings beats/misses against analyst estimates.',
    benchmark: 'Below 0%: declining. 0–10%: modest. 10–20%: solid. 20%+: strong growth',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Growth Factor)', 'Growth Scans'],
    tags: ['earnings', 'profit', 'growth'],
  },
  {
    id: 'eps_growth_3y_cagr',
    name: 'EPS CAGR (3 Year)',
    category: 'Growth',
    shortDesc: 'Compound annual earnings per share growth over 3 years',
    definition: 'Smooths out short-term volatility by showing the compound annual growth rate of earnings per share over 3 years. A more reliable indicator of genuine business quality than single-year earnings.',
    formula: 'EPS CAGR = (Current EPS ÷ EPS 3 years ago)^(1/3) − 1',
    interpretation: 'EPS CAGR above 10–15% over 3 years is the hallmark of a quality compounder. Ensure EPS growth comes from genuine business improvement, not just buybacks reducing share count.',
    benchmark: 'Below 5%: weak. 5–10%: adequate. 10–15%: good. 15%+: excellent',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Growth Factor)'],
    tags: ['EPS', 'growth', 'CAGR'],
  },
  {
    id: 'revenue_cagr_5y',
    name: 'Revenue CAGR (5 Year)',
    category: 'Growth',
    shortDesc: 'Compound annual revenue growth over 5 years',
    definition: '5-year revenue CAGR provides a long-term view of business growth durability, smoothing out economic cycles and one-off events. It distinguishes genuine compounders from one-year wonders.',
    formula: 'Revenue CAGR = (Current Revenue ÷ Revenue 5 years ago)^(1/5) − 1',
    interpretation: 'A business growing revenue at 10%+ CAGR for 5 years is demonstrating durable competitive advantage. 15%+ over 5 years is exceptional. Adjust for acquisitions.',
    benchmark: 'Below 3%: stagnant. 3–8%: steady. 8–15%: strong. 15%+: exceptional compounder',
    example: 'Revenue of $100M 5 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/5) − 1 = 14.9% a year.',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Growth Factor)'],
    tags: ['revenue', 'CAGR', '5-year', 'growth'],
  },

  // ── FINANCIAL HEALTH ───────────────────────────────────────────────────────
  {
    id: 'piotroski_f_score',
    name: 'Piotroski F-Score',
    category: 'Financial Health',
    shortDesc: '9-point financial health score based on profitability, leverage, and efficiency signals',
    definition: 'Developed by accounting professor Joseph Piotroski, the F-Score is a 0–9 score calculated from 9 binary accounting signals across three categories: Profitability (4 signals), Leverage/Liquidity (3 signals), and Operating Efficiency (2 signals). Each signal scores 1 if positive, 0 if negative.',
    formula: 'F-Score = Profitability (4 pts) + Leverage/Liquidity (3 pts) + Operating Efficiency (2 pts)\nSignals include: positive ROA, positive CFO, improving ROA, accruals ratio, improving leverage, improving current ratio, no dilution, improving gross margin, improving asset turnover',
    interpretation: 'F-Score 0–2: financially weak, potential short candidate. F-Score 3–6: average. F-Score 7–9: financially strong, historically outperforms. Strong backtests show buying F-Score 8–9 stocks significantly outperforms the market.',
    benchmark: '0–2: weak (avoid or short). 3–6: neutral. 7–9: strong (buy signal)',
    example: 'A company scores: positive ROA ✓, positive CFO ✓, improving ROA ✓, low accruals ✓, falling debt ✓, improving current ratio ✓, no dilution ✓, improving gross margin ✓, improving asset turnover ✗ → F-Score = 8/9 — financially very strong.',
    beginnerTip: 'Think of the Piotroski F-Score like a health check-up for a company\'s finances. It checks 9 simple yes/no questions: Is it making money? Is it generating real cash? Is it getting more or less debt? A score of 8 or 9 out of 9 means the company is in excellent financial shape across the board.',
    beginner: true,
    relatedMetrics: ['altman_z_score', 'debt_to_equity', 'current_ratio', 'roe'],
    usedIn: ['Screener', 'Company Detail', 'Quality Scans', 'Composite Score (Quality Factor)', 'Top 5 Strategy'],
    tags: ['quality', 'financial health', 'Piotroski', 'score'],
  },
  {
    id: 'altman_z_score',
    name: 'Altman Z-Score',
    category: 'Financial Health',
    shortDesc: 'Bankruptcy prediction score combining 5 financial ratios',
    definition: 'Developed by Edward Altman, the Z-Score predicts the probability of corporate bankruptcy within 2 years using 5 weighted financial ratios: working capital/assets, retained earnings/assets, EBIT/assets, market cap/book liabilities, and revenue/assets.',
    formula: 'Z = 1.2×(Working Capital/Assets) + 1.4×(Retained Earnings/Assets) + 3.3×(EBIT/Assets) + 0.6×(Market Cap/Book Liabilities) + 1.0×(Revenue/Assets)',
    interpretation: 'Z < 1.81: distress zone (high bankruptcy risk). Z 1.81–2.99: grey zone. Z > 2.99: safe zone. Originally designed for manufacturers — less accurate for financial firms and service businesses.',
    benchmark: 'Below 1.81: danger. 1.81–2.99: caution. Above 2.99: healthy',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Quality Factor)'],
    tags: ['bankruptcy', 'risk', 'Altman', 'financial health'],
  },
  {
    id: 'debt_to_equity',
    name: 'Debt-to-Equity Ratio',
    category: 'Financial Health',
    shortDesc: 'Total debt relative to shareholders\' equity',
    definition: 'D/E measures financial leverage — how much debt a company uses relative to equity. High leverage amplifies both gains and losses. It is critical to assess whether a company\'s debt level is sustainable relative to its earnings and cash flows.',
    formula: 'D/E = Total Debt ÷ Shareholders\' Equity',
    interpretation: 'Below 0.5: conservative. 0.5–1.5: moderate. Above 1.5: elevated (acceptable in stable cash-flow businesses). Above 3: high risk unless in capital-intensive industry like utilities or property. Negative equity makes D/E meaningless.',
    benchmark: 'Tech/services: <0.3. Industrials: 0.3–1.0. Banks: 8–12× (different measure). REITs: 0.5–1.5',
    example: 'Company has $300M total debt and $500M shareholders\' equity → D/E = 0.6×. For every $1 of equity, there is $0.60 of debt. A utility with $2B debt and $1B equity has D/E = 2.0× — high, but acceptable given stable cash flows.',
    beginnerTip: 'D/E is like a personal finance check: if someone earns $100k but owes $50k on their mortgage, their D/E is 0.5× — manageable. If they owe $300k, it\'s 3× — very leveraged. High debt isn\'t automatically bad (it amplifies gains too), but it amplifies losses and creates risk if the business hits trouble.',
    beginner: true,
    relatedMetrics: ['current_ratio', 'debt_to_ebitda', 'net_debt_to_ebitda', 'altman_z_score'],
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Quality Factor)', 'Value Scans'],
    tags: ['debt', 'leverage', 'risk'],
  },
  {
    id: 'current_ratio',
    name: 'Current Ratio',
    category: 'Financial Health',
    shortDesc: 'Ability to pay short-term obligations with current assets',
    definition: 'The current ratio compares current assets (cash, receivables, inventory) to current liabilities (short-term debt, payables). It measures short-term liquidity — can the company pay its bills over the next 12 months?',
    formula: 'Current Ratio = Current Assets ÷ Current Liabilities',
    interpretation: 'Below 1.0: potential liquidity risk. 1.0–1.5: adequate. 1.5–3.0: healthy. Above 3.0: very conservative (potentially inefficient use of assets). Context matters — supermarkets can operate with current ratios below 1 due to fast inventory turns.',
    benchmark: 'Below 1.0: risk. 1.0–1.5: adequate. 1.5–2.5: healthy. Above 3.0: overcapitalised',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['liquidity', 'short-term', 'health'],
  },
  {
    id: 'fcf_fy0',
    name: 'Free Cash Flow (FCF)',
    category: 'Financial Health',
    shortDesc: 'Cash generated after all capital expenditures',
    definition: 'Free cash flow is the cash a business generates from operations after paying for capital expenditure needed to maintain or grow the business. It is the truest measure of financial health — "cash is king" in fundamental analysis.',
    formula: 'FCF = Operating Cash Flow − Capital Expenditure',
    interpretation: 'Positive and growing FCF is the hallmark of a quality business. Consistently negative FCF requires funding from debt or equity issuance. FCF significantly below net profit may signal earnings quality issues.',
    usedIn: ['Screener', 'Company Detail', 'Turnaround Scan', 'Quality Scans'],
    tags: ['cash flow', 'FCF', 'financial health'],
  },

  // ── TECHNICALS ─────────────────────────────────────────────────────────────
  {
    id: 'rsi_14',
    name: 'RSI-14 (Relative Strength Index)',
    category: 'Technical Indicators',
    shortDesc: 'Momentum oscillator measuring speed and magnitude of price movements (0–100)',
    definition: 'RSI is a momentum oscillator that measures the speed and magnitude of recent price changes to evaluate overbought or oversold conditions. RSI-14 uses a 14-period (usually days) lookback window. It oscillates between 0 and 100.',
    formula: 'RSI = 100 − (100 ÷ (1 + RS))\nRS = Average Gain over 14 periods ÷ Average Loss over 14 periods',
    interpretation: 'RSI below 30: oversold — potential buy signal or downtrend continuation. RSI above 70: overbought — potential sell signal or strong trend. RSI between 40–60: neutral zone. In strong uptrends, RSI can stay above 60 for extended periods.',
    benchmark: '<30: oversold. 30–50: bearish bias. 50–70: bullish bias. >70: overbought',
    example: 'Stock falls 8 of the last 14 days, avg gain = 0.3%, avg loss = 0.9% → RS = 0.3÷0.9 = 0.33 → RSI = 100 − (100÷1.33) = 24.8. Below 30 signals potential oversold bounce — but confirm with a trend check.',
    beginnerTip: 'RSI is like a thermometer for a stock\'s recent price momentum. A reading below 30 means the stock has been falling fast and might be "oversold" (due for a bounce). Above 70 means it\'s been rising very quickly and might be "overbought" (due for a pullback). It doesn\'t tell you which direction — only how hot or cold the recent moves have been.',
    beginner: true,
    relatedMetrics: ['adx_14', 'macd', 'sma_50', 'momentum_3m'],
    usedIn: ['Screener', 'Company Detail', 'Technical Tab', 'RSI Oversold Scan', 'RSI Overbought Scan', 'Turnaround Scan', 'Composite Score (Momentum Factor)'],
    tags: ['RSI', 'momentum', 'overbought', 'oversold', 'technical'],
  },
  {
    id: 'adx_14',
    name: 'ADX-14 (Average Directional Index)',
    category: 'Technical Indicators',
    shortDesc: 'Measures trend strength (not direction) on a 0–100 scale',
    definition: 'ADX measures the strength of a price trend regardless of direction. A rising ADX means the trend (up or down) is strengthening. ADX does NOT indicate direction — only strength. Used to distinguish trending markets from ranging/choppy markets.',
    formula: 'ADX = Smoothed average of DX over 14 periods\nDX = |+DI − −DI| ÷ (|+DI + −DI|) × 100',
    interpretation: 'ADX below 20: weak/no trend (avoid trend-following strategies). ADX 20–25: emerging trend. ADX 25–40: strong trend. ADX above 40: very strong trend (often signals climax/exhaustion approaching).',
    benchmark: '<20: no trend. 20–25: weak trend. 25–40: strong trend. >40: very strong',
    usedIn: ['Screener', 'Company Detail', 'Momentum Scan', 'Volume Breakout Scan', 'Composite Score (Momentum Factor)'],
    tags: ['ADX', 'trend strength', 'technical'],
  },
  {
    id: 'macd',
    name: 'MACD (Moving Average Convergence Divergence)',
    category: 'Technical Indicators',
    shortDesc: 'Trend-following momentum indicator showing relationship between two EMAs',
    definition: 'MACD shows the relationship between two exponential moving averages (EMA). It consists of the MACD line (12-day EMA minus 26-day EMA) and the Signal line (9-day EMA of MACD). Crossovers and divergences from price generate trade signals.',
    formula: 'MACD Line = EMA(12) − EMA(26)\nSignal Line = EMA(9) of MACD Line\nHistogram = MACD Line − Signal Line',
    interpretation: 'Bullish: MACD crosses above Signal line. Bearish: MACD crosses below Signal line. MACD above 0: bullish trend. MACD below 0: bearish trend. Divergence between MACD and price is a powerful reversal signal.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['MACD', 'trend', 'momentum', 'EMA', 'technical'],
  },
  {
    id: 'sma_50',
    name: 'SMA-50 (50-Day Moving Average)',
    category: 'Technical Indicators',
    shortDesc: 'Average closing price over the past 50 trading days',
    definition: 'The 50-day simple moving average smooths short-term volatility and is widely watched by institutional investors as a medium-term trend indicator. Price above SMA-50 is broadly considered bullish; below is bearish.',
    formula: 'SMA-50 = Sum of last 50 closing prices ÷ 50',
    interpretation: 'Price above SMA-50: medium-term uptrend. Price below SMA-50: medium-term downtrend. SMA-50 crossing above SMA-200 = Golden Cross (bullish). SMA-50 crossing below SMA-200 = Death Cross (bearish).',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab', 'Golden Cross Scan'],
    tags: ['moving average', 'SMA', 'trend', 'technical'],
  },
  {
    id: 'sma_200',
    name: 'SMA-200 (200-Day Moving Average)',
    category: 'Technical Indicators',
    shortDesc: 'Average closing price over the past 200 trading days — the key long-term trend line',
    definition: 'The 200-day moving average is the most widely watched technical indicator by fund managers and institutional investors. It defines the primary long-term trend. Price above SMA-200 = long-term bull market. Below = long-term bear market.',
    formula: 'SMA-200 = Sum of last 200 closing prices ÷ 200',
    interpretation: 'The single most important moving average. Many professional fund managers will not buy a stock trading below its 200-day MA. It acts as strong support in uptrends and resistance in downtrends.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab', 'Golden Cross Scan', 'Momentum Scan', 'Composite Score (Momentum Factor)'],
    tags: ['moving average', 'SMA', 'long-term trend', 'technical'],
  },
  {
    id: 'volatility_20d',
    name: 'Volatility (20-Day)',
    category: 'Technical Indicators',
    shortDesc: 'Annualised standard deviation of daily returns over 20 days',
    definition: 'Volatility measures how much a stock\'s price swings day-to-day. 20-day volatility is the annualised standard deviation of daily returns over the past 20 trading days. Higher volatility means larger price swings — both up and down.',
    formula: 'Vol = StdDev(daily returns over 20 days) × √252 × 100',
    interpretation: 'Low-volatility stocks (under 20%) are stable. Mid-range (20–40%) is typical for most stocks. High-volatility (40%+) stocks carry higher risk but may offer higher reward. Compare a stock\'s volatility against its sector average.',
    benchmark: 'ASX large caps: 15–25%. Mid caps: 25–40%. Small caps/speculative: 40–80%+',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['volatility', 'risk', 'standard deviation'],
  },
  {
    id: 'beta_1y',
    name: 'Beta (1 Year)',
    category: 'Technical Indicators',
    shortDesc: 'Sensitivity of stock price movements relative to the ASX200',
    definition: 'Beta measures how much a stock moves relative to the overall market (ASX200). Beta is calculated by regressing the stock\'s daily returns against the index returns over the past year.',
    formula: 'Beta = Covariance(Stock, Market) ÷ Variance(Market)',
    interpretation: 'Beta = 1: moves in line with market. Beta > 1: amplifies market moves (e.g., Beta 1.5 = stock moves 1.5× the index). Beta < 1: more stable than market (defensive). Beta < 0: moves inversely to market (very rare).',
    benchmark: 'Defensive: <0.7. Market-like: 0.7–1.3. Aggressive: 1.3–2.0. Highly speculative: >2.0',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['beta', 'market sensitivity', 'risk', 'correlation'],
  },
  {
    id: 'sharpe_1y',
    name: 'Sharpe Ratio (1 Year)',
    category: 'Technical Indicators',
    shortDesc: 'Risk-adjusted return — return per unit of volatility taken',
    definition: 'The Sharpe ratio measures how much return you earn per unit of risk. It divides excess returns (above the risk-free rate) by the standard deviation of returns. A Sharpe ratio above 1 means the return is more than adequate compensation for the risk.',
    formula: 'Sharpe = (Stock Return − Risk-Free Rate) ÷ Standard Deviation of Returns',
    interpretation: 'Below 0: negative risk-adjusted return. 0–1: modest. 1–2: good. Above 2: excellent. Many institutional investors target Sharpe ratios above 1 for their portfolios.',
    benchmark: '<0: poor. 0–0.5: below average. 0.5–1.0: adequate. 1.0–2.0: good. >2.0: excellent',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['Sharpe', 'risk-adjusted', 'return'],
  },
  {
    id: 'drawdown_from_ath',
    name: 'Drawdown from All-Time High',
    category: 'Technical Indicators',
    shortDesc: 'How far the stock is below its all-time high price',
    definition: 'Maximum drawdown from ATH shows peak-to-current loss. A large drawdown can signal distress but can also represent opportunity for mean-reversion investors.',
    formula: 'Drawdown = (Current Price − All-Time High) ÷ All-Time High × 100',
    interpretation: 'Small drawdowns (0–15%): near highs, strong trend. Moderate (15–35%): normal correction. Large (35–60%): significant decline. Severe (60%+): major distress or structural decline.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['drawdown', 'ATH', 'price', 'technical'],
  },

  // ── RETURNS ────────────────────────────────────────────────────────────────
  {
    id: 'return_1w',
    name: 'Return (1 Week)',
    category: 'Price & Returns',
    shortDesc: 'Price change over the past 5 trading days',
    definition: 'The percentage price change over the past 5 trading days. Used to identify very short-term momentum and recent news-driven moves.',
    formula: 'Return 1W = (Current Price − Price 5 days ago) ÷ Price 5 days ago × 100',
    usedIn: ['Screener', 'Market Overview', 'Movers Widget', 'Volume Breakout Scan'],
    tags: ['return', 'short-term', 'momentum'],
  },
  {
    id: 'return_1m',
    name: 'Return (1 Month)',
    category: 'Price & Returns',
    shortDesc: 'Price change over the past month (~21 trading days)',
    definition: 'The percentage price change over the past month. A key short-to-medium term momentum signal. Used in momentum factor scoring.',
    formula: 'Return 1M = (Current Price − Price ~21 days ago) ÷ Price ~21 days ago × 100',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Momentum Factor)', 'Golden Cross Scan'],
    tags: ['return', 'momentum', 'monthly'],
  },
  {
    id: 'return_3m',
    name: 'Return (3 Month)',
    category: 'Price & Returns',
    shortDesc: 'Price change over the past quarter (~63 trading days)',
    definition: 'The 3-month return is one of the most widely used momentum signals in quantitative finance. Research consistently shows that stocks with strong 3-month returns tend to continue outperforming over the next 3–6 months.',
    formula: 'Return 3M = (Current Price − Price ~63 days ago) ÷ Price ~63 days ago × 100',
    interpretation: 'Positive 3M return above 10% indicates strong momentum. Combined with fundamentals, 3M momentum is a reliable factor for stock selection.',
    usedIn: ['Screener', 'Company Detail', 'Momentum Scan', 'Composite Score (Momentum Factor)', '52W Highs Scan', 'Top 5 Strategy'],
    tags: ['return', 'momentum', 'quarterly'],
  },
  {
    id: 'return_1y',
    name: 'Return (1 Year)',
    category: 'Price & Returns',
    shortDesc: 'Total price change over the past 12 months',
    definition: '12-month return captures a full annual performance cycle. It is the most common benchmark for individual stock performance and is used heavily in performance attribution.',
    formula: 'Return 1Y = (Current Price − Price 12 months ago) ÷ Price 12 months ago × 100',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Momentum Factor)', 'Top 5 Strategy'],
    tags: ['return', 'annual', 'performance'],
  },
  {
    id: 'return_ytd',
    name: 'Return (Year-to-Date)',
    category: 'Price & Returns',
    shortDesc: 'Price return since 1 January of the current year',
    definition: 'YTD return shows how the stock has performed since the start of the current calendar year. Widely used for year-end performance reporting and comparison against indices.',
    formula: 'Return YTD = (Current Price − Price at Jan 1) ÷ Price at Jan 1 × 100',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['return', 'YTD', 'calendar year'],
  },
  {
    id: 'high_52w',
    name: '52-Week High',
    category: 'Price & Returns',
    shortDesc: 'Highest price reached in the past 52 weeks',
    definition: 'The highest intraday price over the past 52 weeks. Stocks trading near their 52W high are showing strength; stocks trading near their 52W low are showing weakness. Used in momentum and contrarian strategies.',
    interpretation: 'Price near 52W high: strong momentum, breakout candidate. Price near 52W low: potential recovery or continued decline. Research shows that stocks breaking to new 52W highs often continue higher.',
    usedIn: ['Screener', 'Company Detail', '52W Highs Scan', '52W Lows Scan'],
    tags: ['52-week', 'price', 'high', 'momentum'],
  },
  {
    id: 'pct_from_52w_low',
    name: '% from 52-Week Low',
    category: 'Price & Returns',
    shortDesc: 'How far current price is above the 52-week low point',
    definition: 'Measures the percentage distance between current price and the lowest price over the past 52 weeks. Used to identify stocks that are near their lows — potential recovery candidates or continued downtrends.',
    formula: 'Pct from Low = (Current Price − 52W Low) ÷ 52W Low × 100',
    interpretation: '0–10%: very close to lows (near 52W Lows scan). 10–30%: recovered somewhat. 50%+: significant recovery from lows.',
    usedIn: ['Screener', '52W Lows Scan'],
    tags: ['52-week', 'low', 'recovery', 'mean reversion'],
  },
  {
    id: 'volume',
    name: 'Volume',
    category: 'Price & Returns',
    shortDesc: 'Number of shares traded on the most recent trading day',
    definition: 'Daily trading volume is the total number of shares exchanged between buyers and sellers. Volume confirms price moves — a breakout on high volume is more significant than one on low volume.',
    interpretation: 'High volume confirms price trends. Breakouts on 2× average volume or more are significantly more reliable. Low-volume price rises can be manipulated or unsustainable.',
    usedIn: ['Screener', 'Company Detail', 'Volume Breakout Scan', 'Market Overview'],
    tags: ['volume', 'liquidity', 'trading'],
  },
  {
    id: 'avg_volume_20d',
    name: 'Average Volume (20-Day)',
    category: 'Price & Returns',
    shortDesc: 'Average daily shares traded over the past 20 trading days',
    definition: 'The 20-day average volume establishes the baseline trading activity for a stock. Comparing current volume to 20-day average volume reveals unusual activity — a signal of institutional buying, news events, or emerging breakouts.',
    formula: 'Avg Volume 20D = Sum of daily volumes over 20 days ÷ 20',
    interpretation: 'Volume > 2× average: unusual activity (breakout/news signal). Volume < 0.5× average: unusually quiet (holidays, indecision). Volume ratio is used in Volume Breakout scans.',
    usedIn: ['Screener', 'Company Detail', 'Volume Breakout Scan', 'Movers Widget'],
    tags: ['volume', 'average', 'breakout'],
  },

  // ── QUALITY SCORES ─────────────────────────────────────────────────────────
  {
    id: 'composite_score',
    name: 'Composite Score',
    category: 'Quality Scores',
    shortDesc: 'Equal-weighted average of all 5 factor scores (0–100)',
    definition: 'The Composite Score is our proprietary overall ranking score. It equally weights the 5 factor scores: Momentum, Quality, Value, Income, and Growth. Each factor is a percentile rank (0–100) within the ASX universe. A score of 80 means the stock ranks in the top 20% on the combined factor model.',
    formula: 'Composite Score = (Momentum + Quality + Value + Income + Growth) ÷ 5\n(Each factor = average percentile rank of its component signals, 0–100)',
    interpretation: 'Scores above 70 are high-quality. Scores above 80 are in the top tier of the ASX. Used by the Top 5 Strategy to select monthly picks. A balanced high score across all 5 factors identifies the strongest all-round opportunities.',
    benchmark: 'Below 40: below average. 40–60: average. 60–70: good. 70–80: excellent. 80+: top tier',
    usedIn: ['Screener', 'Company Detail', 'Top 5 Strategy'],
    tags: ['composite', 'score', 'ranking', 'factor model'],
  },
  {
    id: 'momentum_score',
    name: 'Momentum Score',
    category: 'Quality Scores',
    shortDesc: 'Percentile rank on price momentum signals (0–100)',
    definition: 'The Momentum Score percentile-ranks each stock against all ASX stocks on 5 momentum signals: 1-month return, 3-month return, 6-month return, RSI-14, and ADX-14. A score of 90 means this stock has stronger momentum than 90% of the ASX.',
    formula: 'Momentum Score = Average percentile rank of: return_1m, return_3m, return_6m, rsi_14, adx_14',
    usedIn: ['Screener', 'Company Detail', 'Composite Score', 'Top 5 Strategy'],
    tags: ['momentum', 'score', 'factor'],
  },
  {
    id: 'quality_score',
    name: 'Quality Score',
    category: 'Quality Scores',
    shortDesc: 'Percentile rank on financial quality signals (0–100)',
    definition: 'The Quality Score ranks stocks on 6 financial quality signals: Piotroski F-Score, ROE, ROCE, Altman Z-Score, Debt/Equity (inverse), and Net Margin. It identifies fundamentally sound businesses with strong balance sheets and profitable operations.',
    formula: 'Quality Score = Average percentile rank of: piotroski_f_score, roe, roce, altman_z_score, 1/debt_to_equity, net_margin',
    usedIn: ['Screener', 'Company Detail', 'Composite Score', 'Quality Scans', 'Top 5 Strategy'],
    tags: ['quality', 'score', 'factor'],
  },
  {
    id: 'value_score',
    name: 'Value Score',
    category: 'Quality Scores',
    shortDesc: 'Percentile rank on valuation metrics — cheaper = higher score (0–100)',
    definition: 'The Value Score ranks stocks on 5 valuation metrics where lower multiples = better value: P/E ratio, P/B ratio, EV/EBITDA, P/S ratio, and FCF yield (higher is better). A Value Score of 80 means the stock is cheaper than 80% of the ASX on a combined valuation basis.',
    formula: 'Value Score = Average percentile rank of: 1/pe_ratio, 1/price_to_book, 1/ev_to_ebitda, fcf_yield, 1/price_to_sales',
    usedIn: ['Screener', 'Company Detail', 'Composite Score', 'Value Scans', 'Top 5 Strategy'],
    tags: ['value', 'score', 'factor', 'valuation'],
  },
  {
    id: 'income_score',
    name: 'Income Score',
    category: 'Quality Scores',
    shortDesc: 'Percentile rank on income/dividend quality signals (0–100)',
    definition: 'The Income Score ranks stocks on 5 dividend quality signals: grossed-up yield, dividend yield, franking percentage, consecutive dividend years, and dividend CAGR. It also penalises unsustainable payout ratios. Critical for ASX income investors.',
    formula: 'Income Score = Average percentile rank of: grossed_up_yield, dividend_yield, franking_pct, dividend_consecutive_yrs, dividend_cagr_3y, 1/payout_ratio',
    usedIn: ['Screener', 'Company Detail', 'Composite Score', 'Dividend Scans', 'Top 5 Strategy'],
    tags: ['income', 'dividends', 'score', 'factor'],
  },
  {
    id: 'growth_score',
    name: 'Growth Score',
    category: 'Quality Scores',
    shortDesc: 'Percentile rank on growth signals (0–100)',
    definition: 'The Growth Score ranks stocks on 6 growth signals: revenue growth 1Y, earnings growth 1Y, EPS CAGR 3Y, revenue growth HoH (half-yearly), EPS growth HoH, and revenue CAGR 5Y. Higher-growing companies score higher.',
    formula: 'Growth Score = Average percentile rank of: revenue_growth_1y, earnings_growth_1y, eps_growth_3y_cagr, revenue_growth_hoh, eps_growth_hoh, revenue_cagr_5y',
    usedIn: ['Screener', 'Company Detail', 'Composite Score', 'Growth Scans', 'Top 5 Strategy'],
    tags: ['growth', 'score', 'factor'],
  },
  {
    id: 'short_pct',
    name: 'Short Interest %',
    category: 'Quality Scores',
    shortDesc: 'Percentage of shares sold short as a fraction of float',
    definition: 'Short interest measures how many shares are sold short relative to total float. High short interest means many investors are betting the stock will fall. Data sourced from ASIC\'s daily short position reports — unique to the ASX Screener.',
    formula: 'Short % = Shares Sold Short ÷ Total Float × 100',
    interpretation: 'High short interest (above 5%) can signal negative sentiment but also creates potential for a "short squeeze" if news is better than expected. Low short interest is generally positive. Compare against sector averages.',
    benchmark: 'Low: <2%. Moderate: 2–5%. High: 5–10%. Very high: >10% (significant bearish bet)',
    usedIn: ['Screener', 'Company Detail', 'Market Overview', 'Movers Widget'],
    tags: ['short selling', 'ASIC', 'sentiment', 'risk'],
  },
  {
    id: 'percent_insiders',
    name: 'Insider Holding %',
    category: 'Quality Scores',
    shortDesc: 'Percentage of shares held by directors and key management',
    definition: 'Insider holding measures what percentage of shares is owned by directors, executives, and major related parties. High insider ownership aligns management incentives with shareholders — skin in the game.',
    formula: 'Insider % = Insider Shares ÷ Total Shares × 100',
    interpretation: 'Significant insider ownership (15%+) is generally positive — management has meaningful personal financial exposure. Very high (60%+) can indicate illiquidity risk. Insider buying (purchasing in open market) is a stronger signal than simply owning founding shares.',
    benchmark: 'Low: <5%. Moderate: 5–20%. High: 20–50%. Very high: >50%',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['insider', 'management', 'ownership'],
  },

  // ── ADDITIONAL ALLOWED_FIELDS METRICS ──────────────────────────────────────

  // Profitability extras
  {
    id: 'asset_turnover',
    name: 'Asset Turnover',
    category: 'Profitability',
    shortDesc: 'Revenue generated per dollar of total assets',
    definition: 'Asset turnover measures how efficiently a company uses its total assets to generate revenue. A higher ratio means the company generates more revenue per dollar of assets deployed.',
    formula: 'Asset Turnover = Annual Revenue ÷ Average Total Assets',
    interpretation: 'Higher is better. Asset-light businesses (software, services) have high asset turnover. Capital-intensive businesses (miners, utilities) have low turnover. Compare within the same industry only.',
    benchmark: 'Retail: 1.5–2.5×. Manufacturing: 0.5–1.5×. Utilities: 0.2–0.5×. Software: 0.5–1.0×',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['efficiency', 'assets', 'turnover'],
  },
  {
    id: 'inventory_turnover',
    name: 'Inventory Turnover',
    category: 'Profitability',
    shortDesc: 'How many times inventory is sold and replaced per year',
    definition: 'Inventory turnover measures how efficiently a company manages its stock. It shows how many times inventory is completely sold and replenished in a year. Slow turnover ties up cash; fast turnover indicates strong demand.',
    formula: 'Inventory Turnover = Cost of Goods Sold ÷ Average Inventory',
    interpretation: 'Higher is generally better — fast-moving inventory means less capital tied up. Very low turnover can signal obsolete stock or weak demand. Context-dependent: supermarkets turn inventory daily; equipment manufacturers may turn it quarterly.',
    benchmark: 'Retail/FMCG: 8–15×. Manufacturing: 4–8×. Heavy industry: 2–4×',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['efficiency', 'inventory', 'working capital'],
  },
  {
    id: 'avg_roe_3y',
    name: 'Average ROE (3 Year)',
    category: 'Profitability',
    shortDesc: 'ROE averaged over the past 3 years — smooths out single-year spikes',
    definition: '3-year average ROE smooths out one-time gains, write-offs, or cyclical swings that can distort a single year. It is a more reliable indicator of sustainable capital efficiency than trailing 12-month ROE.',
    formula: 'Avg ROE 3Y = (ROE Year 1 + ROE Year 2 + ROE Year 3) ÷ 3',
    interpretation: 'Consistently high Avg ROE (15%+) over 3 years is a strong signal of durable competitive advantage. A falling average suggests deteriorating returns. Compare against the single-year ROE to spot mean reversion.',
    benchmark: 'Below 10%: weak. 10–15%: adequate. 15–20%: good. Above 20%: excellent compounder',
    example: 'ROE of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail', 'Quality Scans'],
    tags: ['ROE', 'average', '3-year', 'quality'],
  },

  // Growth extras
  {
    id: 'revenue_growth_3y_cagr',
    name: 'Revenue CAGR (3 Year)',
    category: 'Growth',
    shortDesc: 'Compound annual revenue growth over the past 3 years',
    definition: '3-year revenue CAGR captures medium-term growth durability, smoothing single-year volatility while remaining sensitive to more recent trends than a 5-year figure.',
    formula: 'Revenue CAGR 3Y = (Current Revenue ÷ Revenue 3 years ago)^(1/3) − 1',
    interpretation: 'A business growing revenue at 10%+ CAGR for 3 years is demonstrating momentum. Useful alongside 1-year and 5-year CAGRs to spot acceleration or deceleration in the growth trajectory.',
    benchmark: 'Below 3%: stagnant. 3–8%: steady. 8–15%: strong. 15%+: high growth',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Growth Factor)'],
    tags: ['revenue', 'CAGR', '3-year', 'growth'],
  },
  {
    id: 'earnings_growth_3y_cagr',
    name: 'Earnings CAGR (3 Year)',
    category: 'Growth',
    shortDesc: 'Compound annual net profit growth over the past 3 years',
    definition: '3-year earnings CAGR shows whether a company has been consistently growing its bottom-line profit, not just revenue. Earnings growth above revenue growth indicates improving margins.',
    formula: 'Earnings CAGR 3Y = (Current NPAT ÷ NPAT 3 years ago)^(1/3) − 1',
    interpretation: 'Sustained earnings CAGR above 10–15% is a hallmark of quality compounders. Rising earnings CAGR alongside rising revenue CAGR is ideal — both the top and bottom lines growing together.',
    benchmark: 'Below 5%: weak. 5–10%: adequate. 10–15%: good. 15%+: strong',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Growth Factor)'],
    tags: ['earnings', 'CAGR', '3-year', 'growth'],
  },
  {
    id: 'eps_cagr_5y',
    name: 'EPS CAGR (5 Year)',
    category: 'Growth',
    shortDesc: 'Compound annual earnings per share growth over 5 years',
    definition: '5-year EPS CAGR provides the longest standard view of per-share earnings compounding, covering a full business cycle. It distinguishes genuine compounders from companies benefiting from short-term tailwinds.',
    formula: 'EPS CAGR 5Y = (Current EPS ÷ EPS 5 years ago)^(1/5) − 1',
    interpretation: 'A 5-year EPS CAGR above 10% sustained through a full cycle is exceptional. Ensure growth is not driven by share buybacks alone — revenue growth should underpin it.',
    benchmark: 'Below 3%: stagnant. 3–8%: adequate. 8–12%: good. 12%+: excellent compounder',
    usedIn: ['Screener', 'Company Detail', 'Composite Score (Growth Factor)'],
    tags: ['EPS', 'CAGR', '5-year', 'growth'],
  },
  {
    id: 'net_income_growth_hoh',
    name: 'Net Income Growth (Half-on-Half) ★',
    category: 'Growth',
    shortDesc: 'Net profit change from H1 to H2 — ASX half-yearly reporting',
    definition: 'ASX-specific metric. Compares the most recent half-year net profit to the prior half-year. Catches earnings inflection points faster than annual comparisons — useful for identifying companies where profitability is accelerating or deteriorating mid-cycle.',
    formula: 'HoH Net Income Growth = (Latest Half NPAT − Prior Half NPAT) ÷ |Prior Half NPAT| × 100',
    interpretation: 'Accelerating HoH net income growth alongside stable or rising HoH revenue signals improving margins. Declining HoH net income even with rising revenue signals cost pressure or margin compression.',
    usedIn: ['Screener', 'Company Detail', 'Growth Scans (Half-Yearly Acceleration)', 'Composite Score (Growth Factor)'],
    tags: ['net income', 'half-yearly', 'ASX', 'growth'],
  },
  {
    id: 'eps_growth_hoh',
    name: 'EPS Growth (Half-on-Half) ★',
    category: 'Growth',
    shortDesc: 'EPS change from H1 to H2 — ASX half-yearly reporting',
    definition: 'ASX-specific metric. Compares EPS from the most recent half-year to the prior half-year. Unlike HoH revenue or net income, EPS growth also captures the effect of share issuance or buybacks on per-share value.',
    formula: 'HoH EPS Growth = (Latest Half EPS − Prior Half EPS) ÷ |Prior Half EPS| × 100',
    interpretation: 'Positive HoH EPS growth with stable or declining share count is the strongest signal. EPS growing faster than net income indicates buybacks are adding per-share value.',
    usedIn: ['Screener', 'Company Detail', 'Growth Scans (Half-Yearly Acceleration)', 'Composite Score (Growth Factor)'],
    tags: ['EPS', 'half-yearly', 'ASX', 'growth'],
  },
  {
    id: 'revenue_growth_yoy_q',
    name: 'Revenue Growth (Quarterly YoY)',
    category: 'Growth',
    shortDesc: 'Revenue growth vs same quarter prior year — most current signal',
    definition: 'Compares revenue in the latest reported quarter to the same quarter 12 months ago (year-on-year). The most timely fundamental growth signal available, especially for companies reporting quarterly (miners, large caps).',
    formula: 'Quarterly YoY Growth = (Latest Q Revenue − Same Q Prior Year Revenue) ÷ Same Q Prior Year Revenue × 100',
    interpretation: 'Accelerating quarterly YoY growth is a leading indicator of improving annual results. Decelerating quarterly growth is often an early warning sign before annual figures reflect it.',
    usedIn: ['Screener', 'Company Detail', 'Growth Scans'],
    tags: ['revenue', 'quarterly', 'YoY', 'growth'],
  },

  // Financial Health extras
  {
    id: 'total_debt',
    name: 'Total Debt',
    category: 'Financial Health',
    shortDesc: 'Total interest-bearing borrowings (short-term + long-term)',
    definition: 'Total debt is all interest-bearing financial liabilities — bank loans, bonds, lease liabilities, and any other borrowings. It excludes trade payables and other operational liabilities. Used to assess absolute debt burden.',
    formula: 'Total Debt = Short-term Debt + Long-term Debt + Lease Liabilities',
    interpretation: 'Total debt in isolation is less meaningful than debt ratios (D/E, Debt/EBITDA). The key question is whether earnings and cash flows can comfortably service and repay the debt. Rising total debt with flat or falling earnings is a warning sign.',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['debt', 'borrowings', 'leverage', 'balance sheet'],
  },
  {
    id: 'cfo_fy0',
    name: 'Operating Cash Flow (CFO)',
    category: 'Financial Health',
    shortDesc: 'Cash generated from core business operations before investing and financing',
    definition: 'Operating cash flow (CFO) is the cash generated by a company\'s core business activities — collected from customers, after paying suppliers and employees, before capital expenditure. It is the lifeblood of a business and harder to manipulate than reported earnings.',
    formula: 'CFO = Net Income + Depreciation & Amortisation ± Changes in Working Capital',
    interpretation: 'CFO consistently above net income indicates high earnings quality — earnings are backed by real cash. CFO significantly below net income may signal aggressive accounting or working capital deterioration. Negative CFO requires cash from debt or equity to survive.',
    benchmark: 'CFO/Net Income ratio above 1.0×: high earnings quality. Below 0.7×: investigate accounting',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab', 'Quality Scans'],
    tags: ['cash flow', 'CFO', 'operations', 'earnings quality'],
  },
  {
    id: 'debt_to_ebitda',
    name: 'Debt/EBITDA',
    category: 'Financial Health',
    shortDesc: 'Years of EBITDA needed to repay total debt',
    definition: 'Debt/EBITDA shows how many years of operating earnings (before interest, tax, depreciation) are needed to retire all debt. It is the most widely used leverage ratio in credit analysis and M&A — directly comparable across industries as it is capital-structure neutral.',
    formula: 'Debt/EBITDA = Total Debt ÷ EBITDA',
    interpretation: 'Below 1×: very low leverage. 1–2×: comfortable. 2–3×: moderate. 3–4×: elevated. Above 4×: high — potential refinancing risk if earnings deteriorate. Lenders typically set covenant thresholds at 3–4×.',
    benchmark: 'Low risk: <2×. Moderate: 2–3×. Elevated: 3–4×. High risk: >4×',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['debt', 'EBITDA', 'leverage', 'credit'],
  },
  {
    id: 'net_debt_to_ebitda',
    name: 'Net Debt/EBITDA',
    category: 'Financial Health',
    shortDesc: 'Net leverage — years of EBITDA to repay net debt (debt minus cash)',
    definition: 'More conservative than Debt/EBITDA, this ratio uses net debt (debt minus cash). A company holding significant cash relative to debt may appear highly leveraged on Debt/EBITDA but neutral on Net Debt/EBITDA. The preferred leverage metric for credit rating analysis.',
    formula: 'Net Debt/EBITDA = (Total Debt − Cash & Equivalents) ÷ EBITDA',
    interpretation: 'Negative = net cash position (more cash than debt). 0–1×: very low net leverage. 1–2.5×: moderate. 2.5–4×: elevated. Above 4×: potentially distressed unless cash flows are very predictable.',
    benchmark: 'Negative: net cash. 0–1×: low. 1–2.5×: moderate. 2.5–4×: elevated. >4×: high risk',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['net debt', 'EBITDA', 'leverage', 'credit'],
  },
  {
    id: 'cash_conversion_cycle',
    name: 'Cash Conversion Cycle (CCC)',
    category: 'Financial Health',
    shortDesc: 'Days taken to convert inventory and receivables into cash',
    definition: 'The Cash Conversion Cycle measures working capital efficiency — how many days elapse between paying for raw materials and receiving cash from customers. A shorter CCC means the business converts inventory and sales into cash faster, requiring less working capital.',
    formula: 'CCC = Days Inventory Outstanding + Days Sales Outstanding − Days Payable Outstanding',
    interpretation: 'Shorter CCC is better. Negative CCC (e.g., supermarkets) means the business collects cash from customers before paying suppliers — extremely efficient. A rising CCC signals working capital stress: slowing collections or accumulating inventory.',
    benchmark: 'Negative: exceptional (Coles, Woolworths model). 0–30 days: excellent. 30–60 days: good. 60–90 days: moderate. >90 days: watch carefully',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['working capital', 'efficiency', 'cash', 'CCC'],
  },

  // Returns extras
  {
    id: 'return_3y',
    name: 'Return (3 Year)',
    category: 'Price & Returns',
    shortDesc: 'Cumulative price return over the past 3 years',
    definition: '3-year total return captures performance through a meaningful portion of the business cycle. Used for medium-term performance attribution and comparison against benchmark indices.',
    formula: 'Return 3Y = (Current Price − Price 3 years ago) ÷ Price 3 years ago × 100',
    interpretation: 'A 3-year return above the ASX200 total return indicates outperformance. Stocks with strong 3-year returns often have improving fundamentals — not just short-term momentum.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['return', '3-year', 'performance'],
  },
  {
    id: 'return_5y',
    name: 'Return (5 Year)',
    category: 'Price & Returns',
    shortDesc: 'Cumulative price return over the past 5 years',
    definition: '5-year return spans a full business cycle for most industries and is the standard horizon for long-term performance evaluation. It separates genuine compounders from cyclical or momentum-driven stories.',
    formula: 'Return 5Y = (Current Price − Price 5 years ago) ÷ Price 5 years ago × 100',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['return', '5-year', 'long-term', 'performance'],
  },
  {
    id: 'return_10y',
    name: 'Return (10 Year)',
    category: 'Price & Returns',
    shortDesc: 'Cumulative price return over the past 10 years',
    definition: '10-year return is the ultimate test of a long-term compounder. It includes at least one full market cycle (bear + bull), separating truly exceptional businesses from lucky shorter-term performers.',
    formula: 'Return 10Y = (Current Price − Price 10 years ago) ÷ Price 10 years ago × 100',
    interpretation: 'Very few stocks double the market over 10 years. A 10-year return above 300% (approximately 15% CAGR) represents exceptional long-term compounding. Compare against the XJO total return benchmark.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['return', '10-year', 'long-term', 'compounding'],
  },

  // Technical extras
  {
    id: 'sma_20',
    name: 'SMA-20 (20-Day Moving Average)',
    category: 'Technical Indicators',
    shortDesc: 'Average closing price over the past 20 trading days',
    definition: 'The 20-day simple moving average is the shortest standard moving average, primarily used by short-term traders. Price above SMA-20 signals short-term bullish momentum. It is highly sensitive to price changes and generates many signals.',
    formula: 'SMA-20 = Sum of last 20 closing prices ÷ 20',
    interpretation: 'Price above SMA-20: short-term bullish. Price below SMA-20: short-term bearish. Less reliable as a standalone signal than SMA-50 or SMA-200 but useful for timing entries within an established trend.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['moving average', 'SMA', 'short-term', 'technical'],
  },
  {
    id: 'volatility_60d',
    name: 'Volatility (60-Day)',
    category: 'Technical Indicators',
    shortDesc: 'Annualised standard deviation of daily returns over 60 trading days',
    definition: '60-day volatility uses a longer lookback than 20-day volatility, capturing medium-term price stability. Less reactive to short-term spikes, it provides a more stable estimate of a stock\'s inherent risk level.',
    formula: 'Vol 60D = StdDev(daily returns over 60 days) × √252 × 100',
    interpretation: 'Compare against 20-day volatility: if 60D > 20D, recent period has been unusually calm. If 20D > 60D, recent period has been more volatile than normal. Rising volatility often precedes or accompanies major price moves.',
    benchmark: 'Large caps: 15–25%. Mid caps: 25–40%. Small caps: 40–80%+',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['volatility', 'risk', '60-day', 'standard deviation'],
  },
  {
    id: 'sharpe_3y',
    name: 'Sharpe Ratio (3 Year)',
    category: 'Technical Indicators',
    shortDesc: 'Risk-adjusted return over 3 years — more stable than 1-year Sharpe',
    definition: 'The 3-year Sharpe ratio measures risk-adjusted performance over a longer period than the 1-year version. It is more statistically reliable and less affected by short-term market conditions. Preferred by institutional investors for evaluating consistent risk management.',
    formula: 'Sharpe 3Y = (3Y Annualised Return − Risk-Free Rate) ÷ 3Y Annualised Volatility',
    interpretation: 'The same scale as 1-year Sharpe applies. A 3-year Sharpe above 1.0 sustained over a full cycle demonstrates genuine risk-adjusted outperformance, not just good luck in a bull market.',
    benchmark: '<0: poor. 0–0.5: below average. 0.5–1.0: adequate. 1.0–2.0: good. >2.0: excellent',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['Sharpe', 'risk-adjusted', '3-year', 'return'],
  },
  {
    id: 'sortino_1y',
    name: 'Sortino Ratio (1 Year)',
    category: 'Technical Indicators',
    shortDesc: 'Risk-adjusted return measuring only downside volatility',
    definition: 'The Sortino ratio is a refinement of the Sharpe ratio — it only penalises downside volatility (harmful to investors), not upside volatility (beneficial). A stock that has strong gains with minimal drawdowns scores well on Sortino even if total volatility is high.',
    formula: 'Sortino = (Return − Risk-Free Rate) ÷ Downside Deviation\nDownside Deviation = StdDev of negative returns only',
    interpretation: 'Higher is better. Sortino > Sharpe indicates most volatility is upside. Sortino significantly below Sharpe indicates the stock has frequent or severe drawdowns relative to its gains.',
    benchmark: '<0: poor. 0–1.0: adequate. 1.0–2.0: good. >2.0: excellent downside management',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['Sortino', 'downside risk', 'risk-adjusted', 'return'],
  },
  {
    id: 'beta_3y',
    name: 'Beta (3 Year)',
    category: 'Technical Indicators',
    shortDesc: 'Market sensitivity over 3 years — more stable than 1-year beta',
    definition: '3-year beta uses a longer regression window, producing a more stable and reliable measure of a stock\'s systematic risk versus the ASX200. Preferred over 1-year beta for portfolio construction as it is less affected by recent market dislocations.',
    formula: 'Beta 3Y = Covariance(Stock 3Y Returns, Market 3Y Returns) ÷ Variance(Market 3Y Returns)',
    interpretation: 'Same interpretation as 1-year beta but more reliable: Beta < 1 = defensive, Beta > 1 = aggressive. A stock with consistently low 3-year beta across multiple periods is genuinely defensive.',
    benchmark: 'Defensive: <0.7. Market-like: 0.7–1.3. Aggressive: 1.3–2.0. Highly speculative: >2.0',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['beta', '3-year', 'market sensitivity', 'risk'],
  },
  {
    id: 'max_drawdown_1y',
    name: 'Max Drawdown (1 Year)',
    category: 'Technical Indicators',
    shortDesc: 'Largest peak-to-trough price decline over the past 12 months',
    definition: 'Maximum drawdown measures the largest peak-to-trough decline in price over the past year. It captures the worst-case loss an investor would have experienced if they bought at the peak and sold at the trough.',
    formula: 'Max Drawdown = (Trough Value − Peak Value) ÷ Peak Value × 100 (negative number)',
    interpretation: 'Smaller (less negative) is better. A max drawdown of −10% is very low. −20% to −30% is significant. Below −40% is severe. Stocks with low max drawdown combined with strong returns are the most desirable on a risk-adjusted basis.',
    benchmark: 'Excellent: > −10%. Good: −10% to −20%. Moderate: −20% to −35%. Poor: < −35%',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['drawdown', 'risk', 'downside', 'peak-to-trough'],
  },
  {
    id: 'relative_strength_xjo',
    name: 'Relative Strength vs XJO',
    category: 'Technical Indicators',
    shortDesc: 'Stock return minus ASX200 (XJO) return — alpha vs benchmark',
    definition: 'Relative strength compares a stock\'s price return against the ASX200 (XJO) benchmark. A positive figure means the stock has outperformed the index; negative means it has lagged. It is the simplest measure of stock-specific alpha.',
    formula: 'Relative Strength XJO = Stock Return (period) − ASX200 Return (same period)',
    interpretation: 'Positive: outperforming the market. Negative: underperforming. A stock consistently showing positive relative strength across multiple time periods is demonstrating sustainable competitive advantage or sector tailwinds.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['relative strength', 'XJO', 'alpha', 'benchmark', 'outperformance'],
  },

  // Quality extras
  {
    id: 'percent_institutions',
    name: 'Institutional Holding %',
    category: 'Quality Scores',
    shortDesc: 'Percentage of shares held by institutional investors (funds, super, etc.)',
    definition: 'Institutional holding measures what proportion of a company\'s shares is owned by fund managers, superannuation funds, ETFs, insurance companies, and other professional investors. High institutional ownership signals that the stock meets the governance and liquidity requirements of large professional investors.',
    formula: 'Institutional % = Institutional Shares ÷ Total Shares × 100',
    interpretation: 'High institutional ownership (40%+) typically means better analyst coverage, stronger governance scrutiny, and more liquid trading. Very high (80%+) can amplify selling pressure during downturns as institutions rebalance simultaneously. Very low institutional ownership may signal illiquidity or governance concerns.',
    benchmark: 'Low: <15%. Moderate: 15–40%. High: 40–70%. Very high: >70%',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['institutional', 'ownership', 'funds', 'governance'],
  },
  {
    id: 'beneish_m_score',
    name: 'Beneish M-Score',
    category: 'Quality Scores',
    shortDesc: 'Statistical model detecting probability of earnings manipulation',
    definition: 'Developed by Professor Messod Beneish, the M-Score uses 8 financial ratios to detect potential earnings manipulation. It became famous for identifying Enron as a likely manipulator before its collapse. Higher (less negative) scores indicate higher manipulation probability.',
    formula: 'M = −4.84 + 0.92×DSRI + 0.528×GMI + 0.404×AQI + 0.892×SGI + 0.115×DEPI − 0.172×SGAI + 4.679×TATA − 0.327×LVGI\n(8 accounting ratios measuring receivables, margins, assets, growth, depreciation, expenses, accruals, leverage)',
    interpretation: 'M-Score below −2.22: likely not manipulating. M-Score above −1.78: high probability of manipulation. Between −2.22 and −1.78: grey zone. Use as a red flag indicator alongside other quality checks, not a definitive verdict.',
    benchmark: 'Below −2.22: low risk. −2.22 to −1.78: caution. Above −1.78: high manipulation risk',
    usedIn: ['Screener', 'Company Detail', 'Quality Scans'],
    tags: ['Beneish', 'manipulation', 'earnings quality', 'forensic accounting'],
  },

  // ASX-Specific
  {
    id: 'nta_per_share',
    name: 'NTA Per Share (Net Tangible Assets)',
    category: 'ASX-Specific',
    shortDesc: 'Per-share value of tangible assets after all liabilities (excl. intangibles)',
    definition: 'NTA per share is the book value per share excluding goodwill and intangible assets. It represents the hard asset backing per share. Particularly important for Listed Investment Companies (LICs), REITs, and property trusts where asset values are central to valuation.',
    formula: 'NTA Per Share = (Total Assets − Intangible Assets − Goodwill − Total Liabilities) ÷ Shares Outstanding',
    interpretation: 'For LICs and REITs, buying below NTA = buying assets at a discount. Buying above NTA = paying a premium for management or growth expectations. A persistent NTA discount can be a value opportunity or signal of poor management.',
    example: 'Nta of $250M ÷ 500M shares outstanding = $0.50 per share.',
    usedIn: ['Screener', 'Company Detail', 'LIC/REIT Scans'],
    tags: ['NTA', 'tangible assets', 'LIC', 'REIT', 'valuation'],
  },
  {
    id: 'nta_discount_premium',
    name: 'NTA Discount / Premium %',
    category: 'ASX-Specific',
    shortDesc: 'How much the share price differs from NTA per share (+ = premium, − = discount)',
    definition: 'Expresses the difference between share price and NTA as a percentage. A discount means shares trade below asset backing — potentially a value opportunity. A premium means the market values management or growth prospects above the underlying assets.',
    formula: 'NTA Discount/Premium = (Share Price − NTA Per Share) ÷ NTA Per Share × 100',
    interpretation: 'For LICs: historical average discount/premium is a useful reference point. Buying a quality LIC at a wider-than-average discount can generate alpha when the discount narrows. Persistent discounts may signal poor capital allocation by management.',
    benchmark: 'Discount > 10%: potential value. Discount 0–10%: fair. Premium 0–10%: normal for quality. Premium >15%: expensive',
    usedIn: ['Screener', 'Company Detail', 'LIC Scans'],
    tags: ['NTA', 'discount', 'premium', 'LIC', 'REIT'],
  },
  {
    id: 'gearing_ratio',
    name: 'Gearing Ratio',
    category: 'ASX-Specific',
    shortDesc: 'Debt as a percentage of total capital (debt + equity)',
    definition: 'Gearing ratio expresses total debt as a proportion of total capital (debt + equity). Preferred over Debt/Equity for REITs and property companies where leverage limits are regulated or sector-standard. A gearing ratio of 30% means 30 cents of every dollar of capital is funded by debt.',
    formula: 'Gearing Ratio = Total Debt ÷ (Total Debt + Total Equity) × 100',
    interpretation: 'Low gearing: <20%. Moderate: 20–40%. High: 40–60%. Very high: >60%. ASX REITs typically target 25–40% gearing. Many REIT trust deeds have covenants capping gearing at 50–60%.',
    benchmark: 'Defensive: <20%. Normal: 20–40%. High (REITs): 35–50%. Danger: >60%',
    usedIn: ['Screener', 'Company Detail', 'REIT Scans'],
    tags: ['gearing', 'leverage', 'debt', 'REIT', 'property'],
  },
  {
    id: 'wale_years',
    name: 'WALE (Weighted Average Lease Expiry)',
    category: 'ASX-Specific',
    shortDesc: 'Average remaining lease term weighted by income — key REIT metric',
    definition: 'WALE measures the average time remaining on a property portfolio\'s leases, weighted by income contribution. A longer WALE means more income is locked in under existing leases — lower near-term vacancy and re-leasing risk. Critical for evaluating ASX REITs and property trusts.',
    formula: 'WALE = Σ (Lease Remaining Years × Annual Rent from that Lease) ÷ Total Annual Rent',
    interpretation: 'Longer WALE = more income certainty. Short WALE (< 3 years) means significant leases are expiring soon — re-leasing risk, especially if market rents are falling. WALE above 5 years is generally considered secure for commercial property.',
    benchmark: 'Short: <3 years (high risk). Moderate: 3–5 years. Good: 5–8 years. Long: >8 years (very secure)',
    usedIn: ['Screener', 'Company Detail', 'REIT Scans'],
    tags: ['WALE', 'lease', 'REIT', 'property', 'income security'],
  },
  {
    id: 'management_expense_ratio',
    name: 'MER (Management Expense Ratio)',
    category: 'ASX-Specific',
    shortDesc: 'Annual fee charged by an ETF or managed fund as % of assets',
    definition: 'The Management Expense Ratio is the annual cost of owning an ETF or managed fund, expressed as a percentage of assets under management. It is automatically deducted from fund returns — a 0.10% MER means 10 cents per $100 invested is paid annually in fees.',
    formula: 'MER = Total Annual Fund Costs ÷ Average Assets Under Management × 100',
    interpretation: 'Lower is better for passive funds. Index ETFs should have MER below 0.20%. Active funds typically charge 0.50–1.50%. High MER is only justified by genuine, consistent outperformance after fees — which most active managers fail to deliver long-term.',
    benchmark: 'Passive ETFs: 0.03–0.20%. Smart beta: 0.20–0.50%. Active funds: 0.50–1.50%. High-fee: >1.50%',
    usedIn: ['Screener', 'Company Detail', 'ETF & Funds Section'],
    tags: ['MER', 'ETF', 'fund', 'fees', 'cost'],
  },
  {
    id: 'aisc_per_oz',
    name: 'AISC Per Ounce (All-In Sustaining Cost)',
    category: 'ASX-Specific',
    shortDesc: 'Total cost to produce one ounce of gold including sustaining capex',
    definition: 'AISC is the industry-standard cost metric for gold (and silver) miners. It includes all direct and indirect costs of producing gold: mining costs, processing, royalties, sustaining capital expenditure, and corporate overhead. Developed by the World Gold Council for comparability.',
    formula: 'AISC = (Operating Costs + Royalties + Sustaining CapEx + Corporate Costs) ÷ Ounces Produced',
    interpretation: 'The margin between gold price and AISC determines profitability. AISC below USD $1,200/oz = very low cost. USD $1,200–$1,600/oz = average. Above USD $1,800/oz = high cost, marginal at current gold prices. Lower AISC = more resilient to gold price falls.',
    benchmark: 'Tier 1 (low cost): <USD $1,200/oz. Average: USD $1,200–1,600/oz. High cost: >USD $1,600/oz',
    usedIn: ['Screener', 'Company Detail', 'Miner Scans'],
    tags: ['AISC', 'gold', 'mining', 'cost', 'margin'],
  },

  // ── VALUATION (ADDITIONAL) ────────────────────────────────────────────────
  {
    id: 'enterprise_value',
    name: 'Enterprise Value (EV)',
    category: 'Valuation',
    shortDesc: 'Total value of a company to all capital providers',
    definition: 'Enterprise Value is the total theoretical acquisition price of a business — what you would pay to own it outright. It combines market cap with net debt, giving a capital-structure-neutral measure of size and value.',
    formula: 'EV = Market Cap + Total Debt − Cash & Equivalents',
    interpretation: 'EV is the denominator in EV/EBITDA and EV/Revenue multiples. A company with high debt has a much higher EV than market cap, making it appear more expensive on EV multiples — correctly so, as an acquirer inherits the debt.',
    benchmark: 'Use EV relative to EBITDA, EBIT, or Revenue rather than in isolation',
    usedIn: ['Screener', 'Company Detail', 'Valuation Tab'],
    tags: ['enterprise value', 'market cap', 'debt', 'valuation'],
  },
  {
    id: 'ev_to_revenue',
    name: 'EV/Revenue',
    category: 'Valuation',
    shortDesc: 'Enterprise value relative to annual revenue',
    definition: 'EV/Revenue divides Enterprise Value by total revenue. Unlike P/S, it accounts for debt — making it more useful for comparing companies with different capital structures. Common for early-stage, high-growth businesses without positive EBITDA.',
    formula: 'EV/Revenue = (Market Cap + Net Debt) ÷ Annual Revenue',
    interpretation: 'Lower EV/Revenue = cheaper. Useful when EBITDA is negative. SaaS companies often trade at 8–20× EV/Revenue; traditional businesses at 0.5–2×. Compare within sectors only.',
    benchmark: 'Software/SaaS: 5–20×. Industrials: 0.5–2×. Retail: 0.2–0.5×',
    usedIn: ['Screener', 'Company Detail', 'Valuation Tab'],
    tags: ['EV', 'revenue', 'valuation', 'growth'],
  },
  {
    id: 'price_to_cash_flow',
    name: 'Price/Cash Flow (P/CF)',
    category: 'Valuation',
    shortDesc: 'Share price relative to operating cash flow per share',
    definition: 'Price/Cash Flow compares share price to operating cash flow per share. It is harder to manipulate than P/E (earnings can be managed with accruals; cash flow is more concrete) and useful for capital-intensive businesses with high depreciation.',
    formula: 'P/CF = Share Price ÷ Operating Cash Flow Per Share',
    interpretation: 'P/CF below 10 is generally considered cheap. More reliable than P/E for cyclicals and heavy industry. A company with low P/E but high P/CF may have poor cash conversion.',
    benchmark: 'Broad market: 10–20×. Value threshold: <10×. Capital-intensive (miners, utilities): 5–12×',
    usedIn: ['Screener', 'Company Detail', 'Valuation Tab'],
    tags: ['cash flow', 'valuation', 'operating cash flow'],
  },
  {
    id: 'market_cap',
    name: 'Market Capitalisation',
    category: 'Valuation',
    shortDesc: 'Total market value of all shares on issue',
    definition: 'Market capitalisation is the total value the stock market places on a company, calculated by multiplying the current share price by the total number of shares outstanding. It is the simplest measure of company size.',
    formula: 'Market Cap = Share Price × Total Shares Outstanding',
    interpretation: 'Market cap is used to classify companies by size: Micro-cap (<$50M), Small-cap ($50M–$500M), Mid-cap ($500M–$5B), Large-cap (>$5B), Mega-cap (>$50B on ASX). Larger companies are generally more liquid and lower-risk.',
    benchmark: 'ASX micro-cap: <$50M. Small-cap: $50M–$500M. Mid-cap: $500M–$5B. Large-cap: >$5B',
    usedIn: ['Screener', 'Company Detail', 'Size Filters'],
    tags: ['market cap', 'size', 'shares', 'valuation'],
  },

  // ── PROFITABILITY (ADDITIONAL) ────────────────────────────────────────────
  {
    id: 'ebitda',
    name: 'EBITDA',
    category: 'Profitability',
    shortDesc: 'Earnings before interest, tax, depreciation and amortisation',
    definition: 'EBITDA strips out the effects of financing (interest), accounting choices (depreciation/amortisation) and tax to give a proxy for operating cash generation. It is widely used for cross-company comparisons and is the denominator in EV/EBITDA.',
    formula: 'EBITDA = Revenue − COGS − Operating Expenses (before D&A)',
    interpretation: 'Positive EBITDA but negative net profit often means a company is operationally viable but weighed down by debt interest or large D&A. Compare EBITDA margin (EBITDA ÷ Revenue) across companies for efficiency.',
    benchmark: 'EBITDA margin: <15% low, 15–30% solid, >30% strong (varies heavily by sector)',
    usedIn: ['Screener', 'Company Detail', 'Valuation Tab'],
    tags: ['EBITDA', 'profitability', 'earnings', 'operating'],
  },
  {
    id: 'gross_profit',
    name: 'Gross Profit',
    category: 'Profitability',
    shortDesc: 'Revenue minus cost of goods sold (COGS)',
    definition: 'Gross profit is what remains after subtracting the direct costs of producing goods or services (COGS) from revenue. It represents the pool of money available to cover operating expenses, interest, tax, and generate net profit.',
    formula: 'Gross Profit = Revenue − Cost of Goods Sold',
    interpretation: 'High gross profit does not guarantee profitability — overhead and admin costs still need to be paid. Gross profit margin (Gross Profit ÷ Revenue) is a better comparator: >60% is typical for software/pharma, <30% for manufacturing.',
    usedIn: ['Screener', 'Company Detail', 'Profitability Tab'],
    tags: ['gross profit', 'revenue', 'COGS', 'profitability'],
  },
  {
    id: 'eps',
    name: 'Earnings Per Share (EPS)',
    category: 'Profitability',
    shortDesc: 'Net profit attributable to each ordinary share',
    definition: 'EPS divides net profit (after tax and minority interests) by the weighted average number of shares on issue. It is the most fundamental measure of per-share profitability and the primary driver of dividends and share price over time.',
    formula: 'EPS = Net Profit After Tax ÷ Weighted Average Shares Outstanding',
    interpretation: 'Rising EPS over time signals growing per-share value. Negative EPS means the company is loss-making. Diluted EPS (which includes options and convertibles) is more conservative than basic EPS. EPS growth rate is a key driver of P/E expansion or contraction.',
    benchmark: 'No absolute benchmark — compare EPS growth YoY and against sector peers',
    usedIn: ['Screener', 'Company Detail', 'Earnings Tab'],
    tags: ['EPS', 'earnings', 'profitability', 'per share'],
  },
  {
    id: 'net_income',
    name: 'Net Profit (NPAT)',
    category: 'Profitability',
    shortDesc: 'Bottom-line profit after all expenses and tax',
    definition: 'Net Profit After Tax (NPAT) is the final profit remaining after subtracting all operating costs, depreciation, interest expense, and income tax from revenue. It represents the earnings attributable to shareholders and is the basis for EPS and dividends.',
    formula: 'Net Profit = Revenue − COGS − Operating Expenses − D&A − Interest − Tax',
    interpretation: 'Consistent profitability over multiple years is the foundation of quality investing. One-off items (asset sales, write-downs) can distort single-year figures — look at 3–5 year trends. Negative NPAT is acceptable for early-stage growth companies if operating cash flow is positive.',
    usedIn: ['Screener', 'Company Detail', 'Earnings Tab'],
    tags: ['net profit', 'NPAT', 'earnings', 'profitability'],
  },
  {
    id: 'revenue',
    name: 'Revenue',
    category: 'Profitability',
    shortDesc: 'Total sales or income generated by the business',
    definition: 'Revenue (also called turnover or sales) is the total amount a company earns from its primary business activities before any expenses are deducted. It is the top line of the income statement and the starting point for all profitability analysis.',
    formula: 'Revenue = Units Sold × Average Selling Price (varies by business model)',
    interpretation: 'Revenue growth alone is insufficient — focus on whether revenue growth is translating into margin expansion. A company growing revenue 30% while margins compress is concerning. Consistent revenue and profit growth is the ideal profile.',
    usedIn: ['Screener', 'Company Detail', 'Growth Tab'],
    tags: ['revenue', 'sales', 'turnover', 'top line'],
  },
  {
    id: 'roic',
    name: 'ROIC (Return on Invested Capital)',
    category: 'Profitability',
    shortDesc: 'How efficiently a company generates profit from its invested capital',
    definition: 'ROIC measures the return generated on all capital invested in the business — both equity and debt. It is considered one of the best single indicators of business quality. Companies consistently earning ROIC above their cost of capital create shareholder value.',
    formula: 'ROIC = NOPAT ÷ (Total Equity + Net Debt)',
    interpretation: 'ROIC above 15% sustained over 5+ years indicates a high-quality business with a genuine competitive advantage. ROIC below WACC means the company is destroying value even if it is profitable. Compare ROIC against peers in the same sector.',
    benchmark: 'Excellent: >20%. Good: 15–20%. Average: 10–15%. Capital destructive: <WACC (~8–10%)',
    usedIn: ['Screener', 'Company Detail', 'Quality Tab'],
    tags: ['ROIC', 'return', 'capital', 'profitability', 'quality'],
  },

  // ── FINANCIAL HEALTH (ADDITIONAL) ────────────────────────────────────────
  {
    id: 'cash',
    name: 'Cash & Equivalents',
    category: 'Financial Health',
    shortDesc: 'Liquid assets held by the company',
    definition: 'Cash & equivalents represents the total liquid assets on the company\'s balance sheet — cash in hand, bank deposits, and short-term instruments convertible to cash within 90 days. High cash relative to debt provides a financial cushion and signals flexibility.',
    formula: 'Cash = Cash on Hand + Cash Equivalents (money market, short-term deposits)',
    interpretation: 'Cash-rich companies can self-fund growth, pay dividends, buy back shares, or make acquisitions without needing external financing. For miners and early-stage companies, track the cash burn rate: Quarters of Cash = Cash ÷ Quarterly Burn Rate.',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['cash', 'liquidity', 'balance sheet'],
  },
  {
    id: 'total_assets',
    name: 'Total Assets',
    category: 'Financial Health',
    shortDesc: 'Everything the company owns or controls',
    definition: 'Total assets is the sum of all assets on the balance sheet — current assets (cash, receivables, inventory) plus non-current assets (property, equipment, intangibles, investments). It represents the total resource base the business uses to generate returns.',
    formula: 'Total Assets = Current Assets + Non-Current Assets',
    interpretation: 'Asset size alone is not useful — focus on how efficiently assets generate returns (Return on Assets). Capital-light businesses (tech, financials) generate high returns from relatively small asset bases. Asset-heavy businesses (miners, utilities) require large asset bases for revenue.',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['assets', 'balance sheet', 'total assets'],
  },
  {
    id: 'total_equity',
    name: 'Shareholders\' Equity',
    category: 'Financial Health',
    shortDesc: 'Net assets attributable to shareholders',
    definition: 'Shareholders\' equity (also called net assets or book value) is what remains after subtracting total liabilities from total assets. It represents the shareholders\' residual claim on the business. Rising equity over time (from retained profits) signals wealth creation.',
    formula: 'Shareholders\' Equity = Total Assets − Total Liabilities',
    interpretation: 'Negative equity is a red flag — it means liabilities exceed assets, often due to accumulated losses or excessive debt. Book value per share derived from equity is the basis for P/B ratio analysis.',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['equity', 'book value', 'net assets', 'balance sheet'],
  },
  {
    id: 'capex',
    name: 'Capital Expenditure (CapEx)',
    category: 'Financial Health',
    shortDesc: 'Investment in physical assets and long-term infrastructure',
    definition: 'CapEx is the cash a company spends to purchase, upgrade, or maintain physical assets such as property, plant, equipment, and technology. It represents the investment needed to sustain or grow the business and appears in the cash flow statement.',
    formula: 'Free Cash Flow = Operating Cash Flow − Capital Expenditure',
    interpretation: 'High CapEx relative to revenue indicates capital-intensive industries (miners, utilities, infrastructure). Low CapEx businesses (tech, professional services) generate more free cash flow. Rising CapEx can signal either growth investment or maintenance drag — context matters.',
    benchmark: 'CapEx/Revenue: Capital-light (<5%), Moderate (5–15%), Capital-intensive (>15%)',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['capex', 'capital expenditure', 'investment', 'cash flow'],
  },
  {
    id: 'book_value_per_share',
    name: 'Book Value Per Share',
    category: 'Financial Health',
    shortDesc: 'Net assets per share at accounting (book) value',
    definition: 'Book value per share divides shareholders\' equity by total shares outstanding. It represents the theoretical per-share value of the company if all assets were sold at book value and liabilities repaid. The P/B ratio compares share price to this figure.',
    formula: 'Book Value Per Share = Shareholders\' Equity ÷ Total Shares Outstanding',
    interpretation: 'Buying below book value (P/B below 1) can indicate undervaluation — or a sign that assets are impaired. Financial stocks are most appropriately valued on a book value basis. For most businesses, intangible assets (brands, IP) mean book value understates true value.',
    example: 'Book_Value of $250M ÷ 500M shares outstanding = $0.50 per share.',
    usedIn: ['Screener', 'Company Detail', 'Financial Health Tab'],
    tags: ['book value', 'per share', 'equity', 'assets'],
  },

  // ── GROWTH (ADDITIONAL) ───────────────────────────────────────────────────
  {
    id: 'eps_forward',
    name: 'Forward EPS',
    category: 'Growth',
    shortDesc: 'Analyst consensus earnings per share estimate for next 12 months',
    definition: 'Forward EPS is the consensus estimate of EPS for the upcoming fiscal year or next 12 months, aggregated from analyst forecasts. It is used to calculate the Forward P/E ratio and assess whether current earnings justify the share price.',
    formula: 'Forward EPS = Consensus Analyst Estimate ÷ Shares Outstanding',
    interpretation: 'Forward EPS rising faster than share price signals improving value. Compare forward EPS growth rate to the current P/E to assess if growth justifies the valuation. Stocks with high P/E but rapidly growing forward EPS may be fairly valued.',
    usedIn: ['Screener', 'Company Detail', 'Analyst Tab'],
    tags: ['EPS', 'forward', 'estimate', 'consensus', 'growth'],
  },
  {
    id: 'eps_growth_yoy_q',
    name: 'EPS Growth YoY (Quarterly)',
    category: 'Growth',
    shortDesc: 'Quarterly EPS compared to the same quarter a year ago',
    definition: 'Year-over-year quarterly EPS growth compares EPS in the most recent quarter to the same quarter in the prior year. This controls for seasonality and gives the most current view of earnings momentum.',
    formula: 'EPS Growth YoY Q = (EPS This Quarter − EPS Same Quarter Last Year) ÷ |EPS Same Quarter Last Year|',
    interpretation: 'Accelerating quarterly EPS growth is one of the strongest signals of improving business momentum. Two consecutive quarters of EPS acceleration often precede share price outperformance.',
    usedIn: ['Screener', 'Company Detail', 'Earnings Tab'],
    tags: ['EPS', 'growth', 'quarterly', 'momentum'],
  },
  {
    id: 'net_income_growth_yoy_q',
    name: 'Net Income Growth YoY (Quarterly)',
    category: 'Growth',
    shortDesc: 'Net profit compared to the same quarter one year ago',
    definition: 'Measures the percentage change in net profit for the most recent quarter compared to the same quarter of the prior year. Like EPS Growth YoY Q, it controls for seasonality and provides a current-momentum read on profitability trends.',
    formula: 'Net Income Growth YoY Q = (Net Income Q − Net Income Q-4) ÷ |Net Income Q-4|',
    interpretation: 'Positive and accelerating quarterly net income growth is a bullish signal. Watch for one-time items (asset sales, write-downs) that can distort the figure. Combine with operating cash flow growth for confirmation.',
    usedIn: ['Screener', 'Company Detail', 'Earnings Tab'],
    tags: ['net income', 'profit', 'growth', 'quarterly'],
  },
  {
    id: 'net_profit_forward',
    name: 'Forward Net Profit',
    category: 'Growth',
    shortDesc: 'Consensus analyst estimate for next year net profit',
    definition: 'Forward net profit is the analyst consensus estimate for NPAT in the upcoming fiscal year. It is used to gauge the expected profitability trajectory and assess whether the current share price is pricing in realistic earnings expectations.',
    formula: 'Derived from consensus analyst model aggregation',
    interpretation: 'Compare forward net profit to current-year net profit to assess expected growth. A significant jump implies analysts expect positive catalysts. Consensus estimates can be wrong — treat forward profit as a useful guide, not a guarantee.',
    usedIn: ['Screener', 'Company Detail', 'Analyst Tab'],
    tags: ['net profit', 'forward', 'estimate', 'consensus'],
  },
  {
    id: 'revenue_forward',
    name: 'Forward Revenue',
    category: 'Growth',
    shortDesc: 'Consensus analyst estimate for next year revenue',
    definition: 'Forward revenue is the analyst consensus estimate for total revenue in the upcoming fiscal year. It is the basis for the forward EV/Revenue and forward P/S multiples, and gives a view on expected top-line growth trajectory.',
    formula: 'Derived from consensus analyst model aggregation',
    interpretation: 'Strong forward revenue growth with stable or expanding margins is the ideal combination. Revenue upgrades from analysts (upward revisions) often precede share price appreciation. Downgrades trigger the reverse.',
    usedIn: ['Screener', 'Company Detail', 'Analyst Tab'],
    tags: ['revenue', 'forward', 'estimate', 'growth'],
  },

  // ── PROFIT-BASED SIGNALS ─────────────────────────────────────────────────
  {
    id: 'operating_margin_expanding',
    name: 'Operating Margin Expanding',
    category: 'Profitability',
    shortDesc: 'Operating margin is above its own 3-year average — a margin expansion signal',
    definition: 'A boolean signal that is true when the current operating profit margin exceeds the company\'s 3-year average operating margin. Margin expansion while growing revenue is one of the strongest indicators of a scaling, efficient business.',
    formula: 'Operating Margin Expanding = Current OPM > 3Y Average OPM',
    interpretation: 'When true, the company is becoming more profitable as it grows — fixed costs are spreading over a larger revenue base. The best businesses show sustained margin expansion over multiple years. A false reading (margin contracting) may indicate rising competition, input cost pressure, or heavy spending to sustain growth.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['margin', 'profitability', 'expansion', 'operating', 'efficiency'],
  },
  {
    id: 'gross_margin_expanding',
    name: 'Gross Margin Expanding',
    category: 'Profitability',
    shortDesc: 'Gross margin is above its own 3-year average — signals improving pricing power or cost control',
    definition: 'A boolean signal that is true when the current gross profit margin exceeds the company\'s 3-year average gross margin. Gross margin is the first line of profitability defence — if it is expanding, the business has pricing power, improving cost of goods, or a better product mix.',
    formula: 'Gross Margin Expanding = Current Gross Margin > 3Y Average Gross Margin',
    interpretation: 'Rising gross margin while revenue grows is a hallmark of a quality compounder. It often signals brand strength, software-like economics, or improving scale advantages. A declining gross margin despite revenue growth is a warning sign — it may mean discounting, rising input costs, or commoditisation of the product.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['gross margin', 'profitability', 'expansion', 'pricing power'],
  },
  {
    id: 'fcf_conversion',
    name: 'FCF Conversion',
    category: 'Profitability',
    shortDesc: 'Free cash flow as a multiple of net profit — measures earnings quality',
    definition: 'FCF Conversion is the ratio of free cash flow to net profit. A ratio above 1.0x (100%) means the company generates more cash than its reported accounting profit, which is a strong signal of high earnings quality. A ratio well below 1.0x means profits are not backed by real cash — a warning sign.',
    formula: 'FCF Conversion = Free Cash Flow ÷ Net Profit (ratio, e.g. 1.2 = 120%)',
    interpretation: 'FCF Conversion > 1.0x: excellent — the business converts more than 100% of earnings into cash. 0.8–1.0x: solid. Below 0.5x: investigate — high accruals, heavy capex, or aggressive revenue recognition may be inflating reported profits. Negative FCF conversion with positive net income is a red flag.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['FCF', 'cash flow', 'earnings quality', 'conversion', 'profitability'],
  },
  {
    id: 'eps_beats_revenue_growth',
    name: 'EPS Beats Revenue Growth',
    category: 'Growth',
    shortDesc: 'EPS is growing faster than revenue — a sign of operating leverage or buybacks',
    definition: 'A boolean that is true when 1-year EPS growth exceeds 1-year revenue growth. This pattern — earnings per share growing faster than the top line — usually means the company has operating leverage (fixed costs spreading over more revenue), cost discipline, or effective share buybacks reducing the share count.',
    formula: 'EPS Beats Revenue Growth = EPS Growth 1Y > Revenue Growth 1Y',
    interpretation: 'This is one of the clearest signs that a company is scaling efficiently. When true and driven by genuine operating leverage (not just buybacks), it indicates the business model becomes more profitable as it grows. Confirm by also checking that operating margins are expanding. If EPS beats revenue solely due to heavy buybacks with flat margins, quality is lower.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['EPS', 'revenue', 'operating leverage', 'growth', 'efficiency'],
  },
  {
    id: 'operating_leverage',
    name: 'Operating Leverage (pp)',
    category: 'Growth',
    shortDesc: 'EBITDA growth minus revenue growth in percentage points — measures profit scalability',
    definition: 'Operating leverage measures how much faster EBITDA is growing relative to revenue, expressed in percentage points. A positive value means EBITDA is outpacing revenue growth — the classic sign of a scalable business where fixed costs are being leveraged over a growing revenue base.',
    formula: 'Operating Leverage = EBITDA Growth 1Y − Revenue Growth 1Y (in pp)',
    interpretation: 'Positive operating leverage (e.g. +10pp) means for every 1% of revenue growth, EBITDA is growing faster — the business is becoming more efficient. High sustained operating leverage is characteristic of software, platforms, and asset-light models. Negative operating leverage (revenue grows but EBITDA lags) means the company must spend heavily just to sustain growth — a warning sign.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['EBITDA', 'revenue', 'operating leverage', 'scalability', 'efficiency'],
  },

  // ── BALANCE SHEET SIGNALS ────────────────────────────────────────────────
  {
    id: 'net_cash',
    name: 'Net Cash Position',
    category: 'Financial Strength',
    shortDesc: 'Company holds more cash than total debt — the strongest balance sheet signal',
    definition: 'A boolean that is true when net debt is negative — meaning total cash exceeds total debt. A net cash company has no net leverage, can fund growth, acquisitions, buybacks, and dividends without borrowing, and is highly resilient in downturns.',
    formula: 'Net Cash = Net Debt < 0  (i.e. Cash > Total Debt)',
    interpretation: 'Net cash companies are the gold standard of balance sheet quality. They can opportunistically acquire, buy back shares, or simply wait out a downturn while competitors struggle. Combined with high ROIC and strong FCF, a net cash position is a hallmark of a true quality compounder. Be cautious when cash is large but earns low returns — it may indicate poor capital allocation.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['cash', 'debt', 'net cash', 'balance sheet', 'financial strength'],
  },
  {
    id: 'cash_to_debt',
    name: 'Cash to Debt (ratio)',
    category: 'Financial Strength',
    shortDesc: 'How many times cash covers total debt — a direct liquidity-vs-leverage ratio',
    definition: 'Cash to Debt is the ratio of cash and cash equivalents to total debt. A ratio above 1.0x means the company could repay all debt immediately from existing cash. Unlike net debt, this ratio shows the magnitude of coverage.',
    formula: 'Cash to Debt = Cash & Equivalents ÷ Total Debt (ratio)',
    interpretation: 'Above 1.0x: cash exceeds debt (net cash). 0.5x–1.0x: solid buffer. Below 0.2x: highly leveraged relative to cash. A company with a rising cash-to-debt ratio over multiple years is deleveraging — typically a positive signal. A falling ratio means debt is growing faster than cash, which warrants monitoring.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['cash', 'debt', 'liquidity', 'leverage', 'financial strength'],
  },
  {
    id: 'fcf_to_debt',
    name: 'FCF to Debt (ratio)',
    category: 'Financial Strength',
    shortDesc: 'Free cash flow as a fraction of total debt — measures debt serviceability from cash generation',
    definition: 'FCF to Debt measures how much of total debt could be repaid from one year\'s free cash flow. It is a forward-looking serviceability metric — unlike interest coverage (which measures interest only), this measures the ability to reduce the entire debt load.',
    formula: 'FCF to Debt = Free Cash Flow ÷ Total Debt (ratio)',
    interpretation: 'Above 0.25x (25%): strong — can repay all debt within ~4 years from FCF. Above 0.5x: excellent. Below 0.1x: debt is large relative to cash generation — the company depends on refinancing. Negative FCF to Debt means the company cannot service debt from operations, which is a warning sign unless the company is in a deliberate high-growth investment phase.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['FCF', 'free cash flow', 'debt', 'serviceability', 'leverage'],
  },
  {
    id: 'working_capital_to_sales',
    name: 'Working Capital to Sales',
    category: 'Financial Strength',
    shortDesc: 'Working capital as a fraction of revenue — measures capital efficiency of the operating cycle',
    definition: 'Working Capital to Sales is the ratio of (current assets minus current liabilities) to revenue. It shows how much working capital is needed to support each dollar of sales. A low or negative ratio means the business is capital-efficient — it can grow without tying up much cash in receivables or inventory.',
    formula: 'Working Capital to Sales = (Current Assets − Current Liabilities) ÷ Revenue',
    interpretation: 'Low positive (0.0–0.2x): capital-efficient growth. Negative: excellent — the company receives customer cash before incurring costs (software, subscriptions, fast-turnover retail). Above 0.3x: capital-intensive — growth requires proportionally more working capital. Rising over time is a warning sign — the business may be accumulating receivables or inventory to sustain revenue.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['working capital', 'revenue', 'capital efficiency', 'operating cycle'],
  },
  {
    id: 'debt_growing_slower_than_profit',
    name: 'Debt Growing Slower Than Profit',
    category: 'Financial Strength',
    shortDesc: 'Profit growth is outpacing debt growth — a deleveraging or disciplined borrowing signal',
    definition: 'A boolean that is true when 1-year profit growth exceeds 1-year debt growth. This signals that the company is becoming more profitable faster than it is taking on debt — a core pattern of compounding balance sheet strength.',
    formula: 'Debt Growing Slower Than Profit = Profit Growth 1Y > Debt Growth 1Y',
    interpretation: 'When true over multiple consecutive years, this pattern means net debt / EBITDA is naturally declining without requiring forced debt repayment. It is the balance sheet equivalent of operating leverage — earnings expand while the debt load shrinks in relative terms. A false reading (debt growing faster than profit) can still be acceptable if debt is funding high-ROIC acquisitions, but requires scrutiny.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['debt', 'profit', 'growth', 'deleveraging', 'financial discipline'],
  },
  {
    id: 'inventory_growing_slower_than_sales',
    name: 'Inventory Growing Slower Than Sales',
    category: 'Financial Strength',
    shortDesc: 'Revenue growth is keeping pace with or outpacing inventory growth — healthy stock management',
    definition: 'A boolean that is true when revenue growth (1Y) is greater than or equal to inventory growth (1Y). A company where sales grow faster than inventory is converting stock to revenue efficiently — it is not accumulating unsold goods.',
    formula: 'Inventory Growing Slower Than Sales = Revenue Growth 1Y ≥ Inventory Growth 1Y',
    interpretation: 'When true, the company\'s inventory turnover is stable or improving — a sign of healthy demand and efficient operations. When false (inventory grows faster than sales), it may indicate demand weakness, overproduction, channel stuffing, or obsolescence risk. A pattern of rising inventory relative to sales often precedes gross margin pressure and later write-downs.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['inventory', 'revenue', 'sales', 'turnover', 'working capital'],
  },
  {
    id: 'receivables_growing_slower_than_sales',
    name: 'Receivables Growing Slower Than Sales',
    category: 'Financial Strength',
    shortDesc: 'Revenue growth is keeping pace with or outpacing receivables growth — clean revenue quality',
    definition: 'A boolean that is true when revenue growth (1Y) is greater than or equal to trade receivables growth (1Y). It checks whether the company\'s reported revenue growth is backed by real cash collection — or whether revenue is being recognised before cash arrives.',
    formula: 'Receivables Growing Slower Than Sales = Revenue Growth 1Y ≥ Receivables Growth 1Y',
    interpretation: 'When true, the company is collecting cash at least as fast as it is booking revenue — a strong earnings quality signal. When false (receivables grow faster than sales), reported revenue may be running ahead of actual collections. Sustained receivables outpacing sales is a classic early warning of channel stuffing, aggressive revenue recognition, or customer payment stress. Always check alongside Days Sales Outstanding.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['receivables', 'revenue', 'earnings quality', 'DSO', 'revenue recognition'],
  },

  // ── CASH FLOW SIGNALS ────────────────────────────────────────────────────
  {
    id: 'ocf_beats_net_income',
    name: 'OCF Beats Net Income',
    category: 'Cash Flow',
    shortDesc: 'Operating cash flow is at least as large as net profit — the primary earnings quality gate',
    definition: 'A boolean that is true when operating cash flow (OCF) is greater than or equal to reported net income. This is the single most important check for whether accounting profits are backed by real cash. Companies where OCF consistently exceeds net income have high-quality, reliable earnings.',
    formula: 'OCF Beats Net Income = OCF / Net Income ≥ 1.0  (i.e. cash conversion ≥ 100%)',
    interpretation: 'When true, every dollar of reported profit is matched or exceeded by real operating cash. The gap between OCF and net income is driven by non-cash charges (depreciation) and working capital movements. Persistently true = excellent earnings quality. When false (net income > OCF), investigate: rising receivables, inventory build-up, or aggressive revenue recognition are common culprits. A company where OCF trails net income for multiple years is a red flag even if profits look strong.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['OCF', 'net income', 'earnings quality', 'cash conversion', 'operating cash flow'],
  },
  {
    id: 'capex_to_ocf',
    name: 'Capex to OCF (ratio)',
    category: 'Cash Flow',
    shortDesc: 'Capital expenditure as a fraction of operating cash flow — measures the capex burden on free cash generation',
    definition: 'Capex to OCF is the ratio of capital expenditure to operating cash flow. It shows how much of the business\'s cash generation is consumed by reinvestment. A low ratio means most OCF flows through as free cash flow; a high ratio means heavy reinvestment is required just to maintain or grow the business.',
    formula: 'Capex to OCF = Capital Expenditure ÷ Operating Cash Flow',
    interpretation: 'Below 0.25x (25%): asset-light — excellent FCF generation. 0.25x–0.50x: healthy balance of reinvestment and free cash. 0.50x–0.75x: capital-intensive. Above 0.75x: most OCF is consumed by capex, leaving little free cash. Software, platforms, and consumer brands tend to have very low capex/OCF. Utilities, mining, and telecoms tend to be high. Compare within sector.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['capex', 'OCF', 'free cash flow', 'capital intensity', 'asset-light'],
  },
  {
    id: 'fcf_growing_faster_than_revenue',
    name: 'FCF Growing Faster Than Revenue',
    category: 'Cash Flow',
    shortDesc: 'Free cash flow growth outpaces revenue growth — the hallmark of a quality compounder',
    definition: 'A boolean that is true when 1-year FCF growth exceeds 1-year revenue growth. This is one of the strongest cash-flow quality signals — it means the business is becoming more cash-generative as it scales, not just bigger. FCF growing faster than revenue implies improving margins, lower capex intensity, or better working capital management.',
    formula: 'FCF Growing Faster Than Revenue = FCF Growth 1Y > Revenue Growth 1Y',
    interpretation: 'When true, the business has cash flow operating leverage — it converts incremental revenue into free cash at an accelerating rate. The best compounders sustain this across 3, 5, and 10 years. A single year is informative; a multi-year trend is powerful. When false (revenue grows but FCF lags), the business may be consuming cash to fund growth — which is acceptable if ROIC is high, but concerning if persistent.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['FCF', 'revenue', 'free cash flow', 'growth', 'compounder', 'cash efficiency'],
  },
  {
    id: 'ocf_positive',
    name: 'OCF Positive',
    category: 'Cash Flow',
    shortDesc: 'Operating cash flow is positive — the most basic sign that the business generates real cash',
    definition: 'A boolean that is true when the most recent annual operating cash flow (OCF) is greater than zero. This is a fundamental quality gate — a business with positive OCF is generating real cash from its core operations, not just recording accounting profits.',
    formula: 'OCF Positive = Operating Cash Flow > 0',
    interpretation: 'Positive OCF is a minimum threshold for most quality screens. Many early-stage, loss-making, or restructuring companies have negative OCF for years. Filtering for OCF Positive removes these and focuses the universe on businesses that self-fund from operations. Note that even OCF-positive companies can have poor cash quality — always check OCF vs Net Income and the trend over time.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['OCF', 'operating cash flow', 'positive', 'cash quality', 'profitability'],
  },
  {
    id: 'ocf_growing',
    name: 'OCF Growing (YoY)',
    category: 'Cash Flow',
    shortDesc: 'Operating cash flow is higher than the prior year — a momentum signal for cash generation',
    definition: 'A boolean that is true when the most recent annual OCF is higher than the prior year\'s OCF. Year-on-year OCF growth means the business is generating more cash from operations than it did 12 months ago — a positive momentum signal on the most fundamental cash flow measure.',
    formula: 'OCF Growing = Current Year OCF > Prior Year OCF',
    interpretation: 'When true, the core cash engine is strengthening. Combined with OCF Positive and OCF Beats Net Income, OCF Growing gives a three-way cash quality confirmation. One year of OCF growth is a signal; look for consistency across 3, 5, and 7 years for a quality compounder. A company where OCF grows even in down-revenue years is showing strong operating leverage and working capital discipline.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['OCF', 'operating cash flow', 'growth', 'YoY', 'momentum', 'cash generation'],
  },

  // ── RATIO FRAMEWORK SIGNALS ──────────────────────────────────────────────
  {
    id: 'earning_power',
    name: 'Earning Power (EBIT/Assets %)',
    category: 'Profitability',
    shortDesc: 'EBIT as a percentage of total assets — a pre-tax, pre-interest measure of asset productivity',
    definition: 'Earning Power is EBIT divided by total assets, expressed as a percentage. Unlike ROA (which uses net income), Earning Power strips out the effects of interest expense and tax — making it a cleaner measure of how productively the company uses its assets before financing and tax decisions.',
    formula: 'Earning Power = EBIT ÷ Total Assets × 100%',
    interpretation: 'High earning power means the company\'s core operations generate strong returns from its asset base, regardless of how it is financed. It is especially useful for comparing companies with different capital structures or tax positions. A falling earning power over time — even with rising net income — can signal that the asset base is growing faster than operating profit, a warning of declining efficiency.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['EBIT', 'total assets', 'earning power', 'ROA', 'profitability', 'asset return'],
  },
  {
    id: 'financial_leverage',
    name: 'Financial Leverage (Assets/Equity)',
    category: 'Financial Strength',
    shortDesc: 'Total assets divided by shareholders equity — the DuPont leverage multiplier',
    definition: 'Financial Leverage is the ratio of total assets to shareholders\' equity. It is the leverage component of the DuPont ROE decomposition: ROE = Net Margin × Asset Turnover × Financial Leverage. A higher ratio means more of the asset base is funded by debt and liabilities, amplifying both returns and risk.',
    formula: 'Financial Leverage = Total Assets ÷ Shareholders\' Equity',
    interpretation: '1.0x means the company is fully equity-funded (no liabilities). 2.0x–3.0x is typical for most industrial businesses. Above 5x is highly leveraged — common in banks and utilities but risky elsewhere. Unlike Debt/Equity (which only counts financial debt), Financial Leverage captures all liabilities including trade payables, leases, and provisions — making it a broader balance sheet leverage measure.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['leverage', 'DuPont', 'equity', 'assets', 'financial strength', 'balance sheet'],
  },
  {
    id: 'days_payable_outstanding',
    name: 'Days Payable Outstanding',
    category: 'Profitability',
    shortDesc: 'How many days the company takes to pay its suppliers — a measure of working capital management',
    definition: 'Days Payable Outstanding (DPO) measures the average number of days a company takes to pay its trade creditors. It is calculated by dividing trade payables by COGS and multiplying by 365. DPO is the third component of the Cash Conversion Cycle alongside DSO and DIO.',
    formula: 'DPO = Trade Payables ÷ Cost of Goods Sold × 365',
    interpretation: 'Higher DPO means the company takes longer to pay suppliers — which can be positive (efficient use of supplier credit, improving working capital) or negative (struggling to pay, damaging supplier relationships). Great businesses often have moderate DPO that is stable over time. A sharply rising DPO can signal cash flow stress. Compare with DSO: if DSO rises while DPO rises, both customers and suppliers are under strain.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['DPO', 'payables', 'working capital', 'cash cycle', 'suppliers', 'COGS'],
  },
  {
    id: 'cash_conversion_cycle',
    name: 'Cash Conversion Cycle (days)',
    category: 'Profitability',
    shortDesc: 'DIO + DSO − DPO — the full working capital cycle, measuring days from cash-out to cash-in',
    definition: 'The Cash Conversion Cycle (CCC) measures how many days it takes a company to convert its investments in inventory and receivables back into cash, after accounting for supplier credit. A lower CCC means the company ties up less cash in its operating cycle. A negative CCC (collecting cash before paying suppliers or holding inventory) is exceptional.',
    formula: 'CCC = Days Inventory Outstanding + Days Sales Outstanding − Days Payable Outstanding',
    interpretation: 'CCC < 0: exceptional — the company uses customer cash to fund operations (software, subscriptions, some retailers). CCC 0–30 days: very efficient. CCC 30–60 days: typical for manufacturers and distributors. CCC > 90 days: capital-intensive, large amounts of cash tied up. A falling CCC over time signals improving working capital efficiency — a hallmark of compounding operational quality.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['CCC', 'cash conversion cycle', 'working capital', 'DIO', 'DSO', 'DPO', 'liquidity'],
  },
  {
    id: 'roe_improving',
    name: 'ROE Improving',
    category: 'Profitability',
    shortDesc: 'Current ROE is above the 3-year average — a trend signal for improving shareholder returns',
    definition: 'A boolean that is true when the current Return on Equity (ROE) exceeds the company\'s 3-year average ROE. This signals that the company is becoming more profitable for shareholders — either through margin expansion, better asset utilisation, or disciplined leverage.',
    formula: 'ROE Improving = Current ROE > 3Y Average ROE',
    interpretation: 'When true, the company\'s ability to generate profit from shareholder equity is trending up — one of the most important indicators of business quality improvement. Combined with low debt (to confirm ROE is not artificially inflated by leverage), this is a strong quality signal. When false but ROE is already very high (e.g. 30%+), a slight dip may reflect base effects rather than deterioration. Always check alongside ROCE to confirm the trend is real.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['ROE', 'return on equity', 'improving', 'trend', 'profitability', 'quality'],
  },
  {
    id: 'roce_improving',
    name: 'ROCE Improving',
    category: 'Profitability',
    shortDesc: 'Current ROCE is above the 3-year average — signals the capital base is being used more efficiently',
    definition: 'A boolean that is true when the current Return on Capital Employed (ROCE) exceeds the company\'s 3-year average ROCE. ROCE measures returns on all capital (equity + debt), making it a cleaner indicator of operational efficiency than ROE, which can be distorted by leverage.',
    formula: 'ROCE Improving = Current ROCE > 3Y Average ROCE',
    interpretation: 'A rising ROCE means the business is generating more operating profit per dollar of capital — the hallmark of a quality compounder. When ROCE improving is true alongside debt_growing_slower_than_profit and operating_margin_expanding, the company is simultaneously becoming more efficient, more profitable, and less leveraged — a rare and powerful combination. A falling ROCE despite rising revenue often signals that growth is coming at the cost of capital efficiency.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['ROCE', 'return on capital', 'improving', 'trend', 'capital efficiency', 'quality'],
  },

  // ── TIER-1 QUALITATIVE PROXIES ────────────────────────────────────────────
  {
    id: 'gross_margin_stability',
    name: 'Gross Margin Stability',
    category: 'Quality',
    shortDesc: 'Standard deviation of gross margin over 5 years — lower values indicate a more stable, defensible business model',
    definition: 'Measures the variability of gross margin (gross profit ÷ revenue) across the most recent 5 fiscal years, expressed as a standard deviation. A low score means the company consistently earns similar margins regardless of market conditions — a hallmark of pricing power, brand strength, or durable cost advantages.',
    formula: 'Gross Margin Stability = StdDev(Gross Margin %, last 5 FY)',
    interpretation: 'A low value (e.g., under 0.03) means gross margins have barely moved over 5 years — indicating the company can maintain pricing in downturns and isn\'t exposed to volatile input costs. This is a proxy for moat durability. Combine with high avg_gross_margin_3y to identify businesses with both high and stable margins. A high value suggests the company\'s margins swing with commodity prices, project mix, or competitive pressure.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['gross margin', 'stability', 'moat', 'pricing power', 'quality', 'consistency'],
  },
  {
    id: 'revenue_predictability',
    name: 'Revenue Predictability',
    category: 'Quality',
    shortDesc: 'Coefficient of variation of revenue growth over 5 years — lower values indicate more predictable, recurring revenue',
    definition: 'Measures how consistently a company grows revenue by computing the coefficient of variation (standard deviation ÷ mean) of annual revenue growth rates over the last 5 fiscal years. A lower score means revenue growth is smoother and more reliable — suggesting recurring contracts, subscription models, or structural demand rather than lumpy project wins.',
    formula: 'Revenue Predictability = StdDev(Revenue Growth %, last 5 FY) ÷ Mean(Revenue Growth %, last 5 FY)',
    interpretation: 'A value close to 0 indicates highly consistent growth year-on-year — the business is predictable, which markets typically reward with higher P/E multiples. Values above 1.0 suggest growth is erratic: the company may boom in some years and stall or contract in others, making it harder to model future earnings. Use alongside revenue_cagr_3y to distinguish between high-growth-but-lumpy versus steady-compounding businesses.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['revenue', 'predictability', 'consistency', 'recurring revenue', 'quality', 'growth'],
  },
  {
    id: 'revenue_above_sector_median',
    name: 'Revenue Growth Above Sector Median',
    category: 'Quality',
    shortDesc: 'True when a company\'s 3-year revenue CAGR exceeds its sector\'s median — a proxy for market share gain',
    definition: 'A boolean that is true when the company\'s 3-year revenue CAGR (revenue_cagr_3y) is above the median 3-year revenue CAGR for all companies in the same sector. This is a relative strength signal: even if the sector is growing slowly, companies beating the median are likely taking market share from competitors.',
    formula: 'Revenue Above Sector Median = Revenue CAGR 3Y > Median(Revenue CAGR 3Y, same sector)',
    interpretation: 'This signal is powerful precisely because it is relative. A company growing at 8% in a sector with a median of 4% is outperforming its peers — even if 8% sounds modest in isolation. Combine with gross_margin_stability and operating_margin_expanding to identify companies gaining share without sacrificing profitability. The sector median is recomputed each nightly build, so the signal adapts as sector composition changes.',
    usedIn: ['Screener', 'Filter Builder', 'Query Mode'],
    tags: ['revenue', 'sector', 'market share', 'relative strength', 'growth', 'quality'],
  },

  // ── QUALITY (ADDITIONAL) ──────────────────────────────────────────────────
  {
    id: 'avg_roic_3y',
    name: '3-Year Average ROIC',
    category: 'Quality Scores',
    shortDesc: 'Return on invested capital averaged over 3 years',
    definition: 'The 3-year average ROIC smooths out single-year fluctuations to give a more reliable view of capital efficiency. Consistently high ROIC over 3+ years is one of the best indicators of a durable competitive advantage.',
    formula: 'Avg ROIC 3Y = (ROIC Year-1 + ROIC Year-2 + ROIC Year-3) ÷ 3',
    interpretation: 'A business maintaining 15%+ ROIC for 3+ years has a genuine edge. Look for stability alongside the level — a ROIC that swings wildly suggests cyclicality rather than a structural moat.',
    benchmark: 'World-class: >25%. Strong: 15–25%. Average: 8–15%. Poor: <8%',
    example: 'roic of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail', 'Quality Tab'],
    tags: ['ROIC', 'quality', 'capital efficiency', '3-year average'],
  },
  {
    id: 'avg_roic_5y',
    name: '5-Year Average ROIC',
    category: 'Quality Scores',
    shortDesc: 'Return on invested capital averaged over 5 years',
    definition: 'The 5-year average ROIC provides the most reliable assessment of capital allocation quality, spanning a full business cycle. Quality investors look for 5-year average ROIC of 15%+ as a hallmark of a truly great business.',
    formula: 'Avg ROIC 5Y = Sum of ROIC over 5 years ÷ 5',
    interpretation: 'The most robust quality signal in fundamental analysis. A company with 20%+ average ROIC over 5 years has almost certainly compounded shareholder wealth significantly. Compare against peers, not absolute benchmarks.',
    benchmark: 'Elite: >20%. Strong: 15–20%. Good: 10–15%. Weak: <10%',
    example: 'roic of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail', 'Quality Tab'],
    tags: ['ROIC', 'quality', 'capital efficiency', '5-year average'],
  },
  {
    id: 'ocf_to_net_profit',
    name: 'OCF / Net Profit',
    category: 'Quality Scores',
    shortDesc: 'Operating cash flow as a multiple of reported net profit',
    definition: 'The ratio of operating cash flow to net profit measures earnings quality — specifically whether reported profits are backed by real cash generation. Accounting profits can be inflated by aggressive revenue recognition; cash flow is harder to manipulate.',
    formula: 'OCF to Net Profit = Operating Cash Flow ÷ Net Profit After Tax',
    interpretation: 'A ratio consistently above 1.0 means the company collects more cash than it reports as profit — a sign of high earnings quality. Ratio below 0.7 over multiple years is a red flag suggesting earnings quality issues or accruals build-up.',
    benchmark: 'Excellent: >1.2. Good: 1.0–1.2. Acceptable: 0.8–1.0. Concerning: <0.8',
    usedIn: ['Screener', 'Company Detail', 'Quality Tab'],
    tags: ['cash flow', 'earnings quality', 'accruals', 'quality'],
  },
  {
    id: 'fcf_payout_ratio',
    name: 'FCF Payout Ratio',
    category: 'Quality Scores',
    shortDesc: 'Dividends paid as a percentage of free cash flow',
    definition: 'FCF payout ratio measures what proportion of free cash flow (operating cash flow minus CapEx) is distributed to shareholders as dividends. Unlike the earnings-based payout ratio, it reflects whether dividends are truly affordable.',
    formula: 'FCF Payout Ratio = Dividends Paid ÷ Free Cash Flow',
    interpretation: 'FCF payout ratio below 60% suggests a sustainable dividend with room for growth. Above 90% indicates the dividend is consuming nearly all free cash flow. Above 100% means dividends are being funded by debt or asset sales.',
    benchmark: 'Sustainable: <60%. Watch: 60–90%. Stretched: 90–100%. Unsustainable: >100%',
    usedIn: ['Screener', 'Company Detail', 'Dividends Tab'],
    tags: ['FCF', 'payout ratio', 'dividend sustainability', 'free cash flow'],
  },
  {
    id: 'fcf_positive_years',
    name: 'FCF Positive Years (of 5)',
    category: 'Quality Scores',
    shortDesc: 'Number of years in the past 5 with positive free cash flow',
    definition: 'Counts the number of years out of the last five in which the company generated positive free cash flow. It is a simple consistency check for cash generation quality.',
    formula: 'FCF Positive Years = Count of years where (OCF − CapEx) > 0, over the trailing 5 years',
    interpretation: '5/5 years of positive FCF = highly reliable cash generator. 3–4/5 = generally good with some cyclicality. Less than 3/5 = concerning; may be funding operations with debt or equity issuance.',
    benchmark: 'Excellent: 5/5. Good: 4/5. Acceptable: 3/5. Poor: <3/5',
    usedIn: ['Screener', 'Company Detail', 'Quality Tab'],
    tags: ['FCF', 'free cash flow', 'consistency', 'quality'],
  },
  {
    id: 'eps_volatility_5y',
    name: 'EPS Volatility (5-Year)',
    category: 'Quality Scores',
    shortDesc: 'Variability of earnings per share over the past 5 years',
    definition: 'EPS volatility measures how stable or erratic a company\'s earnings have been over the past 5 years, expressed as the standard deviation of EPS. Low volatility indicates predictable, quality earnings.',
    formula: 'EPS Volatility = Standard Deviation of EPS over 5 years',
    interpretation: 'Low EPS volatility is a hallmark of high-quality businesses — think consumer staples, toll roads, or regulated utilities. High volatility suggests cyclicality (miners, energy) or operational instability. In combination with high ROIC, low volatility commands a premium P/E.',
    usedIn: ['Screener', 'Company Detail', 'Quality Tab'],
    tags: ['EPS', 'volatility', 'earnings quality', 'stability', 'quality'],
  },
  {
    id: 'shares_dilution_3y',
    name: 'Share Dilution (3-Year)',
    category: 'Quality Scores',
    shortDesc: 'Percentage change in shares on issue over 3 years',
    definition: 'Share dilution tracks the percentage increase in total shares outstanding over the past 3 years. Companies that repeatedly issue new shares dilute existing shareholders\' ownership and reduce EPS growth even when profits are rising.',
    formula: 'Share Dilution 3Y = (Current Shares − Shares 3 Years Ago) ÷ Shares 3 Years Ago × 100',
    interpretation: 'Negative dilution (buybacks) is shareholder-friendly. Zero dilution means the company is self-funding. 10%+ dilution over 3 years is a meaningful headwind to EPS growth. Capital raises are acceptable for genuine growth but not to fund ongoing operations.',
    benchmark: 'Excellent (buybacks): <0%. Good: 0–3%. Acceptable: 3–10%. Concerning: >10%',
    usedIn: ['Screener', 'Company Detail', 'Quality Tab'],
    tags: ['dilution', 'shares', 'buyback', 'quality'],
  },
  {
    id: 'short_interest_chg_1w',
    name: 'Short Interest Change (1-Week)',
    category: 'Quality Scores',
    shortDesc: 'Weekly change in the percentage of shares sold short',
    definition: 'Measures the week-over-week change in short interest as a percentage of shares outstanding. Sourced from ASIC\'s bi-monthly short position reports. A sharp increase in short interest may signal that informed traders expect the share price to fall.',
    formula: 'Short Interest Change 1W = Short Interest This Week − Short Interest Last Week (% of shares)',
    interpretation: 'A spike in short interest change (e.g., +1% in a week) is a warning signal — it indicates conviction selling from short sellers who must eventually buy back shares. Large short interest can also create short squeezes when positive news triggers rapid covering.',
    usedIn: ['Screener', 'Company Detail', 'Short Data Tab'],
    tags: ['short interest', 'ASIC', 'short selling', 'sentiment'],
  },

  // ── TECHNICAL INDICATORS (ADDITIONAL) ────────────────────────────────────
  {
    id: 'ema_20',
    name: '20-Day Exponential Moving Average',
    category: 'Technical Indicators',
    shortDesc: 'Weighted moving average giving more weight to recent prices',
    definition: 'The 20-day EMA gives exponentially more weight to recent price data than older data, making it more responsive to new information than a simple moving average. It is used to identify short-term trends and dynamic support/resistance levels.',
    formula: 'EMA = Previous EMA × (1 − k) + Current Price × k, where k = 2 ÷ (n+1)',
    interpretation: 'Price above EMA-20 signals a short-term uptrend; below signals a downtrend. The EMA-20 often acts as a dynamic support level in trending markets. Crossovers with the EMA-50 generate buy/sell signals.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['EMA', 'moving average', 'trend', 'technical'],
  },
  {
    id: 'macd_signal',
    name: 'MACD Signal Line',
    category: 'Technical Indicators',
    shortDesc: '9-day EMA of the MACD line, used to generate buy/sell signals',
    definition: 'The MACD Signal Line is a 9-period EMA of the MACD line itself. Buy signals are generated when the MACD crosses above the signal line; sell signals when it crosses below. The gap between MACD and signal (the histogram) shows momentum strength.',
    formula: 'Signal Line = 9-day EMA of (EMA-12 − EMA-26)',
    interpretation: 'MACD above signal line = bullish momentum. MACD crossing below signal = bearish. Divergence between price and MACD (price making new highs while MACD does not) is a classic reversal warning. Best used with volume confirmation.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['MACD', 'signal', 'momentum', 'technical'],
  },
  {
    id: 'bb_upper',
    name: 'Bollinger Band Upper',
    category: 'Technical Indicators',
    shortDesc: '2 standard deviations above the 20-day moving average',
    definition: 'The upper Bollinger Band is set at 2 standard deviations above the 20-day simple moving average of price. It dynamically widens during high-volatility periods and contracts during low-volatility periods, providing a statistical measure of extended price levels.',
    formula: 'BB Upper = SMA-20 + (2 × 20-day Standard Deviation of Price)',
    interpretation: 'Price touching the upper band in a strong trend is normal. In range-bound markets, the upper band is a reliable resistance area. Combine with RSI for confirmation. A "squeeze" (narrow bands) often precedes a major breakout.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['Bollinger Bands', 'volatility', 'resistance', 'technical'],
  },
  {
    id: 'bb_lower',
    name: 'Bollinger Band Lower',
    category: 'Technical Indicators',
    shortDesc: '2 standard deviations below the 20-day moving average',
    definition: 'The lower Bollinger Band is set at 2 standard deviations below the 20-day simple moving average. When price reaches the lower band, statistically around 95% of recent price action is above it, indicating a relatively oversold condition.',
    formula: 'BB Lower = SMA-20 − (2 × 20-day Standard Deviation of Price)',
    interpretation: 'Price at the lower band in a range-bound market often represents a buying opportunity. In a downtrend, price can continue walking the lower band. Always combine with trend analysis and volume for confirmation.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['Bollinger Bands', 'volatility', 'support', 'technical'],
  },
  {
    id: 'atr_14',
    name: 'Average True Range (14-day)',
    category: 'Technical Indicators',
    shortDesc: 'Average daily price movement over 14 days (volatility measure)',
    definition: 'ATR measures market volatility by averaging the "true range" (the largest of: high−low, high−previous close, low−previous close) over 14 days. It does not indicate direction — only the magnitude of typical daily price swings.',
    formula: 'ATR = 14-day EMA of True Range',
    interpretation: 'High ATR = high volatility stock — position sizes should be smaller to control risk. Low ATR = calm, low-volatility mover. ATR expanding sharply can precede a big directional move. Commonly used to set stop-loss levels (e.g., stop at 2× ATR below entry).',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['ATR', 'volatility', 'range', 'risk', 'technical'],
  },
  {
    id: 'momentum_3m',
    name: '3-Month Price Momentum',
    category: 'Technical Indicators',
    shortDesc: 'Total price return over the past 3 months',
    definition: 'Three-month momentum measures the percentage price return over the past 63 trading days. Price momentum is one of the most academically validated stock return factors, with stocks showing strong recent returns tending to continue outperforming.',
    formula: 'Momentum 3M = (Current Price ÷ Price 3 months ago) − 1',
    interpretation: 'Stocks with strong 3–12 month momentum tend to continue outperforming over the next 3–6 months. Pair with fundamental quality filters to avoid momentum traps in deteriorating businesses.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['momentum', '3-month', 'price return', 'technical'],
  },
  {
    id: 'momentum_6m',
    name: '6-Month Price Momentum',
    category: 'Technical Indicators',
    shortDesc: 'Total price return over the past 6 months',
    definition: 'Six-month momentum is the percentage price return over the past 126 trading days. Research consistently finds that stocks with strong 6–12 month momentum outperform over the following 3–6 months, especially in trending market regimes.',
    formula: 'Momentum 6M = (Current Price ÷ Price 6 months ago) − 1',
    interpretation: 'Strong 6-month momentum combined with solid fundamentals is a high-conviction signal. Momentum works best in trending markets and tends to underperform or reverse sharply around market turning points.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['momentum', '6-month', 'price return', 'technical'],
  },
  {
    id: 'momentum_12m',
    name: '12-Month Price Momentum',
    category: 'Technical Indicators',
    shortDesc: 'Total price return over the past 12 months',
    definition: 'Twelve-month momentum is the most widely studied momentum signal. The Jegadeesh-Titman (1993) paper demonstrated that stocks with the highest 12-month returns tend to continue outperforming over the next year.',
    formula: 'Momentum 12M = (Current Price ÷ Price 12 months ago) − 1',
    interpretation: 'Top-decile 12-month momentum stocks historically outperform by 1–2% per month over the following 3–12 months. The effect is strongest in mid-cap stocks and tends to reverse over 3–5 year horizons.',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['momentum', '12-month', 'price return', 'factor', 'technical'],
  },
  {
    id: 'above_sma50',
    name: 'Price Above 50-Day SMA',
    category: 'Technical Indicators',
    shortDesc: 'Whether the current price is above the 50-day moving average',
    definition: 'A binary indicator (true/false) showing whether the current share price is trading above its 50-day simple moving average. The 50-day SMA is the most widely watched medium-term trend indicator used by technical traders and quantitative funds.',
    formula: 'Above SMA50 = 1 if Current Price > 50-day SMA, else 0',
    interpretation: 'Price above SMA-50 signals a medium-term uptrend. Stocks breaking above their SMA-50 after a consolidation period often see increased institutional buying. This filter is widely used to exclude stocks in downtrends from a watchlist.',
    usedIn: ['Screener', 'Technical Tab'],
    tags: ['SMA', '50-day', 'trend', 'moving average', 'technical'],
  },
  {
    id: 'above_sma200',
    name: 'Price Above 200-Day SMA',
    category: 'Technical Indicators',
    shortDesc: 'Whether the current price is above the 200-day moving average',
    definition: 'A binary indicator showing whether the current price is above the 200-day simple moving average — the most important long-term trend indicator in technical analysis. Institutional investors widely use the 200-day SMA as the boundary between bull and bear market phases.',
    formula: 'Above SMA200 = 1 if Current Price > 200-day SMA, else 0',
    interpretation: 'Being above the 200-day SMA is considered the definition of a long-term uptrend. Many systematic funds only hold long positions in stocks above this level. The "death cross" (50-day SMA crossing below 200-day SMA) is a widely watched bearish signal.',
    usedIn: ['Screener', 'Technical Tab'],
    tags: ['SMA', '200-day', 'trend', 'moving average', 'technical'],
  },
  {
    id: 'volume_ratio',
    name: 'Volume Ratio',
    category: 'Technical Indicators',
    shortDesc: 'Today\'s volume relative to the 20-day average volume',
    definition: 'Volume ratio compares the current trading volume to the 20-day average volume. A ratio above 1.0 means today is busier than usual; below 1.0 means quieter. Unusual volume often precedes or accompanies significant price movements.',
    formula: 'Volume Ratio = Today\'s Volume ÷ 20-Day Average Volume',
    interpretation: 'Volume ratio above 2.0 with a price breakout significantly increases signal reliability — volume confirms price. Low volume rallies are less trustworthy. High volume on a down day suggests distribution (selling pressure).',
    usedIn: ['Screener', 'Company Detail', 'Technical Tab'],
    tags: ['volume', 'ratio', 'liquidity', 'technical'],
  },

  // ── PRICE & RETURNS (ADDITIONAL) ─────────────────────────────────────────
  {
    id: 'return_6m',
    name: '6-Month Total Return',
    category: 'Price & Returns',
    shortDesc: 'Price appreciation plus dividends over the past 6 months',
    definition: 'Six-month total return measures the combined gain from share price appreciation and dividends received over the past 26 weeks, expressed as a percentage. It is the primary medium-term return horizon used in momentum research.',
    formula: 'Return 6M = ((End Price + Dividends) ÷ Start Price) − 1',
    usedIn: ['Screener', 'Company Detail', 'Returns Tab'],
    tags: ['return', '6-month', 'performance', 'price'],
  },
  {
    id: 'return_7y',
    name: '7-Year Total Return',
    category: 'Price & Returns',
    shortDesc: 'Cumulative total return including dividends over 7 years',
    definition: 'The 7-year total return measures the full compounded gain (price + dividends) over the past seven years. It spans more than one typical business cycle, revealing whether a company consistently creates long-term value through different economic environments.',
    formula: 'Return 7Y = ((Current Price + Cumulative Dividends) ÷ Price 7 years ago) − 1',
    interpretation: 'Seven-year returns reveal compound value creation across a full cycle. Strong long-term returns combined with low volatility indicate a truly outstanding business. Compare against the ASX 200 total return benchmark for relative outperformance.',
    usedIn: ['Screener', 'Company Detail', 'Returns Tab'],
    tags: ['return', '7-year', 'long-term', 'performance'],
  },
  {
    id: 'low_52w',
    name: '52-Week Low',
    category: 'Price & Returns',
    shortDesc: 'Lowest share price traded over the past 52 weeks',
    definition: 'The 52-week low is the lowest price at which the shares have traded over the past year. Together with the 52-week high, it provides context for where the current price sits within the recent trading range.',
    formula: '52-Week Low = Minimum closing price over past 252 trading days',
    interpretation: 'A stock trading near its 52-week low may be cheap or in distress — fundamental analysis is essential to distinguish the two. Contrarian investors screen for stocks near 52-week lows with improving fundamentals. Stocks breaking to new 52-week lows often continue falling.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['52-week low', 'price', 'range', 'support'],
  },

  // ── DIVIDENDS (ADDITIONAL) ────────────────────────────────────────────────
  {
    id: 'dps',
    name: 'Dividends Per Share (DPS)',
    category: 'Dividends & Income',
    shortDesc: 'Total annual dividend paid per share',
    definition: 'Dividends Per Share is the total cash dividend distributed to shareholders for each ordinary share held, typically over a fiscal year (combining interim and final dividends). It is the raw dollar amount before any tax considerations.',
    formula: 'DPS = Total Dividends Paid ÷ Total Shares Outstanding',
    interpretation: 'Rising DPS over time signals management confidence in earnings sustainability. Dividend cuts are severe negative signals — markets typically punish cuts sharply. Compare DPS to earnings (payout ratio) and free cash flow (FCF payout ratio) to assess sustainability.',
    benchmark: 'ASX median yield context: 4–5% gross. High yield: >6%. Very low: <1%',
    usedIn: ['Screener', 'Company Detail', 'Dividends Tab'],
    tags: ['dividend', 'DPS', 'income', 'yield'],
  },
  {
    id: 'franking_credit_per_share',
    name: 'Franking Credits Per Share',
    category: 'ASX-Specific',
    shortDesc: 'Tax credits attached to each share\'s dividend, passed to Australian shareholders',
    definition: 'Franking credits (also called imputation credits) represent the tax already paid by the company at the corporate rate (30% or 25% for base rate entities). Australian resident shareholders can use these credits to reduce their personal tax bill or receive a cash refund if their marginal rate is lower.',
    formula: 'Franking Credit = (Dividend ÷ (1 − Company Tax Rate)) × Company Tax Rate',
    interpretation: 'Franking credits are extremely valuable for Australian investors, particularly self-managed super funds in pension phase (0% tax) and low-income earners who receive cash refunds. A fully franked 5% yield grosses up to ~7.1% for a 30% taxpayer — compare grossed-up yields when evaluating income stocks.',
    benchmark: 'Fully franked: 100% (maximum credits). Partially franked: 0–99%. Unfranked: 0% (common for international earners, REITs)',
    example: 'Franking_Credit of $250M ÷ 500M shares outstanding = $0.50 per share.',
    usedIn: ['Screener', 'Company Detail', 'Dividends Tab', 'ASX-Specific'],
    tags: ['franking', 'imputation', 'dividend', 'tax', 'ASX'],
  },

  // ── ANALYST COVERAGE ─────────────────────────────────────────────────────
  {
    id: 'analyst_target_price',
    name: 'Analyst Target Price',
    category: 'Quality Scores',
    shortDesc: '12-month consensus price target from covering analysts',
    definition: 'The analyst target price is the average 12-month price target across all sell-side analysts who cover the stock. It represents the collective view on fair value, though targets are frequently revised and have significant forecast error.',
    formula: 'Analyst Target Price = Consensus of individual analyst 12-month price targets',
    interpretation: 'Large upside to consensus target (analyst upside above 20%) can indicate the stock is under-followed or misunderstood. However, targets systematically lag price — buy-side institutions adjust their own views earlier than published sell-side targets. Use as one input, not a primary driver.',
    usedIn: ['Screener', 'Company Detail', 'Analyst Tab'],
    tags: ['analyst', 'target price', 'consensus', 'valuation'],
  },
  {
    id: 'analyst_upside',
    name: 'Analyst Upside (%)',
    category: 'Quality Scores',
    shortDesc: 'Percentage difference between current price and consensus target',
    definition: 'Analyst upside measures the percentage gap between the current share price and the average analyst 12-month target price. Positive values mean analysts see upside; negative values mean the stock has exceeded consensus targets.',
    formula: 'Analyst Upside = (Consensus Target Price − Current Price) ÷ Current Price × 100',
    interpretation: 'Upside above 20% combined with 3+ buy ratings is a meaningfully bullish consensus signal. Negative implied upside suggests the stock may be priced for perfection or analysts have not yet upgraded targets after positive news.',
    usedIn: ['Screener', 'Company Detail', 'Analyst Tab'],
    tags: ['analyst', 'upside', 'target', 'consensus'],
  },
  {
    id: 'analyst_count',
    name: 'Analyst Coverage Count',
    category: 'Quality Scores',
    shortDesc: 'Number of analysts providing earnings estimates for the stock',
    definition: 'The number of sell-side analysts who publish research and earnings estimates for the stock. Coverage count is a proxy for investor awareness and liquidity. Highly covered stocks have more efficient pricing; under-covered stocks may offer alpha opportunities.',
    formula: 'Count of analysts with active models for the stock',
    interpretation: 'More than 10 analysts = well-covered (large-cap, efficient pricing). 5–10 = moderate coverage. 1–4 = under-covered (potential discovery opportunity). Zero analysts = self-directed analysis required.',
    usedIn: ['Screener', 'Company Detail', 'Analyst Tab'],
    tags: ['analyst', 'coverage', 'consensus'],
  },
  {
    id: 'analyst_buy_pct',
    name: 'Analyst Buy %',
    category: 'Quality Scores',
    shortDesc: 'Percentage of analysts with a Buy or Strong Buy rating',
    definition: 'The proportion of covering analysts who have issued a Buy, Strong Buy, or Outperform recommendation. It summarises sentiment in the analyst community. Note: sell-side analysts rarely issue Sell recommendations, so even 50% buy ratings may indicate moderate conviction.',
    formula: 'Analyst Buy % = (Number of Buy Ratings ÷ Total Analyst Ratings) × 100',
    interpretation: 'Buy % above 80% = strong consensus buy. 60–80% = moderate buy bias. 40–60% = mixed/neutral. Below 40% = analyst caution (rare). After earnings beats with rising buy %, upgrades often follow and can be a catalyst.',
    usedIn: ['Screener', 'Company Detail', 'Analyst Tab'],
    tags: ['analyst', 'buy rating', 'consensus', 'sentiment'],
  },
  {
    id: 'analyst_consensus_score',
    name: 'Analyst Consensus Score',
    category: 'Quality Scores',
    shortDesc: 'Numeric score from analyst ratings (1=Strong Buy to 5=Strong Sell)',
    definition: 'A numerical aggregation of analyst recommendations on a standardised scale: 1 = Strong Buy, 2 = Buy, 3 = Hold, 4 = Sell, 5 = Strong Sell. A lower score indicates a more bullish consensus.',
    formula: 'Consensus Score = Weighted average of individual analyst rating scores',
    interpretation: 'Score of 1.0–1.5 = near-unanimous buy consensus (rare and significant). 1.5–2.5 = bullish bias. 2.5–3.5 = neutral/hold consensus. 3.5+ = negative bias (unusual for sell-side, so meaningful when it occurs). Track changes over time — improving score trends correlate with price outperformance.',
    usedIn: ['Screener', 'Company Detail', 'Analyst Tab'],
    tags: ['analyst', 'consensus', 'score', 'rating'],
  },
  {
    id: 'above_sma20',
    name: 'Above SMA 20',
    category: 'Technical Indicators',
    shortDesc: 'True when: Above SMA 20',
    definition: 'A yes/no flag — true when the stock meets the condition \'Above SMA 20\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'above_vwap',
    name: 'Price Above VWAP',
    category: 'ASX-Specific',
    shortDesc: 'True when: Price Above VWAP',
    definition: 'A yes/no flag — true when the stock meets the condition \'Price Above VWAP\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'asx-specific'],
  },
  {
    id: 'avg_ebitda_margin_3y',
    name: 'Avg Ebitda Margin (3Y)',
    category: 'Quality Scores',
    shortDesc: '3-year average of Ebitda Margin',
    definition: 'The simple average of Ebitda Margin over the last 3 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Ebitda Margin over 3 years',
    interpretation: 'A high, stable 3-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'ebitda margin of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['ebitda', 'quality', 'average'],
  },
  {
    id: 'avg_ebitda_margin_5y',
    name: 'Avg Ebitda Margin (5Y)',
    category: 'Quality Scores',
    shortDesc: '5-year average of Ebitda Margin',
    definition: 'The simple average of Ebitda Margin over the last 5 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Ebitda Margin over 5 years',
    interpretation: 'A high, stable 5-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'ebitda margin of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['ebitda', 'quality', 'average'],
  },
  {
    id: 'avg_eps_growth_3y',
    name: 'Avg Eps Growth (3Y)',
    category: 'Quality Scores',
    shortDesc: '3-year average of Eps Growth',
    definition: 'The simple average of Eps Growth over the last 3 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Eps Growth over 3 years',
    interpretation: 'A high, stable 3-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'eps growth of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['eps', 'quality', 'average'],
  },
  {
    id: 'avg_eps_growth_5y',
    name: 'Avg Eps Growth (5Y)',
    category: 'Quality Scores',
    shortDesc: '5-year average of Eps Growth',
    definition: 'The simple average of Eps Growth over the last 5 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Eps Growth over 5 years',
    interpretation: 'A high, stable 5-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'eps growth of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['eps', 'quality', 'average'],
  },
  {
    id: 'avg_gross_margin_3y',
    name: 'Avg Gross Margin (3Y)',
    category: 'Quality Scores',
    shortDesc: '3-year average of Gross Margin',
    definition: 'The simple average of Gross Margin over the last 3 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Gross Margin over 3 years',
    interpretation: 'A high, stable 3-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'gross margin of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['gross', 'quality', 'average'],
  },
  {
    id: 'avg_gross_margin_5y',
    name: 'Avg Gross Margin (5Y)',
    category: 'Quality Scores',
    shortDesc: '5-year average of Gross Margin',
    definition: 'The simple average of Gross Margin over the last 5 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Gross Margin over 5 years',
    interpretation: 'A high, stable 5-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'gross margin of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['gross', 'quality', 'average'],
  },
  {
    id: 'avg_net_margin_3y',
    name: 'Avg Net Margin (3Y)',
    category: 'Quality Scores',
    shortDesc: '3-year average of Net Margin',
    definition: 'The simple average of Net Margin over the last 3 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Net Margin over 3 years',
    interpretation: 'A high, stable 3-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'net margin of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net', 'quality', 'average'],
  },
  {
    id: 'avg_net_margin_5y',
    name: 'Avg Net Margin (5Y)',
    category: 'Quality Scores',
    shortDesc: '5-year average of Net Margin',
    definition: 'The simple average of Net Margin over the last 5 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Net Margin over 5 years',
    interpretation: 'A high, stable 5-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'net margin of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net', 'quality', 'average'],
  },
  {
    id: 'avg_operating_margin_3y',
    name: 'Avg Operating Margin (3Y)',
    category: 'Quality Scores',
    shortDesc: '3-year average of Operating Margin',
    definition: 'The simple average of Operating Margin over the last 3 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Operating Margin over 3 years',
    interpretation: 'A high, stable 3-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'operating margin of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['operating', 'quality', 'average'],
  },
  {
    id: 'avg_operating_margin_5y',
    name: 'Avg Operating Margin (5Y)',
    category: 'Quality Scores',
    shortDesc: '5-year average of Operating Margin',
    definition: 'The simple average of Operating Margin over the last 5 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual Operating Margin over 5 years',
    interpretation: 'A high, stable 5-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'operating margin of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['operating', 'quality', 'average'],
  },
  {
    id: 'avg_roa_3y',
    name: 'Avg ROA (3Y)',
    category: 'Quality Scores',
    shortDesc: '3-year average of ROA',
    definition: 'The simple average of ROA over the last 3 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual ROA over 3 years',
    interpretation: 'A high, stable 3-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'ROA of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['roa', 'quality', 'average'],
  },
  {
    id: 'avg_roa_5y',
    name: 'Avg ROA (5Y)',
    category: 'Quality Scores',
    shortDesc: '5-year average of ROA',
    definition: 'The simple average of ROA over the last 5 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual ROA over 5 years',
    interpretation: 'A high, stable 5-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'ROA of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['roa', 'quality', 'average'],
  },
  {
    id: 'avg_roce_3y',
    name: 'Avg ROCE (3Y)',
    category: 'Quality Scores',
    shortDesc: '3-year average of ROCE',
    definition: 'The simple average of ROCE over the last 3 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual ROCE over 3 years',
    interpretation: 'A high, stable 3-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'ROCE of 14%, 18% and 13% over three years → 3-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['roce', 'quality', 'average'],
  },
  {
    id: 'avg_roce_5y',
    name: 'Avg ROCE (5Y)',
    category: 'Quality Scores',
    shortDesc: '5-year average of ROCE',
    definition: 'The simple average of ROCE over the last 5 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual ROCE over 5 years',
    interpretation: 'A high, stable 5-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'ROCE of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['roce', 'quality', 'average'],
  },
  {
    id: 'avg_roe_5y',
    name: 'Avg ROE (5Y)',
    category: 'Quality Scores',
    shortDesc: '5-year average of ROE',
    definition: 'The simple average of ROE over the last 5 years. Averaging smooths out one-off good or bad years to reveal the underlying, durable level.',
    formula: 'Average of annual ROE over 5 years',
    interpretation: 'A high, stable 5-year average signals durable quality — more reliable than a single year\'s figure.',
    example: 'ROE of 14%, 18%, 12%, 16% and 15% over five years → 5-year average = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['roe', 'quality', 'average'],
  },
  {
    id: 'bb_pct',
    name: 'Bollinger %B',
    category: 'Technical Indicators',
    shortDesc: 'Position within the Bollinger Bands',
    definition: 'Where the price sits within its Bollinger Bands — 0 = lower band, 1 = upper band, 0.5 = the midline.',
    formula: '%B = (Price − Lower Band) ÷ (Upper Band − Lower Band)',
    interpretation: '>1 = above the upper band (overbought); <0 = below the lower band (oversold).',
    example: 'Price $52 with bands at $48 (lower) and $56 (upper) → %B = (52 − 48) ÷ (56 − 48) = 0.50 (mid-band).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['technical', 'volatility', 'bollinger'],
  },
  {
    id: 'bb_width',
    name: 'Bollinger Band Width',
    category: 'Technical Indicators',
    shortDesc: 'How wide the Bollinger Bands are',
    definition: 'The distance between the upper and lower Bollinger Bands relative to price — a volatility gauge. Narrow bands (\'squeeze\') often precede big moves.',
    formula: 'BB Width = (Upper − Lower) ÷ Middle Band',
    interpretation: 'Low width = low volatility / coiling; high width = high volatility.',
    example: 'Bands at $48–$56 around a $52 midline → width = (56 − 48) ÷ 52 = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['technical', 'volatility', 'bollinger'],
  },
  {
    id: 'bvps_cagr_3y',
    name: 'Book Value per Share CAGR (3Y)',
    category: 'Growth',
    shortDesc: 'Compound annual book value per share growth over 3 years',
    definition: 'The compound annual growth rate (CAGR) of book value per share over the past 3 years — the smoothed yearly rate that compounds book value per share from 3 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Book Value per Share now / Book Value per Share 3Y ago)^(1/3) − 1',
    interpretation: '>10% is strong, >15% exceptional over 3 years. Smooths out volatile single years.',
    example: 'Book value per share of $100M 3 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/3) − 1 = 26% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['bvps', 'growth', 'cagr'],
  },
  {
    id: 'bvps_cagr_5y',
    name: 'Book Value per Share CAGR (5Y)',
    category: 'Growth',
    shortDesc: 'Compound annual book value per share growth over 5 years',
    definition: 'The compound annual growth rate (CAGR) of book value per share over the past 5 years — the smoothed yearly rate that compounds book value per share from 5 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Book Value per Share now / Book Value per Share 5Y ago)^(1/5) − 1',
    interpretation: '>10% is strong, >15% exceptional over 5 years. Smooths out volatile single years.',
    example: 'Book value per share of $100M 5 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/5) − 1 = 14.9% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['bvps', 'growth', 'cagr'],
  },
  {
    id: 'capex_intensity',
    name: 'Capex Intensity',
    category: 'Profitability',
    shortDesc: 'Capital spending as a percent of revenue',
    definition: 'How much of revenue is reinvested in property, plant and equipment. Low capex intensity = an asset-light, cash-generative model.',
    formula: 'Capex Intensity = Capex ÷ Revenue',
    interpretation: 'Utilities/miners run high (15%+); software runs low (<5%). High intensity isn\'t bad if returns on that capex are strong.',
    example: 'Capex $150M on revenue $1,000M → 15% capex intensity (typical of a capital-heavy utility).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['capex', 'capital', 'asset intensity'],
  },
  {
    id: 'capex_to_revenue',
    name: 'Capex / Revenue',
    category: 'Profitability',
    shortDesc: 'Capital expenditure relative to sales',
    definition: 'Capital expenditure as a fraction of revenue — the same idea as capex intensity, useful for spotting reinvestment-heavy businesses.',
    formula: 'Capex ÷ Revenue',
    interpretation: 'Persistently high capex/revenue with weak FCF is a red flag for capital-hungry, low-return businesses.',
    example: 'Capex $90M on revenue $1,000M → 9%. Compare to operating cash flow to see what\'s left as free cash flow.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['capex', 'revenue'],
  },
  {
    id: 'capital_efficiency_score',
    name: 'Capital Efficiency Score',
    category: 'Quality Scores',
    shortDesc: 'Composite of returns-on-capital quality',
    definition: 'A proprietary 0–100 score blending ROE, ROIC, ROCE and their stability — a quick read on how well a company turns capital into profit.',
    interpretation: 'Higher = more capital-efficient. Useful as a quality screen alongside Piotroski and Altman.',
    example: 'A company with ROE 22%, ROIC 18% and ROCE 20%, all stable for 5 years, scores in the top decile (~90/100).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['quality', 'score', 'capital'],
  },
  {
    id: 'capital_employed',
    name: 'Capital Employed',
    category: 'Financial Health',
    shortDesc: 'Total long-term capital in the business',
    definition: 'The total capital funding the business — equity plus debt. The denominator for Return on Capital Employed (ROCE).',
    formula: 'Capital Employed = Total Equity + Total Debt',
    interpretation: 'ROCE = EBIT ÷ Capital Employed. Growing capital employed only creates value if ROCE exceeds the cost of capital.',
    example: 'Equity $600M + total debt $250M = $850M capital employed; with EBIT $180M, ROCE = 180÷850 = 21%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['capital', 'balance sheet'],
  },
  {
    id: 'cash_per_share',
    name: 'Cash per Share',
    category: 'Financial Health',
    shortDesc: 'Cash divided by shares outstanding',
    definition: 'Cash expressed on a per-share basis, so it can be compared directly to the share price.',
    formula: 'Cash per Share = Cash ÷ Shares Outstanding',
    interpretation: 'Compare to price: e.g. cash/share near the share price flags a cash-rich stock; tangible book/share is a conservative floor value.',
    example: 'Cash of $250M ÷ 500M shares outstanding = $0.50 per share.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['cash', 'per share'],
  },
  {
    id: 'cash_ratio',
    name: 'Cash Ratio',
    category: 'Financial Health',
    shortDesc: 'The strictest liquidity test',
    definition: 'The cash ratio measures whether cash alone covers current liabilities — the most conservative liquidity check.',
    formula: 'Cash Ratio = Cash & Equivalents ÷ Current Liabilities',
    interpretation: '>0.5 is very strong; most healthy firms sit 0.1–0.4. Very high can mean idle cash.',
    example: 'Cash $90M ÷ current liabilities $300M → cash ratio 0.30×.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['liquidity', 'cash', 'solvency'],
  },
  {
    id: 'cfi',
    name: 'Investing Cash Flow',
    category: 'Financial Health',
    shortDesc: 'Cash used in/from investing activities',
    definition: 'Net cash spent on (or received from) investments — capex, acquisitions, asset sales. Usually negative for growing companies that are reinvesting.',
    interpretation: 'Large negative CFI funded by operating cash flow = healthy reinvestment; funded by debt/equity = watch.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['cash flow', 'investing'],
  },
  {
    id: 'cogs',
    name: 'Cost of Goods Sold (COGS)',
    category: 'Financial Health',
    shortDesc: 'Direct cost of producing what the company sells',
    definition: 'COGS is the direct cost of the goods or services a company sold — materials, direct labour and production costs. Revenue minus COGS equals gross profit.',
    formula: 'Gross Profit = Revenue − COGS',
    interpretation: 'Lower COGS relative to revenue means higher gross margin and stronger pricing power.',
    example: 'Revenue $1,000M with COGS of $600M → gross profit $400M = a 40% gross margin.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['cost', 'income statement'],
  },
  {
    id: 'days_inventory_outstanding',
    name: 'Days Inventory Outstanding (DIO)',
    category: 'Profitability',
    shortDesc: 'Average days inventory is held before sale',
    definition: 'DIO measures how many days stock sits before being sold. Lower means leaner inventory and less cash tied up.',
    formula: 'DIO = Inventory ÷ COGS × 365',
    interpretation: 'Rising DIO can mean slowing demand or obsolescence risk. Retailers and manufacturers watch this closely.',
    example: 'Inventory $50M on COGS $365M → DIO = 50 ÷ 365 × 365 = 50 days of stock on hand.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['working capital', 'inventory', 'efficiency'],
  },
  {
    id: 'days_sales_outstanding',
    name: 'Days Sales Outstanding (DSO)',
    category: 'Profitability',
    shortDesc: 'Average days to collect customer payments',
    definition: 'DSO measures how many days, on average, it takes to collect cash from credit sales. Lower is better — cash arrives faster.',
    formula: 'DSO = Trade Receivables ÷ Revenue × 365',
    interpretation: 'Rising DSO can signal collection problems or channel stuffing. Compare to industry norms.',
    example: 'Trade receivables $80M on revenue $730M → DSO = 80 ÷ 730 × 365 = 40 days to collect.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['working capital', 'receivables', 'efficiency'],
  },
  {
    id: 'death_cross',
    name: 'Death Cross',
    category: 'Technical Indicators',
    shortDesc: 'True when: Death Cross',
    definition: 'A yes/no flag — true when the stock meets the condition \'Death Cross\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'debt_to_assets',
    name: 'Debt / Assets',
    category: 'Financial Health',
    shortDesc: 'Total debt as a share of assets',
    definition: 'How much of the asset base is funded by interest-bearing debt. A direct leverage gauge.',
    formula: 'Debt ÷ Total Assets',
    interpretation: 'Lower is safer; compare to sector norms (utilities carry more debt than tech).',
    example: 'Total debt $300M ÷ total assets $1,000M → 0.30 (30% of assets funded by debt).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['leverage', 'debt'],
  },
  {
    id: 'depreciation',
    name: 'Depreciation & Amortisation',
    category: 'Financial Health',
    shortDesc: 'Non-cash expense spreading asset costs over time',
    definition: 'Depreciation (tangible assets) and amortisation (intangibles) spread the cost of long-lived assets across their useful lives. It is a non-cash expense added back in cash-flow analysis.',
    formula: 'Annual D&A charge from the income statement',
    interpretation: 'High D&A relative to capex can flatter cash flow; compare to maintenance capex.',
    example: 'A miner with $3,000M of PP&E and a 10-year asset life books roughly $300M of depreciation a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['non-cash', 'expense'],
  },
  {
    id: 'dividend_cagr_5y',
    name: 'Dividend CAGR (5Y)',
    category: 'Dividends & Income',
    shortDesc: 'Compound annual dividend growth over 5 years',
    definition: 'The smoothed yearly growth rate of dividends per share over five years. A core metric for income and dividend-growth investors.',
    formula: 'CAGR = (DPS_now / DPS_5y_ago)^(1/5) − 1',
    interpretation: '>5% sustained dividend growth signals a healthy, growing payout. Pair with payout ratio for sustainability.',
    example: 'Dividends per share grew from $0.40 to $0.60 over 5 years → CAGR = (0.60 ÷ 0.40)^(1/5) − 1 = 8.4% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['dividends', 'growth', 'income'],
  },
  {
    id: 'dividends_paid',
    name: 'Dividends Paid',
    category: 'Financial Health',
    shortDesc: 'Total cash dividends paid to shareholders',
    definition: 'The cash paid out to shareholders as dividends during the year. Compared to free cash flow to judge sustainability.',
    interpretation: 'Dividends paid should be well covered by free cash flow — paying dividends from debt is unsustainable.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['dividends', 'cash flow'],
  },
  {
    id: 'dma200_ratio',
    name: 'Price / 200-Day MA',
    category: 'Technical Indicators',
    shortDesc: 'Price relative to its 200-day average',
    definition: 'The current price divided by its 200-day moving average — the classic long-term trend filter.',
    formula: 'Price ÷ SMA(200)',
    interpretation: 'Above the 200-day = long-term uptrend (bullish bias); below = downtrend.',
    example: 'Price $21.00 ÷ 200-day moving average $24.00 = 0.875 — below the long-term trend (bearish bias).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['technical', 'trend', 'moving average'],
  },
  {
    id: 'dma50_ratio',
    name: 'Price / 50-Day MA',
    category: 'Technical Indicators',
    shortDesc: 'Price relative to its 50-day average',
    definition: 'The current price divided by its 50-day simple moving average. Above 1.0 = trading above the medium-term trend.',
    formula: 'Price ÷ SMA(50)',
    interpretation: '>1 = short/medium-term uptrend; <1 = below trend. Crossovers are common trade triggers.',
    example: 'Price $21.00 ÷ 50-day moving average $20.00 = 1.05 — trading 5% above its medium-term trend.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['technical', 'trend', 'moving average'],
  },
  {
    id: 'dollar_volume_avg_20d',
    name: 'Avg Dollar Volume (20D)',
    category: 'Price & Returns',
    shortDesc: 'Average daily value traded over 20 days',
    definition: 'The average dollar value of shares traded per day over the last 20 sessions — a liquidity measure. Higher means easier to buy/sell without moving the price.',
    formula: 'Avg Dollar Volume = Avg Daily Volume × Price',
    interpretation: 'Low dollar volume (e.g. <$100k/day) means thin liquidity and wide spreads — risky for larger positions.',
    example: '200,000 shares trade per day at $5.00 → average daily dollar volume = $1.0M (thin — large orders would move the price).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['liquidity', 'volume'],
  },
  {
    id: 'earnings_stability_score',
    name: 'Earnings Stability Score',
    category: 'Quality Scores',
    shortDesc: 'How consistent earnings have been',
    definition: 'A proprietary score rewarding companies with steady, predictable earnings and penalising volatile or erratic profit histories.',
    interpretation: 'Higher = more reliable earnings — favoured by conservative/income investors.',
    example: 'A utility with net profit of $98M, $101M, $99M, $103M, $100M over 5 years scores very high; a miner swinging from −$50M to $400M scores low.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['quality', 'score', 'earnings'],
  },
  {
    id: 'earnings_yield',
    name: 'Earnings Yield',
    category: 'Valuation',
    shortDesc: 'Earnings Yield %',
    definition: 'Earnings Yield % for the stock.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['valuation'],
  },
  {
    id: 'ebit',
    name: 'EBIT (Operating Profit)',
    category: 'Financial Health',
    shortDesc: 'Earnings before interest and tax — core operating profit',
    definition: 'EBIT is profit from operations before financing costs and tax are deducted. It measures how much the underlying business earns from trading, independent of how it is financed or taxed.',
    formula: 'EBIT = Revenue − Operating Expenses (incl. depreciation)',
    interpretation: 'Higher EBIT margin = a more profitable core business. EBIT is the numerator for interest coverage and EV/EBIT.',
    example: 'Revenue $1,000M − operating costs (incl. depreciation) $820M = EBIT $180M, an 18% EBIT margin.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['profit', 'operating', 'earnings'],
  },
  {
    id: 'ebitda_cagr_3y',
    name: 'EBITDA CAGR (3Y)',
    category: 'Growth',
    shortDesc: 'Compound annual ebitda growth over 3 years',
    definition: 'The compound annual growth rate (CAGR) of ebitda over the past 3 years — the smoothed yearly rate that compounds ebitda from 3 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (EBITDA now / EBITDA 3Y ago)^(1/3) − 1',
    interpretation: '>10% is strong, >15% exceptional over 3 years. Smooths out volatile single years.',
    example: 'EBITDA of $100M 3 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/3) − 1 = 26% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['ebitda', 'growth', 'cagr'],
  },
  {
    id: 'ebitda_cagr_5y',
    name: 'EBITDA CAGR (5Y)',
    category: 'Growth',
    shortDesc: 'Compound annual ebitda growth over 5 years',
    definition: 'The compound annual growth rate (CAGR) of ebitda over the past 5 years — the smoothed yearly rate that compounds ebitda from 5 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (EBITDA now / EBITDA 5Y ago)^(1/5) − 1',
    interpretation: '>10% is strong, >15% exceptional over 5 years. Smooths out volatile single years.',
    example: 'EBITDA of $100M 5 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/5) − 1 = 14.9% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['ebitda', 'growth', 'cagr'],
  },
  {
    id: 'ebitda_growth_1y',
    name: 'EBITDA Growth',
    category: 'Growth',
    shortDesc: 'Year-on-year ebitda growth in the latest year',
    definition: 'The percentage change in ebitda in the latest year versus the year before. A single-year growth read (use the CAGRs for multi-year trends).',
    formula: 'Growth = (EBITDA this year − EBITDA prior) ÷ |EBITDA prior|',
    interpretation: 'Positive and accelerating is best. One strong year can be a base effect — confirm with the multi-year CAGR.',
    example: 'EBITDA rising from $80M to $96M → growth = (96 − 80) ÷ 80 = +20% (same maths in dollars or per-share).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['ebitda', 'growth'],
  },
  {
    id: 'ebitda_interest_coverage',
    name: 'EBITDA Interest Coverage',
    category: 'Financial Health',
    shortDesc: 'How many times EBITDA covers interest',
    definition: 'How comfortably operating cash earnings (EBITDA) cover interest payments. A core solvency metric for lenders.',
    formula: 'EBITDA Interest Coverage = EBITDA ÷ Interest Expense',
    interpretation: '>3× is comfortable; <1.5× is stressed and risky.',
    example: 'EBITDA $250M ÷ interest expense $50M = 5× — comfortably covers interest.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['solvency', 'debt', 'coverage'],
  },
  {
    id: 'eps_fy0',
    name: 'EPS FY0 (AUD)',
    category: 'Profitability',
    shortDesc: 'EPS FY0 (AUD)',
    definition: 'EPS FY0 (AUD) for the stock.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['profitability'],
  },
  {
    id: 'eps_fy1',
    name: 'EPS FY1 Est (AUD)',
    category: 'Profitability',
    shortDesc: 'EPS FY1 Est (AUD)',
    definition: 'EPS FY1 Est (AUD) for the stock.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['profitability'],
  },
  {
    id: 'eps_growth_1y',
    name: 'EPS Growth',
    category: 'Growth',
    shortDesc: 'Year-on-year eps growth in the latest year',
    definition: 'The percentage change in eps in the latest year versus the year before. A single-year growth read (use the CAGRs for multi-year trends).',
    formula: 'Growth = (EPS this year − EPS prior) ÷ |EPS prior|',
    interpretation: 'Positive and accelerating is best. One strong year can be a base effect — confirm with the multi-year CAGR.',
    example: 'EPS rising from $0.80 to $0.96 → growth = (96 − 80) ÷ 80 = +20% (same maths in dollars or per-share).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['eps', 'growth'],
  },
  {
    id: 'equity_ratio',
    name: 'Equity Ratio',
    category: 'Financial Health',
    shortDesc: 'Share of assets funded by equity',
    definition: 'The proportion of total assets financed by shareholders rather than debt. Higher = a more conservatively financed balance sheet.',
    formula: 'Equity Ratio = Total Equity ÷ Total Assets',
    interpretation: '>50% is conservative; <30% means heavy reliance on debt/liabilities.',
    example: 'Total equity $600M ÷ total assets $1,000M → equity ratio 0.60 (60% funded by shareholders).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['leverage', 'balance sheet', 'solvency'],
  },
  {
    id: 'fcf_cagr_3y',
    name: 'Free Cash Flow CAGR (3Y)',
    category: 'Growth',
    shortDesc: 'Compound annual free cash flow growth over 3 years',
    definition: 'The compound annual growth rate (CAGR) of free cash flow over the past 3 years — the smoothed yearly rate that compounds free cash flow from 3 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Free Cash Flow now / Free Cash Flow 3Y ago)^(1/3) − 1',
    interpretation: '>10% is strong, >15% exceptional over 3 years. Smooths out volatile single years.',
    example: 'Free cash flow of $100M 3 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/3) − 1 = 26% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['fcf', 'growth', 'cagr'],
  },
  {
    id: 'fcf_cagr_5y',
    name: 'Free Cash Flow CAGR (5Y)',
    category: 'Growth',
    shortDesc: 'Compound annual free cash flow growth over 5 years',
    definition: 'The compound annual growth rate (CAGR) of free cash flow over the past 5 years — the smoothed yearly rate that compounds free cash flow from 5 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Free Cash Flow now / Free Cash Flow 5Y ago)^(1/5) − 1',
    interpretation: '>10% is strong, >15% exceptional over 5 years. Smooths out volatile single years.',
    example: 'Free cash flow of $100M 5 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/5) − 1 = 14.9% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['fcf', 'growth', 'cagr'],
  },
  {
    id: 'fcf_growth_1y',
    name: 'Free Cash Flow Growth',
    category: 'Growth',
    shortDesc: 'Year-on-year free cash flow growth in the latest year',
    definition: 'The percentage change in free cash flow in the latest year versus the year before. A single-year growth read (use the CAGRs for multi-year trends).',
    formula: 'Growth = (Free Cash Flow this year − Free Cash Flow prior) ÷ |Free Cash Flow prior|',
    interpretation: 'Positive and accelerating is best. One strong year can be a base effect — confirm with the multi-year CAGR.',
    example: 'Free cash flow rising from $80M to $96M → growth = (96 − 80) ÷ 80 = +20% (same maths in dollars or per-share).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['fcf', 'growth'],
  },
  {
    id: 'fcf_margin',
    name: 'Free Cash Flow Margin',
    category: 'Profitability',
    shortDesc: 'Free cash flow per dollar of sales',
    definition: 'The percent of revenue left as free cash flow after capex. The ultimate measure of how cash-generative a business is.',
    formula: 'FCF Margin = Free Cash Flow ÷ Revenue',
    interpretation: '>10% is excellent; negative means the business consumes cash to grow.',
    example: 'Free cash flow $130M on revenue $1,000M → FCF margin = 13% — very cash-generative.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['cash flow', 'margin', 'fcf'],
  },
  {
    id: 'fcf_per_share',
    name: 'Free Cash Flow per Share',
    category: 'Financial Health',
    shortDesc: 'Free Cash Flow divided by shares outstanding',
    definition: 'Free Cash Flow expressed on a per-share basis, so it can be compared directly to the share price.',
    formula: 'Free Cash Flow per Share = Free Cash Flow ÷ Shares Outstanding',
    interpretation: 'Compare to price: e.g. cash/share near the share price flags a cash-rich stock; tangible book/share is a conservative floor value.',
    example: 'Free cash flow of $250M ÷ 500M shares outstanding = $0.50 per share.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['fcf', 'per share'],
  },
  {
    id: 'fixed_asset_turnover',
    name: 'Fixed Asset Turnover',
    category: 'Profitability',
    shortDesc: 'Revenue generated per dollar of PP&E',
    definition: 'How efficiently the company uses its property, plant and equipment to generate sales. Higher = more revenue squeezed from each dollar of fixed assets.',
    formula: 'Fixed Asset Turnover = Revenue ÷ Net PP&E',
    interpretation: 'Asset-light businesses run high; capital-intensive miners/utilities run low. Compare within sector.',
    example: 'Revenue $900M ÷ net PP&E $600M = 1.5× of sales per dollar of fixed assets.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['efficiency', 'assets', 'turnover'],
  },
  {
    id: 'golden_cross',
    name: 'Golden Cross',
    category: 'Technical Indicators',
    shortDesc: 'True when: Golden Cross',
    definition: 'A yes/no flag — true when the stock meets the condition \'Golden Cross\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'goodwill',
    name: 'Goodwill',
    category: 'Financial Health',
    shortDesc: 'Premium paid over net assets in acquisitions',
    definition: 'The excess an acquirer paid over the fair value of acquired net assets. Large goodwill raises impairment risk if acquisitions underperform.',
    interpretation: 'High goodwill relative to equity is a quality flag — watch for write-downs. Subtract it for tangible book value.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'acquisitions', 'intangible'],
  },
  {
    id: 'gross_profit_fy0',
    name: 'Gross Profit (Most Recent Year)',
    category: 'Financial Health',
    shortDesc: 'Gross Profit from the most recent fiscal year',
    definition: 'The company\'s gross profit from the most recent fiscal year. Part of the multi-year gross profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether gross profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['gross profit', 'history', 'income statement'],
  },
  {
    id: 'gross_profit_fy1',
    name: 'Gross Profit (Last Year)',
    category: 'Financial Health',
    shortDesc: 'Gross Profit from last year',
    definition: 'The company\'s gross profit from last year. Part of the multi-year gross profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether gross profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['gross profit', 'history', 'income statement'],
  },
  {
    id: 'gross_profit_fy10',
    name: 'Gross Profit (10 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Gross Profit from 10 years ago',
    definition: 'The company\'s gross profit from 10 years ago. Part of the multi-year gross profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether gross profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['gross profit', 'history', 'income statement'],
  },
  {
    id: 'gross_profit_fy3',
    name: 'Gross Profit (3 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Gross Profit from 3 years ago',
    definition: 'The company\'s gross profit from 3 years ago. Part of the multi-year gross profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether gross profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['gross profit', 'history', 'income statement'],
  },
  {
    id: 'gross_profit_fy5',
    name: 'Gross Profit (5 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Gross Profit from 5 years ago',
    definition: 'The company\'s gross profit from 5 years ago. Part of the multi-year gross profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether gross profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['gross profit', 'history', 'income statement'],
  },
  {
    id: 'gross_profit_fy7',
    name: 'Gross Profit (7 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Gross Profit from 7 years ago',
    definition: 'The company\'s gross profit from 7 years ago. Part of the multi-year gross profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether gross profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['gross profit', 'history', 'income statement'],
  },
  {
    id: 'income_tax_expense',
    name: 'Income Tax Expense',
    category: 'Financial Health',
    shortDesc: 'Corporate tax charged against profit',
    definition: 'The income tax charged on pre-tax profit for the year. Pre-tax profit minus tax equals net profit.',
    formula: 'Effective tax rate = Income Tax ÷ Pre-tax Profit',
    interpretation: 'Australian company tax is ~30%. A much lower effective rate may signal tax assets, offshore earnings or one-offs.',
    example: 'Pre-tax profit $200M with tax expense $60M → an effective tax rate of 30% (Australia\'s company rate).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['tax', 'income statement'],
  },
  {
    id: 'industry',
    name: 'Industry',
    category: 'ASX-Specific',
    shortDesc: 'The stock\'s industry',
    definition: 'The industry classification for the stock. Filter or group by it in screens (e.g. only Materials, or exclude Financials).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['classification', 'industry'],
  },
  {
    id: 'intangibles',
    name: 'Intangible Assets',
    category: 'Financial Health',
    shortDesc: 'Non-physical assets (patents, brands, software)',
    definition: 'Assets without physical form — patents, trademarks, capitalised software, customer lists. Value can be real but is harder to verify than tangible assets.',
    interpretation: 'Subtract goodwill + intangibles from equity for tangible book value — a conservative net-asset measure.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'intangible'],
  },
  {
    id: 'interest_coverage',
    name: 'Interest Coverage',
    category: 'Financial Health',
    shortDesc: 'How many times EBIT covers interest',
    definition: 'How many times operating profit (EBIT) covers the interest bill. Below ~1.5× the company struggles to service its debt.',
    formula: 'Interest Coverage = EBIT ÷ Interest Expense',
    interpretation: '>3× safe, 1.5–3× watch, <1.5× distress risk.',
    example: 'EBIT $180M ÷ interest expense $50M = 3.6× — a safe cushion.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['solvency', 'debt', 'coverage'],
  },
  {
    id: 'interest_expense',
    name: 'Interest Expense',
    category: 'Financial Health',
    shortDesc: 'Cost of the company\'s debt',
    definition: 'The interest paid on borrowings during the year. Used with EBIT/EBITDA to compute interest coverage — a key solvency check.',
    formula: 'Interest Coverage = EBIT ÷ Interest Expense',
    interpretation: 'Rising interest expense with flat EBIT squeezes coverage and raises financial risk.',
    example: '$500M of debt at a 5% average rate → interest expense ≈ $25M; with EBIT $180M, coverage = 180÷25 = 7.2×.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['debt', 'interest', 'finance cost'],
  },
  {
    id: 'inventory',
    name: 'Inventory',
    category: 'Financial Health',
    shortDesc: 'Value of unsold stock',
    definition: 'The cost of goods held for sale or in production. Excluded from the quick ratio because it can be slow to convert to cash.',
    interpretation: 'Rising inventory faster than sales can signal weakening demand. Used in DIO and inventory turnover.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'working capital'],
  },
  {
    id: 'is_asx100',
    name: 'In ASX 100',
    category: 'ASX-Specific',
    shortDesc: 'True when: In ASX 100',
    definition: 'A yes/no flag — true when the stock meets the condition \'In ASX 100\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'asx-specific'],
  },
  {
    id: 'is_asx20',
    name: 'In ASX 20',
    category: 'ASX-Specific',
    shortDesc: 'True when: In ASX 20',
    definition: 'A yes/no flag — true when the stock meets the condition \'In ASX 20\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'asx-specific'],
  },
  {
    id: 'is_asx200',
    name: 'In ASX 200',
    category: 'ASX-Specific',
    shortDesc: 'True when: In ASX 200',
    definition: 'A yes/no flag — true when the stock meets the condition \'In ASX 200\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'asx-specific'],
  },
  {
    id: 'is_asx300',
    name: 'In ASX 300',
    category: 'ASX-Specific',
    shortDesc: 'True when: In ASX 300',
    definition: 'A yes/no flag — true when the stock meets the condition \'In ASX 300\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'asx-specific'],
  },
  {
    id: 'is_asx50',
    name: 'In ASX 50',
    category: 'ASX-Specific',
    shortDesc: 'True when: In ASX 50',
    definition: 'A yes/no flag — true when the stock meets the condition \'In ASX 50\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'asx-specific'],
  },
  {
    id: 'is_miner',
    name: 'Is Miner',
    category: 'ASX-Specific',
    shortDesc: 'True when: Is Miner',
    definition: 'A yes/no flag — true when the stock meets the condition \'Is Miner\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'asx-specific'],
  },
  {
    id: 'is_reit',
    name: 'Is REIT',
    category: 'ASX-Specific',
    shortDesc: 'True when: Is REIT',
    definition: 'A yes/no flag — true when the stock meets the condition \'Is REIT\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'asx-specific'],
  },
  {
    id: 'liabilities_to_assets',
    name: 'Liabilities / Assets',
    category: 'Financial Health',
    shortDesc: 'Share of assets funded by liabilities',
    definition: 'The fraction of total assets financed by liabilities (debt + payables + provisions). The mirror image of the equity ratio.',
    formula: 'Liabilities ÷ Total Assets',
    interpretation: 'Lower is safer. >70% signals a highly geared balance sheet.',
    example: 'Total liabilities $400M ÷ total assets $1,000M → 0.40 (40% funded by liabilities).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['leverage', 'balance sheet'],
  },
  {
    id: 'long_term_debt',
    name: 'Long-term Debt',
    category: 'Financial Health',
    shortDesc: 'Borrowings due beyond 12 months',
    definition: 'Debt with maturities greater than one year. The core of structural leverage and refinancing risk.',
    interpretation: 'Compare to EBITDA and equity. A wall of near-term maturities is a refinancing risk in rising-rate environments.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['debt', 'balance sheet'],
  },
  {
    id: 'lt_debt_to_capital',
    name: 'Long-term Debt / Capital',
    category: 'Financial Health',
    shortDesc: 'Long-term debt in the capital structure',
    definition: 'The share of permanent capital (debt + equity) made up of long-term debt. Shows structural leverage.',
    formula: 'LT Debt ÷ (LT Debt + Equity)',
    interpretation: '<0.4 is conservative; >0.6 is aggressively geared.',
    example: 'Long-term debt $200M ÷ (debt $200M + equity $600M) = 0.25 — conservatively geared.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['leverage', 'debt', 'capital structure'],
  },
  {
    id: 'macd_bearish_cross',
    name: 'MACD Bearish Cross',
    category: 'Technical Indicators',
    shortDesc: 'True when: MACD Bearish Cross',
    definition: 'A yes/no flag — true when the stock meets the condition \'MACD Bearish Cross\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'macd_bullish_cross',
    name: 'MACD Bullish Cross',
    category: 'Technical Indicators',
    shortDesc: 'True when: MACD Bullish Cross',
    definition: 'A yes/no flag — true when the stock meets the condition \'MACD Bullish Cross\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'net_debt',
    name: 'Net Debt',
    category: 'Financial Health',
    shortDesc: 'Total debt minus cash',
    definition: 'Debt remaining after using available cash to pay it down. The truest measure of leverage; negative net debt means net cash.',
    formula: 'Net Debt = Total Debt − Cash & Equivalents',
    interpretation: 'Net Debt ÷ EBITDA is the key gearing ratio — <2× comfortable, >4× stretched.',
    example: 'Total debt $300M − cash $90M = net debt $210M; at EBITDA $250M, net debt/EBITDA = 0.8× (low leverage).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['debt', 'balance sheet', 'leverage'],
  },
  {
    id: 'net_income_cagr_5y',
    name: 'Net Income CAGR (5Y)',
    category: 'Growth',
    shortDesc: 'Compound annual net income growth over 5 years',
    definition: 'The compound annual growth rate (CAGR) of net income over the past 5 years — the smoothed yearly rate that compounds net income from 5 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Net Income now / Net Income 5Y ago)^(1/5) − 1',
    interpretation: '>10% is strong, >15% exceptional over 5 years. Smooths out volatile single years.',
    example: 'Net income of $100M 5 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/5) − 1 = 14.9% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net income', 'growth', 'cagr'],
  },
  {
    id: 'net_profit_fy0',
    name: 'Net Profit (Most Recent Year)',
    category: 'Financial Health',
    shortDesc: 'Net Profit from the most recent fiscal year',
    definition: 'The company\'s net profit from the most recent fiscal year. Part of the multi-year net profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether net profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net profit', 'history', 'income statement'],
  },
  {
    id: 'net_profit_fy1',
    name: 'Net Profit (Last Year)',
    category: 'Financial Health',
    shortDesc: 'Net Profit from last year',
    definition: 'The company\'s net profit from last year. Part of the multi-year net profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether net profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net profit', 'history', 'income statement'],
  },
  {
    id: 'net_profit_fy10',
    name: 'Net Profit (10 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Net Profit from 10 years ago',
    definition: 'The company\'s net profit from 10 years ago. Part of the multi-year net profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether net profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net profit', 'history', 'income statement'],
  },
  {
    id: 'net_profit_fy3',
    name: 'Net Profit (3 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Net Profit from 3 years ago',
    definition: 'The company\'s net profit from 3 years ago. Part of the multi-year net profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether net profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net profit', 'history', 'income statement'],
  },
  {
    id: 'net_profit_fy5',
    name: 'Net Profit (5 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Net Profit from 5 years ago',
    definition: 'The company\'s net profit from 5 years ago. Part of the multi-year net profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether net profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net profit', 'history', 'income statement'],
  },
  {
    id: 'net_profit_fy7',
    name: 'Net Profit (7 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Net Profit from 7 years ago',
    definition: 'The company\'s net profit from 7 years ago. Part of the multi-year net profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether net profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['net profit', 'history', 'income statement'],
  },
  {
    id: 'new_52w_high',
    name: 'New 52W High',
    category: 'Technical Indicators',
    shortDesc: 'True when: New 52W High',
    definition: 'A yes/no flag — true when the stock meets the condition \'New 52W High\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'new_52w_low',
    name: 'New 52W Low',
    category: 'Technical Indicators',
    shortDesc: 'True when: New 52W Low',
    definition: 'A yes/no flag — true when the stock meets the condition \'New 52W Low\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'nopat',
    name: 'NOPAT',
    category: 'Profitability',
    shortDesc: 'Net operating profit after tax',
    definition: 'NOPAT is operating profit (EBIT) after deducting tax, but before financing effects. It is the clean profit the business generates for all capital providers, used in ROIC and economic-profit analysis.',
    formula: 'NOPAT = EBIT × (1 − effective tax rate)',
    interpretation: 'NOPAT ÷ Invested Capital = ROIC. Growing NOPAT with stable capital = genuine value creation.',
    example: 'EBIT $200M at a 30% effective tax rate → NOPAT = 200 × (1 − 0.30) = $140M.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['profit', 'roic', 'operating'],
  },
  {
    id: 'ocf_margin',
    name: 'Operating Cash Flow Margin',
    category: 'Profitability',
    shortDesc: 'Operating cash flow per dollar of sales',
    definition: 'The share of revenue that converts into operating cash flow. A high, stable OCF margin signals real, cash-backed earnings rather than accounting profit.',
    formula: 'OCF Margin = Operating Cash Flow ÷ Revenue',
    interpretation: 'Compare to net margin — OCF margin well below net margin can flag aggressive accounting or working-capital strain.',
    example: 'Operating cash flow $220M on revenue $1,000M → OCF margin = 22%. Above the 16% net margin = high-quality, cash-backed earnings.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['cash flow', 'margin', 'quality'],
  },
  {
    id: 'ocf_per_share',
    name: 'Operating Cash Flow per Share',
    category: 'Financial Health',
    shortDesc: 'Operating Cash Flow divided by shares outstanding',
    definition: 'Operating Cash Flow expressed on a per-share basis, so it can be compared directly to the share price.',
    formula: 'Operating Cash Flow per Share = Operating Cash Flow ÷ Shares Outstanding',
    interpretation: 'Compare to price: e.g. cash/share near the share price flags a cash-rich stock; tangible book/share is a conservative floor value.',
    example: 'Operating cash flow of $250M ÷ 500M shares outstanding = $0.50 per share.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['ocf', 'per share'],
  },
  {
    id: 'pbt_cagr_10y',
    name: 'Pre-tax Profit CAGR (10Y)',
    category: 'Growth',
    shortDesc: 'Compound annual pre-tax profit growth over 10 years',
    definition: 'The compound annual growth rate (CAGR) of pre-tax profit over the past 10 years — the smoothed yearly rate that compounds pre-tax profit from 10 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Pre-tax Profit now / Pre-tax Profit 10Y ago)^(1/10) − 1',
    interpretation: '>10% is strong, >15% exceptional over 10 years. Smooths out volatile single years.',
    example: 'Pre-tax profit of $100M 10 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/10) − 1 = 7.2% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'growth', 'cagr'],
  },
  {
    id: 'pbt_cagr_3y',
    name: 'Pre-tax Profit CAGR (3Y)',
    category: 'Growth',
    shortDesc: 'Compound annual pre-tax profit growth over 3 years',
    definition: 'The compound annual growth rate (CAGR) of pre-tax profit over the past 3 years — the smoothed yearly rate that compounds pre-tax profit from 3 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Pre-tax Profit now / Pre-tax Profit 3Y ago)^(1/3) − 1',
    interpretation: '>10% is strong, >15% exceptional over 3 years. Smooths out volatile single years.',
    example: 'Pre-tax profit of $100M 3 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/3) − 1 = 26% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'growth', 'cagr'],
  },
  {
    id: 'pbt_cagr_5y',
    name: 'Pre-tax Profit CAGR (5Y)',
    category: 'Growth',
    shortDesc: 'Compound annual pre-tax profit growth over 5 years',
    definition: 'The compound annual growth rate (CAGR) of pre-tax profit over the past 5 years — the smoothed yearly rate that compounds pre-tax profit from 5 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Pre-tax Profit now / Pre-tax Profit 5Y ago)^(1/5) − 1',
    interpretation: '>10% is strong, >15% exceptional over 5 years. Smooths out volatile single years.',
    example: 'Pre-tax profit of $100M 5 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/5) − 1 = 14.9% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'growth', 'cagr'],
  },
  {
    id: 'pbt_cagr_7y',
    name: 'Pre-tax Profit CAGR (7Y)',
    category: 'Growth',
    shortDesc: 'Compound annual pre-tax profit growth over 7 years',
    definition: 'The compound annual growth rate (CAGR) of pre-tax profit over the past 7 years — the smoothed yearly rate that compounds pre-tax profit from 7 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Pre-tax Profit now / Pre-tax Profit 7Y ago)^(1/7) − 1',
    interpretation: '>10% is strong, >15% exceptional over 7 years. Smooths out volatile single years.',
    example: 'Pre-tax profit of $100M 7 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/7) − 1 = 10.4% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'growth', 'cagr'],
  },
  {
    id: 'pbt_fy0',
    name: 'Pre-tax Profit (Most Recent Year)',
    category: 'Financial Health',
    shortDesc: 'Pre-tax Profit from the most recent fiscal year',
    definition: 'The company\'s pre-tax profit from the most recent fiscal year. Part of the multi-year pre-tax profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether pre-tax profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'history', 'income statement'],
  },
  {
    id: 'pbt_fy1',
    name: 'Pre-tax Profit (Last Year)',
    category: 'Financial Health',
    shortDesc: 'Pre-tax Profit from last year',
    definition: 'The company\'s pre-tax profit from last year. Part of the multi-year pre-tax profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether pre-tax profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'history', 'income statement'],
  },
  {
    id: 'pbt_fy10',
    name: 'Pre-tax Profit (10 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Pre-tax Profit from 10 years ago',
    definition: 'The company\'s pre-tax profit from 10 years ago. Part of the multi-year pre-tax profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether pre-tax profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'history', 'income statement'],
  },
  {
    id: 'pbt_fy3',
    name: 'Pre-tax Profit (3 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Pre-tax Profit from 3 years ago',
    definition: 'The company\'s pre-tax profit from 3 years ago. Part of the multi-year pre-tax profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether pre-tax profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'history', 'income statement'],
  },
  {
    id: 'pbt_fy5',
    name: 'Pre-tax Profit (5 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Pre-tax Profit from 5 years ago',
    definition: 'The company\'s pre-tax profit from 5 years ago. Part of the multi-year pre-tax profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether pre-tax profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'history', 'income statement'],
  },
  {
    id: 'pbt_fy7',
    name: 'Pre-tax Profit (7 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Pre-tax Profit from 7 years ago',
    definition: 'The company\'s pre-tax profit from 7 years ago. Part of the multi-year pre-tax profit series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether pre-tax profit is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'history', 'income statement'],
  },
  {
    id: 'pbt_growth_1y',
    name: 'Pre-tax Profit Growth',
    category: 'Growth',
    shortDesc: 'Year-on-year pre-tax profit growth in the latest year',
    definition: 'The percentage change in pre-tax profit in the latest year versus the year before. A single-year growth read (use the CAGRs for multi-year trends).',
    formula: 'Growth = (Pre-tax Profit this year − Pre-tax Profit prior) ÷ |Pre-tax Profit prior|',
    interpretation: 'Positive and accelerating is best. One strong year can be a base effect — confirm with the multi-year CAGR.',
    example: 'Pre-tax profit rising from $80M to $96M → growth = (96 − 80) ÷ 80 = +20% (same maths in dollars or per-share).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'growth'],
  },
  {
    id: 'pbt_growth_prev_y',
    name: 'Pre-tax Profit Growth (Last Year)',
    category: 'Growth',
    shortDesc: 'Year-on-year pre-tax profit growth in the prior year',
    definition: 'The percentage change in pre-tax profit in the prior year versus the year before. A single-year growth read (use the CAGRs for multi-year trends).',
    formula: 'Growth = (Pre-tax Profit this year − Pre-tax Profit prior) ÷ |Pre-tax Profit prior|',
    interpretation: 'Positive and accelerating is best. One strong year can be a base effect — confirm with the multi-year CAGR.',
    example: 'Pre-tax profit rising from $80M to $96M → growth = (96 − 80) ÷ 80 = +20% (same maths in dollars or per-share).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['pbt', 'growth'],
  },
  {
    id: 'pct_from_52w_high',
    name: '% from 52-Week High',
    category: 'Price & Returns',
    shortDesc: 'Distance below the yearly high',
    definition: 'How far the current price sits below its highest point in the past year, as a percent. A momentum and drawdown gauge.',
    formula: '(Price − 52W High) ÷ 52W High',
    interpretation: 'Near 0% = at highs (momentum). Deeply negative = out of favour or a potential value setup.',
    example: 'Price $42 against a 52-week high of $60 → (42 − 60) ÷ 60 = −30% below the high.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['momentum', 'price', 'drawdown'],
  },
  {
    id: 'ppe_net',
    name: 'PP&E (Net)',
    category: 'Financial Health',
    shortDesc: 'Net property, plant and equipment',
    definition: 'The book value of physical long-lived assets — land, buildings, machinery — after accumulated depreciation. The productive asset base of capital-intensive firms.',
    interpretation: 'Used in fixed-asset turnover. Heavy for miners/utilities, light for software.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'assets'],
  },
  {
    id: 'pretax_margin',
    name: 'Pre-tax Margin',
    category: 'Profitability',
    shortDesc: 'Pre-tax profit as a percent of revenue',
    definition: 'Pre-tax margin shows how much of each sales dollar survives as profit before tax. It captures operating efficiency plus financing costs.',
    formula: 'Pre-tax Margin = Pre-tax Profit ÷ Revenue',
    interpretation: 'Higher is better. Compare within a sector — capital-light businesses run far higher margins than retailers.',
    example: 'Pre-tax profit $150M on revenue $1,000M → pre-tax margin = 150÷1,000 = 15%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['margin', 'profit'],
  },
  {
    id: 'price',
    name: 'Share Price',
    category: 'Price & Returns',
    shortDesc: 'Latest traded price per share',
    definition: 'The most recent closing price of one share. The basis for market cap and every price-based ratio.',
    interpretation: 'Price alone says nothing about value — always pair with earnings, book value or cash flow.',
    example: '5 million shares change hands at $20.00; the last trade sets the price used for market cap (= 20 × shares on issue).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['price'],
  },
  {
    id: 'price_to_52w_high',
    name: 'Price / 52W High',
    category: 'ASX-Specific',
    shortDesc: 'Price relative to the yearly high',
    definition: 'The current price as a fraction of the 52-week high (1.0 = at the high). A momentum positioning indicator.',
    formula: 'Price ÷ 52W High',
    interpretation: 'Close to 1.0 = strong momentum; well below 1.0 = lagging or recovering.',
    example: 'Price $42 ÷ 52-week high $60 = 0.70 (trading at 70% of its yearly peak).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['momentum', 'price'],
  },
  {
    id: 'price_to_52w_low',
    name: 'Price / 52W Low',
    category: 'ASX-Specific',
    shortDesc: 'Price relative to the yearly low',
    definition: 'The current price as a multiple of the 52-week low (1.0 = at the low). Shows how far a stock has rebounded.',
    formula: 'Price ÷ 52W Low',
    interpretation: 'Near 1.0 = at/near lows (oversold or weak); well above 1.0 = strong recovery off the bottom.',
    example: 'Price $42 ÷ 52-week low $30 = 1.40 (up 40% off its yearly low).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['momentum', 'price'],
  },
  {
    id: 'quick_ratio',
    name: 'Quick Ratio (Acid Test)',
    category: 'Financial Health',
    shortDesc: 'Liquidity excluding inventory',
    definition: 'The quick ratio tests whether a company can cover short-term liabilities with its most liquid assets, excluding inventory (which can be hard to sell fast).',
    formula: 'Quick Ratio = (Current Assets − Inventory) ÷ Current Liabilities',
    interpretation: '>1.0 is healthy; <1.0 means the firm relies on selling inventory to meet near-term obligations.',
    example: 'Current assets $500M − inventory $120M = $380M, ÷ current liabilities $300M → quick ratio 1.27× (healthy).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['liquidity', 'solvency', 'working capital'],
  },
  {
    id: 'receivables_turnover',
    name: 'Receivables Turnover',
    category: 'Profitability',
    shortDesc: 'How many times receivables are collected per year',
    definition: 'How often the company collects its average receivables in a year. Higher turnover = faster collection and better working-capital discipline.',
    formula: 'Receivables Turnover = Revenue ÷ Trade Receivables',
    interpretation: 'Higher is better; falling turnover signals slower collections (rising DSO).',
    example: 'Revenue $730M ÷ trade receivables $80M = 9.1× — receivables collected about nine times a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['working capital', 'receivables', 'efficiency'],
  },
  {
    id: 'relative_volume',
    name: 'Relative Volume',
    category: 'Technical Indicators',
    shortDesc: 'Today\'s volume vs the average',
    definition: 'How today\'s trading volume compares to the recent average. Values above 1 mean unusually heavy interest — often around news or breakouts.',
    formula: 'Relative Volume = Today\'s Volume ÷ Avg Volume',
    interpretation: '>2× signals a surge in attention; confirm price moves with volume.',
    example: '4.0M shares trade today vs a 2.0M average → relative volume 2.0× — twice the usual interest.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['technical', 'volume'],
  },
  {
    id: 'retained_earnings',
    name: 'Retained Earnings',
    category: 'Financial Health',
    shortDesc: 'Cumulative profits kept in the business',
    definition: 'The accumulated profits a company has reinvested rather than paid out as dividends. Negative retained earnings (accumulated losses) are common for young or troubled companies.',
    interpretation: 'Growing retained earnings funds growth without new capital. Persistently negative signals a history of losses.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'equity'],
  },
  {
    id: 'return_15y',
    name: 'Return (15 Years)',
    category: 'Price & Returns',
    shortDesc: 'Total price return over 15 years',
    definition: 'The cumulative share-price return over the past 15 years — a very long-run performance gauge for established companies.',
    interpretation: 'Long-run returns reveal genuine compounders. Few stocks sustain high returns over 15 years.',
    example: '$10,000 invested 15 years ago now worth $40,000 → a 15-year total price return of +300%.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['returns', 'performance'],
  },
  {
    id: 'revenue_cagr_10y',
    name: 'Revenue CAGR (10Y)',
    category: 'Growth',
    shortDesc: 'Compound annual revenue growth over 10 years',
    definition: 'The compound annual growth rate (CAGR) of revenue over the past 10 years — the smoothed yearly rate that compounds revenue from 10 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Revenue now / Revenue 10Y ago)^(1/10) − 1',
    interpretation: '>10% is strong, >15% exceptional over 10 years. Smooths out volatile single years.',
    example: 'Revenue of $100M 10 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/10) − 1 = 7.2% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'growth', 'cagr'],
  },
  {
    id: 'revenue_cagr_7y',
    name: 'Revenue CAGR (7Y)',
    category: 'Growth',
    shortDesc: 'Compound annual revenue growth over 7 years',
    definition: 'The compound annual growth rate (CAGR) of revenue over the past 7 years — the smoothed yearly rate that compounds revenue from 7 years ago to today. Only computed when both endpoints are positive.',
    formula: 'CAGR = (Revenue now / Revenue 7Y ago)^(1/7) − 1',
    interpretation: '>10% is strong, >15% exceptional over 7 years. Smooths out volatile single years.',
    example: 'Revenue of $100M 7 years ago growing to $200M today → CAGR = (200 ÷ 100)^(1/7) − 1 = 10.4% a year.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'growth', 'cagr'],
  },
  {
    id: 'revenue_fy0',
    name: 'Sales (Most Recent Year)',
    category: 'Financial Health',
    shortDesc: 'Sales from the most recent fiscal year',
    definition: 'The company\'s sales from the most recent fiscal year. Part of the multi-year sales series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether sales is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'history', 'income statement'],
  },
  {
    id: 'revenue_fy1',
    name: 'Sales (Last Year)',
    category: 'Financial Health',
    shortDesc: 'Sales from last year',
    definition: 'The company\'s sales from last year. Part of the multi-year sales series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether sales is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'history', 'income statement'],
  },
  {
    id: 'revenue_fy10',
    name: 'Sales (10 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Sales from 10 years ago',
    definition: 'The company\'s sales from 10 years ago. Part of the multi-year sales series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether sales is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'history', 'income statement'],
  },
  {
    id: 'revenue_fy2',
    name: 'Sales (2 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Sales from 2 years ago',
    definition: 'The company\'s sales from 2 years ago. Part of the multi-year sales series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether sales is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'history', 'income statement'],
  },
  {
    id: 'revenue_fy3',
    name: 'Sales (3 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Sales from 3 years ago',
    definition: 'The company\'s sales from 3 years ago. Part of the multi-year sales series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether sales is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'history', 'income statement'],
  },
  {
    id: 'revenue_fy5',
    name: 'Sales (5 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Sales from 5 years ago',
    definition: 'The company\'s sales from 5 years ago. Part of the multi-year sales series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether sales is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'history', 'income statement'],
  },
  {
    id: 'revenue_fy7',
    name: 'Sales (7 Years Ago)',
    category: 'Financial Health',
    shortDesc: 'Sales from 7 years ago',
    definition: 'The company\'s sales from 7 years ago. Part of the multi-year sales series (most-recent / last-year / 3Y / 5Y / 7Y / 10Y) used to read the long-run trajectory.',
    interpretation: 'Compare across the series to judge whether sales is growing, flat or shrinking over time.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'history', 'income statement'],
  },
  {
    id: 'revenue_per_share',
    name: 'Revenue per Share',
    category: 'Financial Health',
    shortDesc: 'Revenue divided by shares outstanding',
    definition: 'Revenue expressed on a per-share basis, so it can be compared directly to the share price.',
    formula: 'Revenue per Share = Revenue ÷ Shares Outstanding',
    interpretation: 'Compare to price: e.g. cash/share near the share price flags a cash-rich stock; tangible book/share is a conservative floor value.',
    example: 'Revenue of $250M ÷ 500M shares outstanding = $0.50 per share.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'per share'],
  },
  {
    id: 'rsi_21',
    name: 'RSI (21)',
    category: 'Technical Indicators',
    shortDesc: '21-day Relative Strength Index',
    definition: 'A slower version of RSI over 21 days — measures momentum on a 0–100 scale. Smoother and less twitchy than the 14-day RSI.',
    interpretation: '>70 overbought, <30 oversold, ~50 neutral. The longer window filters out noise.',
    example: 'After a steady multi-week rally a stock\'s 21-day RSI reads 68 — approaching overbought (70) but not yet stretched.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['technical', 'momentum', 'rsi'],
  },
  {
    id: 'rsi_overbought',
    name: 'RSI Overbought (≥70)',
    category: 'Technical Indicators',
    shortDesc: 'True when: RSI Overbought (≥70)',
    definition: 'A yes/no flag — true when the stock meets the condition \'RSI Overbought (≥70)\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'rsi_oversold',
    name: 'RSI Oversold (≤30)',
    category: 'Technical Indicators',
    shortDesc: 'True when: RSI Oversold (≤30)',
    definition: 'A yes/no flag — true when the stock meets the condition \'RSI Oversold (≤30)\'. Use it to include or exclude a group in a screen.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['flag', 'technical'],
  },
  {
    id: 'sales_growth_prev_y',
    name: 'Sales Growth (Last Year)',
    category: 'Growth',
    shortDesc: 'Year-on-year sales growth in the prior year',
    definition: 'The percentage change in sales in the prior year versus the year before. A single-year growth read (use the CAGRs for multi-year trends).',
    formula: 'Growth = (Sales this year − Sales prior) ÷ |Sales prior|',
    interpretation: 'Positive and accelerating is best. One strong year can be a base effect — confirm with the multi-year CAGR.',
    example: 'Sales rising from $80M to $96M → growth = (96 − 80) ÷ 80 = +20% (same maths in dollars or per-share).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['revenue', 'growth'],
  },
  {
    id: 'sector',
    name: 'Sector',
    category: 'ASX-Specific',
    shortDesc: 'The stock\'s sector',
    definition: 'The sector classification for the stock. Filter or group by it in screens (e.g. only Materials, or exclude Financials).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['classification', 'sector'],
  },
  {
    id: 'shares_outstanding',
    name: 'Shares Outstanding',
    category: 'ASX-Specific',
    shortDesc: 'Total shares on issue',
    definition: 'The total number of shares a company has issued. Rising share count dilutes existing holders; buybacks reduce it.',
    interpretation: 'Watch the trend — steady dilution erodes per-share value even when total profit grows.',
    example: 'Net profit $100M ÷ 500M shares outstanding = EPS of $0.20. If 25M new shares are issued, EPS falls even if profit is flat.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['shares', 'dilution'],
  },
  {
    id: 'stoch_d',
    name: 'StochasticD',
    category: 'Technical Indicators',
    shortDesc: 'Stochastic %D',
    definition: 'Stochastic %D for the stock.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['technical'],
  },
  {
    id: 'stoch_k',
    name: 'StochasticK',
    category: 'Technical Indicators',
    shortDesc: 'Stochastic %K',
    definition: 'Stochastic %K for the stock.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['technical'],
  },
  {
    id: 'stock_type',
    name: 'Stock Type',
    category: 'ASX-Specific',
    shortDesc: 'The stock\'s stock type',
    definition: 'The stock type classification for the stock. Filter or group by it in screens (e.g. only Materials, or exclude Financials).',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['classification', 'stock type'],
  },
  {
    id: 'tangible_book_value_per_share',
    name: 'Tangible Book Value per Share',
    category: 'Financial Health',
    shortDesc: 'Tangible Book Value divided by shares outstanding',
    definition: 'Tangible Book Value expressed on a per-share basis, so it can be compared directly to the share price.',
    formula: 'Tangible Book Value per Share = Tangible Book Value ÷ Shares Outstanding',
    interpretation: 'Compare to price: e.g. cash/share near the share price flags a cash-rich stock; tangible book/share is a conservative floor value.',
    example: 'Equity $600M − goodwill $50M − intangibles $30M = $520M ÷ 500M shares = $1.04 tangible book per share.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['tangible', 'per share'],
  },
  {
    id: 'total_current_assets',
    name: 'Current Assets',
    category: 'Financial Health',
    shortDesc: 'Assets convertible to cash within a year',
    definition: 'Cash, receivables, inventory and other assets expected to convert to cash within 12 months. The numerator of the current ratio.',
    interpretation: 'Compared to current liabilities to assess short-term liquidity.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'liquidity'],
  },
  {
    id: 'total_current_liabilities',
    name: 'Current Liabilities',
    category: 'Financial Health',
    shortDesc: 'Obligations due within a year',
    definition: 'Payables, short-term debt and other obligations due within 12 months. The denominator of liquidity ratios.',
    interpretation: 'Current assets should comfortably exceed current liabilities for most businesses.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'liquidity'],
  },
  {
    id: 'total_liabilities',
    name: 'Total Liabilities',
    category: 'Financial Health',
    shortDesc: 'Everything the company owes',
    definition: 'All obligations — debt, payables, provisions, deferred tax. Total assets minus total liabilities equals shareholders\' equity.',
    interpretation: 'Used in liabilities/assets and equity ratios to gauge overall leverage.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'leverage'],
  },
  {
    id: 'trade_receivables',
    name: 'Trade Receivables',
    category: 'Financial Health',
    shortDesc: 'Money owed by customers',
    definition: 'Amounts customers owe for goods/services already delivered on credit. Collected over the DSO period.',
    interpretation: 'Receivables growing faster than revenue can flag aggressive revenue recognition or collection issues.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['balance sheet', 'working capital'],
  },
  {
    id: 'working_capital',
    name: 'Working Capital',
    category: 'Financial Health',
    shortDesc: 'Current assets minus current liabilities',
    definition: 'The short-term capital a business has to fund day-to-day operations. Positive = a buffer; negative can be efficient (retailers) or risky.',
    formula: 'Working Capital = Current Assets − Current Liabilities',
    interpretation: 'Trend matters more than level. Watch banks/retailers separately — negative working capital is normal for them.',
    example: 'Current assets $500M − current liabilities $300M = $200M of working capital.',
    usedIn: ['Screener', 'Company Detail'],
    tags: ['liquidity', 'balance sheet'],
  },
]

// ── Category config ───────────────────────────────────────────────────────────

const CATEGORIES = [
  { key: 'all',                   label: 'All Metrics',          colour: 'bg-gray-100 text-gray-700',     bar: 'bg-gray-300' },
  { key: 'Valuation',             label: 'Valuation',            colour: 'bg-blue-100 text-blue-700',     bar: 'bg-blue-400' },
  { key: 'Profitability',         label: 'Profitability',        colour: 'bg-emerald-100 text-emerald-700', bar: 'bg-emerald-400' },
  { key: 'Growth',                label: 'Growth',               colour: 'bg-violet-100 text-violet-700', bar: 'bg-violet-400' },
  { key: 'Dividends & Income',    label: 'Dividends & Income',   colour: 'bg-amber-100 text-amber-700',   bar: 'bg-amber-400' },
  { key: 'Financial Health',      label: 'Financial Health',     colour: 'bg-rose-100 text-rose-700',     bar: 'bg-rose-400' },
  { key: 'Technical Indicators',  label: 'Technicals',           colour: 'bg-cyan-100 text-cyan-700',     bar: 'bg-cyan-400' },
  { key: 'Price & Returns',       label: 'Price & Returns',      colour: 'bg-orange-100 text-orange-700', bar: 'bg-orange-400' },
  { key: 'Quality Scores',        label: 'Quality Scores',       colour: 'bg-purple-100 text-purple-700', bar: 'bg-purple-400' },
  { key: 'ASX-Specific',          label: 'ASX-Specific',         colour: 'bg-green-100 text-green-700',   bar: 'bg-green-400' },
]

function catColour(cat: string) {
  return CATEGORIES.find(c => c.key === cat)?.colour ?? 'bg-gray-100 text-gray-600'
}
function catBar(cat: string) {
  return CATEGORIES.find(c => c.key === cat)?.bar ?? 'bg-gray-300'
}

// ── Section label helper ──────────────────────────────────────────────────────

function SectionLabel({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-1.5 mb-2.5">
      {icon}
      <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{label}</span>
    </div>
  )
}

// ── Metric card ───────────────────────────────────────────────────────────────

function MetricCard({ metric, expandAll }: { metric: Metric; expandAll: boolean | null }) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (expandAll !== null) setOpen(expandAll)
  }, [expandAll])

  return (
    <div className={cn(
      'bg-white border rounded-xl transition-all duration-150 overflow-hidden',
      open ? 'border-blue-300 shadow-md' : 'border-gray-200 hover:border-blue-200 hover:shadow-sm',
    )}>
      {/* Category colour accent bar */}
      <div className={cn('h-0.5', catBar(metric.category))} />

      {/* Header — always visible */}
      <button
        className="w-full text-left px-5 py-4 flex items-start justify-between gap-3"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
            <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded-full', catColour(metric.category))}>
              {metric.category}
            </span>
            {metric.beginner && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700 border border-green-200">
                ✦ Beginner Friendly
              </span>
            )}
          </div>
          <h3 className="font-semibold text-sm text-gray-900">{metric.name}</h3>
          <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{metric.shortDesc}</p>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0 mt-1">
          {metric.formula    && <span className="hidden sm:inline text-[9px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-100 px-1.5 py-0.5 rounded">∑ formula</span>}
          {metric.benchmark  && <span className="hidden sm:inline text-[9px] font-bold text-purple-700 bg-purple-50 border border-purple-100 px-1.5 py-0.5 rounded">⬡ benchmark</span>}
          {open ? <ChevronUp className="w-4 h-4 text-blue-500" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </div>
      </button>

      {/* Expanded content */}
      {open && (
        <div className="border-t border-gray-100">

          {/* Beginner tip — amber highlight block */}
          {metric.beginnerTip && (
            <div className="mx-5 mt-5 bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-base">💡</span>
                <span className="text-[10px] font-bold text-amber-800 uppercase tracking-widest">Simple Explanation</span>
              </div>
              <p className="text-sm text-amber-900 leading-relaxed">{metric.beginnerTip}</p>
            </div>
          )}

          <div className="px-5 pb-6 pt-5 space-y-5">

            {/* What it measures */}
            <div>
              <SectionLabel icon={<Info className="w-3.5 h-3.5 text-blue-500" />} label="What it measures" />
              <p className="text-sm text-gray-700 leading-relaxed">{metric.definition}</p>
            </div>

            {/* Formula */}
            {metric.formula && (
              <div>
                <SectionLabel icon={<Calculator className="w-3.5 h-3.5 text-emerald-500" />} label="Formula / Calculation" />
                <div className="bg-slate-900 rounded-xl px-4 py-3.5 overflow-x-auto">
                  <pre className="text-xs text-emerald-300 font-mono leading-relaxed whitespace-pre-wrap">{metric.formula}</pre>
                </div>
              </div>
            )}

            {/* Real-world example */}
            {metric.example && (
              <div>
                <SectionLabel icon={<BarChart2 className="w-3.5 h-3.5 text-blue-400" />} label="Real-World Example" />
                <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3.5">
                  <p className="text-sm text-blue-900 leading-relaxed font-medium">{metric.example}</p>
                </div>
              </div>
            )}

            {/* How to interpret */}
            {metric.interpretation && (
              <div>
                <SectionLabel icon={<Target className="w-3.5 h-3.5 text-amber-500" />} label="How to Interpret It" />
                <p className="text-sm text-gray-700 leading-relaxed">{metric.interpretation}</p>
              </div>
            )}

            {/* Benchmarks */}
            {metric.benchmark && (
              <div>
                <SectionLabel icon={<Tag className="w-3.5 h-3.5 text-purple-500" />} label="Benchmarks & Ranges" />
                <div className="bg-gradient-to-r from-purple-50 to-white border border-purple-100 rounded-xl px-4 py-3">
                  <p className="text-xs text-purple-900 leading-relaxed font-medium">{metric.benchmark}</p>
                </div>
              </div>
            )}

            {/* Related metrics */}
            {metric.relatedMetrics && metric.relatedMetrics.length > 0 && (
              <div>
                <SectionLabel icon={<Link2 className="w-3.5 h-3.5 text-gray-400" />} label="Related Metrics" />
                <div className="flex flex-wrap gap-1.5">
                  {metric.relatedMetrics.map(id => {
                    const m = METRICS.find(x => x.id === id)
                    return m ? (
                      <span key={id} className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-700 border border-gray-200 font-medium hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 transition-colors cursor-default">
                        {m.name}
                      </span>
                    ) : null
                  })}
                </div>
              </div>
            )}

            {/* Used in */}
            <div>
              <SectionLabel icon={<MapPin className="w-3.5 h-3.5 text-rose-400" />} label="Where you'll see this" />
              <div className="flex flex-wrap gap-1.5">
                {metric.usedIn.map(u => (
                  <span key={u} className="text-[11px] px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-100 font-medium">
                    {u}
                  </span>
                ))}
              </div>
            </div>

            {/* Tags */}
            <div className="flex flex-wrap gap-1.5 pt-3 border-t border-gray-100">
              {metric.tags.map(t => (
                <span key={t} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                  #{t}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Quick filter chip ─────────────────────────────────────────────────────────

type QuickFilter = 'formula' | 'benchmark' | 'screener' | 'alphafive' | 'beginner'

const QUICK_FILTERS: { key: QuickFilter; label: string; colour: string }[] = [
  { key: 'formula',    label: '∑ Has Formula',          colour: 'border-emerald-300 text-emerald-700 bg-emerald-50' },
  { key: 'benchmark',  label: '⬡ Has Benchmark',         colour: 'border-purple-300 text-purple-700 bg-purple-50' },
  { key: 'screener',   label: '🔍 Used in Screener',     colour: 'border-blue-300 text-blue-700 bg-blue-50' },
  { key: 'alphafive',  label: '🏆 Used in AlphaFive',    colour: 'border-amber-300 text-amber-700 bg-amber-50' },
  { key: 'beginner',   label: '✦ Beginner Friendly',    colour: 'border-green-300 text-green-700 bg-green-50' },
]

function matchesQuickFilter(m: Metric, f: QuickFilter): boolean {
  switch (f) {
    case 'formula':   return !!m.formula
    case 'benchmark': return !!m.benchmark
    case 'screener':  return m.usedIn.some(u => u.includes('Screener'))
    case 'alphafive': return m.usedIn.some(u => u.toLowerCase().includes('top 5') || u.toLowerCase().includes('alphafive'))
    case 'beginner':  return !!m.beginner
  }
}

// ── Main content ──────────────────────────────────────────────────────────────

function GlossaryContent() {
  const [search,       setSearch]       = useState('')
  const [activeCat,    setActiveCat]    = useState('all')
  const [activeQF,     setActiveQF]     = useState<Set<QuickFilter>>(new Set())
  const [expandAll,    setExpandAll]    = useState<boolean | null>(null)

  function toggleQF(f: QuickFilter) {
    setActiveQF(prev => {
      const next = new Set(prev)
      next.has(f) ? next.delete(f) : next.add(f)
      return next
    })
  }

  const filtered = useMemo(() => {
    let m = METRICS
    if (activeCat !== 'all') m = m.filter(x => x.category === activeCat)
    if (activeQF.size > 0)   m = m.filter(x => [...activeQF].every(f => matchesQuickFilter(x, f)))
    if (search.trim()) {
      const q = search.toLowerCase()
      m = m.filter(x =>
        x.name.toLowerCase().includes(q) ||
        x.shortDesc.toLowerCase().includes(q) ||
        x.definition.toLowerCase().includes(q) ||
        x.tags.some(t => t.toLowerCase().includes(q)) ||
        x.usedIn.some(u => u.toLowerCase().includes(q))
      )
    }
    return m
  }, [search, activeCat, activeQF])

  const counts = useMemo(() => {
    const map: Record<string, number> = { all: METRICS.length }
    METRICS.forEach(m => { map[m.category] = (map[m.category] ?? 0) + 1 })
    return map
  }, [])

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
      <div className="flex gap-8">

        {/* Sidebar */}
        <aside className="hidden lg:block w-56 flex-shrink-0">
          <div className="sticky top-20 space-y-1">
            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3 px-2">Categories</p>
            {CATEGORIES.map(cat => (
              <button
                key={cat.key}
                onClick={() => setActiveCat(cat.key)}
                className={cn(
                  'w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors',
                  activeCat === cat.key
                    ? 'bg-blue-50 text-blue-700 font-semibold'
                    : 'text-gray-600 hover:bg-gray-100',
                )}
              >
                <span>{cat.label}</span>
                <span className={cn(
                  'text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[20px] text-center',
                  activeCat === cat.key ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500',
                )}>
                  {counts[cat.key] ?? 0}
                </span>
              </button>
            ))}
          </div>
        </aside>

        {/* Main */}
        <div className="flex-1 min-w-0">

          {/* Search bar */}
          <div className="relative mb-4">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search 140+ metrics, formulas, concepts..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-10 pr-20 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white shadow-sm"
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs font-medium">
                Clear
              </button>
            )}
          </div>

          {/* Quick filter chips */}
          <div className="flex flex-wrap gap-2 mb-4">
            {QUICK_FILTERS.map(f => (
              <button
                key={f.key}
                onClick={() => toggleQF(f.key)}
                className={cn(
                  'text-xs px-3 py-1.5 rounded-full border font-medium transition-all',
                  activeQF.has(f.key)
                    ? f.colour + ' shadow-sm'
                    : 'border-gray-200 text-gray-600 bg-white hover:border-gray-300',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Mobile category pills */}
          <div className="flex gap-2 overflow-x-auto pb-2 mb-4 lg:hidden scrollbar-hide">
            {CATEGORIES.map(cat => (
              <button
                key={cat.key}
                onClick={() => setActiveCat(cat.key)}
                className={cn(
                  'flex-shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors',
                  activeCat === cat.key
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300',
                )}
              >
                {cat.label} ({counts[cat.key] ?? 0})
              </button>
            ))}
          </div>

          {/* Results bar + Expand All */}
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-500">
              {filtered.length === METRICS.length
                ? <><span className="font-semibold text-gray-700">{METRICS.length}</span> metrics</>
                : <><span className="font-semibold text-gray-700">{filtered.length}</span> of {METRICS.length} metrics</>
              }
              {activeCat !== 'all' && <span className="text-blue-600"> in {activeCat}</span>}
            </p>
            <button
              onClick={() => setExpandAll(v => v === true ? false : true)}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-blue-600 transition-colors px-3 py-1.5 rounded-lg border border-gray-200 hover:border-blue-200 bg-white"
            >
              <ChevronsUpDown className="w-3.5 h-3.5" />
              {expandAll === true ? 'Collapse All' : 'Expand All'}
            </button>
          </div>

          {/* Metric cards */}
          {filtered.length > 0 ? (
            <div className="space-y-2.5">
              {filtered.map(m => <MetricCard key={m.id} metric={m} expandAll={expandAll} />)}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <Search className="w-10 h-10 text-gray-200 mb-3" />
              <p className="text-gray-500 font-medium">No metrics found</p>
              <p className="text-sm text-gray-400 mt-1">Try a different search term or clear the filters</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function GlossaryPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600
                            flex items-center justify-center shadow-sm flex-shrink-0">
              <BookOpen className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2.5 flex-wrap mb-1">
                <h1 className="text-2xl font-bold text-gray-900">Metrics Glossary</h1>
                <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-blue-100 text-blue-700 border border-blue-200">
                  <Zap className="w-3 h-3" /> Pro &amp; Premium
                </span>
              </div>
              <p className="text-gray-500 text-sm mt-0.5 max-w-2xl">
                Your investment education library — plain-English definitions, formulas, benchmarks,
                real-world examples and beginner explanations for every metric across the ASX Screener platform.
              </p>
              <div className="flex flex-wrap items-center gap-4 mt-4">
                <div className="text-center">
                  <p className="text-xl font-bold text-gray-900">{METRICS.length}</p>
                  <p className="text-xs text-gray-500">Metrics</p>
                </div>
                <div className="w-px h-8 bg-gray-200" />
                <div className="text-center">
                  <p className="text-xl font-bold text-gray-900">{CATEGORIES.length - 1}</p>
                  <p className="text-xs text-gray-500">Categories</p>
                </div>
                <div className="w-px h-8 bg-gray-200" />
                <div className="text-center">
                  <p className="text-xl font-bold text-gray-900">
                    {METRICS.filter(m => m.formula).length}
                  </p>
                  <p className="text-xs text-gray-500">With Formulas</p>
                </div>
                <div className="w-px h-8 bg-gray-200" />
                <div className="text-center">
                  <p className="text-xl font-bold text-gray-900">
                    {METRICS.filter(m => m.benchmark).length}
                  </p>
                  <p className="text-xs text-gray-500">With Benchmarks</p>
                </div>
                <div className="w-px h-8 bg-gray-200" />
                <div className="text-center">
                  <p className="text-xl font-bold text-gray-900">
                    {METRICS.filter(m => m.beginner).length}
                  </p>
                  <p className="text-xs text-gray-500">Beginner Tips</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <PlanGate required="pro" feature="Metrics Glossary">
        <GlossaryContent />
      </PlanGate>
    </div>
  )
}
