import { useCallback, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../auth/authClient'
import { useResource } from '../hooks/useResource'
import {
  workService,
  type Department,
  type DepartmentDetail,
  type WorkDetail,
  type Officer,
} from '../services/workService'
import {
  Card,
  Badge,
  PriorityBadge,
  EmptyState,
  PageHeader,
  Select,
  Skeleton,
  Textarea,
  Alert,
} from '../components/common/UI'
import { Field, FormMessage } from '../components/common/FormParts'
import { Modal } from '../components/common/Modal'
import { ErrorState } from '../components/common/ErrorState'
import { categories } from '../types/complaint'
import { formatDate } from '../utils/dates'
import { ComplaintImageGallery } from '../components/complaints/ComplaintComponents'

const button = 'ui-button ui-button-primary'
const section = 'mx-auto max-w-7xl space-y-6 px-4 py-10 sm:px-6'
const statusOptions = [
  'UNASSIGNED',
  'DEPARTMENT_ASSIGNED',
  'OFFICER_ASSIGNED',
  'IN_PROGRESS',
  'NEEDS_REVIEW',
]
type Operation = {
  title: string
  path: string
  method?: string
  fields?: ReactNode
  payload: (form: FormData) => object
}

export function WorkConfirmation({
  operation,
  onClose,
  onSaved,
}: {
  operation: Operation
  onClose: () => void
  onSaved: () => void
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [frozen, setFrozen] = useState<object | null>(null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setPending(true)
    setError(null)
    try {
      if (
        !frozen &&
        (String(form.get('reason') ?? '').trim().length < 10 || form.get('confirmed') !== 'on')
      )
        throw new Error('Enter a reason of at least10 characters and confirm the change.')
      const body = frozen ?? {
        ...operation.payload(form),
        operationId: crypto.randomUUID(),
        reason: form.get('reason'),
        confirmed: form.get('confirmed') === 'on',
      }
      setFrozen(body)
      await workService.change(operation.path, operation.method ?? 'POST', body)
      onSaved()
      onClose()
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Operation failed. Retry the same request.',
      )
      setConflict(reason instanceof ApiError && reason.status === 409)
    } finally {
      setPending(false)
    }
  }
  return (
    <Modal
      title={operation.title}
      onClose={() => {
        if (!pending) onClose()
      }}
    >
      <form onSubmit={submit} className="space-y-4">
        <p className="text-sm text-slate-600">
          This changes real local municipal work records. Confirm the current versions and explain
          the decision. No citizen notification or final repair approval is sent.
        </p>
        <fieldset disabled={pending || frozen !== null} className="space-y-4">
          {operation.fields}
          <Textarea
            id="work-reason"
            name="reason"
            label="Assignment or progress reason"
            required
            minLength={10}
            maxLength={1000}
          />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" name="confirmed" required className="mt-1" />I confirm this
            municipal work change and its recorded justification.
          </label>
        </fieldset>
        <FormMessage error={error} />
        {conflict && (
          <Alert>
            Close this dialog and refresh before making a new decision. Do not resubmit stale
            versions.
          </Alert>
        )}
        {frozen && !conflict && error && (
          <p className="text-sm">
            Retry sends the exact same operation ID and inputs. Close to refresh and make a new
            decision.
          </p>
        )}
        <button className={button} type="submit" disabled={pending || conflict}>
          {pending
            ? 'Saving…'
            : frozen && error
              ? 'Retry same work operation'
              : 'Confirm and save work change'}
        </button>
      </form>
    </Modal>
  )
}

function AdminLinks() {
  return (
    <details className="related-navigation">
      <summary>Related workspaces</summary>
      <nav aria-label="Municipal management" className="flex flex-wrap gap-4 text-sm text-teal-700">
        <Link to="/admin/dashboard">Administrator dashboard</Link>
        <Link to="/admin/departments">Departments</Link>
        <Link to="/admin/assignments">Assignments</Link>
        <Link to="/admin/priorities">Priorities</Link>
      </nav>
    </details>
  )
}

function DepartmentFields({ department }: { department?: Department }) {
  return (
    <>
      <Field
        id="department-code"
        name="code"
        label="Department code"
        required
        pattern="[A-Z][A-Z0-9_]{2,49}"
        defaultValue={department?.code}
      />
      <Field
        id="department-name"
        name="name"
        label="Department name"
        required
        minLength={3}
        maxLength={100}
        defaultValue={department?.name}
      />
      <Textarea
        id="department-description"
        name="description"
        label="Department description"
        maxLength={1000}
        defaultValue={department?.description}
      />
      <label className="flex gap-2 text-sm">
        <input type="checkbox" name="active" defaultChecked={department?.active ?? true} />
        Active department
      </label>
      <Textarea
        id="department-areas"
        name="areas"
        label="Service-area rectangles (JSON)"
        defaultValue={JSON.stringify(department?.areas ?? [], null, 2)}
      />
      <p className="text-xs text-slate-600">
        Use [] for category-only demonstration mode, or up to10 objects with name, south, north,
        west, east. Coordinates do not verify location accuracy. Reassign active work before
        changing boundaries.
      </p>
    </>
  )
}
function departmentPayload(form: FormData, version = 0) {
  return {
    code: form.get('code'),
    name: form.get('name'),
    description: form.get('description'),
    active: form.get('active') === 'on',
    areas: JSON.parse(String(form.get('areas') || '[]')) as unknown,
    expectedVersion: version,
  }
}

export function DepartmentsPage() {
  const loader = useCallback(
    () => Promise.all([workService.departments(), workService.summary()]),
    [],
  )
  const { data, error, loading, retry } = useResource(loader)
  const [operation, setOperation] = useState<Operation | null>(null)
  return (
    <section className={section}>
      <AdminLinks />
      <PageHeader
        title="Municipal departments"
        description="Editable demonstration responsibilities, trusted officer memberships and real work queues. No actual municipality is implied."
      />
      <div className="flex flex-wrap gap-3">
        <button
          className={button}
          onClick={() =>
            setOperation({
              title: 'Create department',
              path: '/admin/departments',
              fields: <DepartmentFields />,
              payload: (form) => departmentPayload(form),
            })
          }
        >
          Create department
        </button>
        <button
          className={button}
          onClick={() =>
            setOperation({
              title: 'Seed demonstration departments',
              path: '/admin/departments/seed',
              payload: () => ({}),
            })
          }
        >
          Seed demonstration departments
        </button>
        <button onClick={retry} className="text-teal-700">
          Refresh departments
        </button>
      </div>
      {loading && <Skeleton />}
      {error && <ErrorState message={error} onRetry={retry} />}
      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {Object.entries(data[1]).map(([key, value]) => (
              <Card key={key}>
                <p className="break-words text-xs text-slate-600">
                  {key.replace(/([A-Z])/g, ' $1')}
                </p>
                <p className="mt-2 text-2xl font-bold">{value ?? 'Unavailable'}</p>
              </Card>
            ))}
          </div>
          {!data[0].items.length && (
            <EmptyState title="No departments configured">
              An administrator can seed editable demonstration defaults.
            </EmptyState>
          )}
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {data[0].items.map((d) => (
              <Card key={d.id}>
                <Badge>{d.active ? 'ACTIVE' : 'INACTIVE'}</Badge>
                <h2 className="mt-3 text-lg font-semibold">{d.name}</h2>
                <p className="break-words text-xs text-slate-600">{d.code}</p>
                <p className="mt-3 text-sm">
                  {d.officerCount ?? 'Unavailable'} active officers ·{' '}
                  {d.activeIncidents ?? 'Unavailable'} active incidents ·{' '}
                  {d.highCriticalIncidents ?? 'Unavailable'} fresh high/critical ·{' '}
                  {d.pendingPriorityIncidents ?? 'Unavailable'} pending priorities
                </p>
                <Link
                  to={`/admin/departments/${d.id}`}
                  className="mt-4 inline-block font-semibold text-teal-700"
                >
                  View department details
                </Link>
              </Card>
            ))}
          </div>
        </>
      )}
      {operation && (
        <WorkConfirmation
          operation={operation}
          onClose={() => setOperation(null)}
          onSaved={retry}
        />
      )}
    </section>
  )
}

