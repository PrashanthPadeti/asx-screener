'use client'
/**
 * CookieConsent.tsx
 *
 * Cookie consent banner — Privacy Act 1988 (Cth) + GDPR compliance.
 *
 * Behaviour:
 *  - First visit  → shows sticky bottom banner
 *  - Accept       → sets localStorage 'cookie-consent' = 'accepted', hides banner
 *  - Decline      → sets localStorage 'cookie-consent' = 'declined', hides banner,
 *                   analytics cookies are NOT loaded
 *  - Cookie Settings link (Footer) → dispatches 'open-cookie-settings' event,
 *                   which forces the banner to re-appear
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Cookie, X, Check } from 'lucide-react'

const STORAGE_KEY = 'cookie-consent'
const OPEN_EVENT  = 'open-cookie-settings'

export type CookieConsent = 'accepted' | 'declined' | null

export function getStoredConsent(): CookieConsent {
  if (typeof window === 'undefined') return null
  const v = localStorage.getItem(STORAGE_KEY)
  if (v === 'accepted' || v === 'declined') return v
  return null
}

export default function CookieConsent() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    // Show banner if no consent stored yet
    if (!getStoredConsent()) {
      setVisible(true)
    }

    // Listen for "Cookie Settings" link clicks (dispatched from Footer)
    const handler = () => setVisible(true)
    window.addEventListener(OPEN_EVENT, handler)
    return () => window.removeEventListener(OPEN_EVENT, handler)
  }, [])

  function accept() {
    localStorage.setItem(STORAGE_KEY, 'accepted')
    setVisible(false)
    // Analytics can now be initialised — fire a custom event so
    // analytics providers (GA etc.) can self-initialise if needed.
    window.dispatchEvent(new Event('cookie-consent-accepted'))
  }

  function decline() {
    localStorage.setItem(STORAGE_KEY, 'declined')
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div
      role="dialog"
      aria-label="Cookie consent"
      aria-modal="false"
      className="fixed bottom-0 left-0 right-0 z-50 p-3 sm:p-4"
    >
      {/* Backdrop blur on mobile only */}
      <div
        className="max-w-3xl mx-auto bg-white border border-slate-200 rounded-2xl shadow-2xl
                   shadow-slate-200/60 p-4 sm:p-5"
      >
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
            <Cookie className="w-5 h-5 text-blue-600" />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-bold text-slate-900 mb-1">
              We use cookies
            </h2>
            <p className="text-xs text-slate-500 leading-relaxed">
              We use <strong className="text-slate-700">essential cookies</strong> to
              keep you signed in, and{' '}
              <strong className="text-slate-700">analytics cookies</strong>{' '}
              (Google Analytics) to understand how the platform is used. We never use
              advertising or cross-site tracking cookies.{' '}
              <Link href="/privacy#section-6" className="text-blue-600 hover:underline font-medium">
                Cookie policy
              </Link>
            </p>

            {/* Buttons */}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                onClick={accept}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 hover:bg-blue-700
                           text-white text-xs font-semibold rounded-lg transition-colors"
              >
                <Check className="w-3 h-3" />
                Accept all
              </button>
              <button
                onClick={decline}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 border border-slate-200
                           hover:border-slate-300 text-slate-600 text-xs font-semibold rounded-lg
                           transition-colors bg-white hover:bg-slate-50"
              >
                Essential only
              </button>
              <Link
                href="/privacy#section-6"
                className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
              >
                Learn more
              </Link>
            </div>
          </div>

          {/* Close (same as decline) */}
          <button
            onClick={decline}
            aria-label="Close cookie banner"
            className="shrink-0 p-1 rounded-lg text-slate-400 hover:text-slate-600
                       hover:bg-slate-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
