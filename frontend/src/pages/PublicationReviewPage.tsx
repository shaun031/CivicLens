import { useState, type FormEvent } from 'react'
import { discoveryService } from '../services/discoveryService'
import { Field, FormMessage } from '../components/common/FormParts'
import { Card, PageHeader, Select, Textarea } from '../components/common/UI'

export function PublicationReviewPage() {
  const [complaintId, setComplaintId] = useState('')
  const [decision, setDecision] = useState<'APPROVE' | 'REJECT' | 'UNPUBLISH'>('APPROVE')
  const [summary, setSummary] = useState('')
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [reviewed, setReviewed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    setSuccess(null)
    try {
      const result = await discoveryService.reviewPublication(complaintId.trim(), {
        decision,
        ...(decision === 'APPROVE'
          ? {
              publicSummary: summary.trim(),
              publicLatitude: Number(latitude),
              publicLongitude: Number(longitude),
              reviewedForPrivacy: reviewed,
            }
          : {}),
      })
      setSuccess('Audited publication decision saved: ' + result.publicationStatus)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Publication review failed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="mx-auto max-w-3xl space-y-6 px-4 py-12 sm:px-6">
      <PageHeader
        title="Publication review"
        description="Review a citizen’s publication request. Public summaries and approximate coordinates require a privacy review before approval."
      />
      <Card>
        <form onSubmit={(event) => void submit(event)}>
          <fieldset disabled={busy} className="space-y-4">
            <Field
              id="review-id"
              label="Complaint ID"
              required
              pattern="[0-9a-fA-F-]{36}"
              value={complaintId}
              onChange={(event) => setComplaintId(event.target.value)}
            />
            <Select
              id="review-decision"
              label="Decision"
              value={decision}
              onChange={(event) => setDecision(event.target.value as typeof decision)}
            >
              <option value="APPROVE">Approve</option>
              <option value="REJECT">Reject</option>
              <option value="UNPUBLISH">Unpublish</option>
            </Select>
            {decision === 'APPROVE' && (
              <>
                <Textarea
                  id="public-summary"
                  label="Reviewed public summary"
                  required
                  minLength={15}
                  maxLength={300}
                  value={summary}
                  onChange={(event) => setSummary(event.target.value)}
                />
                <Field
                  id="public-latitude"
                  label="Public latitude"
                  type="number"
                  step="any"
                  min={-90}
                  max={90}
                  required
                  value={latitude}
                  onChange={(event) => setLatitude(event.target.value)}
                />
                <Field
                  id="public-longitude"
                  label="Public longitude"
                  type="number"
                  step="any"
                  min={-180}
                  max={180}
                  required
                  value={longitude}
                  onChange={(event) => setLongitude(event.target.value)}
                />
                <label className="flex items-start gap-3 text-sm">
                  <input
                    type="checkbox"
                    required
                    checked={reviewed}
                    onChange={(event) => setReviewed(event.target.checked)}
                  />
                  I reviewed the summary and general location for privacy and removed personal
                  information.
                </label>
              </>
            )}
            <button className="action-link" type="submit">
              {busy ? 'Saving review…' : 'Save audited decision'}
            </button>
          </fieldset>
          <FormMessage error={error} success={success} />
        </form>
      </Card>
    </section>
  )
}
