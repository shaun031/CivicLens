import { authRequest } from '../auth/authClient'
import type { Incident, IncidentPage } from './incidentService'

export type PriorityBand = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export interface PriorityFactor {
  rawValue: number | null
  normalizedValue: number
  weight: number
  contribution: number
  status: string
}
export interface PriorityResult {
  incidentId: string
  incidentVersion: number
  calculatedScore: number
  calculatedBand: PriorityBand
  effectiveScore: number
  priorityBand: PriorityBand
  assessmentStatus: string
  factors: Record<'severity' | 'publicImpact' | 'reporters' | 'aging', PriorityFactor>
  urgentHazard: boolean
  hazardStatus: string
  overrideStatus: string
  unresolvedSeconds: number
  unresolvedDays: number
  explanation: string[]
  reviewFlags: string[]
  calculatedAt: string
  algorithmVersion: string
}
export interface PriorityControl {
  score?: number | null
  status?: string
  reason?: string
  evidenceReferences?: string[]
  assessedBy?: string
  assessedAt?: string
  epoch?: number
}
export interface PriorityState {
  incident: Incident
  priority: PriorityResult | null
  priorityRevision: number
  incidentVersion: number
  membershipEpoch: number
  controls: {
    severity?: PriorityControl
    publicImpact?: PriorityControl
    hazard?: PriorityControl & { flag: boolean }
    override?: PriorityControl & {
      overrideId?: string
      createdBy?: string
      createdAt?: string
      expiresAt?: string | null
    }
  }
  stale: boolean
  staleReasons: string[]
  evidenceOptions: { id: string; label: string }[]
  currentConfigVersion: string
}
export interface PriorityHistory {
  eventId: string
  kind: string
  reason: string
  actorId: string
  createdAt: string
  snapshot: {
    before: PriorityResult | null
    after: PriorityResult
    inputs: { uniqueReporters: number; totalReports: number }
  }
}
export interface PrioritySummary {
  activeIncidents: number
  scoredIncidents: number | null
  pendingOrStale: number | null
  bands: Record<PriorityBand, number | null>
  needsAssessment: number | null
  urgentHazards: number | null
  overridden: number | null
  providerNote?: string
}
export type PriorityOperation =
  'SEVERITY' | 'PUBLIC_IMPACT' | 'HAZARD' | 'OVERRIDE' | 'REMOVE_OVERRIDE' | 'RECALCULATE'
export interface PriorityAction {
  operationId: string
  expectedIncidentVersion: number
  expectedPriorityRevision: number
  reason: string
  confirmed: boolean
  score?: number | null
  status?: string
  evidenceReferences?: string[]
  flag?: boolean
  expiresAt?: string | null
}
const root = '/admin/incidents'
const encoded = encodeURIComponent
export const priorityService = {
  list: (query: string) =>
    authRequest<IncidentPage<{ incident: Incident; priority: PriorityResult }>>(
      `${root}/priorities?${query}`,
    ),
  summary: () => authRequest<PrioritySummary>(`${root}/priorities/summary`),
  detail: (id: string) => authRequest<PriorityState>(`${root}/${encoded(id)}/priority`),
  history: (id: string, cursor?: string) =>
    authRequest<IncidentPage<PriorityHistory>>(
      `${root}/${encoded(id)}/priority/history?limit=20${cursor ? `&cursor=${encoded(cursor)}` : ''}`,
    ),
  change: (id: string, kind: PriorityOperation, data: PriorityAction) => {
    const [method, suffix] = {
      SEVERITY: ['PATCH', 'severity'],
      PUBLIC_IMPACT: ['PATCH', 'public-impact'],
      HAZARD: ['PATCH', 'hazard-review'],
      OVERRIDE: ['POST', 'priority/override'],
      REMOVE_OVERRIDE: ['DELETE', 'priority/override'],
      RECALCULATE: ['POST', 'priority/recalculate'],
    }[kind]
    return authRequest<{ priority: PriorityResult }>(
      `${root}/${encoded(id)}/${suffix}`,
      method,
      data,
    )
  },
}
