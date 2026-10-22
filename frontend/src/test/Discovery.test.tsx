import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { Link, MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { MapBounds, PublicIssue } from '../types/complaint'
import { discoveryService } from '../services/discoveryService'
import type { NearbyIssue } from '../types/nearby'

vi.mock('../components/complaints/ComplaintMap', () => ({
  default: ({
    publicIssues = [],
    onBoundsChange,
    nearbyIssues = [],
    onSelect,
    radiusMeters,
  }: {
    publicIssues?: PublicIssue[]
    onBoundsChange?: (bounds: MapBounds) => void
    nearbyIssues?: NearbyIssue[]
    onSelect?: (lat: number, lon: number) => void
    radiusMeters?: number
  }) => (
    <div role="region" aria-label="Infrastructure issue map">
      <button
        onClick={() => {
          onSelect?.(12.96, 77.58)
          onBoundsChange?.({
            minLatitude: 12.96,
            maxLatitude: 12.99,
            minLongitude: 77.58,
            maxLongitude: 77.61,
          })
        }}
      >
        Move map
      </button>
      {publicIssues.map((item) => (
        <Link key={item.publicIssueId} to={`/issues/${item.publicIssueId}`}>
          {item.summary}
        </Link>
      ))}
      <span>Radius circle: {radiusMeters ?? 0} metres</span>
      {nearbyIssues.map((item) => (
        <Link key={item.issueId} to={item.detailsUrl}>
          {item.title}
        </Link>
      ))}
    </div>
  ),
}))
const id = '706d4e75-2753-48e1-bf8b-a5fa45090638'
const publicId = '6817f8fe-6889-456b-95a5-08b7c5489470'
const principal = {
  id: 'owner-a',
  email: 'viewer@example.com',
  display_name: 'Discovery Citizen',
  role: 'CITIZEN',
  provider: 'local',
  is_active: true,
  is_verified: true,
  is_authenticated: true,
}
const stored = {
  complaintId: id,
  citizenId: 'owner-a',
  title: 'Pothole beside the town library',
  description: 'A damaged road surface needs inspection near the library.',
  category: 'POTHOLE',
  reportedSeverity: 'HIGH',
  latitude: 12.972,
  longitude: 77.595,
  landmark: 'Library gate',
  addressLabel: 'Library Road',
  status: 'SUBMITTED',
  incidentId: null,
  createdAt: '2026-10-19T10:00:00.000Z',
  updatedAt: '2026-10-19T10:00:00.000Z',
  images: [],
  publication: {
    citizenRequestedPublication: false,
    publicationStatus: 'PRIVATE',
    publicIssueId: null,
  },
}
const publicIssue: PublicIssue = {
  publicIssueId: publicId,
  category: 'POTHOLE',
  status: 'SUBMITTED',
  summary: 'Reviewed road surface damage at the community junction',
  latitude: 12.972,
  longitude: 77.595,
  publishedAt: '2026-10-19T11:00:00.000Z',
}
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const nearbyPublic: NearbyIssue = {
  issueId: publicId,
  title: publicIssue.summary,
  category: publicIssue.category,
  status: publicIssue.status,
  latitude: publicIssue.latitude,
  longitude: publicIssue.longitude,
  distanceMeters: 345.6,
  createdAt: publicIssue.publishedAt,
  dateLabel: 'Published',
  isOwn: false,
  isPublic: true,
  detailsUrl: '/issues/' + publicId,
}
async function chooseLatest() {
  fireEvent.click(await screen.findByRole('button', { name: 'Search near my latest complaint' }))
}
function setup(
  path: string,
  handler?: (url: string, init?: RequestInit) => Response | Promise<Response> | undefined,
  role = 'CITIZEN',
) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const handled = handler?.(url, init)
    if (handled) return handled
    if (url.endsWith('/auth/me')) return json({ ...principal, role })
    if (url.includes('/portal/')) return json({ message: 'Allowed' })
    if (url.includes('/complaints/summary'))
      return json({
        total: 2,
        counts: { SUBMITTED: 2 },
        recent: [stored],
        byCategory: [{ category: 'POTHOLE', count: 2 }],
        submissionTrend: [{ date: '2026-10-19', count: 2 }],
      })
    if (url.includes('/complaints?')) return json({ items: [stored], nextCursor: null, total: 1 })
    if (url.endsWith('/complaints/' + id)) return json(stored)
    if (url.endsWith('/citizen/issues/latest-location'))
      return json({ location: { latitude: 12.972, longitude: 77.595 } })
    if (url.includes('/citizen/issues/nearby?'))
      return json({ items: [nearbyPublic], nextCursor: null })
    if (url.includes('/public/issues?') || url.includes('/public/issues/nearby?'))
      return json({ items: [publicIssue], nextCursor: null })
    if (url.endsWith('/public/issues/' + publicId)) return json(publicIssue)
    return json({ detail: 'Not found' }, 404)
  })
  vi.stubGlobal('fetch', fetch)
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
  return fetch
}
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Phase 5 server search controls', () => {
  it('debounces text, sends a full-history query and keeps URL filters', async () => {
    const fetch = setup('/citizen/complaints?category=POTHOLE&severity=HIGH')
    await screen.findByRole('heading', { name: stored.title })
    expect(screen.getByLabelText('Category')).toHaveValue('POTHOLE')
    expect(screen.getByLabelText('Reported severity')).toHaveValue('HIGH')
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'lib' } })
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'library' } })
    expect(fetch.mock.calls.some(([url]) => url.includes('q=lib'))).toBe(false)
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url]) =>
            url.includes('q=library') &&
            url.includes('category=POTHOLE') &&
            url.includes('reportedSeverity=HIGH'),
        ),
      ).toBe(true),
    )
    expect(fetch.mock.calls.some(([url]) => url.includes('q=lib&'))).toBe(false)
  })
  it.each([
    ['Category', 'DRAINAGE', 'category=DRAINAGE'],
    ['Status', 'RESOLVED', 'status=RESOLVED'],
    ['Reported severity', 'LOW', 'reportedSeverity=LOW'],
    ['Submitted from', '2026-10-01', 'dateFrom=2026-10-01'],
    ['Submitted through', '2026-10-19', 'dateTo=2026-10-19'],
    ['Sort by', 'oldest', 'sortOrder=asc'],
    ['Sort by', 'category', 'sortBy=category'],
    ['Sort by', 'status', 'sortBy=status'],
  ])('sends %s filtering to the backend', async (label, value, query) => {
    const fetch = setup('/citizen/complaints')
    await screen.findByRole('heading', { name: stored.title })
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.includes(query))).toBe(true))
  })
  it('preserves filters on pagination and resets cursor after filter changes', async () => {
    const fetch = setup('/citizen/complaints?category=POTHOLE', (url) =>
      url.includes('/complaints?')
        ? json({
            items: [stored],
            total: 22,
            nextCursor: url.includes('cursor=') ? null : 'context-key',
          })
        : undefined,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Load more complaints' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url]) => url.includes('cursor=context-key') && url.includes('category=POTHOLE'),
        ),
      ).toBe(true),
    )
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'SUBMITTED' } })
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter(([url]) => url.includes('status=SUBMITTED')).at(-1)?.[0],
      ).not.toContain('cursor='),
    )
  })
  it('resets all filters to the full owner history', async () => {
    const fetch = setup(
      '/citizen/complaints?category=POTHOLE&status=SUBMITTED&severity=HIGH&dateFrom=2026-10-01&sort=oldest',
    )
    await screen.findByRole('heading', { name: stored.title })
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByLabelText('Category')).toHaveValue('')
    expect(screen.getByLabelText('Submitted from')).toHaveValue('')
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter(([url]) => url.includes('/complaints?')).at(-1)?.[0],
      ).not.toContain('category='),
    )
  })
  it('ignores an older search response that resolves after the newest one', async () => {
    let resolveOld: ((value: Response) => void) | undefined
    const fetch = setup('/citizen/complaints', (url) =>
      url.includes('q=old')
        ? new Promise<Response>((resolve) => {
            resolveOld = resolve
          })
        : url.includes('q=new')
          ? json({ items: [], total: 0, nextCursor: null })
          : undefined,
    )
    await screen.findByRole('heading', { name: stored.title })
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'old' } })
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.includes('q=old'))).toBe(true))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'new' } })
    await screen.findByRole('heading', { name: 'No matching complaints' })
    resolveOld?.(json({ items: [stored], total: 1, nextCursor: null }))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: stored.title })).not.toBeInTheDocument(),
    )
  })
})

