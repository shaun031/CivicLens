import { useEffect, useRef, useState } from 'react'
import type { Chart as ChartInstance } from 'chart.js'
import type { ComplaintSummary } from '../../services/complaintService'
import { categories, statuses } from '../../types/complaint'
import { Card } from '../common/UI'

export function Chart({
  title,
  rows,
  line = false,
  measure = 'Complaints',
}: {
  title: string
  rows: { label: string; count: number }[]
  line?: boolean
  measure?: string
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [failed, setFailed] = useState(false)
  const rowsKey = JSON.stringify(rows)
  useEffect(() => {
    let active = true
    let chart: ChartInstance | undefined
    // jsdom has no canvas renderer. The accessible table is also the non-canvas fallback.
    const values = JSON.parse(rowsKey) as typeof rows
    if (typeof CanvasRenderingContext2D === 'undefined' || !values.some((row) => row.count > 0))
      return
    void import('chart.js')
      .then(
        ({
          Chart,
          BarController,
          BarElement,
          LineController,
          LineElement,
          PointElement,
          CategoryScale,
          LinearScale,
          Tooltip,
          Legend,
        }) => {
          if (!active || !canvas.current) return
          Chart.register(
            BarController,
            BarElement,
            LineController,
            LineElement,
            PointElement,
            CategoryScale,
            LinearScale,
            Tooltip,
            Legend,
          )
          setFailed(false)
          chart = new Chart(canvas.current, {
            type: line ? 'line' : 'bar',
            data: {
              labels: values.map((row) => row.label),
              datasets: [
                {
                  label: measure,
                  data: values.map((row) => row.count),
                  backgroundColor: values.map((row) =>
                    row.label === 'CRITICAL' || row.label === 'HIGH'
                      ? '#dc2626'
                      : row.label === 'MEDIUM'
                        ? '#f59e0b'
                        : getComputedStyle(document.documentElement)
                            .getPropertyValue('--action')
                            .trim() || '#0f766e',
                  ),
                  borderColor:
                    getComputedStyle(document.documentElement)
                      .getPropertyValue('--action')
                      .trim() || '#0f766e',
                  borderWidth: 2,
                  pointRadius: 2,
                  borderRadius: line ? undefined : 5,
                },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              animation: false,
              plugins: { legend: { display: false } },
              scales: {
                x: {
                  grid: { display: false },
                  ticks: { color: '#64748b', maxRotation: 30, font: { size: 10 } },
                  border: { display: false },
                },
                y: {
                  beginAtZero: true,
                  ticks: { precision: 0, color: '#64748b', font: { size: 10 } },
                  grid: { color: '#f1f5f9' },
                  border: { display: false },
                },
              },
            },
          })
        },
      )
      .catch(() => {
        if (active) setFailed(true)
      })
    return () => {
      active = false
      chart?.destroy()
    }
  }, [rowsKey, line, measure])
  return (
    <Card>
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      {failed && (
        <p role="status" className="mb-3 text-sm text-slate-600">
          Chart display unavailable. The data table below remains available.
        </p>
      )}
      {rows.some((row) => row.count) ? (
        <>
          <div className="relative h-60 min-w-0">
            <canvas
              className="max-w-full"
              ref={canvas}
              role="img"
              aria-label={title + ': ' + rows.map((row) => row.label + ' ' + row.count).join(', ')}
            />
          </div>
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer font-semibold">
              View {title.toLowerCase()} data
            </summary>
            <div
              className="max-h-60 overflow-auto"
              tabIndex={0}
              role="region"
              aria-label={`${title} data table`}
            >
              <table className="mt-3 w-full text-left">
                <caption className="sr-only">{title}</caption>
                <thead>
                  <tr>
                    <th scope="col">Group</th>
                    <th scope="col">{measure}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.label}>
                      <th className="py-1 font-normal" scope="row">
                        {row.label}
                      </th>
                      <td>{row.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <div className="chart-empty">
          <h3>No chart data</h3>
          <p>No {measure.toLowerCase()} in this group or period.</p>
        </div>
      )}
    </Card>
  )
}
export function AnalyticsCharts({ summary }: { summary: ComplaintSummary }) {
  return (
    <section
      aria-label="Personal complaint analytics"
      className="grid min-w-0 gap-4 xl:grid-cols-3"
    >
      <Chart
        title="Complaints by category"
        rows={(summary.byCategory ?? []).map((row) => ({
          label: categories[row.category],
          count: row.count,
        }))}
      />
      <Chart
        title="Complaints by status"
        rows={Object.entries(statuses).map(([key, label]) => ({
          label,
          count: summary.counts[key as keyof typeof statuses] ?? 0,
        }))}
      />
      <Chart
        title="Submission trend (UTC days)"
        line
        rows={(summary.submissionTrend ?? []).map((row) => ({ label: row.date, count: row.count }))}
      />
    </section>
  )
}
