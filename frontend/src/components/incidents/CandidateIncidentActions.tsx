import { useState } from 'react'
import { Link } from 'react-router-dom'
import { IncidentCorrectionDialog } from './IncidentCorrectionDialog'
import type { CandidateDetail } from '../../services/duplicateService'
import type { Incident } from '../../services/incidentService'
import { Card } from '../common/UI'
import { duplicateService } from '../../services/duplicateService'
import { FormMessage } from '../common/FormParts'

export function CandidateIncidentActions({
  detail,
  onRefresh,
}: {
  detail: CandidateDetail
  onRefresh: () => void
}) {
  const [kind, setKind] = useState<'merge' | 'link-complaint' | null>(null)
  const [keeping, setKeeping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const first = detail.complaints[0]
  const second = detail.complaints[1]
  const source = first?.incident
  const target = second?.incident
  if (!detail.complaints.some((complaint) => complaint.incident !== undefined)) return null
  const linked = source && target && source.incidentId === target.incidentId
  return (
    <Card>
      <h2 className="font-semibold">Actual incident membership</h2>
      <p className="mt-2 text-sm">
        Detection confidence is separate from membership. No merge follows merely from this score.
      </p>
      <div className="my-4 grid gap-4 text-sm sm:grid-cols-2">
        {detail.complaints.map((complaint) => (
          <div className="break-all" key={complaint.complaintId}>
            <p>{complaint.title}</p>
            {complaint.incident ? (
              <Link
                className="text-teal-700"
                to={`/admin/incidents/${complaint.incident.incidentId}`}
              >
                {complaint.incident.incidentId} · v{complaint.incident.version}
              </Link>
            ) : (
              <p>Singleton initialization pending; refresh after processing.</p>
            )}
          </div>
        ))}
      </div>
      {linked ? (
        <p>These complaints are already linked to the same incident.</p>
      ) : (
        source &&
        target &&
        source.status === 'OPEN' &&
        target.status === 'OPEN' && (
          <div className="flex flex-wrap gap-3">
            <button className="action-link" onClick={() => setKind('link-complaint')}>
              Review and link first report to second incident
            </button>
            <button className="action-link" onClick={() => setKind('merge')}>
              Review merge of these incidents
            </button>
          </div>
        )
      )}
      {!linked && (
        <button
          type="button"
          className="secondary-button mt-3"
          disabled={keeping}
          onClick={() => {
            setKeeping(true)
            setError(null)
            void duplicateService
              .review(detail.candidateId, 'dismiss')
              .then(onRefresh)
              .catch((failure: unknown) =>
                setError(
                  failure instanceof Error ? failure.message : 'Could not record separate review',
                ),
              )
              .finally(() => setKeeping(false))
          }}
        >
          {keeping ? 'Recording separate review…' : 'Keep separate (dismiss suggestion)'}
        </button>
      )}
      <FormMessage error={error} />
      {kind && source && target && (
        <IncidentCorrectionDialog
          kind={kind}
          source={source as Incident}
          targetSnapshot={target as Incident}
          selected={[first.complaintId]}
          candidateId={detail.candidateId}
          onClose={() => setKind(null)}
          onSaved={() => {
            setKind(null)
            onRefresh()
          }}
        />
      )}
    </Card>
  )
}
