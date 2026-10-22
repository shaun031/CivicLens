import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import {
  AssignmentDetailsPage,
  DepartmentsPage,
  DepartmentDetailsPage,
  OfficerDashboard,
  WorkConfirmation,
  WorkloadCard,
  WorkQueue,
} from '../pages/WorkPages'
import type { DepartmentDetail, Officer, WorkDetail } from '../services/workService'

const id = 'a936a1bb-7e69-4c8b-bd45-d426e0be4329'
const officer: Officer = {
  officerId: id,
  displayName: 'Field Officer',
  departmentId: id,
  active: true,
  eligibleAccount: true,
  availability: 'AVAILABLE',
  capacity: 10,
  areas: [],
  version: 1,
  workload: 3,
  activeIncidents: 2,
  pendingPriorities: 0,
}
const department: DepartmentDetail = {
  id,
  code: 'ROAD_MAINTENANCE',
  name: 'Road Maintenance',
  description: 'Editable demo road responsibility',
  active: true,
  areas: [],
  version: 1,
  officers: [officer],
  rules: [{ id, category: 'POTHOLE', departmentId: id, precedence: 100, active: true, version: 1 }],
  workload: {
    activeIncidents: 2,
    unassignedIncidents: 1,
    weightedWorkload: 4,
    overCapacity: [],
    policy: 'Manual approval; no automatic redistribution.',
  },
}
const state: WorkDetail = {
  incidentId: id,
  title: 'Library road pothole',
  category: 'POTHOLE',
  latitude: 12.97,
  longitude: 77.59,
  incidentVersion: 2,
  incidentStatus: 'OPEN',
  assignment: {
    incidentId: id,
    departmentId: id,
    officerId: null,
    status: 'DEPARTMENT_ASSIGNED',
    method: 'AUTO_DEPARTMENT',
    ruleVersion: 'rules-1',
    explanation: [],
    version: 1,
    percentage: 0,
    assignedAt: null,
    updatedAt: null,
  },
  priorityStale: true,
  priority: null,
  department,
  suggestedRouting: {
    departmentId: id,
    review: false,
    mode: 'CATEGORY_DEMONSTRATION',
    explanation: ['Category determines responsibility'],
    ruleVersion: 'rules-1',
  },
  recommendations: { ranked: [officer], excluded: [], incomingUnits: 4, mode: 'MANUAL_APPROVAL' },
}
const page = {
  items: [state],
  nextCursor: null,
  stats: { assigned: 1, inProgress: 0, high: 0, critical: 0, urgent: 0, pendingPriority: 1 },
  workload: { workload: 3 },
}
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
function mock(overrides: Record<string, unknown> = {}) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method && init.method !== 'GET') return json({ version: 2 })
    if (url in overrides) return json(overrides[url])
    if (url.includes('/assignment-history') || url.includes('/history?'))
      return json({ items: [], nextCursor: null })
    if (url === '/api/admin/departments/summary')
      return json({ totalDepartments: 1, activeDepartments: 1, officers: 1 })
    if (url === '/api/admin/departments') return json({ items: [department] })
    if (url === '/api/admin/officers')
      return json({ items: [{ officerId: id, displayName: 'Field Officer' }], nextAfter: null })
    if (url === `/api/admin/departments/${id}`) return json(department)
    if (url === `/api/admin/incidents/${id}/assignment` || url === `/api/officer/incidents/${id}`)
      return json(state)
    if (url.includes('/incidents?') || url.includes('/assignments?')) return json(page)
    return json({ detail: 'Unmocked route' }, 404)
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}
function confirm() {
  fireEvent.change(screen.getByLabelText('Assignment or progress reason'), {
    target: { value: 'Site review confirms this municipal work decision' },
  })
  fireEvent.click(screen.getByLabelText(/I confirm this municipal work change/))
}
function detail(officer = false) {
  render(
    <MemoryRouter initialEntries={[`/work/${id}`]}>
      <Routes>
        <Route path="/work/:incidentId" element={<AssignmentDetailsPage officer={officer} />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Municipal work administration', () => {
  it('loads real department overview and status', async () => {
    mock()
    render(
      <MemoryRouter>
        <DepartmentsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Road Maintenance')).toBeVisible()
    expect(screen.getByText('ACTIVE')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Seed demonstration departments' })).toBeVisible()
  })
  it('creates a confirmed department and waits for persisted success', async () => {
    const fetch = mock()
    render(
      <MemoryRouter>
        <DepartmentsPage />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Create department' }))
    fireEvent.change(screen.getByLabelText('Department code'), { target: { value: 'PARKS_TEAM' } })
    fireEvent.change(screen.getByLabelText('Department name'), { target: { value: 'Parks Team' } })
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and save work change' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const post = fetch.mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      code: 'PARKS_TEAM',
      expectedVersion: 0,
      active: true,
      confirmed: true,
    })
  })
  it('renders department memberships, service mode, workload and edit controls', async () => {
    mock()
    render(
      <MemoryRouter initialEntries={[`/departments/${id}`]}>
        <Routes>
          <Route path="/departments/:departmentId" element={<DepartmentDetailsPage />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(
      await screen.findByRole('heading', { name: 'Officer availability and workload' }),
    ).toBeVisible()
    expect(screen.getByText('AVAILABLE')).toBeVisible()
    expect(
      screen.getByRole('progressbar', { name: 'Field Officer weighted utilization' }),
    ).toHaveAttribute('value', '30')
    expect(screen.getByRole('button', { name: 'Add officer membership' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Edit department' }))
    expect(screen.getByLabelText('Department name')).toHaveValue('Road Maintenance')
  })
  it('distinguishes suggestions and assigned state, without auto-writing recommendations', async () => {
    const fetch = mock()
    detail()
    expect(await screen.findByRole('heading', { name: /Recommended officers/ })).toBeVisible()
    expect(screen.getByText('No officer assigned')).toBeVisible()
    expect(screen.getByText('CATEGORY_DEMONSTRATION · rule version rules-1')).toBeVisible()
    expect(fetch.mock.calls.every(([, i]) => !i?.method || i.method === 'GET')).toBe(true)
  })
  it('submits reassignment with current versions and documented reason', async () => {
    const fetch = mock()
    detail()
    fireEvent.click(await screen.findByRole('button', { name: 'Assign or reassign work' }))
    fireEvent.change(screen.getByLabelText('Eligible officer ID (blank removes officer)'), {
      target: { value: id },
    })
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and save work change' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([u, i]) => u.endsWith('/reassign') && i?.method === 'POST'),
      ).toBe(true),
    )
    const post = fetch.mock.calls.find(([u]) => u.endsWith('/reassign'))
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      expectedIncidentVersion: 2,
      expectedAssignmentVersion: 1,
      officerId: id,
      departmentId: id,
    })
  })
  it('displays officer-specific queue statistics and pending priorities', async () => {
    mock()
    render(
      <MemoryRouter>
        <OfficerDashboard />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Library road pothole')).toBeVisible()
    expect(screen.getByText('PRIORITY PENDING / STALE')).toBeVisible()
    expect(screen.getByText('My global weighted workload: 3 units')).toBeVisible()
  })
  it('keeps unavailable cloud queue statistics unknown instead of displaying a false zero', async () => {
    mock({
      '/api/officer/incidents?': {
        ...page,
        stats: { assigned: null, inProgress: null, high: null, critical: null },
      },
    })
    render(
      <MemoryRouter>
        <OfficerDashboard />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Library road pothole')).toBeVisible()
    expect(screen.getByText('High priority').parentElement).toHaveTextContent('Unavailable')
    expect(screen.getByText('In progress').parentElement).toHaveTextContent('Unavailable')
  })
  it('starts assigned work with a private progress note', async () => {
    const own = {
      ...state,
      assignment: { ...state.assignment, officerId: id, status: 'OFFICER_ASSIGNED' },
    }
    const fetch = mock({ [`/api/officer/incidents/${id}`]: own })
    detail(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Start work' }))
    fireEvent.change(screen.getByLabelText('Private operational progress note'), {
      target: { value: 'Crew inspected the damaged road surface' },
    })
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and save work change' }))
    await waitFor(() => expect(fetch.mock.calls.some(([u]) => u.endsWith('/start'))).toBe(true))
    expect(
      screen.queryByRole('button', { name: 'Assign or reassign work' }),
    ).not.toBeInTheDocument()
  })
  it('supports progress updates without a resolution control', async () => {
    mock({
      [`/api/officer/incidents/${id}`]: {
        ...state,
        assignment: { ...state.assignment, officerId: id, status: 'IN_PROGRESS', percentage: 20 },
      },
    })
    detail(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Record progress' }))
    expect(screen.getByLabelText('Work percentage (not verified resolution)')).toHaveValue(20)
    expect(screen.queryByRole('button', { name: /resolve incident/i })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Blocked work: request administrative review')).toBeVisible()
  })
  it('shows empty and error queues honestly', async () => {
    mock({ '/api/officer/incidents?': { ...page, items: [] } })
    render(
      <MemoryRouter>
        <WorkQueue officer />
      </MemoryRouter>,
    )
    expect(await screen.findByText('No work matches this queue')).toBeVisible()
  })
  it('renders failed requests with retry', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ detail: 'Work storage unavailable' }, 503)),
    )
    render(
      <MemoryRouter>
        <WorkQueue />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Work storage unavailable')).toBeVisible()
  })
  it('explains missing capacity without inventing utilization', () => {
    render(<WorkloadCard officer={{ ...officer, capacity: null }} />)
    expect(screen.getByText('Unknown capacity: manual approval only.')).toBeVisible()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
  it('retains the exact operation ID for ambiguous retries', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: 'Retry same operation' }, 503))
      .mockResolvedValueOnce(json({ version: 2 }))
    vi.stubGlobal('fetch', fetch)
    const saved = vi.fn()
    render(
      <WorkConfirmation
        operation={{
          title: 'Assign',
          path: '/admin/test',
          payload: () => ({ expectedAssignmentVersion: 1 }),
        }}
        onClose={vi.fn()}
        onSaved={saved}
      />,
    )
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and save work change' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Retry same work operation' }))
    await waitFor(() => expect(saved).toHaveBeenCalled())
    expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body)
  })
  it('requires reason and confirmation before a write', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    render(
      <WorkConfirmation
        operation={{ title: 'Assign', path: '/admin/test', payload: () => ({}) }}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    fireEvent.submit(
      screen.getByRole('button', { name: 'Confirm and save work change' }).closest('form')!,
    )
    expect(await screen.findByText(/Enter a reason/)).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('stale conflicts require refresh instead of pretending success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ detail: 'Work version changed' }, 409)),
    )
    const saved = vi.fn()
    render(
      <WorkConfirmation
        operation={{ title: 'Assign', path: '/admin/test', payload: () => ({}) }}
        onClose={vi.fn()}
        onSaved={saved}
      />,
    )
    confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and save work change' }))
    expect(await screen.findByText(/Close this dialog and refresh/)).toBeVisible()
    expect(saved).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Retry same work operation' })).toBeDisabled()
  })
  it('citizens cannot open assignment administration routes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        json({
          id,
          email: 'citizen@example.com',
          display_name: 'Citizen',
          role: 'CITIZEN',
          provider: 'local',
          is_active: true,
          is_verified: true,
          is_authenticated: true,
        }),
      ),
    )
    render(
      <MemoryRouter initialEntries={['/admin/assignments']}>
        <App />
      </MemoryRouter>,
    )
    expect(
      await screen.findByRole('heading', { name: /not authorized|access denied/i }),
    ).toBeVisible()
  })
})
