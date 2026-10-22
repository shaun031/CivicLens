import { LoaderCircle } from 'lucide-react'

export function LoadingState({ message = 'Loading…' }: { message?: string }) {
  return (
    <div
      role="status"
      className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-5 text-slate-600"
    >
      <LoaderCircle className="animate-spin text-civic-600" aria-hidden="true" />
      <span>{message}</span>
    </div>
  )
}
