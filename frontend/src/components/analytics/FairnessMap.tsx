import { useState } from 'react'
import { MapContainer, Rectangle, Tooltip } from 'react-leaflet'
import type { FairnessArea } from '../../services/civicIntelligenceService'
import { MapResize, OpenStreetMapTiles } from '../maps/MapSupport'

export type FairnessMeasure =
  | 'medianWorkStartHours'
  | 'overdueRate'
  | 'activeIncidents'
  | 'verifiedResolutionRate'
  | 'confirmedRecurrenceIncidents'
export default function FairnessMap({
  areas,
  measure,
  serviceAreas = {},
}: {
  areas: FairnessArea[]
  measure: FairnessMeasure
  serviceAreas?: Record<string, number[]>
}) {
  const [tiles, setTiles] = useState(false)
  const [tileError, setTileError] = useState(false)
  if (!areas.length) return <p>No occupied geographic cells in this cohort.</p>
  const maximum = Math.max(1, ...areas.map((a) => a[measure] ?? 0))
  const south = Math.min(...areas.map((a) => a.south)),
    west = Math.min(...areas.map((a) => a.west))
  const north = Math.max(...areas.map((a) => a.north)),
    east = Math.max(...areas.map((a) => a.east))
  return (
    <section className="space-y-3" aria-label="Private geographic service comparison map">
      <p className="text-sm">
        Legend: gray = insufficient comparison data; blue intensity = selected recorded metric, not
        a fairness ranking. Exact values and sample sizes are in the accessible table.
      </p>
      <label className="flex gap-2 text-sm">
        <input
          type="checkbox"
          checked={tiles}
          onChange={(e) => {
            setTiles(e.target.checked)
            setTileError(false)
          }}
        />
        Load optional OpenStreetMap basemap (shares tile requests externally)
      </label>
      {tiles && tileError && (
        <p role="status">
          Map tiles are unavailable. Geographic cells and the data table remain available. Toggle
          the basemap to retry.
        </p>
      )}
      <MapContainer
        key={`${south}:${west}:${north}:${east}`}
        bounds={[
          [south, west],
          [north, east],
        ]}
        scrollWheelZoom={false}
        className="h-96 w-full rounded-xl bg-slate-100"
      >
        <MapResize />
        {tiles && <OpenStreetMapTiles onError={() => setTileError(true)} />}
        {Object.entries(serviceAreas).map(([name, bounds]) => (
          <Rectangle
            key={name}
            bounds={[
              [bounds[0], bounds[1]],
              [bounds[2], bounds[3]],
            ]}
            pathOptions={{ color: '#0f766e', weight: 2, dashArray: '6 4', fill: false }}
          >
            <Tooltip>
              Configured service-area boundary: {name}; not a verified ward boundary
            </Tooltip>
          </Rectangle>
        ))}
        {areas.slice(0, 500).map((area) => (
          <Rectangle
            key={area.areaId}
            bounds={[
              [area.south, area.west],
              [area.north, area.east],
            ]}
            pathOptions={{
              color: area.dataSufficient ? '#1d4ed8' : '#64748b',
              weight: 1,
              fillOpacity:
                area[measure] === null ? 0.1 : 0.15 + (0.6 * (area[measure] ?? 0)) / maximum,
            }}
          >
            <Tooltip>
              Cell {area.cell}: {measure} = {area[measure] ?? 'unavailable'}; {area.incidentCount}{' '}
              incidents; {area.responseObservations} recorded work starts; {area.slaObservations}{' '}
              SLA observations; {area.status}
            </Tooltip>
          </Rectangle>
        ))}
      </MapContainer>
      <p className="text-xs">
        At most 500 map cells; the table includes the full bounded result. No automatic polling or
        public data publication.
      </p>
    </section>
  )
}
