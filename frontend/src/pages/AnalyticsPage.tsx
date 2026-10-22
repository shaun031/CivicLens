import { lazy, Suspense, useCallback, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useResource } from '../hooks/useResource'
import { analyticsService } from '../services/analyticsService'
import type { AnalyticsView, ChartRow } from '../services/analyticsService'
import { AnalyticsFilterBar } from '../components/analytics/AnalyticsFilterBar'
import {
  AnalyticsChart,
  AnalyticsStats,
  AnalyticsTable,
  DataFreshnessIndicator,
} from '../components/analytics/AnalyticsComponents'
import { valueLabel } from '../services/analyticsFormatting'
import { Alert, Card, PageHeader, Skeleton } from '../components/common/UI'
import { Button } from '../components/common/Button'

const HotspotMap = lazy(() => import('../components/analytics/HotspotMap'))
const pages: Record<AnalyticsView, string> = {
  overview: 'Municipal Command Center',
  'complaint-trends': 'Complaint submission trends',
  incidents: 'Canonical incident analytics',
  priorities: 'Priority distribution',
  departments: 'Department performance context',
  officers: 'Officer workload analytics',
  sla: 'SLA and escalation analytics',
  backlog: 'Active incident backlog',
  hotspots: 'Geographic concentrations',
  'response-times': 'Recorded response and resolution times',
}
const analyticsLinks = [
  ['Repair verification', '/admin/repair-verification'],
  ['Recurrences', '/admin/recurrences'],
  ['Service comparison', '/admin/fairness'],
  ['Command Center', '/admin/command-center'],
  ['Incidents', '/admin/analytics/incidents'],
  ['Priority analytics', '/admin/analytics/priorities'],
  ['Departments', '/admin/analytics/departments'],
  ['Officer workloads', '/admin/analytics/officers'],
  ['Hotspots', '/admin/hotspots'],
  ['SLA & backlog', '/admin/analytics/sla'],
  ['Reports', '/admin/reports'],
  ['Workflow monitoring', '/admin/workflows'],
] as const

