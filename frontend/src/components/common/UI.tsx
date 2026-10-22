import { FileSearch, ChevronRight } from 'lucide-react'
import type { ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { Link } from 'react-router-dom'
import { fieldClass } from './FormParts'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`ui-card ${className}`}>{children}</div>
}
export function Badge({ children }: { children: ReactNode }) {
  return <span className="ui-badge">{children}</span>
}
export function Alert({ children }: { children: ReactNode }) {
  return <div className="ui-notice">{children}</div>
}
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card className="py-10 text-center">
      <FileSearch className="mx-auto mb-3 text-slate-400" size={32} aria-hidden="true" />
      <h2 className="font-semibold text-slate-900">{title}</h2>
      <div className="mt-2 text-sm leading-6 text-slate-600">{children}</div>
    </Card>
  )
}
export function Skeleton() {
  return (
    <div role="status" aria-label="Loading content" className="space-y-4">
      <span className="sr-only">Loading content…</span>
      {[1, 2, 3].map((item) => (
        <div key={item} className="loading-skeleton h-28 rounded-2xl" />
      ))}
    </div>
  )
}
export function PageHeader({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow mb-2">Community infrastructure</p>
        <h1>{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
      </div>
      {action}
    </header>
  )
}
export function Breadcrumbs({ current }: { current: string }) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="mb-5 flex flex-wrap items-center gap-2 text-sm text-slate-600"
    >
      <Link to="/citizen/dashboard">Dashboard</Link>
      <ChevronRight size={14} aria-hidden="true" />
      <span aria-current="page">{current}</span>
    </nav>
  )
}
export function Select({
  label,
  id,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; id: string }) {
  return (
    <label className="block text-sm font-medium text-slate-700" htmlFor={id}>
      {label}
      <select className={fieldClass} id={id} {...props} />
    </label>
  )
}
export function Textarea({
  label,
  id,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; id: string }) {
  return (
    <label className="block text-sm font-medium text-slate-700" htmlFor={id}>
      {label}
      <textarea className={fieldClass} id={id} {...props} />
    </label>
  )
}
export function InlineError({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p className="mt-1 text-sm text-red-800" id={`${id}-error`}>
      {message}
    </p>
  ) : null
}

export function PriorityBadge({ band, stale = false }: { band?: string; stale?: boolean }) {
  const tone = stale
    ? 'unknown'
    : ['CRITICAL', 'HIGH'].includes(band ?? '')
      ? 'urgent'
      : band === 'MEDIUM'
        ? 'warning'
        : 'neutral'
  return (
    <span className={`priority-badge priority-${tone}`}>
      <span aria-hidden="true" />
      {stale ? 'PRIORITY PENDING / STALE' : (band ?? 'Not assessed')}
    </span>
  )
}
