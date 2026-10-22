import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useCitizen } from '../auth/CitizenContext'
import { useComplaintSearch } from '../hooks/useComplaintSearch'
import { complaintService, type ComplaintPage } from '../services/complaintService'
import type { Complaint } from '../types/complaint'
import { ComplaintCard, ComplaintFilters } from '../components/complaints/ComplaintComponents'
import { type FilterValues } from '../utils/complaints'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { Breadcrumbs, EmptyState, PageHeader, Skeleton } from '../components/common/UI'
import { ErrorState } from '../components/common/ErrorState'
import { FormMessage } from '../components/common/FormParts'
import { Button } from '../components/common/Button'

export function MyComplaintsPage() {
  const { demo } = useCitizen()
  const [params, setParams] = useSearchParams()
  const filters: FilterValues = {
    search: params.get('q') ?? '',
    category: params.get('category') ?? '',
    status: params.get('status') ?? '',
    severity: params.get('severity') ?? '',
    dateFrom: params.get('dateFrom') ?? '',
    dateTo: params.get('dateTo') ?? '',
    sort: params.get('sort') ?? 'newest',
  }
  const search = useDebouncedValue(filters.search)
  const { data, error, loading, retry } = useComplaintSearch(demo, { ...filters, search })
  function setFilters(next: FilterValues) {
    const value = new URLSearchParams()
    Object.entries(next).forEach(([key, text]) => {
      if (text && !(key === 'sort' && text === 'newest'))
        value.set(key === 'search' ? 'q' : key, text)
    })
    setParams(value, { replace: true })
  }
  const [pages, setPages] = useState<{
    first?: ComplaintPage
    items: Complaint[]
    nextCursor: string | null
  }>({ items: [], nextCursor: null })
  const [busy, setBusy] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  const locked = useRef(false)
  const items = pages.first === data ? pages.items : (data?.items ?? [])
  const cursor = pages.first === data ? pages.nextCursor : data?.nextCursor
  const filtered = items
  const hasFilters = Boolean(
    filters.search.trim() ||
    filters.category ||
    filters.status ||
    filters.severity ||
    filters.dateFrom ||
    filters.dateTo,
  )
  const searchPending = filters.search !== search
  async function loadMore() {
    if (!cursor || locked.current) return
    locked.current = true
    setBusy(true)
    setMoreError(null)
    try {
      const page = await complaintService.list(demo, cursor, { ...filters, search })
      const combined = [...items, ...page.items]
      setPages({
        first: data,
        items: combined.filter(
          (item, index) =>
            combined.findIndex((other) => other.complaintId === item.complaintId) === index,
        ),
        nextCursor: page.nextCursor,
      })
    } catch (reason) {
      setMoreError(reason instanceof Error ? reason.message : 'Could not load more complaints.')
    } finally {
      locked.current = false
      setBusy(false)
    }
  }
  return (
    <>
      <Breadcrumbs current="My Complaints" />
      <PageHeader
        title="My Complaints"
        description={
          demo
            ? 'Explore fictional complaints. These are not your reports.'
            : 'Search your reports, follow their progress, and find the details you need.'
        }
        action={
          <Link className="action-link" to="/citizen/report">
            Report an Issue
          </Link>
        }
      />
      <ComplaintFilters value={filters} onChange={setFilters} />
      <button
        type="button"
        className="text-sm font-semibold text-teal-700"
        onClick={retry}
        disabled={busy || loading}
      >
        Refresh complaints
      </button>
      {searchPending && (
        <p role="status" className="text-sm text-slate-600">
          Updating search…
        </p>
      )}
      {loading ? (
        <Skeleton />
      ) : error ? (
        <ErrorState title="Complaints unavailable" message={error} onRetry={retry} />
      ) : (
        <>
          <p role="status" className="text-sm text-slate-600">
            {data?.total ?? filtered.length} {demo ? 'simulated' : 'account'} complaints matching ·{' '}
            {items.length} loaded{cursor ? ' · more available' : ''}
          </p>
          {filtered.length ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {filtered.map((complaint) => (
                <ComplaintCard key={complaint.complaintId} complaint={complaint} />
              ))}
            </div>
          ) : (
            <EmptyState title={hasFilters ? 'No matching complaints' : 'No complaints yet'}>
              {hasFilters
                ? 'Try another search or clear filters to return to your full history.'
                : 'Your first saved complaint will appear here. Report an issue to get started.'}
            </EmptyState>
          )}
          <FormMessage error={moreError} />
          {cursor && (
            <Button disabled={busy || searchPending} onClick={() => void loadMore()}>
              {busy ? 'Loading more…' : 'Load more complaints'}
            </Button>
          )}
        </>
      )}
    </>
  )
}
