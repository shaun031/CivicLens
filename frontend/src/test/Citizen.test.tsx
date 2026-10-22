import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { Principal } from '../auth/types'
import { complaintService } from '../services/complaintService'

vi.mock('../components/complaints/ComplaintMap', () => ({
  default: ({
    issues = [],
    onSelect,
  }: {
    issues?: unknown[]
    onSelect?: (lat: number, lng: number) => void
  }) => (
    <div role="region" aria-label="Infrastructure issue map">
      <p>{issues.length} simulated markers</p>
      <button type="button" onClick={() => onSelect?.(12.97, 77.59)}>
        Select sample coordinate
      </button>
    </div>
  ),
}))
const citizen: Principal = {
  id: 'actual-user',
  email: 'real@example.com',
  display_name: 'Actual Citizen',
  role: 'CITIZEN',
  provider: 'local',
  is_active: true,
  is_verified: true,
  is_authenticated: true,
}
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
function setup(path: string, user: Principal | null = citizen) {
  const fetch = vi.fn(async (url: string) => {
    if (url.endsWith('/auth/me'))
      return json(user ?? { detail: 'Sign in required.' }, user ? 200 : 401)
    if (url.includes('/notifications?')) return json({ items: [], nextCursor: null })
    if (url.endsWith('/notifications/unread-count')) return json({ unreadCount: 0 })
    if (url.includes('/complaints?')) return json({ items: [], nextCursor: null })
    if (url.endsWith('/complaints/summary')) return json({ total: 0, counts: {}, recent: [] })
    if (url.includes('/complaints/')) return json({ detail: 'Complaint not found.' }, 404)
    return json({ message: 'Access granted.' })
  })
  vi.stubGlobal('fetch', fetch)
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
  return fetch
}
async function samples() {
  await userEvent.click(await screen.findByRole('checkbox', { name: 'Show sample data' }))
}
beforeEach(() => {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:sample-preview')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Citizen experience', () => {
  it('shows the real greeting, empty account statistics, and all quick actions', async () => {
    setup('/citizen/dashboard')
    expect(await screen.findByText(/Welcome back, Actual Citizen/)).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'No complaints yet' })).toBeInTheDocument()
    for (const text of [
      'Report New Issue',
      'View My Complaints',
      'Explore Nearby Issues',
      'View Notifications',
    ])
      expect(screen.getByRole('link', { name: new RegExp(text) })).toBeInTheDocument()
    expect(screen.queryByText('fictional-demo-citizen')).not.toBeInTheDocument()
  })
  it('keeps fictional statistics opt-in and removes sample data immediately when disabled', async () => {
    setup('/citizen/dashboard')
    await samples()
    expect(
      await screen.findByRole('region', { name: 'Simulated complaint statistics' }),
    ).toBeInTheDocument()
    expect(await screen.findByText('Recent sample complaints')).toBeInTheDocument()
    await samples()
    expect(screen.queryByText('Recent sample complaints')).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'No complaints yet' })).toBeInTheDocument()
  })
  it('searches, filters, sorts, and clears sample complaints', async () => {
    setup('/citizen/complaints')
    await samples()
    await screen.findByText(/6 simulated complaints matching/)
    const search = screen.getByRole('searchbox')
    await userEvent.type(search, 'library')
    expect(await screen.findByText(/1 simulated complaints matching/)).toBeInTheDocument()
    await userEvent.clear(search)
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'DRAINAGE')
    expect(await screen.findByRole('heading', { name: /Blocked drain/ })).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'SUBMITTED')
    expect(
      await screen.findByRole('heading', { name: 'No matching complaints' }),
    ).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    await userEvent.selectOptions(screen.getByLabelText('Sort by'), 'oldest')
    await waitFor(() =>
      expect(screen.getAllByRole('article')[0]).toHaveTextContent('Pothole beside'),
    )
  })
  it('navigates from a sample card to its own details, not a random complaint', async () => {
    setup('/citizen/complaints')
    await samples()
    await userEvent.click(await screen.findByRole('link', { name: /View details: Pothole/ }))
    expect(
      await screen.findByRole('heading', { name: 'Pothole beside the community library' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/sample-1/)).toBeInTheDocument()
    expect(screen.queryByText(/Not yet reached:/)).not.toBeInTheDocument()
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByText('Submitted')).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: /Preview Illustration/ }))
    expect(screen.getByRole('dialog', { name: 'Evidence preview' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it.each(['/citizen/complaints/does-not-exist', '/citizen/complaints/sample-1'])(
    'does not silently substitute a fixture for %s in account mode',
    async (path) => {
      setup(path)
      expect(
        await screen.findByRole('heading', { name: 'Complaint not found' }),
      ).toBeInTheDocument()
    },
  )
  it('keeps an invalid sample ID not found even in sample mode', async () => {
    setup('/citizen/complaints/missing')
    await samples()
    expect(await screen.findByRole('heading', { name: 'Complaint not found' })).toBeInTheDocument()
  })
  it('validates required fields inline and focuses the first invalid input', async () => {
    const fetch = setup('/citizen/report')
    await userEvent.click(await screen.findByRole('button', { name: /Preview locally/ }))
    expect(screen.getByText('Choose a complaint category.')).toBeInTheDocument()
    expect(screen.getByLabelText('Complaint category')).toHaveFocus()
    expect(screen.getByText(/Enter latitude from/)).toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => url === '/api/complaints')).toBe(false)
  })
  it('validates and previews without sending or persisting a complaint', async () => {
    const fetch = setup('/citizen/report')
    await screen.findByLabelText('Complaint category')
    await userEvent.selectOptions(screen.getByLabelText('Complaint category'), 'POTHOLE')
    await userEvent.type(screen.getByLabelText('Complaint title'), 'Road defect near library')
    await userEvent.type(
      screen.getByLabelText('Description'),
      'An uneven surface creates a hazard for people cycling here.',
    )
    await userEvent.type(screen.getByLabelText('Location / landmark'), 'Library Road')
    await userEvent.type(screen.getByLabelText('Latitude'), '999')
    await userEvent.type(screen.getByLabelText('Longitude'), '77')
    await userEvent.click(screen.getByRole('button', { name: /Preview locally/ }))
    expect(screen.getByText(/Enter latitude from/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Select sample coordinate' }))
    await userEvent.click(screen.getByRole('button', { name: /Preview locally/ }))
    const dialog = screen.getByRole('dialog', { name: /Local report preview/ })
    expect(within(dialog).getByText(/This preview does not submit/)).toBeInTheDocument()
    expect(within(dialog).getByText('Road defect near library')).toBeInTheDocument()
    expect(
      fetch.mock.calls.every(([url]) =>
        /auth\/me|portal\/citizen|notifications\/unread-count/.test(url),
      ),
    ).toBe(true)
  })
  it('rejects unsupported and oversized files; previews valid evidence and revokes URLs', async () => {
    setup('/citizen/report')
    const input = await screen.findByLabelText('Photograph evidence (optional)')
    fireEvent.change(input, {
      target: { files: [new File(['data'], 'test.svg', { type: 'image/svg+xml' })] },
    })
    expect(screen.getByRole('alert')).toHaveTextContent('Only JPEG, PNG, and WebP')
    const oversized = new File(['small'], 'large.png', { type: 'image/png' })
    Object.defineProperty(oversized, 'size', { value: 6 * 1024 * 1024 })
    fireEvent.change(input, { target: { files: [oversized] } })
    expect(screen.getByRole('alert')).toHaveTextContent('no larger than 1.5 MiB')
    fireEvent.change(input, {
      target: { files: [new File(['image'], 'road.png', { type: 'image/png' })] },
    })
    expect(await screen.findByAltText('Selected evidence: road.png')).toHaveAttribute(
      'src',
      'blob:sample-preview',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Remove image 1' }))
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:sample-preview'))
    expect(screen.queryByAltText('Selected evidence: road.png')).not.toBeInTheDocument()
  })
  it('retains a draft across citizen routes and only clears after confirmation', async () => {
    setup('/citizen/report')
    await userEvent.type(await screen.findByLabelText('Complaint title'), 'Retained draft')
    await userEvent.click(screen.getByRole('link', { name: 'My Complaints' }))
    await userEvent.click(
      within(screen.getByRole('navigation', { name: 'Citizen navigation' })).getByRole('link', {
        name: 'Report an Issue',
      }),
    )
    expect(await screen.findByLabelText('Complaint title')).toHaveValue('Retained draft')
    await userEvent.click(screen.getByRole('button', { name: 'Clear form' }))
    await userEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.getByLabelText('Complaint title')).toHaveValue('Retained draft')
    await userEvent.click(screen.getByRole('button', { name: 'Clear form' }))
    await userEvent.click(screen.getByRole('button', { name: 'Clear draft' }))
    expect(screen.getByLabelText('Complaint title')).toHaveValue('')
  })
  it('filters nearby markers and handles denied geolocation without automatic requests', async () => {
    const getCurrentPosition = vi.fn((_success, fail) => fail({ code: 1 }))
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } })
    setup('/citizen/nearby')
    await samples()
    expect(await screen.findByText('6 simulated markers')).toBeInTheDocument()
    expect(getCurrentPosition).not.toHaveBeenCalled()
    await userEvent.selectOptions(screen.getByLabelText('Map category'), 'BROKEN_STREETLIGHT')
    expect(screen.getByText('1 simulated markers')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Use My Location' }))
    expect(await screen.findByText(/Location permission denied/)).toBeInTheDocument()
  })
  it('uses local read state only and resets to empty when sample mode is off', async () => {
    setup('/citizen/notifications')
    expect(await screen.findByRole('heading', { name: 'No notifications yet' })).toBeInTheDocument()
    await samples()
    await screen.findByRole('heading', { name: 'Complaint received' })
    await userEvent.selectOptions(screen.getByLabelText('Read status'), 'unread')
    expect(screen.getAllByRole('article')).toHaveLength(4)
    await userEvent.click(screen.getAllByRole('button', { name: /Mark sample as read/ })[0])
    expect(screen.getAllByRole('article')).toHaveLength(3)
    await samples()
    expect(await screen.findByRole('heading', { name: 'No notifications yet' })).toBeInTheDocument()
  })
  it('shows a load error and supports a successful retry', async () => {
    vi.spyOn(complaintService, 'list').mockRejectedValueOnce(new Error('Sample view unavailable.'))
    setup('/citizen/complaints')
    expect(await screen.findByRole('alert')).toHaveTextContent('Sample view unavailable.')
    await userEvent.click(screen.getByRole('button', { name: /Retry/ }))
    expect(await screen.findByRole('heading', { name: 'No complaints yet' })).toBeInTheDocument()
  })
  it.each([
    '/citizen/report',
    '/citizen/complaints',
    '/citizen/nearby',
    '/citizen/notifications',
    '/citizen/profile',
  ])('protects %s from anonymous users and officers', async (path) => {
    setup(path, { ...citizen, role: 'OFFICER' })
    expect(await screen.findByRole('heading', { name: /Access denied/ })).toBeInTheDocument()
  })
})
