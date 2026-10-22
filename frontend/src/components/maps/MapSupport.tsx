import { useEffect } from 'react'
import { TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

/** Leaflet observes window resizes, but not sidebar/grid/hidden-panel changes. */
export function MapResize() {
  const map = useMap()
  useEffect(() => {
    let frame = 0
    const resize = () => {
      cancelAnimationFrame(frame)
      // Preserve the geographic center when the container shrinks. With pan:false,
      // existing marker pixels can remain outside the new mobile clipping area.
      frame = requestAnimationFrame(() =>
        map.invalidateSize({ pan: true, animate: false, debounceMoveend: true }),
      )
    }
    const observer = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(resize)
    observer?.observe(map.getContainer())
    window.addEventListener('resize', resize)
    resize()
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(frame)
    }
  }, [map])
  return null
}

export function OpenStreetMapTiles({
  onError,
  onReady,
}: {
  onError?: () => void
  onReady?: () => void
}) {
  return (
    <TileLayer
      url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      maxZoom={19}
      // Send only the origin, not private routes or query parameters, to OSM.
      referrerPolicy="strict-origin-when-cross-origin"
      updateWhenIdle
      keepBuffer={1}
      eventHandlers={{
        ...(onError ? { tileerror: onError } : {}),
        ...(onReady ? { load: onReady } : {}),
      }}
    />
  )
}
