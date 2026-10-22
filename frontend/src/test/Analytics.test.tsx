import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

vi.mock('../components/analytics/HotspotMap', () => ({
  default: () => <div aria-label="Private geographic concentration map">Offline map fixture</div>,
}))
const id = 'cdbcedba-79f3-4c45-b3c9-b0572451e40b'
const base = {
  calculatedAt: '2026-10-20T12:00:00Z',
  reportingTimezone: 'Asia/Kolkata',
  scope: 'test-municipality',
  window: { startInclusive: '2026-09-20T18:30:00Z', endExclusive: '2026-10-20T18:30:00Z' },
  dataFreshness: {
    mode: 'DIRECT_SNAPSHOT',
    sourceRevision: 12,
    projectionVersion: 1,
    stalePriorityCount: 2,
    stale: false,
  },
  limitations: [],
  totalComplaints: 15,
  totalIncidents: 1,
  activeIncidents: 1,
  criticalIncidents: 1,
  overdueIncidents: 1,
  unassignedIncidents: 0,
  priorityDistribution: [{ label: 'CRITICAL', count: 1 }],
  categoryDistribution: [{ label: 'POTHOLE', count: 1 }],
  complaintTrend: [{ date: '2026-10-20', count: 15 }],
  incidentTrend: [{ date: '2026-10-20', count: 1 }],
  urgentQueue: [
    {
      incidentId: id,
      category: 'POTHOLE',
      priority: 'CRITICAL',
      urgentHazard: true,
      reportCount: 15,
      overdue: true,
    },
  ],
  recentActivity: [],
  items: [
    {
      departmentId: id,
      membershipId: id,
      displayName: 'Synthetic Officer',
      name: 'Road Maintenance',
      priorities: [{ label: 'HIGH', count: 1 }],
      activeIncidents: 1,
      workloadUnits: 3,
      weightedWorkload: 3,
      capacity: null,
      utilization: null,
      assignedActiveIncidents: 1,
      availability: 'AVAILABLE',
      selectedWorkload: 3,
      overdue: 1,
    },
  ],
  cells: [
    {
      cell: '1297:7759',
      south: 12.97,
      west: 77.59,
      north: 12.98,
      east: 77.6,
      incidentCount: 1,
      reportCount: 15,
      activeIncidents: 1,
      criticalIncidents: 1,
      overdueIncidents: 1,
    },
  ],
  totalBacklog: 1,
  aging: [{ label: '7–30 days', count: 1 }],
  overlappingSubgroups: [{ label: 'Critical', count: 1 }],
  responseCompliance: { rate: null, denominator: 0, pending: 1, unavailable: 0 },
  resolutionCompliance: { rate: null, denominator: 0, pending: 1, unavailable: 0 },
  distribution: [{ label: 'CRITICAL', count: 1 }],
  byCategory: [{ label: 'POTHOLE', count: 1 }],
  nextCursor: null,
}
const config = {
  reportingTimezone: 'Asia/Kolkata',
  scope: 'test-municipality',
  serviceAreas: {},
  departments: [{ id, name: 'Road Maintenance', active: 1 }],
  reports: [
    { type: 'citywide', view: 'overview' },
    { type: 'officers', view: 'officers' },
  ],
}
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function setup(
  path: string,
  options: { role?: string; fail?: boolean; empty?: boolean; exportFail?: boolean } = {},
) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me'))
      return response({
        id,
        email: 'synthetic@example.com',
        display_name: 'Analytics Admin',
        role: options.role ?? 'ADMIN',
        is_active: true,
        is_verified: true,
        is_authenticated: true,
        provider: 'local',
      })
    if (url.endsWith('/notifications/unread-count')) return response({ unreadCount: 0 })
    if (url.endsWith('/portal/admin')) return response({ message: 'authorized' })
    if (options.fail && url.includes('/analytics/'))
      return response({ detail: 'Analytics source unavailable' }, 503)
    if (url.endsWith('/analytics/reports')) return response(config)
    if (url.includes('/csv?')) {
      expect(init?.method).toBe('POST')
      return options.exportFail
        ? response({ detail: 'Export audit unavailable' }, 503)
        : new Response('metric,value\r\ntotalComplaints,15', {
            headers: { 'Content-Type': 'text/csv' },
          })
    }
    if (url.includes('/analytics/reports/'))
      return response({
        title: 'Citywide municipal report',
        reportType: 'citywide',
        generatedAt: base.calculatedAt,
        reportingTimezone: base.reportingTimezone,
        columns: ['metric', 'value'],
        rows: [{ metric: 'totalComplaints', value: 15 }],
        sampleSize: 1,
        definitions: 'Current canonical state only.',
        pageOnly: false,
        nextCursor: null,
        dataFreshness: base.dataFreshness,
      })
    if (url.includes('/analytics/'))
      return response(
        options.empty
          ? {
              ...base,
              items: [],
              cells: [],
              urgentQueue: [],
              priorityDistribution: [],
              categoryDistribution: [],
              complaintTrend: [],
              incidentTrend: [],
              totalComplaints: 0,
              totalIncidents: 0,
            }
          : base,
      )
    throw new Error(`Unexpected request ${url}`)
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
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('Private Phase11 municipal analytics', () => {
  it('renders separate report/incident counts, freshness, charts and authorized drill-down', async () => {
    setup('/admin/command-center')
    expect(
      await screen.findByRole('heading', { name: 'Municipal Command Center' }),
    ).toBeInTheDocument()
    expect(await screen.findByText('Eligible complaint reports')).toBeInTheDocument()
    expect(screen.getByText('Eligible complaint reports').parentElement).toHaveTextContent('15')
    expect(screen.getByText(/Consistent source snapshot/)).toBeInTheDocument()
    expect(screen.getByText(/Stale\/unavailable priorities: 2/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'POTHOLE: 1' })).toHaveAttribute(
      'href',
      '/admin/analytics/incidents?category=POTHOLE',
    )
    expect(screen.getByRole('img', { name: /Canonical incidents by category/ })).toBeInTheDocument()
  })
  it('combines URL category, date, department and priority filters and resets pagination', async () => {
    const fetch = setup('/admin/command-center?start=2026-10-01&end=2026-10-20')
    await screen.findByText('Eligible complaint reports')
    fireEvent.change(screen.getByLabelText('Infrastructure category'), {
      target: { value: 'POTHOLE' },
    })
    fireEvent.change(screen.getByLabelText('Priority band'), { target: { value: 'HIGH' } })
    fireEvent.change(screen.getByLabelText('Department'), { target: { value: id } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply analytics filters' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url]) =>
            url.includes('priority=HIGH') &&
            url.includes('category=POTHOLE') &&
            url.includes('start=2026-10-01') &&
            url.includes(`department=${id}`),
        ),
      ).toBe(true),
    )
  })
  it.each([
    ['CITIZEN', '/admin/command-center'],
    ['OFFICER', '/admin/analytics/officers'],
    ['CITIZEN', '/admin/reports'],
  ])('denies %s internal analytics at %s', async (role, path) => {
    const fetch = setup(path, { role })
    expect(
      await screen.findByRole('heading', { name: /Access denied|not authorized/i }),
    ).toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => url.includes('/analytics/'))).toBe(false)
  })
  it('shows source failure without falling back to operational sample numbers', async () => {
    setup('/admin/command-center', { fail: true })
    expect(await screen.findByRole('alert')).toHaveTextContent('Analytics source unavailable')
    expect(screen.queryByText('15')).not.toBeInTheDocument()
  })
  it('renders meaningful real empty states', async () => {
    setup('/admin/command-center', { empty: true })
    expect(await screen.findByText('Eligible complaint reports')).toBeInTheDocument()
    expect(screen.getAllByText('No chart data').length).toBeGreaterThan(0)
    expect(screen.getAllByText('No records in this scope.').length).toBeGreaterThan(0)
  })
  it.each([
    ['departments', 'Department operations'],
    ['officers', 'Officer workloads and capacity'],
    ['incidents', 'Filtered canonical incidents'],
    ['sla', 'Measured compliance'],
    ['backlog', 'Unique active backlog'],
  ])('renders %s analysis with accessible alternatives', async (view, title) => {
    setup(`/admin/analytics/${view}`)
    expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
  })
  it('keeps canonical and report volume map layers distinct and provides cell list', async () => {
    setup('/admin/hotspots')
    expect(
      await screen.findByRole('heading', { name: 'Accessible occupied-cell list' }),
    ).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Map measure'), { target: { value: 'reportCount' } })
    expect(screen.getByLabelText('Map measure')).toHaveValue('reportCount')
    expect(screen.getByRole('columnheader', { name: 'Eligible reports' })).toBeInTheDocument()
  })
  it('previews and downloads a protected CSV using authenticated POST', async () => {
    Object.defineProperty(URL, 'createObjectURL', {
      value: vi.fn(() => 'blob:analytics-fixture'),
      configurable: true,
    })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const fetch = setup('/admin/reports')
    await screen.findByRole('heading', { name: 'Report preview' })
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledOnce())
    expect(fetch.mock.calls.find(([url]) => url.includes('/csv?'))?.[1]?.credentials).toBe(
      'include',
    )
  })
  it('reports export failure accurately without creating a fake file', async () => {
    setup('/admin/reports', { exportFail: true })
    await screen.findByRole('heading', { name: 'Report preview' })
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Export audit unavailable')
  })
})
