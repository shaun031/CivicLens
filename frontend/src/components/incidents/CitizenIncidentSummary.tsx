import { useEffect, useState } from 'react'
import { incidentService } from '../../services/incidentService'
import { categories } from '../../types/complaint'
import { Card } from '../common/UI'

export function CitizenIncidentSummary({ complaintId }: { complaintId: string }) {
  const [result, setResult] = useState<Awaited<
    ReturnType<typeof incidentService.ownerSummary>
  > | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let active = true
    incidentService
      .ownerSummary(complaintId)
      .then((data) => {
        if (active) setResult(data)
      })
      .catch(() => {
        if (active) setError(true)
      })
    return () => {
      active = false
    }
  }, [complaintId])
  return (
    <Card>
      <h2 className="font-semibold">Associated incident</h2>
      {error ? (
        <p className="mt-3 text-sm">
          Incident summary unavailable. Refresh your complaint to retry.
        </p>
      ) : !result ? (
        <p role="status" className="mt-3 text-sm">
          Loading your incident summary…
        </p>
      ) : result.incidentId ? (
        <dl className="detail-grid mt-4">
          <dt>Incident ID</dt>
          <dd className="break-all">{result.incidentId}</dd>
          <dt>Incident status</dt>
          <dd>{result.status}</dd>
          <dt>Category</dt>
          <dd>{result.category && categories[result.category]}</dd>
        </dl>
      ) : (
        <p className="mt-3 text-sm">
          Incident initialization is pending. Your complaint is saved; refresh later.
        </p>
      )}
      <p className="mt-3 text-xs text-slate-600">
        CivicLens considers assessed severity, public impact, eligible independent accounts and
        unresolved time. Unassessed inputs remain provisional; priority never automatically
        publishes private reports. This is not an emergency dispatch service.
      </p>
      <p className="mt-3 text-xs text-slate-600">
        Only your safe association is shown. Other reporters, membership counts, private
        descriptions and photos are not disclosed.
      </p>
    </Card>
  )
}
