import { beginCognitoLogin, getCognitoManager, logoutCognito } from './cognitoAuthClient'
import type { Principal, Registration } from './types'

const mode = import.meta.env.VITE_AUTH_MODE ?? 'local'
if (mode !== 'local' && mode !== 'aws') throw new Error('VITE_AUTH_MODE must be local or aws')
export const isAwsAuth = mode === 'aws'
const base = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

export async function authRequest<T>(
  path: string,
  method = 'GET',
  body?: object,
  options: { headers?: Record<string, string>; responseType?: 'blob' } = {},
): Promise<T> {
  const multipart = body instanceof FormData
  const headers: Record<string, string> = {
    Accept: options.responseType === 'blob' ? 'image/jpeg' : 'application/json',
    ...options.headers,
  }
  if (body && !multipart) headers['Content-Type'] = 'application/json'
  if (isAwsAuth) {
    const user = await getCognitoManager().getUser()
    if (user && !user.expired) headers.Authorization = `Bearer ${user.access_token}`
  }
  let response: Response
  try {
    response = await fetch(`${base}${path}`, {
      method,
      headers,
      credentials: isAwsAuth ? 'omit' : 'include',
      body: multipart ? body : body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new Error('The API is unavailable. Check the backend connection and try again.')
  }
  if (!response.ok) {
    if (response.status === 401 && !['/auth/login', '/auth/register', '/auth/me'].includes(path))
      window.dispatchEvent(new Event('civiclens:session-expired'))
    const data = (await response.json().catch(() => null)) as {
      detail?: string | { msg: string }[]
    } | null
    const message =
      typeof data?.detail === 'string'
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((item) => item.msg).join('; ')
          : 'The request could not be completed.'
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  if (options.responseType === 'blob') return (await response.blob()) as T
  return response.json() as Promise<T>
}

export const authClient = {
  me: () => authRequest<Principal>('/auth/me'),
  async login(email: string, password: string, returnTo: string): Promise<Principal | null> {
    if (isAwsAuth) {
      await beginCognitoLogin(returnTo)
      return null
    }
    return authRequest<Principal>('/auth/login', 'POST', { email, password })
  },
  register: (input: Registration) => authRequest<Principal>('/auth/register', 'POST', input),
  logout: () => (isAwsAuth ? logoutCognito() : authRequest<void>('/auth/logout', 'POST')),
  updateProfile: (display_name: string) =>
    authRequest<Principal>('/profile', 'PATCH', { display_name }),
  forgotPassword: (email: string) =>
    authRequest<{ message: string }>('/auth/forgot-password', 'POST', {
      email,
    }),
  resetPassword: (token: string, password: string, confirm_password: string) =>
    authRequest<{ message: string }>('/auth/reset-password', 'POST', {
      token,
      password,
      confirm_password,
    }),
}
