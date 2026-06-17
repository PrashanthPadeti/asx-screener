import Link from 'next/link'
import type { Metadata } from 'next'
import { BarChart2, AlertTriangle, ChevronLeft, Zap, BookOpen, TrendingUp, Shield } from 'lucide-react'
import Breadcrumb from '@/components/Breadcrumb'

export const metadata: Metadata = {
  title: 'ASX Healthcare Sector — Biotech, Medical Devices & Healthcare Services | ASX Screener',
  description: 'Overview of the ASX Healthcare sector. Key metrics for CSL, Cochlear, Ramsay, and ASX biotech. How to screen and research Australian healthcare stocks.',
  alternates: { canonical: 'https://asxscreener.com.au/sectors/healthcare' },
}

const KEY_METRICS = [
  { metric: 'Revenue Growth (1Y & 3Y CAGR)', why: 'Healthcare companies derive much of their value from growth. Consistent double-digit revenue growth in pharma, biotech, and device companies is the primary driver of re-rating.' },
  { metric: 'Gross Margin', why: 'High gross margins (50–80%+) are the hallmark of IP-protected healthcare businesses — drugs, devices, and diagnostics. Low gross margins signal commoditised services.' },
  { metric: 'ROIC (Return on Invested Capital)', why: 'The best healthcare companies sustain ROIC well above cost of capital for decades — a sign of durable IP moats. CSL is the ASX benchmark example.' },
  { metric: 'R&D as % of Revenue', why: 'Biotech and pharma companies invest heavily in R&D to build pipeline. High R&D spend relative to revenue signals a company investing in future growth — but also near-term earnings pressure.' },
  { metric: 'EPS Growth & EPS CAGR 5Y', why: 'For established healthcare companies, consistent EPS growth (10%+ pa over 5+ years) is the key quality signal — it shows the business model is working and compounding.' },
  { metric: 'Enterprise Value / EBITDA', why: 'Used more than P/E for healthcare because depreciation and amortisation of intangibles (IP, patents) can distort earnings. EV/EBITDA normalises this.' },
  { metric: 'Cash Burn Rate (Pre-revenue biotech)', why: 'For pre-revenue clinical-stage companies, track cash runway (months of cash at current burn). Running out of cash = dilutive capital raise or failure.' },
]

const SUB_SECTORS = [
  {
    name: 'Blood Products & Plasma',
    desc: 'CSL dominates this globally. Plasma collection and fractionation is a capital-intensive, highly regulated, patent-protected business with very high barriers to entry. Among the highest-quality businesses on the ASX.',
    examples: 'CSL',
  },
  {
    name: 'Medical Devices',
    desc: 'Companies that design, manufacture, and sell implantable or wearable medical devices. Long regulatory approval cycles but durable recurring revenue from consumables and replacement parts.',
    examples: 'COH (Cochlear), NAN (Nanosonics), SHL (Sonic Healthcare), IMP',
  },
  {
    name: 'Healthcare Services',
    desc: 'Hospital operators, pathology providers, radiology, and aged care. Revenue is more defensive (non-discretionary healthcare spending) but margins are lower and labour cost is a major headwind.',
    examples: 'RHC (Ramsay), SHL, HLS (Healius), REG',
  },
  {
    name: 'Pharmaceuticals & Generics',
    desc: 'Drug manufacturers and distributors. Branded pharma benefits from patent protection; generics compete on cost. Exposed to pricing pressure, patent cliffs, and regulatory risk.',
    examples: 'API, IHD, PCL',
  },
  {
    name: 'Biotech (Clinical Stage)',
    desc: 'Pre-revenue or early-revenue companies advancing drugs, gene therapies, or diagnostics through clinical trials. Binary risk — trial success or failure dramatically impacts value. Assess pipeline, cash runway, and management track record.',
    examples: 'IMM, ARX, CU6, OPT, IMU',
  },
  {
    name: 'Digital Health & Health IT',
    desc: 'Software platforms for healthcare providers, electronic health records, and AI-assisted diagnostics. SaaS-like economics with high switching costs. Growing but still a small part of the ASX healthcare universe.',
    examples: 'RMD (ResMed), VHT, HCW',
  },
]

