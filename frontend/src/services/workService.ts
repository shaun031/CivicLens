import { authRequest } from '../auth/authClient'
import type { PriorityResult } from './priorityService'
export interface Area {
  name: string
  south: number
  north: number
  west: number
  east: number
}
export interface Department {
  id: string
  code: string
  name: string
  description: string
  active: boolean
  areas: Area[]
  version: number
  officerCount?: number
  activeIncidents?: number
  highCriticalIncidents?: number
  pendingPriorityIncidents?: number
}
export interface Officer {
  officerId: string
  displayName: string
  departmentId: string
  active: boolean
  eligibleAccount: boolean
  availability: string
  capacity: number | null
  areas: Area[]
  version: number
  workload: number
  activeIncidents: number
  pendingPriorities: number
  utilization?: number | null
  projectedWorkload?: number
  explanation?: string
}
export interface Rule {
  id: string
  category: string
  departmentId: string
  precedence: number
  active: boolean
  version: number
}
export interface DepartmentDetail extends Department {
  rebalancing?: {
    proposals: { incidentId: string; fromOfficerId: string; toOfficerId: string; reason: string }[]
    message: string
  }
  officers: Officer[]
  rules: Rule[]
  workload: {
    activeIncidents: number
    unassignedIncidents: number
    weightedWorkload: number
    overCapacity: string[]
    policy: string
  }
}
export interface Assignment {
  incidentId: string
  departmentId: string | null
  officerId: string | null
  status: string
  method: string | null
  ruleVersion: string | null
  explanation: string[]
  version: number
  percentage: number
  assignedAt: string | null
  updatedAt: string | null
}
export interface WorkItem {
  incidentId: string
  title: string
  category: string
  latitude: number
  longitude: number
  incidentVersion: number
  assignment: Assignment
  departmentName?: string | null
  priorityStale: boolean
  priority: PriorityResult | null
}
export interface WorkDetail extends WorkItem {
  incidentStatus: string
  department: Department | null
  suggestedRouting?: {
    departmentId: string | null
    review: boolean
    mode: string
    explanation: string[]
    ruleVersion: string
  }
  recommendations?: {
    ranked: Officer[]
    excluded: { officerId: string; reasons: string[] }[]
    incomingUnits?: number
    message?: string
    mode: string
  }
  evidence?: { complaintId: string; imageId: string }[]
}
export interface WorkHistory {
  eventId: string
  kind: string
  actorId: string
  reason: string
  createdAt: string
  after: { status?: string; note?: string; percentage?: number }
}
export interface WorkPage {
  items: WorkItem[]
  nextCursor: string | null
  stats: {
    total?: number
    assigned: number
    inProgress: number
    high: number
    critical: number
    urgent: number
    pendingPriority: number
  }
  workload?: { workload: number; activeIncidents: number; pendingPriorities: number }
}
export const workService = {
  departments: () => authRequest<{ items: Department[] }>('/admin/departments'),
  department: (id: string) =>
    authRequest<DepartmentDetail>(`/admin/departments/${encodeURIComponent(id)}`),
  directory: (after = '') =>
    authRequest<{ items: { officerId: string; displayName: string }[]; nextAfter: string | null }>(
      `/admin/officers${after ? `?after=${encodeURIComponent(after)}` : ''}`,
    ),
  detail: (id: string, officer = false) =>
    authRequest<WorkDetail>(
      officer
        ? `/officer/incidents/${encodeURIComponent(id)}`
        : `/admin/incidents/${encodeURIComponent(id)}/assignment`,
    ),
  queue: async (query: string, officer = false, department?: string, unassigned = false) => {
    const result = await authRequest<WorkPage>(
      `${officer ? '/officer/incidents' : department ? `/admin/departments/${encodeURIComponent(department)}/incidents` : unassigned ? '/admin/assignments/unassigned' : '/admin/assignments'}?${query}`,
    )
    if (!Array.isArray(result.items) || !result.stats || typeof result.stats !== 'object')
      throw new Error('The API returned an invalid work queue. Refresh or check the backend.')
    return result
  },
  history: (id: string, officer = false, department = false, cursor?: string) =>
    authRequest<{ items: WorkHistory[]; nextCursor: string | null }>(
      `${officer ? `/officer/incidents/${encodeURIComponent(id)}/history` : department ? `/admin/departments/${encodeURIComponent(id)}/history` : `/admin/incidents/${encodeURIComponent(id)}/assignment-history`}?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`,
    ),
  summary: () => authRequest<Record<string, number>>('/admin/departments/summary'),
  change: (path: string, method: string, body: object) => authRequest<object>(path, method, body),
}
