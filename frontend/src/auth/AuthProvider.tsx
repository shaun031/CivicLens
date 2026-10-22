import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { AuthContext } from './AuthContext'
import { ApiError, authClient } from './authClient'
import type { Principal } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Principal | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const version = useRef(0)
  const refresh = useCallback(async () => {
    const attempt = ++version.current
    try {
      const principal = await authClient.me()
      if (attempt !== version.current) return null
      setUser(principal)
      setError(null)
      return principal
    } catch (reason: unknown) {
      if (attempt !== version.current) return null
      setUser(null)
      setError(
        reason instanceof ApiError && reason.status === 401
          ? null
          : reason instanceof Error
            ? reason.message
            : 'Session could not be restored.',
      )
      return null
    } finally {
      if (attempt === version.current) setLoading(false)
    }
  }, [])
  useEffect(() => {
    void Promise.resolve().then(refresh)
    const expired = () => {
      version.current += 1
      setUser(null)
      setLoading(false)
    }
    const focused = () => {
      void refresh()
    }
    window.addEventListener('civiclens:session-expired', expired)
    window.addEventListener('focus', focused)
    const timer = window.setInterval(focused, 60_000)
    return () => {
      window.removeEventListener('civiclens:session-expired', expired)
      window.removeEventListener('focus', focused)
      window.clearInterval(timer)
    }
  }, [refresh])
  const login = useCallback(async (email: string, password: string, returnTo: string) => {
    const principal = await authClient.login(email, password, returnTo)
    if (principal) {
      version.current += 1
      setUser(principal)
      setError(null)
      setLoading(false)
    }
    return principal
  }, [])
  const logout = useCallback(async () => {
    await authClient.logout()
    version.current += 1
    setUser(null)
  }, [])
  const updateProfile = useCallback(async (name: string) => {
    const attempt = ++version.current
    const principal = await authClient.updateProfile(name)
    if (attempt === version.current) setUser(principal)
  }, [])
  const value = useMemo(
    () => ({ user, loading, error, refresh, login, logout, updateProfile }),
    [user, loading, error, refresh, login, logout, updateProfile],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
