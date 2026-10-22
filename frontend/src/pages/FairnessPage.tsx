import { lazy, Suspense, useCallback, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { authRequest } from '../auth/authClient'
import { useResource } from '../hooks/useResource'
import { analyticsService } from '../services/analyticsService'
import { AnalyticsFilterBar } from '../components/analytics/AnalyticsFilterBar'
import { AnalyticsChart } from '../components/analytics/AnalyticsComponents'
import { Alert, Card, PageHeader, Skeleton } from '../components/common/UI'
import { Button } from '../components/common/Button'
import { ErrorState } from '../components/common/ErrorState'
import { fieldClass } from '../components/common/FormParts'
import type {
  FairnessArea,
  FairnessResult,
  FairnessReviewRecord,
  Page,
} from '../services/civicIntelligenceService'
import type { FairnessMeasure } from '../components/analytics/FairnessMap'
import { useCivicOperation } from '../hooks/useCivicOperation'

const FairnessMap = lazy(() => import('../components/analytics/FairnessMap'))
const measures: FairnessMeasure[] = [
  'medianWorkStartHours',
  'overdueRate',
  'activeIncidents',
  'verifiedResolutionRate',
  'confirmedRecurrenceIncidents',
]
function value(area: FairnessArea, key: FairnessMeasure) {
  const n = area[key]
  return n === null
    ? 'Unavailable'
    : key.endsWith('Rate')
      ? `${(n * 100).toFixed(1)}%`
      : n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}
export function FairnessPage() {
  const { user } = useAuth()
  const [query, setQuery] = useSearchParams()
  const key = query.toString()
  const load = useCallback(() => {
    if (!user?.id) return Promise.reject(new Error('Administrator session required'))
    return authRequest<FairnessResult>(`/admin/analytics/fairness?${key}`)
  }, [key, user?.id])
  const configLoad = useCallback(() => {
    if (!user?.id) return Promise.reject(new Error('Administrator session required'))
    return analyticsService.config()
  }, [user?.id])
  const reviewLoad = useCallback(() => {
    if (!user?.id) return Promise.reject(new Error('Administrator session required'))
    return authRequest<Page<FairnessReviewRecord>>('/admin/analytics/fairness/reviews')
  }, [user?.id])
  const resource = useResource(load),
    config = useResource(configLoad),
    reviews = useResource(reviewLoad)
  const [measure, setMeasure] = useState<FairnessMeasure>('medianWorkStartHours')
  const [selected, setSelected] = useState<string[]>([])
  const [areaId, setAreaId] = useState('')
  const [notes, setNotes] = useState('')
  const operation = useCivicOperation()
  const compared = resource.data?.areas.filter((a) => selected.includes(a.areaId)) ?? []
  return (
    <section className="mx-auto max-w-7xl space-y-6 px-4 py-8">
      <PageHeader
        title="Geographic service comparison"
        description="Private, unadjusted operational indicators for administrative investigation. Differences do not prove discrimination, negligence or infrastructure quality."
      />
      <nav className="flex flex-wrap gap-5 text-teal-700">
        <Link to="/admin/dashboard">Administrator dashboard</Link>
        <Link to="/admin/recurrences">Recurrence review</Link>
        <Link to="/admin/repair-verification">Repair review</Link>
        <Link to="/admin/reports">Authorized CSV reports</Link>
      </nav>
      <AnalyticsFilterBar
        query={query}
        onApply={setQuery}
        config={config.data}
        geographic
        geographicDefaults={false}
      />
      {config.error && <ErrorState message={config.error} onRetry={config.retry} />}
      {resource.loading && <Skeleton />}
      {resource.error && <ErrorState message={resource.error} onRetry={resource.retry} />}
      {resource.data && (
        <>
          <Card className="space-y-3">
            <p>
              {resource.data.grouping} · {resource.data.normalization} · minimum{' '}
              {resource.data.minimumSampleSize} observations per compared metric
            </p>
            <p className="text-sm">
              Period {resource.data.window.startInclusive} through{' '}
              {resource.data.window.endExclusive} (exclusive); reporting zone{' '}
              {resource.data.reportingTimezone}. Calculated {resource.data.calculatedAt}.
            </p>
            {resource.data.limitations.map((text) => (
              <p className="text-sm" key={text}>
                {text}
              </p>
            ))}
          </Card>
          <label className="block">
            Map metric
            <select
              className={fieldClass}
              value={measure}
              onChange={(e) => setMeasure(e.target.value as FairnessMeasure)}
            >
              {measures.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
          <Suspense fallback={<Skeleton />}>
            <FairnessMap
              areas={resource.data.areas}
              measure={measure}
              serviceAreas={config.data?.serviceAreas}
            />
          </Suspense>
          {!resource.data.areas.length && (
            <Alert>
              No recorded incidents in this selection; this does not establish good service.
              Unoccupied cells have no observations.
            </Alert>
          )}
          <div
            role="region"
            aria-label="Area service indicators"
            tabIndex={0}
            className="overflow-x-auto rounded-xl border bg-white"
          >
            <table className="w-full min-w-[900px] text-left text-sm">
              <caption className="p-3 text-left">
                Select two areas for side-by-side descriptive comparison; do not rank unsupported
                small samples.
              </caption>
              <thead>
                <tr>
                  {[
                    'Compare',
                    'Grid area',
                    'Incidents',
                    'Work-start median (hours)',
                    'Work-start observations / missing',
                    'Overdue rate (known active SLA)',
                    'Verified resolution rate (cohort)',
                    'Confirmed recurring incidents',
                    'Review signal',
                  ].map((h) => (
                    <th className="p-3" key={h}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {resource.data.areas.map((area) => (
                  <tr className="border-t" key={area.areaId}>
                    <td className="p-3">
                      <input
                        type="checkbox"
                        aria-label={`Compare area ${area.cell}`}
                        checked={selected.includes(area.areaId)}
                        disabled={selected.length >= 2 && !selected.includes(area.areaId)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, area.areaId]
                              : selected.filter((id) => id !== area.areaId),
                          )
                        }
                      />
                    </td>
                    <th scope="row" className="p-3">
                      {area.cell}
                    </th>
                    <td className="p-3">{area.incidentCount}</td>
                    <td className="p-3">{value(area, 'medianWorkStartHours')}</td>
                    <td className="p-3">
                      {area.responseObservations} / {area.missingWorkStart}
                    </td>
                    <td className="p-3">
                      {value(area, 'overdueRate')} (n={area.slaObservations})
                    </td>
                    <td className="p-3">
                      {value(area, 'verifiedResolutionRate')} (n={area.incidentCount})
                    </td>
                    <td className="p-3">
                      {area.confirmedRecurrenceIncidents} confirmed;{' '}
                      {area.potentialRecurrenceIncidents} potential
                    </td>
                    <td className="p-3">
                      {area.status}
                      <p>{area.flags.join('; ')}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {compared.length === 2 && (
            <Card>
              <h2 className="text-xl font-semibold">Side-by-side area comparison</h2>
              <AnalyticsChart
                title={`Recorded ${measure} comparison — not a fairness ranking`}
                rows={compared
                  .filter((area) => area[measure] !== null)
                  .map((area) => ({
                    label: `${area.cell} (n=${area.incidentCount})`,
                    count: (area[measure] ?? 0) * (measure.endsWith('Rate') ? 100 : 1),
                  }))}
                measure={
                  measure.endsWith('Rate')
                    ? 'Percent'
                    : measure === 'medianWorkStartHours'
                      ? 'Hours'
                      : 'Incidents'
                }
              />
              <div className="mt-4 grid gap-5 md:grid-cols-2">
                {compared.map((area) => (
                  <div key={area.areaId}>
                    <h3 className="font-semibold">
                      Cell {area.cell} · n={area.incidentCount}
                    </h3>
                    {!area.dataSufficient && (
                      <Alert>Insufficient comparison data. Do not infer service fairness.</Alert>
                    )}
                    {measures.map((m) => (
                      <p key={m} className="my-2 text-sm">
                        {m}: {value(area, m)}
                      </p>
                    ))}
                    <p className="text-sm">Priority mix: {JSON.stringify(area.priorityMix)}</p>
                    <p className="text-sm break-all">
                      Department coverage: {JSON.stringify(area.departmentMix)}
                    </p>
                    <p className="text-sm">
                      Other-cell comparison observations: {area.comparisonObservations}; missing SLA{' '}
                      {area.missingSla}
                    </p>
                    <Link
                      className="text-teal-700"
                      to={`/admin/analytics/incidents?${new URLSearchParams({ ...Object.fromEntries(query), south: String(area.south), west: String(area.west), north: String(area.north), east: String(area.east) })}`}
                    >
                      Authorized incident list
                    </Link>
                  </div>
                ))}
              </div>
            </Card>
          )}
          <details>
            <summary>Metric definitions and denominator policies</summary>
            {Object.entries(resource.data.definitions).map(([name, text]) => (
              <p className="my-2 text-sm" key={name}>
                <strong>{name}:</strong> {text}
              </p>
            ))}
          </details>
          <Card>
            <h2 className="mb-4 font-semibold">Administrative service review record</h2>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                const body = {
                  expectedVersion: 0,
                  areaId,
                  notes,
                  state: 'UNDER_ADMIN_REVIEW',
                  context: Object.fromEntries(query),
                }
                void operation.run(
                  body,
                  (operationId) =>
                    authRequest('/admin/analytics/fairness/reviews', 'POST', {
                      ...body,
                      operationId,
                    }),
                  reviews.retry,
                )
              }}
            >
              <label className="block">
                Observed grid area
                <select
                  required
                  className={fieldClass}
                  value={areaId}
                  onChange={(e) => setAreaId(e.target.value)}
                >
                  <option value="">Select an area</option>
                  {resource.data.areas.map((a) => (
                    <option key={a.areaId} value={a.areaId}>
                      {a.cell} · {a.status}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                Investigation notes
                <textarea
                  required
                  minLength={10}
                  maxLength={2000}
                  className={fieldClass}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </label>
              <Button type="submit" disabled={operation.busy}>
                Record administrative review
              </Button>
            </form>
          </Card>
        </>
      )}
      {reviews.loading && <Skeleton />}
      {reviews.error && <ErrorState message={reviews.error} onRetry={reviews.retry} />}
      {reviews.data?.items.map((review) => (
        <Card key={review.review_id}>
          <h2 className="font-semibold">
            {review.area_id} · {review.state}
          </h2>
          <p>{review.notes}</p>
          {review.state !== 'REVIEWED' && (
            <Button
              disabled={operation.busy}
              onClick={() => {
                const body = {
                  areaId: review.area_id,
                  context: review.context,
                  notes: review.notes,
                  state: 'REVIEWED',
                  expectedVersion: review.version,
                }
                void operation.run(
                  body,
                  (operationId) =>
                    authRequest(`/admin/analytics/fairness/reviews/${review.review_id}`, 'PATCH', {
                      ...body,
                      operationId,
                    }),
                  reviews.retry,
                )
              }}
            >
              Mark investigation reviewed
            </Button>
          )}
        </Card>
      ))}
      {reviews.data?.nextAfter && (
        <p className="text-sm">
          Showing the first 25 review records. Further records are available through the paginated
          authorized reviews API.
        </p>
      )}
      {operation.error && <p role="alert">{operation.error}</p>}
      {operation.message && <p role="status">{operation.message}</p>}
    </section>
  )
}
