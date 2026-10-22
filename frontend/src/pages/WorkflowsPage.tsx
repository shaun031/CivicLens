import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { workflowService, type Policy } from '../services/workflowService'
import { useResource } from '../hooks/useResource'
import { Badge, EmptyState, PageHeader, Skeleton } from '../components/common/UI'
import { ErrorState } from '../components/common/ErrorState'
import { Modal } from '../components/common/Modal'
import { formatDate } from '../utils/dates'

interface Operation {
  path: string
  title: string
  method?: string
  extra?: object
}
function Control({
  operation,
  close,
  done,
}: {
  operation: Operation
  close: () => void
  done: () => void
}) {
  const [reason, setReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [frozen, setFrozen] = useState<object | null>(null)
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const body = frozen ?? {
      operationId: crypto.randomUUID(),
      confirmed,
      reason,
      ...operation.extra,
    }
    setFrozen(body)
    try {
      await workflowService.control(operation.path, body, operation.method)
      done()
      close()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Control action failed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal
      title={operation.title}
      onClose={() => {
        if (!busy) close()
      }}
    >
      <p className="mb-4 text-sm text-slate-600">
        Only eligible failed work is replayed. Completed stages and notification receipts remain
        preserved. Three redrives maximum.
      </p>
      <form onSubmit={(event) => void submit(event)} className="space-y-4">
        <label className="block">
          Reason
          <textarea
            className="mt-2 w-full rounded-lg border p-2"
            required
            minLength={10}
            maxLength={1000}
            value={reason}
            disabled={busy || Boolean(frozen)}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            required
            checked={confirmed}
            disabled={busy || Boolean(frozen)}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          I confirm this administrative action.
        </label>
        {error && (
          <p role="alert" className="text-red-700">
            {error} Close and refresh if the underlying record changed.
          </p>
        )}
        <button className="action-link" disabled={busy || !confirmed || reason.trim().length < 10}>
          {busy ? 'Processing…' : frozen ? 'Retry same request' : 'Confirm action'}
        </button>
      </form>
    </Modal>
  )
}

function PolicyEditor({
  policy,
  onConfirm,
}: {
  policy: Policy
  onConfirm: (value: Operation) => void
}) {
  const [response, setResponse] = useState(policy.response_hours)
  const [resolution, setResolution] = useState(policy.resolution_hours)
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onConfirm({
          path: `/admin/sla/policies/${policy.policy_id}`,
          method: 'PUT',
          title: 'Change demonstration SLA targets?',
          extra: {
            expectedVersion: policy.version,
            priorityBand: policy.priority_band,
            category: policy.category,
            departmentId: policy.department_id,
            urgent: Boolean(policy.urgent),
            responseHours: response,
            resolutionHours: resolution,
          },
        })
      }}
      className="grid items-end gap-3 rounded-xl border p-4 sm:grid-cols-4"
    >
      <p>
        {policy.priority_band}
        <span className="block text-xs text-slate-500">
          Policy {policy.policy_id} · v{policy.version}
        </span>
      </p>
      <label>
        Response hours
        <input
          type="number"
          min="0.01"
          max="8760"
          step="0.01"
          required
          className="mt-1 w-full rounded border p-2"
          value={response}
          onChange={(event) => setResponse(Number(event.target.value))}
        />
      </label>
      <label>
        Resolution hours
        <input
          type="number"
          min={response}
          max="17520"
          step="0.01"
          required
          className="mt-1 w-full rounded border p-2"
          value={resolution}
          onChange={(event) => setResolution(Number(event.target.value))}
        />
      </label>
      <button className="font-semibold text-teal-700">Review policy change</button>
    </form>
  )
}

