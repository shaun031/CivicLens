import { useRef, useState, type FormEvent } from 'react'
import { FormMessage, Field } from '../common/FormParts'
import { Textarea } from '../common/UI'
import { Modal } from '../common/Modal'
import {
  incidentService,
  type Incident,
  type IncidentCorrection,
} from '../../services/incidentService'

type Kind = Parameters<typeof incidentService.correct>[0]
export function IncidentCorrectionDialog({
  kind,
  source,
  selected = [],
  onClose,
  onSaved,
  candidateId,
  targetSnapshot,
}: {
  kind: Kind
  source: Incident
  selected?: string[]
  candidateId?: string
  targetSnapshot?: Incident
  onClose: () => void
  onSaved: (incident: Incident) => void
}) {
  const [operationId] = useState(() => crypto.randomUUID())
  const [target, setTarget] = useState(targetSnapshot?.incidentId ?? '')
  const [destination, setDestination] = useState<Incident | null>(targetSnapshot ?? null)
  const targetRequest = useRef(0)
  const [reason, setReason] = useState('')
  const [physical, setPhysical] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Freeze the exact request after the first attempt: retries retain durable idempotency.
  const [attempted, setAttempted] = useState<IncidentCorrection | null>(null)
  const moving = kind === 'merge' || kind === 'link-complaint'
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      let request = attempted
      if (!request) {
        if (moving && !destination) throw new Error('Load and review the target snapshot first.')
        request = {
          operationId,
          sourceIncidentId: source.incidentId,
          expectedSourceVersion: source.version,
          reason: reason.trim(),
          confirmed,
          ...(moving
            ? {
                targetIncidentId: destination!.incidentId,
                expectedTargetVersion: destination!.version,
                physicalIssueConfirmed: physical,
              }
            : {}),
          ...(kind === 'split' || kind === 'unlink-complaint' ? { complaintIds: selected } : {}),
          ...(kind === 'link-complaint' ? { complaintId: selected[0] } : {}),
          ...(candidateId ? { matchingCandidateId: candidateId } : {}),
        }
        setAttempted(request)
      }
      const result = await incidentService.correct(kind, request)
      onSaved(result)
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : 'Incident operation failed. Refresh after a version conflict.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal
      title={`Confirm incident ${kind}`}
      onClose={() => {
        if (!busy) onClose()
      }}
    >
      <p className="mb-4 break-all text-sm">
        Source {source.incidentId}, version {source.version}. {selected.length} selected reports.
        Original reports and photos are retained. Publication and complaint statuses do not change.
      </p>
      <form onSubmit={(event) => void submit(event)} className="space-y-4">
        <fieldset disabled={busy || attempted !== null} className="space-y-4">
          {moving && (
            <Field
              id="incident-target"
              label="Target incident ID"
              value={target}
              required
              pattern="[0-9a-fA-F-]{36}"
              onChange={(event) => {
                setTarget(event.target.value)
                targetRequest.current++
                setDestination(null)
                setPhysical(false)
              }}
            />
          )}
          {moving && (
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setError(null)
                const requestId = ++targetRequest.current
                void incidentService
                  .detail(target.trim())
                  .then((value) => {
                    if (requestId !== targetRequest.current) return
                    if (value.incidentId !== target.trim() || value.status !== 'OPEN')
                      throw new Error('Enter the canonical OPEN target ID, not a retired alias.')
                    setDestination(value)
                  })
                  .catch((failure: unknown) =>
                    setError(failure instanceof Error ? failure.message : 'Target unavailable'),
                  )
              }}
            >
              Load target for confirmation
            </button>
          )}
          {moving && destination && (
            <p className="rounded-xl bg-slate-50 p-3 text-sm">
              Target: {destination.canonicalTitle} · {destination.totalComplaintCount} linked
              reports · version {destination.version}. Review before confirming; stale versions are
              rejected.
            </p>
          )}
          <Textarea
            id="incident-reason"
            label="Written correction reason"
            value={reason}
            required
            minLength={10}
            maxLength={500}
            onChange={(event) => setReason(event.target.value)}
          />
          {moving && (
            <label className="flex gap-3 text-sm">
              <input
                type="checkbox"
                required
                checked={physical}
                onChange={(event) => setPhysical(event.target.checked)}
              />
              I reviewed the locations and evidence and confirm the same physical issue.
            </label>
          )}
          <label className="flex gap-3 text-sm">
            <input
              type="checkbox"
              required
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            I confirm this membership operation and its recorded reason.
          </label>
        </fieldset>
        <FormMessage error={error} />
        {attempted && error && (
          <p className="text-sm text-amber-900">
            Retry resends the identical operation ID and request. For a 409/version conflict, close,
            refresh the incident and confirm a new operation.
          </p>
        )}
        <button className="action-link" type="submit" disabled={busy || (moving && !destination)}>
          {busy
            ? 'Applying…'
            : attempted
              ? 'Retry identical operation'
              : 'Apply confirmed operation'}
        </button>
      </form>
    </Modal>
  )
}
