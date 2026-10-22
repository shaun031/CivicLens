import { divIcon } from 'leaflet'
import { categoryConfig, markerConfig } from './categoryConfig'
const icons = new Map(
  Object.keys(categoryConfig).map((category) => {
    const config = markerConfig(category)
    return [
      category,
      divIcon({
        className: 'civic-map-marker category-map-marker',
        iconSize: [36, 36],
        iconAnchor: [18, 18],
        html: `<span style="background:${config.color}"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="#0f172a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${config.paths.map((path) => `<path d="${path}"/>`).join('')}</svg></span>`,
      }),
    ]
  }),
)
export function categoryMarker(category: string) {
  return icons.get(category) ?? icons.get('OTHER')!
}
