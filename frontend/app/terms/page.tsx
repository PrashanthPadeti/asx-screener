import Link from 'next/link'
import { Scale, AlertTriangle } from 'lucide-react'

export const metadata = {
  title: 'Terms of Service | ASX Screener',
  description: 'Terms and conditions for using ASX Screener — subscription, cancellation, refunds, data accuracy, and acceptable use.',
}

const UPDATED = 'May 2026 (Revised)'

const SECTIONS = [
  'Acceptance of Terms',
  'Service Description',
  'Not Financial Advice',
  'Account Registration',
  'Subscription & Billing',
  'Cancellation & Refunds',
  'Acceptable Use',
  'Intellectual Property',
  'Data Accuracy Disclaimer',
  'Third-Party Services & Affiliate Disclosure',
  'Limitation of Liability',
  'Australian Consumer Law',
  'Governing Law',
  '13A. Dispute Resolution',
  'Amendments',
  'Contact',
]

export default function TermsPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">

      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Scale className="w-6 h-6 text-blue-600 shrink-0" />
          <span className="text-sm font-medium text-blue-600">ASX Screener</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Terms of Service</h1>
        <p className="text-sm text-slate-400">Last updated: {UPDATED}</p>
        <div className="mt-3 bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
          <strong>Updates in this revision:</strong> Strengthened AI screener disclaimer (Section 3),
          enhanced affiliate disclosure requirements (Section 10), improved refund terms (Section 6),
          added dispute resolution procedure (Section 13A).
        </div>
        <p className="mt-3 text-slate-600 leading-relaxed">
          These Terms of Service (&quot;Terms&quot;) govern your access to and use of ASX Screener
          (&quot;we&quot;, &quot;us&quot;, &quot;our&quot;) at <strong>asxscreener.com.au</strong>. By
          accessing or using our services you agree to be bound by these Terms. If you do not
          agree, please do not use our platform.
        </p>
      </div>

      {/* Quick nav */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">Contents</p>
        <ol className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
          {SECTIONS.map((s, i) => {
            const label = s.startsWith('13A.') ? s : `${i + 1}. ${s}`
            const anchor = s.startsWith('13A.') ? 'term-13a' : `term-${i + 1}`
            return (
              <li key={s}>
                <a href={`#${anchor}`} className="text-sm text-blue-600 hover:underline">
                  {label}
                </a>
              </li>
            )
          })}
        </ol>
      </div>

      {/* 1 — Acceptance */}
      <section id="term-1" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">1. Acceptance of Terms</h2>
        <p className="text-slate-700 leading-relaxed">
          By creating an account, subscribing to a paid plan, or otherwise using ASX Screener, you
          confirm that you are at least 18 years old, have the legal capacity to enter into a
          binding agreement, and agree to these Terms and our{' '}
          <Link href="/privacy" className="text-blue-600 hover:underline">Privacy Policy</Link>.
        </p>
        <p className="text-slate-700 leading-relaxed">
          These Terms constitute the entire agreement between you and ASX Screener and supersede
          all prior communications regarding your use of the platform.
        </p>
      </section>

      {/* 2 — Service Description */}
      <section id="term-2" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">2. Service Description</h2>
        <p className="text-slate-700 leading-relaxed">
          ASX Screener provides an online platform for researching ASX-listed securities, including:
        </p>
        <ul className="list-disc list-inside space-y-1 text-slate-700 text-sm leading-relaxed">
          <li>Stock screener with 80+ financial and technical filters</li>
          <li>Company financial data, price history, and announcements</li>
          <li>Watchlists, portfolios, and price alerts</li>
          <li>Educational content, glossary, and broker comparisons</li>
          <li>AI-powered natural language screener (Pro/Premium plans)</li>
        </ul>
        <p className="text-slate-700 leading-relaxed">
          We reserve the right to modify, suspend, or discontinue any part of the service at any
          time with reasonable notice where practicable.
        </p>
      </section>

      {/* 3 — NOT financial advice — KEY SECTION */}
      <section id="term-3" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">3. Not Financial Advice</h2>
        <div className="bg-amber-50 border-2 border-amber-300 rounded-2xl p-5 space-y-3">
          <p className="font-bold text-amber-900 text-base">
            ⚠️ ASX Screener does not provide financial product advice.
          </p>
          <p className="text-amber-800 text-sm leading-relaxed">
            All content, data, screener results, AI-generated queries, broker comparisons,
            educational articles, and any other information on ASX Screener is provided for
            <strong> general informational and educational purposes only</strong>. Nothing on this
            platform constitutes:
          </p>
          <ul className="list-disc list-inside space-y-1 text-amber-800 text-sm leading-relaxed">
            <li>A recommendation or opinion to buy, sell, or hold any financial product</li>
            <li>Financial product advice as defined under the{' '}
              <em>Corporations Act 2001 (Cth)</em></li>
            <li>An offer or invitation to apply for any financial product</li>
            <li>Accounting, legal, or tax advice</li>
          </ul>
          <p className="text-amber-800 text-sm leading-relaxed">
            <strong>You must not rely on any information on ASX Screener as the basis for making
            investment decisions.</strong> Always conduct your own research (DYOR) and consider
            seeking advice from a licensed financial adviser, accountant, or lawyer before making
            any investment decision.
          </p>
          <p className="text-amber-800 text-sm leading-relaxed">
            ASX Screener does not hold an Australian Financial Services Licence (AFSL). Screener
            results, rankings, and AI outputs are generated by algorithms applied to publicly
            available data — they are tools for your own research, not recommendations.
          </p>
        </div>

        {/* AI screener disclaimer — new */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 space-y-2">
          <p className="font-semibold text-slate-800">AI-powered screener disclaimer</p>
          <p className="leading-relaxed">
            The AI-powered natural language screener is a software tool that mechanically translates
            your plain-language queries into structured database filters applied to publicly available
            market data. The AI does not analyse, evaluate, or form opinions on the merits of any
            security. Screener outputs reflect the mechanical application of your specified criteria —
            they are not curated, ranked by investment merit, or selected based on any assessment of
            value, quality, or suitability. The inclusion of any security in screener results does not
            constitute a recommendation. You are solely responsible for evaluating the suitability of
            any security for your circumstances.
          </p>
        </div>
      </section>

      {/* 4 — Account Registration */}
      <section id="term-4" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">4. Account Registration</h2>
        <p className="text-slate-700 leading-relaxed">
          You are responsible for maintaining the confidentiality of your account credentials and
          for all activity that occurs under your account. You must:
        </p>
        <ul className="list-disc list-inside space-y-1 text-slate-700 text-sm leading-relaxed">
          <li>Provide accurate and current registration information</li>
          <li>Notify us immediately of any unauthorised use of your account</li>
          <li>Not share your login credentials with any third party</li>
          <li>Not create multiple accounts to circumvent plan limits or restrictions</li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          We reserve the right to suspend or terminate accounts that violate these Terms or that
          we reasonably believe have been compromised.
        </p>
      </section>

      {/* 5 — Subscription & Billing */}
      <section id="term-5" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">5. Subscription & Billing</h2>
        <p className="text-slate-700 leading-relaxed">
          Paid plans (Pro and Premium) are available on a monthly or annual basis. All prices are
          in <strong>Australian Dollars (AUD)</strong> and include GST where applicable.
        </p>
        <ul className="list-disc list-inside space-y-1.5 text-slate-700 text-sm leading-relaxed">
          <li>
            <strong>Automatic renewal:</strong> Subscriptions automatically renew at the end of
            each billing period unless cancelled before the renewal date.
          </li>
          <li>
            <strong>Billing:</strong> Payments are processed by Stripe. By subscribing you
            authorise us to charge your payment method on a recurring basis.
          </li>
          <li>
            <strong>Price changes:</strong> We will give at least 30 days&apos; notice before
            changing subscription prices. Continued use after the effective date constitutes
            acceptance of the new price.
          </li>
          <li>
            <strong>Failed payments:</strong> If a payment fails, access to paid features may be
            suspended until payment is resolved.
          </li>
          <li>
            <strong>GST:</strong> Where applicable under Australian tax law, GST will be included
            in the price displayed at checkout.
          </li>
        </ul>
      </section>

      {/* 6 — Cancellation & Refunds */}
      <section id="term-6" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">6. Cancellation & Refunds</h2>

        <h3 className="font-semibold text-slate-800">Cancellation</h3>
        <p className="text-slate-700 text-sm leading-relaxed">
          You may cancel your subscription at any time from your Account page. Cancellation takes
          effect at the end of the current billing period — you retain access to paid features
          until that date.
        </p>

        <h3 className="font-semibold text-slate-800 mt-3">Refunds</h3>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 space-y-2">
          <p>
            <strong>Monthly plans:</strong> No refund is provided for the current billing period.
            Cancel before the next renewal date to avoid being charged again.
          </p>
          <p>
            <strong>Annual plans:</strong> You may request a <strong>full refund within 30 days</strong>{' '}
            of your annual subscription start or renewal date. After 30 days, you may request a{' '}
            <strong>pro-rata refund</strong> for the unused portion of your subscription at any time
            by contacting{' '}
            <a href="mailto:asxscreener@gmail.com" className="text-blue-600 hover:underline">
              asxscreener@gmail.com
            </a>. Refunds will be processed within 14 business days.
          </p>
          <p>
            <strong>Exceptional circumstances:</strong> We will consider refund requests on a
            case-by-case basis where there has been a billing error, significant service outage, or
            other exceptional circumstances. Contact{' '}
            <a href="mailto:asxscreener@gmail.com" className="text-blue-600 hover:underline">
              asxscreener@gmail.com
            </a>.
          </p>
        </div>
        <p className="text-slate-700 text-sm leading-relaxed">
          Nothing in this section limits your rights under the{' '}
          <strong>Australian Consumer Law</strong> — see Section 12.
        </p>
      </section>

      {/* 7 — Acceptable Use */}
      <section id="term-7" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">7. Acceptable Use</h2>
        <p className="text-slate-700 leading-relaxed">You must not:</p>
        <ul className="list-disc list-inside space-y-1.5 text-slate-700 text-sm leading-relaxed">
          <li>Scrape, crawl, or systematically download data beyond personal research use</li>
          <li>Use automated tools to access the platform beyond the intended API access</li>
          <li>Reproduce, redistribute, or resell ASX Screener data or content commercially</li>
          <li>Attempt to circumvent plan limits, access controls, or authentication systems</li>
          <li>Upload malicious code, viruses, or harmful content via support attachments</li>
          <li>Use the service for any unlawful purpose under Australian or applicable law</li>
          <li>Impersonate ASX Screener or misrepresent your affiliation with us</li>
          <li>Interfere with or disrupt the integrity or performance of the service</li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          Violation of these rules may result in immediate account suspension without refund.
        </p>
      </section>

      {/* 8 — IP */}
      <section id="term-8" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">8. Intellectual Property</h2>
        <p className="text-slate-700 leading-relaxed">
          All original content on ASX Screener — including the software, user interface, screener
          methodology, AI models, editorial content, and branding — is owned by or licensed to ASX
          Screener and protected by Australian and international copyright, trademark, and other
          intellectual property laws.
        </p>
        <p className="text-slate-700 leading-relaxed">
          Market data (prices, financials) is sourced from third-party providers (EODHD, FMP, ASX)
          and is subject to their respective terms. You may use data accessed through ASX Screener
          for your own personal research only.
        </p>
        <p className="text-slate-700 leading-relaxed">
          You retain ownership of content you create on the platform (watchlists, notes, saved
          screens). By using the service, you grant us a limited licence to store and display this
          content to deliver the service.
        </p>
      </section>

      {/* 9 — Data Accuracy */}
      <section id="term-9" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">9. Data Accuracy Disclaimer</h2>
        <p className="text-slate-700 leading-relaxed">
          Financial data displayed on ASX Screener is sourced from third-party providers and
          publicly available sources. While we take reasonable care to ensure accuracy:
        </p>
        <ul className="list-disc list-inside space-y-1.5 text-slate-700 text-sm leading-relaxed">
          <li>Data may contain errors, omissions, or delays</li>
          <li>Historical data may be restated or adjusted without notice</li>
          <li>Real-time data may be subject to exchange delays (typically 20 minutes)</li>
          <li>Screener results depend on data quality and should be independently verified</li>
          <li>AI-generated screener outputs mechanically interpret your query and apply filters —
              they are not verified by humans and do not constitute recommendations</li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          <strong>You are solely responsible for verifying any data before relying on it.</strong>{' '}
          Always cross-reference with the ASX Market Announcements Platform
          (asx.com.au) and the company&apos;s official filings.
        </p>
      </section>

      {/* 10 — Third-Party Services & Affiliate Disclosure */}
      <section id="term-10" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">10. Third-Party Services & Affiliate Disclosure</h2>
        <p className="text-slate-700 leading-relaxed">
          ASX Screener links to or integrates with third-party services including broker platforms,
          educational courses, and data providers. These links are provided for your convenience
          and do not constitute an endorsement. Third-party services have their own terms of
          service and privacy policies that you should review independently.
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 space-y-2">
          <p className="font-semibold text-slate-800">Affiliate disclosure</p>
          <p className="leading-relaxed">
            ASX Screener participates in affiliate programmes with certain stockbrokers. Where we
            provide a link to a broker and you subsequently open an account, we may receive a referral
            fee from that broker. This affiliate relationship is disclosed prominently on our{' '}
            <Link href="/brokers" className="text-blue-600 hover:underline">Broker Compare</Link>{' '}
            page with a clear notice adjacent to each affiliate link. Affiliate relationships do
            <strong> not</strong> influence the inclusion, exclusion, or ordering of brokers on our
            comparison pages. Broker comparisons are based on publicly available fee schedules,
            platform features, and account types. We encourage you to independently verify all broker
            information and compare options before opening an account.
          </p>
        </div>
      </section>

      {/* 11 — Limitation of Liability */}
      <section id="term-11" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">11. Limitation of Liability</h2>
        <p className="text-slate-700 leading-relaxed">
          To the maximum extent permitted by Australian law:
        </p>
        <ul className="list-disc list-inside space-y-1.5 text-slate-700 text-sm leading-relaxed">
          <li>ASX Screener is provided &quot;as is&quot; without warranties of any kind, express or implied</li>
          <li>We are not liable for any investment loss, financial loss, or consequential damage
              arising from your use of — or reliance on — any information on the platform</li>
          <li>We are not liable for data errors, service interruptions, or third-party service failures</li>
          <li>Our total aggregate liability to you for any claim shall not exceed the total amount
              you paid us in the 3 months preceding the claim</li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          These limitations apply regardless of the legal theory under which the claim arises
          (contract, tort, statute) and even if we have been advised of the possibility of such loss.
        </p>
      </section>

      {/* 12 — ACL */}
      <section id="term-12" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">12. Australian Consumer Law</h2>
        <p className="text-slate-700 leading-relaxed">
          Nothing in these Terms excludes, restricts, or modifies any consumer guarantee, right,
          or remedy conferred by the <strong>Australian Consumer Law</strong> (Schedule 2 of the{' '}
          <em>Competition and Consumer Act 2010 (Cth)</em>) that cannot be lawfully excluded.
        </p>
        <p className="text-slate-700 leading-relaxed">
          Where our liability cannot be excluded, it is limited to the extent permitted — for
          services, to re-supplying the service or paying the cost of re-supply.
        </p>
      </section>

      {/* 13 — Governing Law */}
      <section id="term-13" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">13. Governing Law</h2>
        <p className="text-slate-700 leading-relaxed">
          These Terms are governed by the laws of <strong>New South Wales, Australia</strong>. You
          agree to submit to the exclusive jurisdiction of the courts of New South Wales for any
          dispute arising under these Terms, subject to any rights you have under the Australian
          Consumer Law.
        </p>
      </section>

      {/* 13A — Dispute Resolution — NEW */}
      <section id="term-13a" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">13A. Dispute Resolution</h2>
        <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-2 text-xs text-blue-700 font-medium inline-block mb-1">
          New section — structured dispute resolution process before court proceedings.
        </div>
        <p className="text-slate-700 leading-relaxed">
          Before commencing any court proceedings in relation to a dispute arising under these Terms,
          the parties agree to follow this dispute resolution process:
        </p>
        <ul className="space-y-3 text-slate-700 text-sm leading-relaxed">
          <li className="flex gap-3">
            <span className="font-semibold text-slate-800 shrink-0">Step 1 — Informal resolution:</span>
            <span>The party raising the dispute must first contact the other party in writing, setting
            out the nature of the dispute and the outcome sought. The parties will use their best
            efforts to resolve the dispute informally within 21 days of receipt of the written notice.</span>
          </li>
          <li className="flex gap-3">
            <span className="font-semibold text-slate-800 shrink-0">Step 2 — Mediation:</span>
            <span>If the dispute is not resolved within 21 days, either party may refer the dispute
            to mediation administered by the Australian Disputes Centre (ADC) in Sydney, NSW. The
            costs of mediation will be shared equally between the parties unless the mediator
            determines otherwise.</span>
          </li>
          <li className="flex gap-3">
            <span className="font-semibold text-slate-800 shrink-0">Step 3 — Court proceedings:</span>
            <span>If the dispute is not resolved through mediation within 60 days of referral, either
            party may commence court proceedings in the courts of New South Wales.</span>
          </li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          Nothing in this clause prevents either party from seeking urgent injunctive or interlocutory
          relief from a court at any time. This dispute resolution clause does not limit your rights
          under the Australian Consumer Law.
        </p>
      </section>

      {/* 14 — Amendments */}
      <section id="term-14" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">14. Amendments</h2>
        <p className="text-slate-700 leading-relaxed">
          We may update these Terms from time to time. We will notify registered users by email
          of material changes at least 14 days before they take effect. Continued use of ASX
          Screener after the effective date constitutes acceptance of the updated Terms.
        </p>
      </section>

      {/* 15 — Contact */}
      <section id="term-15" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">15. Contact</h2>
        <p className="text-slate-700 leading-relaxed">
          Questions about these Terms? Contact us:
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 space-y-1">
          <p><strong>ASX Screener</strong></p>
          <p>Email:{' '}
            <a href="mailto:asxscreener@gmail.com" className="text-blue-600 hover:underline">
              asxscreener@gmail.com
            </a>
          </p>
          <p>Support:{' '}
            <Link href="/contact" className="text-blue-600 hover:underline">
              asxscreener.com.au/contact
            </Link>
          </p>
        </div>
      </section>

      {/* Footer disclaimer */}
      <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-700">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
        <p>
          The information provided on ASX Screener is for informational and educational purposes only.
          It does not constitute financial advice, a recommendation to buy or sell any security, or an
          offer of any kind. Past performance is not indicative of future results. All data is sourced
          from publicly available information and may contain errors or omissions. You should seek
          independent financial advice before making any investment decision. Always do your own
          research (DYOR).{' '}
          These Terms were last updated {UPDATED}. Please also read our{' '}
          <Link href="/privacy" className="font-semibold underline">Privacy Policy</Link>.
        </p>
      </div>

    </div>
  )
}
