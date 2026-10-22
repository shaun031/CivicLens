import { useState, useEffect } from 'react'
import { divIcon } from 'leaflet'
import { MapContainer, Marker, Popup, useMap, useMapEvents } from 'react-leaflet'
import { Link } from 'react-router-dom'
import type { Complaint, IssueLocation, MapBounds, PublicIssue } from '../../types/complaint'
import { categories, statuses } from '../../types/complaint'
import { Alert } from '../common/UI'
import { MapResize, OpenStreetMapTiles } from '../maps/MapSupport'
import { DEFAULT_MAP_CENTER, wrapLongitude } from '../maps/mapConfig'
import type { NearbyIssue } from '../../types/nearby'
import { NearbyLayer, RadiusCircle } from '../maps/NearbyLayer'
import { categoryMarker } from '../maps/markerIcons'
import { CategoryLegend } from '../maps/CategoryLegend'

const selectedMarker = divIcon({
  className: 'civic-map-marker location-selection-marker',
  html: '<span aria-hidden="true">●</span>',
  iconSize: [34, 34],
  iconAnchor: [17, 17],
})
const searchMarker = divIcon({
  className: 'civic-map-marker location-selection-marker search-center-marker',
  html: '<span aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 0v4m0 16v4M0 12h4m16 0h4"/></svg></span>',
  iconSize: [52, 52],
  iconAnchor: [26, 26],
})
function MapInteraction({
  center,
  onSelect,
  onBoundsChange,
}: {
  center: [number, number]
  onSelect?: (latitude: number, longitude: number) => void
  onBoundsChange?: (bounds: MapBounds) => void
}) {
  const map = useMap()
  const [latitude, longitude] = center
  useEffect(() => {
    map.setView([latitude, longitude], map.getZoom(), { animate: false })
  }, [latitude, longitude, map])
  const emitBounds = () => {
    const b = map.getBounds()
    onBoundsChange?.({
      minLatitude: Math.max(-90, b.getSouth()),
      maxLatitude: Math.min(90, b.getNorth()),
      minLongitude: ((((b.getWest() + 180) % 360) + 360) % 360) - 180,
      maxLongitude: ((((b.getEast() + 180) % 360) + 360) % 360) - 180,
    })
  }
  useEffect(() => {
    const b = map.getBounds()
    onBoundsChange?.({
      minLatitude: Math.max(-90, b.getSouth()),
      maxLatitude: Math.min(90, b.getNorth()),
      minLongitude: ((((b.getWest() + 180) % 360) + 360) % 360) - 180,
      maxLongitude: ((((b.getEast() + 180) % 360) + 360) % 360) - 180,
    })
  }, [map, onBoundsChange])
  useMapEvents({
    moveend: emitBounds,
    zoomend: emitBounds,
    click(event) {
      if (Math.abs(event.latlng.lat) <= 90)
        onSelect?.(event.latlng.lat, wrapLongitude(event.latlng.lng))
    },
  })
  return null
}
export default function ComplaintMap({
  issues = [],
  center = DEFAULT_MAP_CENTER,
  selection,
  onSelect,
  publicIssues = [],
  onBoundsChange,
  nearbyIssues,
  radiusMeters,
  focusedIssue,
  onIssueFocus,
}: {
  issues?: Complaint[]
  center?: [number, number]
  selection?: Pick<IssueLocation, 'latitude' | 'longitude'>
  onSelect?: (latitude: number, longitude: number) => void
  publicIssues?: PublicIssue[]
  onBoundsChange?: (bounds: MapBounds) => void
  nearbyIssues?: NearbyIssue[]
  radiusMeters?: number
  focusedIssue?: string
  onIssueFocus?: (id: string) => void
}) {
  const [tiles, setTiles] = useState(true)
  const [tileError, setTileError] = useState(false)
  const [tileReady, setTileReady] = useState(false)
  const [tileAttempt, setTileAttempt] = useState(0)
  useEffect(() => {
    if (!tiles || tileReady || tileError) return
    const timer = window.setTimeout(() => setTileError(true), 12000)
    return () => window.clearTimeout(timer)
  }, [tiles, tileReady, tileError, tileAttempt])
  return (
    <div className="space-y-3">
      <div className="map-introduction">
        <p>
          {onSelect
            ? 'Select a point on the map, or enter coordinates.'
            : 'Explore reviewed public summaries. Select a marker for details.'}
        </p>
        <details>
          <summary>Map privacy & basemap</summary>
          <p>
            The basemap shares your IP address and viewed area with OpenStreetMap. You can hide it
            and enter coordinates instead. Browser location is requested only when you choose it.
          </p>
        </details>
        {!tiles && (
          <button
            type="button"
            className="mt-2 font-semibold text-teal-700"
            onClick={() => {
              setTiles(true)
              setTileError(false)
              setTileReady(false)
            }}
          >
            Load OpenStreetMap basemap
          </button>
        )}
        {tiles && (
          <button
            type="button"
            className="mt-2 font-semibold text-teal-700"
            onClick={() => setTiles(false)}
          >
            Hide external basemap
          </button>
        )}
      </div>
      {(nearbyIssues !== undefined ||
        !onSelect ||
        issues.length > 0 ||
        publicIssues.length > 0) && <CategoryLegend />}
      {tiles && !tileReady && !tileError && (
        <p role="status" className="text-sm text-slate-600">
          Loading OpenStreetMap…
        </p>
      )}
      {!tiles && (
        <p className="text-sm text-slate-600">
          Basemap hidden. Enter coordinates manually or load the basemap to identify a location.
        </p>
      )}
      {tiles && tileError && (
        <Alert>
          Map tiles couldn't load. You can still select or enter coordinates. Check your internet
          connection.
          {onSelect
            ? ' Enter latitude and longitude manually, or use your current location. Your selected coordinates are retained.'
            : ' Markers remain available; use the issue list or data table for details.'}
          <button
            type="button"
            className="map-retry"
            onClick={() => {
              setTileError(false)
              setTileReady(false)
              setTileAttempt((value) => value + 1)
            }}
          >
            Retry map tiles
          </button>
        </Alert>
      )}
      {radiusMeters && selection && Math.abs(selection.latitude) >= 85 && (
        <Alert>
          Polar search: this map projection cannot display the pole accurately. Coordinates,
          distances and the results list remain valid; the radius circle is hidden in this view.
        </Alert>
      )}
      <div
        role="region"
        aria-label="Infrastructure issue map"
        className="tab-panel isolate overflow-hidden rounded-2xl border border-slate-300"
      >
        <MapContainer
          center={center}
          zoom={14}
          scrollWheelZoom={false}
          className="civic-location-map"
          attributionControl
        >
          <MapInteraction center={center} onSelect={onSelect} onBoundsChange={onBoundsChange} />
          <MapResize />
          {radiusMeters && selection && (
            <RadiusCircle
              latitude={selection.latitude}
              longitude={selection.longitude}
              radius={radiusMeters}
            />
          )}
          {nearbyIssues && (
            <NearbyLayer items={nearbyIssues} focused={focusedIssue} onFocus={onIssueFocus} />
          )}
          {tiles && (
            <OpenStreetMapTiles
              key={tileAttempt}
              onError={() => setTileError(true)}
              onReady={() => setTileReady(true)}
            />
          )}
          {issues.map((issue) => (
            <Marker
              key={issue.complaintId}
              position={[issue.location.latitude, issue.location.longitude]}
              icon={categoryMarker(issue.category)}
              title={`Simulated: ${issue.title}`}
              alt={`Simulated: ${issue.title}`}
            >
              <Popup>
                <strong>Simulated issue</strong>
                <p>{issue.title}</p>
                <p>
                  {categories[issue.category]} · {statuses[issue.status]}
                </p>
                <Link to={`/citizen/complaints/${encodeURIComponent(issue.complaintId)}`}>
                  View simulated complaint
                </Link>
              </Popup>
            </Marker>
          ))}
          {publicIssues.map((issue) => (
            <Marker
              key={`public-${issue.publicIssueId}`}
              position={[issue.latitude, issue.longitude]}
              icon={categoryMarker(issue.category)}
              title={issue.summary}
              alt={issue.summary}
            >
              <Popup>
                <strong>Approved public issue</strong>
                <p>{issue.summary}</p>
                <p>
                  {categories[issue.category]} · {statuses[issue.status]}
                </p>
                <p>
                  Published {new Date(issue.publishedAt).toLocaleDateString()} · Approximate
                  location ({issue.latitude.toFixed(3)}, {issue.longitude.toFixed(3)})
                </p>
                <Link to={`/issues/${encodeURIComponent(issue.publicIssueId)}`}>
                  View public issue
                </Link>
              </Popup>
            </Marker>
          ))}
          {selection && (
            <Marker
              icon={radiusMeters ? searchMarker : selectedMarker}
              position={[selection.latitude, selection.longitude]}
              title={radiusMeters ? 'Search center' : 'Selected location'}
              alt={radiusMeters ? 'Search center' : 'Selected location'}
              zIndexOffset={radiusMeters ? -500 : 0}
              draggable={Boolean(onSelect)}
              autoPan
              eventHandlers={{
                dragend(event) {
                  const point = event.target.getLatLng()
                  if (Math.abs(point.lat) <= 90) onSelect?.(point.lat, wrapLongitude(point.lng))
                },
              }}
            >
              <Popup>
                {radiusMeters
                  ? 'Search center — drag to change the nearby search location.'
                  : onSelect
                    ? 'Issue location — drag to adjust. Saved only when you submit.'
                    : 'Selected location'}
              </Popup>
            </Marker>
          )}
        </MapContainer>
      </div>
      <p className="text-xs text-slate-600">
        {radiusMeters
          ? 'Click to change the search center; the selected radius is preserved. Map clusters count individual visible reports, not unique incidents. '
          : onSelect
            ? 'Click to choose the issue location; drag the marker to refine it. '
            : `${publicIssues.length} approved public markers · ${issues.length} simulated markers. `}
        <a
          className="underline"
          href="https://www.openstreetmap.org/fixthemap"
          target="_blank"
          rel="noreferrer"
        >
          Report a basemap issue
        </a>
      </p>
    </div>
  )
}
