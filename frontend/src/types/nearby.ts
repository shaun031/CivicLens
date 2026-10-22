import type { Category, ComplaintStatus } from './complaint'
export interface NearbyIssue {
  issueId: string
  title: string
  category: Category
  status: ComplaintStatus
  latitude: number
  longitude: number
  distanceMeters: number
  createdAt: string
  dateLabel: 'Reported' | 'Published'
  isOwn: boolean
  isPublic: boolean
  detailsUrl: string
}
export interface NearbyPage {
  items: NearbyIssue[]
  nextCursor: string | null
  countPolicy?: string
}
export interface NearbySearch {
  center: [number, number] | null
  radiusKm: number
}
