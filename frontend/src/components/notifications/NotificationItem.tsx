import { Link } from 'react-router-dom'
import { Bell } from 'lucide-react'
import type { CitizenNotification } from '../../types/notification'
import { formatDate } from '../../utils/dates'
import { Badge } from '../common/UI'
export function NotificationItem({
  notification,
  onRead,
}: {
  notification: CitizenNotification
  onRead: () => void
}) {
  return (
    <article
      className={`notification-item flex items-start gap-3 rounded-2xl border bg-white p-5 ${notification.read ? 'border-slate-200' : 'border-teal-300'}`}
    >
      <Bell className="mt-1 shrink-0 text-teal-700" size={20} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-semibold">{notification.title}</h2>
          <Badge>{notification.read ? 'Read' : 'Unread'}</Badge>
        </div>
        <p className="mt-2 text-sm leading-6 text-slate-600">{notification.message}</p>
        <time dateTime={notification.createdAt} className="mt-2 block text-xs text-slate-600">
          {formatDate(notification.createdAt, true)} ·{' '}
          {notification.isSimulated ? 'Simulated notification' : 'In-app notification'}
        </time>
        <div className="mt-4 flex flex-wrap gap-4">
          <Link to={notification.targetUrl} className="text-sm font-semibold text-teal-700">
            View related page<span className="sr-only">: {notification.title}</span>
          </Link>
          {!notification.read && (
            <button className="text-sm font-semibold text-teal-700" onClick={onRead}>
              {notification.isSimulated ? 'Mark sample as read' : 'Mark as read'}
              <span className="sr-only">: {notification.title}</span>
            </button>
          )}
        </div>
      </div>
    </article>
  )
}