export function WorkloadCard({ officer }: { officer: Officer }) {
  const utilization = officer.capacity ? officer.workload / officer.capacity : null
  return (
    <Card>
      <h3 className="font-semibold">{officer.displayName}</h3>
      {officer.projectedWorkload !== undefined && (
        <p className="mt-2 text-xs text-slate-600">
          Recommendation comparison excludes this incident from existing work; projected total after
          assignment: {officer.projectedWorkload} units.
        </p>
      )}
      <div className="my-2 flex flex-wrap gap-2">
        <Badge>{officer.availability}</Badge>
        <Badge>
          {officer.active && officer.eligibleAccount
            ? 'ELIGIBLE MEMBERSHIP'
            : 'INACTIVE / INELIGIBLE'}
        </Badge>
      </div>
      <p className="text-sm">
        {officer.activeIncidents} active incidents · {officer.workload} weighted units · capacity{' '}
        {officer.capacity ?? 'unknown'}
      </p>
      {utilization !== null ? (
        <>
          <progress
            className="mt-3 w-full"
            aria-label={`${officer.displayName} weighted utilization`}
            max={100}
            value={Math.min(100, utilization * 100)}
          />
          <p className="text-xs">
            {Math.round(utilization * 100)}% weighted utilization
            {utilization > 1 ? ' — over capacity' : ''}
          </p>
        </>
      ) : (
        <p className="mt-2 text-xs">Unknown capacity: manual approval only.</p>
      )}
      {!!officer.pendingPriorities && (
        <p className="mt-2 text-xs">
          {officer.pendingPriorities} stale/pending priorities conservatively charged maximum
          weight.
        </p>
      )}
      {officer.explanation && <p className="mt-2 text-xs text-slate-600">{officer.explanation}</p>}
    </Card>
  )
}

