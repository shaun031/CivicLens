import { useCallback, useContext, useState } from 'react'
import { CitizenContext } from '../auth/CitizenContext'
import { Link, useParams } from 'react-router-dom'
import { authRequest } from '../auth/authClient'
import { useAuth } from '../auth/AuthContext'
import { useResource } from '../hooks/useResource'
import { useCivicOperation } from '../hooks/useCivicOperation'
import { Alert, Badge, Card, EmptyState, PageHeader, Skeleton } from '../components/common/UI'
import { Button } from '../components/common/Button'
import { ErrorState } from '../components/common/ErrorState'
import { fieldClass } from '../components/common/FormParts'
import { ImageUpload } from '../components/complaints/ImageUpload'
import { ComplaintImageGallery } from '../components/complaints/ComplaintComponents'
import { sendEvidence, type Page, type Repair } from '../services/civicIntelligenceService'

function RepairCard({
  repair,
  citizen,
  onSelect,
}: {
  repair: Repair
  citizen: boolean
  onSelect: () => void
}) {
  return (
    <Card>
      <Badge>{repair.state}</Badge>
      <h2 className="mt-3 text-lg font-semibold">{repair.title}</h2>
      <p className="my-3 text-sm">
        Attempt {repair.cycle} · submitted {new Date(repair.submittedAt).toLocaleString()}
      </p>
      <p className="mb-4 whitespace-pre-wrap text-sm">{repair.description}</p>
      <Button onClick={onSelect}>
        {citizen ? 'Verify repair / view response' : 'Review repair attempt'}
      </Button>
    </Card>
  )
}

