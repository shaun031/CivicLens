import { useEffect, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { Field } from '../common/FormParts'
import { searchLocation, type LocationResult } from '../../services/locationSearch'

export function LocationSearch({
  onSelect,
  disabled,
}: {
  onSelect: (latitude: number, longitude: number) => void
  disabled: boolean
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<LocationResult[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  const pending = useRef(false)
  useEffect(
    () => () => {
      generation.current++
    },
    [],
  )
  async function search() {
    if (pending.current || disabled) return
    pending.current = true
    const current = ++generation.current
    setBusy(true)
    setResults([])
    setMessage('')
    try {
      const found = await searchLocation(query)
      if (current !== generation.current) return
      setResults(found)
      setMessage(
        found.length
          ? 'Choose a result to set the marker, then adjust it on the map.'
          : 'No results. Try coordinates or choose a point on the map.',
      )
    } catch (error) {
      if (current === generation.current)
        setMessage(
          error instanceof Error
            ? error.message
            : 'Location search is unavailable. Use manual coordinates.',
        )
    } finally {
      pending.current = false
      if (current === generation.current) setBusy(false)
    }
  }
  return (
    <details className="location-search">
      <summary>Find a location</summary>
      <p className="mt-2 text-sm text-slate-600">
        Search coordinates such as latitude, longitude. Place names require an operator-configured
        search provider.
      </p>
      <div className="location-search-controls">
        <Field
          id="location-search"
          label="Search location"
          value={query}
          maxLength={200}
          disabled={disabled || busy}
          onChange={(event) => {
            setQuery(event.target.value)
            setResults([])
            setMessage('')
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void search()
            }
          }}
        />
        <button
          type="button"
          className="location-action"
          disabled={disabled || busy}
          onClick={() => void search()}
        >
          <Search size={18} aria-hidden="true" />
          {busy ? 'Searching…' : 'Search location'}
        </button>
      </div>
      {message && (
        <p role="status" className="mt-2 text-sm text-slate-700">
          {message}
        </p>
      )}
      {results.length > 0 && (
        <ul aria-label="Location search results" className="mt-2 space-y-2">
          {results.map((result, index) => (
            <li key={index}>
              <button
                type="button"
                className="location-result"
                disabled={disabled}
                onClick={() => {
                  onSelect(result.latitude, result.longitude)
                  setResults([])
                  setMessage('Location selected. Adjust the marker if needed.')
                }}
              >
                Use {result.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </details>
  )
}
