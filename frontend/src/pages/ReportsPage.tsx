import { useCallback, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { analyticsService } from '../services/analyticsService'
import { useResource } from '../hooks/useResource'
import { AnalyticsFilterBar } from '../components/analytics/AnalyticsFilterBar'
import { AnalyticsTable } from '../components/analytics/AnalyticsComponents'
import { AnalyticsNavigation } from './AnalyticsPage'
import { Alert, Card, PageHeader, Skeleton } from '../components/common/UI'
import { Button } from '../components/common/Button'

export function ReportsPage() {
  const { user } = useAuth()
  const [query, setQuery] = useSearchParams()
  const key = query.toString()
  const [kind, setKind] = useState('citywide')
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')
  const config = useResource(
    useCallback(() => {
      if (!user?.id) return Promise.reject(new Error('Administrator session required.'))
      return analyticsService.config()
    }, [user?.id]),
  )
  const preview = useResource(
    useCallback(() => {
      if (!user?.id) return Promise.reject(new Error('Administrator session required.'))
      return analyticsService.preview(kind, new URLSearchParams(key))
    }, [kind, key, user?.id]),
  )
  async function download() {
    setError('')
    setExporting(true)
    try {
      const blob = await analyticsService.export(kind, new URLSearchParams(key))
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `civiclens-${kind}-${new Date().toISOString().slice(0, 10)}.csv`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Export failed. No file was generated.')
    } finally {
      setExporting(false)
    }
  }
  return (
    <section className="mx-auto max-w-7xl space-y-6 px-4 py-9 sm:px-6">
      <Link className="text-teal-700" to="/admin/dashboard">
        Administrator dashboard
      </Link>
      <PageHeader
        title="Administrative reports"
        description="Allowlisted aggregate reports only. No raw database dump, citizen contact data, private report descriptions, image keys or exact private report coordinates."
      />
      <AnalyticsNavigation />
      <Card>
        <label className="font-semibold">
          Report type
          <select
            className="ml-3 rounded-lg border border-slate-300 p-2"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            {(config.data?.reports ?? [{ type: 'citywide', view: 'overview' }]).map((r) => (
              <option key={r.type} value={r.type}>
                {r.type}
              </option>
            ))}
          </select>
        </label>
      </Card>
      <AnalyticsFilterBar
        key={key + kind}
        query={query}
        config={config.data}
        geographic={kind === 'hotspots'}
        onApply={setQuery}
      />
      <div className="flex gap-3">
        <Button variant="secondary" onClick={preview.retry}>
          Generate report preview
        </Button>
        <Button
          disabled={exporting || !preview.data || preview.loading}
          onClick={() => {
            void download()
          }}
        >
          {exporting ? 'Exporting…' : 'Export CSV'}
        </Button>
      </div>
      {preview.loading && <Skeleton />}
      {(preview.error || error || config.error) && (
        <div role="alert">
          <Alert>{error || preview.error || config.error} No successful export is claimed.</Alert>
        </div>
      )}
      {preview.data && (
        <>
          <Card>
            <h2 className="font-semibold">{preview.data.title}</h2>
            <p className="mt-2 text-sm">
              Generated UTC {preview.data.generatedAt} · reporting zone{' '}
              {preview.data.reportingTimezone} · {preview.data.sampleSize} rows · source revision{' '}
              {preview.data.dataFreshness.sourceRevision}
            </p>
            <p className="mt-2 text-sm">{preview.data.definitions}</p>
            {preview.data.window && (
              <p className="mt-2 break-words text-sm">
                UTC window: {preview.data.window.startInclusive} (inclusive) to{' '}
                {preview.data.window.endExclusive} (exclusive).
              </p>
            )}
            {preview.data.filters && (
              <details className="mt-3 text-sm">
                <summary>Applied report filters</summary>
                <p className="mt-2 break-words">{JSON.stringify(preview.data.filters)}</p>
              </details>
            )}
            <p className="mt-2 text-sm">
              {preview.data.pageOnly
                ? 'This is a bounded detail page, not the complete dataset. Use Next report page for additional rows.'
                : 'Complete bounded aggregate response.'}{' '}
              Missing capacity/outcomes remain unavailable, not zero.
            </p>
          </Card>
          <AnalyticsTable
            title="Report preview"
            rows={preview.data.rows}
            columns={preview.data.columns.map((k) => [k, k])}
          />
          {(preview.data.nextCursor || query.has('cursor')) && (
            <div className="flex gap-3">
              <Button
                variant="secondary"
                onClick={() => {
                  const next = new URLSearchParams(key)
                  next.delete('cursor')
                  setQuery(next)
                }}
              >
                First report page
              </Button>
              <Button
                disabled={!preview.data.nextCursor}
                onClick={() => {
                  const next = new URLSearchParams(key)
                  if (preview.data?.nextCursor) next.set('cursor', preview.data.nextCursor)
                  setQuery(next)
                }}
              >
                Next report page
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
