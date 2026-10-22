import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { CandidateDetail } from '../services/duplicateService'

const id = '706d4e75-2753-48e1-bf8b-a5fa45090638'
const source = '6817f8fe-6889-456b-95a5-08b7c5489470'
const duplicate = '5535f1d7-7258-48cc-8f04-de50baac1111'
const detail: CandidateDetail = {
  candidateId: id,
  sourceComplaintId: source,
  possibleDuplicateId: duplicate,
  sourceTitle: 'Large pothole at school',
  duplicateTitle: 'Road hole near school',
  sourceCategory: 'POTHOLE',
  duplicateCategory: 'POTHOLE',
  combinedScore: 0.86,
  geographicScore: 0.95,
  textScore: 0.77,
  imageScore: null,
  distanceMeters: 2.5,
  effectiveWeights: { geographic: 0.5, text: 0.5, image: 0 },
  categoryCompatibility: 'SAME_CATEGORY',
  classification: 'STRONG_CANDIDATE',
  reviewStatus: 'PENDING_REVIEW',
  explanation: ['Compatible category and close location'],
  indicators: ['Missing image evidence'],
  method: 'haversine+tfidf+dhash',
  modelVersion: 'tfidf-v1',
  configVersion: 'matching-v1',
  updatedAt: '2026-10-20T10:00:00Z',
  lastCheckedAt: '2026-10-20T10:00:00Z',
  reviewedAt: null,
  complaints: [source, duplicate].map((complaintId, index) => ({
    complaintId,
    title: index ? 'Road hole near school' : 'Large pothole at school',
    description: 'Private road surface description with enough evidence for review.',
    category: 'POTHOLE',
    latitude: 12.97,
    longitude: 77.59,
    status: 'SUBMITTED',
    createdAt: '2026-10-20T10:00:00Z',
    incidentId: null,
    images: [],
  })),
  processing: [
    { state: 'COMPLETE' },
    { state: 'INCOMPLETE', report: { incomplete: true, queryTruncated: true, compared: 1 } },
  ],
}
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
function setup(
  path = '/admin/duplicate-candidates',
  handler?: (url: string, init?: RequestInit) => Response | Promise<Response> | undefined,
  role = 'ADMIN',
) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me'))
      return json({
        id: 'admin-test',
        email: 'admin@example.com',
        display_name: 'Admin',
        role,
        provider: 'local',
        is_active: true,
        is_verified: true,
        is_authenticated: true,
      })
    const result = handler?.(url, init)
    if (result) return result
    if (url.includes('/duplicate-candidates?')) return json({ items: [detail], nextCursor: null })
    if (url.endsWith('/duplicate-check')) return json({ processing: { state: 'COMPLETE' } })
    if (url.endsWith('/dismiss') || url.endsWith('/reviewed')) return json(detail)
    if (url.endsWith('/duplicate-candidates/' + id)) return json(detail)
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

describe('Administrator duplicate review', () => {
  it('renders scores categories distance missing images and classification without merge controls', async () => {
    setup()
    await screen.findByText('86.0/100')
    expect(screen.getByText('77.0/100')).toBeInTheDocument()
    expect(screen.getByText('2.50 m')).toBeInTheDocument()
    expect(screen.getByText('Unavailable — not zero')).toBeInTheDocument()
    expect(screen.getByText('STRONG_CANDIDATE', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('Pothole / Pothole')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /merge|priority/i })).not.toBeInTheDocument()
  })
  it.each([
    ['Review status', 'DISMISSED', 'reviewStatus=DISMISSED'],
    ['Sort', 'date', 'sort=date'],
    ['Classification', 'REVIEW_REQUIRED', 'classification=REVIEW_REQUIRED'],
    ['Category', 'DRAINAGE', 'category=DRAINAGE'],
  ])('sends %s filter to server', async (label, value, query) => {
    const fetch = setup()
    await screen.findByText('86.0/100')
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => url.includes(query))).toBe(true))
  })
  it('shows loading and an honest empty state', async () => {
    let complete: ((value: Response) => void) | undefined
    setup('/admin/duplicate-candidates', (url) =>
      url.includes('/duplicate-candidates?')
        ? new Promise<Response>((resolve) => {
            complete = resolve
          })
        : undefined,
    )
    await screen.findByLabelText('Loading content')
    // The route chunk can show the shared loader before its API request has started.
    await waitFor(() => expect(complete).toBeTypeOf('function'))
    complete?.(json({ items: [], nextCursor: null }))
    await screen.findByText('No duplicate candidates')
    expect(screen.getByText(/does not prove there are no duplicates/)).toBeInTheDocument()
  })
  it('shows API errors and retry', async () => {
    const fetch = setup('/admin/duplicate-candidates', (url) =>
      url.includes('/duplicate-candidates?')
        ? json({ detail: 'Matching unavailable' }, 503)
        : undefined,
    )
    await screen.findByText('Matching unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter(([url]) => url.includes('/duplicate-candidates?')).length,
      ).toBe(2),
    )
  })
  it('opens side-by-side private details with explanations method version and incomplete warning', async () => {
    setup('/admin/duplicate-candidates/' + id)
    await screen.findByRole('heading', { name: 'Large pothole at school' })
    expect(screen.getByRole('heading', { name: 'Road hole near school' })).toBeInTheDocument()
    expect(screen.getByText('Compatible category and close location')).toBeInTheDocument()
    expect(screen.getByText(/Method: haversine/)).toBeInTheDocument()
    expect(screen.getByText(/Matching is pending, failed or incomplete/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Back to candidates/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^merge/i })).not.toBeInTheDocument()
  })
  it.each([
    ['Dismiss candidate', '/dismiss'],
    ['Mark reviewed possible duplicate', '/reviewed'],
    ['Rerun matching', '/duplicate-check'],
  ])('persists %s and refreshes the detail', async (name, path) => {
    const fetch = setup('/admin/duplicate-candidates/' + id)
    fireEvent.click(await screen.findByRole('button', { name }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([url, init]) => url.endsWith(path) && init?.method === 'POST'),
      ).toBe(true),
    )
    await waitFor(() =>
      expect(
        fetch.mock.calls.filter(([url]) => url.endsWith('/duplicate-candidates/' + id)).length,
      ).toBe(2),
    )
  })
  it('shows action errors without fabricating a success', async () => {
    setup('/admin/duplicate-candidates/' + id, (url) =>
      url.endsWith('/dismiss') ? json({ detail: 'Review unavailable' }, 503) : undefined,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss candidate' }))
    await screen.findByText('Review unavailable')
    expect(screen.queryByText(/Review decision saved/)).not.toBeInTheDocument()
  })
  it.each(['CITIZEN', 'OFFICER'])('does not fetch private matching data as %s', async (role) => {
    const fetch = setup('/admin/duplicate-candidates', undefined, role)
    await screen.findByRole('heading', { name: /Access denied/ })
    expect(fetch.mock.calls.some(([url]) => url.includes('/duplicate-candidates'))).toBe(false)
  })
  it('submits bounded recheck from the empty list', async () => {
    const fetch = setup('/admin/duplicate-candidates', (url) =>
      url.includes('/duplicate-candidates?') ? json({ items: [], nextCursor: null }) : undefined,
    )
    await screen.findByText('No duplicate candidates')
    fireEvent.change(screen.getByLabelText('Complaint ID to recheck'), {
      target: { value: source },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Recheck complaint' }))
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.includes(source + '/duplicate-check'))).toBe(
        true,
      ),
    )
  })
})
