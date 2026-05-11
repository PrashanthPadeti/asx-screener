'use client'
import { ExternalLink, Check, X, Minus, Shield, Zap, DollarSign, Globe, Star } from 'lucide-react'
import { PlanGate } from '@/components/PlanGate'

interface Broker {
  name: string
  logo: string
  tagline: string
  brokerage: string
  platformFee: string
  minDeposit: string
  chess: boolean | null
  international: boolean
  fractional: boolean
  research: 'basic' | 'good' | 'excellent'
  bestFor: string
  promoText?: string
  affiliateUrl: string
  highlight?: boolean
}

const BROKERS: Broker[] = [
  {
    name: 'CommSec',
    logo: 'CS',
    tagline: 'Australia\'s largest online broker',
    brokerage: '$10 – $19.95',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: true,
    international: true,
    fractional: false,
    research: 'excellent',
    bestFor: 'Full-service investing with deep research',
    affiliateUrl: 'https://www.commsec.com.au',
  },
  {
    name: 'SelfWealth',
    logo: 'SW',
    tagline: 'Flat $9.50 brokerage, always',
    brokerage: '$9.50 flat',
    platformFee: 'Free (Premium $20/mo)',
    minDeposit: '$0',
    chess: true,
    international: true,
    fractional: false,
    research: 'good',
    bestFor: 'Cost-conscious investors who buy regularly',
    promoText: 'Get 5 free trades for new accounts',
    affiliateUrl: 'https://www.selfwealth.com.au',
    highlight: true,
  },
  {
    name: 'Superhero',
    logo: 'SH',
    tagline: 'Simple investing from $5',
    brokerage: '$5 ASX · $0 US',
    platformFee: 'Free',
    minDeposit: '$100',
    chess: false,
    international: true,
    fractional: true,
    research: 'basic',
    bestFor: 'Beginners and US stock investors',
    promoText: 'No brokerage on ETF purchases',
    affiliateUrl: 'https://www.superhero.com.au',
  },
  {
    name: 'Pearler',
    logo: 'PL',
    tagline: 'Built for long-term investors',
    brokerage: '$6.50',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: true,
    international: true,
    fractional: false,
    research: 'basic',
    bestFor: 'Passive investors and ETF accumulators',
    promoText: 'Auto-invest on a schedule',
    affiliateUrl: 'https://www.pearler.com',
  },
  {
    name: 'CMC Invest',
    logo: 'CMC',
    tagline: 'Zero brokerage on small trades',
    brokerage: '$0 (under $1k) · $11+',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: true,
    international: false,
    fractional: false,
    research: 'good',
    bestFor: 'Active traders who want low costs',
    affiliateUrl: 'https://www.cmcinvest.com.au',
  },
  {
    name: 'nabtrade',
    logo: 'NT',
    tagline: 'Premium research for serious investors',
    brokerage: '$14.95 – $19.95',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: true,
    international: true,
    fractional: false,
    research: 'excellent',
    bestFor: 'NAB customers seeking premium research',
    affiliateUrl: 'https://www.nabtrade.com.au',
  },
  {
    name: 'Stake',
    logo: 'SK',
    tagline: 'Modern investing, ASX & US',
    brokerage: '$3 AUS · $0 US',
    platformFee: 'Free (Stake Black $9/mo)',
    minDeposit: '$0',
    chess: false,
    international: true,
    fractional: true,
    research: 'basic',
    bestFor: 'Investors who want both ASX and US exposure',
    affiliateUrl: 'https://www.stake.com.au',
  },
  {
    name: 'moomoo',
    logo: 'MM',
    tagline: 'Advanced tools, low fees',
    brokerage: '$0.99 – $3.99',
    platformFee: 'Free',
    minDeposit: '$0',
    chess: false,
    international: true,
    fractional: false,
    research: 'good',
    bestFor: 'Active traders who want advanced charting',
    promoText: 'Up to 180 days free brokerage for new users',
    affiliateUrl: 'https://www.moomoo.com/au',
    highlight: true,
  },
]

const RESEARCH_LABEL = {
  basic: { label: 'Basic', cls: 'bg-slate-100 text-slate-600' },
  good: { label: 'Good', cls: 'bg-blue-100 text-blue-700' },
  excellent: { label: 'Excellent', cls: 'bg-emerald-100 text-emerald-700' },
}

function TrileanIcon({ value }: { value: boolean | null }) {
  if (value === true)  return <Check className="w-4 h-4 text-emerald-500 mx-auto" />
  if (value === false) return <X className="w-4 h-4 text-red-400 mx-auto" />
  return <Minus className="w-4 h-4 text-slate-300 mx-auto" />
}

