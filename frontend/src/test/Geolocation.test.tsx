import { act, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useGeolocation } from '../hooks/useGeolocation'
afterEach(() => vi.restoreAllMocks())
it.each([
  [1, 'permission denied'],
  [2, 'unavailable'],
  [3, 'timed out'],
])('handles geolocation failure code %s', (code, message) => {
  const getCurrentPosition = vi.fn((_success, error) => error({ code }))
  vi.spyOn(navigator, 'geolocation', 'get').mockReturnValue({
    getCurrentPosition,
  } as unknown as Geolocation)
  const callback = vi.fn()
  const { result } = renderHook(() => useGeolocation(callback))
  expect(getCurrentPosition).not.toHaveBeenCalled()
  act(() => result.current.locate())
  expect(result.current.message).toContain(message)
  expect(callback).not.toHaveBeenCalled()
})
it('supports browsers without geolocation', () => {
  vi.spyOn(navigator, 'geolocation', 'get').mockReturnValue(undefined as unknown as Geolocation)
  const { result } = renderHook(() => useGeolocation(vi.fn()))
  act(() => result.current.locate())
  expect(result.current.message).toContain('not supported')
})
it('forwards successful coordinates only after explicit action, without persistence', () => {
  const getCurrentPosition = vi.fn((success) => success({ coords: { latitude: 0, longitude: 0 } }))
  vi.spyOn(navigator, 'geolocation', 'get').mockReturnValue({
    getCurrentPosition,
  } as unknown as Geolocation)
  const callback = vi.fn()
  const { result } = renderHook(() => useGeolocation(callback))
  act(() => result.current.locate())
  expect(callback).toHaveBeenCalledWith(0, 0)
  expect(result.current.message).toContain('not been stored')
})
it('warns about low accuracy while retaining the explicitly requested real coordinates', () => {
  vi.spyOn(navigator, 'geolocation', 'get').mockReturnValue({
    getCurrentPosition: vi.fn((success) =>
      success({ coords: { latitude: 12.97, longitude: 77.59, accuracy: 850 } }),
    ),
  } as unknown as Geolocation)
  const callback = vi.fn()
  const { result } = renderHook(() => useGeolocation(callback))
  act(() => result.current.locate())
  expect(callback).toHaveBeenCalledWith(12.97, 77.59)
  expect(result.current.message).toContain('accuracy ±850 m')
})
it('rejects invalid browser coordinates without selecting a fallback', () => {
  vi.spyOn(navigator, 'geolocation', 'get').mockReturnValue({
    getCurrentPosition: vi.fn((success) => success({ coords: { latitude: NaN, longitude: 200 } })),
  } as unknown as Geolocation)
  const callback = vi.fn()
  const { result } = renderHook(() => useGeolocation(callback))
  act(() => result.current.locate())
  expect(callback).not.toHaveBeenCalled()
  expect(result.current.message).toContain('invalid location')
  expect(result.current.busy).toBe(false)
})
it('deduplicates pending permission requests and ignores success after unmount', () => {
  let success: PositionCallback = () => undefined
  const getCurrentPosition = vi.fn((callback) => {
    success = callback
  })
  vi.spyOn(navigator, 'geolocation', 'get').mockReturnValue({
    getCurrentPosition,
  } as unknown as Geolocation)
  const callback = vi.fn()
  const { result, unmount } = renderHook(() => useGeolocation(callback))
  act(() => {
    result.current.locate()
    result.current.locate()
  })
  expect(getCurrentPosition).toHaveBeenCalledTimes(1)
  unmount()
  act(() => success({ coords: { latitude: 0, longitude: 0, accuracy: 1 } } as GeolocationPosition))
  expect(callback).not.toHaveBeenCalled()
})
