import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { CandidateIncidentActions } from '../components/incidents/CandidateIncidentActions'
import { Field, FormMessage } from '../components/common/FormParts'
import { Badge, Card, EmptyState, PageHeader, Select, Skeleton } from '../components/common/UI'
import { ComplaintImageGallery } from '../components/complaints/ComplaintComponents'
import {
  classifications,
  duplicateService,
  reviewStatuses,
  type Candidate,
  type CandidateDetail,
} from '../services/duplicateService'
import { categories } from '../types/complaint'
import { formatDate } from '../utils/dates'

const score = (value: number) => `${(value * 100).toFixed(1)}/100`
function Scores({ candidate }: { candidate: Candidate }) {
  return (
    <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
      <div>
        <dt>Similarity index</dt>
        <dd className="font-bold">{score(candidate.combinedScore)}</dd>
      </div>
      <div>
        <dt>Distance</dt>
        <dd>{candidate.distanceMeters.toFixed(2)} m</dd>
      </div>
      <div>
        <dt>Geographic similarity</dt>
        <dd>{score(candidate.geographicScore)}</dd>
      </div>
      <div>
        <dt>Text similarity</dt>
        <dd>{score(candidate.textScore)}</dd>
      </div>
      <div>
        <dt>Image similarity</dt>
        <dd>
          {candidate.imageScore === null ? 'Unavailable — not zero' : score(candidate.imageScore)}
        </dd>
      </div>
    </dl>
  )
}

