import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Publication } from '../../types/complaint'
import { discoveryService } from '../../services/discoveryService'
import { Card } from '../common/UI'
import { FormMessage } from '../common/FormParts'

export function PublicationControls({
  complaintId,
  initial,
}: {
  complaintId: string
  initial?: Publication
}) {
  const [value, setValue] = useState<Publication>(
    initial ?? {
      citizenRequestedPublication: false,
      publicationStatus: 'PRIVATE',
      publicIssueId: null,
    },
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function change(requested: boolean) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      setValue(await discoveryService.requestPublication(complaintId, requested))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Publication request failed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card>
      <h2 className="text-lg font-semibold">Public map publication</h2>
      <p className="mt-3 text-sm">
        Publication status: {value.publicationStatus.replaceAll('_', ' ')}
      </p>
      <p className="mt-3 text-sm leading-7 text-slate-600">
        Your complaint stays private by default. You may request a public map entry. An
        administrator must review a separate public summary and approximate coordinates. Reporter
        identity and private photographs are never published. You can withdraw consent at any time.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => void change(!value.citizenRequestedPublication)}
        >
          {busy
            ? 'Saving publication request…'
            : value.citizenRequestedPublication
              ? 'Withdraw publication request'
              : 'Request public map publication'}
        </button>
        {value.publicationStatus === 'PUBLISHED' && value.publicIssueId && (
          <Link className="font-semibold text-teal-700" to={`/issues/${value.publicIssueId}`}>
            View approved public issue
          </Link>
        )}
      </div>
      <FormMessage error={error} />
    </Card>
  )
}
