import { authRequest } from '../auth/authClient'
import type { Category } from '../types/complaint'
import type { Incident } from './incidentService'

export const classifications = [
  'STRONG_CANDIDATE',
  'REVIEW_REQUIRED',
  'WEAK_MATCH',
  'INSUFFICIENT_EVIDENCE',
  'CATEGORY_MISMATCH',
  'OUTSIDE_SEARCH_RADIUS',
] as const
export const reviewStatuses = [
  'PENDING_REVIEW',
  'DISMISSED',
  'REVIEWED_POSSIBLE_DUPLICATE',
] as const
export interface Candidate {
  candidateId: string
  sourceComplaintId: string
  possibleDuplicateId: string
  sourceTitle?: string
  duplicateTitle?: string
  sourceCategory?: Category
  duplicateCategory?: Category
  combinedScore: number
  geographicScore: number
  textScore: number
  imageScore: number | null
  distanceMeters: number
  effectiveWeights: Record<string, number>
  categoryCompatibility: string
  classification: (typeof classifications)[number]
  reviewStatus: (typeof reviewStatuses)[number]
  explanation: string[]
  indicators: string[]
  method: string
  modelVersion: string
  configVersion: string
  updatedAt: string
  reviewedAt: string | null
  lastCheckedAt: string
}
export interface ComparisonComplaint {
  incident?: Incident | null
  complaintId: string
  title: string
  description: string
  category: Category
  latitude: number
  longitude: number
  status: string
  createdAt: string
  incidentId: string | null
  images: { imageId: string; url: string }[]
}
export interface Processing {
  state: string
  report?: { incomplete: boolean; queryTruncated: boolean; compared: number }
  errorCategory?: string
}
export interface CandidateDetail extends Candidate {
  complaints: ComparisonComplaint[]
  processing: (Processing | null)[]
}
const root = '/admin/duplicate-candidates'
export const duplicateService = {
  list: (query: string) =>
    authRequest<{ items: Candidate[]; nextCursor: string | null }>(`${root}?${query}`),
  detail: (id: string) => authRequest<CandidateDetail>(`${root}/${encodeURIComponent(id)}`),
  review: (id: string, action: 'dismiss' | 'reviewed') =>
    authRequest<Candidate>(`${root}/${encodeURIComponent(id)}/${action}`, 'POST'),
  recheck: (id: string) =>
    authRequest<{ processing: Processing }>(
      `/admin/complaints/${encodeURIComponent(id)}/duplicate-check`,
      'POST',
    ),
}
