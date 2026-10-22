import { useEffect, useState } from 'react'
import { authRequest } from '../../auth/authClient'
import { Link } from 'react-router-dom'
import {
  MapPin,
  ArrowUpRight,
  Route,
  Droplets,
  Lightbulb,
  Trash2,
  Construction,
  CircleDot,
} from 'lucide-react'
import { categories, statuses } from '../../types/complaint'
import type {
  Complaint,
  ComplaintStatus,
  EvidenceImage,
  ProgressEvent,
  Category,
} from '../../types/complaint'
import { formatDate } from '../../utils/dates'
import { Badge, Card, Select } from '../common/UI'
import { Field } from '../common/FormParts'
import { Modal } from '../common/Modal'
import { emptyFilters, type FilterValues } from '../../utils/complaints'

const statusColors: Record<ComplaintStatus, string> = {
  SUBMITTED: 'bg-teal-50 text-teal-800',
  UNDER_REVIEW: 'bg-amber-50 text-amber-900',
  ASSIGNED: 'bg-slate-100 text-slate-700',
  IN_PROGRESS: 'bg-teal-50 text-teal-800',
  RESOLVED: 'bg-emerald-50 text-emerald-900',
  REJECTED: 'bg-red-50 text-red-900',
}
export function StatusBadge({ status }: { status: ComplaintStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${statusColors[status]}`}
    >
      {statuses[status]}
    </span>
  )
}
export function CategoryIcon({ category }: { category: string }) {
  const icons = {
    POTHOLE: CircleDot,
    DAMAGED_ROAD: Route,
    BROKEN_STREETLIGHT: Lightbulb,
    GARBAGE: Trash2,
    DRAINAGE: Droplets,
    PUBLIC_PROPERTY_DAMAGE: Construction,
  }
  const Icon = icons[category as keyof typeof icons] ?? Construction
  return <Icon size={21} strokeWidth={1.7} aria-hidden="true" />
}
export function ComplaintCard({
  complaint,
  compact = false,
}: {
  complaint: Complaint
  compact?: boolean
}) {
  return (
    <article className={`complaint-card ${compact ? 'compact' : ''}`}>
      <div className="complaint-card-top">
        <span className="category-icon">
          <CategoryIcon category={complaint.category} />
        </span>
        <StatusBadge status={complaint.status} />
      </div>
      {complaint.isSimulated && <Badge>Simulated complaint</Badge>}
      <h2>
        <Link to={`/citizen/complaints/${encodeURIComponent(complaint.complaintId)}`}>
          {complaint.title}
        </Link>
      </h2>
      <p className="complaint-meta">
        {categories[complaint.category]} · {formatDate(complaint.createdAt)}
      </p>
      <p className="complaint-location">
        <MapPin size={14} aria-hidden="true" />
        {complaint.location.addressLabel}
      </p>
      <Link
        className="complaint-detail-link"
        to={`/citizen/complaints/${encodeURIComponent(complaint.complaintId)}`}
      >
        View details<span className="sr-only">: {complaint.title}</span>
        <ArrowUpRight size={15} aria-hidden="true" />
      </Link>
    </article>
  )
}
export function ComplaintCategorySelector({
  value,
  onChange,
  ...props
}: {
  value: string
  onChange: (value: Category | '') => void
  'aria-invalid'?: boolean
  'aria-describedby'?: string
}) {
  return (
    <Select
      label="Complaint category"
      id="category"
      value={value}
      onChange={(event) => onChange(event.target.value as Category | '')}
      {...props}
    >
      <option value="">Choose a category</option>
      {Object.entries(categories).map(([key, label]) => (
        <option key={key} value={key}>
          {label}
        </option>
      ))}
    </Select>
  )
}
export function ComplaintFilters({
  value,
  onChange,
}: {
  value: FilterValues
  onChange: (value: FilterValues) => void
}) {
  const update = (key: keyof FilterValues, text: string) => onChange({ ...value, [key]: text })
  return (
    <Card>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Field
          id="search"
          label="Search complaints"
          type="search"
          value={value.search}
          onChange={(event) => update('search', event.target.value)}
        />
        <Select
          id="category-filter"
          label="Category"
          value={value.category}
          onChange={(event) => update('category', event.target.value)}
        >
          <option value="">All categories</option>
          {Object.entries(categories).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
        <Select
          id="status-filter"
          label="Status"
          value={value.status}
          onChange={(event) => update('status', event.target.value)}
        >
          <option value="">All statuses</option>
          {Object.entries(statuses).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
        <Select
          id="sort"
          label="Sort by"
          value={value.sort}
          onChange={(event) => update('sort', event.target.value)}
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="category">Category (A–Z)</option>
          <option value="status">Status (A–Z)</option>
        </Select>
      </div>
      <details className="mt-4" open={Boolean(value.severity || value.dateFrom || value.dateTo)}>
        <summary className="text-xs font-semibold text-teal-700">More filters</summary>
        <div className="mt-3 grid gap-4 sm:grid-cols-3">
          <Select
            id="severity-filter"
            label="Reported severity"
            value={value.severity ?? ''}
            onChange={(event) => update('severity', event.target.value)}
          >
            <option value="">All severities</option>
            {['LOW', 'MEDIUM', 'HIGH'].map((severity) => (
              <option value={severity} key={severity}>
                {severity}
              </option>
            ))}
          </Select>
          <Field
            id="date-from"
            label="Submitted from"
            type="date"
            value={value.dateFrom ?? ''}
            onChange={(event) => update('dateFrom', event.target.value)}
          />
          <Field
            id="date-to"
            label="Submitted through"
            type="date"
            value={value.dateTo ?? ''}
            onChange={(event) => update('dateTo', event.target.value)}
          />
        </div>
      </details>
      <button
        className="mt-4 text-sm font-semibold text-teal-700"
        onClick={() => onChange(emptyFilters)}
      >
        Clear filters
      </button>
    </Card>
  )
}
export function ComplaintTimeline({ events }: { events: ProgressEvent[] }) {
  const sorted = [...events].sort((a, b) => a.createdAt.localeCompare(b.createdAt))
  return (
    <div>
      <ol className="complaint-timeline">
        {sorted.map((event, index) => (
          <li key={`${event.createdAt}-${index}`}>
            <StatusBadge status={event.status} />
            <p className="mt-1 text-sm text-slate-600">{event.message}</p>
            <time className="text-xs text-slate-600" dateTime={event.createdAt}>
              {formatDate(event.createdAt, true)}
            </time>
          </li>
        ))}
      </ol>
    </div>
  )
}
function GalleryImage({ image }: { image: EvidenceImage }) {
  const [failed, setFailed] = useState(false)
  const [privateUrl, setPrivateUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!image.requiresAuth) return
    let active = true
    let objectUrl: string | null = null
    Promise.resolve()
      .then(() =>
        active ? authRequest<Blob>(image.url, 'GET', undefined, { responseType: 'blob' }) : null,
      )
      .then((blob) => {
        if (!active || !blob) return
        if (blob.type !== 'image/jpeg') {
          setFailed(true)
          return
        }
        objectUrl = URL.createObjectURL(blob)
        setPrivateUrl(objectUrl)
      })
      .catch(() => {
        if (active) setFailed(true)
      })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [image.url, image.requiresAuth])
  if (image.requiresAuth && !privateUrl && !failed)
    return (
      <span role="status" className="block rounded-xl bg-slate-100 p-8 text-sm">
        Loading private evidence…
      </span>
    )
  return failed ? (
    <span className="block rounded-xl bg-slate-100 p-8 text-sm">Image unavailable</span>
  ) : (
    <img
      src={image.requiresAuth ? (privateUrl ?? undefined) : image.url}
      alt={image.alt}
      onError={() => setFailed(true)}
      className="max-h-96 w-full rounded-xl object-contain"
    />
  )
}
export function ComplaintImageGallery({ images }: { images: EvidenceImage[] }) {
  const [preview, setPreview] = useState<EvidenceImage | null>(null)
  if (!images.length) return <p className="text-sm text-slate-600">No photo evidence provided.</p>
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        {images.map((image) => (
          <button
            key={image.url}
            type="button"
            onClick={() => setPreview(image)}
            aria-label={`Preview ${image.alt}`}
          >
            <GalleryImage image={image} />
          </button>
        ))}
      </div>
      {preview && (
        <Modal title="Evidence preview" onClose={() => setPreview(null)}>
          <GalleryImage image={preview} />
        </Modal>
      )}
    </>
  )
}
