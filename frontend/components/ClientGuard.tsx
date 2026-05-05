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

  // Show minimal spinner while auth hydrates from localStorage
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  // Block render on protected routes until redirect fires
  if (!pub && !user) return null

  return <>{children}</>
}
