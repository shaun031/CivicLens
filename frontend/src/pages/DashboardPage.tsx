import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { authRequest } from '../auth/authClient'
import { FormMessage } from '../components/common/FormParts'
import { PageHeader, Card } from '../components/common/UI'
import { Link } from 'react-router-dom'
import {
  ArrowUpRight,
  LayoutDashboard,
  Layers,
  Users,
  ShieldCheck,
  Workflow,
  FileText,
} from 'lucide-react'
const destinations = [
  {
    title: 'Command Center',
    detail: 'Priorities, incident trends, and department workload.',
    to: '/admin/command-center',
    Icon: LayoutDashboard,
  },
  {
    title: 'Incident management',
    detail: 'Review master incidents, duplicate candidates, and priorities.',
    to: '/admin/incidents',
    Icon: Layers,
  },
  {
    title: 'Departments & assignments',
    detail: 'Configure teams and allocate eligible officers.',
    to: '/admin/departments',
    Icon: Users,
  },
  {
    title: 'Repair verification',
    detail: 'Review submitted evidence and recorded citizen feedback.',
    to: '/admin/repair-verification',
    Icon: ShieldCheck,
  },
  {
    title: 'Workflow monitoring',
    detail: 'Inspect processing stages, failures, and SLA alerts.',
    to: '/admin/workflows',
    Icon: Workflow,
  },
  {
    title: 'Reports & exports',
    detail: 'Generate reports from authorized operational records.',
    to: '/admin/reports',
    Icon: FileText,
  },
]
export function DashboardPage({ portal }: { portal: 'admin' | 'citizen' | 'officer' }) {
  const { user } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [verified, setVerified] = useState(false)
  useEffect(() => {
    let active = true
    authRequest<{ message: string }>(`/portal/${portal}`)
      .then(() => {
        if (active) setVerified(true)
      })
      .catch((reason: unknown) => {
        if (active)
          setError(reason instanceof Error ? reason.message : 'Portal verification failed.')
      })
    return () => {
      active = false
    }
  }, [portal])
  return (
    <section className="space-y-6">
      <PageHeader
        title={`${portal === 'admin' ? 'Administrator' : portal === 'officer' ? 'Officer' : 'Citizen'} dashboard`}
        description={`Welcome, ${user?.display_name}. Choose a workspace to continue.`}
        action={
          <Link to="/admin/command-center" className="action-link">
            Open Command Center <ArrowUpRight size={16} aria-hidden="true" />
          </Link>
        }
      />
      <FormMessage error={error} />
      <p role="status" className="text-xs text-slate-500">
        {verified ? 'Access verified by the backend.' : 'Verifying portal access…'}
      </p>
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {destinations.map(({ title, detail, to, Icon }) => (
          <Card key={to} className="workspace-destination">
            <Icon size={24} strokeWidth={1.6} aria-hidden="true" />
            <h2>{title}</h2>
            <p>{detail}</p>
            <Link to={to}>
              Open workspace <ArrowUpRight size={15} aria-hidden="true" />
              <span className="sr-only">: {title}</span>
            </Link>
          </Card>
        ))}
      </div>
      <details className="analytics-disclosure">
        <summary>Additional review tools</summary>
        <div className="mt-4 flex flex-wrap gap-5 text-sm text-teal-700">
          <Link to="/admin/duplicate-candidates">Review duplicate candidates</Link>
          <Link to="/admin/publication-review">Review public map publication requests</Link>
          <Link to="/admin/priorities">Manage incident priorities</Link>
          <Link to="/admin/assignments">Allocate municipal work</Link>
          <Link to="/admin/recurrences">Recurring infrastructure failures</Link>
          <Link to="/admin/fairness">Geographic service comparison</Link>
        </div>
      </details>
    </section>
  )
}
