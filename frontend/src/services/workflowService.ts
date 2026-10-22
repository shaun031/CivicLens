import { authRequest } from '../auth/authClient'
export interface Page<T> {
  items: T[]
  nextCursor: string | null
}
export interface Workflow {
  workflow_id: string
  workflow_type: string
  aggregate_id: string
  correlation_id: string
  status: string
  current_step: string | null
  attempt_count: number
  started_at: string | null
  updated_at: string
  completed_at: string | null
  error_category: string | null
  incident_id: string | null
  steps?: {
    step: string
    status: string
    updated_at: string
    attempts?: number
    result: Record<string, unknown>
  }[]
}
export interface DeadLetter {
  message_id: string
  event_id: string
  consumer: string
  attempts: number
  error_category: string
  redrives: number
  acknowledged_at: string | null
}
export interface Escalation {
  escalation_id: string
  incident_id: string
  milestone: string
  deadline: string
  status: string
  created_at: string
}
export interface Policy {
  policy_id: string
  priority_band: string
  category: string | null
  department_id: string | null
  urgent: boolean
  response_hours: number
  resolution_hours: number
  version: number
}
export interface Summary {
  workflows: Record<string, number>
  queue: Record<string, number>
  pendingEvents: number | null
  averageProcessingSeconds: number | null
  openEscalations: number | null
  sampled?: boolean
}
async function page<T>(path: string, filters: Record<string, string> = {}) {
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value))
  const value = await authRequest<Page<T>>(`${path}?${query}`)
  if (!Array.isArray(value.items)) throw new Error('Invalid workflow response. Refresh to retry.')
  return value
}
export const workflowService = {
  summary: () => authRequest<Summary>('/admin/workflows/summary'),
  list: (filters: Record<string, string>) => page<Workflow>('/admin/workflows', filters),
  detail: (id: string) => authRequest<Workflow>(`/admin/workflows/${id}`),
  dead: (cursor = '') => page<DeadLetter>('/admin/workflows/dead-letters', { cursor }),
  escalations: (cursor = '') => page<Escalation>('/admin/sla/escalations', { cursor }),
  policies: () => authRequest<{ items: Policy[] }>('/admin/sla/policies'),
  control: (path: string, body: object, method = 'POST') => authRequest(path, method, body),
}
