import { useEffect, useRef, useState } from 'react'
import { divIcon, type Circle as LeafletCircle, type Marker as LeafletMarker } from 'leaflet'
import { Circle, Marker, Popup, useMap, useMapEvents } from 'react-leaflet'
import { Link } from 'react-router-dom'
import type { NearbyIssue } from '../../types/nearby'
import { categories, statuses } from '../../types/complaint'
import { categoryMarker } from './markerIcons'
import { clusterPoints } from './clustering'

function IssueMarker({
  issue,
  active,
  onFocus,
}: {
  issue: NearbyIssue
  active: boolean
  onFocus?: (id: string) => void
}) {
  const map = useMap(),
    marker = useRef<LeafletMarker>(null)
  const { latitude, longitude, issueId } = issue
  const lng = longitude + 360 * Math.round((map.getCenter().lng - longitude) / 360)
  useEffect(() => {
    if (!active) return
    const lon = longitude + 360 * Math.round((map.getCenter().lng - longitude) / 360)
    map.setView([latitude, lon], Math.max(16, map.getZoom()), { animate: false })
    marker.current?.openPopup()
  }, [active, latitude, longitude, issueId, map])
  return (
    <Marker
      ref={marker}
      position={[latitude, lng]}
      icon={categoryMarker(issue.category)}
      title={issue.title}
      alt={issue.title}
      zIndexOffset={active ? 1000 : 0}
      eventHandlers={{ click: () => onFocus?.(issue.issueId) }}
    >
      <Popup
        maxWidth={220}
        minWidth={160}
        maxHeight={200}
        autoPanPaddingTopLeft={[60, 12]}
        autoPanPaddingBottomRight={[12, 12]}
      >
        <strong>{issue.title}</strong>
        <p>
          {categories[issue.category]} · {statuses[issue.status]}
        </p>
        <p>{(issue.distanceMeters / 1000).toFixed(2)} km from search center</p>
        <p>
          {issue.dateLabel} {new Date(issue.createdAt).toLocaleDateString()}
        </p>
        {issue.isOwn && (
          <p>
            <b>My Report</b> · {issue.isPublic ? 'Publicly Visible' : 'Not Publicly Visible'}
          </p>
        )}
        <Link to={issue.detailsUrl}>
          {issue.isOwn ? 'View complaint details' : 'View public issue'}
        </Link>
      </Popup>
    </Marker>
  )
}

export function RadiusCircle({
  latitude,
  longitude,
  radius,
}: {
  latitude: number
  longitude: number
  radius: number
}) {
  const map = useMap()
  const layer = useRef<LeafletCircle>(null)
  useEffect(() => {
    // Leaflet calculates circle bounds using its attached map's pixel projection.
    // The child Circle mounts its layer before this parent effect runs.
    if (Math.abs(latitude) >= 85) {
      map.setView([Math.max(-85, Math.min(85, latitude)), longitude], 3, { animate: false })
      return
    }
    const bounds = layer.current?.getBounds()
    if (bounds?.isValid()) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 15, animate: false })
    else map.setView([Math.max(-85, Math.min(85, latitude)), longitude], 3, { animate: false })
  }, [map, latitude, longitude, radius])
  // Web Mercator cannot represent a polar radius faithfully; avoid enormous or
  // invalid SVG radii without changing the original search coordinates.
  if (Math.abs(latitude) >= 85) return null
  return (
    <Circle
      ref={layer}
      center={[latitude, longitude]}
      radius={radius}
      pathOptions={{ color: '#0d9488', weight: 2, fillOpacity: 0.05, interactive: false }}
    />
  )
}

export function NearbyLayer({
  items,
  focused,
  onFocus,
}: {
  items: NearbyIssue[]
  focused?: string
  onFocus?: (id: string) => void
}) {
  const map = useMap()
  const [, render] = useState(0)
  useMapEvents({ zoomend: () => render((v) => v + 1), moveend: () => render((v) => v + 1) })
  const selected = items.find((item) => item.issueId === focused)
  const groups = clusterPoints(
    items
      .filter((item) => item !== selected)
      .map((item) => {
        const longitude =
          item.longitude + 360 * Math.round((map.getCenter().lng - item.longitude) / 360)
        const point = map.project([item.latitude, longitude], map.getZoom())
        return { item, x: point.x, y: point.y }
      }),
  )
  // Keep individual markers in one keyed sibling list when focus changes. Moving a
  // marker between nested child arrays remounts it during Leaflet's click dispatch
  // and can leave an orphaned popup behind.
  const markers = groups.map((group) =>
    group.length === 1 ? (
      <IssueMarker key={group[0].issueId} issue={group[0]} active={false} onFocus={onFocus} />
    ) : (
      <Marker
        key={`cluster-${group[0].issueId}`}
        position={[
          group[0].latitude,
          group[0].longitude + 360 * Math.round((map.getCenter().lng - group[0].longitude) / 360),
        ]}
        icon={divIcon({
          className: 'nearby-cluster-marker',
          html: `<span>${group.length}</span>`,
          iconSize: [42, 42],
          iconAnchor: [21, 21],
        })}
        title={`${group.length} reports; zoom or open the report list`}
        alt={`${group.length} reports`}
        eventHandlers={{
          click() {
            map.setView([group[0].latitude, group[0].longitude], Math.min(19, map.getZoom() + 2), {
              animate: false,
            })
          },
        }}
      >
        <Popup
          maxWidth={220}
          minWidth={160}
          maxHeight={200}
          autoPanPaddingTopLeft={[60, 12]}
          autoPanPaddingBottomRight={[12, 12]}
        >
          <strong>{group.length} individual reports, not unique incidents</strong>
          <p>
            Zoom in to separate nearby markers. Exactly co-located reports remain at their real
            coordinates; select one below.
          </p>
          <ul>
            {group.map((issue) => (
              <li key={issue.issueId}>
                <button
                  type="button"
                  className="map-retry"
                  onClickCapture={(event) => {
                    // Focus can remove this popup before Leaflet inspects the
                    // bubbling click. Stop it during capture so selecting a
                    // report cannot accidentally choose a new search center.
                    event.stopPropagation()
                    onFocus?.(issue.issueId)
                  }}
                >
                  {issue.title}
                </button>
              </li>
            ))}
          </ul>
        </Popup>
      </Marker>
    ),
  )
  if (selected)
    markers.push(<IssueMarker key={selected.issueId} issue={selected} active onFocus={onFocus} />)
  return <>{markers}</>
}
