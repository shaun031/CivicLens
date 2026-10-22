import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { discoveryService } from '../services/discoveryService'
import { useResource } from '../hooks/useResource'
import { categories, statuses } from '../types/complaint'
import { Card, PageHeader, Skeleton } from '../components/common/UI'
import { ErrorState } from '../components/common/ErrorState'
import { formatDate } from '../utils/dates'

export function PublicIssuePage() {
  const { publicIssueId = '' } = useParams()
  const loader = useCallback(() => discoveryService.detail(publicIssueId), [publicIssueId])
  const { data, loading, error, retry } = useResource(loader)
  return (
    <section className="mx-auto max-w-4xl space-y-6 px-4 py-12 sm:px-6">
      <PageHeader
        title="Approved public issue"
        description="Reviewed information with approximate coordinates. Reporter identities and private evidence stay protected."
      />
      {loading ? (
        <Skeleton />
      ) : error ? (
        <ErrorState title="Public issue unavailable" message={error} onRetry={retry} />
      ) : (
        data && (
          <Card>
            <h2 className="text-xl font-semibold">{data.summary}</h2>
            <dl className="detail-grid mt-5">
              <dt>Category</dt>
              <dd>{categories[data.category]}</dd>
              <dt>Current status</dt>
              <dd>{statuses[data.status]}</dd>
              <dt>General location</dt>
              <dd>
                {data.latitude.toFixed(3)}, {data.longitude.toFixed(3)}
              </dd>
              <dt>Published</dt>
              <dd>{formatDate(data.publishedAt, true)}</dd>
            </dl>
          </Card>
        )
      )}
      <Link className="font-semibold text-teal-700" to="/citizen/nearby">
        Explore Nearby Issues
      </Link>
    </section>
  )
}
