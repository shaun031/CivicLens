import { useEffect, useRef, useState } from 'react'
import { validCoordinates } from '../utils/validation'
export function useGeolocation(onLocation: (latitude: number, longitude: number) => void) {
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const active = useRef(true)
  const pending = useRef(false)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  function locate() {
    if (pending.current) return
    if (!navigator.geolocation) {
      setMessage('Geolocation is not supported. Choose a location manually.')
      return
    }
    setBusy(true)
    pending.current = true
    setMessage(null)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        pending.current = false
        if (!active.current) return
        setBusy(false)
        if (
          !validCoordinates(String(position.coords.latitude), String(position.coords.longitude))
        ) {
          setMessage('The browser returned an invalid location. Choose a location manually.')
          return
        }
        onLocation(position.coords.latitude, position.coords.longitude)
        const accuracy = position.coords.accuracy
        setMessage(
          Number.isFinite(accuracy) && accuracy > 100
            ? `Approximate location selected (accuracy ±${Math.round(accuracy)} m). Drag the marker or edit coordinates to identify the issue. It has not been stored.`
            : 'Current location selected. Check or adjust the marker before submitting. It has not been stored.',
        )
      },
      (error) => {
        pending.current = false
        if (!active.current) return
        setBusy(false)
        setMessage(
          error.code === 1
            ? 'Location permission denied. Choose a location manually.'
            : error.code === 3
              ? 'Location request timed out. Try again or choose manually.'
              : 'Location unavailable. Choose a location manually.',
        )
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    )
  }
  return { locate, busy, message }
}
