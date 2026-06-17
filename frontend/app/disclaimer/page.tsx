import type { Metadata } from 'next'
import { AlertTriangle, Scale, BookOpen } from 'lucide-react'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'Disclaimer | ASX Screener',
  description: 'ASX Screener is an educational and research tool, not a financial adviser. Read our full disclaimer before using any information on this site.',
  alternates: { canonical: 'https://asxscreener.com.au/disclaimer' },
}

export default function DisclaimerPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      <div>
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center shrink-0">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Disclaimer</h1>
        </div>
        <p className="text-sm text-slate-500">Last updated: June 2026</p>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6">
        <p className="font-semibold text-amber-900 mb-2">Important — please read before using ASX Screener</p>
        <p className="text-sm text-amber-800 leading-relaxed">
          ASX Screener is an educational research and stock screening tool. It is <strong>not a financial adviser</strong>, stockbroker, or investment service. Nothing on this website constitutes financial advice, a recommendation to buy or sell any security, or a prediction of future performance.
        </p>
      </div>

      <div className="space-y-6 text-slate-700 leading-relaxed">

        <section>
          <h2 className="text-lg font-bold text-slate-900 mb-2">Not Financial Advice</h2>
          <p className="text-sm">
            All content on ASX Screener — including screener results, financial metrics, composite scores, AI-generated insights, education articles, glossary definitions, and any other information — is provided for <strong>educational and research purposes only</strong>. It does not constitute financial product advice within the meaning of the <em>Corporations Act 2001</em> (Cth).
          </p>
          <p className="text-sm mt-2">
            ASX Screener does not hold an Australian Financial Services Licence (AFSL). If you need financial advice, please consult a licensed financial adviser who is registered with ASIC.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-slate-900 mb-2">No Stock Recommendations</h2>
          <p className="text-sm">
            ASX Screener does not recommend any specific stock, security, or investment strategy. Screener results, scan outputs, composite scores, and Top 5 strategy outputs are research tools that surface data matching defined criteria — they are not buy, sell, or hold recommendations. Past screener results do not predict future performance.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-slate-900 mb-2">DYOR — Do Your Own Research</h2>
          <p className="text-sm">
            Any investment decision you make is your own responsibility. Before acting on any information from ASX Screener, you should conduct your own independent research, consider your personal financial circumstances, investment objectives, and risk tolerance, and consult a qualified financial adviser if needed.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-slate-900 mb-2">Data Accuracy</h2>
          <p className="text-sm">
            Financial data displayed on ASX Screener is sourced from third-party providers and ASX company filings. While we make reasonable efforts to maintain accuracy, we do not guarantee that any data is complete, accurate, current, or free from errors. Data may be delayed, estimated, or subject to revision. Always verify important financial data from primary sources (ASX announcements, company annual reports) before making any investment decision.
          </p>
          <p className="text-sm mt-2">
            See our <Link href="/data-freshness" className="text-blue-600 hover:underline">Data Freshness Policy</Link> for details on how frequently each data type is updated.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-slate-900 mb-2">AI Insights Limitations</h2>
          <p className="text-sm">
            AI-generated insights on ASX Screener are produced by large language models and may contain errors, omissions, or outdated information. AI outputs must not be relied upon as financial advice. They are provided as a research aid only.
          </p>
          <p className="text-sm mt-2">
            See our <Link href="/ai-insights-limitations" className="text-blue-600 hover:underline">AI Insights Limitations</Link> page for full details.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-slate-900 mb-2">No Liability</h2>
          <p className="text-sm">
            To the maximum extent permitted by law, ASX Screener and its operators accept no liability for any loss or damage (including loss of profits, investment loss, or consequential loss) arising from your use of, or reliance on, any information or tools provided on this website. Your use of ASX Screener is entirely at your own risk.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-bold text-slate-900 mb-2">External Links</h2>
          <p className="text-sm">
            ASX Screener may contain links to third-party websites, broker platforms, or course providers. We do not endorse or take responsibility for the content, accuracy, or reliability of any external site. Some links may be affiliate links — see our <Link href="/terms" className="text-blue-600 hover:underline">Terms of Service</Link> for disclosure.
          </p>
        </section>

      </div>

      <div className="flex flex-wrap gap-3 pt-4 border-t border-slate-200">
        {[
          { href: '/terms', label: 'Terms of Service', icon: Scale },
          { href: '/privacy', label: 'Privacy Policy', icon: Scale },
          { href: '/data-freshness', label: 'Data Freshness', icon: BookOpen },
          { href: '/ai-insights-limitations', label: 'AI Insights Limitations', icon: BookOpen },
        ].map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 hover:underline">
            <Icon className="w-3.5 h-3.5 shrink-0" />
            {label}
          </Link>
        ))}
      </div>
    </div>
  )
}
