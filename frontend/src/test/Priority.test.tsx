import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import {
  PriorityBreakdown,
  PriorityEditor,
  PriorityPanel,
} from '../components/incidents/PriorityPanel'
import type { PriorityResult, PriorityState } from '../services/priorityService'

const id = '75b045ae-7c29-40c2-b2bd-806e4b6cc248'
const priority: PriorityResult = {
  incidentId: id,
  incidentVersion: 2,
  calculatedScore: 55.07,
  calculatedBand: 'MEDIUM',
  effectiveScore: 100,
  priorityBand: 'CRITICAL',
  assessmentStatus: 'NEEDS_REVIEW',
  urgentHazard: true,
  hazardStatus: 'VERIFIED',
  overrideStatus: 'NONE',
  unresolvedSeconds: 15 * 86400,
  unresolvedDays: 15,
  factors: {
    severity: {
      rawValue: 8,
      normalizedValue: 8,
      weight: 0.4,
      contribution: 32,
      status: 'VERIFIED',
    },
    publicImpact: {
      rawValue: null,
      normalizedValue: 3,
      weight: 0.25,
      contribution: 7.5,
      status: 'PROVISIONAL',
    },
    reporters: {
      rawValue: 3,
      normalizedValue: 4.037,
      weight: 0.2,
      contribution: 8.07,
      status: 'ELIGIBLE_ACCOUNTS',
    },
    aging: {
      rawValue: 15,
      normalizedValue: 5,
      weight: 0.15,
      contribution: 7.5,
      status: 'APPROXIMATE_BASELINE',
    },
  },
  explanation: ['Prototype rubric, not accident probability.'],
  reviewFlags: ['Public impact needs assessment'],
  calculatedAt: '2026-10-20T10:00:00Z',
  algorithmVersion: 'priority-v1-test',
}
const state: PriorityState = {
  incident: {
    incidentId: id,
    canonicalTitle: 'School entrance pothole',
    canonicalDescription: 'Private narrative',
    category: 'POTHOLE',
    latitude: 12.97,
    longitude: 77.59,
    status: 'OPEN',
    representativeComplaintId: id,
    totalComplaintCount: 3,
    uniqueReporterCount: 3,
    version: 2,
    firstReportedAt: '2026-10-01T00:00:00Z',
    lastReportedAt: '2026-10-20T00:00:00Z',
    createdAt: '2026-10-01T00:00:00Z',
    updatedAt: '2026-10-20T00:00:00Z',
  },
  priority,
  priorityRevision: 4,
  incidentVersion: 2,
  membershipEpoch: 1,
  controls: {},
  stale: false,
  staleReasons: [],
  evidenceOptions: [{ id, label: 'Original report evidence' }],
  currentConfigVersion: 'priority-v1-test',
}
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
function confirm() {
  fireEvent.change(screen.getByLabelText('Priority assessment or correction reason'), {
    target: { value: 'Administrator inspected and recorded the physical evidence' },
  })
  fireEvent.click(screen.getByLabelText(/I confirm this assessed change/))
}
describe('Explainable priority UI', () => {
  it('separates calculated/effective scores, unknown inputs, status and hazard', () => {
    render(<PriorityBreakdown priority={priority} />)
    expect(screen.getByText('55.07/100 · MEDIUM')).toBeVisible()
    expect(screen.getByText('100/100 · CRITICAL')).toBeVisible()
    expect(screen.getByText('VERIFIED URGENT HAZARD')).toBeVisible()
    expect(screen.getByRole('progressbar', { name: 'Severity contribution' })).toHaveAttribute(
      'aria-valuenow',
      '32',
    )
    expect(screen.getByText(/Input Unknown/)).toBeVisible()
    expect(screen.getByText(/priority-v1-test/)).toBeVisible()
  })
  it.each(['SEVERITY', 'PUBLIC_IMPACT'] as const)(
    'submits verified %s with reason, evidence and versions',
    async (kind) => {
      const fetch = vi.fn(async (_url: string, init?: RequestInit) =>
        json({ priority, ...(init ? {} : {}) }),
      )
      vi.stubGlobal('fetch', fetch)
      const saved = vi.fn()
      render(<PriorityEditor state={state} kind={kind} onClose={vi.fn()} onSaved={saved} />)
      fireEvent.change(screen.getByLabelText('Assessment score (0–10)'), { target: { value: '8' } })
      fireEvent.click(screen.getByLabelText('Original report evidence'))
      confirm()
      fireEvent.click(screen.getByRole('button', { name: 'Save confirmed priority operation' }))
      await waitFor(() => expect(saved).toHaveBeenCalled())
      const input = JSON.parse(fetch.mock.calls[0][1]!.body as string)
      expect(input).toMatchObject({
        score: 8,
        status: 'VERIFIED',
        evidenceReferences: [id],
        expectedIncidentVersion: 2,
        expectedPriorityRevision: 4,
        confirmed: true,
      })
    },
  )
  it('blocks verification without evidence before making a request', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    render(<PriorityEditor state={state} kind="SEVERITY" onClose={vi.fn()} onSaved={vi.fn()} />)
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Save confirmed priority operation' }))
    await screen.findByText(/Select supporting evidence/)
    expect(fetch).not.toHaveBeenCalled()
  })
  it('creates an override and retries an identical frozen request after a conflict', async () => {
    const fetch = vi.fn(async (url: string, init?: RequestInit) =>
      json({ detail: 'Stale priority revision', path: url, method: init?.method }, 409),
    )
    vi.stubGlobal('fetch', fetch)
    render(<PriorityEditor state={state} kind="OVERRIDE" onClose={vi.fn()} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Override score (0–100)'), { target: { value: '85' } })
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Save confirmed priority operation' }))
    await screen.findByText('Stale priority revision')
    expect(screen.getByLabelText('Priority assessment or correction reason')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry identical priority operation' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(fetch.mock.calls[0]).toEqual(fetch.mock.calls[1])
  })
  it('uses an audited DELETE to remove an override', async () => {
    const fetch = vi.fn(async (_url: string, init?: RequestInit) =>
      json({ priority, method: init?.method }),
    )
    vi.stubGlobal('fetch', fetch)
    const saved = vi.fn()
    render(
      <PriorityEditor state={state} kind="REMOVE_OVERRIDE" onClose={vi.fn()} onSaved={saved} />,
    )
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Save confirmed priority operation' }))
    await waitFor(() => expect(saved).toHaveBeenCalled())
    expect(fetch.mock.calls[0][1]!.method).toBe('DELETE')
  })
  it('shows pending state and preserved history without inventing a score', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        json(
          url.includes('/history')
            ? { items: [], nextCursor: null }
            : {
                ...state,
                priority: null,
                stale: true,
                staleReasons: ['Initial calculation pending'],
              },
        ),
      ),
    )
    render(
      <MemoryRouter>
        <PriorityPanel incidentId={id} />
      </MemoryRouter>,
    )
    await screen.findByText('Priority not calculated')
    expect(screen.getByText(/Initial calculation pending/)).toBeVisible()
    expect(screen.getByText('No priority history yet.')).toBeVisible()
  })
  it.each(['CITIZEN', 'OFFICER'])('denies %s the priority dashboard', async (role) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        json({
          id: 'user',
          email: 'user@example.com',
          display_name: 'User',
          role,
          provider: 'local',
          is_active: true,
          is_verified: true,
          is_authenticated: true,
        }),
      ),
    )
    render(
      <MemoryRouter initialEntries={['/admin/priorities']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: /access denied/i })
    expect(screen.queryByText('School entrance pothole')).not.toBeInTheDocument()
  })
  it('renders real ranked results, filters, counts and cursor pagination', async () => {
    const fetch = vi.fn(async (url: string) => {
      if (url.endsWith('/auth/me'))
        return json({
          id: 'admin',
          email: 'admin@example.com',
          display_name: 'Admin',
          role: 'ADMIN',
          provider: 'local',
          is_active: true,
          is_verified: true,
          is_authenticated: true,
        })
      if (url.endsWith('/summary'))
        return json({
          activeIncidents: 1,
          scoredIncidents: 1,
          pendingOrStale: 0,
          bands: { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 1 },
          needsAssessment: 1,
          urgentHazards: 1,
          overridden: 0,
        })
      return json({ items: [{ incident: state.incident, priority }], nextCursor: 'opaque-page' })
    })
    vi.stubGlobal('fetch', fetch)
    render(
      <MemoryRouter initialEntries={['/admin/priorities']}>
        <App />
      </MemoryRouter>,
    )
    await screen.findByText('School entrance pothole')
    fireEvent.change(screen.getByLabelText('Priority band'), { target: { value: 'CRITICAL' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply priority filters' }))
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.includes('band=CRITICAL'))).toBe(true),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Next priority page' }))
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.includes('cursor=opaque-page'))).toBe(true),
    )
  })
})
