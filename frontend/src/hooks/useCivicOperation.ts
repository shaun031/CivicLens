import { useRef, useState } from 'react'

/** Keep an operation ID on transport retries; edited inputs start a new operation. */
export function useCivicOperation() {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const saved = useRef({ fingerprint: '', id: '' })
  async function run(
    body: unknown,
    action: (operationId: string) => Promise<unknown>,
    complete: () => void,
  ) {
    const fingerprint = JSON.stringify(body)
    if (saved.current.fingerprint !== fingerprint)
      saved.current = { fingerprint, id: crypto.randomUUID() }
    setBusy(true)
    setMessage('')
    setError('')
    try {
      await action(saved.current.id)
      setMessage('Saved by the backend. Refreshing the recorded state.')
      saved.current = { fingerprint: '', id: '' }
      complete()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Operation failed. Retry the same input.')
    } finally {
      setBusy(false)
    }
  }
  return { busy, message, error, run }
}
