import { Link } from 'react-router-dom'
import { Card } from '../common/UI'
import type { AnalyticsResult, AnalyticsRow, ChartRow } from '../../services/analyticsService'
import { Chart } from '../dashboard/AnalyticsCharts'
import { valueLabel } from '../../services/analyticsFormatting'

export function DataFreshnessIndicator({ data }: { data: AnalyticsResult }) {
  return (
    <details className="data-freshness">
      <summary>Source snapshot & reporting context</summary>
      <div className="mt-3">
        <p className="font-semibold">
          Calculated{' '}
          {new Date(data.calculatedAt).toLocaleString(undefined, {
            timeZone: data.reportingTimezone,
          })}{' '}
          · {data.reportingTimezone}
        </p>
        <p className="mt-1 text-sm">
          {data.scope} ·{' '}
          {data.dataFreshness.mode === 'DIRECT_SNAPSHOT'
            ? 'Consistent source snapshot'
            : 'Bounded cloud projection'}{' '}
          · revision {data.dataFreshness.sourceRevision}
        </p>
        <p className="mt-1 text-sm">
          UTC window: {data.window.startInclusive} (inclusive) to {data.window.endExclusive}{' '}
          (exclusive).
        </p>
        <p className="mt-1 text-sm">
          Stale/unavailable priorities: {data.dataFreshness.stalePriorityCount}. Counts are
          creation-date cohorts with current membership and assignment, not historical citywide
          snapshots.
        </p>
        {data.dataFreshness.projectionCalculatedAt && (
          <p>
            Projection generated {data.dataFreshness.projectionCalculatedAt}; eventual consistency
            applies.
          </p>
        )}
      </div>
    </details>
  )
}
export function AnalyticsStats({
  data,
  fields,
}: {
  data: AnalyticsRow
  fields: [string, string][]
}) {
  return (
    <div
      className={`metric-grid grid min-w-0 gap-4 sm:grid-cols-2 ${fields.length === 4 ? 'xl:grid-cols-4' : 'xl:grid-cols-3'}`}
    >
      {fields.map(([key, label]) => (
        <Card key={key}>
          <h2 className="text-sm font-medium text-slate-600">{label}</h2>
          <p className="mt-3 break-words text-2xl font-bold text-slate-950">
            {valueLabel(data[key])}
          </p>
        </Card>
      ))}
    </div>
  )
}
export function AnalyticsTable({
  title,
  rows,
  columns,
}: {
  title: string
  rows: AnalyticsRow[]
  columns: [string, string][]
}) {
  return (
    <Card>
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      {rows.length ? (
        <div
          className="max-w-full overflow-auto focus-visible:outline-2 focus-visible:outline-teal-700"
          tabIndex={0}
          role="region"
          aria-label={`${title} scrollable table`}
        >
          <table
            className={`w-full ${columns.length > 4 ? 'min-w-[44rem]' : 'min-w-80'} text-left text-sm`}
          >
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                {columns.map(([key, label]) => (
                  <th key={key} className="p-2" scope="col">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  key={
                    String(
                      row.incidentId ?? row.membershipId ?? row.departmentId ?? row.cell ?? index,
                    ) +
                    ':' +
                    index
                  }
                  className="border-t border-slate-100"
                >
                  {columns.map(([key]) => (
                    <td key={key} className="max-w-80 break-words p-2">
                      {key === 'incidentId' && typeof row[key] === 'string' ? (
                        <Link
                          className="text-teal-700 underline"
                          to={`/admin/incidents/${row[key]}`}
                        >
                          {row[key]}
                        </Link>
                      ) : key === 'capacity' && row[key] == null ? (
                        'Not configured'
                      ) : (
                        valueLabel(row[key])
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-slate-600">No records in this scope.</p>
      )}
    </Card>
  )
}
export function AnalyticsChart({
  title,
  rows = [],
  measure = 'Incidents',
  line = false,
}: {
  title: string
  rows?: ChartRow[]
  measure?: string
  line?: boolean
}) {
  return <Chart title={title} rows={rows} measure={measure} line={line} />
}
