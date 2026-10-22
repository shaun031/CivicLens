import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { authRequest } from '../auth/authClient'
import { useResource } from '../hooks/useResource'
import { Alert, Badge, Card, EmptyState, PageHeader, Skeleton } from '../components/common/UI'
import { ErrorState } from '../components/common/ErrorState'
import { Button } from '../components/common/Button'
import { fieldClass } from '../components/common/FormParts'
import { categories } from '../types/complaint'
import type { Page, Recurrence } from '../services/civicIntelligenceService'
import { useCivicOperation } from '../hooks/useCivicOperation'

export function RecurrencesPage() {
  const { user } = useAuth()
  const [query, setQuery] = useState({ state: '', category: '', start: '', end: '' })
  const [after, setAfter] = useState('')
  const [selected, setSelected] = useState('')
  const [incident, setIncident] = useState('')
  const [reason, setReason] = useState('')
  const [physical, setPhysical] = useState(false)
  const operation = useCivicOperation()
  const params = new URLSearchParams(
    Object.entries({ ...query, after }).filter(([, value]) => value),
  ).toString()
  const load = useCallback(() => {
    if (!user?.id) return Promise.reject(new Error('Administrator session required'))
    return authRequest<Page<Recurrence>>(`/admin/recurrences?${params}`)
  }, [params, user?.id])
  const resource = useResource(load)
  const current = resource.data?.items.find((r) => r.recurrenceId === selected)
  function decide(action: string) {
    if (!current) return
    const body = {
      expectedVersion: current.version,
      reason,
      confirmed: true,
      physicalIdentityConfirmed: physical,
    }
    void operation.run(
      { action, body },
      (operationId) =>
        authRequest(`/admin/recurrences/${current.recurrenceId}/${action}`, 'POST', {
          ...body,
          operationId,
        }),
      resource.retry,
    )
  }
  return (
    <section className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      <PageHeader
        title="Recurring infrastructure failures"
        description="A duplicate is an ongoing unresolved issue; recurrence requires a later failure after a recorded verified repair. Nearby location alone does not establish physical identity."
      />
      <nav className="flex flex-wrap gap-5 text-teal-700">
        <Link to="/admin/dashboard">Administrator dashboard</Link>
        <Link to="/admin/repair-verification">Repair review</Link>
        <Link to="/admin/fairness">Geographic service indicators</Link>
      </nav>
      <Alert>
        Potential matches are not confirmed repeat failures. No incident is automatically merged, no
        asset ID is invented, and evidence scores are not calibrated probabilities.
      </Alert>
      <Card>
        <form
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault()
            resource.retry()
          }}
        >
          <label>
            Review state
            <select
              className={fieldClass}
              value={query.state}
              onChange={(e) => {
                setQuery({ ...query, state: e.target.value })
                setAfter('')
              }}
            >
              <option value="">All states</option>
              {[
                'POTENTIAL_RECURRENCE',
                'CONFIRMED_RECURRENCE',
                'DISMISSED',
                'INSUFFICIENT_EVIDENCE',
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            Category
            <select
              className={fieldClass}
              value={query.category}
              onChange={(e) => {
                setQuery({ ...query, category: e.target.value })
                setAfter('')
              }}
            >
              <option value="">All categories</option>
              {Object.entries(categories).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          {(['start', 'end'] as const).map((key) => (
            <label key={key}>
              {key === 'start' ? 'Review records from' : 'Review records through'}
              <input
                type="date"
                className={fieldClass}
                value={query[key]}
                onChange={(e) => {
                  setQuery({ ...query, [key]: e.target.value })
                  setAfter('')
                }}
              />
            </label>
          ))}
          <Button type="submit" variant="secondary">
            Refresh candidates
          </Button>
        </form>
      </Card>
      <Card>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            void operation.run(
              { incident },
              (operationId) =>
                authRequest(`/admin/incidents/${incident}/check-recurrence`, 'POST', {
                  operationId,
                }),
              resource.retry,
            )
          }}
        >
          <label>
            Canonical incident ID for bounded historical analysis
            <input
              required
              pattern="[0-9a-fA-F-]{36}"
              className={fieldClass}
              value={incident}
              onChange={(e) => setIncident(e.target.value)}
            />
          </label>
          <Button disabled={operation.busy} type="submit">
            Check recurrence
          </Button>
        </form>
      </Card>
      {resource.loading && <Skeleton />}
      {resource.error && <ErrorState message={resource.error} onRetry={resource.retry} />}
      {resource.data && (
        <>
          <p className="text-sm">
            This page:{' '}
            {resource.data.items.filter((r) => r.state === 'POTENTIAL_RECURRENCE').length}{' '}
            potential,{' '}
            {
              resource.data.items.filter(
                (r) => r.state === 'CONFIRMED_RECURRENCE' && !r.needsReassessment,
              ).length
            }{' '}
            valid confirmed relationships. Geographic counts use distinct recurring incidents in the
            service comparison dashboard.
          </p>
          {!resource.data.items.length && (
            <EmptyState title="No recurrence records in this selection" />
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {resource.data.items.map((row) => (
              <Card key={row.recurrenceId}>
                <Badge>{row.state}</Badge>
                <h2 className="my-3 font-semibold">{row.newTitle}</h2>
                <p className="text-sm">
                  Previous: {row.previousTitle} · {row.distanceMeters.toFixed(1)} metres ·{' '}
                  {row.daysSinceRepair.toFixed(1)} days after verified repair
                </p>
                {row.needsReassessment && (
                  <Alert>Canonical state changed. Reassessment required.</Alert>
                )}
                <Button
                  onClick={() => {
                    setSelected(row.recurrenceId)
                    setReason('')
                    setPhysical(false)
                  }}
                >
                  Compare recurrence evidence
                </Button>
              </Card>
            ))}
          </div>
          <div className="flex gap-3">
            {after && <Button onClick={() => setAfter('')}>First page</Button>}
            {resource.data.nextAfter && (
              <Button onClick={() => setAfter(resource.data!.nextAfter!)}>Next page</Button>
            )}
          </div>
        </>
      )}
      {current && (
        <Card className="space-y-4">
          <h2 className="text-xl font-semibold">Recurrence evidence comparison</h2>
          <div className="grid gap-5 md:grid-cols-2">
            <div>
              <h3 className="font-semibold">Previous incident</h3>
              <p>{current.previousTitle}</p>
              <p>Repair verified {new Date(current.previousRepairVerifiedAt).toLocaleString()}</p>
              <Link
                className="break-all text-teal-700"
                to={`/admin/incidents/${current.previousIncidentId}`}
              >
                {current.previousIncidentId}
              </Link>
            </div>
            <div>
              <h3 className="font-semibold">New occurrence</h3>
              <p>{current.newTitle}</p>
              <p>
                Reported {new Date(current.newReportedAt).toLocaleString()} ·{' '}
                {current.newIncidentStatus}
              </p>
              <Link
                className="break-all text-teal-700"
                to={`/admin/incidents/${current.newIncidentId}`}
              >
                {current.newIncidentId}
              </Link>
            </div>
          </div>
          <p>
            Evidence score {current.score.toFixed(3)} · {current.distanceMeters.toFixed(1)} m ·{' '}
            {current.daysSinceRepair.toFixed(1)} days
          </p>
          <dl className="grid grid-cols-2 gap-2">
            {Object.entries(current.explanation.signals).map(([key, value]) => (
              <div key={key}>
                <dt>{key} similarity/evidence</dt>
                <dd>{value.toFixed(3)}</dd>
              </div>
            ))}
          </dl>
          {current.explanation.limitations.map((text) => (
            <p key={text} className="text-sm">
              {text}
            </p>
          ))}
          {current.explanation.contradictions.map((text) => (
            <Alert key={text}>{text}</Alert>
          ))}
          <h3 className="font-semibold">Chronological infrastructure history</h3>
          <ol className="space-y-2">
            {current.timeline.map((entry, index) => (
              <li className="text-sm" key={index}>
                {new Date(entry.at).toLocaleString()} · {entry.kind} ·{' '}
                <span className="break-all">{entry.incidentId}</span>
              </li>
            ))}
          </ol>
          {current.reviewReason && <p>Previous decision: {current.reviewReason}</p>}
          <label className="block">
            Required review explanation
            <textarea
              minLength={10}
              maxLength={2000}
              className={fieldClass}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <label className="flex gap-2">
            <input
              type="checkbox"
              checked={physical}
              onChange={(e) => setPhysical(e.target.checked)}
            />
            I reviewed physical infrastructure identity beyond nearby coordinates and similar text.
          </label>
          <div className="flex flex-wrap gap-3">
            {['confirm', 'dismiss', 'request-review'].map((action) => (
              <Button
                key={action}
                disabled={
                  operation.busy ||
                  reason.trim().length < 10 ||
                  (action === 'confirm' && (!physical || current.needsReassessment))
                }
                onClick={() => decide(action)}
              >
                {action.replaceAll('-', ' ')} recurrence
              </Button>
            ))}
          </div>
        </Card>
      )}
      {operation.error && <p role="alert">{operation.error}</p>}
      {operation.message && <p role="status">{operation.message}</p>}
    </section>
  )
}
