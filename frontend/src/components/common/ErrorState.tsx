import { CircleAlert } from 'lucide-react'
import { Button } from './Button'

type ErrorStateProps = {
  message: string
  title?: string
  onRetry?: () => void
}

export function ErrorState({ message, title = 'Backend unavailable', onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-900">
      <div className="flex items-start gap-3">
        <CircleAlert className="mt-0.5 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-semibold">{title}</p>
          <p className="mt-1 text-sm">{message}</p>
          {onRetry && (
            <Button className="mt-4" onClick={onRetry}>
              Retry connection
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
