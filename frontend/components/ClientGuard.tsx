'use client'

/**
 * ClientGuard — enforces authentication at the layout level.
 *
 * Public routes (no auth needed): /, /auth/*
 * All other routes require a signed-in user.
 * On unauthenticated access, redirects to /auth/login?redirect=<pathname>
 * so the user is returned to the intended page after login.
 */

import { useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/lib/auth'

const PUBLIC_PREFIXES = ['/', '/auth/']

function isPublic(pathname: string): boolean {
  if (pathname === '/') return true
  return PUBLIC_PREFIXES.slice(1).some(prefix => pathname.startsWith(prefix))
}

export function ClientGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const router            = useRouter()
  const pathname          = usePathname()
  const pub               = isPublic(pathname)

  useEffect(() => {
    if (loading) return
    if (!pub && !user) {
      router.replace(`/auth/login?redirect=${encodeURIComponent(pathname)}`)
    }
  }, [user, loading, pathname, pub, router])

  // A public route never waits on auth.
  //
  // `loading` is true during server rendering and again until auth hydrates
  // from localStorage, so the spinner below was what the server emitted for
  // EVERY route. Measured on 2 Oct 2026, the homepage shipped 68 KB of HTML
  // containing roughly 1,000 characters of visible text -- the navbar and the
  // footer disclaimer -- with the hero, the preview table and the whole SEO
  // section present only inside the RSC script payload. No <h1> reached the
  // markup on any page.
  //
  // Nothing about a public route depends on who is asking, so it can render
  // immediately. This changes no access rule: it only stops a page that is
  // already public from being withheld until JavaScript runs.
  if (pub) return <>{children}</>

  // Show minimal spinner while auth hydrates from localStorage
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  // Block render on protected routes until redirect fires
  if (!user) return null

  return <>{children}</>
}
