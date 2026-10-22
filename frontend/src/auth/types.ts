export type Role = 'CITIZEN' | 'OFFICER' | 'ADMIN'
export type Principal = {
  id: string
  email: string
  display_name: string
  role: Role
  provider: 'local' | 'cognito'
  is_active: boolean
  is_verified: boolean
  is_authenticated: boolean
}
export type Registration = {
  display_name: string
  email: string
  password: string
  confirm_password: string
}
export const portalRoles: Record<string, readonly Role[]> = {
  citizen: ['CITIZEN', 'ADMIN'],
  officer: ['OFFICER', 'ADMIN'],
  admin: ['ADMIN'],
}
export const dashboardFor = (role: Role) => `/${role.toLowerCase()}/dashboard`

export function safeDestination(value: unknown, fallback = '/') {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    /[\\\r\n]/.test(value)
  )
    return fallback
  return value
}