describe('Real personal analytics', () => {
  it('renders four core metrics and retains accurate accessible analytics on demand', async () => {
    setup('/citizen/dashboard')
    expect(await screen.findByText(/Welcome back, Discovery Citizen/)).toBeInTheDocument()
    await screen.findByRole('region', { name: 'Account complaint statistics' })
    expect(
      within(screen.getByRole('region', { name: 'Account complaint statistics' })).getByText(
        'Total complaints',
      ),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByText('Your reporting insights'))
    expect(
      await screen.findByRole('img', { name: 'Complaints by category: Pothole 2' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('img', { name: /Complaints by status: Submitted 2/ }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('img', { name: 'Submission trend (UTC days): 2026-10-19 2' }),
    ).toBeInTheDocument()
  })
  it('requests the selected trend period and supports refresh', async () => {
    const fetch = setup('/citizen/dashboard')
    fireEvent.click(await screen.findByText('Your reporting insights'))
    await screen.findByLabelText('Submission trend period')
    fireEvent.change(screen.getByLabelText('Submission trend period'), { target: { value: '7' } })
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.endsWith('/summary?days=7'))).toBe(true),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Refresh dashboard' }))
    await waitFor(() =>
      expect(fetch.mock.calls.filter(([url]) => url.endsWith('/summary?days=7')).length).toBe(2),
    )
  })
})

describe('Public discovery and publication', () => {
  it('renders owner-private reports in the same map/list dataset with safe owner links', async () => {
    const mine: NearbyIssue = {
      ...nearbyPublic,
      issueId: id,
      title: stored.title,
      isOwn: true,
      isPublic: false,
      dateLabel: 'Reported',
      detailsUrl: '/citizen/complaints/' + id,
    }
    setup('/citizen/nearby', (url) =>
      url.includes('/citizen/issues/nearby?')
        ? json({ items: [mine, nearbyPublic], nextCursor: null })
        : undefined,
    )
    await chooseLatest()
    await screen.findByRole('heading', { name: stored.title })
    expect(screen.getByRole('link', { name: stored.title })).toHaveAttribute(
      'href',
      '/citizen/complaints/' + id,
    )
    expect(screen.getByText('My Report · Not Publicly Visible')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View complaint details' })).toHaveAttribute(
      'href',
      '/citizen/complaints/' + id,
    )
    expect(screen.getByText(/2 visible reports loaded/)).toBeInTheDocument()
    expect(screen.getByText('Radius circle: 10000 metres')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'List view' }))
    expect(screen.queryByRole('link', { name: stored.title })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: stored.title })).toBeInTheDocument()
  })
  it('supports presets through 200km, slider changes, and preserves center when clearing filters', async () => {
    const fetch = setup('/citizen/nearby')
    await chooseLatest()
    await screen.findByRole('heading', { name: nearbyPublic.title })
    expect(screen.getByRole('slider')).toHaveAttribute('max', '200')
    fireEvent.click(screen.getByRole('button', { name: '200 km' }))
    await waitFor(() =>
      expect(screen.getByText('Radius circle: 200000 metres')).toBeInTheDocument(),
    )
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.includes('radiusKm=200'))).toBe(true),
    )
    fireEvent.change(screen.getByRole('slider'), { target: { value: '25' } })
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.includes('radiusKm=25'))).toBe(true),
    )
    fireEvent.change(screen.getByLabelText('Map category'), { target: { value: 'GARBAGE' } })
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.includes('category=GARBAGE'))).toBe(true),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Clear Filters' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter(([url]) => url.includes('/issues/nearby?')).at(-1)?.[0],
      ).not.toContain('category='),
    )
    expect(screen.getByRole('slider')).toHaveValue('25')
    expect(screen.getByLabelText('Map latitude')).toHaveValue('12.972000')
  })
  it('paginates, de-duplicates repeated results and resets pages after a new search', async () => {
    const second = {
      ...nearbyPublic,
      issueId: 'public-second',
      title: 'Another reviewed issue',
      detailsUrl: '/issues/public-second',
    }
    const fetch = setup('/citizen/nearby', (url) =>
      url.includes('/citizen/issues/nearby?')
        ? json({
            items: url.includes('cursor=') ? [nearbyPublic, second] : [nearbyPublic],
            nextCursor: url.includes('cursor=') ? null : 'next-page',
          })
        : undefined,
    )
    await chooseLatest()
    fireEvent.click(await screen.findByRole('button', { name: 'Load more nearby issues' }))
    await screen.findByRole('heading', { name: second.title })
    expect(screen.getAllByRole('heading', { name: nearbyPublic.title })).toHaveLength(1)
    expect(
      fetch.mock.calls.some(
        ([url]) => url.includes('cursor=next-page') && url.includes('radiusKm=10'),
      ),
    ).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Move map' }))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: second.title })).not.toBeInTheDocument(),
    )
    await screen.findByRole('heading', { name: nearbyPublic.title })
  })
  it('retries a failed search without showing a false empty state', async () => {
    let requests = 0
    setup('/citizen/nearby', (url) =>
      url.includes('/citizen/issues/nearby?')
        ? ++requests === 1
          ? json({ detail: 'Discovery temporarily unavailable' }, 503)
          : json({ items: [nearbyPublic], nextCursor: null })
        : undefined,
    )
    await chooseLatest()
    await screen.findByText('Unable to load nearby issues. Please try again.')
    expect(
      screen.queryByText('No visible issues were found within the selected radius.'),
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry connection' }))
    await screen.findByRole('heading', { name: nearbyPublic.title })
  })
  it('does not invent coordinates when the latest eligible complaint is absent', async () => {
    const fetch = setup('/citizen/nearby', (url) =>
      url.endsWith('/latest-location') ? json({ location: null }) : undefined,
    )
    await chooseLatest()
    await screen.findByText(/No eligible complaint location was found/)
    expect(screen.getByLabelText('Map latitude')).toHaveValue('')
    expect(fetch.mock.calls.some(([url]) => url.includes('/issues/nearby?'))).toBe(false)
    fireEvent.change(screen.getByLabelText('Map latitude'), { target: { value: '91' } })
    fireEvent.click(screen.getByRole('button', { name: 'Set map center' }))
    await screen.findByText(/Enter valid coordinates/)
    expect(fetch.mock.calls.some(([url]) => url.includes('/issues/nearby?'))).toBe(false)
  })
  it('removes stale markers while a different center search is in flight', async () => {
    let requests = 0
    setup('/citizen/nearby', (url) => {
      if (!url.includes('/citizen/issues/nearby?')) return undefined
      requests++
      return requests === 1
        ? json({ items: [nearbyPublic], nextCursor: null })
        : new Promise<Response>(() => {})
    })
    await chooseLatest()
    await screen.findByRole('link', { name: publicIssue.summary })
    fireEvent.click(screen.getByRole('button', { name: 'Move map' }))
    await waitFor(() => expect(requests).toBe(2))
    expect(screen.queryByRole('link', { name: publicIssue.summary })).not.toBeInTheDocument()
  })
  it('requires a selected center and requests bounded authenticated discovery with safe public links', async () => {
    const fetch = setup('/citizen/nearby')
    await screen.findByRole('heading', {
      name: 'Select a location to find nearby infrastructure issues.',
    })
    expect(fetch.mock.calls.some(([url]) => url.includes('/issues/nearby?'))).toBe(false)
    await chooseLatest()
    expect(await screen.findByRole('link', { name: publicIssue.summary })).toHaveAttribute(
      'href',
      '/issues/' + publicId,
    )
    expect(
      fetch.mock.calls.some(
        ([url]) =>
          url.includes('/citizen/issues/nearby?') &&
          url.includes('radiusKm=10') &&
          url.includes('latitude=12.972'),
      ),
    ).toBe(true)
    expect(fetch.mock.calls.some(([url]) => url.includes('/complaints?'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Move map' }))
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.includes('latitude=12.96'))).toBe(true),
    )
  })
  it('combines map filters and radius and shows distances in list view', async () => {
    const fetch = setup('/citizen/nearby', (url) =>
      url.includes('/issues/nearby?')
        ? json({ items: [nearbyPublic], nextCursor: null })
        : undefined,
    )
    await chooseLatest()
    await screen.findByRole('link', { name: publicIssue.summary })
    fireEvent.change(screen.getByLabelText('Map category'), { target: { value: 'POTHOLE' } })
    fireEvent.change(screen.getByLabelText('Map status'), { target: { value: 'SUBMITTED' } })
    fireEvent.change(screen.getByRole('slider'), { target: { value: '200' } })
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url]) =>
            url.includes('/issues/nearby?') &&
            url.includes('radiusKm=200') &&
            url.includes('category=POTHOLE') &&
            url.includes('status=SUBMITTED'),
        ),
      ).toBe(true),
    )
    fireEvent.click(screen.getByRole('button', { name: 'List view' }))
    expect(await screen.findByText(/0.35 km from search center/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View public issue' })).toHaveAttribute(
      'href',
      '/issues/' + publicId,
    )
  })
  it('shows empty public results without substituting private complaints or samples', async () => {
    setup('/citizen/nearby', (url) =>
      url.includes('/citizen/issues/nearby?') ? json({ items: [], nextCursor: null }) : undefined,
    )
    await chooseLatest()
    await screen.findByRole('heading', {
      name: 'No visible issues were found within the selected radius.',
    })
    expect(screen.queryByText(stored.title)).not.toBeInTheDocument()
    expect(screen.queryByText('Simulated complaint')).not.toBeInTheDocument()
  })
  it('shows public API failures and does not fabricate markers', async () => {
    setup('/citizen/nearby', (url) =>
      url.includes('/citizen/issues/nearby?')
        ? json({ detail: 'Map area is too large. Zoom in.' }, 422)
        : undefined,
    )
    await chooseLatest()
    expect(await screen.findByText('Map area is too large. Zoom in.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: publicIssue.summary })).not.toBeInTheDocument()
  })
  it('handles a malformed successful public response without a rendering crash', async () => {
    setup('/citizen/nearby', (url) =>
      url.includes('/citizen/issues/nearby?') ? json({ message: 'not a nearby page' }) : undefined,
    )
    await chooseLatest()
    expect(
      await screen.findByText('The nearby issue API returned an invalid page. Please retry.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: publicIssue.summary })).not.toBeInTheDocument()
  })
  it('renders public details without private photo or complaint endpoints', async () => {
    const fetch = setup('/issues/' + publicId)
    await screen.findByRole('heading', { name: publicIssue.summary })
    expect(screen.queryByText(stored.description)).not.toBeInTheDocument()
    expect(screen.queryByText('Photo evidence')).not.toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => url.includes('/complaints/'))).toBe(false)
  })
  it('handles withdrawn or unknown public details safely', async () => {
    setup('/issues/' + publicId, (url) =>
      url.endsWith('/issues/' + publicId)
        ? json({ detail: 'Public issue not found.' }, 404)
        : undefined,
    )
    expect(await screen.findByText('Public issue not found.')).toBeInTheDocument()
  })
  it('requests and withdraws publication using the owner endpoint', async () => {
    const fetch = setup('/citizen/complaints/' + id, (url, init) =>
      url.endsWith('/publication-request')
        ? json({
            citizenRequestedPublication: JSON.parse(String(init?.body)).requested,
            publicationStatus: JSON.parse(String(init?.body)).requested
              ? 'PENDING_REVIEW'
              : 'PRIVATE',
            publicIssueId: null,
          })
        : undefined,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Request public map publication' }))
    await screen.findByText('Publication status: PENDING REVIEW')
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw publication request' }))
    await screen.findByText('Publication status: PRIVATE')
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/publication-request'))).toHaveLength(2)
    expect(fetch.mock.calls.some(([url]) => url.includes('/admin/'))).toBe(false)
  })
  it('handles publication session expiry through the existing login guard', async () => {
    setup('/citizen/complaints/' + id, (url) =>
      url.endsWith('/publication-request') ? json({ detail: 'Session expired.' }, 401) : undefined,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Request public map publication' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
  it('restricts review UI to administrators', async () => {
    setup('/admin/publication-review')
    expect(
      await screen.findByRole('heading', { name: /not authorized|Access denied|Unauthorized/i }),
    ).toBeInTheDocument()
  })
  it('sends explicit privacy-reviewed approval through the administrator API', async () => {
    const fetch = setup(
      '/admin/publication-review',
      (url) =>
        url.endsWith('/publication')
          ? json({
              publicationStatus: 'PUBLISHED',
              citizenRequestedPublication: true,
              publicIssueId: publicId,
            })
          : undefined,
      'ADMIN',
    )
    await screen.findByLabelText('Complaint ID')
    for (const [label, value] of [
      ['Complaint ID', id],
      ['Reviewed public summary', publicIssue.summary],
      ['Public latitude', '12.972'],
      ['Public longitude', '77.595'],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } })
    fireEvent.click(screen.getByRole('checkbox', { name: /I reviewed/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save audited decision' }))
    await screen.findByText('Audited publication decision saved: PUBLISHED')
    const call = fetch.mock.calls.find(([url]) => url.endsWith('/publication'))!
    expect(JSON.parse(String(call[1]?.body))).toMatchObject({
      decision: 'APPROVE',
      reviewedForPrivacy: true,
      publicLatitude: 12.972,
    })
  })
  it('encodes public queries centrally without hardcoded cloud URLs', async () => {
    const fetch = vi.fn<(url: string) => Promise<Response>>(async () =>
      json({ items: [], nextCursor: null }),
    )
    vi.stubGlobal('fetch', fetch)
    await discoveryService.bounds(
      { minLatitude: 0, maxLatitude: 0.1, minLongitude: 179.9, maxLongitude: -179.9 },
      { cursor: 'opaque+a&b', category: 'POTHOLE' },
    )
    expect(fetch.mock.calls[0]?.[0]).toContain('cursor=opaque%2Ba%26b')
  })
})
