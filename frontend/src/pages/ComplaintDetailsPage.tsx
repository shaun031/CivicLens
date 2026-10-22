import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCitizen } from '../auth/CitizenContext'
import { useResource } from '../hooks/useResource'
import { complaintService } from '../services/complaintService'
import { categories } from '../types/complaint'
import {
  ComplaintImageGallery,
  ComplaintTimeline,
  StatusBadge,
} from '../components/complaints/ComplaintComponents'
import { Alert, Breadcrumbs, Card, EmptyState, PageHeader, Skeleton } from '../components/common/UI'
import { ErrorState } from '../components/common/ErrorState'
import { formatDate } from '../utils/dates'
import { PublicationControls } from '../components/complaints/PublicationControls'
import { CitizenIncidentSummary } from '../components/incidents/CitizenIncidentSummary'
export function ComplaintDetailsPage() {
  const { complaintId = '' } = useParams()
  const { demo } = useCitizen()
  const loader = useCallback(() => complaintService.detail(complaintId, demo), [complaintId, demo])
  const { data, loading, error, retry } = useResource(loader)
  if (loading) return <Skeleton />
  if (error) return <ErrorState title="Complaint unavailable" message={error} onRetry={retry} />
  if (!data)
    return (
      <EmptyState title="Complaint not found">
        This complaint does not exist or is not available to this account. Sample IDs only work in
        sample preview.
        <br />
        <Link className="mt-3 inline-block font-semibold text-teal-700" to="/citizen/complaints">
          Back to My Complaints
        </Link>
      </EmptyState>
    )
  return (
    <>
      <Breadcrumbs current="Complaint details" />
      <PageHeader
        title={data.title}
        description={`${data.isSimulated ? 'Simulated complaint' : 'Complaint'} · ${data.complaintId}`}
        action={<StatusBadge status={data.status} />}
      />
      {data.isSimulated && (
        <Alert>
          Simulated complaint. This report, timeline, and any related incident are fictional. No
          action has been taken by a real department.
        </Alert>
      )}
      <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
        <div className="space-y-6">
          <Card>
            <h2 className="mb-4 text-lg font-semibold">Issue details</h2>
            <p className="whitespace-pre-wrap text-sm leading-7 text-slate-600">
              {data.description}
            </p>
            <dl className="detail-grid mt-5">
              <dt>Category</dt>
              <dd>{categories[data.category]}</dd>
              <dt>Location</dt>
              <dd>{data.location.addressLabel}</dd>
              {data.location.landmark && (
                <>
                  <dt>Landmark</dt>
                  <dd>{data.location.landmark}</dd>
                </>
              )}
              <dt>Coordinates</dt>
              <dd>
                {data.location.latitude.toFixed(5)}, {data.location.longitude.toFixed(5)}
              </dd>
              <dt>Reported severity</dt>
              <dd>{data.reportedSeverity} (not a verified priority score)</dd>
              <dt>Created</dt>
              <dd>{formatDate(data.createdAt, true)}</dd>
              <dt>Last update</dt>
              <dd>{formatDate(data.updatedAt, true)}</dd>
              {data.incidentId && (
                <>
                  <dt>Related incident</dt>
                  <dd>
                    {data.incidentId}
                    {data.isSimulated ? ' (simulated)' : ''}
                  </dd>
                </>
              )}
            </dl>
          </Card>
          <Card>
            <h2 className="mb-4 text-lg font-semibold">Photo evidence</h2>
            <ComplaintImageGallery images={data.images} />
          </Card>
        </div>
        <Card>
          <h2 className="mb-5 text-lg font-semibold">Progress timeline</h2>
          <ComplaintTimeline events={data.progress} />
        </Card>
      </div>
      {!data.isSimulated && (
        <CitizenIncidentSummary
          key={`incident-${data.complaintId}`}
          complaintId={data.complaintId}
        />
      )}
      {!data.isSimulated && (
        <PublicationControls
          key={data.complaintId}
          complaintId={data.complaintId}
          initial={data.publication}
        />
      )}
      <Link className="text-sm font-semibold text-teal-700" to="/citizen/complaints">
        ← Back to My Complaints
      </Link>
    </>
  )
}
