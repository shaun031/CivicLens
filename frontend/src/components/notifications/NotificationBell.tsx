import { Bell } from 'lucide-react'
import { useCallback, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { notificationService } from '../../services/notificationService'
import { useResource } from '../../hooks/useResource'
import { useAuth } from '../../auth/AuthContext'

export function NotificationBell() {
  const location = useLocation()
  const { user } = useAuth()
  const principalId = user?.id
  const loader = useCallback(() => {
    // Navigation-triggered refresh only; no aggressive timer or background polling.
    void location.pathname
    if (!principalId) return Promise.resolve({ unreadCount: 0 })
    return notificationService.unread()
  }, [location.pathname, principalId])
  const { data, error, retry } = useResource(loader)
  useEffect(() => {
    window.addEventListener('civiclens:notifications-changed', retry)
    return () => window.removeEventListener('civiclens:notifications-changed', retry)
  }, [retry])
  return (
    <Link
      className="notification-bell icon-button"
      to={user?.role === 'CITIZEN' ? '/citizen/notifications' : '/notifications'}
      aria-label={
        error
          ? 'Notifications ! Unread count unavailable'
          : `Notifications ${data?.unreadCount ?? '…'} unread`
      }
    >
      <Bell size={19} aria-hidden="true" />
      <span className="sr-only">Notifications</span>
      <span
        aria-label={
          error
            ? 'Unread count unavailable'
            : `${data?.unreadCount ?? 'Pending'} unread notifications`
        }
        className="notification-count"
      >
        {error ? '!' : (data?.unreadCount ?? '…')}
      </span>
    </Link>
  )
}
