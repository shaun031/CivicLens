import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

vi.mock('../components/analytics/FairnessMap', () => ({
  default: () => (
    <div aria-label="Private geographic service comparison map">Offline comparison layer</div>
  ),
}))
const id = 'cdbcedba-79f3-4c45-b3c9-b0572451e40b'
const repair = {
  attemptId: id,
  incidentId: id,
  requestId: id,
  title: 'Pothole repair at college entrance',
  description: 'Repair surface restored and inspected by assigned officer.',
  state: 'PENDING_VERIFICATION',
  cycle: 1,
  version: 1,
  incidentVersion: 2,
  incidentStatus: 'OPEN',
  submittedAt: '2026-10-20T12:00:00Z',
  repairedAt: '2026-10-20T11:00:00Z',
  verifiedAt: null,
  membershipChanged: false,
  canRespond: true,
  images: [],
  response: null,
  recommendation: 'INSUFFICIENT_RESPONSES',
  eligibleCitizens: 1,
  missingResponses: 1,
  responses: { CONFIRMED_FIXED: 0, STILL_BROKEN: 0, UNSURE: 0 },
  notes: 'Private officer note',
  feedback: [],
  audit: [],
}
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function setup(
  path: string,
  options: { role?: string; empty?: boolean; fail?: boolean; operationFail?: boolean } = {},
) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me'))
      return response({
        id,
        email: 'test@example.com',
        display_name: 'Test Account',
        role: options.role ?? 'ADMIN',
        is_active: true,
        is_verified: true,
        is_authenticated: true,
        provider: 'local',
      })
    if (url.includes('/notifications/unread-count')) return response({ unreadCount: 0 })
    if (url.includes('/portal/')) return response({ message: 'authorized' })
    if (options.fail) return response({ detail: 'Source temporarily unavailable' }, 503)
    if (init?.method === 'POST' || init?.method === 'PATCH')
      return options.operationFail
        ? response({ detail: 'Concurrent update; refresh' }, 409)
        : response({ message: 'Recorded' })
    if (url.includes('/analytics/reports'))
      return response({
        reports: [],
        departments: [],
        serviceAreas: {},
        reportingTimezone: 'UTC',
        scope: 'test',
      })
    if (url.includes('/fairness/reviews')) return response({ items: [], nextAfter: null })
    if (url.includes('/analytics/fairness'))
      return response({
        areas: [],
        minimumSampleSize: 10,
        grouping: 'Non-overlapping grid',
        normalization: 'UNADJUSTED',
        calculatedAt: '2026-10-20T12:00:00Z',
        reportingTimezone: 'UTC',
        window: { startInclusive: '2026-10-01', endExclusive: '2026-11-01' },
        limitations: ['Differences do not establish discrimination'],
        definitions: { response: 'Recorded work start in hours' },
      })
    if (url.includes('/admin/recurrences')) return response({ items: [], nextAfter: null })
    if (url.includes('/admin/repairs/') && !url.includes('/pending')) return response(repair)
    if (url.includes('/verification-requests/') && !url.includes('/respond'))
      return response(repair)
    if (
      url.includes('/repairs/pending') ||
      url.includes('/verification-requests') ||
      url.includes('/verification-history') ||
      url.includes('/repair-attempts')
    )
      return response({
        items: options.empty || options.role === 'OFFICER' ? [] : [repair],
        nextAfter: null,
        summary: { PENDING_VERIFICATION: 1 },
      })
    if (url.includes('/officer/incidents/'))
      return response({ incidentVersion: 2, assignment: { version: 1, status: 'IN_PROGRESS' } })
    throw new Error('Unexpected request ' + url)
  })
  vi.stubGlobal('fetch', fetch)
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
  return fetch
}
afterEach(() => vi.unstubAllGlobals())
describe('Phase12 protected operational interfaces', () => {
  it.each(['CONFIRMED_FIXED', 'STILL_BROKEN', 'UNSURE'])(
    'records %s without fabricating official closure',
    async (answer) => {
      const fetch = setup('/citizen/verification', { role: 'CITIZEN' })
      fireEvent.click(await screen.findByRole('button', { name: 'Verify repair / view response' }))
      fireEvent.change(await screen.findByLabelText('Repair response'), {
        target: { value: answer },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Record verification response' }))
      await screen.findByText('Saved by the backend. Refreshing the recorded state.')
      const call = fetch.mock.calls.find(
        ([url, init]) => url.includes('/respond') && init?.method === 'POST',
      )
      expect(JSON.parse((call![1]!.body as FormData).get('payload') as string).result).toBe(answer)
      expect(await screen.findByText(/not an official closure/)).toBeInTheDocument()
    },
  )
  it('shows empty verification requests honestly', async () => {
    setup('/citizen/verification', { role: 'CITIZEN', empty: true })
    expect(await screen.findByText('No eligible repair requests')).toBeInTheDocument()
  })
  it('blocks real verification actions while sample preview is selected', async () => {
    const fetch = setup('/citizen/verification', { role: 'CITIZEN' })
    await screen.findByRole('button', { name: 'Verify repair / view response' })
    fetch.mockClear()
    fireEvent.click(screen.getByLabelText('Show sample data'))
    expect(
      await screen.findByText(/Repair verification has no fabricated sample results/),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Verify repair / view response' }),
    ).not.toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => url.includes('/verification-requests'))).toBe(false)
  })
  it('preserves backend errors and does not report success', async () => {
    setup('/citizen/verification', { role: 'CITIZEN', operationFail: true })
    fireEvent.click(await screen.findByRole('button', { name: 'Verify repair / view response' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Record verification response' }))
    expect(await screen.findByText('Concurrent update; refresh')).toBeInTheDocument()
    expect(
      screen.queryByText('Saved by the backend. Refreshing the recorded state.'),
    ).not.toBeInTheDocument()
  })
  it.each(['approve', 'reject', 'request rework'])(
    'requires an accountable administrator %s decision',
    async (action) => {
      const fetch = setup('/admin/repair-verification')
      fireEvent.click(await screen.findByRole('button', { name: 'Review repair attempt' }))
      const button = await screen.findByRole('button', { name: action })
      expect(button).toBeDisabled()
      fireEvent.change(screen.getByLabelText('Decision reason / independent verification basis'), {
        target: { value: 'Independent site review and citizen feedback evaluated carefully.' },
      })
      fireEvent.click(
        screen.getByLabelText(
          'I reviewed current evidence, feedback, hazards and incident membership.',
        ),
      )
      fireEvent.click(button)
      await waitFor(() =>
        expect(
          fetch.mock.calls.some(
            ([url, init]) =>
              url.endsWith('/' + action.replaceAll(' ', '-')) && init?.method === 'POST',
          ),
        ).toBe(true),
      )
    },
  )
  it('supports officer submission with optional private evidence', async () => {
    const fetch = setup(`/officer/incidents/${id}/repair`, { role: 'OFFICER' })
    fireEvent.change(await screen.findByLabelText('Repair description'), {
      target: { value: 'Physical road surface repaired and inspected on location.' },
    })
    fireEvent.change(screen.getByLabelText('Repair completed at (your local time)'), {
      target: { value: '2026-10-20T11:00' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Submit repair for verification' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url, init]) => url.endsWith('/repair-attempts') && init?.method === 'POST',
        ),
      ).toBe(true),
    )
    expect(
      screen.queryByRole('button', { name: 'Approve verified resolution' }),
    ).not.toBeInTheDocument()
  })
  it('shows recurrence safeguards and empty state', async () => {
    setup('/admin/recurrences')
    expect(await screen.findByText('No recurrence records in this selection')).toBeInTheDocument()
    expect(screen.getByText(/scores are not calibrated probabilities/)).toBeInTheDocument()
  })
  it('shows fairness limitations and an honest empty map cohort', async () => {
    setup('/admin/fairness')
    expect(await screen.findByText(/No recorded incidents in this selection/)).toBeInTheDocument()
    expect(
      await screen.findByLabelText('Private geographic service comparison map'),
    ).toBeInTheDocument()
    expect(screen.getByText('Differences do not establish discrimination')).toBeInTheDocument()
  })
  it('offers retry when source reads fail', async () => {
    setup('/admin/repair-verification', { fail: true })
    expect(await screen.findByText('Source temporarily unavailable')).toBeInTheDocument()
  })
  it.each(['/admin/repair-verification', '/admin/recurrences', '/admin/fairness'])(
    'rejects citizen access to %s',
    async (path) => {
      setup(path, { role: 'CITIZEN' })
      expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument()
    },
  )
})
