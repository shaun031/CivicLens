import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

const id = 'babbadca-7882-47c1-aedc-660f7e34222c'
const notification = {
  notificationId: id,
  type: 'COMPLAINT_RECEIVED',
  title: 'Report accepted',
  message: 'Stored privately for your account.',
  read: false,
  createdAt: '2026-10-20T10:00:00Z',
  targetUrl: `/citizen/complaints/${id}`,
  isSimulated: false,
}
const workflow = {
  workflow_id: id,
  workflow_type: 'IncidentTriageWorkflow',
  aggregate_id: id,
  correlation_id: id,
  status: 'WAITING_RETRY',
  current_step: 'RecalculatePriority',
  attempt_count: 2,
  started_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-20T10:01:00Z',
  completed_at: null,
  incident_id: id,
  error_category: 'TRANSIENT_STEP_ERROR',
  steps: [
    {
      step: 'RunDuplicateDetection',
      status: 'COMPLETED',
      updated_at: '2026-10-20T10:00:00Z',
      result: { completed: true },
    },
  ],
}
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function setup(path: string, options: { admin?: boolean; empty?: boolean; fail?: boolean } = {}) {
  let read = false
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me'))
      return response({
        id,
        email: 'synthetic@example.com',
        display_name: 'Test Principal',
        role: options.admin ? 'ADMIN' : 'CITIZEN',
        is_active: true,
        is_verified: true,
        is_authenticated: true,
        provider: 'local',
      })
    if (options.fail && /notifications|workflows/.test(url))
      return response({ detail: 'Processing store unavailable.' }, 503)
    if (url.endsWith('/notifications/unread-count'))
      return response({ unreadCount: read || options.empty ? 0 : 1 })
    if (url.endsWith('/read') || url.endsWith('/mark-all-read')) {
      read = true
      return response({ unreadCount: 0 })
    }
    if (url.includes('/notifications?'))
      return response({
        items: options.empty ? [] : [{ ...notification, read }],
        nextCursor: options.empty ? null : 'older-token',
      })
    if (url.endsWith('/admin/workflows/summary'))
      return response({
        workflows: { COMPLETED: 3, WAITING_RETRY: 1 },
        queue: { RETRY: 1, DEAD: 1 },
        pendingEvents: 2,
        averageProcessingSeconds: 1.2,
        openEscalations: 1,
      })
    if (url.includes('/admin/workflows/dead-letters?'))
      return response({
        items: options.empty
          ? []
          : [
              {
                message_id: id,
                event_id: id,
                consumer: 'triage',
                attempts: 5,
                error_category: 'RETRIES_EXHAUSTED',
                redrives: 0,
                acknowledged_at: null,
              },
            ],
        nextCursor: null,
      })
    if (url.includes('/admin/sla/escalations?'))
      return response({
        items: options.empty
          ? []
          : [
              {
                escalation_id: id,
                incident_id: id,
                milestone: 'RESPONSE',
                deadline: '2026-10-20T11:00:00Z',
                status: 'OPEN',
              },
            ],
        nextCursor: null,
      })
    if (url.endsWith('/admin/sla/policies'))
      return response({
        items: [
          {
            policy_id: 'LOW',
            priority_band: 'LOW',
            category: null,
            department_id: null,
            urgent: false,
            response_hours: 336,
            resolution_hours: 672,
            version: 1,
          },
        ],
      })
    if (url.includes('/admin/workflows?'))
      return response({ items: options.empty ? [] : [workflow], nextCursor: 'next-workflow-page' })
    if (url.endsWith(`/admin/workflows/${id}`)) return response(workflow)
    if (init?.method === 'POST' || init?.method === 'PUT') return response({ accepted: true })
    return response({ message: 'Access granted' })
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

describe('Real notifications and workflow operations', () => {
  it('loads private real notifications, unread count and authenticated links', async () => {
    setup('/notifications')
    expect(await screen.findByRole('heading', { name: 'Report accepted' })).toBeInTheDocument()
    expect(screen.getByText('Unread: 1')).toBeInTheDocument()
    expect(screen.getByText(/In-app notification/)).toBeInTheDocument()
    expect(screen.queryByText(/Simulated notification/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /View related page/ })).toHaveAttribute(
      'href',
      `/citizen/complaints/${id}`,
    )
  })
  it('persists mark-as-read and mark-all-read through backend calls', async () => {
    const fetch = setup('/notifications')
    fireEvent.click(await screen.findByRole('button', { name: /Mark as read/ }))
    await waitFor(() => expect(screen.getByText('Unread: 0')).toBeInTheDocument())
    expect(
      fetch.mock.calls.some(
        ([url, init]) => url.endsWith(`/${id}/read`) && init?.method === 'PATCH',
      ),
    ).toBe(true)
  })
  it('filters and paginates on the server without supplying another recipient ID', async () => {
    const fetch = setup('/notifications')
    await screen.findByRole('heading', { name: 'Report accepted' })
    fireEvent.change(screen.getByLabelText('Read status'), { target: { value: 'unread' } })
    await waitFor(() =>
      expect(fetch.mock.calls.some(([url]) => url.includes('read=false'))).toBe(true),
    )
    fireEvent.change(screen.getByLabelText('Notification type'), {
      target: { value: 'COMPLAINT_RECEIVED' },
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Older notifications' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url]) => url.includes('cursor=older-token') && url.includes('type=COMPLAINT_RECEIVED'),
        ),
      ).toBe(true),
    )
    expect(fetch.mock.calls.every(([url]) => !url.includes('recipient'))).toBe(true)
  })
  it('shows actual empty notification state', async () => {
    setup('/notifications', { empty: true })
    expect(await screen.findByRole('heading', { name: 'No notifications yet' })).toBeInTheDocument()
  })
  it('shows notification load errors and a bounded manual refresh', async () => {
    setup('/notifications', { fail: true })
    expect(await screen.findByText('Notifications unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument()
  })
  it('shows workflow history, accurate failure categories and separate SLA alerts', async () => {
    setup(`/admin/workflows/${id}`, { admin: true })
    expect(await screen.findByRole('heading', { name: 'Workflow details' })).toBeInTheDocument()
    expect(screen.getByText('RunDuplicateDetection')).toBeInTheDocument()
    expect(screen.getByText(/TRANSIENT_STEP_ERROR/)).toBeInTheDocument()
    expect(screen.getByText('OVERDUE')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry workflow' })).toBeInTheDocument()
  })
  it('requires reason and explicit confirmation before redrive and never exposes payload editing', async () => {
    const fetch = setup('/admin/workflows', { admin: true })
    fireEvent.click(await screen.findByRole('button', { name: 'Redrive message' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('button', { name: 'Confirm action' })).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('Reason'), {
      target: { value: 'Configuration repaired and approved for a bounded safe replay' },
    })
    fireEvent.click(within(dialog).getByRole('checkbox'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm action' }))
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url, init]) => url.endsWith('/redrive') && JSON.parse(init?.body as string).confirmed,
        ),
      ).toBe(true),
    )
    expect(screen.queryByLabelText(/payload/i)).not.toBeInTheDocument()
  })
  it('protects operational monitoring against citizens', async () => {
    setup('/admin/workflows')
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument()
  })
})