export function AnalyticsNavigation() {
  return (
    <details className="related-navigation">
      <summary>Explore analytics & review tools</summary>
      <nav
        aria-label="Municipal analytics"
        className="mb-6 flex flex-wrap gap-x-5 gap-y-3 text-sm font-semibold text-teal-700"
      >
        {analyticsLinks.map(([label, path]) => (
          <Link key={path} to={path}>
            {label}
          </Link>
        ))}
      </nav>
    </details>
  )
}
const defaults = { south: '12.9', west: '77.5', north: '13', east: '77.7' }
export function AnalyticsPage({ view = 'overview' }: { view?: AnalyticsView }) {
  const { user } = useAuth()
  const [query, setQuery] = useSearchParams()
  const key = query.toString()
  const loader = useCallback(() => {
    if (!user?.id) return Promise.reject(new Error('Administrator session required.'))
    const filters = new URLSearchParams(key)
    if (view === 'hotspots' && !filters.has('south'))
      Object.entries(defaults).forEach(([k, v]) => filters.set(k, v))
    return analyticsService.view(view, filters)
  }, [key, view, user?.id])
  const configLoader = useCallback(() => {
    if (!user?.id) return Promise.reject(new Error('Administrator session required.'))
    return analyticsService.config()
  }, [user?.id])
  const config = useResource(configLoader)
  const result = useResource(loader)
  const [measure, setMeasure] = useState<
    'incidentCount' | 'reportCount' | 'criticalIncidents' | 'overdueIncidents'
  >('incidentCount')
  const [viewport, setViewport] = useState<number[] | null>(null)
  const [compared, setCompared] = useState<string[]>([])
  const data = result.data
  const trend = (rows?: { date: string; count: number }[]): ChartRow[] =>
    rows?.map((r) => ({ label: r.date, count: r.count })) ?? []
  const drill = (field: string, value: string) => {
    const params = new URLSearchParams(key)
    params.delete('cursor')
    params.set(field, value)
    return `/admin/analytics/incidents?${params}`
  }
  function next() {
    const params = new URLSearchParams(key)
    if (data?.nextCursor) params.set('cursor', data.nextCursor)
    setQuery(params)
  }
  const bounds = ['south', 'west', 'north', 'east'].map((k) =>
    Number(query.get(k) ?? defaults[k as keyof typeof defaults]),
  )
  return (
    <section className="mx-auto max-w-7xl space-y-6 px-4 py-9 sm:px-6">
      <Link className="text-sm font-semibold text-teal-700" to="/admin/dashboard">
        Administrator dashboard
      </Link>
      <PageHeader
        title={pages[view]}
        description="A focused view of active incidents, priorities, and team workload. Filters apply to recorded creation-date cohorts."
      />
      <AnalyticsNavigation />
      <AnalyticsFilterBar
        key={`${view}:${key}`}
        query={query}
        config={config.data}
        geographic={view === 'hotspots'}
        officers={view === 'officers'}
        onApply={setQuery}
      />
      {config.error && <Alert>Filter configuration unavailable: {config.error}</Alert>}
      <div className="flex flex-wrap gap-4">
        <Button variant="secondary" onClick={result.retry}>
          Refresh analytics
        </Button>
        <Link
          className="self-center text-teal-700 underline"
          to="/admin/analytics/complaint-trends"
        >
          Submission trends
        </Link>
        <Link className="self-center text-teal-700 underline" to="/admin/analytics/backlog">
          Backlog
        </Link>
        <Link className="self-center text-teal-700 underline" to="/admin/analytics/response-times">
          Response times
        </Link>
      </div>
      {result.loading && <Skeleton />}
      {result.error && (
        <div role="alert">
          <Alert>{result.error} No sample metrics are substituted.</Alert>
        </div>
      )}
      {data && (
        <>
          <DataFreshnessIndicator data={data} />
          {view === 'overview' && (
            <>
              <AnalyticsStats
                data={data}
                fields={[
                  ['activeIncidents', 'Active incidents'],
                  ['criticalIncidents', 'Current critical incidents'],
                  ['overdueIncidents', 'Currently overdue incidents'],
                  ['unassignedIncidents', 'Unassigned incidents'],
                ]}
              />
              <div className="grid min-w-0 gap-5 xl:grid-cols-3">
                <AnalyticsChart
                  title="Canonical incident creation"
                  rows={trend(data.incidentTrend)}
                  line
                />
                <AnalyticsChart
                  title="Current active priority distribution"
                  rows={data.priorityDistribution}
                />
                <AnalyticsChart title="Department active work" rows={data.departmentOverview} />
              </div>
              <details className="analytics-disclosure">
                <summary>
                  <span>Additional operational context</span>
                </summary>
                <div className="mt-5 space-y-5">
                  <AnalyticsStats
                    data={data}
                    fields={[
                      ['totalComplaints', 'Eligible complaint reports'],
                      ['totalIncidents', 'Canonical master incidents'],
                    ]}
                  />
                  <div className="grid min-w-0 gap-5 lg:grid-cols-2">
                    <AnalyticsChart
                      title="Canonical incidents by category"
                      rows={data.categoryDistribution}
                    />
                    <AnalyticsChart
                      title="Complaint submissions"
                      rows={trend(data.complaintTrend)}
                      measure="Reports"
                      line
                    />
                  </div>
                </div>
              </details>
              <Card>
                <h2 className="mb-3 font-semibold">Chart drill-down</h2>
                <p className="mb-3 text-sm">
                  Links retain the selected scope and require administrator authorization.
                </p>
                <div className="flex flex-wrap gap-4">
                  {data.categoryDistribution?.map((r) => (
                    <Link
                      className="text-teal-700 underline"
                      key={r.label}
                      to={drill('category', r.label)}
                    >
                      {r.label}: {r.count}
                    </Link>
                  ))}
                  {data.priorityDistribution?.map((r) => (
                    <Link
                      className="text-teal-700 underline"
                      key={r.label}
                      to={drill('priority', r.label)}
                    >
                      {r.label}: {r.count}
                    </Link>
                  ))}
                </div>
              </Card>
              <AnalyticsTable
                title="Urgent incident queue"
                rows={data.urgentQueue ?? []}
                columns={[
                  ['incidentId', 'Incident'],
                  ['category', 'Category'],
                  ['priority', 'Effective band'],
                  ['urgentHazard', 'Verified hazard'],
                  ['reportCount', 'Reports'],
                  ['overdue', 'Overdue'],
                ]}
              />
              <AnalyticsChart
                title="Geographic preview: top 10 incident cells"
                rows={data.geographicPreview?.map((c) => ({
                  label: c.cell,
                  count: c.incidentCount,
                }))}
              />
              <AnalyticsTable
                title="Recent recorded operations"
                rows={data.recentActivity ?? []}
                columns={[
                  ['incidentId', 'Incident'],
                  ['kind', 'Recorded event'],
                  ['at', 'UTC timestamp'],
                ]}
              />
            </>
          )}
          {view === 'complaint-trends' && (
            <>
              <AnalyticsStats
                data={data}
                fields={[
                  ['total', 'Eligible submissions'],
                  ['linkedCurrent', 'Currently linked reports'],
                  ['historicalExistingVsNew', 'Historical existing/new linkage'],
                ]}
              />
              <div className="grid gap-5 lg:grid-cols-2">
                <AnalyticsChart
                  title="Complaint submission trend"
                  rows={trend(data.series)}
                  measure="Reports"
                  line
                />
                <AnalyticsChart
                  title="Reports by category"
                  rows={data.byCategory}
                  measure="Reports"
                />
                <AnalyticsChart
                  title="Reported severity (not assessed priority)"
                  rows={data.bySeverity}
                  measure="Reports"
                />
              </div>
              <p>{valueLabel(data.historicalLinkReason)}</p>
            </>
          )}
          {view === 'incidents' && (
            <>
              <AnalyticsStats
                data={data}
                fields={[
                  ['total', 'Canonical incidents'],
                  ['singleReport', 'Single-report incidents'],
                  ['multiReport', 'Multi-report incidents'],
                  ['averageReports', 'Mean eligible reports per incident'],
                  ['uniqueReporters', 'Distinct eligible reporters'],
                  ['resolved', 'Valid recorded resolution transitions'],
                ]}
              />
              <div className="grid gap-5 lg:grid-cols-2">
                <AnalyticsChart title="Incident category distribution" rows={data.byCategory} />
                <AnalyticsChart title="Recorded lifecycle states" rows={data.byStatus} />
                <AnalyticsChart
                  title="Incident creation trend"
                  rows={trend(data.creationTrend)}
                  line
                />
              </div>
              <AnalyticsTable
                title="Filtered canonical incidents"
                rows={data.items ?? []}
                columns={[
                  ['incidentId', 'Incident'],
                  ['category', 'Category'],
                  ['priority', 'Current priority'],
                  ['reportCount', 'Eligible reports'],
                  ['uniqueReporters', 'Unique reporters'],
                  ['assignmentStatus', 'Assignment'],
                  ['overdue', 'Overdue'],
                ]}
              />
            </>
          )}
          {view === 'priorities' && (
            <>
              <AnalyticsStats
                data={data}
                fields={[
                  ['verifiedUrgentHazards', 'Fresh verified hazards'],
                  ['requiringAssessment', 'Requires assessment or refresh'],
                  ['provisional', 'Provisional assessments'],
                  ['meanCalculatedScore', 'Mean calculated score (not effective override)'],
                  ['medianCalculatedScore', 'Median calculated score'],
                  ['sampleSize', 'Fresh score sample'],
                ]}
              />
              <AnalyticsChart
                title="Active authoritative priority bands"
                rows={data.distribution}
              />
              <AnalyticsTable
                title="Priority by category"
                rows={
                  (data.byCategoryPriorities as import('../services/analyticsService').AnalyticsRow[]) ??
                  []
                }
                columns={[
                  ['label', 'Category'],
                  ['priorities', 'Band counts'],
                ]}
              />
              <AnalyticsTable
                title="Actual recorded priority events (last 100)"
                rows={
                  (data.historicalPriorityTrend as import('../services/analyticsService').AnalyticsRow[]) ??
                  []
                }
                columns={[
                  ['at', 'UTC time'],
                  ['kind', 'Event'],
                  ['priority', 'Recorded band'],
                ]}
              />
            </>
          )}
          {view === 'departments' && (
            <>
              <Alert>
                Responsibilities, severity, staffing, coverage and missing records differ. These
                metrics are operational context, not an objective department ranking. Unallocated
                active incidents: {valueLabel(data.unallocatedActiveIncidents)}.
              </Alert>
              <Card>
                <h2 className="font-semibold">Compare departments</h2>
                <div className="mt-3 flex flex-wrap gap-4">
                  {data.items?.map((row) => (
                    <label
                      key={String(row.departmentId)}
                      className="flex items-center gap-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={compared.includes(String(row.departmentId))}
                        onChange={(event) =>
                          setCompared((previous) =>
                            event.target.checked
                              ? [...previous, String(row.departmentId)]
                              : previous.filter((id) => id !== row.departmentId),
                          )
                        }
                      />
                      {String(row.name)}
                    </label>
                  ))}
                </div>
              </Card>
              <div className="grid gap-5 lg:grid-cols-2">
                {data.items
                  ?.filter((row) => !compared.length || compared.includes(String(row.departmentId)))
                  .map((row) => (
                    <Card key={String(row.departmentId)}>
                      <h2 className="font-semibold">{String(row.name)}</h2>
                      <p className="my-3 text-sm">
                        Response: {valueLabel(row.response)}. Response compliance:{' '}
                        {valueLabel(row.responseCompliance)}
                      </p>
                      <Link
                        className="text-teal-700 underline"
                        to={drill('department', String(row.departmentId))}
                      >
                        Inspect this department’s incidents
                      </Link>
                      <AnalyticsChart
                        title={`${String(row.name)} priorities`}
                        rows={row.priorities as ChartRow[]}
                      />
                      <AnalyticsChart
                        title={`${String(row.name)} recorded operations`}
                        rows={(
                          row.recordedOperationsTrend as
                            { date: string; count: number }[] | undefined
                        )?.map((r) => ({ label: r.date, count: r.count }))}
                        measure="Recorded events"
                        line
                      />
                    </Card>
                  ))}
              </div>
              <AnalyticsChart
                title="Department weighted active workload"
                rows={data.items?.map((r) => ({
                  label: String(r.name),
                  count: Number(r.workloadUnits),
                }))}
                measure="Weighted units"
              />
              <AnalyticsTable
                title="Department operations"
                rows={data.items ?? []}
                columns={[
                  ['name', 'Department'],
                  ['activeIncidents', 'Active incidents'],
                  ['assignedIncidents', 'Officer assigned'],
                  ['awaitingOfficer', 'Awaiting officer'],
                  ['inProgress', 'In progress'],
                  ['overdue', 'Overdue'],
                  ['workloadUnits', 'Weighted units'],
                  ['recordedWorkMilestones', 'Recorded 100% work milestones (not resolution)'],
                  ['availableOfficers', 'Available officers'],
                ]}
              />
              <Link className="text-teal-700 underline" to="/admin/departments">
                Existing department and officer configuration
              </Link>
            </>
          )}
          {view === 'officers' && (
            <>
              <Alert>
                Workload is not verified productivity or a disciplinary score. Unknown capacity is
                not configured; no utilization is invented. Global workload includes active
                assignments outside the selected creation-date cohort. Multiple membership rows for
                one officer are not additive.
              </Alert>
              <AnalyticsChart
                title="Global officer weighted workload by membership"
                rows={data.items?.map((r) => ({
                  label: `${String(r.displayName)} · ${String(r.departmentId).slice(0, 8)}`,
                  count: Number(r.weightedWorkload),
                }))}
                measure="Weighted units"
              />
              <AnalyticsTable
                title="Officer workloads and capacity"
                rows={data.items ?? []}
                columns={[
                  ['displayName', 'Officer'],
                  ['departmentId', 'Department'],
                  ['availability', 'Availability'],
                  ['assignedActiveIncidents', 'Selected active incidents'],
                  ['weightedWorkload', 'Global workload'],
                  ['globalPendingPriorities', 'Global stale priorities'],
                  ['selectedWorkload', 'Selected workload'],
                  ['capacity', 'Capacity (unavailable = not configured)'],
                  ['utilization', 'Global load / capacity'],
                  ['highPriority', 'Selected high/critical assignments'],
                  ['overdue', 'Selected overdue'],
                  ['recordedWorkMilestones', 'Recorded work milestones (not resolution)'],
                ]}
              />
              <AnalyticsChart
                title="Membership availability on this page"
                measure="Memberships"
                rows={Object.entries(
                  (data.items ?? []).reduce<Record<string, number>>((counts, row) => {
                    const label = String(row.availability)
                    counts[label] = (counts[label] ?? 0) + 1
                    return counts
                  }, {}),
                ).map(([label, count]) => ({ label, count }))}
              />
              <details>
                <summary className="cursor-pointer font-semibold">
                  Recorded officer assignment trends
                </summary>
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  {data.items?.map((row) => (
                    <AnalyticsChart
                      key={String(row.membershipId)}
                      title={`${String(row.displayName)} · ${String(row.departmentId).slice(0, 8)} assignment events`}
                      measure="Recorded events"
                      line
                      rows={(
                        row.assignmentTrend as { date: string; count: number }[] | undefined
                      )?.map((r) => ({ label: r.date, count: r.count }))}
                    />
                  ))}
                </div>
              </details>
              <Link className="text-teal-700 underline" to="/admin/departments">
                Manage existing trusted memberships
              </Link>
            </>
          )}
          {view === 'sla' && (
            <>
              <Alert>
                Demonstration operational targets, not legal deadlines. Pending and unavailable
                outcomes are shown separately; the compliance denominator is measurable MET + MISSED
                incident outcomes, never complaint submissions.
              </Alert>
              <AnalyticsStats
                data={data}
                fields={[
                  ['overdueIncidents', 'Distinct currently overdue incidents'],
                  ['approachingDeadline', 'Approaching within 24 hours'],
                  ['escalationCount', 'Recorded alerts in selected period'],
                  ['distinctEscalatedIncidents', 'Distinct incidents escalated'],
                  ['acknowledged', 'Acknowledged alerts'],
                  ['unacknowledged', 'Unacknowledged alerts'],
                ]}
              />
              <Card>
                <h2 className="font-semibold">Measured compliance</h2>
                <p className="mt-3">Response: {valueLabel(data.responseCompliance)}</p>
                <p className="mt-3">Recorded resolution: {valueLabel(data.resolutionCompliance)}</p>
              </Card>
              <div className="grid gap-5 lg:grid-cols-2">
                <AnalyticsChart
                  title="Current overdue by department"
                  rows={data.overdueByDepartment}
                />
                <AnalyticsChart title="Current overdue by priority" rows={data.overdueByPriority} />
              </div>
              <Link className="text-teal-700 underline" to="/admin/workflows">
                Existing SLA policies, acknowledgements and workflow operations
              </Link>
            </>
          )}
          {view === 'backlog' && (
            <>
              <AnalyticsStats data={data} fields={[['totalBacklog', 'Unique active backlog']]} />
              <Alert>
                Subgroups overlap; never sum them to obtain total backlog. “Awaiting officer” means
                a department exists but no officer is assigned, not a proven availability shortage.
                Historical backlog is unavailable without point-in-time source records.
              </Alert>
              <div className="grid gap-5 lg:grid-cols-2">
                <AnalyticsChart
                  title="Overlapping backlog subgroups"
                  rows={data.overlappingSubgroups}
                />
                <AnalyticsChart title="Backlog aging in current open cycle" rows={data.aging} />
                <AnalyticsChart title="Backlog by department" rows={data.byDepartment} />
                <AnalyticsChart title="Backlog by current priority" rows={data.byPriority} />
              </div>
            </>
          )}
          {view === 'response-times' && (
            <>
              <AnalyticsStats
                data={data}
                fields={[
                  ['firstAssignment', 'Current-cycle first valid assignment'],
                  ['workStart', 'Current-cycle first recorded work start'],
                  ['recordedResolution', 'Valid recorded resolution transitions'],
                ]}
              />
              <Alert>
                {valueLabel(data.resolutionReason)}. Statistics report sample size, mean, median,
                minimum and maximum where available. No working hours or completion times are
                inferred.
              </Alert>
            </>
          )}
          {view === 'hotspots' && (
            <>
              <Alert>
                ADMIN-only location aggregation. Initial example viewport is not the configured
                municipal boundary. Change the bounds to your service area. Incident counts and
                report volume are distinct layers; no citizen identities, photographs or report
                descriptions are returned.
              </Alert>
              <label className="block text-sm font-semibold">
                Map measure
                <select
                  className="ml-3 rounded-lg border border-slate-300 p-2"
                  value={measure}
                  onChange={(e) => setMeasure(e.target.value as typeof measure)}
                >
                  <option value="incidentCount">Canonical incidents</option>
                  <option value="reportCount">Complaint-report volume</option>
                  <option value="criticalIncidents">Current critical incidents</option>
                  <option value="overdueIncidents">Current overdue incidents</option>
                </select>
              </label>
              <Card>
                <Suspense fallback={<Skeleton />}>
                  <HotspotMap
                    cells={data.cells ?? []}
                    bounds={bounds}
                    measure={measure}
                    onBounds={setViewport}
                  />
                </Suspense>
              </Card>
              <Button
                variant="secondary"
                disabled={!viewport}
                onClick={() => {
                  if (viewport) {
                    const next = new URLSearchParams(key)
                    ;['south', 'west', 'north', 'east'].forEach((k, i) =>
                      next.set(k, viewport[i].toFixed(6)),
                    )
                    next.delete('cursor')
                    setQuery(next)
                  }
                }}
              >
                Apply current map viewport
              </Button>
              <AnalyticsTable
                title="Accessible occupied-cell list"
                rows={
                  (data.cells ??
                    []) as unknown as import('../services/analyticsService').AnalyticsRow[]
                }
                columns={[
                  ['cell', 'Grid cell'],
                  ['incidentCount', 'Canonical incidents'],
                  ['reportCount', 'Eligible reports'],
                  ['activeIncidents', 'Active'],
                  ['criticalIncidents', 'Critical'],
                  ['overdueIncidents', 'Overdue'],
                  ['averageCalculatedScore', 'Mean fresh score'],
                ]}
              />
            </>
          )}
          {(data.nextCursor || query.has('cursor')) && (
            <div className="flex gap-4">
              <Button
                variant="secondary"
                onClick={() => {
                  const next = new URLSearchParams(key)
                  next.delete('cursor')
                  setQuery(next)
                }}
              >
                First page
              </Button>
              <Button disabled={!data.nextCursor} onClick={next}>
                Next analytics page
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
