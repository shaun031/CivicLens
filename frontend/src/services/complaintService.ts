import { ApiError, authRequest } from '../auth/authClient'
import { demoComplaints } from '../data/demoComplaints'
import { filterComplaints, type FilterValues } from '../utils/complaints'
import type {
  Complaint,
  ComplaintDraft,
  Category,
  ComplaintStatus,
  Severity,
  Publication,
} from '../types/complaint'

export interface ComplaintPage {
  items: Complaint[]
  nextCursor: string | null
  total?: number | null
}
export interface ComplaintSummary {
  total: number
  counts: Partial<Record<ComplaintStatus, number>>
  recent: Complaint[]
  byCategory?: { category: Category; count: number }[]
  submissionTrend?: { date: string; count: number }[]
  trendDays?: number
}
interface StoredComplaint {
  complaintId: string
  citizenId: string
  incidentId: string | null
  title: string
  description: string
  category: Category
  status: ComplaintStatus
  reportedSeverity: Severity
  latitude: number
  longitude: number
  landmark: string | null
  addressLabel: string | null
  createdAt: string
  updatedAt: string
  images: { imageId: string; contentType: string; fileSize: number; createdAt: string }[]
  publication?: Publication
}
function fromApi(item: StoredComplaint): Complaint {
  if (
    !item ||
    !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(item.complaintId) ||
    typeof item.title !== 'string' ||
    !Number.isFinite(item.latitude) ||
    !Number.isFinite(item.longitude) ||
    !Array.isArray(item.images)
  )
    throw new Error('The complaint API returned an invalid response. Please retry.')
  return {
    ...item,
    incidentId: item.incidentId ?? undefined,
    location: {
      latitude: item.latitude,
      longitude: item.longitude,
      addressLabel: item.addressLabel || item.landmark || 'Selected map location',
      landmark: item.landmark ?? undefined,
    },
    imageKeys: [],
    images: item.images.map((image) => ({
      url: `/complaints/${encodeURIComponent(item.complaintId)}/images/${encodeURIComponent(image.imageId)}`,
      alt: 'Submitted photo evidence',
      requiresAuth: true,
    })),
    progress: [
      {
        status: 'SUBMITTED',
        createdAt: item.createdAt,
        message: 'Complaint submitted. No subsequent status changes have been recorded.',
      },
    ],
    isSimulated: false,
  }
}
export const complaintService = {
  async list(demo: boolean, cursor?: string, filters?: FilterValues): Promise<ComplaintPage> {
    if (demo) {
      const items = filters
        ? filterComplaints(structuredClone(demoComplaints), filters)
        : structuredClone(demoComplaints)
      return { items, nextCursor: null, total: items.length }
    }
    const params = new URLSearchParams({ limit: '20' })
    if (cursor) params.set('cursor', cursor)
    if (filters) {
      for (const [key, value] of Object.entries({
        q: filters.search,
        category: filters.category,
        status: filters.status,
        reportedSeverity: filters.severity,
        dateFrom: filters.dateFrom,
        dateTo: filters.dateTo,
      }))
        if (value) params.set(key, value)
      params.set(
        'sortBy',
        ['category', 'status'].includes(filters.sort) ? filters.sort : 'createdAt',
      )
      params.set('sortOrder', filters.sort === 'newest' ? 'desc' : 'asc')
    }
    const page = await authRequest<{ items: StoredComplaint[]; nextCursor: string | null }>(
      `/complaints?${params}`,
    )
    if (!Array.isArray(page.items))
      throw new Error('The complaint API returned an invalid page. Please retry.')
    return { ...page, items: page.items.map(fromApi) }
  },
  async detail(id: string, demo: boolean): Promise<Complaint | null> {
    if (demo) return structuredClone(demoComplaints.find((item) => item.complaintId === id) ?? null)
    // Sample identifiers must never resolve into an unrelated real complaint.
    if (id.startsWith('sample-')) return null
    try {
      return fromApi(await authRequest<StoredComplaint>(`/complaints/${encodeURIComponent(id)}`))
    } catch (reason) {
      if (reason instanceof ApiError && [404, 422].includes(reason.status)) return null
      throw reason
    }
  },
  async summary(demo: boolean, days = 30): Promise<ComplaintSummary> {
    if (demo) {
      const counts: ComplaintSummary['counts'] = {}
      demoComplaints.forEach((item) => {
        counts[item.status] = (counts[item.status] ?? 0) + 1
      })
      return {
        total: demoComplaints.length,
        counts,
        recent: [...structuredClone(demoComplaints)]
          .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
          .slice(0, 3),
        byCategory: Object.keys(counts).length
          ? Object.entries(
              demoComplaints.reduce<Partial<Record<Category, number>>>(
                (result, item) => ({
                  ...result,
                  [item.category]: (result[item.category] ?? 0) + 1,
                }),
                {},
              ),
            ).map(([category, count]) => ({ category: category as Category, count }))
          : [],
        submissionTrend: [],
      }
    }
    const value = await authRequest<{
      total: number
      counts: ComplaintSummary['counts']
      recent: StoredComplaint[]
      byCategory?: ComplaintSummary['byCategory']
      submissionTrend?: ComplaintSummary['submissionTrend']
    }>(`/complaints/summary${days === 30 ? '' : `?days=${days}`}`)
    if (
      !Number.isInteger(value.total) ||
      value.total < 0 ||
      !value.counts ||
      !Array.isArray(value.recent) ||
      (value.byCategory !== undefined &&
        (!Array.isArray(value.byCategory) ||
          value.byCategory.some((row) => !row || !Number.isInteger(row.count) || row.count < 0))) ||
      (value.submissionTrend !== undefined &&
        (!Array.isArray(value.submissionTrend) ||
          value.submissionTrend.some(
            (row) =>
              !row || typeof row.date !== 'string' || !Number.isInteger(row.count) || row.count < 0,
          )))
    )
      throw new Error('The complaint API returned an invalid summary. Please retry.')
    return { ...value, recent: value.recent.map(fromApi) }
  },
  async nearby(demo: boolean): Promise<Complaint[]> {
    return demo ? structuredClone(demoComplaints) : []
  },
  async create(draft: ComplaintDraft): Promise<Complaint> {
    const data = new FormData()
    for (const key of [
      'title',
      'description',
      'category',
      'reportedSeverity',
      'latitude',
      'longitude',
      'addressLabel',
      'landmark',
    ] as const)
      data.append(key, draft[key])
    draft.files.forEach((file) => data.append('images', file))
    return fromApi(
      await authRequest<StoredComplaint>('/complaints', 'POST', data, {
        headers: { 'Idempotency-Key': draft.requestKey },
      }),
    )
  },
}
