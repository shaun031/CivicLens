export const categories = {
  POTHOLE: 'Pothole',
  DAMAGED_ROAD: 'Damaged road',
  BROKEN_STREETLIGHT: 'Broken streetlight',
  GARBAGE: 'Garbage accumulation',
  DRAINAGE: 'Drainage blockage',
  PUBLIC_PROPERTY_DAMAGE: 'Public infrastructure damage',
  OTHER: 'Other',
} as const
export type Category = keyof typeof categories
export const statuses = {
  SUBMITTED: 'Submitted',
  UNDER_REVIEW: 'Under Review',
  ASSIGNED: 'Assigned',
  IN_PROGRESS: 'In Progress',
  RESOLVED: 'Resolved',
  REJECTED: 'Rejected',
} as const
export type ComplaintStatus = keyof typeof statuses
export type Severity = 'LOW' | 'MEDIUM' | 'HIGH'
export interface IssueLocation {
  latitude: number
  longitude: number
  addressLabel: string
  landmark?: string
}
export interface ProgressEvent {
  status: ComplaintStatus
  createdAt: string
  message: string
}
export interface EvidenceImage {
  url: string
  alt: string
  requiresAuth?: boolean
}
export interface Complaint {
  complaintId: string
  citizenId: string
  incidentId?: string
  title: string
  description: string
  category: Category
  status: ComplaintStatus
  location: IssueLocation
  imageKeys: string[]
  images: EvidenceImage[]
  reportedSeverity: Severity
  createdAt: string
  updatedAt: string
  progress: ProgressEvent[]
  isSimulated: boolean
  publication?: Publication
}
export interface Publication {
  citizenRequestedPublication: boolean
  publicationStatus: 'PRIVATE' | 'PENDING_REVIEW' | 'PUBLISHED' | 'REJECTED'
  publicIssueId: string | null
  publicSummary?: string | null
  publicLatitude?: number | null
  publicLongitude?: number | null
  publishedAt?: string | null
}
export interface PublicIssue {
  publicIssueId: string
  category: Category
  status: ComplaintStatus
  summary: string
  latitude: number
  longitude: number
  publishedAt: string
  distanceMeters?: number
}
export interface MapBounds {
  minLatitude: number
  maxLatitude: number
  minLongitude: number
  maxLongitude: number
}
export interface ComplaintDraft {
  requestKey: string
  category: Category | ''
  title: string
  description: string
  addressLabel: string
  landmark: string
  latitude: string
  longitude: string
  reportedSeverity: Severity
  files: File[]
}
export const emptyDraft = (): ComplaintDraft => ({
  requestKey: crypto.randomUUID(),
  category: '',
  title: '',
  description: '',
  addressLabel: '',
  landmark: '',
  latitude: '',
  longitude: '',
  reportedSeverity: 'MEDIUM',
  files: [],
})
