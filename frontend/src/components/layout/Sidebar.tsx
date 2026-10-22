import {
  Bell,
  Compass,
  FileText,
  LayoutDashboard,
  PlusCircle,
  UserRound,
  ShieldCheck,
  Building2,
  GitMerge,
  Layers,
  ListChecks,
  ChartNoAxesCombined,
  MapPinned,
  Workflow,
  ClipboardCheck,
  Repeat2,
  Scale,
  ChevronDown,
  Gauge,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
type Item = readonly [string, string, LucideIcon]
const citizen: Item[] = [
  ['Dashboard', '/citizen/dashboard', LayoutDashboard],
  ['Report an Issue', '/citizen/report', PlusCircle],
  ['My Complaints', '/citizen/complaints', FileText],
  ['Nearby Issues', '/citizen/nearby', Compass],
  ['Repair verification', '/citizen/verification', ShieldCheck],
  ['Notifications', '/citizen/notifications', Bell],
  ['Profile', '/citizen/profile', UserRound],
]
const officer: Item[] = [
  ['Dashboard', '/officer/dashboard', LayoutDashboard],
  ['My Assigned Work', '/officer/dashboard#assigned-work', ListChecks],
  ['Notifications', '/notifications', Bell],
  ['Profile', '/profile', UserRound],
]
const adminMain: Item[] = [
  ['Command Center', '/admin/command-center', LayoutDashboard],
  ['Incidents', '/admin/incidents', Layers],
  ['Priorities', '/admin/priorities', Gauge],
]
const adminGroups: { title: string; items: Item[] }[] = [
  {
    title: 'Teams & operations',
    items: [
      ['Departments', '/admin/departments', Building2],
      ['Assignments', '/admin/assignments', Users],
      ['Workflows', '/admin/workflows', Workflow],
      ['Repair verification', '/admin/repair-verification', ShieldCheck],
    ],
  },
  {
    title: 'Review & quality',
    items: [
      ['Duplicate review', '/admin/duplicate-candidates', GitMerge],
      ['Recurrence review', '/admin/recurrences', Repeat2],
      ['Publication review', '/admin/publication-review', ClipboardCheck],
    ],
  },
  {
    title: 'Analytics & maps',
    items: [
      ['Complaint trends', '/admin/analytics/complaint-trends', ChartNoAxesCombined],
      ['Incident analytics', '/admin/analytics/incidents', Layers],
      ['Priority distribution', '/admin/analytics/priorities', Gauge],
      ['Department workload', '/admin/analytics/departments', Building2],
      ['Officer workload', '/admin/analytics/officers', Users],
      ['SLA monitoring', '/admin/analytics/sla', ClipboardCheck],
      ['Backlog', '/admin/analytics/backlog', ListChecks],
      ['Response times', '/admin/analytics/response-times', ChartNoAxesCombined],
      ['Hotspots', '/admin/hotspots', MapPinned],
      ['Geographic fairness', '/admin/fairness', Scale],
      ['Reports', '/admin/reports', FileText],
    ],
  },
]
export function Sidebar({
  onNavigate,
  role = 'CITIZEN',
  compact = false,
}: {
  onNavigate?: () => void
  role?: string
  compact?: boolean
}) {
  const { pathname, hash } = useLocation()
  const item = ([label, to, Icon]: Item) => (
    <NavLink
      key={to}
      to={to}
      onClick={onNavigate}
      title={compact ? label : undefined}
      aria-label={compact ? label : undefined}
      className={({ isActive }) =>
        `sidebar-link ${isActive && (!to.includes('#') || hash === '#assigned-work') ? 'active' : ''}`
      }
    >
      <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
      <span className={compact ? 'sr-only' : ''}>{label}</span>
    </NavLink>
  )
  return (
    <nav
      aria-label={`${role === 'ADMIN' ? 'Administrator' : role === 'OFFICER' ? 'Officer' : 'Citizen'} navigation`}
      className="sidebar-navigation"
    >
      {(role === 'ADMIN' ? adminMain : role === 'OFFICER' ? officer : citizen).map(item)}
      {role === 'ADMIN' &&
        adminGroups.map((group) => (
          <details
            className="nav-group"
            key={group.title}
            open={group.items.some(([, to]) => pathname.startsWith(to))}
          >
            <summary title={compact ? group.title : undefined}>
              {compact ? <Layers size={19} aria-label={group.title} /> : group.title}
              {!compact && <ChevronDown size={14} aria-hidden="true" />}
            </summary>
            <div className="nav-group-items">{group.items.map(item)}</div>
          </details>
        ))}
      {role === 'ADMIN' && (
        <div className="sidebar-secondary">
          {item(['Workspace overview', '/admin/dashboard', Compass])}
          {item(['Notifications', '/notifications', Bell])}
          {item(['Profile', '/profile', UserRound])}
        </div>
      )}
    </nav>
  )
}
