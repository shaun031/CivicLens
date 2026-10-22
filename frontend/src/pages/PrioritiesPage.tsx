import { useCallback, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useResource } from '../hooks/useResource'
import { priorityService } from '../services/priorityService'
import { categories } from '../types/complaint'
import {
  Card,
  Badge,
  PriorityBadge,
  EmptyState,
  PageHeader,
  Select,
  Skeleton,
} from '../components/common/UI'
import { Field } from '../components/common/FormParts'
import { ErrorState } from '../components/common/ErrorState'
import { formatDate } from '../utils/dates'

export function PrioritiesPage() {
  const [query, setQuery] = useState('status=OPEN&sort=priority')
  const [cursor, setCursor] = useState<string | null>(null)
  const loader = useCallback(
    () =>
      Promise.all([
        priorityService.list(query + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '')),
        priorityService.summary(),
      ]),
    [query, cursor],
  )
  const resource = useResource(loader)
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new URLSearchParams()
    for (const [key, value] of new FormData(event.currentTarget).entries())
      if (String(value)) values.set(key, String(value))
    setCursor(null)
    setQuery(values.toString())
  }
  return (
    <section className="mx-auto max-w-7xl space-y-6 px-4 py-10 sm:px-6">
      <Link to="/admin/dashboard" className="text-teal-700">
        ← Administrator dashboard
      </Link>
      <PageHeader
        title="Incident priority queue"
        description="Verified urgent hazards first, then effective urgency, unresolved time and stable incident ID. Provisional rubric—not an accident prediction or emergency dispatch service."
      />
      <Card>
        <form className="grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={filter}>
          <Field
            id="priority-search"
            name="q"
            label="Search priority incidents"
            type="search"
            maxLength={150}
          />
          <Select id="priority-band" name="band" label="Priority band">
            <option value="">All bands</option>
            {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </Select>
          <Select id="priority-category" name="category" label="Priority category">
            <option value="">All categories</option>
            {Object.entries(categories).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
          <Select id="priority-lifecycle" name="status" label="Priority incident status">
            <option>OPEN</option>
            <option>RESOLVED</option>
          </Select>
          <details className="col-span-full">
            <summary className="text-xs font-semibold text-teal-700">
              Advanced priority filters
            </summary>
            <div className="mt-4 grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Select
                id="priority-verification"
                name="assessmentStatus"
                label="Priority assessment status"
              >
                <option value="">All assessment states</option>
                {['PROVISIONAL', 'VERIFIED', 'NEEDS_REVIEW'].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </Select>
              <Select id="priority-hazard" name="urgent" label="Urgent hazard filter">
                <option value="">All incidents</option>
                <option value="true">Verified urgent hazards</option>
                <option value="false">Without verified urgent flag</option>
              </Select>
              <Select id="priority-override" name="overrideStatus" label="Priority override status">
                <option value="">All overrides</option>
                {['NONE', 'ACTIVE', 'EXPIRED', 'REMOVED', 'REVIEW_REQUIRED'].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </Select>
              <Select id="priority-sort" name="sort" label="Priority sorting">
                <option value="priority">Operational priority</option>
                <option value="oldest">Oldest first (urgent hazards first)</option>
              </Select>
              {(
                [
                  'minSeverity',
                  'maxSeverity',
                  'minImpact',
                  'maxImpact',
                  'minDays',
                  'maxDays',
                ] as const
              ).map((key) => (
                <Field
                  key={key}
                  id={`priority-${key}`}
                  name={key}
                  label={
                    {
                      minSeverity: 'Minimum severity',
                      maxSeverity: 'Maximum severity',
                      minImpact: 'Minimum public impact',
                      maxImpact: 'Maximum public impact',
                      minDays: 'Minimum unresolved days',
                      maxDays: 'Maximum unresolved days',
                    }[key]
                  }
                  type="number"
                  min={0}
                  max={key.endsWith('Days') ? 100000 : 10}
                  step="0.1"
                />
              ))}
            </div>
          </details>
          <button className="action-link" type="submit">
            Apply priority filters
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              setCursor(null)
              resource.retry()
            }}
          >
            Refresh ranked queue
          </button>
        </form>
      </Card>
      {resource.loading ? (
        <Skeleton />
      ) : resource.error ? (
        <ErrorState
          message={resource.error}
          onRetry={() => {
            setCursor(null)
            resource.retry()
          }}
        />
      ) : (
        resource.data && (
          <>
            <Card>
              <h2 className="mb-4 font-semibold">Current priority statistics</h2>
              <dl className="grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {Object.entries({
                  'Active incidents': resource.data[1].activeIncidents,
                  'Fresh scored incidents': resource.data[1].scoredIncidents,
                  'Pending or stale': resource.data[1].pendingOrStale,
                  'Needs assessment': resource.data[1].needsAssessment,
                  'Verified urgent hazards': resource.data[1].urgentHazards,
                  'Active overrides': resource.data[1].overridden,
                  ...resource.data[1].bands,
                }).map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-sm text-slate-600">{label}</dt>
                    <dd className="text-xl font-bold">{value ?? 'Unavailable'}</dd>
                  </div>
                ))}
              </dl>
              {resource.data[1].providerNote && (
                <p className="mt-4 text-sm">{resource.data[1].providerNote}</p>
              )}
              <p className="mt-4 text-sm text-slate-600">
                Uncalculated, stale and retired incidents are not presented as current ranked work.
                Queue changes invalidate continuation pages; refresh after a conflict.
              </p>
            </Card>
            {!resource.data[0].items.length ? (
              <EmptyState title="No fresh priorities match">
                Run the bounded local recalculation command or open an incident to
                assess/recalculate it. Pending incidents remain in master incident management.
              </EmptyState>
            ) : (
              <div className="grid gap-5 lg:grid-cols-2">
                {resource.data[0].items.map(({ incident, priority }) => (
                  <Card key={incident.incidentId}>
                    <div className="mb-3 flex flex-wrap gap-2">
                      <PriorityBadge band={priority.priorityBand} />
                      <Badge>{priority.assessmentStatus}</Badge>
                      {priority.urgentHazard && <Badge>VERIFIED URGENT HAZARD</Badge>}
                    </div>
                    <h2 className="text-lg font-semibold">
                      <Link to={`/admin/incidents/${incident.incidentId}`}>
                        {incident.canonicalTitle}
                      </Link>
                    </h2>
                    <p className="mt-2 break-all text-xs">{incident.incidentId}</p>
                    <p className="my-3 text-sm">
                      {categories[incident.category]} · {incident.latitude.toFixed(5)},{' '}
                      {incident.longitude.toFixed(5)}
                    </p>
                    <dl className="detail-grid text-sm">
                      <dt>Calculated score</dt>
                      <dd>{priority.calculatedScore}/100</dd>
                      <dt>Effective priority</dt>
                      <dd>{priority.effectiveScore}/100</dd>
                      <dt>Severity</dt>
                      <dd>
                        {priority.factors.severity.normalizedValue}/10 ·{' '}
                        {priority.factors.severity.status}
                      </dd>
                      <dt>Public impact</dt>
                      <dd>
                        {priority.factors.publicImpact.normalizedValue}/10 ·{' '}
                        {priority.factors.publicImpact.status}
                      </dd>
                      <dt>Eligible unique reporters</dt>
                      <dd>{priority.factors.reporters.rawValue}</dd>
                      <dt>Unresolved days</dt>
                      <dd>{priority.unresolvedDays}</dd>
                      <dt>Override</dt>
                      <dd>{priority.overrideStatus}</dd>
                    </dl>
                    <p className="mt-3 text-xs">
                      Calculated {formatDate(priority.calculatedAt, true)}
                    </p>
                    <Link
                      className="mt-4 inline-block font-semibold text-teal-700"
                      to={`/admin/incidents/${incident.incidentId}`}
                    >
                      View breakdown, assess and manage priority
                    </Link>
                  </Card>
                ))}
              </div>
            )}
            {resource.data[0].nextCursor && (
              <button
                className="action-link"
                onClick={() => setCursor(resource.data![0].nextCursor)}
              >
                Next priority page
              </button>
            )}
            {cursor && (
              <button className="secondary-button" onClick={() => setCursor(null)}>
                First priority page
              </button>
            )}
          </>
        )
      )}
      <Link to="/admin/incidents" className="inline-block text-teal-700">
        Manage all master incidents, including pending scores
      </Link>
    </section>
  )
}
