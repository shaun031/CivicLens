import { lazy, Suspense, useCallback, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useResource } from '../hooks/useResource'
import { Field, FormMessage } from '../components/common/FormParts'
import { Badge, Card, EmptyState, PageHeader, Select, Skeleton } from '../components/common/UI'
import { ErrorState } from '../components/common/ErrorState'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import { ComplaintImageGallery } from '../components/complaints/ComplaintComponents'
import { IncidentCorrectionDialog } from '../components/incidents/IncidentCorrectionDialog'
import { PriorityPanel } from '../components/incidents/PriorityPanel'
import { incidentService, type Incident } from '../services/incidentService'
import { categories } from '../types/complaint'
import { formatDate } from '../utils/dates'
const IncidentMap = lazy(() => import('../components/incidents/IncidentMap'))

export function IncidentsPage() {
  const [query, setQuery] = useState('status=OPEN&sort=newest')
  const [cursor, setCursor] = useState<string | null>(null)
  const loader = useCallback(
    () =>
      Promise.all([
        incidentService.list(query + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '')),
        incidentService.summary(),
      ]),
    [query, cursor],
  )
  const { data, loading, error, retry } = useResource(loader)
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const params = new URLSearchParams()
    for (const [key, value] of new FormData(event.currentTarget).entries())
      if (String(value)) params.set(key, String(value))
    setCursor(null)
    setQuery(params.toString())
  }
  return (
    <section className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <Link to="/admin/dashboard" className="text-teal-700">
        ← Administrator dashboard
      </Link>
      <PageHeader
        title="Master incidents"
        description="Private incident membership management. Reports and photos are preserved; complaint status, publication and priority remain separate."
      />
      <Card>
        <form onSubmit={filter} className="grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field
            id="incident-search"
            name="q"
            label="Search incidents"
            type="search"
            maxLength={150}
          />
          <Select id="incident-status" name="status" label="Incident status" defaultValue="OPEN">
            {['OPEN', 'RESOLVED', 'MERGED', 'SUPERSEDED'].map((status) => (
              <option key={status}>{status}</option>
            ))}
          </Select>
          <Select id="incident-category" name="category" label="Incident category">
            <option value="">All categories</option>
            {Object.entries(categories).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </Select>
          <Select id="incident-sort" name="sort" label="Incident sort">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </Select>
          <button className="action-link" type="submit">
            Apply incident filters
          </button>
          <button type="button" className="secondary-button" onClick={retry}>
            Refresh incidents
          </button>
        </form>
      </Card>
      {loading ? (
        <Skeleton />
      ) : error ? (
        <ErrorState message={error} onRetry={retry} />
      ) : (
        data && (
          <>
            <Card>
              <h2 className="mb-4 font-semibold">Stored incident analytics</h2>
              <dl className="grid gap-4 text-sm sm:grid-cols-3">
                {Object.entries(data[1])
                  .filter(([key]) =>
                    [
                      'activeIncidents',
                      'singleReportIncidents',
                      'multiReportIncidents',
                      'linkedComplaints',
                      'pendingClusteringReviews',
                      'splitOperations',
                      'correctionOperations',
                      'mergedIncidentRecords',
                    ].includes(key),
                  )
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replace(/([A-Z])/g, ' $1')}</dt>
                      <dd className="font-bold">{value ?? 'Unavailable in this provider'}</dd>
                    </div>
                  ))}
              </dl>
            </Card>
            {!data[0].items.length && (
              <EmptyState title="No incidents found">
                Background initialization may still be pending. Original reports remain saved.
                Adjust filters or refresh.
              </EmptyState>
            )}
            <div className="grid min-w-0 gap-5 lg:grid-cols-2">
              {data[0].items.map((incident) => (
                <Card key={incident.incidentId}>
                  <div className="mb-3 flex flex-wrap gap-2">
                    <Badge>{incident.status}</Badge>
                    {incident.reviewNeeded && <Badge>Review needed</Badge>}
                  </div>
                  <h2 className="font-semibold">
                    <Link to={`/admin/incidents/${incident.incidentId}`}>
                      {incident.canonicalTitle}
                    </Link>
                  </h2>
                  <p className="mt-2 break-all text-xs">{incident.incidentId}</p>
                  <p className="mt-3 text-sm">
                    {categories[incident.category]} · {incident.latitude.toFixed(5)},{' '}
                    {incident.longitude.toFixed(5)}
                  </p>
                  <p className="mt-2 text-sm">
                    {incident.totalComplaintCount} linked complaints ·{' '}
                    {incident.uniqueReporterCount} eligible unique reporters
                  </p>
                  <p className="mt-2 text-xs">
                    Created {formatDate(incident.createdAt)} · Last reported{' '}
                    {formatDate(incident.lastReportedAt)}
                  </p>
                  <Link
                    className="mt-4 inline-block font-semibold text-teal-700"
                    to={`/admin/incidents/${incident.incidentId}`}
                  >
                    View incident details
                  </Link>
                </Card>
              ))}
            </div>
            {data[0].nextCursor && (
              <button className="action-link" onClick={() => setCursor(data[0].nextCursor)}>
                Next incident page
              </button>
            )}
            {cursor && (
              <button className="secondary-button" onClick={() => setCursor(null)}>
                First incident page
              </button>
            )}
          </>
        )
      )}
    </section>
  )
}

