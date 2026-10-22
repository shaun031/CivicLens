import { validCoordinates } from '../utils/validation'

export interface LocationResult {
  label: string
  latitude: number
  longitude: number
}

/** Optional same-origin adapter. No public geocoding service is contacted by default.
 * An operator-enabled endpoint must implement application-wide provider limits,
 * identification, caching and attribution; browser limits alone are insufficient.
 */
export function createLocationSearch(endpoint?: string, request: typeof fetch = fetch) {
  const cache = new Map<string, { at: number; results: LocationResult[] }>()
  let lastRequest = -Infinity
  let pending = false
  return async (query: string): Promise<LocationResult[]> => {
    const value = query.trim()
    if (!value || value.length > 200)
      throw new Error('Enter a location using no more than 200 characters.')
    const pair = value.split(',').map((part) => part.trim())
    if (pair.length === 2 && validCoordinates(pair[0], pair[1]))
      return [
        {
          label: `Coordinates: ${pair.join(', ')}`,
          latitude: Number(pair[0]),
          longitude: Number(pair[1]),
        },
      ]
    if (!endpoint)
      throw new Error(
        'Place search is not configured. Search for latitude, longitude, click the map, or enter coordinates manually.',
      )
    if (!endpoint.startsWith('/') || endpoint.startsWith('//'))
      throw new Error(
        'Place search configuration is unavailable. Use the map or manual coordinates.',
      )
    const key = value.toLocaleLowerCase()
    const cached = cache.get(key)
    if (cached && Date.now() - cached.at < 300000) return cached.results
    if (pending || Date.now() - lastRequest < 1000)
      throw new Error('Please wait a moment before searching again.')
    pending = true
    lastRequest = Date.now()
    try {
      const url = new URL(endpoint, window.location.origin)
      url.searchParams.set('q', value)
      const response = await request(url.pathname + url.search, {
        headers: { Accept: 'application/json' },
        credentials: 'omit',
        signal: AbortSignal.timeout(8000),
      })
      if (!response.ok)
        throw new Error('Place search is unavailable. Use the map or manual coordinates.')
      const data: unknown = await response.json()
      if (!data || typeof data !== 'object' || !('results' in data) || !Array.isArray(data.results))
        throw new Error('Place search returned an invalid response. Use manual coordinates.')
      const results = data.results
        .slice(0, 5)
        .filter((row): row is LocationResult =>
          Boolean(
            row &&
            typeof row.label === 'string' &&
            row.label.length > 0 &&
            row.label.length <= 200 &&
            typeof row.latitude === 'number' &&
            typeof row.longitude === 'number' &&
            validCoordinates(String(row.latitude), String(row.longitude)),
          ),
        )
      if (cache.size >= 30) cache.delete(cache.keys().next().value!)
      cache.set(key, { at: Date.now(), results })
      return results
    } finally {
      pending = false
    }
  }
}

export const searchLocation = createLocationSearch(import.meta.env.VITE_LOCATION_SEARCH_URL)
