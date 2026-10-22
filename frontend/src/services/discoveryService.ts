import { authRequest } from '../auth/authClient'
import type { MapBounds, Publication, PublicIssue } from '../types/complaint'
import { categories, statuses } from '../types/complaint'
import type { NearbyPage } from '../types/nearby'
import { validCoordinates } from '../utils/validation'

export interface PublicPage {
  items: PublicIssue[]
  nextCursor: string | null
}
function publicIssue(value: PublicIssue): PublicIssue {
  if (
    !value ||
    typeof value.publicIssueId !== 'string' ||
    typeof value.summary !== 'string' ||
    !Object.hasOwn(categories, value.category) ||
    !Object.hasOwn(statuses, value.status) ||
    !Number.isFinite(value.latitude) ||
    !Number.isFinite(value.longitude) ||
    typeof value.publishedAt !== 'string'
  )
    throw new Error('The public issue API returned invalid data. Please retry.')
  return {
    publicIssueId: value.publicIssueId,
    summary: value.summary,
    category: value.category,
    status: value.status,
    latitude: value.latitude,
    longitude: value.longitude,
    publishedAt: value.publishedAt,
    ...(typeof value.distanceMeters === 'number' && Number.isFinite(value.distanceMeters)
      ? { distanceMeters: value.distanceMeters }
      : {}),
  }
}
function publicPage(value: PublicPage): PublicPage {
  if (
    !value ||
    !Array.isArray(value.items) ||
    value.items.length > 100 ||
    (value.nextCursor != null && typeof value.nextCursor !== 'string')
  )
    throw new Error('The public issue API returned an invalid page. Please retry.')
  return { items: value.items.map(publicIssue), nextCursor: value.nextCursor ?? null }
}
export interface PublicFilters {
  category?: string
  status?: string
  cursor?: string
}
function query(values: object) {
  const result = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== '') result.set(key, String(value))
  })
  return result.toString()
}
export const discoveryService = {
  async visibleNearby(
    latitude: number,
    longitude: number,
    radiusKm: number,
    filters: PublicFilters = {},
  ): Promise<NearbyPage> {
    const value = await authRequest<NearbyPage>(
      `/citizen/issues/nearby?${query({ latitude, longitude, radiusKm, ...filters, limit: 50 })}`,
    )
    if (
      !value ||
      !Array.isArray(value.items) ||
      value.items.length > 100 ||
      (value.nextCursor != null && typeof value.nextCursor !== 'string') ||
      value.items.some(
        (item) =>
          !item ||
          typeof item.issueId !== 'string' ||
          typeof item.title !== 'string' ||
          !Object.hasOwn(categories, item.category) ||
          !Object.hasOwn(statuses, item.status) ||
          !Number.isFinite(item.latitude) ||
          !Number.isFinite(item.longitude) ||
          !validCoordinates(String(item.latitude), String(item.longitude)) ||
          !Number.isFinite(item.distanceMeters) ||
          item.distanceMeters < 0 ||
          typeof item.isOwn !== 'boolean' ||
          typeof item.isPublic !== 'boolean' ||
          (!item.isOwn && !item.isPublic) ||
          typeof item.createdAt !== 'string' ||
          !['Reported', 'Published'].includes(item.dateLabel) ||
          item.detailsUrl !==
            `${item.isOwn ? '/citizen/complaints/' : '/issues/'}${encodeURIComponent(item.issueId)}`,
      )
    )
      throw new Error('The nearby issue API returned an invalid page. Please retry.')
    return {
      items: value.items,
      nextCursor: value.nextCursor ?? null,
      countPolicy: value.countPolicy,
    }
  },
  async latestLocation(): Promise<[number, number] | null> {
    const value = await authRequest<{ location: { latitude: number; longitude: number } | null }>(
      '/citizen/issues/latest-location',
    )
    if (value?.location === null) return null
    if (
      !value?.location ||
      !validCoordinates(String(value.location.latitude), String(value.location.longitude))
    )
      throw new Error('The latest complaint location is unavailable.')
    return [value.location.latitude, value.location.longitude]
  },
  bounds: (bounds: MapBounds, filters: PublicFilters = {}) =>
    authRequest<PublicPage>(`/public/issues?${query({ ...bounds, ...filters, limit: 50 })}`).then(
      publicPage,
    ),
  nearby: (
    latitude: number,
    longitude: number,
    radiusMeters: number,
    filters: PublicFilters = {},
  ) =>
    authRequest<PublicPage>(
      `/public/issues/nearby?${query({ latitude, longitude, radiusMeters, ...filters, limit: 50 })}`,
    ).then(publicPage),
  detail: (publicId: string) =>
    authRequest<PublicIssue>(`/public/issues/${encodeURIComponent(publicId)}`).then(publicIssue),
  requestPublication: (complaintId: string, requested: boolean) =>
    authRequest<Publication>(
      `/complaints/${encodeURIComponent(complaintId)}/publication-request`,
      'PATCH',
      { requested },
    ),
  reviewPublication: (
    complaintId: string,
    data: {
      decision: 'APPROVE' | 'REJECT' | 'UNPUBLISH'
      publicSummary?: string
      publicLatitude?: number
      publicLongitude?: number
      reviewedForPrivacy?: boolean
    },
  ) =>
    authRequest<Publication>(
      `/admin/complaints/${encodeURIComponent(complaintId)}/publication`,
      'PATCH',
      data,
    ),
}