export function DepartmentDetailsPage() {
  const { departmentId = '' } = useParams()
  const loader = useCallback(
    () => Promise.all([workService.department(departmentId), workService.directory()]),
    [departmentId],
  )
  const { data, error, loading, retry } = useResource(loader)
  const [operation, setOperation] = useState<Operation | null>(null)
  const [directoryAfter, setDirectoryAfter] = useState('')
  const directoryLoader = useCallback(() => workService.directory(directoryAfter), [directoryAfter])
  const directory = useResource(directoryLoader)
  function memberOperation(d: DepartmentDetail, member?: Officer): Operation {
    return {
      title: member ? 'Edit officer membership' : 'Add officer membership',
      path: `/admin/departments/${d.id}/officers`,
      fields: (
        <>
          <Select
            id="membership-officer"
            name="officerId"
            label="Provisioned officer"
            required
            defaultValue={member?.officerId}
          >
            <option value="">Select a trusted officer</option>
            {member ? (
              <option value={member.officerId}>{member.displayName}</option>
            ) : (
              (directory.data?.items ?? data?.[1].items ?? []).map((o) => (
                <option key={o.officerId} value={o.officerId}>
                  {o.displayName} · {o.officerId.slice(0, 8)}
                </option>
              ))
            )}
          </Select>
          <Select
            id="membership-availability"
            name="availability"
            label="Officer availability"
            defaultValue={member?.availability ?? 'AVAILABLE'}
          >
            {['AVAILABLE', 'BUSY', 'UNAVAILABLE', 'ON_LEAVE'].map((a) => (
              <option key={a}>{a}</option>
            ))}
          </Select>
          <Field
            id="membership-capacity"
            name="capacity"
            label="Weighted workload capacity (blank means unknown)"
            type="number"
            min="0.01"
            max="10000"
            step="0.01"
            defaultValue={member?.capacity ?? ''}
          />
          <Textarea
            id="membership-areas"
            name="areas"
            label="Officer service-area rectangles (JSON)"
            defaultValue={JSON.stringify(member?.areas ?? [])}
          />
          <label className="flex gap-2 text-sm">
            <input type="checkbox" name="active" defaultChecked={member?.active ?? true} />
            Active membership
          </label>
        </>
      ),
      payload: (form) => ({
        officerId: form.get('officerId'),
        expectedVersion: member?.version ?? 0,
        availability: form.get('availability'),
        capacity: form.get('capacity') ? Number(form.get('capacity')) : null,
        areas: JSON.parse(String(form.get('areas') || '[]')) as unknown,
        active: form.get('active') === 'on',
      }),
    }
  }
  return (
    <section className={section}>
      <AdminLinks />
      {loading && <Skeleton />}
      {error && <ErrorState message={error} onRetry={retry} />}
      {data && (
        <>
          <PageHeader
            title={data[0].name}
            description={`${data[0].code} · ${data[0].active ? 'Active' : 'Inactive'} · version ${data[0].version}`}
          />
          <p>{data[0].description}</p>
          <p className="text-sm">
            Jurisdiction:{' '}
            {data[0].areas.length
              ? data[0].areas.map((a) => a.name).join(', ')
              : 'Category-based demonstration; not geographically verified'}
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              className={button}
              onClick={() =>
                setOperation({
                  title: 'Edit department',
                  path: `/admin/departments/${departmentId}`,
                  method: 'PATCH',
                  fields: <DepartmentFields department={data[0]} />,
                  payload: (form) => departmentPayload(form, data[0].version),
                })
              }
            >
              Edit department
            </button>
            <button className={button} onClick={() => setOperation(memberOperation(data[0]))}>
              Add officer membership
            </button>
            <button className="text-teal-700" onClick={retry}>
              Refresh department
            </button>
          </div>
          {directory.data?.nextAfter && (
            <button
              className="text-sm text-teal-700"
              onClick={() => setDirectoryAfter(directory.data!.nextAfter!)}
            >
              Load next provisioned officers for membership selector
            </button>
          )}
          {directoryAfter && (
            <button className="text-sm text-teal-700" onClick={() => setDirectoryAfter('')}>
              First officer directory page
            </button>
          )}
          <h2 className="text-xl font-semibold">Officer availability and workload</h2>
          <Alert>
            Weights LOW/MEDIUM/HIGH/CRITICAL default to1/2/3/4 experimental units, not labor hours.{' '}
            {data[0].workload.policy}
          </Alert>
          {!data[0].officers.length && (
            <EmptyState title="No officer memberships">
              Provision OFFICER accounts through the trusted local command, then add membership
              here.
            </EmptyState>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {data[0].officers.map((o) => (
              <div key={o.officerId} className="space-y-2">
                <WorkloadCard officer={o} />
                <div className="flex flex-wrap gap-4">
                  <button
                    className="text-sm text-teal-700"
                    onClick={() => setOperation(memberOperation(data[0], o))}
                  >
                    Edit membership for {o.displayName}
                  </button>
                  <button
                    className="text-sm text-red-800"
                    onClick={() =>
                      setOperation({
                        title: 'Remove officer membership',
                        path: `/admin/departments/${departmentId}/officers/${o.officerId}`,
                        method: 'DELETE',
                        payload: () => ({ expectedVersion: o.version }),
                      })
                    }
                  >
                    Remove membership for {o.displayName}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <h2 className="text-xl font-semibold">Routing rules</h2>
          {data[0].rebalancing && (
            <Card>
              <h2 className="text-xl font-semibold">Workload rebalancing review</h2>
              <p className="mt-2 text-sm">{data[0].rebalancing.message}</p>
              {data[0].rebalancing.proposals.length ? (
                data[0].rebalancing.proposals.map((p) => (
                  <p key={p.incidentId} className="mt-3 break-words text-sm">
                    {p.reason} From {p.fromOfficerId.slice(0, 8)} to {p.toOfficerId.slice(0, 8)}.{' '}
                    <Link className="text-teal-700" to={`/admin/assignments/${p.incidentId}`}>
                      Review suggested transfer
                    </Link>
                  </p>
                ))
              ) : (
                <p className="mt-2 text-sm">
                  No safe advisory move found in the bounded unstarted-work sample.
                </p>
              )}
            </Card>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            {data[0].rules.map((r) => (
              <Card key={r.id}>
                <p>
                  {categories[r.category as keyof typeof categories] ?? r.category} · precedence{' '}
                  {r.precedence} · {r.active ? 'active' : 'inactive'}
                </p>
                <button
                  className="mt-2 text-sm text-teal-700"
                  onClick={() =>
                    setOperation({
                      title: 'Edit routing rule',
                      path: '/admin/routing-rules',
                      fields: (
                        <>
                          <Field
                            id="rule-precedence"
                            name="precedence"
                            label="Rule precedence (lower wins)"
                            type="number"
                            min={0}
                            max={1000}
                            defaultValue={r.precedence}
                            required
                          />
                          <label className="flex gap-2">
                            <input type="checkbox" name="active" defaultChecked={r.active} />
                            Active rule
                          </label>
                        </>
                      ),
                      payload: (f) => ({
                        category: r.category,
                        departmentId,
                        precedence: Number(f.get('precedence')),
                        active: f.get('active') === 'on',
                        expectedVersion: r.version,
                      }),
                    })
                  }
                >
                  Edit rule
                </button>
              </Card>
            ))}
          </div>
          <button
            className={button}
            onClick={() =>
              setOperation({
                title: 'Add routing rule',
                path: '/admin/routing-rules',
                fields: (
                  <>
                    <Select id="rule-category" name="category" label="Routing category">
                      {Object.entries(categories).map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </Select>
                    <Field
                      id="new-rule-precedence"
                      name="precedence"
                      label="Rule precedence (lower wins)"
                      type="number"
                      min={0}
                      max={1000}
                      defaultValue={100}
                      required
                    />
                  </>
                ),
                payload: (f) => ({
                  category: f.get('category'),
                  departmentId,
                  precedence: Number(f.get('precedence')),
                  active: true,
                  expectedVersion: 0,
                }),
              })
            }
          >
            Add routing rule
          </button>
          <WorkQueue departmentId={departmentId} />
          <WorkHistoryPanel id={departmentId} department />
        </>
      )}
      {operation && (
        <WorkConfirmation
          operation={operation}
          onClose={() => setOperation(null)}
          onSaved={retry}
        />
      )}
    </section>
  )
}

export function WorkQueue({
  officer = false,
  departmentId,
}: {
  officer?: boolean
  departmentId?: string
}) {
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState<string | null>(null)
  const [unassigned, setUnassigned] = useState(false)
  const loader = useCallback(
    () =>
      workService.queue(
        query + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''),
        officer,
        departmentId,
        unassigned,
      ),
    [query, cursor, officer, departmentId, unassigned],
  )
  const { data, error, loading, retry } = useResource(loader)
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new URLSearchParams()
    for (const [k, v] of new FormData(event.currentTarget)) if (String(v)) values.set(k, String(v))
    setQuery(values.toString())
    setCursor(null)
    retry()
  }
  return (
    <div id={officer ? 'assigned-work' : undefined} className="space-y-5 scroll-mt-28">
      <h2 className="text-xl font-semibold">
        {officer
          ? 'Assigned incident queue'
          : departmentId
            ? 'Department work queue'
            : 'Municipal assignment queue'}
      </h2>
      <p className="text-sm text-slate-600">
        Verified urgent hazards first. Pending priority work is flagged for review; otherwise Phase8
        effective priority, unresolved time and stable incident ID determine order.
      </p>
      <Card>
        <form onSubmit={filter} className="grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Select id="work-filter-status" label="Work status" name="status">
            <option value="">All work states</option>
            {statusOptions.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
          <Select id="work-filter-band" label="Work priority band" name="band">
            <option value="">All bands</option>
            {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((b) => (
              <option key={b}>{b}</option>
            ))}
          </Select>
          <Select id="work-filter-category" label="Work category" name="category">
            <option value="">All categories</option>
            {Object.entries(categories).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
          <Select id="work-filter-urgent" label="Verified hazard filter" name="urgent">
            <option value="">All hazards</option>
            <option value="true">Urgent hazards only</option>
            <option value="false">Without urgent flag</option>
          </Select>
          <button className={button} type="submit">
            Filter work queue
          </button>
          <button
            type="button"
            onClick={() => {
              setCursor(null)
              retry()
            }}
            className="text-teal-700"
          >
            Refresh work queue
          </button>
          {!officer && !departmentId && (
            <label className="flex gap-2 text-sm">
              <input
                type="checkbox"
                checked={unassigned}
                onChange={(e) => {
                  setUnassigned(e.target.checked)
                  setCursor(null)
                }}
              />
              Only unassigned or review work
            </label>
          )}
        </form>
      </Card>
      {loading && <Skeleton />}
      {error && (
        <ErrorState
          message={error}
          onRetry={() => {
            setCursor(null)
            retry()
          }}
        />
      )}
      {data && (
        <>
          {officer ? (
            <div className="metric-grid grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[
                ['My assigned incidents', data.workload?.activeIncidents ?? data.stats.assigned],
                [
                  'High priority',
                  Number.isFinite(data.stats.high) && Number.isFinite(data.stats.critical)
                    ? data.stats.high + data.stats.critical
                    : 'Unavailable',
                ],
                ['In progress', data.stats.inProgress],
                [
                  'Awaiting review',
                  data.items.filter((item) => item.assignment.status === 'NEEDS_REVIEW').length,
                ],
              ].map(([label, value]) => (
                <Card key={String(label)} className="stat-card">
                  <p className="text-sm text-slate-600">{label}</p>
                  <p className="mt-3 text-3xl font-semibold">{value ?? 'Unavailable'}</p>
                  <p className="mt-2 text-xs text-slate-500">
                    {label === 'Awaiting review'
                      ? 'On this filtered queue page'
                      : 'From your work queue'}
                  </p>
                </Card>
              ))}
              {data.workload && (
                <p className="col-span-full text-xs text-slate-500">
                  <span>My global weighted workload: {data.workload.workload} units</span> ·
                  Experimental workload units, not labor hours.
                </p>
              )}
            </div>
          ) : (
            <div className="flex flex-wrap gap-3 text-sm">
              {Object.entries(data.stats).map(([k, v]) => (
                <Badge key={k}>
                  {k.replace(/([A-Z])/g, ' $1')}: {v ?? 'Unavailable'}
                </Badge>
              ))}
            </div>
          )}
          {!data.items.length && (
            <EmptyState title="No work matches this queue">
              No assignment is fabricated. Administrators can review routing and allocate eligible
              officers.
            </EmptyState>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            {data.items.map((item) => (
              <Card key={item.incidentId}>
                <div className="flex flex-wrap gap-2">
                  <Badge>{item.assignment.status}</Badge>
                  <PriorityBadge band={item.priority?.priorityBand} stale={item.priorityStale} />
                  {!item.priorityStale && item.priority && (
                    <span className="text-xs text-slate-500">
                      {item.priority.effectiveScore}/100
                    </span>
                  )}
                  {item.priority?.urgentHazard && !item.priorityStale && (
                    <Badge>VERIFIED URGENT HAZARD</Badge>
                  )}
                </div>
                <h3 className="mt-3 text-lg font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm">
                  {item.category} · {item.departmentName ?? 'Department unassigned'}
                </p>
                <p className="mt-2 text-xs text-slate-600">
                  {item.latitude}, {item.longitude} · Assigned{' '}
                  {item.assignment.assignedAt ? formatDate(item.assignment.assignedAt) : 'not yet'}{' '}
                  · progress {item.assignment.percentage}%
                </p>
                <Link
                  className="mt-4 inline-block font-semibold text-teal-700"
                  to={
                    officer
                      ? `/officer/incidents/${item.incidentId}`
                      : `/admin/assignments/${item.incidentId}`
                  }
                >
                  {officer ? 'Open assigned incident' : 'Review assignment'}
                </Link>
              </Card>
            ))}
          </div>
          <div className="flex gap-4">
            <button className="text-teal-700" disabled={!cursor} onClick={() => setCursor(null)}>
              First work page
            </button>
            {data.nextCursor && (
              <button className={button} onClick={() => setCursor(data.nextCursor)}>
                Next work page
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export function AssignmentsPage() {
  return (
    <section className={section}>
      <AdminLinks />
      <PageHeader
        title="Intelligent work allocation"
        description="Route incidents to the right department and review officer capacity before confirming an assignment."
      />
      <WorkQueue />
    </section>
  )
}
export function OfficerDashboard() {
  return (
    <section className={section}>
      <PageHeader
        title="Officer dashboard"
        description="Your assignments, priorities, and recorded work progress in one focused workspace."
      />
      <WorkQueue officer />
    </section>
  )
}

export function WorkHistoryPanel({
  id,
  officer = false,
  department = false,
}: {
  id: string
  officer?: boolean
  department?: boolean
}) {
  const [cursor, setCursor] = useState<string | undefined>()
  const loader = useCallback(
    () => workService.history(id, officer, department, cursor),
    [id, officer, department, cursor],
  )
  const { data, error, loading, retry } = useResource(loader)
  return (
    <Card>
      <h2 className="mb-4 text-xl font-semibold">
        {officer ? 'My private work progress history' : 'Assignment and configuration history'}
      </h2>
      {loading && <Skeleton />}
      {error && <ErrorState message={error} onRetry={retry} />}
      {data && (
        <>
          <ol className="space-y-4">
            {data.items.map((h) => (
              <li className="border-l-2 border-teal-200 pl-4" key={h.eventId}>
                <p className="font-semibold">{h.kind}</p>
                <p className="text-xs text-slate-600">{formatDate(h.createdAt)}</p>
                <p className="mt-1 break-words text-sm">{h.reason}</p>
                {h.after.note && <p className="mt-1 break-words text-sm">{h.after.note}</p>}
                {h.after.status && <Badge>{h.after.status}</Badge>}
              </li>
            ))}
          </ol>
          {!data.items.length && <p className="text-sm text-slate-600">No recorded events.</p>}
          <div className="mt-4 flex gap-3">
            {cursor && (
              <button className="text-teal-700" onClick={() => setCursor(undefined)}>
                First history page
              </button>
            )}
            {data.nextCursor && (
              <button
                className="text-teal-700"
                onClick={() => setCursor(data.nextCursor ?? undefined)}
              >
                Next history page
              </button>
            )}
          </div>
        </>
      )}
    </Card>
  )
}

function AssignmentFields({
  state,
  departments,
}: {
  state: WorkDetail
  departments: Department[]
}) {
  return (
    <>
      <Select
        id="assign-department"
        label="Confirmed responsible department"
        name="departmentId"
        defaultValue={state.assignment.departmentId ?? ''}
      >
        <option value="">Unassigned department / review</option>
        {departments
          .filter((d) => d.active)
          .map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
      </Select>
      <Field
        id="assign-officer"
        label="Eligible officer ID (blank removes officer)"
        name="officerId"
        defaultValue={state.assignment.officerId ?? ''}
      />
      <p className="text-xs">
        Copy a recommended officer ID below. For another department, confirm responsibility first
        and refresh recommendations. Backend rechecks all constraints at commit.
      </p>
      <label className="flex gap-2 text-sm">
        <input type="checkbox" name="review" />
        Return to administrative review
      </label>
      <label className="flex gap-2 text-sm">
        <input type="checkbox" name="capacityOverride" />
        Explicitly override weighted capacity only (explain why)
      </label>
    </>
  )
}

export function AssignmentDetailsPage({ officer = false }: { officer?: boolean }) {
  const { incidentId = '' } = useParams()
  const loader = useCallback(
    () =>
      Promise.all([
        workService.detail(incidentId, officer),
        officer ? Promise.resolve({ items: [] as Department[] }) : workService.departments(),
      ]),
    [incidentId, officer],
  )
  const { data, error, loading, retry } = useResource(loader)
  const [operation, setOperation] = useState<Operation | null>(null)
  const [historyKey, setHistoryKey] = useState(0)
  const saved = () => {
    retry()
    setHistoryKey((v) => v + 1)
  }
  function begin(state: WorkDetail, kind: string) {
    const base = {
      expectedIncidentVersion: state.incidentVersion,
      expectedAssignmentVersion: state.assignment.version,
    }
    if (officer)
      setOperation({
        title: kind === 'start' ? 'Start assigned work' : 'Record work progress',
        path: `/officer/incidents/${incidentId}/${kind}`,
        fields: (
          <>
            <Textarea
              id="progress-note"
              label="Private operational progress note"
              name="note"
              required
              minLength={10}
              maxLength={2000}
            />
            <Field
              id="progress-percentage"
              label="Work percentage (not verified resolution)"
              name="percentage"
              type="number"
              min={state.assignment.percentage}
              max={100}
              required
              defaultValue={state.assignment.percentage}
            />
            <label className="flex gap-2 text-sm">
              <input type="checkbox" name="requestReview" />
              Blocked work: request administrative review
            </label>
          </>
        ),
        payload: (f) => ({
          ...base,
          note: f.get('note'),
          percentage: Number(f.get('percentage')),
          requestReview: f.get('requestReview') === 'on',
        }),
      })
    else
      setOperation({
        title:
          kind === 'assign-department'
            ? 'Route department automatically'
            : kind === 'unassign-officer'
              ? 'Unassign officer'
              : 'Assign or reassign municipal work',
        path: `/admin/incidents/${incidentId}/${kind}`,
        fields:
          kind === 'reassign' ? (
            <AssignmentFields state={state} departments={data?.[1].items ?? []} />
          ) : undefined,
        payload: (f) =>
          kind === 'reassign'
            ? {
                ...base,
                departmentId: f.get('departmentId') || null,
                officerId: f.get('officerId') || null,
                review: f.get('review') === 'on',
                capacityOverride: f.get('capacityOverride') === 'on',
              }
            : base,
      })
  }
  return (
    <section className={section}>
      {officer ? (
        <Link className="text-teal-700" to="/officer/dashboard">
          ← My work queue
        </Link>
      ) : (
        <AdminLinks />
      )}
      {loading && <Skeleton />}
      {error && <ErrorState message={error} onRetry={retry} />}
      {data && (
        <>
          <PageHeader
            title={data[0].title}
            description={`${data[0].category} · ${data[0].latitude}, ${data[0].longitude} · canonical lifecycle ${data[0].incidentStatus}`}
          />
          {officer && (
            <Link
              className="inline-block font-semibold text-teal-700"
              to={`/officer/incidents/${incidentId}/repair`}
            >
              Submit repair evidence and view verification history
            </Link>
          )}
          <Card>
            <div className="flex flex-wrap gap-2">
              <Badge>{data[0].assignment.status}</Badge>
              <Badge>
                {data[0].priorityStale
                  ? 'PRIORITY PENDING / STALE'
                  : `${data[0].priority?.effectiveScore}/100 · ${data[0].priority?.priorityBand}`}
              </Badge>
              {data[0].priority?.urgentHazard && !data[0].priorityStale && (
                <Badge>VERIFIED URGENT HAZARD</Badge>
              )}
            </div>
            <dl className="detail-grid mt-4">
              <dt>Confirmed department</dt>
              <dd>{data[0].department?.name ?? 'Unassigned'}</dd>
              <dt>Assigned officer</dt>
              <dd className="break-all">{data[0].assignment.officerId ?? 'No officer assigned'}</dd>
              <dt>Work progress</dt>
              <dd>{data[0].assignment.percentage}% — not verified resolution</dd>
              <dt>Assignment method</dt>
              <dd>{data[0].assignment.method ?? 'None'}</dd>
            </dl>
            <div className="mt-5 flex flex-wrap gap-3">
              {officer ? (
                <>
                  {data[0].assignment.status === 'OFFICER_ASSIGNED' && (
                    <button className={button} onClick={() => begin(data[0], 'start')}>
                      Start work
                    </button>
                  )}
                  {data[0].assignment.status === 'IN_PROGRESS' && (
                    <button className={button} onClick={() => begin(data[0], 'progress')}>
                      Record progress
                    </button>
                  )}
                </>
              ) : (
                <>
                  <button className={button} onClick={() => begin(data[0], 'assign-department')}>
                    Route department automatically
                  </button>
                  <button className={button} onClick={() => begin(data[0], 'reassign')}>
                    Assign or reassign work
                  </button>
                  {data[0].assignment.officerId && (
                    <button className={button} onClick={() => begin(data[0], 'unassign-officer')}>
                      Unassign officer
                    </button>
                  )}
                  <Link className="text-teal-700" to={`/admin/incidents/${incidentId}`}>
                    Master incident and priority evidence
                  </Link>
                </>
              )}
              <button className="text-teal-700" onClick={saved}>
                Refresh assignment
              </button>
            </div>
          </Card>
          {!officer && (
            <>
              <Card>
                <h2 className="text-xl font-semibold">
                  Suggested responsibility — not a confirmed assignment
                </h2>
                <p className="mt-2">
                  {data[1].items.find((d) => d.id === data[0].suggestedRouting?.departmentId)
                    ?.name ?? 'No covered department'}
                </p>
                <p className="text-sm">
                  {data[0].suggestedRouting?.mode} · rule version{' '}
                  {data[0].suggestedRouting?.ruleVersion}
                </p>
                {data[0].suggestedRouting?.explanation.map((e) => (
                  <p className="mt-2 text-sm" key={e}>
                    {e}
                  </p>
                ))}
              </Card>
              <h2 className="text-xl font-semibold">
                Recommended officers — awaiting administrator approval
              </h2>
              <p className="text-sm">
                Incoming workload: {data[0].recommendations?.incomingUnits ?? 'unknown'} units.
                Capacity and availability are checked again in the assignment transaction.
              </p>
              {!data[0].recommendations?.ranked.length && (
                <EmptyState title="No eligible officer recommendation">
                  {data[0].recommendations?.message ??
                    'Check memberships, availability, jurisdiction and capacity. Work remains visible for manual review.'}
                </EmptyState>
              )}
              <div className="grid gap-4 md:grid-cols-2">
                {data[0].recommendations?.ranked.map((o) => (
                  <div key={o.officerId}>
                    <WorkloadCard officer={o} />
                    <p className="mt-2 break-all text-xs">Officer ID: {o.officerId}</p>
                  </div>
                ))}
              </div>
              {data[0].recommendations?.excluded.map((o) => (
                <p className="break-words text-xs text-slate-600" key={o.officerId}>
                  Excluded {o.officerId.slice(0, 8)}: {o.reasons.join('; ')}
                </p>
              ))}
            </>
          )}
          {officer && !!data[0].evidence?.length && (
            <Card>
              <h2 className="mb-3 text-xl font-semibold">Authorized supporting photographs</h2>
              <ComplaintImageGallery
                images={data[0].evidence.map((photo) => ({
                  imageId: photo.imageId,
                  url: `/officer/incidents/${incidentId}/complaints/${photo.complaintId}/images/${photo.imageId}`,
                  requiresAuth: true,
                  alt: 'Authorized supporting photograph for assigned infrastructure work',
                }))}
              />
            </Card>
          )}
          <WorkHistoryPanel key={historyKey} id={incidentId} officer={officer} />
        </>
      )}
      {operation && (
        <WorkConfirmation
          operation={operation}
          onClose={() => setOperation(null)}
          onSaved={saved}
        />
      )}
    </section>
  )
}
