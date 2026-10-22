import { lazy, Suspense, useCallback, useState } from 'react'
import { Bell, Compass, FileText, PlusCircle, ArrowUpRight, ChevronDown } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useCitizen } from '../auth/CitizenContext'
import { useResource } from '../hooks/useResource'
import { complaintService } from '../services/complaintService'
import { notificationService } from '../services/notificationService'
import { Card, EmptyState, PageHeader, Select, Skeleton } from '../components/common/UI'
import { ErrorState } from '../components/common/ErrorState'
import { ComplaintCard } from '../components/complaints/ComplaintComponents'
import { StatCard } from '../components/dashboard/DashboardComponents'
const AnalyticsCharts = lazy(() =>
  import('../components/dashboard/AnalyticsCharts').then((m) => ({ default: m.AnalyticsCharts })),
)
export function CitizenDashboard() {
  const { user } = useAuth()
  const { demo } = useCitizen()
  const [days, setDays] = useState(30)
  const [analyticsOpen, setAnalyticsOpen] = useState(false)
  const loader = useCallback(() => complaintService.summary(demo, days), [demo, days])
  const notificationsLoader = useCallback(() => notificationService.list(demo), [demo])
  const notifications = useResource(notificationsLoader)
  const { data, error, loading, retry } = useResource(loader)
  return (
    <>
      <PageHeader
        title="Citizen dashboard"
        description={`Welcome back, ${user?.display_name}! Here’s where your reports stand.`}
        action={
          <Link className="action-link" to="/citizen/report">
            <PlusCircle size={17} aria-hidden="true" />
            Report New Issue
          </Link>
        }
      />
      {loading ? (
        <Skeleton />
      ) : error ? (
        <ErrorState title="Dashboard unavailable" message={error} onRetry={retry} />
      ) : (
        <>
          <section
            aria-label={demo ? 'Simulated complaint statistics' : 'Account complaint statistics'}
            className="metric-grid grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
          >
            <StatCard title="Total complaints" count={data!.total} sample={demo} />
            <StatCard title="Under review" count={data!.counts.UNDER_REVIEW ?? 0} sample={demo} />
            <StatCard title="In progress" count={data!.counts.IN_PROGRESS ?? 0} sample={demo} />
            <StatCard title="Resolved" count={data!.counts.RESOLVED ?? 0} sample={demo} />
          </section>
          <div className="citizen-main-grid">
            <section className="space-y-4">
              <div className="section-header">
                <div>
                  <h2>{demo ? 'Recent sample complaints' : 'Recent complaints'}</h2>
                  <p>The latest from your neighborhood reports.</p>
                </div>
                <Link to="/citizen/complaints" aria-label="View all · View My Complaints">
                  View all <ArrowUpRight size={15} aria-hidden="true" />
                </Link>
              </div>
              {data!.recent.length ? (
                <div className="space-y-3">
                  {[...data!.recent]
                    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
                    .slice(0, 3)
                    .map((item) => (
                      <ComplaintCard key={item.complaintId} complaint={item} compact />
                    ))}
                </div>
              ) : (
                <EmptyState title="No complaints yet">
                  See something that needs attention?{' '}
                  <Link className="font-semibold text-teal-700" to="/citizen/report">
                    Report an Issue
                  </Link>{' '}
                  to get started.
                </EmptyState>
              )}
              <button className="secondary-button" onClick={retry}>
                Refresh dashboard
              </button>
            </section>
            <aside className="space-y-5">
              <Card className="nearby-prompt">
                <Compass size={26} strokeWidth={1.5} aria-hidden="true" />
                <h2>Look around your community</h2>
                <p>Explore reviewed public issues and see what’s happening nearby.</p>
                <Link to="/citizen/nearby">
                  Explore Nearby Issues <ArrowUpRight size={16} aria-hidden="true" />
                </Link>
              </Card>
              <Card>
                <div className="section-header">
                  <h2>Notifications</h2>
                  <Bell size={17} className="text-slate-500" aria-hidden="true" />
                </div>
                {notifications.loading ? (
                  <p className="text-sm text-slate-500" role="status">
                    Loading notifications…
                  </p>
                ) : notifications.error ? (
                  <ErrorState message={notifications.error} onRetry={notifications.retry} />
                ) : notifications.data?.length ? (
                  <ul className="notification-preview">
                    {notifications.data.slice(0, 3).map((n) => (
                      <li key={n.notificationId}>
                        <p>{n.title}</p>
                        <span>{n.message}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm leading-6 text-slate-500">
                    You’re all caught up. Important updates will appear here.
                  </p>
                )}
                <Link
                  className="mt-5 inline-flex items-center gap-2 text-xs font-semibold text-teal-700"
                  to="/citizen/notifications"
                >
                  View Notifications <ArrowUpRight size={14} aria-hidden="true" />
                </Link>
              </Card>
            </aside>
          </div>
          <details
            className="analytics-disclosure"
            open={analyticsOpen}
            onToggle={(e) => setAnalyticsOpen(e.currentTarget.open)}
          >
            <summary>
              <span>
                <FileText size={18} aria-hidden="true" />
                Your reporting insights
              </span>
              <ChevronDown size={17} aria-hidden="true" />
            </summary>
            {analyticsOpen && (
              <div className="space-y-5 pt-5">
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <Select
                    id="trend-period"
                    label="Submission trend period"
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                  >
                    {[7, 30, 90].map((period) => (
                      <option key={period} value={period}>
                        Last {period} days
                      </option>
                    ))}
                  </Select>
                  <p className="text-xs text-slate-500">
                    Submitted: {data!.counts.SUBMITTED ?? 0} · Assigned:{' '}
                    {data!.counts.ASSIGNED ?? 0}
                  </p>
                </div>
                <Suspense fallback={<Skeleton />}>
                  <AnalyticsCharts summary={data!} />
                </Suspense>
              </div>
            )}
          </details>
        </>
      )}
    </>
  )
}