export function DuplicateCandidatesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const query = searchParams.toString() || 'sort=score'
  const [cursor, setCursor] = useState<string | null>(null)
  const [page, setPage] = useState<{ items: Candidate[]; nextCursor: string | null } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    duplicateService
      .list(query + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''))
      .then((value) => {
        if (active) {
          setPage(value)
          setError(null)
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Unable to load candidates')
      })
    return () => {
      active = false
    }
  }, [query, cursor, reload])
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const params = new URLSearchParams()
    for (const [key, value] of data.entries()) if (String(value)) params.set(key, String(value))
    setPage(null)
    setError(null)
    setCursor(null)
    setSearchParams(params)
    setReload((value) => value + 1)
  }
  async function recheck(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const id = String(new FormData(event.currentTarget).get('complaintId')).trim()
    setBusy(true)
    setNotice(null)
    try {
      const result = await duplicateService.recheck(id)
      setNotice(
        `Matching state: ${result.processing.state}. Incomplete results are not exhaustive.`,
      )
      setReload((value) => value + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Recheck failed')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <Link to="/admin/dashboard" className="text-teal-700">
        ← Administrator dashboard
      </Link>
      <PageHeader
        title="Duplicate candidates"
        description="Private administrator review. Similarity is not a probability or proof of the same physical object. No complaints are merged."
      />
      <Card>
        <form onSubmit={filter} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {searchParams.get('complaintId') && (
            <input type="hidden" name="complaintId" value={searchParams.get('complaintId')!} />
          )}
          <Field
            id="candidate-search"
            name="q"
            label="Search titles"
            type="search"
            maxLength={150}
          />
          <Select id="candidate-classification" name="classification" label="Classification">
            <option value="">All classifications</option>
            {classifications.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </Select>
          <Select id="candidate-review" name="reviewStatus" label="Review status">
            <option value="">All review statuses</option>
            {reviewStatuses.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </Select>
          <Select id="candidate-category" name="category" label="Category">
            <option value="">All categories</option>
            {Object.entries(categories).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </Select>
          <Field
            id="candidate-min"
            name="minScore"
            label="Minimum score (0–1)"
            type="number"
            min={0}
            max={1}
            step="0.01"
          />
          <Field
            id="candidate-max"
            name="maxScore"
            label="Maximum score (0–1)"
            type="number"
            min={0}
            max={1}
            step="0.01"
          />
          <Select id="candidate-sort" name="sort" label="Sort">
            <option value="score">Highest similarity</option>
            <option value="date">Last checked</option>
          </Select>
          <button className="action-link" type="submit">
            Apply filters
          </button>
        </form>
      </Card>
      <Card>
        <form onSubmit={(event) => void recheck(event)} className="flex flex-wrap items-end gap-4">
          <Field
            id="matching-source"
            name="complaintId"
            label="Complaint ID to recheck"
            required
            pattern="[0-9a-fA-F-]{36}"
          />
          <button disabled={busy} className="action-link" type="submit">
            {busy ? 'Checking…' : 'Recheck complaint'}
          </button>
        </form>
        <FormMessage success={notice} />
      </Card>
      <FormMessage error={error} />
      {error && (
        <button
          className="action-link"
          onClick={() => {
            setError(null)
            setPage(null)
            setReload((value) => value + 1)
          }}
        >
          Retry loading
        </button>
      )}
      {!page && !error && <Skeleton />}
      {page?.items.length === 0 && (
        <EmptyState title="No duplicate candidates">
          New complaints are checked in the local background. Use a complaint ID to recheck existing
          reports. An empty list does not prove there are no duplicates.
        </EmptyState>
      )}
      <div className="grid min-w-0 gap-5 lg:grid-cols-2">
        {page?.items.map((candidate) => (
          <Card key={candidate.candidateId}>
            <div className="mb-4 flex flex-wrap gap-2">
              <Badge>{candidate.classification}</Badge>
              <Badge>{candidate.reviewStatus}</Badge>
            </div>
            <h2 className="break-words font-semibold">
              <Link to={`/admin/duplicate-candidates/${candidate.candidateId}`}>
                {candidate.sourceTitle} ↔ {candidate.duplicateTitle}
              </Link>
            </h2>
            <p className="my-3 text-sm">
              {candidate.sourceCategory && categories[candidate.sourceCategory]} /{' '}
              {candidate.duplicateCategory && categories[candidate.duplicateCategory]}
            </p>
            <Scores candidate={candidate} />
            <p className="mt-3 text-xs text-slate-600">
              Last checked {formatDate(candidate.lastCheckedAt, true)}
            </p>
            <Link
              className="mt-4 inline-block font-semibold text-teal-700"
              to={`/admin/duplicate-candidates/${candidate.candidateId}`}
            >
              Compare evidence
            </Link>
          </Card>
        ))}
      </div>
      {page?.nextCursor && (
        <button
          className="action-link"
          onClick={() => {
            setPage(null)
            setCursor(page.nextCursor)
          }}
        >
          Next page
        </button>
      )}
      {cursor && (
        <button
          className="action-link"
          onClick={() => {
            setPage(null)
            setCursor(null)
          }}
        >
          First page
        </button>
      )}
    </section>
  )
}

export function DuplicateCandidateDetailPage() {
  const { candidateId = '' } = useParams()
  const [detail, setDetail] = useState<CandidateDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    duplicateService
      .detail(candidateId)
      .then((value) => {
        if (active) {
          setDetail(value)
          setError(null)
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Comparison unavailable')
      })
    return () => {
      active = false
    }
  }, [candidateId, reload])
  async function action(kind: 'dismiss' | 'reviewed' | 'rerun') {
    if (busy || !detail || detail.candidateId !== candidateId) return
    setBusy(true)
    setNotice(null)
    setError(null)
    try {
      if (kind === 'rerun') {
        const value = await duplicateService.recheck(detail.sourceComplaintId)
        setNotice(`Matching state: ${value.processing.state}`)
      } else {
        await duplicateService.review(candidateId, kind)
        setNotice('Review decision saved. Complaints remain separate.')
      }
      setReload((value) => value + 1)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="mx-auto max-w-6xl space-y-6 px-4 py-10 sm:px-6">
      <Link className="text-teal-700" to="/admin/duplicate-candidates">
        ← Back to candidates
      </Link>
      <PageHeader
        title="Compare duplicate candidate"
        description="Administrator-only evidence. Suggestions do not establish object identity. No automatic merge, incident assignment or priority updates."
      />
      <FormMessage error={error} success={notice} />
      {error && (
        <button
          className="action-link"
          onClick={() => {
            setError(null)
            setReload((value) => value + 1)
          }}
        >
          Retry comparison
        </button>
      )}
      {(!detail || detail.candidateId !== candidateId) && !error && <Skeleton />}
      {detail && detail.candidateId === candidateId && (
        <>
          <CandidateIncidentActions
            detail={detail}
            onRefresh={() => setReload((value) => value + 1)}
          />
          <Card>
            <div className="mb-4 flex flex-wrap gap-2">
              <Badge>{detail.classification}</Badge>
              <Badge>{detail.reviewStatus}</Badge>
            </div>
            <Scores candidate={detail} />
            <p className="mt-4 text-sm">Category compatibility: {detail.categoryCompatibility}</p>
            <p className="text-sm">
              Effective weights:{' '}
              {Object.entries(detail.effectiveWeights)
                .map(([key, value]) => `${key} ${value.toFixed(2)}`)
                .join(', ')}
            </p>
            <ul className="my-4 list-disc space-y-2 pl-5 text-sm">
              {[...detail.explanation, ...detail.indicators].map((text, index) => (
                <li key={index}>{text}</li>
              ))}
            </ul>
            <p className="break-all text-xs text-slate-600">
              Method: {detail.method}
              <br />
              Model: {detail.modelVersion}
              <br />
              Config: {detail.configVersion}
              <br />
              Last checked: {formatDate(detail.lastCheckedAt, true)}
              <br />
              Reviewed: {detail.reviewedAt ? formatDate(detail.reviewedAt, true) : 'Not reviewed'}
            </p>
            {detail.processing.some(
              (job) => !job || job.state !== 'COMPLETE' || job.report?.incomplete,
            ) && (
              <p role="status" className="mt-4 text-amber-900">
                Matching is pending, failed or incomplete for at least one complaint. Saved
                candidates are not exhaustive; check timestamps and recheck as needed.
              </p>
            )}
          </Card>
          <div className="grid min-w-0 gap-6 md:grid-cols-2">
            {detail.complaints.map((complaint) => (
              <Card key={complaint.complaintId}>
                <h2 className="break-words text-xl font-semibold">{complaint.title}</h2>
                <p className="my-3 text-sm">
                  {categories[complaint.category]} · {complaint.status}
                </p>
                <p className="whitespace-pre-wrap break-words text-sm">{complaint.description}</p>
                <p className="my-4 text-sm">
                  Location: {complaint.latitude}, {complaint.longitude}
                </p>
                <ComplaintImageGallery
                  images={complaint.images.map((image) => ({
                    ...image,
                    requiresAuth: true,
                    alt: `Private evidence for ${complaint.title}`,
                  }))}
                />
              </Card>
            ))}
          </div>
          <div className="flex flex-wrap gap-4">
            <button className="action-link" disabled={busy} onClick={() => void action('dismiss')}>
              Dismiss candidate
            </button>
            <button className="action-link" disabled={busy} onClick={() => void action('reviewed')}>
              Mark reviewed possible duplicate
            </button>
            <button className="action-link" disabled={busy} onClick={() => void action('rerun')}>
              Rerun matching
            </button>
          </div>
        </>
      )}
    </section>
  )
}
