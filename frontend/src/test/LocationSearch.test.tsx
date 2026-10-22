import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { createLocationSearch } from '../services/locationSearch'
import { LocationSearch } from '../components/complaints/LocationSearch'
import { wrapLongitude } from '../components/maps/mapConfig'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('searches real coordinate input offline, including zero and boundary values', async () => {
  const fetch = vi.fn()
  const search = createLocationSearch(undefined, fetch)
  expect(await search('0, 0')).toEqual([{ label: 'Coordinates: 0, 0', latitude: 0, longitude: 0 }])
  expect((await search('-90, 180'))[0]).toMatchObject({ latitude: -90, longitude: 180 })
  expect(fetch).not.toHaveBeenCalled()
  expect(wrapLongitude(181)).toBe(-179)
  expect(wrapLongitude(-181)).toBe(179)
})

it.each(['91, 0', '0, -181', 'NaN, 0', 'London'])(
  'never invents a location for %s with no provider',
  async (query) => {
    const fetch = vi.fn()
    await expect(createLocationSearch(undefined, fetch)(query)).rejects.toThrow('not configured')
    expect(fetch).not.toHaveBeenCalled()
  },
)

it('requires an explicit result choice and does not submit the complaint from search', async () => {
  const selected = vi.fn(),
    submitted = vi.fn((event) => event.preventDefault())
  render(
    <form onSubmit={submitted}>
      <LocationSearch onSelect={selected} disabled={false} />
    </form>,
  )
  fireEvent.click(screen.getByText('Find a location'))
  fireEvent.change(screen.getByLabelText('Search location'), {
    target: { value: '13.123456, 77.654321' },
  })
  fireEvent.keyDown(screen.getByLabelText('Search location'), { key: 'Enter' })
  const result = await screen.findByRole('button', {
    name: 'Use Coordinates: 13.123456, 77.654321',
  })
  expect(selected).not.toHaveBeenCalled()
  expect(submitted).not.toHaveBeenCalled()
  fireEvent.click(result)
  expect(selected).toHaveBeenCalledWith(13.123456, 77.654321)
})

it('accepts a configured same-origin adapter, caches results and limits uncached requests', async () => {
  const request = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        results: [
          { label: 'Library', latitude: 12.97, longitude: 77.59 },
          { label: 'Bad', latitude: 100, longitude: 0 },
        ],
      }),
    ),
  )
  const search = createLocationSearch('/api/test-geocoder', request)
  expect(await search('Library')).toEqual([{ label: 'Library', latitude: 12.97, longitude: 77.59 }])
  expect(await search('library')).toHaveLength(1)
  expect(request).toHaveBeenCalledTimes(1)
  expect(request.mock.calls[0][0]).toBe('/api/test-geocoder?q=Library')
  expect(request.mock.calls[0][1].credentials).toBe('omit')
  await expect(search('Another place')).rejects.toThrow('wait a moment')
})

it.each(['https://nominatim.openstreetmap.org/search', '//external.example/search'])(
  'rejects an external search endpoint %s',
  async (endpoint) => {
    const request = vi.fn()
    await expect(createLocationSearch(endpoint, request)('Library')).rejects.toThrow(
      'configuration',
    )
    expect(request).not.toHaveBeenCalled()
  },
)

it.each([new Response('{}'), new Response('unavailable', { status: 503 })])(
  'reports unavailable or malformed provider responses',
  async (response) => {
    await expect(
      createLocationSearch('/api/test-geocoder', vi.fn().mockResolvedValue(response))('Library'),
    ).rejects.toThrow(/unavailable|invalid response/)
  },
)