export default function BrokersPage() {
  return (
    <PlanGate required="premium" feature="Broker Compare">
    <div className="max-w-6xl mx-auto space-y-10 pb-16">

      {/* Hero */}
      <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-2xl p-8 text-white">
        <div className="flex items-center gap-2 text-blue-200 text-sm mb-3">
          <Shield className="w-4 h-4" />
          Independent comparison · Fees verified May 2025
        </div>
        <h1 className="text-3xl font-bold mb-3">Best ASX Brokers 2025</h1>
        <p className="text-blue-100 max-w-2xl text-lg">
          Compare Australia's top share trading platforms on fees, features, and CHESS sponsorship.
          Find the right broker for your investing style.
        </p>
        <div className="mt-5 flex flex-wrap gap-3 text-sm">
          <span className="flex items-center gap-1.5 bg-blue-700/60 rounded-full px-3 py-1">
            <DollarSign className="w-3.5 h-3.5" /> Low-cost options from $0/trade
          </span>
          <span className="flex items-center gap-1.5 bg-blue-700/60 rounded-full px-3 py-1">
            <Shield className="w-3.5 h-3.5" /> CHESS-sponsored brokers
          </span>
          <span className="flex items-center gap-1.5 bg-blue-700/60 rounded-full px-3 py-1">
            <Globe className="w-3.5 h-3.5" /> International access
          </span>
        </div>
      </div>

      {/* Disclaimer */}
      <p className="text-xs text-slate-500 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
        <strong>Disclosure:</strong> Some links on this page are affiliate links. We may earn a commission if you open an account via our link, at no extra cost to you. Fees and features are subject to change — always verify with the broker before opening an account. This is not financial advice.
      </p>

      {/* Featured cards */}
      <div>
        <h2 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
          <Star className="w-4 h-4 text-amber-500" />
          Editor's Picks
        </h2>
        <div className="grid md:grid-cols-2 gap-4">
          {BROKERS.filter(b => b.highlight).map(broker => (
            <div key={broker.name} className="bg-white border-2 border-blue-200 rounded-2xl p-6 relative overflow-hidden">
              <div className="absolute top-3 right-3 text-[10px] font-bold bg-blue-600 text-white px-2 py-0.5 rounded-full">
                FEATURED
              </div>
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-blue-600 text-white font-bold text-sm flex items-center justify-center shrink-0">
                  {broker.logo}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-slate-900">{broker.name}</h3>
                  <p className="text-sm text-slate-500">{broker.tagline}</p>
                  {broker.promoText && (
                    <p className="text-xs text-emerald-700 bg-emerald-50 rounded px-2 py-0.5 mt-1.5 inline-block">
                      {broker.promoText}
                    </p>
                  )}
                </div>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3 text-center text-xs">
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-bold text-slate-800">{broker.brokerage}</div>
                  <div className="text-slate-500">Brokerage</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className="font-bold text-slate-800">{broker.chess ? 'CHESS' : 'Custodial'}</div>
                  <div className="text-slate-500">Holding</div>
                </div>
                <div className="bg-slate-50 rounded-lg p-2">
                  <div className={`text-xs font-semibold px-1.5 py-0.5 rounded inline-block ${RESEARCH_LABEL[broker.research].cls}`}>
                    {RESEARCH_LABEL[broker.research].label}
                  </div>
                  <div className="text-slate-500 mt-1">Research</div>
                </div>
              </div>
              <a
                href={broker.affiliateUrl}
                target="_blank"
                rel="noopener noreferrer sponsored"
                className="mt-4 w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold py-2.5 rounded-xl transition-colors"
              >
                Open account <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          ))}
        </div>
      </div>

      {/* Full comparison table */}
      <div>
        <h2 className="text-lg font-semibold text-slate-800 mb-4">Full Comparison</h2>
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="text-left px-4 py-3 font-semibold text-slate-700 w-40">Broker</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700 whitespace-nowrap">Brokerage</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700 whitespace-nowrap">Platform fee</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700 whitespace-nowrap">Min. deposit</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">CHESS</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">Intl.</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">Fractional</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">Research</th>
                  <th className="text-center px-3 py-3 font-semibold text-slate-700">Best for</th>
                  <th className="px-3 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {BROKERS.map(broker => (
                  <tr key={broker.name} className={`hover:bg-slate-50 transition-colors ${broker.highlight ? 'bg-blue-50/40' : ''}`}>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-blue-600 text-white font-bold text-xs flex items-center justify-center shrink-0">
                          {broker.logo}
                        </div>
                        <div>
                          <div className="font-semibold text-slate-900">{broker.name}</div>
                          {broker.promoText && (
                            <div className="text-[10px] text-emerald-700 mt-0.5">{broker.promoText}</div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-4 text-center font-medium text-slate-800">{broker.brokerage}</td>
                    <td className="px-3 py-4 text-center text-slate-600">{broker.platformFee}</td>
                    <td className="px-3 py-4 text-center text-slate-600">{broker.minDeposit}</td>
                    <td className="px-3 py-4 text-center"><TrileanIcon value={broker.chess} /></td>
                    <td className="px-3 py-4 text-center"><TrileanIcon value={broker.international} /></td>
                    <td className="px-3 py-4 text-center"><TrileanIcon value={broker.fractional} /></td>
                    <td className="px-3 py-4 text-center">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${RESEARCH_LABEL[broker.research].cls}`}>
                        {RESEARCH_LABEL[broker.research].label}
                      </span>
                    </td>
                    <td className="px-3 py-4 text-slate-500 text-xs max-w-[160px]">{broker.bestFor}</td>
                    <td className="px-3 py-4">
                      <a
                        href={broker.affiliateUrl}
                        target="_blank"
                        rel="noopener noreferrer sponsored"
                        className="flex items-center gap-1 text-blue-600 hover:text-blue-800 font-medium whitespace-nowrap text-xs"
                      >
                        Open <ExternalLink className="w-3 h-3" />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* CHESS explanation */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <h3 className="font-bold text-slate-900 mb-3 flex items-center gap-2">
            <Shield className="w-5 h-5 text-blue-600" />
            CHESS vs Custodial — what's the difference?
          </h3>
          <p className="text-sm text-slate-600 leading-relaxed mb-3">
            <strong>CHESS-sponsored</strong> (Clearing House Electronic Subregister System) means shares are registered directly in your name with the ASX. You hold a Holder Identification Number (HIN) and legally own the shares.
          </p>
          <p className="text-sm text-slate-600 leading-relaxed">
            <strong>Custodial</strong> brokers hold shares in an omnibus account on your behalf. Cheaper to operate, but you rely on the broker's solvency. Fine for most investors, but important to understand.
          </p>
        </div>
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <h3 className="font-bold text-slate-900 mb-3 flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-500" />
            How to choose the right broker
          </h3>
          <ul className="space-y-2 text-sm text-slate-600">
            <li className="flex gap-2"><span className="text-blue-600 font-bold shrink-0">1.</span> Consider how often you trade — flat fees suit frequent buyers, percentage-based suit large single trades.</li>
            <li className="flex gap-2"><span className="text-blue-600 font-bold shrink-0">2.</span> If you want international stocks (US, ETFs), check international access.</li>
            <li className="flex gap-2"><span className="text-blue-600 font-bold shrink-0">3.</span> Long-term buy-and-hold? Prioritise CHESS sponsorship and low/no platform fees.</li>
            <li className="flex gap-2"><span className="text-blue-600 font-bold shrink-0">4.</span> Need research and analysis tools? CommSec and nabtrade lead here.</li>
          </ul>
        </div>
      </div>

      {/* FAQ */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-5">Frequently Asked Questions</h2>
        <div className="space-y-5">
          {[
            {
              q: 'Is my money safe if an Australian broker collapses?',
              a: 'CHESS-sponsored brokers register shares in your name with the ASX, so shares remain yours if the broker fails. With custodial brokers, shares are held in trust but recovery may be more complex. Cash in trading accounts may be covered by the Financial Claims Scheme (FCS) up to $250,000 for ADI-linked accounts.',
            },
            {
              q: 'Do I need to pay tax on share trading in Australia?',
              a: 'Yes. Capital gains and dividends are taxable in Australia. Shares held for 12+ months qualify for the 50% CGT discount. Fully-franked dividends come with franking credits you can offset against your tax. Consider speaking with an accountant. ASX Screener helps you track your portfolio cost basis and dividend income.',
            },
            {
              q: 'Which broker is best for ETF investing?',
              a: 'Pearler and Superhero are popular for passive ETF investing — Superhero offers zero brokerage on certain ETF purchases. Pearler has an auto-invest feature to set-and-forget. CMC Invest also offers zero brokerage on trades under $1,000.',
            },
            {
              q: 'Can I use multiple brokers?',
              a: 'Absolutely. Many investors use a low-cost broker like SelfWealth for regular purchases and CommSec or nabtrade for research tools. There\'s no restriction on holding multiple brokerage accounts in Australia.',
            },
          ].map(({ q, a }) => (
            <div key={q} className="border-b border-slate-100 pb-5 last:border-0 last:pb-0">
              <div className="font-semibold text-slate-800 mb-1.5 text-sm">{q}</div>
              <div className="text-sm text-slate-600 leading-relaxed">{a}</div>
            </div>
          ))}
        </div>
      </div>

    </div>
    </PlanGate>
  )
}
