import { useCallback, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useResource } from '../../hooks/useResource'
import {
  priorityService,
  type PriorityAction,
  type PriorityOperation,
  type PriorityState,
  type PriorityResult,
} from '../../services/priorityService'
import { Card, Badge, PriorityBadge, EmptyState, Select, Skeleton, Textarea } from '../common/UI'
import { Field, FormMessage } from '../common/FormParts'
import { ErrorState } from '../common/ErrorState'
import { Modal } from '../common/Modal'
import { formatDate } from '../../utils/dates'

const labels = {
  severity: 'Severity',
  publicImpact: 'Public impact',
  reporters: 'Independent reporters',
  aging: 'Unresolved time',
}
export function PriorityBreakdown({ priority }: { priority: PriorityResult }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-3">
        <PriorityBadge band={priority.priorityBand} />
        <Badge>{priority.assessmentStatus}</Badge>
        {priority.urgentHazard && <Badge>VERIFIED URGENT HAZARD</Badge>}
        <Badge>Override: {priority.overrideStatus}</Badge>
      </div>
      <dl className="detail-grid">
        <dt>Calculated priority</dt>
        <dd>
          {priority.calculatedScore}/100 · {priority.calculatedBand}
        </dd>
        <dt>Effective operational priority</dt>
        <dd>
          {priority.effectiveScore}/100 · {priority.priorityBand}
        </dd>
      </dl>
      <p className="text-sm">
        Formula score, hazard escalation and override are separate. This is not an accident
        probability or emergency dispatch service.
      </p>
      <div className="space-y-4">
        {Object.entries(priority.factors).map(([key, factor]) => {
          const maximum = factor.weight * 100
          return (
            <div key={key}>
              <div className="mb-1 flex flex-wrap justify-between gap-2 text-sm">
                <span>{labels[key as keyof typeof labels]}</span>
                <span>
                  {factor.contribution}/{maximum} points · {Math.round(factor.weight * 100)}% weight
                </span>
              </div>
              <div
                role="progressbar"
                aria-label={`${labels[key as keyof typeof labels]} contribution`}
                aria-valuemin={0}
                aria-valuemax={maximum || 1}
                aria-valuenow={factor.contribution}
                className="h-3 overflow-hidden rounded-full bg-slate-100"
              >
                <div
                  className="h-full rounded-full bg-teal-600"
                  style={{ width: `${maximum ? (factor.contribution / maximum) * 100 : 0}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-slate-600">
                Input {factor.rawValue ?? 'Unknown'} · normalized {factor.normalizedValue}/10 ·{' '}
                {factor.status}
              </p>
            </div>
          )
        })}
      </div>
      <ul className="list-disc space-y-2 pl-5 text-sm">
        {priority.explanation.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {priority.reviewFlags.length > 0 && (
        <div className="rounded-xl bg-amber-50 p-4 text-sm text-amber-950">
          <h4 className="font-semibold">Review required</h4>
          <ul className="mt-2 list-disc space-y-2 pl-5">
            {priority.reviewFlags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="break-all text-xs text-slate-600">
        Calculated {formatDate(priority.calculatedAt, true)} · {priority.algorithmVersion}
      </p>
    </div>
  )
}

const actions: [PriorityOperation, string][] = [
  ['SEVERITY', 'Assess severity'],
  ['PUBLIC_IMPACT', 'Assess public impact'],
  ['HAZARD', 'Review urgent hazard'],
  ['OVERRIDE', 'Create priority override'],
  ['REMOVE_OVERRIDE', 'Remove priority override'],
  ['RECALCULATE', 'Recalculate priority'],
]

export function PriorityEditor({
  state,
  kind,
  onClose,
  onSaved,
}: {
  state: PriorityState
  kind: PriorityOperation
  onClose: () => void
  onSaved: () => void
}) {
  const assessing = kind === 'SEVERITY' || kind === 'PUBLIC_IMPACT'
  const existing = state.controls[kind === 'SEVERITY' ? 'severity' : 'publicImpact']
  const [operationId] = useState(() => crypto.randomUUID())
  const [score, setScore] = useState(String(assessing ? (existing?.score ?? 3) : 60))
  const [status, setStatus] = useState('VERIFIED')
  const [reason, setReason] = useState('')
  const [references, setReferences] = useState<string[]>([])
  const [hazard, setHazard] = useState(false)
  const [expires, setExpires] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [attempted, setAttempted] = useState<PriorityAction | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      let request = attempted
      if (!request) {
        if (
          ((assessing && status === 'VERIFIED') || (kind === 'HAZARD' && hazard)) &&
          !references.length
        )
          throw new Error('Select supporting evidence from the current incident before verifying.')
        request = {
          operationId,
          expectedIncidentVersion: state.incidentVersion,
          expectedPriorityRevision: state.priorityRevision,
          reason: reason.trim(),
          confirmed,
          ...(assessing
            ? {
                score: status === 'UNASSESSED' ? null : Number(score),
                status,
                evidenceReferences: references,
              }
            : {}),
          ...(kind === 'HAZARD' ? { flag: hazard, evidenceReferences: references } : {}),
          ...(kind === 'OVERRIDE'
            ? { score: Number(score), expiresAt: expires ? new Date(expires).toISOString() : null }
            : {}),
        }
        setAttempted(request)
      }
      await priorityService.change(state.incident.incidentId, kind, request)
      onSaved()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Priority operation failed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal
      title={actions.find(([value]) => value === kind)![1]}
      onClose={() => {
        if (!busy) onClose()
      }}
    >
      <p className="mb-4 text-sm">
        Incident version {state.incidentVersion}; assessment revision {state.priorityRevision}.
        Original reports, memberships and raw formula remain preserved.
      </p>
      <form onSubmit={(event) => void submit(event)} className="space-y-4">
        <fieldset disabled={busy || attempted !== null} className="space-y-4">
          {assessing && (
            <Select
              id="priority-assessment-status"
              label="Assessment status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="VERIFIED">VERIFIED — inspected evidence</option>
              <option value="PROVISIONAL">PROVISIONAL — uncertain, capped at 6</option>
              <option value="UNASSESSED">UNASSESSED — unknown</option>
            </Select>
          )}
          {(assessing || kind === 'OVERRIDE') && (
            <Field
              id="priority-score"
              label={kind === 'OVERRIDE' ? 'Override score (0–100)' : 'Assessment score (0–10)'}
              type="number"
              min={0}
              max={kind === 'OVERRIDE' ? 100 : status === 'PROVISIONAL' ? 6 : 10}
              step="0.1"
              required={status !== 'UNASSESSED'}
              disabled={assessing && status === 'UNASSESSED'}
              value={score}
              onChange={(event) => setScore(event.target.value)}
            />
          )}
          {kind === 'HAZARD' && (
            <label className="flex gap-3 text-sm">
              <input
                type="checkbox"
                checked={hazard}
                onChange={(event) => setHazard(event.target.checked)}
              />
              I verified an urgent hazard; clearing this records its removal. No external dispatch
              occurs.
            </label>
          )}
          {(assessing || kind === 'HAZARD') && (
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-semibold">
                Supporting current evidence (up to 10)
              </legend>
              {state.evidenceOptions.map((option) => (
                <label key={option.id} className="flex gap-3 text-sm">
                  <input
                    type="checkbox"
                    checked={references.includes(option.id)}
                    onChange={(event) =>
                      setReferences((previous) =>
                        event.target.checked
                          ? [...previous, option.id].slice(0, 10)
                          : previous.filter((id) => id !== option.id),
                      )
                    }
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
          )}
          {kind === 'OVERRIDE' && (
            <Field
              id="priority-expiry"
              label="Optional override expiration (local time)"
              type="datetime-local"
              value={expires}
              onChange={(event) => setExpires(event.target.value)}
            />
          )}
          <Textarea
            id="priority-reason"
            label="Priority assessment or correction reason"
            minLength={10}
            maxLength={1000}
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <label className="flex gap-3 text-sm">
            <input
              type="checkbox"
              required
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            I confirm this assessed change and the recorded reason.
          </label>
        </fieldset>
        <FormMessage error={error} />
        {attempted && error && (
          <p className="text-sm text-amber-950">
            Retry preserves the exact operation ID and input. After a 409, close, refresh and
            confirm a new operation.
          </p>
        )}
        <button className="action-link" disabled={busy} type="submit">
          {busy
            ? 'Saving…'
            : attempted
              ? 'Retry identical priority operation'
              : 'Save confirmed priority operation'}
        </button>
      </form>
    </Modal>
  )
}

export function PriorityPanel({ incidentId }: { incidentId: string }) {
  return <PriorityPanelContent key={incidentId} incidentId={incidentId} />
}
function PriorityPanelContent({ incidentId }: { incidentId: string }) {
  const loader = useCallback(() => priorityService.detail(incidentId), [incidentId])
  const resource = useResource(loader)
  const [cursor, setCursor] = useState<string | null>(null)
  const historyLoader = useCallback(
    () => priorityService.history(incidentId, cursor ?? undefined),
    [incidentId, cursor],
  )
  const history = useResource(historyLoader)
  const [action, setAction] = useState<PriorityOperation | null>(null)
  return (
    <section className="space-y-5" aria-label="Explainable incident priority">
      <Card>
        <h2 className="mb-4 text-xl font-semibold">Priority and urgency breakdown</h2>
        {resource.loading ? (
          <Skeleton />
        ) : resource.error ? (
          <ErrorState message={resource.error} onRetry={resource.retry} />
        ) : (
          resource.data && (
            <>
              {resource.data.stale && (
                <p role="status" className="mb-4 rounded-xl bg-amber-50 p-4 text-sm text-amber-950">
                  Pending or stale priority. Stored scores below are not current rankings.{' '}
                  {resource.data.staleReasons.join('. ')}.
                </p>
              )}
              {resource.data.priority ? (
                <PriorityBreakdown priority={resource.data.priority} />
              ) : (
                <EmptyState title="Priority not calculated">
                  A provisional assessment is pending. Your original reports are preserved.
                </EmptyState>
              )}
              <div className="mt-6 flex flex-wrap gap-3">
                {actions.map(([kind, label]) => (
                  <button key={kind} className="secondary-button" onClick={() => setAction(kind)}>
                    {label}
                  </button>
                ))}
              </div>
              <button
                className="mt-4 text-sm font-semibold text-teal-700"
                onClick={() => {
                  resource.retry()
                  history.retry()
                }}
              >
                Refresh priority and history
              </button>
            </>
          )
        )}
      </Card>
      <Card>
        <h3 className="mb-3 font-semibold">Priority assessment and calculation history</h3>
        {history.loading ? (
          <Skeleton />
        ) : history.error ? (
          <ErrorState message={history.error} onRetry={history.retry} />
        ) : !history.data?.items.length ? (
          <p className="text-sm">No priority history yet.</p>
        ) : (
          <ol className="space-y-4">
            {history.data.items.map((entry) => (
              <li key={entry.eventId} className="rounded-xl border border-slate-200 p-4 text-sm">
                <h4 className="font-semibold">{entry.kind.replaceAll('_', ' ')}</h4>
                <p className="mt-2">{entry.reason}</p>
                <p className="mt-2">
                  Calculated {entry.snapshot.before?.calculatedScore ?? 'Uncalculated'} →{' '}
                  {entry.snapshot.after.calculatedScore}; effective{' '}
                  {entry.snapshot.after.effectiveScore} · {entry.snapshot.after.priorityBand}
                </p>
                <p className="mt-2 break-all text-xs">
                  {formatDate(entry.createdAt, true)} · Actor {entry.actorId}
                </p>
                <details className="mt-3">
                  <summary className="cursor-pointer text-teal-700">
                    Inspect historical factor breakdown
                  </summary>
                  <div className="mt-4">
                    <PriorityBreakdown priority={entry.snapshot.after} />
                  </div>
                </details>
              </li>
            ))}
          </ol>
        )}
        {history.data?.nextCursor && (
          <button
            className="secondary-button mt-4"
            onClick={() => setCursor(history.data!.nextCursor)}
          >
            Next priority history page
          </button>
        )}
        {cursor && (
          <button className="secondary-button mt-4" onClick={() => setCursor(null)}>
            First priority history page
          </button>
        )}
      </Card>
      <Link to="/admin/priorities" className="inline-block text-teal-700">
        View ranked incident queue
      </Link>
      {action && resource.data && (
        <PriorityEditor
          kind={action}
          state={resource.data}
          onClose={() => setAction(null)}
          onSaved={() => {
            setAction(null)
            setCursor(null)
            resource.retry()
            history.retry()
          }}
        />
      )}
    </section>
  )
}
