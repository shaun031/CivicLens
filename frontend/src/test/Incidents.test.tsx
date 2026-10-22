import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { IncidentCorrectionDialog } from '../components/incidents/IncidentCorrectionDialog'
import { CitizenIncidentSummary } from '../components/incidents/CitizenIncidentSummary'
import type { Incident } from '../services/incidentService'

vi.mock('../components/incidents/IncidentMap', () => ({ default: () => <div>Private map</div> }))
const source: Incident = {
  incidentId: '57f70de9-5157-46c5-af40-0b4698e07241',
  canonicalTitle: 'School entrance pothole',
  canonicalDescription: 'Private canonical narrative',
  category: 'POTHOLE',
  latitude: 12.97,
  longitude: 77.59,
  status: 'OPEN',
  representativeComplaintId: '2e9cd1e7-f0d8-4a34-bfbd-d01329fa66f4',
  totalComplaintCount: 1,
  uniqueReporterCount: 1,
  version: 3,
  firstReportedAt: '2026-10-20T10:00:00Z',
  lastReportedAt: '2026-10-20T10:00:00Z',
  createdAt: '2026-10-20T10:00:00Z',
  updatedAt: '2026-10-20T10:00:00Z',
}
const target = { ...source, incidentId: '850aff40-7254-4e4c-b8c9-9e4033a35a02', version: 5 }
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
function fillConfirmation() {
  fireEvent.change(screen.getByLabelText('Written correction reason'), {
    target: { value: 'Reviewed both physical reports and correcting membership' },
  })
  fireEvent.click(screen.getByLabelText(/I confirm this membership/))
}

describe('Incident correction safeguards', () => {
  it('requires a loaded target and sends both versions, physical confirmation and reason', async () => {
    const fetch = vi.fn(async (_url: string, init?: RequestInit) =>
      json(init?.method === 'POST' ? target : target),
    )
    vi.stubGlobal('fetch', fetch)
    const saved = vi.fn()
    render(
      <IncidentCorrectionDialog kind="merge" source={source} onClose={vi.fn()} onSaved={saved} />,
    )
    expect(screen.getByRole('button', { name: 'Apply confirmed operation' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Target incident ID'), {
      target: { value: target.incidentId },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Load target for confirmation' }))
    await screen.findByText(/Target: School entrance pothole/)
    fillConfirmation()
    fireEvent.click(screen.getByLabelText(/I reviewed the locations/))
    fireEvent.click(screen.getByRole('button', { name: 'Apply confirmed operation' }))
    await waitFor(() => expect(saved).toHaveBeenCalledWith(target))
    const request = JSON.parse(
      fetch.mock.calls.find(([, init]) => init?.method === 'POST')![1]!.body as string,
    )
    expect(request).toMatchObject({
      sourceIncidentId: source.incidentId,
      expectedSourceVersion: 3,
      targetIncidentId: target.incidentId,
      expectedTargetVersion: 5,
      confirmed: true,
      physicalIssueConfirmed: true,
    })
    expect(request.operationId).toMatch(/^[0-9a-f-]{36}$/)
  })
  it('freezes a failed request for identical idempotent retry and explains stale versions', async () => {
    const fetch = vi.fn(async () => json({ detail: 'Version conflict. Refresh first.' }, 409))
    vi.stubGlobal('fetch', fetch)
    render(
      <IncidentCorrectionDialog
        kind="split"
        source={source}
        selected={[source.representativeComplaintId]}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    fillConfirmation()
    fireEvent.click(screen.getByRole('button', { name: 'Apply confirmed operation' }))
    await screen.findByText('Version conflict. Refresh first.')
    expect(screen.getByLabelText('Written correction reason')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry identical operation' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(fetch.mock.calls[0]).toEqual(fetch.mock.calls[1])
    expect(screen.getByText(/For a 409\/version conflict/)).toBeVisible()
  })
  it('invalidates the reviewed target snapshot when the target ID changes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(target)),
    )
    render(
      <IncidentCorrectionDialog kind="merge" source={source} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    fireEvent.change(screen.getByLabelText('Target incident ID'), {
      target: { value: target.incidentId },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Load target for confirmation' }))
    await screen.findByText(/Target: School entrance pothole/)
    fireEvent.change(screen.getByLabelText('Target incident ID'), {
      target: { value: source.incidentId },
    })
    expect(screen.queryByText(/Target: School entrance pothole/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply confirmed operation' })).toBeDisabled()
  })
})

describe('Incident privacy and navigation', () => {
  it.each(['CITIZEN', 'OFFICER'])(
    'denies %s the admin catalog before requesting private data',
    async (role) => {
      const fetch = vi.fn(async (...args: [string]) =>
        json({
          id: args[0] ? 'user' : 'anonymous',
          email: 'user@example.com',
          display_name: 'User',
          role,
          provider: 'local',
          is_active: true,
          is_verified: true,
          is_authenticated: true,
        }),
      )
      vi.stubGlobal('fetch', fetch)
      render(
        <MemoryRouter initialEntries={['/admin/incidents']}>
          <App />
        </MemoryRouter>,
      )
      await screen.findByRole('heading', { name: /access denied/i })
      expect(
        fetch.mock.calls.every(([url]) =>
          /\/auth\/me$|\/notifications\/unread-count$/.test(String(url)),
        ),
      ).toBe(true)
    },
  )
  it('lists private counts and sends search, category and sort filters', async () => {
    const fetch = vi.fn(async (url: string) => {
      if (url.endsWith('/auth/me'))
        return json({
          id: 'admin',
          display_name: 'Admin',
          role: 'ADMIN',
          email: 'admin@example.com',
          provider: 'local',
          is_active: true,
          is_verified: true,
          is_authenticated: true,
        })
      if (url.endsWith('/summary')) return json({ activeIncidents: 1, linkedComplaints: 1 })
      return json({ items: [source], nextCursor: null })
    })
    vi.stubGlobal('fetch', fetch)
    render(
      <MemoryRouter initialEntries={['/admin/incidents']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByText('School entrance pothole')
    expect(screen.getByText(/1 linked complaints/)).toBeVisible()
    fireEvent.change(screen.getByLabelText('Search incidents'), { target: { value: 'school' } })
    fireEvent.change(screen.getByLabelText('Incident category'), { target: { value: 'POTHOLE' } })
    fireEvent.change(screen.getByLabelText('Incident sort'), { target: { value: 'oldest' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply incident filters' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url]) =>
            url.includes('q=school') &&
            url.includes('category=POTHOLE') &&
            url.includes('sort=oldest'),
        ),
      ).toBe(true),
    )
  })
  it('uses only the owner-safe summary and never renders membership counts', async () => {
    const fetch = vi.fn(async (...args: [string]) =>
      json({
        incidentId: args[0] ? source.incidentId : null,
        category: 'POTHOLE',
        status: 'OPEN',
        processing: 'COMPLETE',
      }),
    )
    vi.stubGlobal('fetch', fetch)
    render(<CitizenIncidentSummary complaintId={source.representativeComplaintId} />)
    await screen.findByText(source.incidentId, { exact: false })
    expect(fetch.mock.calls[0][0]).toContain(
      `/complaints/${source.representativeComplaintId}/incident`,
    )
    expect(
      screen.queryByText(/unique reporters|canonical narrative|linked complaints/),
    ).not.toBeInTheDocument()
  })
})
