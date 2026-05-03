'use client'

/**
 * ASX Screener — Auth Context
 * ============================
 * Provides useAuth() hook with:
 *   user        — current user (or null)
 *   loading     — true while hydrating from localStorage
 *   login()     — stores tokens, sets user
 *   logout()    — revokes refresh token, clears state
 *   register()  — creates account, stores tokens, sets user
 *   refreshTokens() — silently exchanges refresh token for new pair
 *
 * Tokens stored in localStorage:
 *   asx_access_token   — JWT (15 min)
 *   asx_refresh_token  — opaque (30 days)
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://209.38.84.102:8000'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id:             string
  email:          string
  name:           string | null
  plan:           'free' | 'pro' | 'premium' | 'enterprise'
  email_verified: boolean
}

interface TokenPair {
  access_token:  string
  refresh_token: string
  expires_in:    number   // seconds
}

interface AuthContextValue {
  user:          AuthUser | null
  loading:       boolean
  login:         (email: string, password: string) => Promise<void>
  register:      (email: string, password: string, name?: string) => Promise<void>
  logout:        () => Promise<void>
  refreshTokens: () => Promise<boolean>
}

// ── Storage keys ──────────────────────────────────────────────────────────────

const ACCESS_KEY  = 'asx_access_token'
const REFRESH_KEY = 'asx_refresh_token'

export function getStoredAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(ACCESS_KEY)
}

function storeTokens(pair: TokenPair) {
  localStorage.setItem(ACCESS_KEY,  pair.access_token)
  localStorage.setItem(REFRESH_KEY, pair.refresh_token)
}

function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiPost<T>(path: string, body: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_BASE}${path}`, {
    method:  'POST',
    headers,
    body:    JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json() as Promise<T>
}

async function apiGet<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json() as Promise<T>
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,    setUser]    = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  // Track refresh timer so we can cancel on logout
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Helpers ────────────────────────────────────────────────────────────────

  const fetchMe = useCallback(async (accessToken: string): Promise<AuthUser | null> => {
    try {
      const profile = await apiGet<AuthUser>('/api/v1/auth/me', accessToken)
      return profile
    } catch {
      return null
    }
  }, [])

  const scheduleRefresh = useCallback((expiresIn: number) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    // Refresh 60 seconds before expiry (but at least 10 seconds from now)
    const delay = Math.max((expiresIn - 60) * 1000, 10_000)
    refreshTimerRef.current = setTimeout(async () => {
      await refreshTokens()
    }, delay)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── refreshTokens ──────────────────────────────────────────────────────────

  const refreshTokens = useCallback(async (): Promise<boolean> => {
    const storedRefresh = localStorage.getItem(REFRESH_KEY)
    if (!storedRefresh) return false
    try {
      const pair = await apiPost<TokenPair>('/api/v1/auth/refresh', {
        refresh_token: storedRefresh,
      })
      storeTokens(pair)
      const profile = await fetchMe(pair.access_token)
      if (profile) {
        setUser(profile)
        scheduleRefresh(pair.expires_in)
        return true
      }
    } catch {
      clearTokens()
      setUser(null)
    }
    return false
  }, [fetchMe, scheduleRefresh])

  // ── Hydrate from localStorage on mount ────────────────────────────────────

  useEffect(() => {
    const init = async () => {
      const access = localStorage.getItem(ACCESS_KEY)
      if (!access) {
        setLoading(false)
        return
      }
      // Try the stored access token first
      const profile = await fetchMe(access)
      if (profile) {
        setUser(profile)
        // We don't know exact expiry; schedule a refresh after ~13 minutes
        scheduleRefresh(13 * 60)
      } else {
        // Access token expired — try refresh
        await refreshTokens()
      }
      setLoading(false)
    }
    init()
  }, [fetchMe, refreshTokens, scheduleRefresh])

  // ── login ──────────────────────────────────────────────────────────────────

  const login = useCallback(async (email: string, password: string) => {
    const pair = await apiPost<TokenPair>('/api/v1/auth/login', { email, password })
    storeTokens(pair)
    const profile = await fetchMe(pair.access_token)
    if (!profile) throw new Error('Failed to fetch user profile')
    setUser(profile)
    scheduleRefresh(pair.expires_in)
  }, [fetchMe, scheduleRefresh])

  // ── register ───────────────────────────────────────────────────────────────

  const register = useCallback(async (email: string, password: string, name?: string) => {
    const pair = await apiPost<TokenPair>('/api/v1/auth/register', { email, password, name })
    storeTokens(pair)
    const profile = await fetchMe(pair.access_token)
    if (!profile) throw new Error('Failed to fetch user profile')
    setUser(profile)
    scheduleRefresh(pair.expires_in)
  }, [fetchMe, scheduleRefresh])

  // ── logout ─────────────────────────────────────────────────────────────────

  const logout = useCallback(async () => {
    const storedRefresh = localStorage.getItem(REFRESH_KEY)
    if (storedRefresh) {
      // Best-effort revocation — don't throw if it fails
      try {
        await apiPost('/api/v1/auth/logout', { refresh_token: storedRefresh })
      } catch { /* ignore */ }
    }
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    clearTokens()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshTokens }}>
      {children}
    </AuthContext.Provider>
  )
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
