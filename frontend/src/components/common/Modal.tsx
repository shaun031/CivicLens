import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { Button } from './Button'

// Native modal dialog provides focus containment, background inertness, and Escape handling.
export function Modal({
  title,
  children,
  onClose,
  drawer = false,
}: {
  title: string
  children: ReactNode
  onClose: () => void
  drawer?: boolean
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const element = dialog.current
    const previous = document.activeElement as HTMLElement | null
    element?.showModal()
    return () => {
      element?.close()
      previous?.focus()
    }
  }, [])
  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Tab') return
        const controls = Array.from(
          dialog.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
          ) ?? [],
        )
        const first = controls[0]
        const last = controls.at(-1)
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first?.focus()
        }
      }}
      className={`civic-modal ${drawer ? 'navigation-drawer' : ''}`}
    >
      <div className="mb-5 flex items-start justify-between gap-4">
        <h2 id={titleId} className="text-xl font-bold">
          {title}
        </h2>
        <button className="text-sm font-semibold text-teal-700" onClick={onClose}>
          Close
        </button>
      </div>
      {children}
    </dialog>
  )
}
export function ConfirmDialog({
  onConfirm,
  onClose,
}: {
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Modal title="Clear your local draft?" onClose={onClose}>
      <p className="mb-5 text-slate-600">
        This clears your browser draft, not saved complaints. If an earlier submission timed out,
        check My Complaints before starting over.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button onClick={onConfirm}>Clear draft</Button>
        <button onClick={onClose}>Keep editing</button>
      </div>
    </Modal>
  )
}