type CorrectionKind = Parameters<typeof incidentService.correct>[0]
export function IncidentDetailsPage() {
  const { incidentId = '' } = useParams()
  return <IncidentDetailsContent key={incidentId} incidentId={incidentId} />
}
function IncidentDetailsContent({ incidentId }: { incidentId: string }) {
  const navigate = useNavigate()
  const loader = useCallback(
    () =>
      Promise.all([
        incidentService.detail(incidentId),
        incidentService.members(incidentId),
        incidentService.recommendations(incidentId),
      ]),
    [incidentId],
  )
  const { data, loading, error, retry } = useResource(loader)
  const [selected, setSelected] = useState<string[]>([])
  const [action, setAction] = useState<CorrectionKind | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [historyCursor, setHistoryCursor] = useState<string | null>(null)
  const historyLoader = useCallback(
    () => incidentService.history(incidentId, historyCursor ?? undefined),
    [incidentId, historyCursor],
  )
  const history = useResource(historyLoader)
  function saved(incident: Incident) {
    setAction(null)
    setSelected([])
    setNotice('Audited operation saved. Original reports and photos remain intact.')
    if (incident.incidentId !== incidentId) navigate(`/admin/incidents/${incident.incidentId}`)
    else {
      retry()
      history.retry()
    }
  }
  return (
    <section className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <Link className="text-teal-700" to="/admin/incidents">
        ← All master incidents
      </Link>
      <PageHeader
        title="Master incident details"
        description="Private membership, duplicate evidence, explainable priorities and audited corrections. Department assignment is not enabled."
      />
      <FormMessage success={notice} />
      {loading ? (
        <Skeleton />
      ) : error ? (
        <ErrorState message={error} onRetry={retry} />
      ) : (
        data && (
          <>
            <Card>
              <div className="mb-3 flex flex-wrap gap-2">
                <Badge>{data[0].status}</Badge>
                {data[0].reviewNeeded && <Badge>Review needed</Badge>}
              </div>
              <h2 className="text-xl font-semibold">{data[0].canonicalTitle}</h2>
              <p className="mt-3 whitespace-pre-wrap break-words text-sm">
                {data[0].canonicalDescription}
              </p>
              <dl className="detail-grid mt-5">
                <dt>Incident ID</dt>
                <dd className="break-all">{data[0].incidentId}</dd>
                <dt>Version</dt>
                <dd>{data[0].version}</dd>
                <dt>Linked complaints</dt>
                <dd>{data[0].totalComplaintCount}</dd>
                <dt>Eligible unique reporters</dt>
                <dd>{data[0].uniqueReporterCount}</dd>
                <dt>Category</dt>
                <dd>{categories[data[0].category]}</dd>
              </dl>
              {data[0].aliasChain && data[0].aliasChain.length > 1 && (
                <p className="mt-4 text-sm">
                  This historical incident redirects to the current master incident. Original-ID
                  history is retained below.
                </p>
              )}
            </Card>
            <ErrorBoundary>
              <Card>
                <h2 className="font-semibold">Clustering recommendations</h2>
                <p className="mt-2 text-sm">
                  Mode: {data[2].mode}. Recommendations are not actual memberships.
                </p>
                {data[2].processing.some((job) => job.state !== 'COMPLETE') && (
                  <p role="status" className="mt-3 text-sm text-amber-900">
                    Some clustering work is pending or retrying. Refresh after processing.
                  </p>
                )}
                {data[2].items.length === 0 && (
                  <p className="mt-3 text-sm">
                    No stored recommendations in this batch. This is not proof of non-duplication.
                  </p>
                )}
                <ul className="mt-3 space-y-3 text-sm">
                  {data[2].items.map((row) => (
                    <li key={`${row.sourceComplaintId}:${row.targetIncidentId}`}>
                      <p>{row.explanation}</p>
                      <Link
                        className="text-teal-700"
                        to={`/admin/duplicate-candidates/${row.candidateId}`}
                      >
                        Inspect duplicate evidence and review membership
                      </Link>
                    </li>
                  ))}
                </ul>
                {data[2].nextCursor && (
                  <p className="mt-3 text-sm">
                    More recommendations exist; use per-report duplicate review links below.
                  </p>
                )}
              </Card>
              <Suspense fallback={<Skeleton />}>
                <IncidentMap incident={data[0]} members={data[1].items} />
              </Suspense>
            </ErrorBoundary>
            <div className="flex flex-wrap gap-3">
              <button
                className="secondary-button"
                onClick={() => {
                  retry()
                  history.retry()
                }}
              >
                Refresh current membership
              </button>
              <button className="action-link" onClick={() => setAction('merge')}>
                Merge incidents
              </button>
              <button
                className="action-link"
                disabled={!selected.length}
                onClick={() => setAction('split')}
              >
                Split selected reports
              </button>
              <button
                className="action-link"
                disabled={selected.length !== 1}
                onClick={() => setAction('unlink-complaint')}
              >
                Unlink selected report
              </button>
              <button
                className="action-link"
                disabled={selected.length !== 1}
                onClick={() => setAction('link-complaint')}
              >
                Move selected to incident
              </button>
              <button className="action-link" onClick={() => setAction('recheck')}>
                Recheck clustering
              </button>
            </div>
            <ErrorBoundary>
              <PriorityPanel incidentId={data[0].incidentId} />
            </ErrorBoundary>
            <Link
              className="font-semibold text-teal-700"
              to={`/admin/assignments/${data[0].incidentId}`}
            >
              Manage department and officer assignment
            </Link>
            <h2 className="text-xl font-semibold">Current linked complaints</h2>
            <div className="grid min-w-0 gap-5 md:grid-cols-2">
              {data[1].items.map((member) => (
                <Card key={member.complaintId}>
                  <label className="flex gap-3 font-semibold">
                    <input
                      type="checkbox"
                      checked={selected.includes(member.complaintId)}
                      onChange={(event) =>
                        setSelected((previous) =>
                          event.target.checked
                            ? [...previous, member.complaintId]
                            : previous.filter((value) => value !== member.complaintId),
                        )
                      }
                    />
                    Select {member.title}
                  </label>
                  <p className="mt-3 whitespace-pre-wrap break-words text-sm">
                    {member.description}
                  </p>
                  <p className="my-3 text-xs">
                    {member.status} · {member.latitude}, {member.longitude} ·{' '}
                    {member.eligibleReporter
                      ? 'Eligible reporter'
                      : 'Excluded from independent support'}
                  </p>
                  <ComplaintImageGallery
                    images={member.images.map((image) => ({
                      ...image,
                      requiresAuth: true,
                      alt: `Private incident evidence for ${member.title}`,
                    }))}
                  />
                  <Link
                    className="mt-4 inline-block text-teal-700"
                    to={`/admin/duplicate-candidates?complaintId=${member.complaintId}`}
                  >
                    Review duplicate suggestions
                  </Link>
                </Card>
              ))}
            </div>
            <h2 className="text-xl font-semibold">Membership and merge history</h2>
            {history.loading ? (
              <Skeleton />
            ) : history.error ? (
              <ErrorState message={history.error} onRetry={history.retry} />
            ) : (
              <div className="space-y-4">
                {history.data?.items.map((entry) => (
                  <Card key={entry.eventId}>
                    <h3 className="font-semibold">{entry.operation.replaceAll('_', ' ')}</h3>
                    <p className="my-2 text-sm">{entry.reason}</p>
                    <p className="text-xs">
                      {formatDate(entry.createdAt, true)} · {entry.evidence.changes.length}{' '}
                      membership changes · Actor {entry.actorId}
                    </p>
                    <details className="mt-3 text-xs">
                      <summary className="cursor-pointer text-teal-700">
                        Inspect membership changes
                      </summary>
                      <ul className="mt-3 space-y-3">
                        {entry.evidence.changes.map((change) => (
                          <li key={change.complaint_id} className="break-all">
                            Report {change.complaint_id}:{' '}
                            {change.previous_incident_id ?? 'Unassigned'}
                            {' → '}
                            {change.new_incident_id}
                            {change.evidence && (
                              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all">
                                {JSON.stringify(change.evidence, null, 2)}
                              </pre>
                            )}
                          </li>
                        ))}
                      </ul>
                    </details>
                  </Card>
                ))}
              </div>
            )}
            {history.data?.nextCursor && (
              <button
                className="secondary-button"
                onClick={() => setHistoryCursor(history.data!.nextCursor)}
              >
                Next history page
              </button>
            )}
            {action && (
              <IncidentCorrectionDialog
                key={`${data[0].incidentId}:${data[0].version}:${action}`}
                kind={action}
                source={data[0]}
                selected={selected}
                onClose={() => setAction(null)}
                onSaved={saved}
              />
            )}
          </>
        )
      )}
    </section>
  )
}
