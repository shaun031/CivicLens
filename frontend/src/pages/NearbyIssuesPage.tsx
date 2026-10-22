import { lazy, Suspense, useCallback, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCitizen } from '../auth/CitizenContext'
import { useResource } from '../hooks/useResource'
import { useGeolocation } from '../hooks/useGeolocation'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { complaintService } from '../services/complaintService'
import { discoveryService } from '../services/discoveryService'
import { categories, statuses } from '../types/complaint'
import type { NearbyPage } from '../types/nearby'
import { validCoordinates } from '../utils/validation'
import {
  Breadcrumbs,
  Card,
  EmptyState,
  PageHeader,
  Select,
  Skeleton,
} from '../components/common/UI'
import { Field, FormMessage } from '../components/common/FormParts'
import { ErrorState } from '../components/common/ErrorState'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import { ComplaintCard } from '../components/complaints/ComplaintComponents'
const ComplaintMap = lazy(() => import('../components/complaints/ComplaintMap'))
const EMPTY: NearbyPage = { items: [], nextCursor: null }
const MAX_DISPLAYED = 500

export function NearbyIssuesPage() {
  const { demo, nearbySearch, setNearbySearch } = useCitizen()
  const { center, radiusKm } = nearbySearch
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [view, setView] = useState('map')
  const [latitude, setLatitude] = useState(center?.[0].toFixed(6) ?? '')
  const [longitude, setLongitude] = useState(center?.[1].toFixed(6) ?? '')
  const [locationError, setLocationError] = useState<string | null>(null)
  const [latestBusy, setLatestBusy] = useState(false)
  const [focused, setFocused] = useState<string>()
  const mapPanel = useRef<HTMLDivElement>(null)
  const appliedRadius = useDebouncedValue(radiusKm, 350)
  const applyingRadius = appliedRadius !== radiusKm
  const requestKey = JSON.stringify({ center, radiusKm: appliedRadius, category, status, demo })
  const loader = useCallback(() => {
    const values = JSON.parse(requestKey) as {
      center: [number, number] | null
      radiusKm: number
      category: string
      status: string
      demo: boolean
    }
    if (values.demo || !values.center) return Promise.resolve(EMPTY)
    return discoveryService.visibleNearby(...values.center, values.radiusKm, {
      category: values.category,
      status: values.status,
    })
  }, [requestKey])
  const { data, loading, error, retry } = useResource(loader)
  const samples = useResource(useCallback(() => complaintService.nearby(demo), [demo]))
  const [extra, setExtra] = useState<{ key: string; first?: NearbyPage; page: NearbyPage }>()
  const [busyKey, setBusyKey] = useState<string>()
  const [pageError, setPageError] = useState<{ key: string; message: string }>()
  const page = extra?.key === requestKey && extra.first === data ? extra.page : data
  const items = applyingRadius ? [] : (page?.items ?? [])
  async function loadMore() {
    if (!center || !page?.nextCursor || busyKey || page.items.length >= MAX_DISPLAYED) return
    const key = requestKey
    setBusyKey(key)
    setPageError(undefined)
    try {
      const next = await discoveryService.visibleNearby(...center, appliedRadius, {
        category,
        status,
        cursor: page.nextCursor,
      })
      setExtra({
        key,
        first: data,
        page: {
          ...next,
          items: [
            ...new Map([...page.items, ...next.items].map((item) => [item.issueId, item])).values(),
          ],
        },
      })
    } catch (reason) {
      setPageError({
        key,
        message: reason instanceof Error ? reason.message : 'Could not load more nearby issues.',
      })
    } finally {
      setBusyKey(undefined)
    }
  }
  function selectLocation(lat: number, lng: number) {
    if (!validCoordinates(String(lat), String(lng))) return
    setNearbySearch((previous) => ({ ...previous, center: [lat, lng] }))
    setLatitude(lat.toFixed(6))
    setLongitude(lng.toFixed(6))
    setFocused(undefined)
    setLocationError(null)
  }
  const geo = useGeolocation(selectLocation)
  async function latestLocation() {
    setLatestBusy(true)
    setLocationError(null)
    try {
      const point = await discoveryService.latestLocation()
      if (point) selectLocation(...point)
      else
        setLocationError(
          'No eligible complaint location was found. Choose a point on the map or enter coordinates.',
        )
    } catch (reason) {
      setLocationError(
        reason instanceof Error ? reason.message : 'Could not find your latest complaint.',
      )
    } finally {
      setLatestBusy(false)
    }
  }
  const filteredSamples = (samples.data ?? []).filter(
    (issue) => (!category || issue.category === category) && (!status || issue.status === status),
  )
  return (
    <>
      <Breadcrumbs current="Nearby Issues" />
      <PageHeader
        title="Nearby Issues"
        description={
          demo
            ? 'Fictional sample map — not live municipal incidents.'
            : 'Explore approved public summaries and your own eligible reports. Other citizens’ private reports remain hidden. Public locations are approximate.'
        }
      />
      <Card>
        <div className="grid items-end gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Select
            label="Map category"
            id="map-category"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value)
              setFocused(undefined)
            }}
          >
            <option value="">All categories</option>
            {Object.entries(categories).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </Select>
          <Select
            label="Map status"
            id="map-status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setFocused(undefined)
            }}
          >
            <option value="">All statuses</option>
            {Object.entries(statuses).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </Select>
          <Field
            id="map-latitude"
            label="Map latitude"
            inputMode="decimal"
            value={latitude}
            onChange={(e) => setLatitude(e.target.value)}
          />
          <Field
            id="map-longitude"
            label="Map longitude"
            inputMode="decimal"
            value={longitude}
            onChange={(e) => setLongitude(e.target.value)}
          />
        </div>
        <div className="nearby-actions mt-4 flex flex-wrap gap-3">
          <button
            className="secondary-button"
            onClick={() =>
              validCoordinates(latitude, longitude)
                ? selectLocation(Number(latitude), Number(longitude))
                : setLocationError(
                    'Enter valid coordinates: latitude −90 to 90, longitude −180 to 180.',
                  )
            }
          >
            Set map center
          </button>
          <button className="secondary-button" disabled={geo.busy} onClick={geo.locate}>
            {geo.busy ? 'Locating…' : 'Use My Location'}
          </button>
          {!demo && (
            <button
              className="secondary-button"
              disabled={latestBusy}
              onClick={() => void latestLocation()}
            >
              {latestBusy ? 'Finding location…' : 'Search near my latest complaint'}
            </button>
          )}
          <button
            className="secondary-button"
            disabled={loading || !center || applyingRadius}
            onClick={retry}
          >
            Refresh visible results
          </button>
          <button
            className="secondary-button"
            disabled={!category && !status}
            onClick={() => {
              setCategory('')
              setStatus('')
              setFocused(undefined)
            }}
          >
            Clear Filters
          </button>
        </div>
        <div className="nearby-radius mt-5">
          <label className="font-semibold" htmlFor="nearby-radius">
            Search Radius: {radiusKm} km
          </label>
          <input
            id="nearby-radius"
            type="range"
            min="1"
            max="200"
            step="1"
            value={radiusKm}
            onChange={(e) => {
              const value = Number(e.target.value)
              setNearbySearch((previous) => ({ ...previous, radiusKm: value }))
              setFocused(undefined)
            }}
          />
          <div className="flex flex-wrap gap-2" role="group" aria-label="Radius presets">
            {[1, 5, 10, 25, 50, 100, 200].map((value) => (
              <button
                key={value}
                className="secondary-button"
                aria-pressed={value === radiusKm}
                onClick={() => {
                  setNearbySearch((previous) => ({ ...previous, radiusKm: value }))
                  setFocused(undefined)
                }}
              >
                {value} km
              </button>
            ))}
          </div>
        </div>
        <p className="mt-3 text-sm text-slate-600">
          {center
            ? `Search center: ${center[0].toFixed(6)}, ${center[1].toFixed(6)}`
            : 'Default map view: Bengaluru. This is not your detected location.'}
        </p>
        <div className="mt-4 flex gap-2" role="group" aria-label="Issue view">
          <button
            className="secondary-button"
            aria-pressed={view === 'map'}
            onClick={() => setView('map')}
          >
            Map view
          </button>
          <button
            className="secondary-button"
            aria-pressed={view === 'list'}
            onClick={() => setView('list')}
          >
            List view
          </button>
        </div>
        <FormMessage error={locationError} success={geo.message} />
      </Card>
      {view === 'map' && (
        <div ref={mapPanel}>
          <ErrorBoundary>
            <Suspense fallback={<Skeleton />}>
              <ComplaintMap
                center={center ?? undefined}
                issues={demo ? filteredSamples : []}
                nearbyIssues={demo ? undefined : items}
                selection={center ? { latitude: center[0], longitude: center[1] } : undefined}
                onSelect={selectLocation}
                radiusMeters={center ? appliedRadius * 1000 : undefined}
                focusedIssue={focused}
                onIssueFocus={setFocused}
              />
            </Suspense>
          </ErrorBoundary>
        </div>
      )}
      {!demo && !center ? (
        <EmptyState title="Select a location to find nearby infrastructure issues.">
          Choose on the map, use your location, enter coordinates, or search near your latest
          complaint.
        </EmptyState>
      ) : applyingRadius || loading ? (
        <>
          <p role="status">
            {applyingRadius ? 'Applying search radius…' : 'Loading nearby issues…'}
          </p>
          <Skeleton />
        </>
      ) : error ? (
        <ErrorState
          title="Unable to load nearby issues. Please try again."
          message={error}
          onRetry={retry}
        />
      ) : (
        <>
          <p role="status" className="text-sm text-slate-600">
            {demo
              ? `${filteredSamples.length} simulated issues`
              : `${items.length} visible reports loaded within ${appliedRadius} km — not unique incidents.`}
            {page?.nextCursor ? ' More results may exist.' : ''}
          </p>
          {(demo ? !filteredSamples.length : !items.length) && (
            <EmptyState title="No visible issues were found within the selected radius.">
              Increase the radius, change the location, or clear category/status filters.
            </EmptyState>
          )}
          <div className="tab-panel grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {demo
              ? filteredSamples.map((item) => (
                  <ComplaintCard key={item.complaintId} complaint={item} />
                ))
              : items.map((item) => (
                  <article
                    key={item.issueId}
                    data-issue-id={item.issueId}
                    className={`nearby-result ${focused === item.issueId ? 'nearby-result-focused' : ''}`}
                  >
                    <Card>
                      <h2 className="break-words font-semibold">{item.title}</h2>
                      <p className="mt-2 text-sm">
                        {categories[item.category]} · {statuses[item.status]}
                      </p>
                      <p className="mt-2 text-sm">
                        {(item.distanceMeters / 1000).toFixed(2)} km from search center ·{' '}
                        {item.dateLabel} {new Date(item.createdAt).toLocaleDateString()}
                      </p>
                      <p className="mt-2 text-sm font-semibold">
                        {item.isOwn
                          ? `My Report · ${item.isPublic ? 'Publicly Visible' : 'Not Publicly Visible'}`
                          : 'Approved public summary · Approximate location'}
                      </p>
                      <div className="nearby-actions mt-3 flex flex-wrap gap-3">
                        <Link className="text-sm font-semibold text-teal-700" to={item.detailsUrl}>
                          {item.isOwn ? 'View complaint details' : 'View public issue'}
                        </Link>
                        <button
                          className="text-sm font-semibold text-teal-700"
                          onClick={() => {
                            setView('map')
                            setFocused(item.issueId)
                            requestAnimationFrame(() =>
                              mapPanel.current?.scrollIntoView({
                                block: 'start',
                                behavior: 'smooth',
                              }),
                            )
                          }}
                        >
                          Show on map
                        </button>
                      </div>
                    </Card>
                  </article>
                ))}
          </div>
          <FormMessage error={pageError?.key === requestKey ? pageError.message : undefined} />
          {!demo &&
            page?.nextCursor &&
            (items.length >= MAX_DISPLAYED ? (
              <p role="status">
                More results may exist. Showing the first {MAX_DISPLAYED} reports; reduce the radius
                or refine filters to explore further.
              </p>
            ) : (
              <button
                className="secondary-button"
                disabled={Boolean(busyKey)}
                onClick={() => void loadMore()}
              >
                {busyKey === requestKey ? 'Loading more…' : 'Load more nearby issues'}
              </button>
            ))}
        </>
      )}
    </>
  )
}
