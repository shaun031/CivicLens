import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { complaintService } from '../services/complaintService'
import { emptyDraft } from '../types/complaint'

vi.mock('../components/complaints/ComplaintMap', () => ({
  default: () => (
    <div aria-label="Infrastructure issue map" role="region">
      Map
    </div>
  ),
}))
const id = '771b060e-abaf-4290-81b7-e28b1322ec74'
const imageId = '0372fa75-135f-474e-8085-ec5aa0f8c58d'
const principal = {
  id: 'real-owner',
  email: 'citizen@example.com',
  display_name: 'Real Citizen',
  role: 'CITIZEN',
  provider: 'local',
  is_active: true,
  is_verified: true,
  is_authenticated: true,
}
const stored = {
  complaintId: id,
  citizenId: principal.id,
  title: 'Pothole near the community library',
  description: 'An uneven road surface is dangerous for people cycling here.',
  category: 'POTHOLE',
  reportedSeverity: 'HIGH',
  latitude: 12.97,
  longitude: 77.59,
  landmark: 'Library gate',
  addressLabel: 'Library Road',
  status: 'SUBMITTED',
  incidentId: null,
  createdAt: '2026-10-19T12:00:00.000Z',
  updatedAt: '2026-10-19T12:00:00.000Z',
  images: [],
}
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
function setup(
  path: string,
  handler?: (url: string, init?: RequestInit) => Response | Promise<Response> | undefined,
) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const handled = handler?.(url, init)
    if (handled) return handled
    if (url.endsWith('/auth/me')) return json(principal)
    if (url.includes('/portal/')) return json({ message: 'Access granted.' })
    if (url.endsWith('/complaints/summary'))
      return json({ total: 1, counts: { SUBMITTED: 1 }, recent: [stored] })
    if (url.includes('/complaints?')) return json({ items: [stored], nextCursor: null })
    if (url === '/api/complaints') return json(stored, 201)
    if (url.endsWith(`/complaints/${id}`)) return json(stored)
    return json({ detail: 'Complaint not found.' }, 404)
  })
  vi.stubGlobal('fetch', fetch)
  const rendered = render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
  return { fetch, ...rendered }
}
async function fill() {
  await screen.findByLabelText('Complaint category')
  for (const [label, value] of [
    ['Complaint category', 'POTHOLE'],
    ['Complaint title', stored.title],
    ['Description', stored.description],
    ['Latitude', '12.97'],
    ['Longitude', '77.59'],
    ['Location / landmark', 'Library Road'],
    ['Landmark (optional)', 'Library gate'],
    ['User-reported severity', 'HIGH'],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
}
beforeEach(() => {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:private-evidence')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Real complaint API integration', () => {
  it('does not claim success for an invalid successful API response', async () => {
    setup('/citizen/report', (url) =>
      url === '/api/complaints' ? json({ message: 'not a saved complaint' }) : undefined,
    )
    await fill()
    fireEvent.click(screen.getByRole('button', { name: 'Submit Complaint' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('invalid response')
    expect(screen.queryByText('Submission successful.')).not.toBeInTheDocument()
  })
  it('submits multipart fields with a scoped request key, cookie credentials and no manually set boundary', async () => {
    const { fetch } = setup('/citizen/report')
    await fill()
    fireEvent.click(screen.getByRole('button', { name: 'Submit Complaint' }))
    expect(await screen.findByRole('heading', { name: 'Complaint submitted' })).toBeInTheDocument()
    expect(screen.getByText(id)).toBeInTheDocument()
    const request = fetch.mock.calls.find(([url]) => url === '/api/complaints')![1]!
    const data = request.body as FormData
    expect(data.get('reportedSeverity')).toBe('HIGH')
    expect(data.get('landmark')).toBe('Library gate')
    expect(data.get('latitude')).toBe('12.97')
    expect(data.get('longitude')).toBe('77.59')
    expect(data.has('citizenId')).toBe(false)
    expect(data.has('status')).toBe(false)
    expect(request.credentials).toBe('include')
    expect(request.headers).not.toHaveProperty('Content-Type')
    expect((request.headers as Record<string, string>)['Idempotency-Key']).toMatch(
      /^[0-9a-f-]{36}$/,
    )
    expect(screen.getByRole('link', { name: 'View complaint details' })).toHaveAttribute(
      'href',
      `/citizen/complaints/${id}`,
    )
  })
  it('disables the form and prevents a double click while the real request is pending', async () => {
    let resolve: (response: Response) => void = () => undefined
    const pending = new Promise<Response>((done) => {
      resolve = done
    })
    const { fetch } = setup('/citizen/report', (url) =>
      url === '/api/complaints' ? pending : undefined,
    )
    await fill()
    const button = screen.getByRole('button', { name: 'Submit Complaint' })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(await screen.findByRole('button', { name: 'Submitting...' })).toBeDisabled()
    expect(screen.getByLabelText('Complaint title')).toBeDisabled()
    expect(fetch.mock.calls.filter(([url]) => url === '/api/complaints')).toHaveLength(1)
    resolve(json(stored, 201))
    expect(await screen.findByText('Submission successful.')).toBeInTheDocument()
  })
  it('retains data and reuses the idempotency key after failure without claiming success', async () => {
    let attempts = 0
    const { fetch } = setup('/citizen/report', (url) =>
      url === '/api/complaints'
        ? ++attempts === 1
          ? json({ detail: 'Evidence storage is unavailable.' }, 503)
          : json(stored, 201)
        : undefined,
    )
    await fill()
    fireEvent.click(screen.getByRole('button', { name: 'Submit Complaint' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Evidence storage is unavailable.')
    expect(screen.getByLabelText('Complaint title')).toHaveValue(stored.title)
    expect(screen.queryByText('Submission successful.')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Submit Complaint' }))
    await screen.findByText('Submission successful.')
    const calls = fetch.mock.calls.filter(([url]) => url === '/api/complaints')
    expect(calls[0][1]?.headers).toEqual(calls[1][1]?.headers)
  })
  it('shows safe network errors while preserving the draft', async () => {
    setup('/citizen/report', (url) =>
      url === '/api/complaints' ? Promise.reject(new TypeError('Network interrupted')) : undefined,
    )
    await fill()
    fireEvent.click(screen.getByRole('button', { name: 'Submit Complaint' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The API is unavailable.')
    expect(screen.getByLabelText('Description')).toHaveValue(stored.description)
  })
  it('handles session expiry during submission through the existing authentication context', async () => {
    setup('/citizen/report', (url) =>
      url === '/api/complaints' ? json({ detail: 'Session expired.' }, 401) : undefined,
    )
    await fill()
    fireEvent.click(screen.getByRole('button', { name: 'Submit Complaint' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
  it('loads actual complaints, searches the full server history and never marks them simulated', async () => {
    const { fetch } = setup('/citizen/complaints', (url) =>
      url.includes('q=not+present') ? json({ items: [], total: 0, nextCursor: null }) : undefined,
    )
    expect(await screen.findByRole('heading', { name: stored.title })).toBeInTheDocument()
    expect(screen.queryByText('Simulated complaint')).not.toBeInTheDocument()
    expect(screen.getByRole('searchbox')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'not present' } })
    expect(
      await screen.findByRole('heading', { name: /No complaints yet|No matching complaints/ }),
    ).toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => url.includes('q=not+present'))).toBe(true)
  })
  it('appends a second cursor page and labels pagination honestly', async () => {
    const second = {
      ...stored,
      complaintId: '3075227e-4e3f-4bb0-b26c-c999955d3aab',
      title: 'Blocked drainage beside the park',
      category: 'DRAINAGE',
    }
    const { fetch } = setup('/citizen/complaints', (url) =>
      url.includes('/complaints?')
        ? json({
            items: [url.includes('cursor=') ? second : stored],
            nextCursor: url.includes('cursor=') ? null : 'opaque-next-page',
          })
        : undefined,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Load more complaints' }))
    expect(await screen.findByRole('heading', { name: second.title })).toBeInTheDocument()
    expect(screen.getByText(/2 account complaints matching · 2 loaded/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load more complaints' })).not.toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => url.includes('cursor=opaque-next-page'))).toBe(true)
  })
  it('shows only real recorded milestones without inventing future events', async () => {
    setup(`/citizen/complaints/${id}`)
    await screen.findByRole('heading', { name: stored.title })
    expect(
      screen.getByText('Complaint submitted. No subsequent status changes have been recorded.'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Not yet reached:/)).not.toBeInTheDocument()
    expect(screen.queryByText('Under Review')).not.toBeInTheDocument()
    expect(screen.getByText('Library gate')).toBeInTheDocument()
  })
  it('retrieves private evidence using the authenticated client and revokes its object URL', async () => {
    const imagePath = `/complaints/${id}/images/${imageId}`
    const { fetch, unmount } = setup(`/citizen/complaints/${id}`, (url) =>
      url.endsWith(imagePath)
        ? new Response(new Uint8Array([255, 216, 255, 217]), {
            headers: { 'Content-Type': 'image/jpeg' },
          })
        : url.endsWith(`/complaints/${id}`)
          ? json({
              ...stored,
              images: [
                { imageId, contentType: 'image/jpeg', fileSize: 4, createdAt: stored.createdAt },
              ],
            })
          : undefined,
    )
    expect(await screen.findByAltText('Submitted photo evidence')).toHaveAttribute(
      'src',
      'blob:private-evidence',
    )
    expect(fetch.mock.calls.find(([url]) => url.endsWith(imagePath))?.[1]?.credentials).toBe(
      'include',
    )
    unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:private-evidence')
  })
  it('keeps unavailable private evidence visible as a fallback, not a broken filesystem URL', async () => {
    setup(`/citizen/complaints/${id}`, (url) =>
      url.includes('/images/')
        ? json({ detail: 'Evidence unavailable.' }, 503)
        : url.endsWith(`/complaints/${id}`)
          ? json({
              ...stored,
              images: [
                { imageId, contentType: 'image/jpeg', fileSize: 4, createdAt: stored.createdAt },
              ],
            })
          : undefined,
    )
    expect(await screen.findByText('Image unavailable')).toBeInTheDocument()
  })
  it('does not substitute samples when real listing fails', async () => {
    setup('/citizen/complaints', (url) =>
      url.includes('/complaints?') ? json({ detail: 'Database unavailable.' }, 503) : undefined,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable.')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })
  it('updates the real dashboard after a successful submission and navigation', async () => {
    let submitted = false
    setup('/citizen/dashboard', (url) => {
      if (url.endsWith('/complaints/summary'))
        return json({
          total: submitted ? 1 : 0,
          counts: submitted ? { SUBMITTED: 1 } : {},
          recent: submitted ? [stored] : [],
        })
      if (url === '/api/complaints') {
        submitted = true
        return json(stored, 201)
      }
    })
    await screen.findByRole('heading', { name: 'No complaints yet' })
    fireEvent.click(screen.getByRole('link', { name: /Report New Issue/ }))
    await fill()
    fireEvent.click(screen.getByRole('button', { name: 'Submit Complaint' }))
    await screen.findByRole('heading', { name: 'Complaint submitted' })
    fireEvent.click(
      within(screen.getByRole('navigation', { name: 'Citizen navigation' })).getByRole('link', {
        name: 'Dashboard',
      }),
    )
    expect(await screen.findByRole('heading', { name: stored.title })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'No complaints yet' })).not.toBeInTheDocument()
  })
  it('uses no complaint API in explicit sample mode and keeps canonical categories', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
    expect((await complaintService.list(true)).items).toHaveLength(6)
    expect((await complaintService.summary(true)).total).toBe(6)
    expect((await complaintService.detail('sample-3', true))?.category).toBe('BROKEN_STREETLIGHT')
    expect(fetch).not.toHaveBeenCalled()
    fetch.mockRestore()
    expect(emptyDraft().requestKey).not.toBe(emptyDraft().requestKey)
  })
  it('does not post invalid form input', async () => {
    const { fetch } = setup('/citizen/report')
    fireEvent.click(await screen.findByRole('button', { name: 'Submit Complaint' }))
    await waitFor(() =>
      expect(screen.getByLabelText('Complaint title')).toHaveAttribute('aria-invalid', 'true'),
    )
    expect(fetch.mock.calls.some(([url]) => url === '/api/complaints')).toBe(false)
  })
})
