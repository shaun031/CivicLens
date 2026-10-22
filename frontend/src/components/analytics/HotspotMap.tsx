import { useState } from 'react'
import { MapContainer, Rectangle, Tooltip, useMapEvents } from 'react-leaflet'
import type { HotspotCell } from '../../services/analyticsService'
import { MapResize, OpenStreetMapTiles } from '../maps/MapSupport'

function Viewport({ onBounds }: { onBounds: (bounds: number[]) => void }) {
  const map = useMapEvents({
    moveend() {
      const b = map.getBounds()
      onBounds([b.getSouth(), b.getWest(), b.getNorth(), b.getEast()])
    },
  })
  return null
}
export default function HotspotMap({
  cells,
  bounds,
  measure,
  onBounds,
}: {
  cells: HotspotCell[]
  bounds: number[]
  measure: 'incidentCount' | 'reportCount' | 'criticalIncidents' | 'overdueIncidents'
  onBounds: (bounds: number[]) => void
}) {
  const [tiles, setTiles] = useState(false)
  const [tileError, setTileError] = useState(false)
  const maximum = Math.max(1, ...cells.map((c) => c[measure]))
  return (
    <section aria-label="Private geographic concentration map" className="space-y-3">
      <p className="text-sm">
        Darker cells show higher{' '}
        {measure === 'reportCount'
          ? 'report volume'
          : measure === 'incidentCount'
            ? 'canonical incident counts'
            : measure === 'criticalIncidents'
              ? 'critical incident counts'
              : 'overdue incident counts'}
        . Exact values are in the data table. This is observed reporting, not validated geographic
        risk.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={tiles}
          onChange={(event) => {
            setTiles(event.target.checked)
            setTileError(false)
          }}
        />
        Load optional OpenStreetMap basemap (shares map tile requests externally)
      </label>
      {tiles && tileError && (
        <p role="status">
          Map tiles are unavailable. Geographic cells and the data table remain available. Toggle
          the basemap to retry.
        </p>
      )}
      <MapContainer
        key={bounds.join(':')}
        bounds={[
          [bounds[0], bounds[1]],
          [bounds[2], bounds[3]],
        ]}
        scrollWheelZoom={false}
        className="h-96 w-full rounded-xl bg-slate-100"
      >
        <Viewport onBounds={onBounds} />
        <MapResize />
        {tiles && <OpenStreetMapTiles onError={() => setTileError(true)} />}
        {cells.slice(0, 500).map((cell) => (
          <Rectangle
            key={cell.cell}
            bounds={[
              [cell.south, cell.west],
              [cell.north, cell.east],
            ]}
            pathOptions={{
              color: '#1d4ed8',
              weight: 1,
              fillOpacity: cell[measure] ? 0.15 + (0.65 * cell[measure]) / maximum : 0,
            }}
          >
            <Tooltip>
              Cell {cell.cell}: {cell.incidentCount} canonical incidents; {cell.reportCount}{' '}
              reports; {cell.overdueIncidents} overdue
            </Tooltip>
          </Rectangle>
        ))}
      </MapContainer>
      <p className="text-xs text-slate-600">
        Map renders at most 500 occupied cells; the accessible list contains the full bounded
        response. Pan/zoom, then explicitly apply the viewport to request new data. No automatic
        polling.
      </p>
    </section>
  )
}
