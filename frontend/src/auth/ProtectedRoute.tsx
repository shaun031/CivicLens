import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { LoadingState } from '../components/common/LoadingState'
import { useAuth } from './AuthContext'
import type { Role } from './types'

export function ProtectedRoute({ roles }: { roles?: readonly Role[] }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading)
    return (
      <div className="mx-auto max-w-xl px-4 py-16">
        <LoadingState message="Restoring your session…" />
      </div>
    )
  if (!user)
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (roles && !roles.includes(user.role)) return <Navigate to="/unauthorized" replace />
  return <Outlet />
}