export function WorkflowsPage() {
  const { workflowId } = useParams()
  const [status, setStatus] = useState('')
  const [cursor, setCursor] = useState('')
  const [deadCursor, setDeadCursor] = useState('')
  const [slaCursor, setSlaCursor] = useState('')
  const [operation, setOperation] = useState<Operation | null>(null)
  const loader = useCallback(async () => {
    const [summary, workflows, dead, escalations, policies, detail] = await Promise.all([
      workflowService.summary(),
      workflowService.list({ status, cursor, workflowType: 'IncidentTriageWorkflow' }),
      workflowService.dead(deadCursor),
      workflowService.escalations(slaCursor),
      workflowService.policies(),
      workflowId ? workflowService.detail(workflowId) : Promise.resolve(null),
    ])
    return { summary, workflows, dead, escalations, policies, detail }
  }, [status, cursor, deadCursor, slaCursor, workflowId])
  const { data, loading, error, retry } = useResource(loader)
  return (
    <section className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <Link className="text-teal-700" to="/admin/dashboard">
        ← Administrator dashboard
      </Link>
      <PageHeader
        title="Workflow operations"
        description="Durable triage, retries, private notifications and demonstration SLA alerts. Review outcomes are valid; no automatic merge, resolution approval or severity override is implied."
      />
      <div className="flex flex-wrap items-end gap-5">
        <label>
          Status
          <select
            className="ml-3 rounded border p-2"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value)
              setCursor('')
            }}
          >
            <option value="">All statuses</option>
            {[
              'PENDING',
              'RUNNING',
              'WAITING_RETRY',
              'COMPLETED',
              'COMPLETED_WITH_REVIEW_REQUIRED',
              'FAILED',
              'CANCELLED',
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <button className="font-semibold text-teal-700" onClick={retry}>
          Refresh operations
        </button>
        <Link className="text-teal-700" to="/notifications">
          My private notifications
        </Link>
      </div>
      {loading ? (
        <Skeleton />
      ) : error ? (
        <ErrorState title="Workflow monitoring unavailable" message={error} onRetry={retry} />
      ) : (
        data && (
          <>
            {data.summary.sampled && (
              <p role="status">
                Bounded cloud sample; global queue counts are unavailable here. Use basic AWS
                service metrics.
              </p>
            )}
            <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {Object.entries({
                'Pending events': data.summary.pendingEvents,
                'Pending workflows': data.summary.workflows.PENDING ?? 0,
                'Running workflows': data.summary.workflows.RUNNING ?? 0,
                'Review outcomes': data.summary.workflows.COMPLETED_WITH_REVIEW_REQUIRED ?? 0,
                'Average processing seconds':
                  data.summary.averageProcessingSeconds === null
                    ? null
                    : Number(data.summary.averageProcessingSeconds.toFixed(2)),
                'Completed workflows':
                  (data.summary.workflows.COMPLETED ?? 0) +
                  (data.summary.workflows.COMPLETED_WITH_REVIEW_REQUIRED ?? 0),
                'Failed workflows': data.summary.workflows.FAILED ?? 0,
                'Pending retries':
                  data.summary.queue.RETRY ?? data.summary.workflows.WAITING_RETRY ?? 0,
                'Dead letters': data.summary.sampled ? null : (data.summary.queue.DEAD ?? 0),
                'Open SLA alerts': data.summary.openEscalations,
              }).map(([label, value]) => (
                <div className="rounded-xl border bg-white p-4" key={label}>
                  <dt className="text-sm text-slate-600">{label}</dt>
                  <dd className="mt-2 text-2xl font-bold">{value ?? 'Unavailable'}</dd>
                </div>
              ))}
            </dl>
            {data.detail && (
              <article className="space-y-3 rounded-xl border bg-white p-5">
                <h2 className="text-xl font-bold">Workflow details</h2>
                <p className="break-all">{data.detail.workflow_id}</p>
                <Badge>{data.detail.status}</Badge>
                <p>
                  Step: {data.detail.current_step ?? 'Not started'} · Attempts:{' '}
                  {data.detail.attempt_count}
                </p>
                <p>
                  Started:{' '}
                  {data.detail.started_at ? formatDate(data.detail.started_at, true) : 'Pending'} ·
                  Updated: {formatDate(data.detail.updated_at, true)}
                </p>
                <p>
                  Observed elapsed:{' '}
                  {data.detail.started_at
                    ? Math.max(
                        0,
                        (new Date(data.detail.completed_at ?? data.detail.updated_at).getTime() -
                          new Date(data.detail.started_at).getTime()) /
                          1000,
                      ).toFixed(2) + ' seconds'
                    : 'Not started'}
                </p>
                <p className="break-all">
                  Complaint: {data.detail.aggregate_id} · Correlation: {data.detail.correlation_id}
                </p>
                {data.detail.error_category && (
                  <p role="alert">
                    {data.detail.error_category}: check configuration and the safe processing
                    history before retrying.
                  </p>
                )}
                {data.detail.incident_id && (
                  <Link
                    className="block text-teal-700"
                    to={`/admin/incidents/${data.detail.incident_id}`}
                  >
                    View canonical incident
                  </Link>
                )}
                <ol className="space-y-2">
                  {data.detail.steps?.map((step) => (
                    <li className="rounded border p-3" key={step.step}>
                      <strong>{step.step}</strong> · {step.status} · Attempts:{' '}
                      {step.attempts ?? 'Unavailable'}
                      <p className="text-sm">
                        {step.result.reviewRequired
                          ? 'Administrative review required'
                          : step.result.skipped
                            ? `Skipped: ${String(step.result.skipped)}`
                            : 'Stage result persisted'}
                      </p>
                    </li>
                  ))}
                </ol>
                {['FAILED', 'WAITING_RETRY'].includes(data.detail.status) && (
                  <button
                    className="text-teal-700"
                    onClick={() =>
                      setOperation({
                        title: 'Retry eligible workflow?',
                        path: `/admin/workflows/${data.detail?.workflow_id}/retry`,
                      })
                    }
                  >
                    Retry workflow
                  </button>
                )}
              </article>
            )}
            <section className="space-y-3">
              <h2 className="text-xl font-bold">Recent triage activity</h2>
              {data.workflows.items.length ? (
                data.workflows.items.map((workflow) => (
                  <article
                    className="flex flex-wrap justify-between gap-3 rounded-xl border bg-white p-4"
                    key={workflow.workflow_id}
                  >
                    <div className="min-w-0">
                      <Link
                        className="break-all font-semibold text-teal-700"
                        to={`/admin/workflows/${workflow.workflow_id}`}
                      >
                        {workflow.workflow_type} · {workflow.aggregate_id}
                      </Link>
                      <p className="mt-2 text-sm">
                        {workflow.current_step ?? 'Pending'} ·{' '}
                        {formatDate(workflow.updated_at, true)} · Attempt {workflow.attempt_count}
                      </p>
                    </div>
                    <Badge>{workflow.status}</Badge>
                  </article>
                ))
              ) : (
                <EmptyState title="No workflows">
                  No stored triage executions match this page.
                </EmptyState>
              )}
              {data.workflows.nextCursor && (
                <button
                  className="text-teal-700"
                  onClick={() => setCursor(data.workflows.nextCursor ?? '')}
                >
                  Older workflows
                </button>
              )}
              {cursor && (
                <button className="ml-4 text-teal-700" onClick={() => setCursor('')}>
                  Newest workflows
                </button>
              )}
            </section>
            <section className="space-y-3">
              <h2 className="text-xl font-bold">Dead-letter inspection</h2>
              {data.dead.items.length ? (
                data.dead.items.map((message) => (
                  <article
                    className="space-y-2 rounded-xl border bg-white p-4"
                    key={message.message_id}
                  >
                    <p className="break-all font-semibold">Message {message.message_id}</p>
                    <p className="break-all text-sm">
                      Event {message.event_id} · {message.consumer} · Attempts {message.attempts} ·
                      Redrives {message.redrives}/3
                    </p>
                    <p>{message.error_category}</p>
                    <p className="text-sm">
                      Only safe metadata is shown. Invalid events need source repair; payload
                      editing is not permitted.
                    </p>
                    <div className="flex flex-wrap gap-5">
                      <button
                        className="text-teal-700"
                        disabled={
                          message.redrives >= 3 ||
                          message.error_category === 'PERMANENT_EVENT_ERROR' ||
                          message.error_category === 'INVALID_EVENT'
                        }
                        onClick={() =>
                          setOperation({
                            title: 'Redrive eligible dead letter?',
                            path: `/admin/workflows/dead-letters/${message.message_id}/redrive`,
                          })
                        }
                      >
                        Redrive message
                      </button>
                      <button
                        className="text-teal-700"
                        disabled={Boolean(message.acknowledged_at)}
                        onClick={() =>
                          setOperation({
                            title: 'Acknowledge dead letter?',
                            path: `/admin/workflows/dead-letters/${message.message_id}/acknowledge`,
                          })
                        }
                      >
                        {message.acknowledged_at ? 'Acknowledged' : 'Acknowledge failure'}
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <p>No dead-letter messages.</p>
              )}
              {data.dead.nextCursor && (
                <button
                  className="text-teal-700"
                  onClick={() => setDeadCursor(data.dead.nextCursor ?? '')}
                >
                  More dead letters
                </button>
              )}
            </section>
            <section className="space-y-3">
              <h2 className="text-xl font-bold">Demonstration SLA escalations</h2>
              <p className="text-sm text-slate-600">
                These are configurable operational targets, not legally mandated deadlines.
                Resolution is monitored only from existing canonical lifecycle data.
              </p>
              {data.escalations.items.length ? (
                data.escalations.items.map((alert) => (
                  <article
                    className="space-y-2 rounded-xl border bg-white p-4"
                    key={alert.escalation_id}
                  >
                    <Badge>{alert.status === 'OPEN' ? 'OVERDUE' : 'ACKNOWLEDGED'}</Badge>
                    <p>
                      {alert.milestone} target · {formatDate(alert.deadline, true)}
                    </p>
                    <Link
                      className="block break-all text-teal-700"
                      to={`/admin/incidents/${alert.incident_id}`}
                    >
                      Incident {alert.incident_id}
                    </Link>
                    {alert.status === 'OPEN' && (
                      <button
                        className="text-teal-700"
                        onClick={() =>
                          setOperation({
                            title: 'Acknowledge SLA alert?',
                            path: `/admin/sla/escalations/${alert.escalation_id}/acknowledge`,
                          })
                        }
                      >
                        Acknowledge SLA alert
                      </button>
                    )}
                  </article>
                ))
              ) : (
                <p>No stored SLA escalations.</p>
              )}
              {data.escalations.nextCursor && (
                <button
                  className="text-teal-700"
                  onClick={() => setSlaCursor(data.escalations.nextCursor ?? '')}
                >
                  More SLA alerts
                </button>
              )}
            </section>
            <section className="space-y-3">
              <h2 className="text-xl font-bold">SLA target configuration</h2>
              {data.policies.items.map((policy) => (
                <PolicyEditor
                  key={`${policy.policy_id}/${policy.version}`}
                  policy={policy}
                  onConfirm={setOperation}
                />
              ))}
            </section>
          </>
        )
      )}
      {operation && <Control operation={operation} close={() => setOperation(null)} done={retry} />}
    </section>
  )
}
