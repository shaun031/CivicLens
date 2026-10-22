import { createContext, useContext } from 'react'
import type { Principal } from './types'

export type AuthContextValue = {
  user: Principal | null
  loading: boolean
  error: string | null
  refresh: () => Promise<Principal | null>
  login: (email: string, password: string, returnTo: string) => Promise<Principal | null>
  logout: () => Promise<void>
  updateProfile: (name: string) => Promise<void>
}
export const AuthContext = createContext<AuthContextValue | undefined>(undefined)
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('Authentication context is missing')
  return context
}
