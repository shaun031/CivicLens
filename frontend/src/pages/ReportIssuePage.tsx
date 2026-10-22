import { lazy, Suspense, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { LocateFixed } from 'lucide-react'
import { useCitizen } from '../auth/CitizenContext'
import { useGeolocation } from '../hooks/useGeolocation'
import { categories, emptyDraft } from '../types/complaint'
import type { Complaint } from '../types/complaint'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { complaintService } from '../services/complaintService'
import type { ComplaintDraft, Severity } from '../types/complaint'
import { validCoordinates, validateDraft } from '../utils/validation'
import { Button } from '../components/common/Button'
import { Field, FormMessage } from '../components/common/FormParts'
import {
  Alert,
  Breadcrumbs,
  Card,
  InlineError,
  PageHeader,
  Select,
  Skeleton,
  Textarea,
} from '../components/common/UI'
import { ConfirmDialog, Modal } from '../components/common/Modal'
import { ComplaintCategorySelector } from '../components/complaints/ComplaintComponents'
import { ImageUpload } from '../components/complaints/ImageUpload'
import { LocationSearch } from '../components/complaints/LocationSearch'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
const ComplaintMap = lazy(() => import('../components/complaints/ComplaintMap'))

export function ReportIssuePage() {
  const { draft, setDraft, demo, setDemo, setNearbySearch } = useCitizen()
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)
  const locked = useRef(false)
  const [submissionError, setSubmissionError] = useState<string | null>(null)
  const [created, setCreated] = useState<Complaint | null>(null)
  const [errors, setErrors] = useState<Partial<Record<keyof ComplaintDraft, string>>>({})
  const [preview, setPreview] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const form = useRef<HTMLFormElement>(null)
  function update<K extends keyof ComplaintDraft>(key: K, value: ComplaintDraft[K]) {
    if (locked.current) return
    setDraft((current) => ({ ...current, [key]: value, requestKey: crypto.randomUUID() }))
    setErrors((current) => ({ ...current, [key]: undefined }))
  }
  function selectLocation(latitude: number, longitude: number) {
    if (locked.current || !validCoordinates(String(latitude), String(longitude))) return
    setDraft((current) => ({
      ...current,
      requestKey: crypto.randomUUID(),
      latitude: latitude.toFixed(6),
      longitude: longitude.toFixed(6),
    }))
    setErrors((current) => ({ ...current, latitude: undefined, longitude: undefined }))
  }
  const geo = useGeolocation(selectLocation)
  function valid() {
    const problems = validateDraft(draft)
    setErrors(problems)
    if (!Object.keys(problems).length) return true
    else {
      const first = Object.keys(problems)[0]
      form.current?.querySelector<HTMLElement>(`#${first}`)?.focus()
    }
    return false
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (locked.current || geo.busy || !valid()) return
    if (demo || user?.role !== 'CITIZEN') {
      setSubmissionError(
        'Real submissions require a citizen account with sample preview turned off.',
      )
      return
    }
    locked.current = true
    setBusy(true)
    setSubmissionError(null)
    try {
      const result = await complaintService.create(draft)
      setCreated(result)
      setNearbySearch((current) => ({
        ...current,
        center: [result.location.latitude, result.location.longitude],
      }))
      setDraft(emptyDraft())
      setDemo(false)
    } catch (reason) {
      setSubmissionError(
        reason instanceof Error
          ? reason.message
          : 'Submission failed. Your draft has been retained.',
      )
    } finally {
      locked.current = false
      setBusy(false)
    }
  }
  const validity = (key: keyof ComplaintDraft) => ({
    'aria-invalid': Boolean(errors[key]),
    'aria-describedby': errors[key] ? `${key}-error` : undefined,
  })
  const selected = validCoordinates(draft.latitude, draft.longitude)
    ? { latitude: Number(draft.latitude), longitude: Number(draft.longitude) }
    : undefined
  if (created)
    return (
      <>
        <PageHeader
          title="Complaint submitted"
          description="Your complaint and accepted photo evidence have been saved privately."
        />
        <Card>
          <p role="status" className="font-semibold text-emerald-800">
            Submission successful.
          </p>
          <p className="mt-3 text-sm">
            Complaint ID: <strong>{created.complaintId}</strong>
          </p>
          <p className="mt-3 text-sm">Initial status: Submitted. No incident has been assigned.</p>
          <Link
            className="action-link mt-5"
            to={`/citizen/complaints/${encodeURIComponent(created.complaintId)}`}
          >
            View complaint details
          </Link>
          <Link className="secondary-button mt-3" to="/citizen/nearby">
            View on Nearby Issues
          </Link>
        </Card>
        <button className="text-sm font-semibold text-teal-700" onClick={() => setCreated(null)}>
          Report another issue
        </button>
      </>
    )
  return (
    <>
      <Breadcrumbs current="Report an Issue" />
      <PageHeader
        title="Report an Issue"
        description="A small observation can make a big difference. Submit your report with optional private photo evidence."
      />
      <nav aria-label="Report sections" className="report-sections">
        <a href="#problem-information">
          <span>01</span>Problem
        </a>
        <a href="#issue-location">
          <span>02</span>Location
        </a>
        <a href="#issue-evidence">
          <span>03</span>Evidence
        </a>
        <a href="#review-report">
          <span>04</span>Review & submit
        </a>
      </nav>
      <form ref={form} noValidate onSubmit={submit} className="space-y-6">
        <fieldset disabled={busy} className="report-form-grid">
          <Card className="report-section">
            <h2 id="problem-information" className="mb-5 text-lg font-semibold">
              1. Tell us about the issue
            </h2>
            <div className="space-y-5">
              <ComplaintCategorySelector
                value={draft.category}
                onChange={(value) => update('category', value)}
                {...validity('category')}
              />
              <InlineError id="category" message={errors.category} />
              <Field
                id="title"
                label="Complaint title"
                maxLength={150}
                value={draft.title}
                onChange={(event) => update('title', event.target.value)}
                placeholder="e.g. Pothole beside the community library"
                {...validity('title')}
              />
              <InlineError id="title" message={errors.title} />
              <Textarea
                id="description"
                label="Description"
                rows={5}
                maxLength={2000}
                value={draft.description}
                onChange={(event) => update('description', event.target.value)}
                {...validity('description')}
              />
              <InlineError id="description" message={errors.description} />
              <p className="text-xs text-slate-600">
                20–2,000 characters. Describe what you saw and its impact. Avoid personal or
                sensitive information.
              </p>
            </div>
          </Card>
          <Card className="report-section report-location">
            <h2 id="issue-location" className="mb-5 text-lg font-semibold">
              2. Where is the issue?
            </h2>
            <div className="space-y-5">
              <Field
                id="addressLabel"
                label="Location / landmark"
                maxLength={200}
                value={draft.addressLabel}
                onChange={(event) => update('addressLabel', event.target.value)}
                {...validity('addressLabel')}
              />
              <InlineError id="addressLabel" message={errors.addressLabel} />
              <Field
                id="landmark"
                label="Landmark (optional)"
                maxLength={200}
                value={draft.landmark}
                onChange={(event) => update('landmark', event.target.value)}
                {...validity('landmark')}
              />
              <InlineError id="landmark" message={errors.landmark} />
              <button
                type="button"
                className="location-action"
                disabled={geo.busy || busy}
                onClick={geo.locate}
              >
                <LocateFixed size={18} aria-hidden="true" />
                {geo.busy ? 'Locating…' : 'Use my current location'}
              </button>
              <p className="text-xs text-slate-600">
                Permission is requested only when you click. Check that the marker identifies the
                issue, which may differ from your current location. The initial Bengaluru map view
                is not a selected location.
              </p>
              <FormMessage success={geo.message} />
              <LocationSearch onSelect={selectLocation} disabled={busy} />
              <ErrorBoundary>
                <Suspense fallback={<Skeleton />}>
                  <ComplaintMap
                    selection={selected}
                    center={selected ? [selected.latitude, selected.longitude] : undefined}
                    onSelect={selectLocation}
                  />
                </Suspense>
              </ErrorBoundary>
              <section
                aria-label="Selected location"
                className="selected-location"
                aria-live="polite"
              >
                <h3>Selected location</h3>
                {selected ? (
                  <dl>
                    <div>
                      <dt>Latitude</dt>
                      <dd>{selected.latitude.toFixed(6)}</dd>
                    </div>
                    <div>
                      <dt>Longitude</dt>
                      <dd>{selected.longitude.toFixed(6)}</dd>
                    </div>
                  </dl>
                ) : (
                  <p>
                    Click on the map or use your current location to select where the issue
                    occurred.
                  </p>
                )}
              </section>
              <p className="text-sm text-slate-600">
                You can also enter or adjust coordinates manually below.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  id="latitude"
                  label="Latitude"
                  inputMode="decimal"
                  value={draft.latitude}
                  onChange={(event) => update('latitude', event.target.value)}
                  {...validity('latitude')}
                />
                <Field
                  id="longitude"
                  label="Longitude"
                  inputMode="decimal"
                  value={draft.longitude}
                  onChange={(event) => update('longitude', event.target.value)}
                  {...validity('latitude')}
                />
              </div>
              <InlineError id="latitude" message={errors.latitude} />
            </div>
          </Card>
          <Card className="report-section report-evidence">
            <h2 id="issue-evidence" className="mb-5 text-lg font-semibold">
              3. Add context
            </h2>
            <div className="space-y-5">
              <ImageUpload
                files={draft.files}
                onChange={(files) => update('files', files)}
                error={errors.files}
              />
              <Select
                label="User-reported severity"
                id="severity"
                value={draft.reportedSeverity}
                onChange={(event) => update('reportedSeverity', event.target.value as Severity)}
              >
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
              </Select>
              <p className="text-xs text-slate-600">
                Your assessment helps describe the problem. Verified incident priority is assessed
                separately.
              </p>
            </div>
          </Card>
          {!!Object.keys(errors).filter((key) => errors[key as keyof ComplaintDraft]).length && (
            <p role="alert" className="text-sm text-red-800">
              Please correct the highlighted fields before continuing.
            </p>
          )}
          <div id="review-report" className="report-submit-panel">
            <div className="report-readiness">
              <strong>Ready to send?</strong>
              <p>Review your details and any selected photographs before submitting.</p>
            </div>
            <Button type="submit" disabled={busy || geo.busy || demo || user?.role !== 'CITIZEN'}>
              {busy ? 'Submitting...' : 'Submit Complaint'}
            </Button>
            <button
              type="button"
              className="text-sm font-semibold text-teal-700"
              onClick={() => {
                if (valid()) setPreview(true)
              }}
            >
              Preview locally — not submit
            </button>
            <button
              className="text-sm font-semibold text-slate-600"
              type="button"
              onClick={() => setConfirm(true)}
            >
              Clear form
            </button>
          </div>
          {demo && (
            <p className="text-sm text-amber-900">
              Sample preview is enabled. Turn it off to submit a real complaint.
            </p>
          )}
          {user?.role !== 'CITIZEN' && (
            <p className="text-sm text-amber-900">
              Only citizen accounts can submit complaints. Use your role’s workspace for assigned
              work and reviews.
            </p>
          )}
          <FormMessage error={submissionError} />
          <p className="report-draft-note text-xs text-slate-600">
            Your draft stays in memory while navigating this citizen workspace. Reloading or signing
            out clears an unsubmitted draft. Successfully submitted complaints and accepted evidence
            remain in private local storage. If a network error occurs, retry without editing to
            reuse the same idempotency key.
          </p>
        </fieldset>
      </form>
      {confirm && (
        <ConfirmDialog
          onClose={() => setConfirm(false)}
          onConfirm={() => {
            setDraft(emptyDraft())
            setErrors({})
            setConfirm(false)
          }}
        />
      )}
      {preview && (
        <Modal title="Local report preview — not submitted" onClose={() => setPreview(false)}>
          <Alert>
            This preview does not submit or save anything. Previous submissions, if any, are not
            changed.
          </Alert>
          <dl className="detail-grid mt-5">
            <dt>Title</dt>
            <dd>{draft.title}</dd>
            <dt>Category</dt>
            <dd>{draft.category && categories[draft.category]}</dd>
            <dt>Description</dt>
            <dd className="whitespace-pre-wrap">{draft.description}</dd>
            <dt>Location</dt>
            <dd>
              {draft.addressLabel} ({draft.latitude}, {draft.longitude})
            </dd>
            <dt>Reported severity</dt>
            <dd>{draft.reportedSeverity}</dd>
            <dt>Selected images</dt>
            <dd>{draft.files.length} (not uploaded)</dd>
          </dl>
        </Modal>
      )}
    </>
  )
}
