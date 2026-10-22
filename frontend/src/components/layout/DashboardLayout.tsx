import { useCallback, useMemo, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { CitizenContext } from '../../auth/CitizenContext'
import { authRequest } from '../../auth/authClient'
import { emptyDraft } from '../../types/complaint'
import { useResource } from '../../hooks/useResource'
import { Skeleton } from '../common/UI'
import { ErrorState } from '../common/ErrorState'
import { ErrorBoundary } from '../common/ErrorBoundary'
import { AppShell } from './AppShell'
import type { NearbySearch } from '../../types/nearby'
function CitizenWorkspace() {
  const [demo, setDemo] = useState(false)
  const [draft, setDraft] = useState(emptyDraft)
  const [nearbySearch, setNearbySearch] = useState<NearbySearch>({ center: null, radiusKm: 10 })
  const [readNotifications, setReadNotifications] = useState<string[]>([])
  const verify = useCallback(() => authRequest<{ message: string }>('/portal/citizen'), [])
  const access = useResource(verify)
  const value = useMemo(
    () => ({
      demo,
      setDemo,
      draft,
      setDraft,
      readNotifications,
      setReadNotifications,
      nearbySearch,
      setNearbySearch,
    }),
    [demo, draft, readNotifications, nearbySearch],
  )
  return (
    <CitizenContext.Provider value={value}>
      <AppShell
        hideNotifications={demo}
        toolbar={
          <div className={`preview-toolbar ${demo ? 'sample-active' : ''}`}>
            <p>
              {demo
                ? 'Sample preview · simulated data, separate from your account'
                : 'Your workspace · Private complaint data'}
            </p>
            <label>
              <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} />
              Show sample data
            </label>
          </div>
        }
      >
        {access.loading ? (
          <Skeleton />
        ) : access.error ? (
          <ErrorState
            title="Citizen portal unavailable"
            message={access.error}
            onRetry={access.retry}
          />
        ) : (
          <>
            <span className="sr-only">Access verified by the backend.</span>
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </>
        )}
      </AppShell>
    </CitizenContext.Provider>
  )
}
export function DashboardLayout() {
  const { user } = useAuth()
  return <CitizenWorkspace key={user?.id} />
}