const SCREENS = [
  {
    name: 'Quality healthcare compounders',
    desc: 'Established healthcare companies with strong ROIC, consistent earnings growth, and manageable debt.',
    filters: [
      'sector = Healthcare',
      'roic > 15',
      'eps_cagr_5y > 10',
      'gross_margin > 50',
      'debt_to_equity < 0.5',
      'market_cap > 1000',
    ],
  },
  {
    name: 'Healthcare growth screen',
    desc: 'Revenue-growing healthcare companies with expanding margins and positive earnings momentum.',
    filters: [
      'sector = Healthcare',
      'revenue_growth_3y_cagr > 10',
      'eps_growth_1y > 8',
      'gross_margin > 40',
      'market_cap > 200',
    ],
  },
  {
    name: 'Healthcare dividend income',
    desc: 'Defensive healthcare businesses generating reliable dividends — services and devices rather than biotech.',
    filters: [
      'sector = Healthcare',
      'dividend_yield > 2',
      'payout_ratio < 70',
      'revenue_growth_1y > 0',
      'debt_to_equity < 1',
      'market_cap > 500',
    ],
  },
]

export default function HealthcareSectorPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-10">

      <Breadcrumb crumbs={[{ label: 'Sectors', href: '/sectors' }, { label: 'Healthcare', href: '/sectors/healthcare' }]} />

      <div>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-rose-100 text-rose-700">GICS Sector</span>
          <span className="text-xs text-slate-400">ASX 200 weight: ~9–12%</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-4 leading-tight">
          ASX Healthcare Sector
        </h1>
        <p className="text-lg text-slate-600 leading-relaxed">
          Healthcare is one of the highest-quality sectors on the ASX — home to world-class businesses like CSL and Cochlear that have compounded shareholder wealth for decades. It spans plasma products, medical devices, healthcare services, and clinical-stage biotech, each with distinct risk and return profiles.
        </p>
      </div>

      <Link
        href="/screener"
        className="flex items-center gap-3 bg-gradient-to-r from-rose-600 to-pink-600 text-white rounded-2xl p-5 hover:from-rose-700 hover:to-pink-700 transition-all"
      >
        <BarChart2 className="w-6 h-6 shrink-0" />
        <div className="flex-1">
          <p className="font-bold">Screen ASX Healthcare Stocks</p>
          <p className="text-rose-200 text-sm">Filter by Sector = Healthcare, then apply ROIC, EPS growth, gross margin and more</p>
        </div>
        <ChevronLeft className="w-5 h-5 rotate-180 shrink-0" />
      </Link>

      <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-rose-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Zap className="w-4 h-4" /> Sector characteristics
        </h2>
        <ul className="space-y-1.5 text-sm text-rose-900">
          {[
            'Non-cyclical demand — healthcare spending is largely non-discretionary and grows with ageing demographics.',
            'IP moats — patents, regulatory approvals, and clinical data create durable competitive advantages.',
            'Long development cycles — drugs and devices take 10–15 years from research to commercialisation.',
            'Currency exposure — most large ASX healthcare companies earn the majority of revenue offshore in USD/EUR.',
            'Regulatory risk — approvals by the TGA, FDA, and EMA are binary events that can make or break a product.',
            'ASX biotech is highly speculative — many companies are pre-revenue with cash burn and binary trial risk.',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <TrendingUp className="w-3.5 h-3.5 text-rose-600 shrink-0 mt-0.5" />
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Sub-sectors on the ASX</h2>
        <div className="space-y-3">
          {SUB_SECTORS.map(({ name, desc, examples }) => (
            <div key={name} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <p className="font-bold text-slate-900">{name}</p>
                <span className="text-xs font-mono text-rose-600 bg-rose-50 px-2 py-0.5 rounded">{examples}</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Key metrics for ASX healthcare stocks</h2>
        <div className="space-y-3">
          {KEY_METRICS.map(({ metric, why }) => (
            <div key={metric} className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="font-semibold text-slate-900 text-sm mb-1">{metric}</p>
              <p className="text-xs text-slate-500 leading-relaxed">{why}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-blue-800 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4" /> CSL: the ASX healthcare benchmark
        </h2>
        <p className="text-sm text-blue-900 leading-relaxed mb-2">
          CSL is frequently cited as one of the highest-quality businesses on the Australian sharemarket. Over 20 years it has delivered consistent double-digit EPS growth through a combination of organic expansion, disciplined R&D, and acquisitions (including Behring and Vifor).
        </p>
        <p className="text-sm text-blue-900 leading-relaxed">
          Key CSL attributes to look for in other healthcare companies: high ROIC (20%+), sustained revenue growth, expanding addressable market, and a management team with a long track record of capital allocation discipline.
        </p>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-4">Healthcare screening strategies</h2>
        <div className="space-y-4">
          {SCREENS.map(({ name, desc, filters }) => (
            <div key={name} className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
              <h3 className="font-bold text-slate-900 mb-1">{name}</h3>
              <p className="text-xs text-slate-500 mb-3">{desc}</p>
              <div className="bg-slate-900 rounded-xl p-3">
                <code className="text-emerald-300 font-mono text-xs leading-relaxed block">{filters.join('\n')}</code>
              </div>
              <Link href="/screener" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-800">
                Apply this screen <ChevronLeft className="w-3.5 h-3.5 rotate-180" />
              </Link>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold text-slate-900 mb-3">Biotech-specific considerations</h2>
        <p className="text-slate-600 text-sm leading-relaxed mb-3">
          Clinical-stage biotech companies require a different analytical framework. Standard screener metrics (P/E, ROE, payout ratio) are meaningless for pre-revenue businesses. Instead focus on:
        </p>
        <div className="space-y-2">
          {[
            { item: 'Cash runway', detail: 'At current burn rate, how many months until the company needs to raise capital? Less than 12 months = high dilution risk.' },
            { item: 'Trial phase and readout dates', detail: 'Phase 3 trials have the highest binary risk and the largest potential share price move on results.' },
            { item: 'Market opportunity (TAM)', detail: 'A drug targeting a $10B global market is more interesting than one targeting $100M. Sizing matters.' },
            { item: 'Management and board track record', detail: 'Have the founders or executives commercialised drugs before? Prior success significantly increases probability of execution.' },
            { item: 'Partnerships and licensing deals', detail: 'A partnership with a major pharma validates the science and often provides non-dilutive cash via milestone payments.' },
          ].map(({ item, detail }) => (
            <div key={item} className="flex items-start gap-3 bg-white border border-slate-200 rounded-xl p-3">
              <span className="text-xs font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded shrink-0 whitespace-nowrap">{item}</span>
              <p className="text-xs text-slate-500 leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4" /> Related resources
        </h2>
        <div className="space-y-2">
          {[
            { href: '/sectors/materials', label: 'ASX Materials Sector Overview' },
            { href: '/sectors/financials', label: 'ASX Financials Sector Overview' },
            { href: '/learn/roic-explained', label: 'ROIC Explained: Return on Invested Capital' },
            { href: '/learn/key-financial-ratios', label: 'Key Financial Ratios for ASX Investors' },
            { href: '/learn/how-to-find-asx-growth-stocks', label: 'How to Find ASX Growth Stocks Using Revenue Growth' },
          ].map(({ href, label }) => (
            <Link key={href} href={href} className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
              <ChevronLeft className="w-3.5 h-3.5 rotate-180 shrink-0" />
              {label}
            </Link>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-500">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p>
          <strong>Not financial advice.</strong> Company mentions (CSL, Cochlear, Ramsay, etc.) are illustrative examples only — not recommendations to buy or sell. Healthcare investing carries sector-specific risks including clinical trial failure, regulatory risk, and currency exposure. Always conduct your own research.
        </p>
      </div>

    </div>
  )
}