export function RepairDetails({
  repair,
  citizen,
  refresh,
}: {
  repair: Repair
  citizen: boolean
  refresh: () => void
}) {
  const [result, setResult] = useState('CONFIRMED_FIXED')
  const [feedback, setFeedback] = useState('')
  const [reason, setReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [approved, setApproved] = useState<string[]>([])
  const [files, setFiles] = useState<File[]>([])
  const operation = useCivicOperation()
  const pending = ['PENDING_VERIFICATION', 'INFORMATION_REQUIRED'].includes(repair.state)
  function decide(action: string) {
    const body = {
      expectedVersion: repair.version,
      expectedIncidentVersion: repair.incidentVersion,
      reason,
      confirmed,
      approvedEvidenceIds: approved,
    }
    void operation.run(
      { action, body },
      (operationId) =>
        authRequest(`/admin/repairs/${repair.attemptId}/${action}`, 'POST', {
          ...body,
          operationId,
        }),
      refresh,
    )
  }
  return (
    <Card className="space-y-5">
      <h2 className="text-xl font-semibold">
        Repair attempt {repair.cycle}: {repair.title}
      </h2>
      <Badge>{repair.state}</Badge>
      <p className="whitespace-pre-wrap">{repair.description}</p>
      <p className="text-sm">
        Submitted {new Date(repair.submittedAt).toLocaleString()} · repaired{' '}
        {new Date(repair.repairedAt).toLocaleString()}
      </p>
      {repair.membershipChanged && (
        <Alert>
          Incident version changed since submission. A new review may be required; stale
          feedback/approval is blocked.
        </Alert>
      )}
      <ComplaintImageGallery
        images={repair.images.map((image) => ({
          url: image.url,
          alt: `${image.kind.toLowerCase()} evidence`,
          requiresAuth: true,
        }))}
      />
      {repair.decisionReason && (
        <p className="whitespace-pre-wrap">Administrative decision: {repair.decisionReason}</p>
      )}
      {repair.verifiedAt && (
        <p>Recorded verified resolution: {new Date(repair.verifiedAt).toLocaleString()}</p>
      )}
      {citizen ? (
        <>
          <Alert>
            Your response is feedback, not an official closure or reopening. One response per
            eligible account and attempt; no photo is required to dispute a repair.
          </Alert>
          {repair.relatedComplaints?.map((id) => (
            <Link key={id} className="block text-teal-700" to={`/citizen/complaints/${id}`}>
              Open your related complaint and original evidence
            </Link>
          ))}
          {repair.response && (
            <p role="status">
              Your recorded response: {repair.response.result}. {repair.response.feedback}
            </p>
          )}
          {repair.canRespond && (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault()
                const body = { expectedVersion: repair.version, result, feedback }
                void operation.run(
                  { body, files: files.map((f) => [f.name, f.size, f.lastModified]) },
                  (operationId) =>
                    sendEvidence(
                      `/citizen/verification-requests/${repair.requestId}/respond`,
                      { ...body, operationId },
                      files,
                    ),
                  refresh,
                )
              }}
            >
              <label className="block text-sm">
                Repair response
                <select
                  className={fieldClass}
                  value={result}
                  onChange={(e) => setResult(e.target.value)}
                >
                  <option value="CONFIRMED_FIXED">Confirm Fixed</option>
                  <option value="STILL_BROKEN">Still Broken</option>
                  <option value="UNSURE">Unsure</option>
                </select>
              </label>
              <label className="block text-sm">
                Optional feedback
                <textarea
                  maxLength={2000}
                  className={fieldClass}
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
              </label>
              <ImageUpload files={files} onChange={setFiles} />
              <Button type="submit" disabled={operation.busy}>
                Record verification response
              </Button>
            </form>
          )}
        </>
      ) : (
        <>
          <p className="text-sm">
            {repair.eligibleCitizens} eligible accounts · {repair.missingResponses} missing
            responses · {repair.recommendation}
          </p>
          <p className="text-sm">
            {Object.entries(repair.responses ?? {})
              .map(([key, value]) => `${key}: ${value}`)
              .join(' · ')}
          </p>
          <Alert>
            Recommendation only. No responses do not establish success. Review all disputes, hazard
            assessments and available evidence before deciding.
          </Alert>
          {repair.priority && (
            <p>
              Priority:{' '}
              {repair.priority.stale
                ? 'Pending/stale'
                : (repair.priority.priority?.priorityBand ?? 'Unavailable')}{' '}
              · urgent hazard:{' '}
              {repair.priority.stale
                ? 'Unavailable'
                : repair.priority.priority?.urgentHazard
                  ? 'Yes — safety review required'
                  : 'No current verified flag'}
            </p>
          )}
          {repair.feedback?.map((vote, index) => (
            <p className="text-sm" key={index}>
              {vote.result} (
              {vote.eligible ? 'currently eligible' : 'historical / no longer eligible'}):{' '}
              {vote.feedback || 'No additional text'}
            </p>
          ))}
          <p className="text-sm whitespace-pre-wrap">
            Internal officer notes: {repair.notes || 'None'}
          </p>
          {pending &&
            repair.images
              .filter((i) => i.kind === 'REPAIR')
              .map((image) => (
                <label key={image.imageId} className="flex gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={approved.includes(image.imageId)}
                    onChange={(e) =>
                      setApproved(
                        e.target.checked
                          ? [...approved, image.imageId]
                          : approved.filter((id) => id !== image.imageId),
                      )
                    }
                  />
                  Approve this repair photograph for eligible citizen verification (
                  {image.approved ? 'already approved' : 'private until approved'})
                </label>
              ))}
          {(pending || repair.state === 'VERIFIED_RESOLVED') && (
            <fieldset className="space-y-4" disabled={operation.busy}>
              <legend className="font-semibold">Accountable administrative decision</legend>
              <label className="block text-sm">
                Decision reason / independent verification basis
                <textarea
                  required
                  minLength={10}
                  maxLength={2000}
                  className={fieldClass}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <label className="flex gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                I reviewed current evidence, feedback, hazards and incident membership.
              </label>
              <div className="flex flex-wrap gap-3">
                {(pending
                  ? [
                      'approve-evidence',
                      'approve',
                      'reject',
                      'request-rework',
                      'request-information',
                    ]
                  : ['reopen']
                ).map((action) => (
                  <Button
                    key={action}
                    disabled={!confirmed || reason.trim().length < 10}
                    onClick={() => decide(action)}
                  >
                    {action.replaceAll('-', ' ')}
                  </Button>
                ))}
              </div>
            </fieldset>
          )}
          <Link className="block text-teal-700" to={`/admin/incidents/${repair.incidentId}`}>
            Canonical incident, priority and membership history
          </Link>
          <details>
            <summary>Recorded repair audit history</summary>
            {repair.audit?.map((row, index) => (
              <p className="my-2 text-sm" key={index}>
                {row.created_at} · {row.kind} · {row.reason}
              </p>
            ))}
          </details>
        </>
      )}
      {operation.error && (
        <p role="alert" className="text-red-700">
          {operation.error}
        </p>
      )}
      {operation.message && <p role="status">{operation.message}</p>}
    </Card>
  )
}

