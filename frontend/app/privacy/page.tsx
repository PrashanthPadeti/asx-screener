import Link from 'next/link'
import { ShieldCheck, AlertTriangle } from 'lucide-react'

export const metadata = {
  title: 'Privacy Policy | ASX Screener',
  description: 'How ASX Screener collects, uses, and protects your personal information under the Australian Privacy Act 1988.',
}

const UPDATED = 'May 2026 (Revised)'

const SECTIONS = [
  'Overview',
  'Information We Collect',
  'How We Use Your Information',
  'Information Sharing & Overseas Disclosure',
  'Data Storage, Security & Breach Notification',
  'Cookies & Tracking',
  '6A. Automated Decision-Making',
  'Your Privacy Rights',
  'Data Retention',
  "Children's Privacy",
  'Changes to This Policy',
  'Contact Us',
]

export default function PrivacyPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">

      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck className="w-6 h-6 text-blue-600 shrink-0" />
          <span className="text-sm font-medium text-blue-600">ASX Screener</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Privacy Policy</h1>
        <p className="text-sm text-slate-400">Last updated: {UPDATED}</p>
        <div className="mt-3 bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
          <strong>Updates in this revision:</strong> Added overseas data transfer disclosures (Section 4),
          automated decision-making disclosure (Section 6A), data breach notification commitment
          (Section 5), and enhanced cookie consent guidance (Section 6).
        </div>
        <p className="mt-3 text-slate-600 leading-relaxed">
          ASX Screener (&quot;we&quot;, &quot;us&quot;, or &quot;our&quot;) is committed to protecting your personal
          information. This policy explains how we collect, use, and safeguard your data in
          accordance with the <strong>Australian Privacy Act 1988 (Cth)</strong> and the Australian
          Privacy Principles (APPs).
        </p>
      </div>

      {/* Quick nav */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5">
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-3">Contents</p>
        <ol className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
          {SECTIONS.map((s, i) => {
            const label = s.startsWith('6A.') ? s : `${i + 1}. ${s}`
            const anchor = s.startsWith('6A.') ? 'section-6a' : `section-${i + 1}`
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

      {/* 1 — Overview */}
      <section id="section-1" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">1. Overview</h2>
        <p className="text-slate-700 leading-relaxed">
          ASX Screener is an Australian financial data platform that allows users to screen,
          research, and track ASX-listed companies. We operate the website at{' '}
          <strong>asxscreener.com.au</strong>.
        </p>
        <p className="text-slate-700 leading-relaxed">
          By using ASX Screener you agree to the collection and use of information in accordance
          with this policy. If you do not agree, please do not use our services.
        </p>
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
          <strong>Not financial advice.</strong> ASX Screener provides informational data only. Nothing
          on this platform constitutes financial advice. See our{' '}
          <Link href="/terms" className="underline font-medium">Terms of Service</Link> for full details.
        </div>
      </section>

      {/* 2 — Information We Collect */}
      <section id="section-2" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">2. Information We Collect</h2>

        <h3 className="font-semibold text-slate-800">Information you provide directly</h3>
        <ul className="list-disc list-inside space-y-1 text-slate-700 text-sm leading-relaxed">
          <li><strong>Account data:</strong> name, email address, and hashed password when you register</li>
          <li><strong>Subscription data:</strong> billing details processed by Stripe (we do not store card numbers)</li>
          <li><strong>Support requests:</strong> name, email, phone (optional), and any attachments you submit via the contact form</li>
          <li><strong>User content:</strong> watchlists, portfolios, saved screens, price alerts, and notes you create</li>
        </ul>

        <h3 className="font-semibold text-slate-800 mt-4">Information collected automatically</h3>
        <ul className="list-disc list-inside space-y-1 text-slate-700 text-sm leading-relaxed">
          <li><strong>Usage data:</strong> pages visited, features used, search queries, click events</li>
          <li><strong>Device data:</strong> IP address, browser type, operating system, screen resolution</li>
          <li><strong>Log data:</strong> server access logs, error logs, API request timestamps</li>
          <li><strong>Cookies:</strong> session tokens, preference cookies (see Section 6)</li>
        </ul>
      </section>

      {/* 3 — How We Use */}
      <section id="section-3" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">3. How We Use Your Information</h2>
        <p className="text-slate-700 leading-relaxed">We use your information to:</p>
        <ul className="list-disc list-inside space-y-1.5 text-slate-700 text-sm leading-relaxed">
          <li>Provide, maintain, and improve the ASX Screener platform</li>
          <li>Create and manage your account and subscription</li>
          <li>Process payments via Stripe</li>
          <li>Send transactional emails: email verification, password resets, subscription receipts, price alerts</li>
          <li>Respond to support requests and troubleshoot issues</li>
          <li>Detect and prevent fraud, abuse, or security incidents</li>
          <li>Analyse aggregate usage patterns to improve features (never sold to third parties)</li>
          <li>Send occasional product update emails (you can unsubscribe at any time)</li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          We only process personal information where we have a lawful basis — typically to perform
          our contract with you (delivering the service), comply with legal obligations, or based on
          your consent.
        </p>
      </section>

      {/* 4 — Sharing & Overseas Disclosure */}
      <section id="section-4" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">4. Information Sharing & Overseas Disclosure</h2>
        <p className="text-slate-700 leading-relaxed">
          <strong>We do not sell your personal information.</strong> We share data only with the
          following trusted service providers, limited to what they need to perform their function:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-slate-50 border border-slate-200">
                <th className="px-3 py-2 text-left font-semibold text-slate-700">Provider</th>
                <th className="px-3 py-2 text-left font-semibold text-slate-700">Purpose</th>
                <th className="px-3 py-2 text-left font-semibold text-slate-700">Data shared</th>
                <th className="px-3 py-2 text-left font-semibold text-slate-700">Country</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Stripe', 'Payment processing', 'Name, email, billing details', 'United States'],
                ['Resend', 'Transactional email delivery', 'Name, email address', 'United States'],
                ['DigitalOcean', 'Cloud infrastructure & storage', 'All user data (encrypted at rest)', 'Australia (Sydney)'],
                ['EODHD / FMP', 'Market data provider', 'No user data — API calls only', 'N/A'],
                ['Google Analytics', 'Aggregate usage analytics', 'Anonymised usage events', 'United States'],
              ].map(([p, pu, d, c]) => (
                <tr key={p} className="border border-slate-200">
                  <td className="px-3 py-2 font-medium text-slate-800">{p}</td>
                  <td className="px-3 py-2 text-slate-600">{pu}</td>
                  <td className="px-3 py-2 text-slate-600">{d}</td>
                  <td className="px-3 py-2 text-slate-600">{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 space-y-2">
          <p className="font-semibold text-slate-800">Overseas data transfers (APP 8)</p>
          <p className="leading-relaxed">
            Some of our service providers process personal information outside Australia, primarily in
            the United States. Before disclosing your information to an overseas recipient, we take
            reasonable steps to ensure that the overseas recipient does not breach the Australian
            Privacy Principles in relation to the information. We do this by reviewing each
            provider&apos;s privacy and security practices, entering into contractual arrangements
            that require the provider to handle personal information in accordance with the APPs, and
            conducting periodic reviews of their compliance. By using ASX Screener, you acknowledge
            and consent to the transfer of your personal information to these overseas recipients for
            the purposes described in this policy.
          </p>
        </div>

        <p className="text-slate-700 text-sm leading-relaxed">
          We may also disclose information if required by Australian law, court order, or to
          protect the rights, property, or safety of ASX Screener, our users, or the public.
        </p>
      </section>

      {/* 5 — Storage, Security & Breach Notification */}
      <section id="section-5" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">5. Data Storage, Security & Breach Notification</h2>
        <p className="text-slate-700 leading-relaxed">
          Your data is stored on <strong>DigitalOcean infrastructure in the Sydney (SYD1) region</strong>,
          keeping your data in Australia. We implement industry-standard security measures:
        </p>
        <ul className="list-disc list-inside space-y-1 text-slate-700 text-sm leading-relaxed">
          <li>All data in transit encrypted via TLS/HTTPS</li>
          <li>Passwords hashed using bcrypt (never stored in plain text)</li>
          <li>Database access restricted to application servers only</li>
          <li>Regular automated backups with point-in-time recovery</li>
          <li>Payment data handled entirely by Stripe — we never store card details</li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          No system is 100% secure. If you become aware of a security issue, please contact us
          immediately at{' '}
          <a href="mailto:asxscreener@gmail.com" className="text-blue-600 hover:underline">
            asxscreener@gmail.com
          </a>.
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 space-y-2">
          <p className="font-semibold text-slate-800">Data breach notification (NDB scheme)</p>
          <p className="leading-relaxed">
            In the event of an eligible data breach that is likely to result in serious harm to any
            individual whose personal information is involved, we will notify the Office of the
            Australian Information Commissioner (OAIC) and affected individuals as soon as
            practicable, and in any case within the timeframes required under the{' '}
            <em>Privacy Act 1988</em>. We maintain a documented data breach response plan that is
            reviewed and tested annually.
          </p>
        </div>
      </section>

      {/* 6 — Cookies */}
      <section id="section-6" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">6. Cookies & Tracking</h2>
        <p className="text-slate-700 leading-relaxed">We use the following types of cookies:</p>
        <ul className="list-disc list-inside space-y-1.5 text-slate-700 text-sm leading-relaxed">
          <li>
            <strong>Essential cookies:</strong> Authentication session tokens required for you to
            stay logged in. These cannot be disabled without breaking the service.
          </li>
          <li>
            <strong>Preference cookies:</strong> Remember your screener column preferences, theme
            settings, and filter defaults.
          </li>
          <li>
            <strong>Analytics cookies:</strong> Google Analytics collects anonymised page-view and
            event data. You can opt out via browser settings or{' '}
            <a href="https://tools.google.com/dlpage/gaoptout" target="_blank" rel="noopener noreferrer"
               className="text-blue-600 hover:underline">
              Google&apos;s opt-out tool
            </a>.
          </li>
        </ul>
        <p className="text-slate-700 text-sm">
          We do not use advertising or cross-site tracking cookies.
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 space-y-2">
          <p className="font-semibold text-slate-800">Cookie consent</p>
          <p className="leading-relaxed">
            When you first visit ASX Screener, a cookie consent banner will allow you to accept or
            reject non-essential cookies (including analytics cookies) before they are set. You can
            change your cookie preferences at any time via the cookie settings link in the website
            footer. Essential cookies required for the service to function cannot be disabled.
          </p>
        </div>
      </section>

      {/* 6A — Automated Decision-Making — NEW */}
      <section id="section-6a" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">6A. Automated Decision-Making</h2>
        <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-2 text-xs text-blue-700 font-medium inline-block mb-1">
          New section — added to comply with Privacy Act 2024 amendments (effective December 2026).
        </div>
        <p className="text-slate-700 leading-relaxed">
          ASX Screener uses substantially automated processes in the following areas:
        </p>
        <ul className="list-disc list-inside space-y-2 text-slate-700 text-sm leading-relaxed">
          <li>
            <strong>AI-powered stock screener:</strong> Our natural language screener uses artificial
            intelligence to interpret your search queries and apply corresponding financial and
            technical filters to publicly available market data. The screener output is a mechanical
            application of filters to data — it does not constitute a recommendation or financial advice.
          </li>
          <li>
            <strong>Price alerts:</strong> Automated monitoring systems check market data against your
            configured alert thresholds and send notifications when conditions are met.
          </li>
          <li>
            <strong>Fraud and abuse detection:</strong> We use automated systems to detect unusual
            account activity, including multiple failed login attempts and suspicious usage patterns.
            These systems may result in temporary account restrictions.
          </li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          These automated processes apply rules and algorithms to data without human review of
          individual outputs. If you believe an automated decision has adversely affected you, you
          may contact us at{' '}
          <a href="mailto:asxscreener@gmail.com" className="text-blue-600 hover:underline">
            asxscreener@gmail.com
          </a>{' '}
          to request a review by a human.
        </p>
      </section>

      {/* 7 — Your Rights */}
      <section id="section-7" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">7. Your Privacy Rights</h2>
        <p className="text-slate-700 leading-relaxed">
          Under the Australian Privacy Principles you have the right to:
        </p>
        <ul className="list-disc list-inside space-y-1.5 text-slate-700 text-sm leading-relaxed">
          <li><strong>Access</strong> the personal information we hold about you</li>
          <li><strong>Correct</strong> inaccurate or out-of-date information</li>
          <li><strong>Delete</strong> your account and associated personal data</li>
          <li><strong>Withdraw consent</strong> for optional communications (unsubscribe links in all emails)</li>
          <li><strong>Lodge a complaint</strong> with the{' '}
            <a href="https://www.oaic.gov.au" target="_blank" rel="noopener noreferrer"
               className="text-blue-600 hover:underline">
              Office of the Australian Information Commissioner (OAIC)
            </a>
          </li>
        </ul>
        <p className="text-slate-700 text-sm leading-relaxed">
          To exercise any of these rights, email us at{' '}
          <a href="mailto:asxscreener@gmail.com" className="text-blue-600 hover:underline">
            asxscreener@gmail.com
          </a>{' '}
          with the subject line &quot;Privacy Request&quot;. We will respond within 30 days.
        </p>
      </section>

      {/* 8 — Retention */}
      <section id="section-8" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">8. Data Retention</h2>
        <ul className="list-disc list-inside space-y-1.5 text-slate-700 text-sm leading-relaxed">
          <li><strong>Account data:</strong> retained while your account is active; deleted within 30 days of account deletion request</li>
          <li><strong>Billing records:</strong> retained for 7 years as required by Australian tax law</li>
          <li><strong>Support tickets:</strong> retained for 3 years for quality assurance, then deleted</li>
          <li><strong>Usage/analytics data:</strong> anonymised after 26 months</li>
          <li><strong>Server logs:</strong> rotated after 90 days</li>
        </ul>
      </section>

      {/* 9 — Children */}
      <section id="section-9" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">9. Children&apos;s Privacy</h2>
        <p className="text-slate-700 leading-relaxed">
          ASX Screener is intended for users aged <strong>18 years and over</strong>. We do not
          knowingly collect personal information from anyone under 18. If you believe a minor has
          provided us with personal information, please contact us and we will delete it promptly.
        </p>
      </section>

      {/* 10 — Changes */}
      <section id="section-10" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">10. Changes to This Policy</h2>
        <p className="text-slate-700 leading-relaxed">
          We may update this Privacy Policy from time to time. When we make material changes, we
          will notify you by email and update the &quot;Last updated&quot; date at the top of this page.
          Continued use of ASX Screener after changes are posted constitutes acceptance of the
          updated policy.
        </p>
      </section>

      {/* 11 — Contact */}
      <section id="section-11" className="space-y-3">
        <h2 className="text-xl font-bold text-slate-900">11. Contact Us</h2>
        <p className="text-slate-700 leading-relaxed">
          For any privacy-related queries, requests, or complaints:
        </p>
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm text-slate-700 space-y-1">
          <p><strong>ASX Screener</strong></p>
          <p>Email:{' '}
            <a href="mailto:asxscreener@gmail.com" className="text-blue-600 hover:underline">
              asxscreener@gmail.com
            </a>
          </p>
          <p>Website:{' '}
            <a href="https://asxscreener.com.au" className="text-blue-600 hover:underline">
              asxscreener.com.au
            </a>
          </p>
        </div>
        <p className="text-slate-600 text-sm">
          If you are not satisfied with our response you may lodge a complaint with the{' '}
          <a href="https://www.oaic.gov.au/privacy/privacy-complaints"
             target="_blank" rel="noopener noreferrer"
             className="text-blue-600 hover:underline">
            Office of the Australian Information Commissioner
          </a>.
        </p>
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
          This Privacy Policy was last updated {UPDATED}. Please also read our{' '}
          <Link href="/terms" className="font-semibold underline">Terms of Service</Link> and our{' '}
          <Link href="/contact" className="font-semibold underline">Contact Support</Link> page.
        </p>
      </div>

    </div>
  )
}
