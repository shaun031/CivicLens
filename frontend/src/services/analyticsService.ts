import { authRequest } from '../auth/authClient'

export type AnalyticsView =
  | 'overview'
  | 'complaint-trends'
  | 'incidents'
  | 'priorities'
  | 'departments'
  | 'officers'
  | 'sla'
  | 'backlog'
  | 'hotspots'
  | 'response-times'
export type AnalyticsRow = Record<string, unknown>
export interface ChartRow {
  label: string
  count: number
}
export interface HotspotCell {
  cell: string
  south: number
  west: number
  north: number
  east: number
  incidentCount: number
  reportCount: number
  activeIncidents: number
  criticalIncidents: number
  overdueIncidents: number
  averageCalculatedScore: number | null
}
export interface AnalyticsResult extends AnalyticsRow {
  calculatedAt: string
  reportingTimezone: string
  scope: string
  window: { startInclusive: string; endExclusive: string }
  dataFreshness: {
    mode: string
    sourceRevision: number
    projectionVersion: number
    stalePriorityCount: number
    stale: boolean
    projectionCalculatedAt?: string | null
  }
  limitations: string[]
  items?: AnalyticsRow[]
  nextCursor?: string | null
  cells?: HotspotCell[]
  series?: { date: string; count: number }[]
  creationTrend?: { date: string; count: number }[]
  complaintTrend?: { date: string; count: number }[]
  incidentTrend?: { date: string; count: number }[]
  byCategory?: ChartRow[]
  bySeverity?: ChartRow[]
  byStatus?: ChartRow[]
  distribution?: ChartRow[]
  priorityDistribution?: ChartRow[]
  categoryDistribution?: ChartRow[]
  departmentOverview?: ChartRow[]
  aging?: ChartRow[]
  overlappingSubgroups?: ChartRow[]
  byDepartment?: ChartRow[]
  byPriority?: ChartRow[]
  overdueByDepartment?: ChartRow[]
  overdueByPriority?: ChartRow[]
  urgentQueue?: AnalyticsRow[]
  recentActivity?: AnalyticsRow[]
  geographicPreview?: HotspotCell[]
}
export interface AnalyticsConfig {
  reports: { type: string; view: string }[]
  reportingTimezone: string
  scope: string
  serviceAreas: Record<string, [number, number, number, number]>
  departments: { id: string; name: string; active: number }[]
}
export interface ReportPreview {
  title: string
  reportType: string
  generatedAt: string
  reportingTimezone: string
  columns: string[]
  rows: AnalyticsRow[]
  sampleSize: number
  definitions: string
  pageOnly: boolean
  nextCursor: string | null
  dataFreshness: AnalyticsResult['dataFreshness']
  filters?: Record<string, unknown>
  window?: { startInclusive: string; endExclusive: string }
}
export function analyticsQuery(filters: URLSearchParams) {
  return filters.toString()
}
export const analyticsService = {
  config: () => authRequest<AnalyticsConfig>('/admin/analytics/reports'),
  view: (view: AnalyticsView, filters: URLSearchParams) =>
    authRequest<AnalyticsResult>(`/admin/analytics/${view}?${analyticsQuery(filters)}`),
  preview: (kind: string, filters: URLSearchParams) =>
    authRequest<ReportPreview>(
      `/admin/analytics/reports/${encodeURIComponent(kind)}?${analyticsQuery(filters)}`,
    ),
  export: (kind: string, filters: URLSearchParams) =>
    authRequest<Blob>(
      `/admin/analytics/reports/${encodeURIComponent(kind)}/csv?${analyticsQuery(filters)}`,
      'POST',
      undefined,
      { responseType: 'blob', headers: { Accept: 'text/csv' } },
    ),
}