export function RepairsPage({ citizen = false }: { citizen?: boolean }) {
  const { user } = useAuth()
  const workspace = useContext(CitizenContext)
  const preview = citizen && Boolean(workspace?.demo)
  const [after, setAfter] = useState('')
  const [history, setHistory] = useState(false)
  const [state, setState] = useState('')
  const [selected, setSelected] = useState('')
  const [notice, setNotice] = useState('')
  const load = useCallback(() => {
    if (!user?.id) return Promise.reject(new Error('Authenticated session required'))
    if (preview) return Promise.resolve<Page<Repair>>({ items: [], nextAfter: null })
    const params = new URLSearchParams({
      ...(after ? { after } : {}),
      ...(!citizen && state ? { state } : {}),
    })
    return authRequest<Page<Repair>>(
      citizen
        ? `/citizen/verification-${history ? 'history' : 'requests'}?${params}`
        : `/admin/repairs/pending?${params}`,
    )
  }, [citizen, history, after, state, user?.id, preview])
  const resource = useResource(load)
  const detailLoad = useCallback(() => {
    if (!user?.id) return Promise.reject(new Error('Authenticated session required'))
    if (preview) return Promise.resolve(null)
    return selected
      ? authRequest<Repair>(
          citizen ? `/citizen/verification-requests/${selected}` : `/admin/repairs/${selected}`,
        )
      : Promise.resolve(null)
  }, [citizen, selected, user?.id, preview])
  const detail = useResource(detailLoad)
  const refresh = () => {
    resource.retry()
    detail.retry()
  }
  if (preview)
    return (
      <Alert>
        Repair verification has no fabricated sample results. Turn off Show sample data to view or
        respond to your real eligible requests.
      </Alert>
    )
  return (
    <section className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      <PageHeader
        title={citizen ? 'Repair verification' : 'Administrative repair verification'}
        description="Repair submission is not resolution. Decisions and feedback are persisted with version checks and auditable history."
      />
      <div className="flex flex-wrap gap-4">
        {citizen ? (
          <label>
            <input
              type="checkbox"
              checked={history}
              onChange={(e) => {
                setHistory(e.target.checked)
                setAfter('')
                setSelected('')
              }}
            />{' '}
            Include completed verification history
          </label>
        ) : (
          <label>
            Repair state
            <select
              className={fieldClass}
              value={state}
              onChange={(e) => {
                setState(e.target.value)
                setAfter('')
                setSelected('')
              }}
            >
              <option value="">All states</option>
              {[
                'PENDING_VERIFICATION',
                'VERIFIED_RESOLVED',
                'REJECTED',
                'REWORK_REQUIRED',
                'REOPENED',
                'INFORMATION_REQUIRED',
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        )}
        <Button variant="secondary" onClick={refresh}>
          Refresh recorded repairs
        </Button>
      </div>
      {resource.loading && <Skeleton />}
      {resource.error && <ErrorState message={resource.error} onRetry={resource.retry} />}
      {resource.data && (
        <>
          {resource.data.summary && (
            <p>
              {Object.entries(resource.data.summary)
                .map(([key, value]) => `${key}: ${value}`)
                .join(' · ')}
            </p>
          )}
          {!resource.data.items.length && (
            <EmptyState title="No eligible repair requests">
              No successful repair or verification result is fabricated.
            </EmptyState>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {resource.data.items.map((repair) => (
              <RepairCard
                key={repair.attemptId}
                repair={repair}
                citizen={citizen}
                onSelect={() => setSelected(citizen ? repair.requestId! : repair.attemptId)}
              />
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
      {detail.loading && <Skeleton />}
      {detail.error && <ErrorState message={detail.error} onRetry={detail.retry} />}
      {notice && <p role="status">{notice}</p>}
      {detail.data && (
        <RepairDetails
          key={`${detail.data.attemptId}:${user?.id}`}
          repair={detail.data}
          citizen={citizen}
          refresh={() => {
            setNotice('Saved by the backend. Refreshing the recorded state.')
            refresh()
          }}
        />
      )}
    </section>
  )
}

export function OfficerRepairPage() {
  const { incidentId } = useParams()
  const { user } = useAuth()
  const [description, setDescription] = useState('')
  const [notes, setNotes] = useState('')
  const [repairedAt, setRepairedAt] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const operation = useCivicOperation()
  const load = useCallback(async () => {
    if (!user?.id) throw new Error('Officer session required')
    const [work, attempts] = await Promise.all([
      authRequest<{ incidentVersion: number; assignment: { version: number; status: string } }>(
        `/officer/incidents/${incidentId}`,
      ),
      authRequest<Page<Repair>>(`/officer/incidents/${incidentId}/repair-attempts`),
    ])
    return { work, attempts }
  }, [incidentId, user?.id])
  const resource = useResource(load)
  return (
    <section className="mx-auto max-w-5xl space-y-5 px-4 py-8">
      <PageHeader
        title="Submit repair completion"
        description="Only your current eligible assignment can submit. An administrator must review official resolution."
      />
      <Link className="text-teal-700" to={`/officer/incidents/${incidentId}`}>
        Back to assigned work and history
      </Link>
      {resource.loading && <Skeleton />}
      {resource.error && <ErrorState message={resource.error} onRetry={resource.retry} />}
      {resource.data && (
        <>
          <Card>
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault()
                const body = {
                  expectedIncidentVersion: resource.data!.work.incidentVersion,
                  expectedAssignmentVersion: resource.data!.work.assignment.version,
                  description,
                  notes,
                  repairedAt: new Date(repairedAt).toISOString(),
                }
                void operation.run(
                  { body, files: files.map((f) => [f.name, f.size, f.lastModified]) },
                  (operationId) =>
                    sendEvidence(
                      `/officer/incidents/${incidentId}/repair-attempts`,
                      { ...body, operationId },
                      files,
                    ),
                  () => {
                    setFiles([])
                    resource.retry()
                  },
                )
              }}
            >
              <label className="block">
                Repair description
                <textarea
                  required
                  minLength={20}
                  maxLength={2000}
                  className={fieldClass}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
              <label className="block">
                Internal work notes
                <textarea
                  maxLength={2000}
                  className={fieldClass}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </label>
              <label className="block">
                Repair completed at (your local time)
                <input
                  required
                  type="datetime-local"
                  step="1"
                  className={fieldClass}
                  value={repairedAt}
                  onChange={(e) => setRepairedAt(e.target.value)}
                />
              </label>
              <ImageUpload files={files} onChange={setFiles} />
              <Button
                type="submit"
                disabled={
                  operation.busy ||
                  resource.data.work.assignment.status !== 'IN_PROGRESS' ||
                  resource.data.attempts.items.some((a) =>
                    ['PENDING_VERIFICATION', 'INFORMATION_REQUIRED'].includes(a.state),
                  )
                }
              >
                Submit repair for verification
              </Button>
            </form>
          </Card>
          {resource.data.attempts.items.map((repair) => (
            <Card key={repair.attemptId}>
              <h2 className="font-semibold">
                Attempt {repair.cycle} · {repair.state}
              </h2>
              <p>{repair.description}</p>
              <p>{repair.decisionReason}</p>
              <p className="text-sm">
                {repair.recommendation} · {repair.missingResponses} missing eligible responses
              </p>
              <ComplaintImageGallery
                images={repair.images.map((i) => ({
                  url: i.url,
                  alt: `${i.kind} repair history`,
                  requiresAuth: true,
                }))}
              />
            </Card>
          ))}
        </>
      )}
      {operation.error && <p role="alert">{operation.error}</p>}
      {operation.message && <p role="status">{operation.message}</p>}
    </section>
  )
}
