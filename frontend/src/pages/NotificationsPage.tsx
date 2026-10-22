import { useCallback, useContext, useState } from 'react'
import { CitizenContext } from '../auth/CitizenContext'
import { useAuth } from '../auth/AuthContext'
import { useResource } from '../hooks/useResource'
import { notificationService } from '../services/notificationService'
import { liveNotificationTypes, notificationTypes } from '../types/notification'
import { Link } from 'react-router-dom'
import { dashboardFor } from '../auth/types'
import { Breadcrumbs, EmptyState, PageHeader, Select, Skeleton } from '../components/common/UI'
import { ErrorState } from '../components/common/ErrorState'
import { NotificationItem } from '../components/notifications/NotificationItem'

export function NotificationsPage() {
  const citizen = useContext(CitizenContext)
  const { user } = useAuth()
  const principalId = user?.id
  const demo = citizen?.demo ?? false
  const [filter, setFilter] = useState('')
  const [type, setType] = useState('')
  const [cursor, setCursor] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const loader = useCallback(async () => {
    if (!principalId) throw new Error('Sign in to view private notifications.')
    if (demo)
      return { items: await notificationService.list(true), nextCursor: null, unreadCount: null }
    const [page, count] = await Promise.all([
      notificationService.page({
        type,
        read: filter === 'read' ? 'true' : filter === 'unread' ? 'false' : '',
        cursor,
      }),
      notificationService.unread(),
    ])
    return { ...page, ...count }
  }, [demo, type, filter, cursor, principalId])
  // AuthProvider remounts protected content when authentication expires; account is never an API parameter.
  const { data, loading, error, retry } = useResource(loader)
  const items = (data?.items ?? [])
    .map((item) => ({
      ...item,
      read:
        item.read || (demo && (citizen?.readNotifications.includes(item.notificationId) ?? false)),
    }))
    .filter(
      (item) =>
        !demo ||
        ((!filter || (filter === 'read' ? item.read : !item.read)) &&
          (!type || item.type === type)),
    )
  async function mark(id?: string) {
    if (demo && id) {
      citizen?.setReadNotifications((current) => [...new Set([...current, id])])
      return
    }
    setBusy(true)
    setActionError('')
    try {
      if (id) await notificationService.read(id)
      else await notificationService.readAll()
      window.dispatchEvent(new Event('civiclens:notifications-changed'))
      retry()
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : 'Could not update notification.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section key={user?.id} className={citizen ? '' : 'mx-auto max-w-5xl space-y-5 px-4 py-10'}>
      {citizen ? (
        <Breadcrumbs current="Notifications" />
      ) : (
        <Link className="text-teal-700" to={dashboardFor(user?.role ?? 'CITIZEN')}>
          ← My dashboard
        </Link>
      )}
      <PageHeader
        title="Notifications"
        description={
          demo
            ? 'Explicit fictional sample preview. Read state is temporary.'
            : 'Private updates for your authenticated account. In-app delivery is not email or SMS delivery.'
        }
      />
      <div className="flex flex-wrap items-center gap-4">
        <p role="status">{demo ? 'Sample preview' : `Unread: ${data?.unreadCount ?? '—'}`}</p>
        <button className="font-semibold text-teal-700" onClick={retry} disabled={loading || busy}>
          Refresh notifications
        </button>
        {!demo && (
          <button
            className="font-semibold text-teal-700"
            onClick={() => void mark()}
            disabled={busy || loading || !data?.unreadCount}
          >
            Mark all as read
          </button>
        )}
      </div>
      <div className="my-4 grid gap-4 sm:grid-cols-2">
        <Select
          id="notification-filter"
          label="Read status"
          value={filter}
          onChange={(event) => {
            setFilter(event.target.value)
            setCursor('')
          }}
        >
          <option value="">All notifications</option>
          <option value="unread">Unread</option>
          <option value="read">Read</option>
        </Select>
        <Select
          id="notification-type"
          label="Notification type"
          value={type}
          onChange={(event) => {
            setType(event.target.value)
            setCursor('')
          }}
        >
          <option value="">All types</option>
          {Object.entries(notificationTypes)
            .filter(([key]) =>
              demo ? !(key in liveNotificationTypes) : key in liveNotificationTypes,
            )
            .map(([key, label]) => (
              <option value={key} key={key}>
                {label}
              </option>
            ))}
        </Select>
      </div>
      {actionError && (
        <p role="alert" className="text-red-700">
          {actionError}
        </p>
      )}
      {loading ? (
        <Skeleton />
      ) : error ? (
        <ErrorState title="Notifications unavailable" message={error} onRetry={retry} />
      ) : items.length ? (
        <section aria-label="Notification list" aria-busy={busy} className="space-y-4">
          {items.map((item) => (
            <NotificationItem
              key={item.notificationId}
              notification={item}
              onRead={() => {
                if (!busy) void mark(item.notificationId)
              }}
            />
          ))}
        </section>
      ) : (
        <EmptyState title="No notifications yet">
          No notifications match this page and its filters. Processing may still be pending.
        </EmptyState>
      )}
      <div className="mt-5 flex gap-5">
        {cursor && (
          <button className="text-teal-700" onClick={() => setCursor('')}>
            Newest notifications
          </button>
        )}
        {data?.nextCursor && (
          <button className="text-teal-700" onClick={() => setCursor(data.nextCursor ?? '')}>
            Older notifications
          </button>
        )}
      </div>
    </section>
  )
}
