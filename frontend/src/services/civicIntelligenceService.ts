import { authRequest } from '../auth/authClient'

export interface Repair {
  attemptId: string
  incidentId: string
  requestId?: string
  title: string
  description: string
  notes?: string
  state: string
  cycle: number
  version: number
  incidentVersion: number
  incidentStatus: string
  submittedAt: string
  repairedAt: string
  verifiedAt: string | null
  membershipChanged: boolean
  canRespond?: boolean
  decisionReason?: string
  recommendation?: string
  eligibleCitizens?: number
  missingResponses?: number
  responses?: Record<string, number>
  feedback?: { result: string; feedback: string; eligible: boolean; createdAt: string }[]
  response?: { result: string; feedback: string; createdAt: string } | null
  images: { imageId: string; kind: string; url: string; approved: boolean }[]
  audit?: { kind: string; reason: string; created_at: string }[]
  relatedComplaints?: string[]
  priority?: { stale: boolean; priority: { urgentHazard: boolean; priorityBand: string } | null }
}
export interface Page<T> {
  items: T[]
  nextAfter: string | null
  summary?: Record<string, number>
}
export interface Recurrence {
  recurrenceId: string
  previousIncidentId: string
  newIncidentId: string
  repairAttemptId: string
  previousTitle: string
  newTitle: string
  category: string
  state: string
  version: number
  score: number
  distanceMeters: number
  daysSinceRepair: number
  needsReassessment: boolean
  previousRepairVerifiedAt: string
  newReportedAt: string
  newIncidentStatus: string
  reviewReason: string | null
  explanation: { signals: Record<string, number>; limitations: string[]; contradictions: string[] }
  timeline: { incidentId: string; at: string; kind: string }[]
}
export interface FairnessArea {
  areaId: string
  cell: string
  south: number
  west: number
  north: number
  east: number
  incidentCount: number
  activeIncidents: number
  activeBacklogRate: number | null
  medianWorkStartHours: number | null
  responseObservations: number
  missingWorkStart: number
  overdueRate: number | null
  overdueIncidents: number
  slaObservations: number
  missingSla: number
  verifiedResolutionRate: number | null
  verifiedResolutions: number
  medianUnresolvedDays: number | null
  confirmedRecurrenceIncidents: number
  potentialRecurrenceIncidents: number
  status: string
  dataSufficient: boolean
  flags: string[]
  priorityMix: Record<string, number>
  departmentMix: Record<string, number>
  comparisonObservations: number
}
export interface FairnessResult {
  areas: FairnessArea[]
  calculatedAt: string
  window: { startInclusive: string; endExclusive: string }
  reportingTimezone: string
  limitations: string[]
  definitions: Record<string, string>
  minimumSampleSize: number
  grouping: string
  normalization: string
}
export interface FairnessReviewRecord {
  review_id: string
  area_id: string
  version: number
  state: string
  notes: string
  context: Record<string, string>
}

export function sendEvidence<T>(path: string, payload: unknown, files: File[]) {
  const form = new FormData()
  form.append('payload', JSON.stringify(payload))
  files.forEach((file) => form.append('images', file))
  return authRequest<T>(path, 'POST', form)
}
