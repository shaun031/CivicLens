import { authRequest } from '../auth/authClient'
import type { Category } from '../types/complaint'

export interface Incident {
  incidentId: string
  canonicalTitle: string
  canonicalDescription: string
  category: Category
  latitude: number
  longitude: number
  status: 'OPEN' | 'RESOLVED' | 'MERGED' | 'SUPERSEDED'
  representativeComplaintId: string
  totalComplaintCount: number
  uniqueReporterCount: number
  firstReportedAt: string
  lastReportedAt: string
  createdAt: string
  updatedAt: string
  version: number
  mergedIntoIncidentId?: string | null
  requestedIncidentId?: string
  aliasChain?: string[]
  reviewNeeded?: boolean
}
export interface IncidentMember {
  distanceMeters?: number
  complaintId: string
  incidentId: string
  title: string
  description: string
  category: Category
  status: string
  latitude: number
  longitude: number
  createdAt: string
  eligibleReporter: boolean
  images: { imageId: string; url: string }[]
}
export interface IncidentHistory {
  eventId: string
  operationId: string
  operation: string
  actorId: string
  reason: string
  createdAt: string
  evidence: {
    changes: {
      complaint_id: string
      previous_incident_id: string | null
      new_incident_id: string
      evidence?: Record<string, unknown>
    }[]
  }
}
export interface IncidentPage<T> {
  items: T[]
  nextCursor: string | null
}
export interface IncidentSummary {
  activeIncidents: number
  singleReportIncidents: number
  multiReportIncidents: number
  linkedComplaints: number
  pendingClusteringReviews: number | null
  splitOperations: number
  correctionOperations: number
  mergedIncidentRecords: number
}
export interface IncidentCorrection {
  operationId: string
  sourceIncidentId: string
  expectedSourceVersion: number
  reason: string
  confirmed: boolean
  targetIncidentId?: string
  expectedTargetVersion?: number
  physicalIssueConfirmed?: boolean
  complaintIds?: string[]
  complaintId?: string
  matchingCandidateId?: string
}
const root = '/admin/incidents'
const encoded = encodeURIComponent
export const incidentService = {
  list: (query: string) => authRequest<IncidentPage<Incident>>(`${root}?${query}`),
  summary: () => authRequest<IncidentSummary>(`${root}/summary`),
  detail: (id: string) => authRequest<Incident>(`${root}/${encoded(id)}`),
  members: (id: string, cursor?: string) =>
    authRequest<IncidentPage<IncidentMember>>(
      `${root}/${encoded(id)}/complaints?limit=30${cursor ? `&cursor=${encoded(cursor)}` : ''}`,
    ),
  history: (id: string, cursor?: string) =>
    authRequest<IncidentPage<IncidentHistory>>(
      `${root}/${encoded(id)}/history?limit=20${cursor ? `&cursor=${encoded(cursor)}` : ''}`,
    ),
  recommendations: (id: string) =>
    authRequest<{
      items: {
        sourceComplaintId: string
        targetIncidentId: string
        candidateId: string
        eligibleForAutoLink: boolean
        explanation: string
      }[]
      mode: string
      processing: { complaintId: string; state: string }[]
      nextCursor: string | null
    }>(`${root}/${encoded(id)}/recommendations`),
  correct: (
    kind: 'merge' | 'split' | 'unlink-complaint' | 'link-complaint' | 'recheck',
    data: IncidentCorrection,
  ) =>
    authRequest<Incident>(
      kind === 'merge'
        ? `${root}/merge`
        : `${root}/${encoded(
            kind === 'link-complaint' ? data.targetIncidentId! : data.sourceIncidentId,
          )}/${kind}`,
      'POST',
      data,
    ),
  ownerSummary: (id: string) =>
    authRequest<{
      incidentId: string | null
      category?: Category
      status?: string
      processing: string
    }>(`/complaints/${encoded(id)}/incident`),
}
